"""Request and response shapes. Times are "HH:MM" strings; domain-level validation (overlapping blocks, bad colors,
impossible windows) happens in the service layer by building the real domain objects."""
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field


class BlockIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    start: str
    end: str
    headcount: int = Field(ge=1, le=50)


class RotationIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    weekdays: list[int] = [0, 1, 2, 3, 4]
    max_trainees: int = Field(default=1, ge=0, le=10)
    blocks: list[BlockIn] = Field(min_length=1)


class RotationOut(RotationIn):
    id: int
    active: bool


class LinkIn(BaseModel):
    rotation_id: int
    level: Literal["training", "trained", "trainer"]


class WindowIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: str
    end: str


class TimeOffIn(BaseModel):
    date: Date
    kind: Literal["approved", "preferred"]


class EmployeeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rank: str = Field(default="", max_length=50)
    color: str = "#4C9AFF"
    max_hours_week: float = Field(default=40, gt=0, le=168)
    target_hours_week: float = Field(default=32, ge=0, le=168)
    rotations: list[LinkIn] = []
    availability: list[WindowIn] = []
    time_off: list[TimeOffIn] = []


class EmployeeOut(EmployeeIn):
    id: int
    active: bool


class ScheduleIn(BaseModel):
    name: str = Field(default="Schedule", min_length=1, max_length=100)
    start_date: Date
    num_days: int = Field(default=7, ge=1, le=28)
    time_limit: float = Field(default=10, ge=1, le=30)  # seconds the solver may spend


class PairIn(BaseModel):
    employee_id: int
    slot_id: str = Field(min_length=1, max_length=100)


class OverridesIn(BaseModel):
    pins: list[PairIn] = []
    bans: list[PairIn] = []
    time_limit: float = Field(default=10, ge=1, le=30)
