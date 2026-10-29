"""API tests need Postgres (docker compose up -d db). Without it they are skipped locally, but CI sets REQUIRE_DB=1
so a missing database fails the build instead of silently skipping."""
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("ortools")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from api.db import engine  # noqa: E402
from api.main import app  # noqa: E402
from api.models import Base  # noqa: E402

TABLES = "rotations, blocks, employees, employee_rotations, availability, time_off, schedules, assignments, locks, audit_log"
MONDAY = "2026-11-02"


@pytest.fixture
def client():
    try:
        Base.metadata.create_all(engine)
    except OperationalError as exc:
        if os.getenv("REQUIRE_DB"):
            raise
        pytest.skip(f"Postgres not available ({exc.__class__.__name__}); run: docker compose up -d db")
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    with TestClient(app) as c:
        yield c


def make_rotation(client, name="Intake", weekdays=(0, 1, 2, 3, 4), max_trainees=1,
                  blocks=(("AM", "07:00", "11:00", 1), ("PM", "11:00", "15:00", 1))):
    body = dict(name=name, weekdays=list(weekdays), max_trainees=max_trainees,
                blocks=[dict(name=n, start=s, end=e, headcount=h) for n, s, e, h in blocks])
    r = client.post("/api/rotations", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def make_employee(client, name, rotations=(), color="#4C9AFF", rank="Associate", weekdays=range(5), window=("06:00", "16:00"),
                  time_off=(), **extra):
    body = dict(name=name, rank=rank, color=color,
                rotations=[dict(rotation_id=i, level=level) for i, level in rotations],
                availability=[dict(weekday=d, start=window[0], end=window[1]) for d in weekdays],
                time_off=[dict(date=d, kind=k) for d, k in time_off], **extra)
    r = client.post("/api/employees", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def small_team(client):
    """One rotation (id 1) with AM and PM, and four people: Ava (trainer), Ben (trained), Cy (training), Dee (not trained)."""
    rotation = make_rotation(client)
    ava = make_employee(client, "Ava", [(rotation["id"], "trainer")], rank="Lead", color="#FF991F")
    ben = make_employee(client, "Ben", [(rotation["id"], "trained")])
    cy = make_employee(client, "Cy", [(rotation["id"], "training")])
    dee = make_employee(client, "Dee")
    return rotation, ava, ben, cy, dee
