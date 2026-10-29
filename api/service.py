"""Business logic between the HTTP routes and the scheduler. No HTTP concepts here (errors are NotFound / Invalid /
Conflict); all scheduling decisions come from the pure `scheduler` package."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from scheduler.cpsat import solve_cpsat
from scheduler.explain import apply_overrides, explain_assignment
from scheduler.models import Assignment, Instance, Schedule
from scheduler.objective import schedule_cost
from scheduler.overrides import describe_change
from scheduler.serialize import (build_instance, candidates_view, eid, employee_from_row, format_hhmm, parse_hhmm,
                                 parse_id, rid, rotation_from_row, schedule_view)

from .errors import Conflict, Invalid, NotFound
from .models import (AssignmentRow, AuditRow, AvailabilityRow, BlockRow, EmployeeRotationRow, EmployeeRow, LockRow,
                     RotationRow, ScheduleRow, TimeOffRow)


def audit(session: Session, action: str, entity_type: str, entity_id, details: dict | None = None) -> None:
    session.add(AuditRow(action=action, entity_type=entity_type, entity_id=str(entity_id), details=details or {}))


def _replace(session: Session, collection: list, new_items: list) -> None:
    """Replace a child collection. Flushing between clear and extend makes the DELETEs run before the INSERTs,
    which matters when a unique constraint covers the children."""
    collection.clear()
    session.flush()
    collection.extend(new_items)


# ---------------- rotations ----------------

def rotation_row_dict(r: RotationRow) -> dict:
    return dict(id=r.id, name=r.name, weekdays=sorted(r.weekdays), max_trainees=r.max_trainees,
                blocks=[dict(name=b.name, start_min=b.start_min, end_min=b.end_min, headcount=b.headcount) for b in r.blocks])


def rotation_out(r: RotationRow) -> dict:
    return dict(id=r.id, name=r.name, active=r.active, weekdays=sorted(r.weekdays), max_trainees=r.max_trainees,
                blocks=[dict(name=b.name, start=format_hhmm(b.start_min), end=format_hhmm(b.end_min), headcount=b.headcount) for b in r.blocks])


def _rotation_payload_to_row(payload: dict) -> dict:
    try:
        row = dict(id=0, name=payload["name"].strip(), weekdays=sorted(set(payload["weekdays"])), max_trainees=payload["max_trainees"],
                   blocks=[dict(name=b["name"].strip(), start_min=parse_hhmm(b["start"]), end_min=parse_hhmm(b["end"]),
                                headcount=b["headcount"]) for b in payload["blocks"]])
        rotation_from_row(row)  # real validation: overlapping blocks, impossible times, bad weekdays
    except ValueError as exc:
        raise Invalid(str(exc)) from exc
    return row


def list_rotations(session: Session, include_archived: bool = False) -> list[dict]:
    query = select(RotationRow).order_by(RotationRow.id)
    if not include_archived:
        query = query.where(RotationRow.active)
    return [rotation_out(r) for r in session.scalars(query)]


def create_rotation(session: Session, payload: dict) -> dict:
    row = _rotation_payload_to_row(payload)
    rotation = RotationRow(name=row["name"], weekdays=row["weekdays"], max_trainees=row["max_trainees"],
                           blocks=[BlockRow(**b) for b in row["blocks"]])
    session.add(rotation)
    session.flush()
    audit(session, "rotation.created", "rotation", rotation.id, {"name": rotation.name})
    session.commit()
    return rotation_out(rotation)


def update_rotation(session: Session, rotation_id: int, payload: dict) -> dict:
    rotation = session.get(RotationRow, rotation_id)
    if rotation is None:
        raise NotFound(f"rotation {rotation_id} not found")
    row = _rotation_payload_to_row(payload)
    rotation.name, rotation.weekdays, rotation.max_trainees = row["name"], row["weekdays"], row["max_trainees"]
    _replace(session, rotation.blocks, [BlockRow(**b) for b in row["blocks"]])
    audit(session, "rotation.updated", "rotation", rotation.id, {"name": rotation.name})
    session.commit()
    return rotation_out(rotation)


def archive_rotation(session: Session, rotation_id: int) -> None:
    rotation = session.get(RotationRow, rotation_id)
    if rotation is None:
        raise NotFound(f"rotation {rotation_id} not found")
    rotation.active = False
    audit(session, "rotation.archived", "rotation", rotation.id, {"name": rotation.name})
    session.commit()


# ---------------- employees ----------------

def employee_row_dict(e: EmployeeRow) -> dict:
    return dict(id=e.id, name=e.name, rank=e.rank, color=e.color, max_hours_week=e.max_hours_week,
                target_hours_week=e.target_hours_week,
                rotations=[dict(rotation_id=l.rotation_id, level=l.level) for l in e.links],
                availability=[dict(weekday=a.weekday, start_min=a.start_min, end_min=a.end_min) for a in e.availability],
                time_off=[dict(date=t.day, kind=t.kind) for t in e.time_off])


def employee_out(e: EmployeeRow) -> dict:
    return dict(
        id=e.id, name=e.name, rank=e.rank, color=e.color, active=e.active, max_hours_week=e.max_hours_week,
        target_hours_week=e.target_hours_week,
        rotations=[dict(rotation_id=l.rotation_id, level=l.level) for l in sorted(e.links, key=lambda l: l.rotation_id)],
        availability=[dict(weekday=a.weekday, start=format_hhmm(a.start_min), end=format_hhmm(a.end_min))
                      for a in sorted(e.availability, key=lambda a: (a.weekday, a.start_min))],
        time_off=[dict(date=t.day, kind=t.kind) for t in sorted(e.time_off, key=lambda t: t.day)])


def _employee_payload_to_row(session: Session, payload: dict) -> dict:
    active_rotations = {r_id for (r_id,) in session.execute(select(RotationRow.id).where(RotationRow.active))}
    linked = [l["rotation_id"] for l in payload["rotations"]]
    if len(set(linked)) != len(linked):
        raise Invalid("each rotation can appear only once in an employee's rotations")
    for rotation_id in linked:
        if rotation_id not in active_rotations:
            raise Invalid(f"rotation {rotation_id} doesn't exist or is archived")
    days = [t["date"] for t in payload["time_off"]]
    if len(set(days)) != len(days):
        raise Invalid("each date can appear only once in an employee's time off")
    try:
        row = dict(id=0, name=payload["name"].strip(), rank=payload["rank"].strip(), color=payload["color"],
                   max_hours_week=payload["max_hours_week"], target_hours_week=payload["target_hours_week"],
                   rotations=[dict(rotation_id=l["rotation_id"], level=l["level"]) for l in payload["rotations"]],
                   availability=[dict(weekday=w["weekday"], start_min=parse_hhmm(w["start"]), end_min=parse_hhmm(w["end"]))
                                 for w in payload["availability"]],
                   time_off=[dict(date=t["date"], kind=t["kind"]) for t in payload["time_off"]])
        employee_from_row(row, {rid(i) for i in active_rotations}, date.today(), 1)  # real validation (color, windows, levels)
    except ValueError as exc:
        raise Invalid(str(exc)) from exc
    return row


def _apply_employee_row(session: Session, employee: EmployeeRow, row: dict) -> None:
    employee.name, employee.rank, employee.color = row["name"], row["rank"], row["color"]
    employee.max_hours_week, employee.target_hours_week = row["max_hours_week"], row["target_hours_week"]
    _replace(session, employee.links, [EmployeeRotationRow(rotation_id=l["rotation_id"], level=l["level"]) for l in row["rotations"]])
    _replace(session, employee.availability, [AvailabilityRow(weekday=w["weekday"], start_min=w["start_min"], end_min=w["end_min"])
                                              for w in row["availability"]])
    _replace(session, employee.time_off, [TimeOffRow(day=t["date"], kind=t["kind"]) for t in row["time_off"]])


def list_employees(session: Session, include_archived: bool = False) -> list[dict]:
    query = select(EmployeeRow).order_by(EmployeeRow.id)
    if not include_archived:
        query = query.where(EmployeeRow.active)
    return [employee_out(e) for e in session.scalars(query)]


def create_employee(session: Session, payload: dict) -> dict:
    row = _employee_payload_to_row(session, payload)
    employee = EmployeeRow(name=row["name"], rank=row["rank"], color=row["color"], max_hours_week=row["max_hours_week"],
                           target_hours_week=row["target_hours_week"])
    session.add(employee)
    session.flush()
    _apply_employee_row(session, employee, row)
    audit(session, "employee.created", "employee", employee.id, {"name": employee.name})
    session.commit()
    return employee_out(employee)


def update_employee(session: Session, employee_id: int, payload: dict) -> dict:
    employee = session.get(EmployeeRow, employee_id)
    if employee is None:
        raise NotFound(f"employee {employee_id} not found")
    _apply_employee_row(session, employee, _employee_payload_to_row(session, payload))
    audit(session, "employee.updated", "employee", employee.id, {"name": employee.name})
    session.commit()
    return employee_out(employee)


def archive_employee(session: Session, employee_id: int) -> None:
    employee = session.get(EmployeeRow, employee_id)
    if employee is None:
        raise NotFound(f"employee {employee_id} not found")
    employee.active = False
    audit(session, "employee.archived", "employee", employee.id, {"name": employee.name})
    session.commit()


# ---------------- schedules ----------------

def build_schedule_instance(session: Session, start_date: date, num_days: int) -> Instance:
    rotations = session.scalars(select(RotationRow).where(RotationRow.active).order_by(RotationRow.id)).all()
    employees = session.scalars(select(EmployeeRow).where(EmployeeRow.active).order_by(EmployeeRow.id)).all()
    try:
        return build_instance([rotation_row_dict(r) for r in rotations], [employee_row_dict(e) for e in employees],
                              start_date, num_days)
    except ValueError as exc:
        raise Invalid(f"the current workforce can't be scheduled: {exc}") from exc


def _get_schedule(session: Session, schedule_id: int, *, lock: bool = False) -> ScheduleRow:
    schedule = session.get(ScheduleRow, schedule_id, with_for_update=lock)
    if schedule is None:
        raise NotFound(f"schedule {schedule_id} not found")
    return schedule


def _current(session: Session, schedule: ScheduleRow) -> Schedule:
    rows = session.scalars(select(AssignmentRow).where(AssignmentRow.schedule_id == schedule.id)
                           .order_by(AssignmentRow.slot_id, AssignmentRow.employee_id)).all()
    return Schedule(tuple(Assignment(eid(r.employee_id), r.slot_id, r.role, eid(r.trainer_id) if r.trainer_id else None) for r in rows))


def _locks(session: Session, schedule_id: int) -> list[LockRow]:
    return list(session.scalars(select(LockRow).where(LockRow.schedule_id == schedule_id).order_by(LockRow.id)))


def _lock_sets(locks: list[LockRow]) -> tuple[set, set]:
    return ({(eid(l.employee_id), l.slot_id) for l in locks if l.kind == "pin"},
            {(eid(l.employee_id), l.slot_id) for l in locks if l.kind == "ban"})


def _store_assignments(session: Session, schedule_id: int, schedule: Schedule) -> None:
    session.execute(delete(AssignmentRow).where(AssignmentRow.schedule_id == schedule_id))
    session.flush()
    for a in schedule.assignments:
        session.add(AssignmentRow(schedule_id=schedule_id, employee_id=parse_id(a.employee_id, "e"), slot_id=a.slot_id,
                                  role=a.role, trainer_id=parse_id(a.trainer_id, "e") if a.trainer_id else None))
    session.flush()


def _store_locks(session: Session, schedule_id: int, pins: set, bans: set) -> None:
    session.execute(delete(LockRow).where(LockRow.schedule_id == schedule_id))
    session.flush()
    for kind, pairs in (("pin", pins), ("ban", bans)):
        for employee_id, slot_id in sorted(pairs):
            session.add(LockRow(schedule_id=schedule_id, employee_id=parse_id(employee_id, "e"), slot_id=slot_id, kind=kind))
    session.flush()


def schedule_out(s: ScheduleRow) -> dict:
    return dict(id=s.id, name=s.name, start_date=s.start_date.isoformat(), num_days=s.num_days,
                solver_status=s.solver_status, objective=s.objective, created_at=s.created_at.isoformat() if s.created_at else None)


def lock_out(l: LockRow) -> dict:
    return dict(id=l.id, employee_id=l.employee_id, slot_id=l.slot_id, kind=l.kind)


def schedule_detail(session: Session, schedule_id: int) -> dict:
    schedule = _get_schedule(session, schedule_id)
    instance = build_schedule_instance(session, schedule.start_date, schedule.num_days)
    return dict(schedule=schedule_out(schedule), view=schedule_view(instance, _current(session, schedule), schedule.start_date),
                locks=[lock_out(l) for l in _locks(session, schedule_id)])


def list_schedules(session: Session) -> list[dict]:
    return [schedule_out(s) for s in session.scalars(select(ScheduleRow).order_by(ScheduleRow.id.desc()))]


def create_schedule(session: Session, *, name: str, start_date: date, num_days: int, time_limit: float,
                    workers: int = 8, seed: int = 0) -> dict:
    instance = build_schedule_instance(session, start_date, num_days)
    if not instance.rotations or not instance.employees:
        raise Invalid("add at least one rotation and one employee before scheduling")
    result = solve_cpsat(instance, time_limit=time_limit, workers=workers, seed=seed)
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        raise Conflict(f"the solver found no schedule ({result.status})")
    schedule = ScheduleRow(name=name, start_date=start_date, num_days=num_days, solver_status=result.status,
                           objective=schedule_cost(instance, result.schedule).total)
    session.add(schedule)
    session.flush()
    _store_assignments(session, schedule.id, result.schedule)
    audit(session, "schedule.created", "schedule", schedule.id,
          {"name": name, "start_date": start_date.isoformat(), "num_days": num_days, "solver_status": result.status,
           "assignments": len(result.schedule.assignments)})
    session.commit()
    return schedule_detail(session, schedule.id)


def revise_schedule(session: Session, schedule_id: int, pins: list[dict], bans: list[dict], time_limit: float,
                    workers: int = 8) -> dict:
    """Apply manual pins/bans on top of the existing locks, changing as little as possible.
    The schedule row is locked for the duration so two simultaneous revisions can't clobber each other."""
    schedule = _get_schedule(session, schedule_id, lock=True)
    instance = build_schedule_instance(session, schedule.start_date, schedule.num_days)
    current = _current(session, schedule)
    old_pins, old_bans = _lock_sets(_locks(session, schedule_id))
    new_pins = {(eid(p["employee_id"]), p["slot_id"]) for p in pins}
    new_bans = {(eid(b["employee_id"]), b["slot_id"]) for b in bans}
    all_pins = (old_pins - new_bans) | new_pins  # the latest decision about an assignment wins
    all_bans = (old_bans - new_pins) | new_bans

    revision = apply_overrides(instance, current, pins=all_pins, bans=all_bans, time_limit=time_limit, workers=workers, seed=0)
    if not revision.ok:
        if revision.problems:
            raise Invalid("; ".join(p.message for p in revision.problems))
        raise Conflict(f"the solver found no schedule ({revision.status})")

    _store_assignments(session, schedule_id, revision.schedule)
    _store_locks(session, schedule_id, all_pins, all_bans)
    schedule.solver_status = revision.status
    schedule.objective = schedule_cost(instance, revision.schedule).total
    changes = [describe_change(instance, c) for c in revision.changes]
    audit(session, "schedule.revised", "schedule", schedule_id,
          {"pins": sorted(f"{e}:{s}" for e, s in new_pins), "bans": sorted(f"{e}:{s}" for e, s in new_bans), "changes": changes})
    session.commit()
    return schedule_detail(session, schedule_id) | {"changes": changes}


def remove_lock(session: Session, schedule_id: int, lock_id: int) -> None:
    """Unlocking only forgets the decision; the assignments stay as they are until the next revision."""
    lock = session.get(LockRow, lock_id)
    if lock is None or lock.schedule_id != schedule_id:
        raise NotFound(f"lock {lock_id} not found on schedule {schedule_id}")
    audit(session, "lock.removed", "schedule", schedule_id, {"employee_id": lock.employee_id, "slot_id": lock.slot_id, "kind": lock.kind})
    session.delete(lock)
    session.commit()


def candidates(session: Session, schedule_id: int, slot_id: str) -> list[dict]:
    schedule = _get_schedule(session, schedule_id)
    instance = build_schedule_instance(session, schedule.start_date, schedule.num_days)
    if slot_id not in instance.slots_by_id:
        raise NotFound(f"slot {slot_id} not found in schedule {schedule_id}")
    return candidates_view(instance, _current(session, schedule), slot_id)


def explain(session: Session, schedule_id: int, employee_id: int, slot_id: str, time_limit: float) -> dict:
    schedule = _get_schedule(session, schedule_id)
    instance = build_schedule_instance(session, schedule.start_date, schedule.num_days)
    if eid(employee_id) not in instance.employees_by_id or slot_id not in instance.slots_by_id:
        raise NotFound("unknown employee or slot for this schedule")
    pins, bans = _lock_sets(_locks(session, schedule_id))
    x = explain_assignment(instance, _current(session, schedule), eid(employee_id), slot_id, locked_pins=pins, locked_bans=bans,
                           time_limit=time_limit, workers=8, seed=0)
    delta = x.cost_delta
    return dict(
        employee_id=employee_id, slot_id=slot_id, status=x.status, summary=x.summary, proven_optimal=x.proven_optimal,
        blockers=[dict(code=b.code, message=b.message) for b in x.blockers],
        changes=[dict(kind=c.kind, employee_id=parse_id(c.employee_id, "e"), slot_id=c.slot_id, role=c.role,
                      text=describe_change(instance, c)) for c in x.changes],
        cost_delta=None if delta is None else dict(coverage=delta.coverage, fairness=delta.fairness,
                                                   preference=delta.preference, training=delta.training, total=delta.total))


def recent_audit(session: Session, limit: int = 50) -> list[dict]:
    rows = session.scalars(select(AuditRow).order_by(AuditRow.id.desc()).limit(limit))
    return [dict(id=r.id, at=r.at.isoformat() if r.at else None, action=r.action, entity_type=r.entity_type,
                 entity_id=r.entity_id, details=r.details) for r in rows]
