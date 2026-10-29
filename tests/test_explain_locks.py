"""Explanations must respect manager decisions (locks) that are already in force."""
from scheduler.explain import explain_assignment
from tests.exhaustive_solver import exhaustive_solver
from tests.helpers import employee, instance, rotation, schedule

AM_ONLY = (("AM", 420, 660),)


def fair():
    return instance([rotation("r1", blocks=AM_ONLY)], [employee("e1", target=16), employee("e2", target=16)], num_days=2)


CURRENT = schedule(("e1", "r1:0:AM"), ("e2", "r1:1:AM"))


def test_a_manual_ban_is_reported_as_a_manual_decision():
    x = explain_assignment(fair(), CURRENT, "e1", "r1:1:AM", locked_bans={("e1", "r1:1:AM")}, solver=exhaustive_solver)
    assert x.status == "blocked" and "manually kept off" in x.summary


def test_the_counterfactual_cannot_undo_an_existing_pin():
    # e2 is pinned to Tuesday, so "what if e1 worked Tuesday?" is impossible without breaking that pin.
    x = explain_assignment(fair(), CURRENT, "e1", "r1:1:AM", locked_pins={("e2", "r1:1:AM")}, solver=exhaustive_solver)
    assert x.status == "blocked" and "pinned" in x.summary


def test_without_locks_the_answer_is_unchanged():
    assert explain_assignment(fair(), CURRENT, "e1", "r1:1:AM", solver=exhaustive_solver).status == "tradeoff"
