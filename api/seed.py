"""Fill the database from a generated instance, so there is something to look at."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from scheduler.models import Instance
from scheduler.serialize import rows_from_instance

from .models import (AvailabilityRow, BlockRow, EmployeeRotationRow, EmployeeRow, RotationRow, TimeOffRow)
from .service import audit


def seed_database(session: Session, instance: Instance, start_date: date) -> tuple[int, int]:
    rotation_rows, employee_rows = rows_from_instance(instance, start_date)
    new_ids: dict[int, int] = {}  # generated id -> database id
    for row in rotation_rows:
        rotation = RotationRow(name=row["name"], weekdays=row["weekdays"], max_trainees=row["max_trainees"],
                               blocks=[BlockRow(**b) for b in row["blocks"]])
        session.add(rotation)
        session.flush()
        new_ids[row["id"]] = rotation.id
    for row in employee_rows:
        session.add(EmployeeRow(
            name=row["name"], rank=row["rank"], color=row["color"], max_hours_week=row["max_hours_week"],
            target_hours_week=row["target_hours_week"],
            links=[EmployeeRotationRow(rotation_id=new_ids[l["rotation_id"]], level=l["level"]) for l in row["rotations"]],
            availability=[AvailabilityRow(**w) for w in row["availability"]],
            time_off=[TimeOffRow(day=t["date"], kind=t["kind"]) for t in row["time_off"]]))
    audit(session, "database.seeded", "system", "seed", {"rotations": len(rotation_rows), "employees": len(employee_rows)})
    session.commit()
    return len(rotation_rows), len(employee_rows)
