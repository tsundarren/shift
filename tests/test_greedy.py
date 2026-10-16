import statistics

from scheduler.generate import generate_instance
from scheduler.greedy import solve_greedy
from scheduler.metrics import quality_report
from scheduler.validate import validate


def test_greedy_never_breaks_a_hard_rule():
    for seed in range(10):
        for tightness in (0.4, 0.7, 1.0, 1.3):
            inst = generate_instance(seed=seed, tightness=tightness)
            assert validate(inst, solve_greedy(inst)) == [], (seed, tightness)


def test_greedy_is_deterministic():
    inst = generate_instance(seed=1)
    assert solve_greedy(inst) == solve_greedy(inst)


def test_coverage_falls_as_the_problem_gets_tighter():
    def mean_coverage(tightness):
        return statistics.fmean(
            quality_report(i, solve_greedy(i)).coverage_pct
            for i in (generate_instance(seed=s, tightness=tightness) for s in range(10)))
    easy, hard = mean_coverage(0.4), mean_coverage(1.3)
    assert easy > 95
    assert hard < easy


def test_trainees_are_placed_with_trainers():
    placed = 0
    for seed in range(6):
        inst = generate_instance(seed=seed, tightness=0.5)
        schedule = solve_greedy(inst)
        trainees = [a for a in schedule.assignments if a.role == "trainee"]
        placed += len(trainees)
        for a in trainees:
            assert a.trainer_id is not None
    assert placed > 0
