"""Tests that run the REAL OR-Tools solver. Skipped automatically if OR-Tools isn't installed.

The formulation itself is verified without OR-Tools in test_model_exhaustive.py; these check the solver
integration: parameters, status handling, extraction, and behavior on realistic instances.
"""
import pytest

pytest.importorskip("ortools")

from scheduler.cpsat import solve_cpsat  # noqa: E402
from scheduler.generate import generate_instance  # noqa: E402
from scheduler.greedy import solve_greedy  # noqa: E402
from scheduler.metrics import quality_report  # noqa: E402
from scheduler.models import Assignment  # noqa: E402
from scheduler.objective import Weights, schedule_cost  # noqa: E402
from scheduler.validate import validate  # noqa: E402
from tests.helpers import employee, instance, rotation  # noqa: E402

FAST = dict(time_limit=10.0, workers=1, seed=1)
AM_ONLY = (("AM", 420, 660),)


def test_reports_status_gap_and_time():
    inst = generate_instance(seed=1, num_rotations=3, num_days=3, tightness=0.8)
    result = solve_cpsat(inst, **FAST)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.gap is not None and result.gap >= 0
    assert result.seconds > 0 and result.variables > 0


def test_never_breaks_a_hard_rule_on_generated_instances():
    for seed in range(4):
        for tightness in (0.6, 1.2):
            inst = generate_instance(seed=seed, num_rotations=4, num_days=7, tightness=tightness)
            result = solve_cpsat(inst, time_limit=5.0, workers=1, seed=1)
            assert result.status in ("OPTIMAL", "FEASIBLE"), (seed, tightness, result.status)
            assert validate(inst, result.schedule) == [], (seed, tightness)


def test_objective_value_matches_the_independent_evaluator():
    weights = Weights()
    for seed in range(3):
        inst = generate_instance(seed=seed, num_rotations=3, num_days=4, tightness=0.9)
        result = solve_cpsat(inst, weights=weights, **FAST)
        assert abs(result.objective - schedule_cost(inst, result.schedule, weights).total) < 1e-6


def test_when_proven_optimal_it_is_never_worse_than_greedy():
    for seed in range(3):
        inst = generate_instance(seed=seed, num_rotations=3, num_days=4, tightness=1.1)
        result = solve_cpsat(inst, **FAST)
        if result.status == "OPTIMAL":
            assert schedule_cost(inst, result.schedule).total <= schedule_cost(inst, solve_greedy(inst)).total


def test_fairness_and_preferences_on_a_tiny_case():
    inst = instance([rotation("r1", blocks=AM_ONLY)],
                    [employee("e1", target=16, preferred_off=(0,)), employee("e2", target=16)], num_days=2)
    result = solve_cpsat(inst, **FAST)
    assert result.status == "OPTIMAL"
    assert set(result.schedule.assignments) == {Assignment("e2", "r1:0:AM"), Assignment("e1", "r1:1:AM")}


def test_impossible_demand_returns_a_partial_schedule_not_an_error():
    inst = instance([rotation("r1", blocks=AM_ONLY, headcount=2)], [employee("e1")], num_days=1)
    result = solve_cpsat(inst, **FAST)
    assert result.status == "OPTIMAL"
    report = quality_report(inst, result.schedule)
    assert report.valid and report.seats_filled == 1 and round(report.coverage_pct) == 50


def test_minimum_rest_splits_the_work_between_people():
    rotations = [rotation("r1", blocks=AM_ONLY), rotation("r2", blocks=(("Late", 840, 1200),))]
    both = instance(rotations, [employee("e1", trained=("r1", "r2"), windows=((360, 1260),)),
                                employee("e2", trained=("r1", "r2"), windows=((360, 1260),))],
                    num_days=2, min_rest_minutes=720)
    result = solve_cpsat(both, **FAST)
    assert validate(both, result.schedule) == []
    assert quality_report(both, result.schedule).coverage_pct == 100

    lone = instance(rotations, [employee("e1", trained=("r1", "r2"), windows=((360, 1260),))],
                    num_days=2, min_rest_minutes=720)
    result = solve_cpsat(lone, **FAST)
    assert validate(lone, result.schedule) == []
    # Four slots, but Late(day 0) -> AM(day 1) leaves only 11h of rest and AM -> Late on one day leaves 3h.
    # The most one person can legally cover is two slots (for example both Late shifts, 18h apart).
    assert quality_report(lone, result.schedule).seats_filled == 2
    assigned = {a.slot_id for a in result.schedule.assignments}
    assert not {"r2:0:Late", "r1:1:AM"} <= assigned    # the one pair the rest rule actually forbids


def test_touching_blocks_are_one_work_period():
    inst = instance([rotation("r1")], [employee("e1")], num_days=1)
    result = solve_cpsat(inst, **FAST)
    assert validate(inst, result.schedule) == []
    assert quality_report(inst, result.schedule).coverage_pct == 100


def test_trainees_are_paired_with_a_certified_trainer():
    inst = instance([rotation("r1", blocks=AM_ONLY)],
                    [employee("tr", trainer_for=("r1",), rank="Senior"), employee("a", trained=(), in_training=("r1",))],
                    num_days=1)
    result = solve_cpsat(inst, **FAST)
    assert validate(inst, result.schedule) == []
    assert Assignment("a", "r1:0:AM", "trainee", "tr") in result.schedule.assignments


def test_same_seed_gives_the_same_answer_when_optimal():
    inst = generate_instance(seed=2, num_rotations=2, num_days=2, tightness=0.9)
    a, b = solve_cpsat(inst, **FAST), solve_cpsat(inst, **FAST)
    if a.status == b.status == "OPTIMAL":
        assert a.schedule == b.schedule


# ---- exercise, part 2 ----

@pytest.mark.xfail(strict=True, reason="EXERCISE: implement add_consecutive_day_limit in scheduler/cpsat.py, then delete this marker")
def test_solver_respects_the_consecutive_day_limit():
    inst = instance([rotation("r1", blocks=AM_ONLY, weekdays=range(7))], [employee("e1")], num_days=7, max_consecutive_days=3)
    result = solve_cpsat(inst, **FAST)
    assert validate(inst, result.schedule) == []
    assert quality_report(inst, result.schedule).uncovered_slots == 1   # work 3, rest 1, work 3
