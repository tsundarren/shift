#!/usr/bin/env python3
"""Load a generated workforce into the database.

    docker compose up -d db
    python -m scripts.seed_db --seed 3 --employees 14 --reset
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from api.db import SessionLocal, engine
from api.models import Base
from api.seed import seed_database
from scheduler.generate import generate_instance


def next_monday(today: date) -> date:
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--rotations", type=int, default=5)
    ap.add_argument("--employees", type=int, default=14)
    ap.add_argument("--start", type=date.fromisoformat, default=next_monday(date.today()), help="first day of the schedule (YYYY-MM-DD)")
    ap.add_argument("--reset", action="store_true", help="delete everything first")
    args = ap.parse_args()

    Base.metadata.create_all(engine)
    instance = generate_instance(seed=args.seed, num_rotations=args.rotations, num_days=14,
                                 num_employees=args.employees, start_weekday=args.start.weekday())
    with SessionLocal() as session:
        if args.reset:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
        rotations, employees = seed_database(session, instance, args.start)
    print(f"Loaded {rotations} rotations and {employees} employees. Time off is relative to {args.start}.")
    print(f'Next: POST /api/schedules with {{"start_date": "{args.start}", "num_days": 7}}')


if __name__ == "__main__":
    main()
