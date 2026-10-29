import dataclasses
from datetime import date, timedelta

from scheduler.generate import generate_instance
from scheduler.models import Assignment, Schedule
from scheduler.serialize import (build_instance, candidates_view, eid, employee_from_row, format_hhmm, parse_hhmm,
                                 parse_id, rid, rows_from_instance, schedule_view)
from tests.helpers import employee, instance, rotation, schedule

MONDAY = date(2026, 11, 2)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def rot_row(**kw):
    return dict(id=1, name="Intake", weekdays=[0, 1, 2, 3, 4], max_trainees=1,
                blocks=[dict(name="AM", start_min=420, end_min=660, headcount=1)]) | kw


def emp_row(**kw):
    return dict(id=1, name="Ava", rank="Senior", color="#36B37E", max_hours_week=40, target_hours_week=32,
                rotations=[dict(rotation_id=1, level="trained")],
                availability=[dict(weekday=wd, start_min=360, end_min=960) for wd in range(5)], time_off=[]) | kw


def test_ids_and_times():
    assert (eid(12), rid(3)) == ("e12", "r3") and parse_id("e12", "e") == 12
    assert raises(lambda: parse_id("x12", "e")) and raises(lambda: parse_id("e", "e")) and raises(lambda: parse_id("e1a", "e"))
    assert parse_hhmm("07:30") == 450 and parse_hhmm("7:05") == 425 and parse_hhmm("24:00") == 1440
    assert format_hhmm(450) == "07:30" and format_hhmm(1440) == "24:00"
    for bad in ("25:00", "07:60", "24:30", "0730", "ab:cd", ""):
        assert raises(lambda bad=bad: parse_hhmm(bad)), bad


def test_levels_become_trained_trainer_and_in_training():
    row = emp_row(rotations=[dict(rotation_id=1, level="trainer"), dict(rotation_id=2, level="training"), dict(rotation_id=3, level="trained")])
    e = employee_from_row(row, {"r1", "r2", "r3"}, MONDAY, 7)
    assert e.trained == {"r1", "r3"} and e.trainer_for == {"r1"} and e.in_training == {"r2"}


def test_links_to_archived_rotations_are_ignored():
    e = employee_from_row(emp_row(rotations=[dict(rotation_id=1, level="trained"), dict(rotation_id=9, level="trainer")]), {"r1"}, MONDAY, 7)
    assert e.trained == {"r1"} and e.trainer_for == set()


def test_time_off_dates_become_day_indexes_inside_the_horizon():
    row = emp_row(time_off=[dict(date=MONDAY + timedelta(days=2), kind="approved"), dict(date=MONDAY + timedelta(days=3), kind="preferred"),
                            dict(date=MONDAY + timedelta(days=30), kind="approved"), dict(date=MONDAY - timedelta(days=1), kind="preferred")])
    e = employee_from_row(row, {"r1"}, MONDAY, 7)
    assert e.days_off == {2} and e.preferred_days_off == {3}


def test_invalid_rows_raise_value_error():
    assert raises(lambda: employee_from_row(emp_row(color="blue"), {"r1"}, MONDAY, 7))
    assert raises(lambda: employee_from_row(emp_row(rotations=[dict(rotation_id=1, level="expert")]), {"r1"}, MONDAY, 7))
    assert raises(lambda: employee_from_row(emp_row(availability=[dict(weekday=0, start_min=600, end_min=600)]), {"r1"}, MONDAY, 7))
    assert raises(lambda: employee_from_row(emp_row(time_off=[dict(date=MONDAY, kind="maybe")]), {"r1"}, MONDAY, 7))
    assert raises(lambda: employee_from_row(emp_row(rotations=[dict(rotation_id=1, level="trained"), dict(rotation_id=1, level="training")]), {"r1"}, MONDAY, 7))
    assert raises(lambda: build_instance([rot_row(blocks=[])], [], MONDAY, 7))
    assert raises(lambda: build_instance([rot_row()], [], MONDAY, 7, rules={"nonsense": 1}))


def test_build_instance_uses_the_start_date_weekday():
    inst = build_instance([rot_row()], [emp_row()], date(2026, 11, 4), 7)       # a Wednesday
    assert inst.horizon.start_weekday == 2
    assert inst.slots[0].id == "r1:0:AM" and len(inst.slots) == 5


def test_a_generated_instance_survives_the_round_trip_through_rows():
    original = generate_instance(seed=4, num_rotations=4, num_days=7, tightness=0.8)
    rotation_rows, employee_rows = rows_from_instance(original, MONDAY)
    rebuilt = build_instance(rotation_rows, employee_rows, MONDAY, 7)
    renamed = tuple(dataclasses.replace(e, id=eid(int(e.id[1:]))) for e in original.employees)   # "e01" -> "e1"
    assert rebuilt.rotations == original.rotations and rebuilt.employees == renamed
    assert rebuilt.horizon == original.horizon


def small():
    inst = instance([rotation("r1")], [employee("e1", color="#112233", rank="Lead", trainer_for=("r1",)),
                                       employee("e2"), employee("e3", trained=(), in_training=("r1",)),
                                       employee("e4", trained=(), windows=((360, 600),)), employee("e5", days_off=(0,))],
                    num_days=1)
    return inst, schedule(("e1", "r1:0:AM"), Assignment("e3", "r1:0:AM", "trainee", "e1"))


def test_schedule_view_has_everything_the_grid_needs():
    inst, sched = small()
    view = schedule_view(inst, sched, MONDAY)
    am = next(s for s in view["slots"] if s["block"] == "AM")
    assert (am["id"], am["date"], am["weekday"], am["start"], am["end"]) == ("r1:0:AM", "2026-11-02", "Monday", "07:00", "11:00")
    assert am["workers"] == 1 and am["short"] == 0
    worker, trainee = am["assignments"]
    assert worker | {} == dict(employee_id=1, name="E1", rank="Lead", color="#112233", role="worker", trainer_id=None, trainer_name=None)
    assert trainee["role"] == "trainee" and trainee["trainer_id"] == 1 and trainee["trainer_name"] == "E1"
    pm = next(s for s in view["slots"] if s["block"] == "PM")
    assert pm["short"] == 1 and pm["assignments"] == []
    assert view["summary"]["valid"] is True and view["violations"] == []


def test_schedule_view_reports_a_stale_schedule_instead_of_hiding_it():
    inst, _ = small()
    stale = schedule(("e4", "r1:0:AM"))      # e4 is not trained on r1 and not available at that time
    view = schedule_view(inst, stale, MONDAY)
    assert {v["rule"] for v in view["violations"]} >= {"not_qualified", "unavailable"} and view["summary"]["valid"] is False


def test_candidates_view_drives_the_dropdown():
    inst, sched = small()
    rows = {r["employee_id"]: r for r in candidates_view(inst, sched, "r1:0:AM")}
    assert rows[1]["status"] == "assigned" and rows[3]["status"] == "assigned"
    assert rows[2]["status"] == "eligible" and rows[2]["needs_change"] is True and "already has all 1 worker" in rows[2]["reasons"][0]
    assert rows[4]["status"] == "blocked" and rows[5]["status"] == "blocked"
    assert any("approved day off" in reason for reason in rows[5]["reasons"])
    assert rows[2]["role"] == "worker" and rows[3]["role"] == "trainee" and rows[4]["role"] is None
    ordered = [r["status"] for r in candidates_view(inst, sched, "r1:0:AM")]
    assert ordered == sorted(ordered, key={"assigned": 0, "eligible": 1, "blocked": 2}.get)


def test_a_free_person_is_eligible_with_no_reasons():
    inst, _ = small()
    rows = {r["employee_id"]: r for r in candidates_view(inst, Schedule(), "r1:0:AM")}
    assert rows[2] | {} == dict(employee_id=2, name="E2", rank="Associate", color="#4C9AFF", status="eligible",
                                role="worker", needs_change=False, reasons=[])
