"""Greedy baseline: the thing the solver has to beat.

Fill the scarcest slots first (fewest eligible people per seat), giving each seat to the eligible
employee with the fewest hours so far (deprioritizing people who asked for that day off). Then a
second pass places trainees, paired with a certified trainer who is already working the slot.

It never violates a hard rule (every pick is checked with the same load checker as the validator)
but it can leave seats empty, and it can't look ahead or undo a choice.
"""
from __future__ import annotations

from collections import defaultdict

from .models import Assignment, Employee, Instance, Schedule, Slot
from .validate import check_employee_load


def _fits(instance: Instance, emp: Employee, current: list[Slot], slot: Slot) -> bool:
    return not check_employee_load(instance, emp, current + [slot])


def solve_greedy(instance: Instance) -> Schedule:
    eligible = {s.id: instance.eligible_workers(s) for s in instance.slots}
    order = sorted(instance.slots, key=lambda s: (len(eligible[s.id]) / s.headcount, s.day, s.start, s.id))

    load: dict[str, list[Slot]] = {e.id: [] for e in instance.employees}
    minutes: dict[str, int] = {e.id: 0 for e in instance.employees}
    crew: dict[str, list[str]] = defaultdict(list)
    assignments: list[Assignment] = []

    for slot in order:
        for _ in range(slot.headcount):
            candidates = [e for e in eligible[slot.id] if e.id not in crew[slot.id] and _fits(instance, e, load[e.id], slot)]
            if not candidates:
                break  # seat stays empty
            best = min(candidates, key=lambda e: (slot.day in e.preferred_days_off, minutes[e.id], e.id))
            load[best.id].append(slot)
            minutes[best.id] += slot.minutes
            crew[slot.id].append(best.id)
            assignments.append(Assignment(best.id, slot.id))

    # Second pass: trainees, up to each person's target hours.
    weeks = instance.horizon.num_days / 7
    trainees_in: dict[str, int] = defaultdict(int)
    trainer_load: dict[tuple[str, str], int] = defaultdict(int)
    for emp in instance.employees:
        cap = emp.target_hours_week * 60 * weeks
        for slot in sorted((s for s in instance.slots if s.rotation_id in emp.in_training), key=lambda s: (s.day, s.start, s.id)):
            if minutes[emp.id] + slot.minutes > cap:
                break
            if trainees_in[slot.id] >= slot.max_trainees or not instance.can_train_on(emp, slot):
                continue
            trainer = next((instance.employees_by_id[t] for t in crew[slot.id]
                            if slot.rotation_id in instance.employees_by_id[t].trainer_for
                            and trainer_load[(slot.id, t)] < instance.rules.max_trainees_per_trainer), None)
            if trainer is None or not _fits(instance, emp, load[emp.id], slot):
                continue
            load[emp.id].append(slot)
            minutes[emp.id] += slot.minutes
            trainees_in[slot.id] += 1
            trainer_load[(slot.id, trainer.id)] += 1
            assignments.append(Assignment(emp.id, slot.id, "trainee", trainer.id))

    return Schedule(tuple(assignments))
