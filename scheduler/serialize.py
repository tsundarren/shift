"""Conversions between plain database-style rows and the domain model. Pure Python: no database, no web framework.

Database ids are integers; domain ids are strings ("e12", "r3"). Row shapes (plain dicts):

  rotation: {id, name, weekdays: [0..6], max_trainees, blocks: [{name, start_min, end_min, headcount}]}
  employee: {id, name, rank, color, max_hours_week, target_hours_week,
             rotations: [{rotation_id, level}]          level: training | trained | trainer
             availability: [{weekday, start_min, end_min}],
             time_off: [{date, kind}]}                  kind: approved | preferred

Time off is stored as calendar dates and becomes day indexes relative to a schedule's start date.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from .metrics import quality_report
from .models import Block, Employee, Horizon, Instance, Interval, Rotation, RuleConfig, Schedule
from .overrides import STATIC_CODES, WEEKDAYS, find_blockers, hhmm
from .validate import validate

LEVELS = ("training", "trained", "trainer")
TIME_OFF_KINDS = ("approved", "preferred")


def eid(pk: int) -> str:
    return f"e{pk}"


def rid(pk: int) -> str:
    return f"r{pk}"


def parse_id(text: str, prefix: str) -> int:
    if not isinstance(text, str) or not text.startswith(prefix) or not text[len(prefix):].isdigit():
        raise ValueError(f"not a valid id: {text!r}")
    return int(text[len(prefix):])


def parse_hhmm(text: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text.strip()) if isinstance(text, str) else None
    if not match:
        raise ValueError(f"time must look like HH:MM, got {text!r}")
    hours, minutes = int(match.group(1)), int(match.group(2))
    if minutes > 59 or hours > 24 or (hours == 24 and minutes != 0):
        raise ValueError(f"not a valid time: {text!r}")
    return hours * 60 + minutes


def format_hhmm(minutes: int) -> str:
    return hhmm(minutes)


# ---------------- rows -> domain ----------------

def rotation_from_row(row: dict) -> Rotation:
    return Rotation(
        id=rid(row["id"]), name=row["name"],
        blocks=tuple(Block(b["name"], b["start_min"], b["end_min"], b["headcount"]) for b in row["blocks"]),
        weekdays=frozenset(row["weekdays"]), max_trainees=row.get("max_trainees", 1))


def employee_from_row(row: dict, valid_rotation_ids: set[str], start_date: date, num_days: int) -> Employee:
    trained, trainer_for, in_training = set(), set(), set()
    for link in row["rotations"]:
        rotation = rid(link["rotation_id"])
        if rotation not in valid_rotation_ids:
            continue  # archived or unknown rotations are ignored
        if link["level"] not in LEVELS:
            raise ValueError(f"unknown training level {link['level']!r}")
        if link["level"] == "training":
            in_training.add(rotation)
        else:
            trained.add(rotation)
            if link["level"] == "trainer":
                trainer_for.add(rotation)

    windows: dict[int, list[Interval]] = defaultdict(list)
    for w in row["availability"]:
        windows[w["weekday"]].append(Interval(w["start_min"], w["end_min"]))

    days_off, preferred = set(), set()
    for t in row["time_off"]:
        if t["kind"] not in TIME_OFF_KINDS:
            raise ValueError(f"unknown time-off kind {t['kind']!r}")
        day = (t["date"] - start_date).days
        if 0 <= day < num_days:
            (days_off if t["kind"] == "approved" else preferred).add(day)

    return Employee(
        id=eid(row["id"]), name=row["name"], rank=row["rank"], color=row["color"],
        trained=frozenset(trained), trainer_for=frozenset(trainer_for), in_training=frozenset(in_training),
        availability={wd: tuple(sorted(ws, key=lambda i: (i.start, i.end))) for wd, ws in windows.items()},
        max_hours_week=float(row["max_hours_week"]), target_hours_week=float(row["target_hours_week"]),
        days_off=frozenset(days_off), preferred_days_off=frozenset(preferred))


def build_instance(rotation_rows: list[dict], employee_rows: list[dict], start_date: date, num_days: int,
                   rules: dict | None = None) -> Instance:
    rotations = tuple(rotation_from_row(r) for r in rotation_rows)
    valid = {r.id for r in rotations}
    employees = tuple(employee_from_row(r, valid, start_date, num_days) for r in employee_rows)
    try:
        config = RuleConfig(**(rules or {}))
    except TypeError as exc:
        raise ValueError(f"unknown rule setting: {exc}") from exc
    return Instance(Horizon(start_date.weekday(), num_days), rotations, employees, config)


# ---------------- domain -> rows (for seeding a database from a generated instance) ----------------

def rows_from_instance(instance: Instance, start_date: date) -> tuple[list[dict], list[dict]]:
    def pk(domain_id: str, fallback: int) -> int:
        digits = re.sub(r"\D", "", domain_id)
        return int(digits) if digits else fallback

    rotation_rows = [dict(
        id=pk(r.id, i + 1), name=r.name, weekdays=sorted(r.weekdays), max_trainees=r.max_trainees,
        blocks=[dict(name=b.name, start_min=b.start, end_min=b.end, headcount=b.headcount) for b in r.blocks])
        for i, r in enumerate(instance.rotations)]

    employee_rows = []
    for i, e in enumerate(instance.employees):
        links = [dict(rotation_id=pk(r, 0), level="trainer" if r in e.trainer_for else "trained") for r in sorted(e.trained)]
        links += [dict(rotation_id=pk(r, 0), level="training") for r in sorted(e.in_training)]
        employee_rows.append(dict(
            id=pk(e.id, i + 1), name=e.name, rank=e.rank, color=e.color, max_hours_week=e.max_hours_week,
            target_hours_week=e.target_hours_week, rotations=links,
            availability=[dict(weekday=wd, start_min=w.start, end_min=w.end) for wd, ws in sorted(e.availability.items()) for w in ws],
            time_off=[dict(date=start_date + timedelta(days=d), kind="approved") for d in sorted(e.days_off)]
                     + [dict(date=start_date + timedelta(days=d), kind="preferred") for d in sorted(e.preferred_days_off)]))
    return rotation_rows, employee_rows


# ---------------- domain -> API views ----------------

def slot_view(instance: Instance, slot, start_date: date) -> dict:
    rotation = instance.rotations_by_id[slot.rotation_id]
    day = start_date + timedelta(days=slot.day)
    return dict(
        id=slot.id, rotation_id=parse_id(slot.rotation_id, "r"), rotation_name=rotation.name, block=slot.block,
        day=slot.day, date=day.isoformat(), weekday=WEEKDAYS[day.weekday()], start=format_hhmm(slot.start),
        end=format_hhmm(slot.end), headcount=slot.headcount, max_trainees=slot.max_trainees)


def _person(instance: Instance, employee_id: str) -> dict:
    e = instance.employees_by_id[employee_id]
    return dict(employee_id=parse_id(e.id, "e"), name=e.name, rank=e.rank, color=e.color)


def schedule_view(instance: Instance, schedule: Schedule, start_date: date) -> dict:
    """Everything the schedule grid needs: each slot with who is on it, plus a quality summary and any rule violations."""
    by_slot = defaultdict(list)
    for a in schedule.assignments:
        if a.slot_id in instance.slots_by_id and a.employee_id in instance.employees_by_id:
            by_slot[a.slot_id].append(a)

    slots = []
    for slot in instance.slots:
        people = []
        for a in sorted(by_slot[slot.id], key=lambda x: (x.role != "worker", x.employee_id)):
            person = _person(instance, a.employee_id) | {"role": a.role, "trainer_id": None, "trainer_name": None}
            if a.role == "trainee" and a.trainer_id in instance.employees_by_id:
                trainer = instance.employees_by_id[a.trainer_id]
                person |= {"trainer_id": parse_id(trainer.id, "e"), "trainer_name": trainer.name}
            people.append(person)
        workers = sum(1 for p in people if p["role"] == "worker")
        slots.append(slot_view(instance, slot, start_date) | {"assignments": people, "workers": workers,
                                                            "short": max(0, slot.headcount - workers)})
    return dict(
        slots=slots,
        summary=quality_report(instance, schedule).as_dict(),
        violations=[dict(rule=v.rule, message=v.message) for v in validate(instance, schedule)])


def candidates_view(instance: Instance, schedule: Schedule, slot_id: str) -> list[dict]:
    """Data for the 'who can I put here?' dropdown. status: assigned | eligible | blocked.
    An eligible person may still need others moved (needs_change), with the reasons listed."""
    slot = instance.slots_by_id[slot_id]
    order = {"assigned": 0, "eligible": 1, "blocked": 2}
    rows = []
    for emp in instance.employees:
        blockers = find_blockers(instance, schedule, emp.id, slot.id)
        if blockers and blockers[0].code == "already_assigned":
            status = "assigned"
        elif any(b.code in STATIC_CODES for b in blockers):
            status = "blocked"
        else:
            status = "eligible"
        role = "worker" if slot.rotation_id in emp.trained else "trainee" if slot.rotation_id in emp.in_training else None
        rows.append(_person(instance, emp.id) | dict(
            status=status, role=role, needs_change=status == "eligible" and bool(blockers),
            reasons=[b.message for b in blockers]))
    return sorted(rows, key=lambda r: (order[r["status"]], r["needs_change"], r["name"]))
