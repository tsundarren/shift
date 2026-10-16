"""Domain model for ShiftWise.

Plain dataclasses: no web, database, or solver dependencies, so everything built on top
(validator, greedy baseline, metrics, and later the solver) is easy to unit test.

Vocabulary
  Rotation   a task or station that needs staffing (created by the user)
  Block      a time window within a rotation's day, with its own headcount (e.g. AM, PM)
  Slot       one block on one day: the unit that gets staffed
  Employee   has trained rotations (checkboxes), a rank (free text), a color, availability
  Assignment an employee on a slot, either as a worker or as a trainee paired with a trainer

Times are minutes after midnight. Days are indexes from the start of the schedule (day 0).
Weekdays are 0 = Monday ... 6 = Sunday.

Note: Employee holds a dict, so don't put employees in sets or dict keys; use their ids.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Literal, Mapping

MINUTES_PER_DAY = 1440
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Interval:
    start: int
    end: int

    def __post_init__(self) -> None:
        if not (0 <= self.start < self.end <= MINUTES_PER_DAY):
            raise ValueError(f"invalid interval {self.start}-{self.end} (minutes after midnight)")

    @property
    def minutes(self) -> int:
        return self.end - self.start

    def contains(self, other: "Interval") -> bool:
        return self.start <= other.start and other.end <= self.end


@dataclass(frozen=True)
class Block:
    name: str
    start: int
    end: int
    headcount: int

    def __post_init__(self) -> None:
        Interval(self.start, self.end)  # validates the window
        if self.headcount < 1:
            raise ValueError("headcount must be at least 1")


@dataclass(frozen=True)
class Rotation:
    id: str
    name: str
    blocks: tuple[Block, ...]
    weekdays: frozenset[int] = frozenset(range(5))
    max_trainees: int = 1  # trainees allowed per slot, on top of the required workers

    def __post_init__(self) -> None:
        if not self.blocks:
            raise ValueError(f"rotation {self.id} needs at least one block")
        if not self.weekdays <= frozenset(range(7)):
            raise ValueError("weekdays must be in 0..6")
        names = [b.name for b in self.blocks]
        if len(set(names)) != len(names):
            raise ValueError(f"rotation {self.id} has duplicate block names")
        ordered = sorted(self.blocks, key=lambda b: b.start)
        for prev, nxt in zip(ordered, ordered[1:]):
            if nxt.start < prev.end:
                raise ValueError(f"rotation {self.id}: blocks {prev.name} and {nxt.name} overlap")


@dataclass(frozen=True)
class Slot:
    id: str
    rotation_id: str
    block: str
    day: int
    start: int
    end: int
    headcount: int
    max_trainees: int

    @property
    def interval(self) -> Interval:
        return Interval(self.start, self.end)

    @property
    def minutes(self) -> int:
        return self.end - self.start

    @property
    def abs_start(self) -> int:
        return self.day * MINUTES_PER_DAY + self.start

    @property
    def abs_end(self) -> int:
        return self.day * MINUTES_PER_DAY + self.end


@dataclass(frozen=True)
class Employee:
    id: str
    name: str
    rank: str  # free text, e.g. "Senior"
    color: str  # "#RRGGBB"
    trained: frozenset[str] = frozenset()  # rotation ids they can work
    trainer_for: frozenset[str] = frozenset()  # rotations they may train others on (subset of trained)
    in_training: frozenset[str] = frozenset()  # rotations they are learning (not yet trained)
    availability: Mapping[int, tuple[Interval, ...]] = field(default_factory=dict)  # weekday -> windows
    max_hours_week: float = 40.0  # hard cap
    target_hours_week: float = 32.0  # soft goal (fairness and over/under-target metrics)
    days_off: frozenset[int] = frozenset()  # approved time off: day indexes, hard
    preferred_days_off: frozenset[int] = frozenset()  # day indexes, soft

    def __post_init__(self) -> None:
        if not _HEX_COLOR.match(self.color):
            raise ValueError(f"color must look like #RRGGBB, got {self.color!r}")
        if not self.trainer_for <= self.trained:
            raise ValueError(f"{self.id}: trainer_for must be a subset of trained")
        if self.trained & self.in_training:
            raise ValueError(f"{self.id}: a rotation can't be both trained and in_training")
        if not (0 < self.max_hours_week) or not (0 <= self.target_hours_week <= self.max_hours_week):
            raise ValueError(f"{self.id}: need 0 <= target_hours_week <= max_hours_week")
        if not set(self.availability) <= set(range(7)):
            raise ValueError(f"{self.id}: availability weekdays must be in 0..6")

    def available_for(self, weekday: int, interval: Interval) -> bool:
        return any(window.contains(interval) for window in self.availability.get(weekday, ()))


@dataclass(frozen=True)
class Horizon:
    start_weekday: int = 0
    num_days: int = 14

    def weekday(self, day: int) -> int:
        return (self.start_weekday + day) % 7


@dataclass(frozen=True)
class RuleConfig:
    min_rest_minutes: int = 600  # between separate work periods (touching blocks form one period)
    max_daily_minutes: int = 720
    max_trainees_per_trainer: int = 1
    max_consecutive_days: int | None = None  # None = rule disabled (see the exercise in validate.py)


Role = Literal["worker", "trainee"]


@dataclass(frozen=True)
class Assignment:
    employee_id: str
    slot_id: str
    role: Role = "worker"
    trainer_id: str | None = None  # required for trainees: "John (Trained by: Jane)"


@dataclass(frozen=True)
class Schedule:
    assignments: tuple[Assignment, ...] = ()


@dataclass(frozen=True)
class Instance:
    horizon: Horizon
    rotations: tuple[Rotation, ...]
    employees: tuple[Employee, ...]
    rules: RuleConfig = field(default_factory=RuleConfig)

    def __post_init__(self) -> None:
        rotation_ids = [r.id for r in self.rotations]
        employee_ids = [e.id for e in self.employees]
        if len(set(rotation_ids)) != len(rotation_ids):
            raise ValueError("duplicate rotation ids")
        if len(set(employee_ids)) != len(employee_ids):
            raise ValueError("duplicate employee ids")
        known = set(rotation_ids)
        for e in self.employees:
            unknown = (e.trained | e.in_training) - known
            if unknown:
                raise ValueError(f"{e.id} references unknown rotations: {sorted(unknown)}")

    @cached_property
    def rotations_by_id(self) -> dict[str, Rotation]:
        return {r.id: r for r in self.rotations}

    @cached_property
    def employees_by_id(self) -> dict[str, Employee]:
        return {e.id: e for e in self.employees}

    @cached_property
    def slots(self) -> list[Slot]:
        out: list[Slot] = []
        for day in range(self.horizon.num_days):
            weekday = self.horizon.weekday(day)
            for rotation in self.rotations:
                if weekday not in rotation.weekdays:
                    continue
                for block in rotation.blocks:
                    out.append(Slot(
                        id=f"{rotation.id}:{day}:{block.name}", rotation_id=rotation.id, block=block.name,
                        day=day, start=block.start, end=block.end, headcount=block.headcount,
                        max_trainees=rotation.max_trainees,
                    ))
        return out

    @cached_property
    def slots_by_id(self) -> dict[str, Slot]:
        return {s.id: s for s in self.slots}

    # ---- eligibility (powers the "who can I assign here?" dropdown) ----

    def is_available(self, emp: Employee, slot: Slot) -> bool:
        if slot.day in emp.days_off:
            return False
        return emp.available_for(self.horizon.weekday(slot.day), slot.interval)

    def can_work(self, emp: Employee, slot: Slot) -> bool:
        return slot.rotation_id in emp.trained and self.is_available(emp, slot)

    def can_train_on(self, emp: Employee, slot: Slot) -> bool:
        """Can this employee be a trainee on the slot (learning the rotation, and free)?"""
        return slot.rotation_id in emp.in_training and self.is_available(emp, slot)

    def eligible_workers(self, slot: Slot) -> list[Employee]:
        return [e for e in self.employees if self.can_work(e, slot)]

    def eligible_trainees(self, slot: Slot) -> list[Employee]:
        return [e for e in self.employees if self.can_train_on(e, slot)]
