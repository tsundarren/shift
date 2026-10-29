"""Explanations ("why isn't Sam on Tuesday?") and manual overrides.

explain_assignment answers in layers:
  1. Already assigned?                        -> say so.
  2. A rule that makes it impossible (not trained, day off, not available) -> say which. No solving needed.
  3. Otherwise it IS possible, so ask the solver: re-solve with that assignment pinned, changing as little as
     possible, and report what would move and what it would cost compared with the current schedule.

apply_overrides is the manual-edit workflow behind it: pin and ban assignments, get back the revised schedule and
the list of changes. Solving goes through `solver` (default: CP-SAT) so tests can substitute an exhaustive one.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Instance, Schedule
from .objective import CostBreakdown, Weights, schedule_cost
from .overrides import (STATIC_CODES, Blocker, Change, Overrides, check_overrides, describe_change, diff_schedules,
                        find_blockers, slot_label)
from .validate import Violation


def _default_solver(instance: Instance, **kwargs):
    from .cpsat import solve_cpsat  # imported here so explanations of "blocked" cases need no OR-Tools

    return solve_cpsat(instance, **kwargs)


@dataclass(frozen=True)
class RevisionResult:
    ok: bool
    schedule: Schedule  # the revised schedule, or the unchanged current one if not ok
    changes: tuple[Change, ...]
    problems: tuple[Violation, ...]  # why the overrides were rejected, if they were
    status: str  # solver status, or "REJECTED"
    proven_optimal: bool | None = None


def apply_overrides(instance: Instance, current: Schedule, pins=(), bans=(), *, weights: Weights = Weights(),
                    solver=None, **solve_kwargs) -> RevisionResult:
    overrides = Overrides(frozenset(pins), frozenset(bans), previous=current)
    problems = check_overrides(instance, overrides)
    if problems:
        return RevisionResult(False, current, (), tuple(problems), "REJECTED")
    result = (solver or _default_solver)(instance, weights=weights, overrides=overrides, **solve_kwargs)
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        return RevisionResult(False, current, (), (), result.status)
    return RevisionResult(True, result.schedule, tuple(diff_schedules(current, result.schedule)), (), result.status,
                          proven_optimal=result.status == "OPTIMAL")


@dataclass(frozen=True)
class Explanation:
    employee_id: str
    slot_id: str
    status: str  # assigned | blocked | tradeoff | improvement | neutral
    summary: str
    blockers: tuple[Blocker, ...] = ()
    changes: tuple[Change, ...] = ()
    cost_delta: CostBreakdown | None = None  # new minus current, excluding the stability term
    proven_optimal: bool | None = None


def _hours(minutes: int) -> str:
    return f"{abs(minutes) / 60:.1f} h"


def describe_cost_delta(delta: CostBreakdown, weights: Weights) -> list[str]:
    """Plain-English effects of a change. Positive cost = worse."""
    parts = []
    if delta.coverage and weights.coverage:
        m = delta.coverage // weights.coverage
        parts.append(f"{_hours(m)} more of the required staffing would go uncovered" if m > 0
                     else f"{_hours(m)} less of the required staffing would go uncovered")
    if delta.fairness and weights.fairness:
        m = delta.fairness // weights.fairness
        parts.append(f"workloads would end up {_hours(m)} further from an even split" if m > 0
                     else f"workloads would end up {_hours(m)} closer to an even split")
    if delta.preference and weights.preference:
        m = delta.preference // weights.preference
        parts.append(f"{_hours(m)} more would be worked on days people asked off" if m > 0
                     else f"{_hours(m)} fewer would be worked on days people asked off")
    if delta.training and weights.training:
        m = delta.training // weights.training  # a positive cost delta means LESS trainee time
        parts.append(f"{_hours(m)} less trainee time" if m > 0 else f"{_hours(m)} more trainee time")
    return parts


def _minus(a: CostBreakdown, b: CostBreakdown) -> CostBreakdown:
    return CostBreakdown(a.coverage - b.coverage, a.fairness - b.fairness, a.preference - b.preference,
                         a.training - b.training, 0)


def explain_assignment(instance: Instance, schedule: Schedule, employee_id: str, slot_id: str, *,
                       locked_pins=(), locked_bans=(), weights: Weights = Weights(), solver=None,
                       **solve_kwargs) -> Explanation:
    """`locked_pins` / `locked_bans` are manager decisions already in force; the counterfactual respects them."""
    if employee_id not in instance.employees_by_id or slot_id not in instance.slots_by_id:
        raise ValueError(f"unknown employee or slot: {employee_id}, {slot_id}")
    emp = instance.employees_by_id[employee_id]
    blockers = find_blockers(instance, schedule, employee_id, slot_id)

    if blockers and blockers[0].code == "already_assigned":
        return Explanation(employee_id, slot_id, "assigned", blockers[0].message + ".", tuple(blockers))
    if any(b.code in STATIC_CODES for b in blockers):
        return Explanation(employee_id, slot_id, "blocked", "; ".join(b.message for b in blockers) + ".", tuple(blockers))

    if (employee_id, slot_id) in set(locked_bans):
        return Explanation(employee_id, slot_id, "blocked",
                           f"{emp.name} was manually kept off {slot_label(instance, instance.slots_by_id[slot_id])} (a manager locked that out).",
                           (Blocker("manual_ban", "manually locked out"),))

    revision = apply_overrides(instance, schedule, pins=set(locked_pins) | {(employee_id, slot_id)}, bans=locked_bans,
                               weights=weights, solver=solver, **solve_kwargs)
    if not revision.ok:
        reason = revision.problems[0].message if revision.problems else f"the solver reported {revision.status}"
        return Explanation(employee_id, slot_id, "blocked", f"Not possible: {reason}.", tuple(blockers))

    delta = _minus(schedule_cost(instance, revision.schedule, weights), schedule_cost(instance, schedule, weights))
    status = "tradeoff" if delta.total > 0 else "improvement" if delta.total < 0 else "neutral"
    sentences = []
    if blockers:
        sentences.append("Right now " + "; ".join(b.message for b in blockers) + ".")
    shown = [describe_change(instance, c) for c in revision.changes[:6]]
    more = f" (and {len(revision.changes) - 6} more)" if len(revision.changes) > 6 else ""
    sentences.append(f"{emp.name} could be scheduled there. Making room changes {len(revision.changes)} assignment(s): "
                     + "; ".join(shown) + more + ".")
    effects = describe_cost_delta(delta, weights)
    if status == "tradeoff":
        sentences.append("That is why it isn't done: " + "; ".join(effects) + ".")
    elif status == "improvement":
        sentences.append("This would actually improve the schedule: " + "; ".join(effects) + ".")
    else:
        sentences.append("It makes no difference to the objective, so either choice is equally good.")
    return Explanation(employee_id, slot_id, status, " ".join(sentences), tuple(blockers), revision.changes, delta,
                       revision.proven_optimal)
