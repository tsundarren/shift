"""Explanations and the override workflow, tested with the exhaustive stand-in solver (no OR-Tools needed)."""
from scheduler.explain import apply_overrides, describe_cost_delta, explain_assignment
from scheduler.objective import CostBreakdown, Weights
from tests.exhaustive_solver import exhaustive_solver, no_solver
from tests.helpers import employee, instance, rotation, schedule

AM_ONLY = (("AM", 420, 660),)
W = Weights()


def fair():
    return instance([rotation("r1", blocks=AM_ONLY)], [employee("e1", target=16), employee("e2", target=16)], num_days=2)


CURRENT = schedule(("e1", "r1:0:AM"), ("e2", "r1:1:AM"))   # an optimal, evenly split schedule


def test_already_assigned():
    x = explain_assignment(fair(), CURRENT, "e1", "r1:0:AM", solver=no_solver)
    assert x.status == "assigned" and "E1" in x.summary


def test_blocked_by_a_rule_never_calls_the_solver():
    inst = instance([rotation("r1", blocks=AM_ONLY), rotation("r2", blocks=AM_ONLY)],
                    [employee("e1"), employee("e2", trained=("r2",)), employee("e3", days_off=(0,))], num_days=1)
    untrained = explain_assignment(inst, schedule(), "e2", "r1:0:AM", solver=no_solver)
    off = explain_assignment(inst, schedule(), "e3", "r1:0:AM", solver=no_solver)
    assert untrained.status == "blocked" and "isn't trained on R1" in untrained.summary
    assert off.status == "blocked" and "approved day off" in off.summary


def test_possible_but_costly_explains_what_moves_and_why_it_is_not_done():
    x = explain_assignment(fair(), CURRENT, "e1", "r1:1:AM", solver=exhaustive_solver)
    assert x.status == "tradeoff" and x.proven_optimal
    assert [b.code for b in x.blockers] == ["slot_full"]
    assert any(c.kind == "removed" and c.employee_id == "e2" for c in x.changes)
    assert any(c.kind == "added" and c.employee_id == "e1" for c in x.changes)
    assert x.cost_delta.fairness > 0 and x.cost_delta.total > 0
    assert "further from an even split" in x.summary and "isn't done" in x.summary


def test_when_the_current_schedule_is_improvable_the_explanation_says_so():
    lopsided = schedule(("e1", "r1:0:AM"), ("e1", "r1:1:AM"))          # e1 works everything, e2 nothing
    x = explain_assignment(fair(), lopsided, "e2", "r1:1:AM", solver=exhaustive_solver)
    assert x.status == "improvement" and x.cost_delta.total < 0
    assert "improve the schedule" in x.summary


def test_apply_overrides_with_no_changes_requested_changes_nothing():
    revision = apply_overrides(fair(), CURRENT, solver=exhaustive_solver)
    assert revision.ok and revision.changes == () and set(revision.schedule.assignments) == set(CURRENT.assignments)


def test_ban_replaces_the_banned_person_with_minimal_disruption():
    revision = apply_overrides(fair(), CURRENT, bans=[("e2", "r1:1:AM")], solver=exhaustive_solver)
    assert revision.ok
    assert [(c.kind, c.employee_id, c.slot_id) for c in revision.changes] == [("removed", "e2", "r1:1:AM"), ("added", "e1", "r1:1:AM")]


def test_bad_overrides_are_rejected_before_solving_and_the_schedule_is_untouched():
    revision = apply_overrides(fair(), CURRENT, pins=[("e1", "r1:0:AM")], bans=[("e1", "r1:0:AM")], solver=no_solver)
    assert not revision.ok and revision.status == "REJECTED" and revision.schedule == CURRENT
    assert [p.rule for p in revision.problems] == ["pin_and_ban"]


def test_cost_effects_are_described_in_plain_english():
    text = describe_cost_delta(CostBreakdown(coverage=100 * 120, fairness=2 * 240, preference=-5 * 60, training=1 * 60), W)
    assert text == ["2.0 h more of the required staffing would go uncovered",
                    "workloads would end up 4.0 h further from an even split",
                    "1.0 h fewer would be worked on days people asked off",
                    "1.0 h less trainee time"]
