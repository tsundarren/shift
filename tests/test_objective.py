from scheduler.generate import generate_instance
from scheduler.greedy import solve_greedy
from scheduler.models import Assignment, Schedule
from scheduler.objective import Weights, ideal_minutes, schedule_cost
from tests.helpers import employee, instance, rotation, schedule

W = Weights(coverage=100, fairness=2, preference=5, training=1)


def week_instance():
    # 5 weekdays x 2 blocks of 240 minutes, headcount 1: demand = 2400 minutes.
    return instance([rotation("r1")], [employee("e1", target=30, preferred_off=(0,)), employee("e2", target=10)], num_days=7)


def test_ideal_minutes_split_demand_in_proportion_to_target_hours():
    assert ideal_minutes(week_instance()) == {"e1": 1800, "e2": 600}


def test_cost_breakdown_on_a_hand_computed_schedule():
    sched = schedule(("e1", "r1:0:AM"), ("e1", "r1:0:PM"))        # e1 works Monday only, on a preferred day off
    cost = schedule_cost(week_instance(), sched, W)
    assert cost.coverage == 100 * 8 * 240                           # 8 of 10 slots empty
    assert cost.fairness == 2 * (abs(480 - 1800) + abs(0 - 600))
    assert cost.preference == 5 * 480
    assert cost.training == 0
    assert cost.total == 192000 + 3840 + 2400


def test_training_minutes_are_a_reward():
    inst = instance([rotation("r1", blocks=(("AM", 420, 660),))],
                    [employee("tr", trainer_for=("r1",)), employee("a", trained=(), in_training=("r1",))], num_days=1)
    sched = schedule(("tr", "r1:0:AM"), Assignment("a", "r1:0:AM", "trainee", "tr"))
    assert schedule_cost(inst, sched, W).training == -240


def test_bad_references_and_duplicates_are_ignored():
    inst = week_instance()
    clean = schedule_cost(inst, schedule(("e1", "r1:1:AM")), W)
    noisy = schedule_cost(inst, schedule(("e1", "r1:1:AM"), ("e1", "r1:1:AM"), ("ghost", "r1:1:AM"), ("e1", "nope")), W)
    assert clean == noisy


def test_a_better_schedule_costs_less_and_empty_is_the_worst_coverage():
    inst = generate_instance(seed=2, num_days=7, tightness=0.7)
    empty, greedy = schedule_cost(inst, Schedule(), Weights()), schedule_cost(inst, solve_greedy(inst), Weights())
    assert greedy.coverage < empty.coverage
    assert greedy.total < empty.total
