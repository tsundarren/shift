"""Database tables. Slots are NOT stored: they are derived from rotations and a schedule's start date.
Employees and rotations are archived (active = false), never deleted, so old schedules keep their references."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RotationRow(Base):
    __tablename__ = "rotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    weekdays: Mapped[list] = mapped_column(JSONB, nullable=False)  # 0 = Monday ... 6 = Sunday
    max_trainees: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    blocks: Mapped[list["BlockRow"]] = relationship(cascade="all, delete-orphan", order_by="BlockRow.start_min", lazy="selectin")


class BlockRow(Base):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rotation_id: Mapped[int] = mapped_column(ForeignKey("rotations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)
    headcount: Mapped[int] = mapped_column(Integer, nullable=False)


class EmployeeRow(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rank: Mapped[str] = mapped_column(String(50), nullable=False, default="")  # free text
    color: Mapped[str] = mapped_column(String(7), nullable=False)  # "#RRGGBB"
    max_hours_week: Mapped[float] = mapped_column(Float, nullable=False)
    target_hours_week: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    links: Mapped[list["EmployeeRotationRow"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    availability: Mapped[list["AvailabilityRow"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    time_off: Mapped[list["TimeOffRow"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class EmployeeRotationRow(Base):
    """One row per (employee, rotation): level is training | trained | trainer."""

    __tablename__ = "employee_rotations"
    __table_args__ = (UniqueConstraint("employee_id", "rotation_id", name="uq_employee_rotation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    rotation_id: Mapped[int] = mapped_column(ForeignKey("rotations.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)


class AvailabilityRow(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_min: Mapped[int] = mapped_column(Integer, nullable=False)
    end_min: Mapped[int] = mapped_column(Integer, nullable=False)


class TimeOffRow(Base):
    __tablename__ = "time_off"
    __table_args__ = (UniqueConstraint("employee_id", "day", name="uq_time_off_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # approved | preferred


class ScheduleRow(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    num_days: Mapped[int] = mapped_column(Integer, nullable=False)
    solver_status: Mapped[str] = mapped_column(String(20), nullable=False)
    objective: Mapped[int | None] = mapped_column(BigInteger)  # schedule_cost of the current assignments
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssignmentRow(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("schedule_id", "employee_id", "slot_id", name="uq_assignment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    slot_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # worker | trainee
    trainer_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))


class LockRow(Base):
    """A manager decision that later re-solves must respect: pin (must be assigned) or ban (must not be)."""

    __tablename__ = "locks"
    __table_args__ = (UniqueConstraint("schedule_id", "employee_id", "slot_id", name="uq_lock"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    slot_id: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # pin | ban
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditRow(Base):
    """Append-only record of who/what changed. There is no authentication yet, so there is no 'who'."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(30), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
