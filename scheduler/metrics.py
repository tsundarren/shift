"""Quality metrics. Reported as separate numbers on purpose: there is no single "score"
because the trade-offs between coverage, fairness and preferences are a business decision."""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass

from .models import Instance, Schedule, Slot
from .validate import validate, worked_minutes


@dataclass(frozen=True)
class QualityReport:
    valid: bool
    violations: int
    seats_required: int
    seats_filled: int
    coverage_pct: float
    uncovered_slots: int
    hours_mean: float
    hours_stddev: float
    hours_min: float
    hours_max: float
    over_target_hours: float
    under_target_hours: float
    preferred_off_worked: int
    trainee_assignments: int

    def as_dict(self) -> dict:
        return asdict(self)


def quality_report(instance: Instance, schedule: Schedule) -> QualityReport:
    violations = validate(instance, schedule)

    workers_in: dict[str, int] = defaultdict(int)
    slots_of: dict[str, list[Slot]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    preferred_off_worked = trainee_assignments = 0
    for a in schedule.assignments:
        emp, slot = instance.employees_by_id.get(a.employee_id), instance.slots_by_id.get(a.slot_id)
        if emp is None or slot is None or (a.employee_id, a.slot_id) in seen:
            continue
        seen.add((a.employee_id, a.slot_id))
        if a.role == "worker":
            workers_in[slot.id] += 1
        elif a.role == "trainee":
            trainee_assignments += 1
        slots_of[emp.id].append(slot)
        if slot.day in emp.preferred_days_off:
            preferred_off_worked += 1

    required = sum(s.headcount for s in instance.slots)
    filled = sum(min(workers_in[s.id], s.headcount) for s in instance.slots)
    uncovered = sum(1 for s in instance.slots if workers_in[s.id] < s.headcount)

    hours = [worked_minutes(slots_of[e.id]) / 60 for e in instance.employees]
    weeks = instance.horizon.num_days / 7
    over = under = 0.0
    for e, h in zip(instance.employees, hours):
        target = e.target_hours_week * weeks
        over += max(0.0, h - target)
        under += max(0.0, target - h)

    return QualityReport(
        valid=not violations,
        violations=len(violations),
        seats_required=required,
        seats_filled=filled,
        coverage_pct=100.0 * filled / required if required else 100.0,
        uncovered_slots=uncovered,
        hours_mean=statistics.fmean(hours) if hours else 0.0,
        hours_stddev=statistics.pstdev(hours) if hours else 0.0,
        hours_min=min(hours, default=0.0),
        hours_max=max(hours, default=0.0),
        over_target_hours=over,
        under_target_hours=under,
        preferred_off_worked=preferred_off_worked,
        trainee_assignments=trainee_assignments,
    )
