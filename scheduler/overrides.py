"""Manual overrides and the "why not?" reasons behind explanations. Pure Python: no solver needed.

A manager can PIN an assignment ("Sam works Tuesday AM, no matter what") or BAN one ("not Jane on Friday"), and the
schedule is re-solved changing as little as possible (the stability term in the objective).

`find_blockers` explains why someone ISN'T on a slot. Reasons come in two kinds:
  static     true no matter how the rest of the schedule is arranged (not trained, day off, not available)
  dynamic    true of the CURRENT schedule only (slot already full, clashes with their other shifts); rearranging
             other people could remove them, so they are context rather than a final answer
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import Employee, Instance, Schedule, Slot
from .validate import Violation, check_employee_load

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STATIC_CODES = {"not_trained", "no_trainer", "day_off", "unavailable_day", "unavailable_window"}


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def day_label(instance: Instance, day: int) -> str:
    return f"{WEEKDAYS[instance.horizon.weekday(day)][:3]} (day {day})"


def slot_label(instance: Instance, slot: Slot) -> str:
    rotation = instance.rotations_by_id[slot.rotation_id]
    return f"{rotation.name} {slot.block} on {day_label(instance, slot.day)}, {hhmm(slot.start)}-{hhmm(slot.end)}"


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str


def pair_exists(instance: Instance, emp: Employee, slot: Slot) -> bool:
    """Can this employee be on this slot at all? Mirrors exactly which variables the solver creates."""
    if instance.can_work(emp, slot):
        return True
    if instance.can_train_on(emp, slot):
        if slot.max_trainees < 1 or instance.rules.max_trainees_per_trainer < 1:
            return False
        return any(slot.rotation_id in t.trainer_for for t in instance.eligible_workers(slot))
    return False


def static_blockers(instance: Instance, emp: Employee, slot: Slot) -> list[Blocker]:
    rotation = instance.rotations_by_id[slot.rotation_id]
    out: list[Blocker] = []
    if slot.rotation_id in emp.trained:
        pass
    elif slot.rotation_id in emp.in_training:
        has_trainer = any(slot.rotation_id in t.trainer_for for t in instance.eligible_workers(slot))
        if not has_trainer or slot.max_trainees < 1 or instance.rules.max_trainees_per_trainer < 1:
            out.append(Blocker("no_trainer", f"{emp.name} is still learning {rotation.name}, so can only attend as a trainee, "
                                             f"and no certified trainer is available for {slot_label(instance, slot)}"))
    else:
        out.append(Blocker("not_trained", f"{emp.name} isn't trained on {rotation.name}"))

    weekday = instance.horizon.weekday(slot.day)
    if slot.day in emp.days_off:
        out.append(Blocker("day_off", f"{emp.name} has an approved day off on {day_label(instance, slot.day)}"))
    else:
        windows = emp.availability.get(weekday, ())
        if not windows:
            out.append(Blocker("unavailable_day", f"{emp.name} isn't available on {WEEKDAYS[weekday]}s"))
        elif not any(w.contains(slot.interval) for w in windows):
            available = ", ".join(f"{hhmm(w.start)}-{hhmm(w.end)}" for w in windows)
            out.append(Blocker("unavailable_window", f"{emp.name} is only available {available} on {WEEKDAYS[weekday]}s, "
                                                     f"but {rotation.name} {slot.block} runs {hhmm(slot.start)}-{hhmm(slot.end)}"))
    return out


def find_blockers(instance: Instance, schedule: Schedule, employee_id: str, slot_id: str) -> list[Blocker]:
    emp, slot = instance.employees_by_id[employee_id], instance.slots_by_id[slot_id]
    names = {e.id: e.name for e in instance.employees}

    for a in schedule.assignments:
        if a.employee_id == employee_id and a.slot_id == slot_id:
            how = f" as a trainee (trained by {names.get(a.trainer_id, '?')})" if a.role == "trainee" else ""
            return [Blocker("already_assigned", f"{emp.name} is already assigned to {slot_label(instance, slot)}{how}")]

    static = static_blockers(instance, emp, slot)
    if static:
        return static

    out: list[Blocker] = []
    in_slot = [a for a in schedule.assignments if a.slot_id == slot_id]
    if slot.rotation_id in emp.trained:
        crew = [a for a in in_slot if a.role == "worker"]
        if len(crew) >= slot.headcount:
            who = ", ".join(names[a.employee_id] for a in crew)
            out.append(Blocker("slot_full", f"{slot_label(instance, slot)} already has all {slot.headcount} worker(s): {who}"))
    elif len([a for a in in_slot if a.role == "trainee"]) >= slot.max_trainees:
        out.append(Blocker("trainee_spots_full", f"{slot_label(instance, slot)} already has its maximum of {slot.max_trainees} trainee(s)"))

    mine = [instance.slots_by_id[a.slot_id] for a in schedule.assignments
            if a.employee_id == employee_id and a.slot_id in instance.slots_by_id]
    before = {v.rule for v in check_employee_load(instance, emp, mine)}
    after = {v.rule for v in check_employee_load(instance, emp, mine + [slot])}
    rules = instance.rules
    for rule in sorted(after - before):
        if rule == "overlap":
            clash = next(s for s in mine if s.day == slot.day and s.start < slot.end and slot.start < s.end)
            message = f"{emp.name} is already working {slot_label(instance, clash)}, which overlaps"
        elif rule == "insufficient_rest":
            message = f"it would leave {emp.name} less than {rules.min_rest_minutes / 60:g} hours of rest between work periods"
        elif rule == "daily_limit":
            message = f"it would put {emp.name} over the {rules.max_daily_minutes / 60:g}-hour daily limit on {day_label(instance, slot.day)}"
        elif rule == "weekly_limit":
            message = f"it would put {emp.name} over their {emp.max_hours_week:g}-hour weekly cap"
        elif rule == "max_consecutive_days":
            message = f"it would make more than {rules.max_consecutive_days} working days in a row for {emp.name}"
        else:
            message = f"it would break the {rule} rule for {emp.name}"
        out.append(Blocker(rule, message))
    return out


# ---------------- overrides ----------------

@dataclass(frozen=True)
class Overrides:
    pins: frozenset[tuple[str, str]] = frozenset()   # (employee_id, slot_id) that MUST be assigned
    bans: frozenset[tuple[str, str]] = frozenset()   # (employee_id, slot_id) that must NOT be assigned
    previous: Schedule | None = None                  # revise this schedule, changing as little as possible


def check_overrides(instance: Instance, overrides: Overrides) -> list[Violation]:
    """Problems with the overrides themselves, found before any solving. An empty list means they can coexist."""
    out: list[Violation] = []
    pinned: dict[str, list[Slot]] = defaultdict(list)
    workers_pinned: dict[str, int] = defaultdict(int)
    trainees_pinned: dict[str, int] = defaultdict(int)

    for employee_id, slot_id in sorted(overrides.pins):
        emp, slot = instance.employees_by_id.get(employee_id), instance.slots_by_id.get(slot_id)
        if emp is None or slot is None:
            out.append(Violation("override_unknown_reference", f"unknown employee or slot: {employee_id}, {slot_id}"))
            continue
        if (employee_id, slot_id) in overrides.bans:
            out.append(Violation("pin_and_ban", f"{emp.name} on {slot_label(instance, slot)} is both pinned and banned", employee_id, slot_id))
            continue
        blockers = static_blockers(instance, emp, slot)
        if blockers:
            out.append(Violation("pin_ineligible", blockers[0].message, employee_id, slot_id))
            continue
        pinned[employee_id].append(slot)
        if slot.rotation_id in emp.trained:
            workers_pinned[slot_id] += 1
        else:
            trainees_pinned[slot_id] += 1

    for employee_id, slots in pinned.items():
        emp = instance.employees_by_id[employee_id]
        for v in check_employee_load(instance, emp, slots):
            out.append(Violation("pin_conflict", f"the pinned assignments for {emp.name} conflict: {v.message}", employee_id))
    for slot_id, n in workers_pinned.items():
        slot = instance.slots_by_id[slot_id]
        if n > slot.headcount:
            out.append(Violation("pin_overstaffed", f"{n} workers are pinned to {slot_label(instance, slot)}, which needs {slot.headcount}", slot_id=slot_id))
    for slot_id, n in trainees_pinned.items():
        slot = instance.slots_by_id[slot_id]
        if n > slot.max_trainees:
            out.append(Violation("pin_too_many_trainees", f"{n} trainees are pinned to {slot_label(instance, slot)} (max {slot.max_trainees})", slot_id=slot_id))
    return out


@dataclass(frozen=True)
class Change:
    kind: str  # "added" or "removed"
    employee_id: str
    slot_id: str
    role: str


def diff_schedules(old: Schedule, new: Schedule) -> list[Change]:
    before = {(a.employee_id, a.slot_id): a for a in old.assignments}
    after = {(a.employee_id, a.slot_id): a for a in new.assignments}
    changes = [Change("removed", e, s, before[(e, s)].role) for e, s in sorted(before.keys() - after.keys(), key=lambda k: (k[1], k[0]))]
    changes += [Change("added", e, s, after[(e, s)].role) for e, s in sorted(after.keys() - before.keys(), key=lambda k: (k[1], k[0]))]
    return changes


def describe_change(instance: Instance, change: Change) -> str:
    emp, slot = instance.employees_by_id[change.employee_id], instance.slots_by_id[change.slot_id]
    verb, prep = ("Remove", "from") if change.kind == "removed" else ("Add", "to")
    trainee = " (as a trainee)" if change.role == "trainee" else ""
    return f"{verb} {emp.name}{trainee} {prep} {slot_label(instance, slot)}"
