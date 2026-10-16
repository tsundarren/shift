from scheduler.metrics import quality_report
from tests.helpers import employee, instance, rotation, schedule
from scheduler.models import Assignment


def test_metrics_on_a_hand_computed_example():
    # One rotation, 2 blocks/day needing 2 workers each, over 7 days Mon-Sun: 5 weekdays x 2 blocks = 10 slots, 20 seats.
    inst = instance([rotation("r1", headcount=2)],
                    [employee("e1", target=8, preferred_off=(0,)), employee("e2", target=8, in_training=(), trained=("r1",))],
                    num_days=7)
    sched = schedule(("e1", "r1:0:AM"), ("e1", "r1:0:PM"), ("e2", "r1:0:AM"))
    r = quality_report(inst, sched)

    assert r.valid and r.violations == 0
    assert r.seats_required == 20 and r.seats_filled == 3
    assert round(r.coverage_pct, 1) == 15.0
    assert r.uncovered_slots == 9                        # only Monday AM (2 of 2 workers) is fully staffed
    assert (r.hours_min, r.hours_max) == (4.0, 8.0)      # e2 worked 4h, e1 worked 8h
    assert r.over_target_hours == 0.0 and r.under_target_hours == 4.0   # e2 is 4h under its 8h target
    assert r.preferred_off_worked == 2                   # e1 worked two slots on a preferred day off
    assert r.trainee_assignments == 0


def test_invalid_schedules_are_reported_not_hidden():
    inst = instance([rotation("r1")], [employee("e1")], num_days=7)
    r = quality_report(inst, schedule(("e1", "r1:0:AM"), ("e1", "r1:0:AM")))
    assert not r.valid and r.violations == 1


def test_trainees_count_toward_hours_but_not_coverage():
    inst = instance([rotation("r1")], [employee("tr", trainer_for=("r1",)), employee("a", trained=(), in_training=("r1",))], num_days=7)
    r = quality_report(inst, schedule(("tr", "r1:0:AM"), Assignment("a", "r1:0:AM", "trainee", "tr")))
    assert r.valid and r.trainee_assignments == 1
    assert r.seats_filled == 1 and r.hours_max == 4.0 and r.hours_min == 4.0
