#!/usr/bin/env python3
"""Greedy vs CP-SAT across many random instances at several difficulty levels.

    python -m scripts.benchmark --seeds 10 --time-limit 10          # full run (several minutes)
    python -m scripts.benchmark --quick                             # smoke test

Both algorithms are judged by the SAME validator and the SAME objective (scheduler/objective.py), so the numbers
are comparable. Report these tables as they come out: where greedy is good enough, the solver won't win.
Results depend on the machine and the time limit, so quote both.
"""
from __future__ import annotations

import argparse
import statistics
import time
from collections import defaultdict

from scheduler.generate import generate_instance
from scheduler.greedy import solve_greedy
from scheduler.metrics import quality_report
from scheduler.objective import Weights, schedule_cost


def summarize(records: list[dict]) -> list[dict]:
    """One row per tightness level. Lower cost is better; 'better' counts CP-SAT wins on that cost."""
    by_level: dict[float, list[dict]] = defaultdict(list)
    for r in records:
        by_level[r["tightness"]].append(r)
    rows = []
    for tightness, rs in sorted(by_level.items()):
        mean = lambda key: statistics.fmean(r[key] for r in rs)  # noqa: E731
        rows.append(dict(
            tightness=tightness, instances=len(rs),
            greedy_coverage=mean("greedy_coverage"), cpsat_coverage=mean("cpsat_coverage"),
            greedy_cost=mean("greedy_cost"), cpsat_cost=mean("cpsat_cost"),
            better=sum(1 for r in rs if r["cpsat_cost"] < r["greedy_cost"]),
            tied=sum(1 for r in rs if r["cpsat_cost"] == r["greedy_cost"]),
            worse=sum(1 for r in rs if r["cpsat_cost"] > r["greedy_cost"]),
            optimal_pct=100 * sum(1 for r in rs if r["cpsat_status"] == "OPTIMAL") / len(rs),
            cpsat_seconds=mean("cpsat_seconds"), greedy_seconds=mean("greedy_seconds"),
            greedy_parts=[statistics.fmean(r["greedy_parts"][i] for r in rs) for i in range(4)],
            cpsat_parts=[statistics.fmean(r["cpsat_parts"][i] for r in rs) for i in range(4)],
            greedy_valid_pct=100 * sum(1 for r in rs if r["greedy_valid"]) / len(rs),
            cpsat_valid_pct=100 * sum(1 for r in rs if r["cpsat_valid"]) / len(rs),
        ))
    return rows


def format_tables(rows: list[dict]) -> str:
    out = ["| Tightness | Instances | Coverage: greedy | Coverage: CP-SAT | Mean cost: greedy | Mean cost: CP-SAT | CP-SAT better / tied / worse |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['tightness']:.2f} | {r['instances']} | {r['greedy_coverage']:.1f}% | {r['cpsat_coverage']:.1f}% | "
                   f"{r['greedy_cost']:,.0f} | {r['cpsat_cost']:,.0f} | {r['better']} / {r['tied']} / {r['worse']} |")
    out += ["", "| Tightness | CP-SAT proven optimal | CP-SAT mean time | Greedy mean time | Valid: greedy | Valid: CP-SAT |",
            "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['tightness']:.2f} | {r['optimal_pct']:.0f}% | {r['cpsat_seconds']:.2f}s | {r['greedy_seconds'] * 1000:.0f}ms | "
                   f"{r['greedy_valid_pct']:.0f}% | {r['cpsat_valid_pct']:.0f}% |")
    out += ["", "Mean cost by component (lower is better; training is a reward, so more negative is better):", "",
            "| Tightness | Coverage: greedy | Coverage: CP-SAT | Fairness: greedy | Fairness: CP-SAT | Preference: greedy | "
            "Preference: CP-SAT | Training: greedy | Training: CP-SAT |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [f"{v:,.0f}" for pair in zip(r["greedy_parts"], r["cpsat_parts"]) for v in pair]
        out.append(f"| {r['tightness']:.2f} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def run(args: argparse.Namespace) -> list[dict]:
    from scheduler.cpsat import solve_cpsat

    weights, records = Weights(), []
    for tightness in args.tightness:
        for seed in range(args.seeds):
            inst = generate_instance(seed=seed, num_rotations=args.rotations, num_days=args.days, tightness=tightness)

            t0 = time.perf_counter()
            greedy = solve_greedy(inst)
            greedy_seconds = time.perf_counter() - t0
            result = solve_cpsat(inst, time_limit=args.time_limit, workers=args.workers, seed=seed, weights=weights)

            g_report, c_report = quality_report(inst, greedy), quality_report(inst, result.schedule)
            g_cost, c_cost = schedule_cost(inst, greedy, weights), schedule_cost(inst, result.schedule, weights)
            records.append(dict(
                tightness=tightness, seed=seed,
                greedy_coverage=g_report.coverage_pct, cpsat_coverage=c_report.coverage_pct,
                greedy_cost=g_cost.total, cpsat_cost=c_cost.total,
                greedy_parts=(g_cost.coverage, g_cost.fairness, g_cost.preference, g_cost.training),
                cpsat_parts=(c_cost.coverage, c_cost.fairness, c_cost.preference, c_cost.training),
                cpsat_status=result.status, cpsat_seconds=result.seconds, greedy_seconds=greedy_seconds,
                greedy_valid=g_report.valid, cpsat_valid=c_report.valid,
            ))
            print(f"  tightness {tightness:.2f} seed {seed}: greedy {records[-1]['greedy_cost']:,} "
                  f"vs CP-SAT {records[-1]['cpsat_cost']:,} ({result.status}, {result.seconds:.1f}s)", flush=True)
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--tightness", type=float, nargs="+", default=[0.5, 0.7, 1.0, 1.3])
    ap.add_argument("--rotations", type=int, default=5)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--time-limit", type=float, default=10.0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--quick", action="store_true", help="3 seeds, 3 s limit")
    args = ap.parse_args()
    if args.quick:
        args.seeds, args.time_limit = 3, 3.0
    print(f"Benchmark: {args.seeds} seeds x {len(args.tightness)} levels, {args.days} days, {args.rotations} rotations, "
          f"time limit {args.time_limit}s, {args.workers} workers\n")
    rows = summarize(run(args))
    print("\n" + format_tables(rows))


if __name__ == "__main__":
    main()
