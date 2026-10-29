"""A drop-in replacement for solve_cpsat that solves tiny instances by exhaustive search (see fake_cp.py).
Lets explanation and override logic be tested end to end without OR-Tools."""
from scheduler.cpsat import SolveResult, _build, _extract
from scheduler.models import Schedule
from tests import fake_cp


def exhaustive_solver(instance, *, weights, overrides=None, **_ignored):
    built = _build(fake_cp, instance, weights, overrides)
    best = fake_cp.exhaustive_solve(built.model)
    if best is None:
        return SolveResult(Schedule(), "INFEASIBLE", None, None, None, 0.0, len(built.x))
    objective, envs = best
    schedule = _extract(instance, built.x, built.pairs, lambda v: envs[0][v])
    return SolveResult(schedule, "OPTIMAL", float(objective), float(objective), 0.0, 0.0, len(built.x))


def no_solver(*_args, **_kwargs):
    raise AssertionError("the solver must not be called for this case")
