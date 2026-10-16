#!/usr/bin/env python3
"""Generate an instance, run the greedy baseline, validate it, and print a readable schedule.

    python -m scripts.demo --seed 3 --tightness 0.7 --days 7
"""
from __future__ import annotations

import argparse

from scheduler.generate import generate_instance
from scheduler.greedy import solve_greedy
from scheduler.metrics import quality_report
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
    args = ap.parse_args()

    instance = generate_instance(seed=args.seed, num_days=args.days, tightness=args.tightness)
    schedule = solve_greedy(instance)
    print(render(instance, schedule))
    print("\nHard-rule violations:", validate(instance, schedule) or "none")
    print("\nQuality:")
    for key, value in quality_report(instance, schedule).as_dict().items():
        print(f"  {key:<22}{value:.1f}" if isinstance(value, float) else f"  {key:<22}{value}")


if __name__ == "__main__":
    main()
