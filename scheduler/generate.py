"""Synthetic problem instances. Everything here is invented: no real people, stations or schedules.

`tightness` is the dial that matters for benchmarking: roughly (hours of work to staff) divided by
(hours of staff capacity). Low = easy, high = nearly impossible. It sizes the workforce when
num_employees isn't given; the real difficulty also depends on who is trained on what.
"""
from __future__ import annotations

import math
import random

from .models import Block, Employee, Horizon, Instance, Interval, Rotation, RuleConfig

ROTATION_NAMES = ["Front Desk", "Intake", "Processing", "Quality Check", "Packaging", "Dispatch",
                  "Records", "Support", "Inventory", "Training Room"]
FIRST_NAMES = ["Ava", "Ben", "Cleo", "Dev", "Elena", "Femi", "Gus", "Hana", "Ivan", "Juno", "Kai", "Lena",
               "Mo", "Nina", "Omar", "Pia", "Quinn", "Ravi", "Sofia", "Theo", "Uma", "Vic", "Wren", "Xavi",
               "Yara", "Zane", "Alma", "Bruno", "Cora", "Dante", "Esme", "Finn", "Gia", "Hugo", "Iris", "Jude",
               "Kira", "Leo", "Maya", "Nico"]
RANKS = [("Associate", "#4C9AFF", 0.45), ("Senior", "#36B37E", 0.30), ("Lead", "#FF991F", 0.15), ("Supervisor", "#6554C0", 0.10)]
TRAINER_RANKS = {"Senior", "Lead", "Supervisor"}

AM = (7 * 60, 11 * 60)
PM = (11 * 60, 15 * 60)
FULL_DAY_WINDOW = Interval(6 * 60, 16 * 60)
AM_WINDOW = Interval(6 * 60, 12 * 60)
PM_WINDOW = Interval(10 * 60, 16 * 60)
AVG_WEEKLY_CAPACITY_HOURS = 29.6  # 60% full-time (40h) and 40% part-time (about 14h)


def generate_instance(seed: int = 0, num_rotations: int = 6, num_days: int = 14, tightness: float = 0.7,
                      num_employees: int | None = None, start_weekday: int = 0) -> Instance:
    if tightness <= 0:
        raise ValueError("tightness must be positive")
    rng = random.Random(seed)

    rotations = []
    for i in range(num_rotations):
        base = ROTATION_NAMES[i % len(ROTATION_NAMES)]
        name = base if i < len(ROTATION_NAMES) else f"{base} {i // len(ROTATION_NAMES) + 1}"
        rotations.append(Rotation(
            id=f"r{i + 1}", name=name,
            blocks=(Block("AM", *AM, rng.choice([1, 2, 3])), Block("PM", *PM, rng.choice([1, 2, 3]))),
            weekdays=frozenset(range(5)),
        ))

    weekly_demand_hours = sum(b.headcount * (b.end - b.start) / 60 * len(r.weekdays) for r in rotations for b in r.blocks)
    max_headcount = max(b.headcount for r in rotations for b in r.blocks)
    n = num_employees if num_employees is not None else max(
        max_headcount + 2, math.ceil(weekly_demand_hours / (tightness * AVG_WEEKLY_CAPACITY_HOURS)))

    rotation_ids = [r.id for r in rotations]
    names = rng.sample(FIRST_NAMES, min(n, len(FIRST_NAMES))) + [f"Staff {i}" for i in range(len(FIRST_NAMES), n)]
    horizon_days = list(range(num_days))
    workdays = [d for d in horizon_days if (start_weekday + d) % 7 < 5]

    people = []  # mutable drafts, frozen into Employee objects at the end
    for i in range(n):
        rank, color, _ = rng.choices(RANKS, weights=[w for _, _, w in RANKS])[0]
        breadth = rng.randint(2, 4) + (1 if rank in TRAINER_RANKS else 0)
        trained = set(rng.sample(rotation_ids, min(breadth, len(rotation_ids))))
        full_time = rng.random() < 0.6
        people.append(dict(i=i, rank=rank, color=color, trained=trained, full_time=full_time))

    # Make sure every rotation has enough trained people, preferring full-time staff.
    min_trained = min(n, max_headcount + 2)
    for rid in rotation_ids:
        have = [p for p in people if rid in p["trained"]]
        lacking = sorted((p for p in people if rid not in p["trained"]), key=lambda p: (not p["full_time"], rng.random()))
        for p in lacking[: max(0, min_trained - len(have))]:
            p["trained"].add(rid)

    employees = []
    for p in people:
        trained = frozenset(p["trained"])
        trainer_for = trained if p["rank"] in TRAINER_RANKS else frozenset()
        untrained = [r for r in rotation_ids if r not in trained]
        in_training = frozenset([rng.choice(untrained)]) if p["rank"] == "Associate" and untrained and rng.random() < 0.5 else frozenset()

        if p["full_time"]:
            availability = {wd: (FULL_DAY_WINDOW,) for wd in range(5)}
            max_hours, target = 40.0, 36.0
        else:
            window = rng.choice([FULL_DAY_WINDOW, AM_WINDOW, PM_WINDOW])
            availability = {wd: (window,) for wd in rng.sample(range(5), rng.randint(3, 4))}
            max_hours, target = 20.0, 14.0

        days_off = frozenset([rng.choice(workdays)]) if workdays and rng.random() < 0.15 else frozenset()
        preferred = frozenset(rng.sample(workdays, min(len(workdays), rng.randint(0, 2))))
        employees.append(Employee(
            id=f"e{p['i'] + 1:02d}", name=names[p["i"]], rank=p["rank"], color=p["color"], trained=trained,
            trainer_for=trainer_for, in_training=in_training, availability=availability,
            max_hours_week=max_hours, target_hours_week=target, days_off=days_off, preferred_days_off=preferred))

    return Instance(Horizon(start_weekday, num_days), tuple(rotations), tuple(employees), RuleConfig())
