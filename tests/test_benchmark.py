from scripts.benchmark import format_tables, summarize


def record(tightness, g_cost, c_cost, status="OPTIMAL", valid=True):
    return dict(tightness=tightness, seed=0, greedy_coverage=90.0, cpsat_coverage=100.0, greedy_cost=g_cost, cpsat_cost=c_cost,
                cpsat_status=status, cpsat_seconds=2.0, greedy_seconds=0.01, greedy_valid=valid, cpsat_valid=True,
                greedy_parts=(g_cost, 0, 0, 0), cpsat_parts=(c_cost, 0, 0, 0))


def test_summary_counts_wins_ties_and_losses_per_level():
    rows = summarize([record(0.5, 100, 90), record(0.5, 100, 100), record(0.5, 100, 120, status="FEASIBLE"), record(1.0, 500, 100)])
    low, high = rows
    assert (low["tightness"], low["instances"]) == (0.5, 3)
    assert (low["better"], low["tied"], low["worse"]) == (1, 1, 1)
    assert round(low["optimal_pct"]) == 67
    assert (high["better"], high["tied"], high["worse"]) == (1, 0, 0)


def test_tables_are_markdown_with_a_row_per_level():
    text = format_tables(summarize([record(0.5, 100, 90), record(1.0, 500, 100)]))
    assert text.count("| 0.50 |") == 3 and text.count("| 1.00 |") == 3   # one row per level in each of the three tables
    assert text.splitlines()[0].startswith("| Tightness |")


def test_component_table_is_included():
    text = format_tables(summarize([record(0.5, 100, 90), record(0.5, 300, 100)]))
    assert "Mean cost by component" in text
    assert "| 0.50 | 200 | 95 | 0 | 0 | 0 | 0 | 0 | 0 |" in text
