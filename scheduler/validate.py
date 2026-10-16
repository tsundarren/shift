"""Independent schedule validator.

This is the source of truth for the HARD rules. Every schedule, from the greedy baseline or
(later) the solver, must pass it. It deliberately shares no logic with either, so a bug in a
solver model can't hide itself.

Coverage is not enforced here: an impossible instance has no complete schedule, and the
solver returns the best partial one. Shortfalls are reported by metrics.quality_report.
Overstaffing, however, is a violation.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import Employee, Instance, Schedule, Slot


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    employee_id: str | None = None
    slot_id: str | None = None


def _union_length(intervals: list[tuple[int, int]]) -> int:
    total, cur_start, cur_end = 0, None, None
    for start, end in sorted(intervals):
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        total += cur_end - cur_start
    return total


def worked_minutes(slots: list[Slot]) -> int:
    """Minutes worked, counting overlapping time once."""
    by_day: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for s in slots:
        by_day[s.day].append((s.start, s.end))
    return sum(_union_length(v) for v in by_day.values())


def consecutive_day_violations(instance: Instance, employee: Employee, slots: list[Slot]) -> list[Violation]:
    """EXERCISE: flag runs of working days longer than instance.rules.max_consecutive_days.

    Spec (the tests in tests/test_validate.py are your acceptance criteria):
      - A "working day" is any day on which the employee has at least one slot.
      - Return ONE Violation(rule="max_consecutive_days", ...) per run that is too long,
        with employee_id set.
      - Exactly the limit is fine; one more day is a violation.
    `slots` is this employee's slots sorted by start time. Only called when the rule is enabled.
    When it works, remove the xfail marker from the test that covers it.
    """
    return []


def check_employee_load(instance: Instance, emp: Employee, slots: list[Slot]) -> list[Violation]:
    """Rules about one employee's whole workload: overlap, rest, daily and weekly limits."""
    rules, out = instance.rules, []
    ordered = sorted(slots, key=lambda s: (s.abs_start, s.abs_end))

    latest: Slot | None = None  # double-booking
    for s in ordered:
        if latest is not None and s.abs_start < latest.abs_end:
            out.append(Violation("overlap", f"{emp.name} is double-booked: {latest.id} overlaps {s.id}", emp.id, s.id))
        if latest is None or s.abs_end > latest.abs_end:
            latest = s

    periods: list[list[int]] = []  # touching blocks merge into one continuous work period
    for s in ordered:
        if periods and s.abs_start <= periods[-1][1]:
            periods[-1][1] = max(periods[-1][1], s.abs_end)
        else:
            periods.append([s.abs_start, s.abs_end])
    for prev, nxt in zip(periods, periods[1:]):
        gap = nxt[0] - prev[1]
        if gap < rules.min_rest_minutes:
            out.append(Violation("insufficient_rest", f"{emp.name} gets only {gap} minutes of rest between work periods "
                                 f"(minimum {rules.min_rest_minutes})", emp.id))

    by_day: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for s in ordered:
        by_day[s.day].append((s.start, s.end))
    for day, intervals in sorted(by_day.items()):
        if _union_length(intervals) > rules.max_daily_minutes:
            out.append(Violation("daily_limit", f"{emp.name} works more than {rules.max_daily_minutes} minutes on day {day}", emp.id))

    by_week: dict[int, int] = defaultdict(int)
    for day, intervals in by_day.items():
        by_week[day // 7] += _union_length(intervals)
    for week, minutes in sorted(by_week.items()):
        if minutes > emp.max_hours_week * 60:
            out.append(Violation("weekly_limit", f"{emp.name} works {minutes / 60:.1f}h in week {week} (cap {emp.max_hours_week:g}h)", emp.id))

    if rules.max_consecutive_days is not None:
        out.extend(consecutive_day_violations(instance, emp, ordered))
    return out


def validate(instance: Instance, schedule: Schedule) -> list[Violation]:
    out: list[Violation] = []
    seen: set[tuple[str, str]] = set()
    slots_of: dict[str, list[Slot]] = defaultdict(list)
    workers: dict[str, list[str]] = defaultdict(list)
    trainees: dict[str, list] = defaultdict(list)

    for a in schedule.assignments:
        emp = instance.employees_by_id.get(a.employee_id)
        slot = instance.slots_by_id.get(a.slot_id)
        if emp is None or slot is None:
            out.append(Violation("unknown_reference", f"assignment references unknown employee or slot: {a.employee_id}, {a.slot_id}"))
            continue
        if (a.employee_id, a.slot_id) in seen:
            out.append(Violation("duplicate_assignment", f"{emp.name} is assigned twice to {slot.id}", emp.id, slot.id))
            continue
        seen.add((a.employee_id, a.slot_id))

        if a.role == "worker":
            if slot.rotation_id not in emp.trained:
                out.append(Violation("not_qualified", f"{emp.name} is not trained on {slot.rotation_id}", emp.id, slot.id))
            workers[slot.id].append(emp.id)
        elif a.role == "trainee":
            if slot.rotation_id not in emp.in_training:
                out.append(Violation("not_in_training", f"{emp.name} is not in training for {slot.rotation_id}", emp.id, slot.id))
            trainees[slot.id].append(a)
        else:
            out.append(Violation("unknown_role", f"unknown role {a.role!r}", emp.id, slot.id))
            continue

        if not instance.is_available(emp, slot):
            out.append(Violation("unavailable", f"{emp.name} is not available for {slot.id}", emp.id, slot.id))
        slots_of[emp.id].append(slot)

    for slot in instance.slots:
        if len(workers[slot.id]) > slot.headcount:
            out.append(Violation("overstaffed", f"{slot.id} has {len(workers[slot.id])} workers, needs {slot.headcount}", slot_id=slot.id))
        if len(trainees[slot.id]) > slot.max_trainees:
            out.append(Violation("too_many_trainees", f"{slot.id} has {len(trainees[slot.id])} trainees (max {slot.max_trainees})", slot_id=slot.id))
        per_trainer: dict[str, int] = defaultdict(int)
        for a in trainees[slot.id]:
            if a.trainer_id is None or a.trainer_id not in workers[slot.id]:
                out.append(Violation("trainee_without_trainer", f"trainee {a.employee_id} on {slot.id} has no trainer working that slot", a.employee_id, slot.id))
                continue
            trainer = instance.employees_by_id[a.trainer_id]
            if slot.rotation_id not in trainer.trainer_for:
                out.append(Violation("trainer_not_certified", f"{trainer.name} may not train others on {slot.rotation_id}", trainer.id, slot.id))
            per_trainer[a.trainer_id] += 1
        for trainer_id, n in per_trainer.items():
            if n > instance.rules.max_trainees_per_trainer:
                out.append(Violation("trainer_overloaded", f"{trainer_id} trains {n} people on {slot.id}", trainer_id, slot.id))

    for emp_id, slots in slots_of.items():
        out.extend(check_employee_load(instance, instance.employees_by_id[emp_id], slots))
    return out
