"""Verifies the CP-SAT model FORMULATION without OR-Tools.

For tiny instances we build the real model with a stand-in modeling API (tests/fake_cp.py), find its best
solution by trying every 0/1 assignment, and compare against a brute-force search over ALL schedules that uses
only the independent validator (hard rules) and schedule_cost (objective). If the model's constraints or
objective ever drift from the validator or the evaluator, these tests fail.
"""
import random

from scheduler.cpsat import _build, _extract
from scheduler.generate import generate_instance
from scheduler.models import Assignment, Schedule
from scheduler.objective import Weights, schedule_cost
from scheduler.validate import validate
from tests import fake_cp
from tests.helpers import employee, instance, rotation

WEIGHTS = Weights()


def candidate_assignments(inst):
    out = []
    for s in inst.slots:
        workers = inst.eligible_workers(s)
        out += [Assignment(e.id, s.id, "worker") for e in workers]
        trainers = [e for e in workers if s.rotation_id in e.trainer_for]
        for e in inst.eligible_trainees(s):
            out += [Assignment(e.id, s.id, "trainee", t.id) for t in trainers]
    return out


def brute_force_optimum(inst):
    """Cheapest schedule that passes the validator, found by trying every subset of possible assignments."""
    cands = candidate_assignments(inst)
    assert len(cands) <= 16, "instance too large for brute force"
    best = None
    for mask in range(1 << len(cands)):
        sched = Schedule(tuple(c for i, c in enumerate(cands) if mask >> i & 1))
        if validate(inst, sched):
            continue
        cost = schedule_cost(inst, sched, WEIGHTS).total
        if best is None or cost < best:
            best = cost
    return best


def check(inst):
    built = _build(fake_cp, inst, WEIGHTS)
    objective, optimal_envs = fake_cp.exhaustive_solve(built.model)
    expected = brute_force_optimum(inst)
    assert objective == expected, "model optimum differs from the brute-force optimum"

    schedules = []
    for env in optimal_envs:  # EVERY solution the model considers optimal must really be optimal and valid
        schedule = _extract(inst, built.x, built.pairs, lambda v, env=env: env[v])
        assert validate(inst, schedule) == [], "model returned a schedule that breaks a hard rule"
        assert schedule_cost(inst, schedule, WEIGHTS).total == objective, "model objective differs from the evaluator"
        schedules.append(schedule)
    return schedules[0]


AM_ONLY = (("AM", 420, 660),)


def test_fairness_splits_the_work():
    inst = instance([rotation("r1", blocks=AM_ONLY)], [employee("e1", target=16), employee("e2", target=16)], num_days=2)
    schedule = check(inst)
    assert sorted(a.employee_id for a in schedule.assignments) == ["e1", "e2"]


def test_preferences_are_honored_when_it_costs_nothing():
    inst = instance([rotation("r1", blocks=AM_ONLY)],
                    [employee("e1", target=16, preferred_off=(0,)), employee("e2", target=16)], num_days=2)
    schedule = check(inst)
    assert Assignment("e2", "r1:0:AM") in schedule.assignments


def test_overlap_touching_blocks_and_minimum_rest_together():
    rotations = [rotation("r1", blocks=(("AM", 420, 660), ("PM", 660, 900))),    # touching blocks
                 rotation("r2", blocks=(("Late", 840, 1200),))]                  # overlaps PM, ends 20:00
    employees = [employee("e1", trained=("r1", "r2"), windows=((360, 1260),)),
                 employee("e2", trained=("r1", "r2"), windows=((360, 1260),))]
    check(instance(rotations, employees, num_days=2, min_rest_minutes=720))      # 11h gap from Late to next AM is too short


def test_rest_rule_with_a_single_person_leaves_a_seat_empty_instead_of_breaking_it():
    rotations = [rotation("r1", blocks=AM_ONLY), rotation("r2", blocks=(("Late", 840, 1200),))]
    inst = instance(rotations, [employee("e1", trained=("r1", "r2"), windows=((360, 1260),))],
                    num_days=2, min_rest_minutes=720)
    schedule = check(inst)
    assert len(schedule.assignments) < len(inst.slots)


def test_daily_and_weekly_caps():
    rots = [rotation("r1")]  # AM + PM touching, 8h total
    check(instance(rots, [employee("e1"), employee("e2")], num_days=1, max_daily_minutes=300))
    check(instance(rots, [employee("e1", max_hours=4, target=4), employee("e2")], num_days=1))


def test_a_lone_employee_is_never_pushed_past_a_daily_limit_to_fill_a_seat():
    inst = instance([rotation("r1")], [employee("e1")], num_days=1, max_daily_minutes=300)   # AM + PM = 8h > 5h
    assert len(check(inst).assignments) == 1


def test_a_lone_employee_is_never_pushed_past_a_weekly_limit_to_fill_a_seat():
    inst = instance([rotation("r1")], [employee("e1", max_hours=4, target=4)], num_days=1)   # AM + PM = 8h > 4h
    assert len(check(inst).assignments) == 1


def test_a_lone_employee_cannot_work_two_overlapping_slots():
    rots = [rotation("r1", blocks=(("AM", 420, 660), ("PM", 660, 900))), rotation("r2", blocks=(("Late", 840, 1200),))]
    inst = instance(rots, [employee("e1", trained=("r1", "r2"), windows=((360, 1260),))], num_days=1)
    schedule = check(inst)
    assert len(schedule.assignments) == 2                                       # AM + PM, or AM + Late; never PM + Late


def test_trainee_must_pair_with_the_trainer_who_is_actually_working():
    rots = [rotation("r1", blocks=AM_ONLY)]
    emps = [employee("t1", trainer_for=("r1",), rank="Senior"), employee("t2", trainer_for=("r1",), rank="Senior"),
            employee("a", trained=(), in_training=("r1",))]
    schedule = check(instance(rots, emps, num_days=2))
    worker_by_slot = {a.slot_id: a.employee_id for a in schedule.assignments if a.role == "worker"}
    for a in schedule.assignments:
        if a.role == "trainee":
            assert worker_by_slot[a.slot_id] == a.trainer_id


def test_trainees_need_a_certified_trainer_in_the_same_slot():
    rots = [rotation("r1", blocks=AM_ONLY)]
    emps = [employee("tr", trainer_for=("r1",), rank="Senior"),
            employee("a", trained=(), in_training=("r1",)), employee("b", trained=(), in_training=("r1",))]
    schedule = check(instance(rots, emps, num_days=2))
    trainees = [a for a in schedule.assignments if a.role == "trainee"]
    assert trainees and all(a.trainer_id == "tr" for a in trainees)


def test_the_per_slot_trainee_limit_holds_even_with_trainers_to_spare():
    # Two trainers both working, two eager trainees, but the rotation allows only one trainee per slot.
    inst = instance([rotation("r1", blocks=AM_ONLY, headcount=2, max_trainees=1)],
                    [employee("t1", trainer_for=("r1",), rank="Senior"), employee("t2", trainer_for=("r1",), rank="Senior"),
                     employee("a", trained=(), in_training=("r1",)), employee("b", trained=(), in_training=("r1",))],
                    num_days=1)
    schedule = check(inst)
    assert sum(1 for a in schedule.assignments if a.role == "trainee") == 1


def test_demand_above_supply_gives_a_partial_schedule():
    inst = instance([rotation("r1", blocks=AM_ONLY, headcount=2)], [employee("e1")], num_days=1)
    schedule = check(inst)
    assert len(schedule.assignments) == 1


def test_model_builds_on_realistic_generated_instances():
    for seed in range(3):
        inst = generate_instance(seed=seed, num_rotations=3, num_days=3, tightness=0.8)
        built = _build(fake_cp, inst, WEIGHTS)
        assert built.x and built.model.constraints and built.model.objective is not None
        assert set(built.short) == {s.id for s in inst.slots}
