# ShiftWise

[![CI](https://github.com/tsundarren/shift/actions/workflows/ci.yml/badge.svg)](https://github.com/tsundarren/shift/actions/workflows/ci.yml)

A scheduling engine that assigns staff to rotations (tasks or stations) across a week or two,
respecting hard rules, optimizing soft goals, and explaining its decisions.

**All data is synthetic.** The project is reimplementation inspired by an internal scheduling tool I built at work.

**Status:** Milestone 1 of 4: domain model, synthetic data generator, independent validator, greedy baseline,
and quality metrics. The optimization solver, explanations, API, and dashboard are on the [Roadmap](#roadmap).

## The model

- **Rotations** are the base: user-created tasks, each split into **blocks** (e.g. AM and PM) with their own headcount.
  A block on a given day is a **slot**, the unit that gets staffed.
- **Employees** have a list of trained rotations (the checkboxes), a free-text **rank**, a hex **color**, availability
  windows by weekday (so part-day staff can cover some blocks but not others), approved days off, and preferred days off.
- **Trainees:** an employee can be assigned to a rotation they're still learning, paired with a certified trainer who is
  working the same slot: "John (trained by Jane)".
- A rotation that needs three people gets three assignments, which is how a part-day employee's AM block and a colleague's
  PM block add up to full coverage.

## Design decisions

**Independent validator.** `scheduler/validate.py` is the source of truth for the hard rules and shares no code with
the greedy baseline or the (upcoming) solver, so a modeling bug can't hide itself. Every schedule from any algorithm
must pass it.

**Pure-Python core.** `scheduler/` has no web, database, or solver dependencies, so it is fully unit-testable.

**Synthetic instances with a tightness dial.** `generate_instance(seed, tightness=...)` sizes the workforce relative
to demand so algorithms can be compared on easy and hard problems across many seeds.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
python -m scripts.demo --seed 3 --tightness 0.7 --days 7   # prints a schedule and quality report
```

## Project layout

```
scheduler/
  models.py     rotations, blocks, slots, employees, assignments, eligibility
  validate.py   independent hard-rule checker
  generate.py   synthetic instance generator
  greedy.py     baseline algorithm
  metrics.py    quality report
scripts/demo.py
tests/
```

## Roadmap

- [x] Domain model, generator, validator, greedy baseline, metrics
- [ ] Rule: maximum consecutive working days (exercise, see `consecutive_day_violations` in `validate.py`)
- [ ] CP-SAT solver with soft coverage and a benchmark against greedy
- [ ] Explanations ("why isn't Sam on Tuesday?") and manual overrides with a stability penalty
- [ ] FastAPI + PostgreSQL
- [ ] React dashboard: employee cards (rank color), rotation editor, schedule grid, eligible-staff dropdowns
- [ ] Deployment, demo GIF, benchmark table

## Known limits

- Not a labor-law compliance engine. The rules are illustrative.
- Shifts live within a single day (no overnight blocks yet).
- The greedy baseline can't look ahead or undo choices; that is the point of comparing it with a solver.
