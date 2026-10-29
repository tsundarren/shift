from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from . import service
from .db import get_session
from .schemas import EmployeeIn, EmployeeOut, OverridesIn, RotationIn, RotationOut, ScheduleIn

router = APIRouter(prefix="/api")


# ---- rotations ----
@router.get("/rotations", response_model=list[RotationOut])
def list_rotations(include_archived: bool = False, session: Session = Depends(get_session)):
    return service.list_rotations(session, include_archived)


@router.post("/rotations", response_model=RotationOut, status_code=201)
def create_rotation(body: RotationIn, session: Session = Depends(get_session)):
    return service.create_rotation(session, body.model_dump())


@router.put("/rotations/{rotation_id}", response_model=RotationOut)
def update_rotation(rotation_id: int, body: RotationIn, session: Session = Depends(get_session)):
    return service.update_rotation(session, rotation_id, body.model_dump())


@router.delete("/rotations/{rotation_id}", status_code=204)
def archive_rotation(rotation_id: int, session: Session = Depends(get_session)):
    service.archive_rotation(session, rotation_id)
    return Response(status_code=204)


# ---- employees ----
@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(include_archived: bool = False, session: Session = Depends(get_session)):
    return service.list_employees(session, include_archived)


@router.post("/employees", response_model=EmployeeOut, status_code=201)
def create_employee(body: EmployeeIn, session: Session = Depends(get_session)):
    return service.create_employee(session, body.model_dump())


@router.put("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: int, body: EmployeeIn, session: Session = Depends(get_session)):
    return service.update_employee(session, employee_id, body.model_dump())


@router.delete("/employees/{employee_id}", status_code=204)
def archive_employee(employee_id: int, session: Session = Depends(get_session)):
    service.archive_employee(session, employee_id)
    return Response(status_code=204)


# ---- schedules ----
@router.get("/schedules")
def list_schedules(session: Session = Depends(get_session)):
    return service.list_schedules(session)


@router.post("/schedules", status_code=201)
def create_schedule(body: ScheduleIn, session: Session = Depends(get_session)):
    """Solves synchronously, so the request takes up to `time_limit` seconds."""
    return service.create_schedule(session, name=body.name, start_date=body.start_date, num_days=body.num_days,
                                   time_limit=body.time_limit)


@router.get("/schedules/{schedule_id}")
def get_schedule(schedule_id: int, session: Session = Depends(get_session)):
    return service.schedule_detail(session, schedule_id)


@router.get("/schedules/{schedule_id}/slots/{slot_id}/candidates")
def slot_candidates(schedule_id: int, slot_id: str, session: Session = Depends(get_session)):
    """Everyone, marked assigned / eligible / blocked, with reasons. Feeds the 'who can go here?' dropdown."""
    return service.candidates(session, schedule_id, slot_id)


@router.post("/schedules/{schedule_id}/overrides")
def revise_schedule(schedule_id: int, body: OverridesIn, session: Session = Depends(get_session)):
    return service.revise_schedule(session, schedule_id, [p.model_dump() for p in body.pins],
                                   [b.model_dump() for b in body.bans], body.time_limit)


@router.delete("/schedules/{schedule_id}/locks/{lock_id}", status_code=204)
def remove_lock(schedule_id: int, lock_id: int, session: Session = Depends(get_session)):
    service.remove_lock(session, schedule_id, lock_id)
    return Response(status_code=204)


@router.get("/schedules/{schedule_id}/explain")
def explain(schedule_id: int, employee_id: int, slot_id: str, time_limit: float = Query(default=10, ge=1, le=30),
            session: Session = Depends(get_session)):
    return service.explain(session, schedule_id, employee_id, slot_id, time_limit)


@router.get("/audit")
def audit_log(limit: int = Query(default=50, ge=1, le=500), session: Session = Depends(get_session)):
    return service.recent_audit(session, limit)
