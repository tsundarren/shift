"""The objective, defined independently of any solver.

The CP-SAT model minimizes exactly this quantity, and `schedule_cost` computes it in plain Python
for ANY schedule. That gives two things: an apples-to-apples way to compare greedy against the
solver, and a test that the model really optimizes what we say it optimizes.

cost = coverage   * (missing worker-minutes)
     + fairness   * sum over employees of |minutes worked - ideal minutes|
     + preference * (minutes worked on a preferred day off)
     - training   * (trainee minutes)

"Ideal minutes" is each person's share of the total demand, proportional to their weekly target
hours, so part-timers are expected to work proportionally less. All quantities are integers.
Lower is better. Coverage dominates by design: leaving a seat empty is far worse than being unfair.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import Instance, Schedule


@dataclass(frozen=True)
class Weights:
    coverage: int = 100
    fairness: int = 2
    preference: int = 5
    training: int = 1


@dataclass(frozen=True)
class CostBreakdown:
    coverage: int
    fairness: int
    preference: int
    training: int

    @property
    def total(self) -> int:
        return self.coverage + self.fairness + self.preference + self.training


def ideal_minutes(instance: Instance) -> dict[str, int]:
    demand = sum(s.headcount * s.minutes for s in instance.slots)
    total_target = sum(e.target_hours_week for e in instance.employees)
    if total_target <= 0:
        return {e.id: 0 for e in instance.employees}
    return {e.id: round(demand * e.target_hours_week / total_target) for e in instance.employees}


def schedule_cost(instance: Instance, schedule: Schedule, weights: Weights = Weights()) -> CostBreakdown:
    workers: dict[str, int] = defaultdict(int)
    minutes: dict[str, int] = defaultdict(int)
    preference = training = 0
    seen: set[tuple[str, str]] = set()
    for a in schedule.assignments:
        emp, slot = instance.employees_by_id.get(a.employee_id), instance.slots_by_id.get(a.slot_id)
        if emp is None or slot is None or (a.employee_id, a.slot_id) in seen:
            continue
        seen.add((a.employee_id, a.slot_id))
        minutes[emp.id] += slot.minutes
        if a.role == "worker":
            workers[slot.id] += 1
        elif a.role == "trainee":
            training += slot.minutes
        if slot.day in emp.preferred_days_off:
            preference += slot.minutes

    missing = sum(max(0, s.headcount - workers[s.id]) * s.minutes for s in instance.slots)
    ideal = ideal_minutes(instance)
    deviation = sum(abs(minutes[e.id] - ideal[e.id]) for e in instance.employees)
    return CostBreakdown(
        coverage=weights.coverage * missing,
        fairness=weights.fairness * deviation,
        preference=weights.preference * preference,
        training=-weights.training * training,
    )
