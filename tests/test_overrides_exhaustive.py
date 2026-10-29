"""Verifies pins, bans and the stability term in the CP-SAT model against brute force (no OR-Tools needed)."""
from scheduler.cpsat import _build, _extract
from scheduler.generate import generate_instance
from scheduler.objective import Weights, schedule_cost
from scheduler.overrides import Overrides, pair_exists
from scheduler.validate import validate
from tests import fake_cp
from tests.helpers import employee, instance, rotation, schedule
from tests.test_model_exhaustive import candidate_assignments
from scheduler.models import Schedule

W = Weights()
AM_ONLY = (("AM", 420, 660),)


def brute(inst, overrides):
    cands = candidate_assignments(inst)
    assert len(cands) <= 14
    best = None
    for mask in range(1 << len(cands)):
        sched = Schedule(tuple(c for i, c in enumerate(cands) if mask >> i & 1))
        if validate(inst, sched):
            continue
        pairs = {(a.employee_id, a.slot_id) for a in sched.assignments}
        if not overrides.pins <= pairs or pairs & overrides.bans:
            continue
        cost = schedule_cost(inst, sched, W, previous=overrides.previous).total
        best = cost if best is None or cost < best else best
    return best


def check(inst, overrides):
    built = _build(fake_cp, inst, W, overrides)
    objective, envs = fake_cp.exhaustive_solve(built.model)
    assert objective == brute(inst, overrides), "model optimum differs from brute force"
    schedules = []
    for env in envs:                                 # every optimal solution must honor the overrides and the evaluator
        sched = _extract(inst, built.x, built.pairs, lambda v, env=env: env[v])
        pairs = {(a.employee_id, a.slot_id) for a in sched.assignments}
        assert validate(inst, sched) == []
        assert overrides.pins <= pairs and not (pairs & overrides.bans)
        assert schedule_cost(inst, sched, W, previous=overrides.previous).total == objective
        schedules.append(sched)
    return schedules


def fair():
    return instance([rotation("r1", blocks=AM_ONLY)], [employee("e1", target=16), employee("e2", target=16)], num_days=2)


PREV = schedule(("e1", "r1:0:AM"), ("e2", "r1:1:AM"))


def test_no_overrides_behaves_like_the_plain_model():
    check(fair(), Overrides())


def test_a_pin_is_honored_even_when_it_is_unfair():
    schedules = check(fair(), Overrides(pins=frozenset({("e1", "r1:1:AM")}), previous=PREV))
    assert all(("e1", "r1:1:AM") in {(a.employee_id, a.slot_id) for a in s.assignments} for s in schedules)


def test_a_ban_removes_someone_and_someone_else_covers():
    schedules = check(fair(), Overrides(bans=frozenset({("e2", "r1:1:AM")}), previous=PREV))
    assert all(("e1", "r1:1:AM") in {(a.employee_id, a.slot_id) for a in s.assignments} for s in schedules)


def test_stability_breaks_ties_in_favor_of_the_existing_schedule():
    # Swapping who works which day is equally fair, so only the stability term can decide.
    schedules = check(fair(), Overrides(previous=PREV))
    assert all(set(s.assignments) == set(PREV.assignments) for s in schedules)


def test_old_assignments_that_can_no_longer_exist_are_a_fixed_cost_not_a_bug():
    inst = instance([rotation("r1", blocks=AM_ONLY)], [employee("e1", target=16), employee("e2", target=16, days_off=(0,))], num_days=2)
    stale = schedule(("e2", "r1:0:AM"), ("e1", "r1:1:AM"))   # e2 now has day 0 off
    check(inst, Overrides(previous=stale))


def test_a_trainee_pin_pulls_in_a_working_trainer():
    inst = instance([rotation("r1", blocks=AM_ONLY)],
                    [employee("t1", trainer_for=("r1",), rank="Senior"), employee("t2", trainer_for=("r1",), rank="Senior"),
                     employee("a", trained=(), in_training=("r1",))], num_days=1)
    schedules = check(inst, Overrides(pins=frozenset({("a", "r1:0:AM")})))
    assert all(any(x.role == "trainee" and x.trainer_id in ("t1", "t2") for x in s.assignments) for s in schedules)


def test_the_models_variables_are_exactly_the_pairs_that_pair_exists_allows():
    for seed in range(3):
        inst = generate_instance(seed=seed, num_rotations=3, num_days=3, tightness=0.8)
        built = _build(fake_cp, inst, W)
        for e in inst.employees:
            for s in inst.slots:
                assert pair_exists(inst, e, s) == ((e.id, s.id) in built.x), (seed, e.id, s.id)
