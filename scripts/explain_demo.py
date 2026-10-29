#!/usr/bin/env python3
"""Ask the scheduler "why not?" and try manual overrides. Needs OR-Tools.

    python -m scripts.explain_demo --seed 3 --list
    python -m scripts.explain_demo --seed 3 --who e03 --slot r1:1:AM
    python -m scripts.explain_demo --seed 3 --pin e03:r1:1:AM --ban e05:r2:0:PM
"""
from __future__ import annotations

import argparse

from scheduler.explain import apply_overrides, explain_assignment
from scheduler.generate import generate_instance
from scheduler.overrides import describe_change, pair_exists, slot_label


def suggest_questions(instance, schedule, per_kind: int = 3):
    """A few interesting (employee, slot) pairs: already scheduled, possible but not chosen, and impossible.
    Evenly spaced through the list, so the same seed always shows the same questions."""
    taken = {(a.employee_id, a.slot_id) for a in schedule.assignments}
    groups = {"assigned": [], "possible but not chosen": [], "impossible": []}
    for e in instance.employees:
        for s in instance.slots:
            kind = ("assigned" if (e.id, s.id) in taken
                    else "possible but not chosen" if pair_exists(instance, e, s) else "impossible")
            groups[kind].append((e.id, s.id))
    return {kind: pairs[:: max(1, len(pairs) // per_kind)][:per_kind] for kind, pairs in groups.items()}


def main() -> None:
    from scheduler.cpsat import solve_cpsat

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--days", type=int, default=4)
    ap.add_argument("--tightness", type=float, default=0.8)
    ap.add_argument("--list", action="store_true", help="show some questions worth asking")
    ap.add_argument("--who", help="employee id, e.g. e03")
    ap.add_argument("--slot", help="slot id, e.g. r1:1:AM")
    ap.add_argument("--pin", action="append", default=[], help="employee:slot to force, e.g. e03:r1:1:AM")
    ap.add_argument("--ban", action="append", default=[], help="employee:slot to forbid")
    args = ap.parse_args()

    instance = generate_instance(seed=args.seed, num_rotations=3, num_days=args.days, tightness=args.tightness)
    base = solve_cpsat(instance, time_limit=10, workers=8, seed=args.seed)
    print(f"Current schedule: {base.status}, {len(base.schedule.assignments)} assignments\n")
    names = {e.id: e.name for e in instance.employees}

    if args.list:
        for kind, pairs in suggest_questions(instance, base.schedule).items():
            print(kind)
            for employee_id, slot_id in pairs:
                print(f"  --who {employee_id} --slot {slot_id}    ({names[employee_id]}, {slot_label(instance, instance.slots_by_id[slot_id])})")
        return

    if args.who and args.slot:
        x = explain_assignment(instance, base.schedule, args.who, args.slot, time_limit=10, workers=8, seed=args.seed)
        print(f"[{x.status}] {x.summary}")
        return

    if args.pin or args.ban:
        split = lambda text: tuple(text.split(":", 1))  # noqa: E731  (slot ids contain colons)
        revision = apply_overrides(instance, base.schedule, pins=[split(p) for p in args.pin], bans=[split(b) for b in args.ban],
                                   time_limit=10, workers=8, seed=args.seed)
        if not revision.ok:
            print("Rejected:", *[f"\n  - {p.message}" for p in revision.problems] or [revision.status])
            return
        print(f"Revised ({revision.status}); {len(revision.changes)} change(s):")
        for change in revision.changes:
            print("  -", describe_change(instance, change))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
