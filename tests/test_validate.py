import pytest

from scheduler.models import Assignment
from scheduler.validate import validate
from tests.helpers import employee, instance, rotation, rules, schedule

AM_D0, PM_D0, AM_D1 = "r1:0:AM", "r1:0:PM", "r1:1:AM"


def base(**kw):
    return instance([rotation("r1")], [employee("e1"), employee("e2")], **kw)


def test_a_clean_schedule_passes_and_coverage_is_not_a_violation():
    assert validate(base(), schedule(("e1", AM_D0))) == []
    assert validate(base(), schedule()) == []  # empty is valid: shortfalls are reported by metrics


def test_unknown_duplicate_and_role_problems():
    assert rules(validate(base(), schedule(("e1", "nope:0:AM")))) == {"unknown_reference"}
    assert rules(validate(base(), schedule(("ghost", AM_D0)))) == {"unknown_reference"}
    assert "duplicate_assignment" in rules(validate(base(), schedule(("e1", AM_D0), ("e1", AM_D0))))
    assert "unknown_role" in rules(validate(base(), schedule(Assignment("e1", AM_D0, "boss"))))


def test_qualification_and_availability():
    inst = instance([rotation("r1"), rotation("r2")],
                    [employee("e1", trained=("r2",)), employee("late", windows=((660, 960),)), employee("off", days_off=(0,))])
    assert "not_qualified" in rules(validate(inst, schedule(("e1", AM_D0))))
    assert "unavailable" in rules(validate(inst, schedule(("late", AM_D0))))   # starts too late for AM
    assert "unavailable" in rules(validate(inst, schedule(("off", AM_D0))))    # approved day off


def test_overstaffing():
    assert "overstaffed" in rules(validate(base(), schedule(("e1", AM_D0), ("e2", AM_D0))))


def test_overlap_between_rotations():
    inst = instance([rotation("r1", blocks=(("AM", 420, 660),)), rotation("r2", blocks=(("X", 600, 780),))],
                    [employee("e1", trained=("r1", "r2"))])
    assert "overlap" in rules(validate(inst, schedule(("e1", "r1:0:AM"), ("e1", "r2:0:X"))))


def test_touching_blocks_are_one_work_period_not_a_rest_violation():
    assert validate(base(), schedule(("e1", AM_D0), ("e1", PM_D0))) == []   # AM then PM, 8h, same person


def test_minimum_rest_between_work_periods():
    rots = [rotation("r1", blocks=(("AM", 420, 660),)), rotation("r2", blocks=(("Late", 840, 1200),))]
    emps = [employee("e1", trained=("r1", "r2"), windows=((360, 1260),))]  # available until 21:00
    tight = instance(rots, emps, min_rest_minutes=720)      # day 0 ends 20:00, day 1 starts 07:00 = 11h gap
    relaxed = instance(rots, emps, min_rest_minutes=600)
    sched = schedule(("e1", "r2:0:Late"), ("e1", "r1:1:AM"))
    assert "insufficient_rest" in rules(validate(tight, sched))
    assert validate(relaxed, sched) == []


def test_daily_and_weekly_limits():
    assert "daily_limit" in rules(validate(base(max_daily_minutes=300), schedule(("e1", AM_D0), ("e1", PM_D0))))   # 8h > 5h
    capped = instance([rotation("r1")], [employee("e1", max_hours=7, target=5)])
    assert "weekly_limit" in rules(validate(capped, schedule(("e1", AM_D0), ("e1", PM_D0))))                        # 8h > 7h


def trainer_scene(**kw):
    return instance([rotation("r1", max_trainees=kw.pop("max_trainees", 1))],
                    [employee("tr", trainer_for=("r1",), rank="Senior"), employee("cert", trained=("r1",)),
                     employee("a", trained=(), in_training=("r1",)), employee("b", trained=(), in_training=("r1",)),
                     employee("plain", trained=("r1",))], **kw)


def test_trainee_with_a_certified_trainer_is_valid():
    sched = schedule(("tr", AM_D0), Assignment("a", AM_D0, "trainee", "tr"))
    assert validate(trainer_scene(), sched) == []


def test_trainee_rules():
    inst = trainer_scene()
    no_trainer = schedule(("tr", AM_D0), Assignment("a", AM_D0, "trainee", None))
    absent = schedule(("plain", AM_D0), Assignment("a", AM_D0, "trainee", "tr"))              # trainer isn't working the slot
    uncertified = schedule(("cert", AM_D0), Assignment("a", AM_D0, "trainee", "cert"))        # trained, but not a trainer
    not_learning = schedule(("tr", AM_D0), Assignment("plain", AM_D0, "trainee", "tr"))       # already trained: not a trainee
    assert "trainee_without_trainer" in rules(validate(inst, no_trainer))
    assert "trainee_without_trainer" in rules(validate(inst, absent))
    assert "trainer_not_certified" in rules(validate(inst, uncertified))
    assert "not_in_training" in rules(validate(inst, not_learning))


def test_trainee_capacity_limits():
    two = schedule(("tr", AM_D0), Assignment("a", AM_D0, "trainee", "tr"), Assignment("b", AM_D0, "trainee", "tr"))
    assert {"too_many_trainees", "trainer_overloaded"} <= rules(validate(trainer_scene(), two))
    roomy = trainer_scene(max_trainees=2, max_trainees_per_trainer=2)
    assert validate(roomy, two) == []


# ---- the exercise: maximum consecutive working days ----

def streak_scene(limit):
    return instance([rotation("r1", blocks=(("AM", 420, 660),), weekdays=range(7))], [employee("e1")],
                    max_consecutive_days=limit)


def test_streak_exactly_at_the_limit_is_fine():
    sched = schedule(*[("e1", f"r1:{d}:AM") for d in range(3)])
    assert "max_consecutive_days" not in rules(validate(streak_scene(3), sched))


@pytest.mark.xfail(strict=True, reason="EXERCISE: implement consecutive_day_violations in scheduler/validate.py, then delete this marker")
def test_streak_over_the_limit_is_flagged_once():
    sched = schedule(*[("e1", f"r1:{d}:AM") for d in range(4)])
    found = [v for v in validate(streak_scene(3), sched) if v.rule == "max_consecutive_days"]
    assert len(found) == 1 and found[0].employee_id == "e1"
