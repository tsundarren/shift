#!/usr/bin/env python3
"""Generate an instance, solve it, validate the result, and print a readable schedule.

    python -m scripts.demo --seed 3 --tightness 0.7 --days 7 --algo greedy
    python -m scripts.demo --seed 3 --tightness 1.2 --days 7 --algo cpsat     # needs OR-Tools
"""
from __future__ import annotations

import argparse

from scheduler.generate import generate_instance
from scheduler.greedy import solve_greedy
from scheduler.metrics import quality_report
from scheduler.objective import schedule_cost
from scheduler.validate import validate

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def render(instance, schedule) -> str:
    names = {e.id: e.name for e in instance.employees}
    by_slot: dict[str, list] = {}
    for a in schedule.assignments:
        by_slot.setdefault(a.slot_id, []).append(a)
    lines, last_day = [], None
    for slot in instance.slots:
        if slot.day != last_day:
            lines.append(f"\n{WEEKDAYS[instance.horizon.weekday(slot.day)]} (day {slot.day})")
            last_day = slot.day
        rotation = instance.rotations_by_id[slot.rotation_id]
        people = []
        for a in by_slot.get(slot.id, []):
            people.append(names[a.employee_id] if a.role == "worker" else f"{names[a.employee_id]} (trained by {names[a.trainer_id]})")
        workers = sum(1 for a in by_slot.get(slot.id, []) if a.role == "worker")
        flag = "" if workers >= slot.headcount else f"  <-- short {slot.headcount - workers}"
        lines.append(f"  {rotation.name:<14}{slot.block:<3} need {slot.headcount}: {', '.join(people) or '-'}{flag}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--tightness", type=float, default=0.7)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--algo", choices=["greedy", "cpsat"], default="greedy")
    ap.add_argument("--time-limit", type=float, default=10.0)
    args = ap.parse_args()

    instance = generate_instance(seed=args.seed, num_days=args.days, tightness=args.tightness)
    if args.algo == "cpsat":
        from scheduler.cpsat import solve_cpsat

        result = solve_cpsat(instance, time_limit=args.time_limit, workers=8, seed=args.seed)
        schedule = result.schedule
        print(f"CP-SAT: {result.status}, gap {result.gap if result.gap is None else format(result.gap, '.1%')}, {result.seconds:.1f}s")
    else:
        schedule = solve_greedy(instance)

    print(render(instance, schedule))
    print("\nHard-rule violations:", validate(instance, schedule) or "none")
    cost = schedule_cost(instance, schedule)
    print(f"\nObjective (lower is better): {cost.total:,}  [coverage {cost.coverage:,}, fairness {cost.fairness:,}, "
          f"preference {cost.preference:,}, training {cost.training:,}]")
    print("\nQuality:")
    for key, value in quality_report(instance, schedule).as_dict().items():
        print(f"  {key:<22}{value:.1f}" if isinstance(value, float) else f"  {key:<22}{value}")


if __name__ == "__main__":
    main()
