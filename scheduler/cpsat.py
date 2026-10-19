"""CP-SAT model for Shift.

One yes/no variable per ELIGIBLE (employee, slot) pair: pairs that are unqualified or unavailable are never
created, which keeps the model small. For an employee trained on the rotation the variable means "works the
slot"; for one still learning it, "attends as a trainee", with a pairing variable choosing the trainer.

Hard constraints: overlap, daily and weekly caps, minimum rest between work periods, trainee limits and
trainer pairing, no overstaffing. Coverage is SOFT: each slot has a shortage variable with a large penalty,
so an impossible instance yields the best partial schedule instead of "infeasible".

The model-building code takes the cp_model module as a parameter, so tests can run the exact same code against a
tiny exhaustive evaluator (tests/fake_cp.py) and prove the formulation matches the independent validator.
OR-Tools renamed its Python API (CamelCase -> snake_case) across releases; `_method` accepts either.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field

from .models import Assignment, Instance, Schedule, Slot
from .objective import Weights, ideal_minutes


def _method(obj, snake: str, camel: str):
    fn = getattr(obj, snake, None)
    return fn if fn is not None else getattr(obj, camel)


def _prop(obj, snake: str, camel: str):
    for name in (snake, camel):
        if hasattr(obj, name):
            value = getattr(obj, name)
            return value() if callable(value) else value
    raise AttributeError(f"{type(obj).__name__} has neither {snake} nor {camel}")


def _lin_sum(cp, terms):
    terms = list(terms)
    if not terms:
        return 0
    linear = getattr(cp, "LinearExpr", None)
    fn = (getattr(linear, "sum", None) or getattr(linear, "Sum", None)) if linear is not None else None
    return fn(terms) if fn is not None else sum(terms)


def add_consecutive_day_limit(add, instance: Instance, employee, day_worked: dict, limit: int) -> None:
    """EXERCISE (part 2): forbid working more than `limit` days in a row.

    `day_worked` maps a day index to a 0/1 variable that is 1 exactly when `employee` works any slot that day.
    Days on which the employee has no candidate slots are absent: treat them as not worked.
    `add` is the model's add-constraint function. In any run of limit + 1 consecutive days, at least one day
    must be a day off. Match the validator's definition (see consecutive_day_violations in validate.py).
    Remove the xfail marker from the solver test when it works.
    """
    return None


@dataclass
class _Built:
    model: object
    x: dict  # (employee_id, slot_id) -> variable
    pairs: dict  # (trainee_id, slot_id) -> [(trainer_id, variable)]
    short: dict  # slot_id -> shortage variable


def _build(cp, instance: Instance, weights: Weights) -> _Built:
    model = cp.CpModel()
    new_bool = _method(model, "new_bool_var", "NewBoolVar")
    new_int = _method(model, "new_int_var", "NewIntVar")
    add = _method(model, "add", "Add")
    at_most_one = _method(model, "add_at_most_one", "AddAtMostOne")
    abs_equality = _method(model, "add_abs_equality", "AddAbsEquality")
    minimize = _method(model, "minimize", "Minimize")

    rules, emps = instance.rules, instance.employees_by_id
    slots = instance.slots
    x: dict[tuple[str, str], object] = {}
    workers_in: dict[str, list[str]] = defaultdict(list)
    trainees_in: dict[str, list[str]] = defaultdict(list)
    pairs: dict[tuple[str, str], list[tuple[str, object]]] = {}

    for s in slots:
        for e in instance.eligible_workers(s):
            x[(e.id, s.id)] = new_bool(f"w_{e.id}_{s.id}")
            workers_in[s.id].append(e.id)

    for s in slots:
        trainers = [t for t in workers_in[s.id] if s.rotation_id in emps[t].trainer_for]
        if not trainers or s.max_trainees < 1 or rules.max_trainees_per_trainer < 1:
            continue
        for e in instance.eligible_trainees(s):
            var = new_bool(f"t_{e.id}_{s.id}")
            x[(e.id, s.id)] = var
            trainees_in[s.id].append(e.id)
            options = []
            for t in trainers:
                p = new_bool(f"p_{e.id}_{t}_{s.id}")
                add(p <= x[(t, s.id)])  # the trainer must actually be working the slot
                options.append((t, p))
            add(_lin_sum(cp, [p for _, p in options]) == var)  # exactly one trainer if attending
            pairs[(e.id, s.id)] = options

    short: dict[str, object] = {}
    for s in slots:
        short[s.id] = new_int(0, s.headcount, f"short_{s.id}")
        add(_lin_sum(cp, [x[(e, s.id)] for e in workers_in[s.id]]) + short[s.id] == s.headcount)
        if trainees_in[s.id]:
            add(_lin_sum(cp, [x[(e, s.id)] for e in trainees_in[s.id]]) <= s.max_trainees)
        for t in workers_in[s.id]:
            mine = [p for e in trainees_in[s.id] for tt, p in pairs[(e, s.id)] if tt == t]
            if mine:
                add(_lin_sum(cp, mine) <= rules.max_trainees_per_trainer)

    ideal = ideal_minutes(instance)
    terms = [weights.coverage * s.minutes * short[s.id] for s in slots]

    for emp in instance.employees:
        mine = [(s, x[(emp.id, s.id)]) for s in slots if (emp.id, s.id) in x]
        by_day: dict[int, list[tuple[Slot, object]]] = defaultdict(list)
        for s, v in mine:
            by_day[s.day].append((s, v))

        for items in by_day.values():  # no double-booking
            items.sort(key=lambda sv: (sv[0].start, sv[0].end))
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    if items[j][0].start >= items[i][0].end:
                        break
                    at_most_one([items[i][1], items[j][1]])

        for items in by_day.values():  # daily cap (overlaps are excluded, so a plain sum is the union)
            add(_lin_sum(cp, [s.minutes * v for s, v in items]) <= rules.max_daily_minutes)
        by_week: dict[int, list[tuple[Slot, object]]] = defaultdict(list)
        for day, items in by_day.items():
            by_week[day // 7].extend(items)
        cap = math.floor(emp.max_hours_week * 60 + 1e-9)
        for items in by_week.values():
            add(_lin_sum(cp, [s.minutes * v for s, v in items]) <= cap)

        _add_rest_constraints(cp, add, mine, rules.min_rest_minutes)

        if rules.max_consecutive_days is not None:
            day_worked = {}
            for day, items in by_day.items():
                worked = new_bool(f"day_{emp.id}_{day}")
                for _, v in items:
                    add(v <= worked)
                add(worked <= _lin_sum(cp, [v for _, v in items]))
                day_worked[day] = worked
            add_consecutive_day_limit(add, instance, emp, day_worked, rules.max_consecutive_days)

        # Objective terms for this employee.
        total_ub = max(1, sum(s.minutes for s, _ in mine))
        bound = max(total_ub, ideal[emp.id])
        worked_min = new_int(0, total_ub, f"W_{emp.id}")
        add(worked_min == _lin_sum(cp, [s.minutes * v for s, v in mine]))
        diff = new_int(-bound, bound, f"diff_{emp.id}")
        add(diff == worked_min - ideal[emp.id])
        deviation = new_int(0, bound, f"dev_{emp.id}")
        abs_equality(deviation, diff)  # exact |W - ideal|, not just an upper bound
        terms.append(weights.fairness * deviation)
        for s, v in mine:
            if s.day in emp.preferred_days_off:
                terms.append(weights.preference * s.minutes * v)
            if s.rotation_id in emp.in_training:
                terms.append(-weights.training * s.minutes * v)

    minimize(_lin_sum(cp, terms))
    return _Built(model, x, pairs, short)


def _add_rest_constraints(cp, add, mine: list[tuple[Slot, object]], min_rest: int) -> None:
    """Minimum rest between work periods, where touching blocks form ONE period.

    Cut the employee's candidate time into elementary segments; busy[k] is 1 when a chosen slot covers segment k.
    For two segments i < j separated by a gap g with 0 < g < min_rest: if both are busy, some segment between them
    must be busy too (otherwise the gap is real rest time that is too short). Pairs whose gap is covered by chosen
    slots are exactly the "same work period" case, so touching blocks are never penalized.
    """
    if min_rest <= 0 or len(mine) < 2:
        return
    bounds = sorted({b for s, _ in mine for b in (s.abs_start, s.abs_end)})
    segments = []
    for lo, hi in zip(bounds, bounds[1:]):
        cover = [v for s, v in mine if s.abs_start <= lo and hi <= s.abs_end]
        if cover:
            segments.append((lo, hi, cover))
    busy = [_lin_sum(cp, cover) for _, _, cover in segments]
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            gap = segments[j][0] - segments[i][1]
            if gap >= min_rest:
                break  # later segments are only further away
            if gap <= 0:
                continue  # touching: same work period
            between = _lin_sum(cp, [busy[k] for k in range(i + 1, j)])
            add(busy[i] + busy[j] <= 1 + between)


def _extract(instance: Instance, x: dict, pairs: dict, value) -> Schedule:
    out = []
    for (eid, sid), var in x.items():
        if not value(var):
            continue
        emp, slot = instance.employees_by_id[eid], instance.slots_by_id[sid]
        if slot.rotation_id in emp.trained:
            out.append(Assignment(eid, sid, "worker"))
        else:
            trainer = next((t for t, p in pairs.get((eid, sid), []) if value(p)), None)
            out.append(Assignment(eid, sid, "trainee", trainer))
    return Schedule(tuple(sorted(out, key=lambda a: (a.slot_id, a.employee_id))))


@dataclass(frozen=True)
class SolveResult:
    schedule: Schedule
    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN, MODEL_INVALID
    objective: float | None
    bound: float | None
    gap: float | None  # relative distance from the proven lower bound (0 = proven optimal)
    seconds: float
    variables: int = field(default=0)


def solve_cpsat(instance: Instance, *, time_limit: float = 10.0, workers: int = 8, seed: int = 0,
                weights: Weights = Weights()) -> SolveResult:
    from ortools.sat.python import cp_model  # imported here so the rest of the package needs no OR-Tools

    started = time.perf_counter()
    built = _build(cp_model, instance, weights)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.random_seed = int(seed)
    try:
        solver.parameters.num_workers = int(workers)
    except (AttributeError, ValueError):
        solver.parameters.num_search_workers = int(workers)  # older releases

    status = _method(solver, "solve", "Solve")(built.model)
    names = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE", cp_model.INFEASIBLE: "INFEASIBLE",
             cp_model.MODEL_INVALID: "MODEL_INVALID", cp_model.UNKNOWN: "UNKNOWN"}
    name = names.get(status, str(status))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(Schedule(), name, None, None, None, time.perf_counter() - started, len(built.x))

    value = _method(solver, "value", "Value")
    objective = float(_prop(solver, "objective_value", "ObjectiveValue"))
    bound = float(_prop(solver, "best_objective_bound", "BestObjectiveBound"))
    schedule = _extract(instance, built.x, built.pairs, value)
    return SolveResult(schedule, name, objective, bound, max(0.0, (objective - bound) / max(1.0, abs(objective))),
                       time.perf_counter() - started, len(built.x))
