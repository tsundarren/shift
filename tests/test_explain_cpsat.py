"""Overrides and explanations with the REAL solver. Skipped automatically if OR-Tools isn't installed."""
import pytest

pytest.importorskip("ortools")

from scheduler.cpsat import solve_cpsat  # noqa: E402
from scheduler.explain import apply_overrides, explain_assignment  # noqa: E402
from scheduler.generate import generate_instance  # noqa: E402
from scheduler.overrides import pair_exists  # noqa: E402
from scheduler.validate import validate  # noqa: E402

FAST = dict(time_limit=10.0, workers=1, seed=1)


def solved(seed=1):
    inst = generate_instance(seed=seed, num_rotations=3, num_days=4, tightness=0.8)
    return inst, solve_cpsat(inst, **FAST)


def unassigned_possible_pairs(inst, schedule, limit):
    taken = {(a.employee_id, a.slot_id) for a in schedule.assignments}
    pairs = [(e.id, s.id) for e in inst.employees for s in inst.slots
             if pair_exists(inst, e, s) and (e.id, s.id) not in taken]
    return pairs[:limit]


def test_revising_with_no_requests_changes_nothing_when_the_schedule_is_optimal():
    inst, result = solved()
    revision = apply_overrides(inst, result.schedule, **FAST)
    assert revision.ok and validate(inst, revision.schedule) == []
    if result.status == "OPTIMAL" and revision.proven_optimal:
        assert revision.changes == ()


def test_a_pin_is_honored_and_the_result_is_still_valid():
    inst, result = solved()
    for employee_id, slot_id in unassigned_possible_pairs(inst, result.schedule, 3):
        revision = apply_overrides(inst, result.schedule, pins=[(employee_id, slot_id)], **FAST)
        assert revision.ok
        assert (employee_id, slot_id) in {(a.employee_id, a.slot_id) for a in revision.schedule.assignments}
        assert validate(inst, revision.schedule) == []


def test_a_ban_is_honored_and_the_result_is_still_valid():
    inst, result = solved()
    for a in result.schedule.assignments[:3]:
        revision = apply_overrides(inst, result.schedule, bans=[(a.employee_id, a.slot_id)], **FAST)
        assert revision.ok
        assert (a.employee_id, a.slot_id) not in {(b.employee_id, b.slot_id) for b in revision.schedule.assignments}
        assert validate(inst, revision.schedule) == []


def test_every_kind_of_question_gets_an_answer():
    inst, result = solved()
    assigned = result.schedule.assignments[0]
    assert explain_assignment(inst, result.schedule, assigned.employee_id, assigned.slot_id, **FAST).status == "assigned"
    for employee_id, slot_id in unassigned_possible_pairs(inst, result.schedule, 4):
        x = explain_assignment(inst, result.schedule, employee_id, slot_id, **FAST)
        assert x.status in ("tradeoff", "improvement", "neutral") and x.summary and x.changes
    blocked = next((e.id, s.id) for e in inst.employees for s in inst.slots if not pair_exists(inst, e, s))
    assert explain_assignment(inst, result.schedule, *blocked, **FAST).status == "blocked"
