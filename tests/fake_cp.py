"""A tiny stand-in for ortools.sat.python.cp_model, used to verify the model FORMULATION by exhaustive search.

It supports exactly the modeling calls scheduler/cpsat.py makes: boolean and bounded integer variables, linear
expressions, <= / >= / == constraints, at-most-one, abs-equality and minimize. `exhaustive_solve` tries every 0/1
assignment, derives the integer variables from the equality constraints that define them, checks every constraint,
and returns the best objective. Only usable on tiny models (about 20 boolean variables).

This does NOT test OR-Tools itself. It tests that the constraints and objective WE wrote mean what we intend.
"""
import itertools


class Expr:
    def __init__(self, terms=None, const=0):
        self.terms = dict(terms or {})
        self.const = const

    @staticmethod
    def of(x):
        if isinstance(x, Expr):
            return x
        if isinstance(x, bool) or not isinstance(x, int):
            raise TypeError(f"unexpected operand {x!r}")
        return Expr({}, x)

    def _combine(self, other, sign):
        o = Expr.of(other)
        terms = dict(self.terms)
        for v, c in o.terms.items():
            terms[v] = terms.get(v, 0) + sign * c
        return Expr({v: c for v, c in terms.items() if c != 0}, self.const + sign * o.const)

    def __add__(self, other):
        return self._combine(other, 1)

    __radd__ = __add__

    def __sub__(self, other):
        return self._combine(other, -1)

    def __rsub__(self, other):
        return Expr.of(other)._combine(self, -1)

    def __mul__(self, k):
        if isinstance(k, bool) or not isinstance(k, int):
            raise TypeError(f"can only scale by an int, got {k!r}")
        return Expr({v: c * k for v, c in self.terms.items()}, self.const * k)

    __rmul__ = __mul__

    def __neg__(self):
        return self * -1

    def __le__(self, other):
        return Constraint(self._combine(other, -1), "<=")

    def __ge__(self, other):
        return Constraint(self._combine(other, -1), ">=")

    def __eq__(self, other):
        return Constraint(self._combine(other, -1), "==")

    def __hash__(self):
        return id(self)

    def value_in(self, env):
        return self.const + sum(c * env[v] for v, c in self.terms.items())


class Var(Expr):
    def __init__(self, lb, ub, name, is_bool):
        super().__init__()
        self.lb, self.ub, self.name, self.is_bool = lb, ub, name, is_bool
        self.terms = {self: 1}


class Constraint:
    def __init__(self, expr, op):
        self.expr, self.op = expr, op  # the constraint is: expr <op> 0

    def holds(self, env):
        v = self.expr.value_in(env)
        return v <= 0 if self.op == "<=" else v >= 0 if self.op == ">=" else v == 0

    def __bool__(self):
        raise TypeError("a constraint was used as a boolean (probably a comparison of two plain numbers)")


class CpModel:
    def __init__(self):
        self.vars, self.constraints, self.abs_eqs, self.objective = [], [], [], None

    def new_bool_var(self, name):
        v = Var(0, 1, name, True)
        self.vars.append(v)
        return v

    def new_int_var(self, lb, ub, name):
        v = Var(lb, ub, name, False)
        self.vars.append(v)
        return v

    def add(self, constraint):
        assert isinstance(constraint, Constraint), f"add() needs a constraint, got {constraint!r}"
        self.constraints.append(constraint)
        return constraint

    def add_at_most_one(self, variables):
        total = Expr()
        for v in variables:
            total = total + v
        self.add(total <= 1)

    def add_abs_equality(self, target, expr):
        self.abs_eqs.append((target, Expr.of(expr)))

    def minimize(self, expr):
        self.objective = Expr.of(expr)


def _resolve(model, env, ints):
    unresolved = set(ints)
    progress = True
    while unresolved and progress:
        progress = False
        for c in model.constraints:
            if c.op != "==":
                continue
            unknown = [v for v in c.expr.terms if v in unresolved]
            if len(unknown) == 1 and abs(c.expr.terms[unknown[0]]) == 1:
                u = unknown[0]
                coef = c.expr.terms[u]
                rest = c.expr.const + sum(co * env[v] for v, co in c.expr.terms.items() if v is not u)
                env[u] = -rest * coef
                unresolved.discard(u)
                progress = True
        for target, expr in model.abs_eqs:
            if target in unresolved and all(v in env for v in expr.terms):
                env[target] = abs(expr.value_in(env))
                unresolved.discard(target)
                progress = True
    return not unresolved


def exhaustive_solve(model, max_bools=20):
    """Returns (best_objective, [every env achieving it]), or None if the model is infeasible."""
    bools = [v for v in model.vars if v.is_bool]
    ints = [v for v in model.vars if not v.is_bool]
    if len(bools) > max_bools:
        raise ValueError(f"{len(bools)} boolean variables is too many for exhaustive search")
    best = None
    for bits in itertools.product((0, 1), repeat=len(bools)):
        env = dict(zip(bools, bits))
        if not _resolve(model, env, ints):
            continue
        if any(not (v.lb <= env[v] <= v.ub) for v in ints):
            continue
        if not all(c.holds(env) for c in model.constraints):
            continue
        objective = model.objective.value_in(env)
        if best is None or objective < best[0]:
            best = (objective, [dict(env)])
        elif objective == best[0]:
            best[1].append(dict(env))
    return best
