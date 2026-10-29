from scheduler.generate import generate_instance
from scheduler.models import Assignment, Schedule
from scheduler.objective import Weights, schedule_cost
from scheduler.overrides import (Change, Overrides, check_overrides, describe_change, diff_schedules, find_blockers,
                                 pair_exists, static_blockers)
from tests.helpers import employee, instance, rotation, schedule

AM_ONLY = (("AM", 420, 660),)


def world(**rules):
    rots = [rotation("r1", blocks=(("AM", 420, 660), ("PM", 660, 900))), rotation("r2", blocks=(("Late", 840, 1200),))]
    emps = [employee("sam"), employee("ann", trained=("r1", "r2"), windows=((360, 1260),)),
            employee("tom", trained=("r2",), windows=((360, 1260),)), employee("lee", days_off=(0,)),
            employee("pt", windows=((360, 600),)), employee("wk", weekdays=(1, 2))]
    return instance(rots, emps, num_days=3, **rules)


def codes(blockers):
    return [b.code for b in blockers]


def blockers_for(inst, sched, who, slot):
    return find_blockers(inst, sched, who, slot)


def test_nothing_blocks_a_free_qualified_person():
    assert blockers_for(world(), schedule(), "sam", "r1:0:AM") == []


def test_already_assigned_names_the_person_and_slot():
    (b,) = blockers_for(world(), schedule(("sam", "r1:0:AM")), "sam", "r1:0:AM")
    assert b.code == "already_assigned" and "SAM" in b.message and "AM" in b.message


def test_static_reasons():
    inst = world()
    assert codes(blockers_for(inst, schedule(), "tom", "r1:0:AM")) == ["not_trained"]
    assert codes(blockers_for(inst, schedule(), "lee", "r1:0:AM")) == ["day_off"]
    assert codes(blockers_for(inst, schedule(), "wk", "r1:0:AM")) == ["unavailable_day"]       # day 0 is a Monday
    (window,) = blockers_for(inst, schedule(), "pt", "r1:0:AM")
    assert window.code == "unavailable_window" and "06:00-10:00" in window.message and "07:00-11:00" in window.message


def test_slot_full_names_who_is_already_there():
    (b,) = blockers_for(world(), schedule(("ann", "r1:0:AM")), "sam", "r1:0:AM")
    assert b.code == "slot_full" and "ANN" in b.message


def test_dynamic_reasons_from_the_persons_other_shifts():
    assert codes(blockers_for(world(), schedule(("ann", "r1:0:PM")), "ann", "r2:0:Late")) == ["overlap"]
    assert codes(blockers_for(world(max_daily_minutes=300), schedule(("ann", "r1:0:AM")), "ann", "r1:0:PM")) == ["daily_limit"]
    assert codes(blockers_for(world(min_rest_minutes=720), schedule(("ann", "r2:0:Late")), "ann", "r1:1:AM")) == ["insufficient_rest"]
    capped = instance([rotation("r1")], [employee("e1", max_hours=4, target=4)], num_days=1)
    assert codes(find_blockers(capped, schedule(("e1", "r1:0:AM")), "e1", "r1:0:PM")) == ["weekly_limit"]


def test_trainee_reasons():
    inst = instance([rotation("r1", blocks=AM_ONLY)],
                    [employee("tr", trainer_for=("r1",)), employee("a", trained=(), in_training=("r1",)),
                     employee("b", trained=(), in_training=("r1",))], num_days=1)
    ok = schedule(("tr", "r1:0:AM"), Assignment("a", "r1:0:AM", "trainee", "tr"))
    assert codes(find_blockers(inst, ok, "b", "r1:0:AM")) == ["trainee_spots_full"]
    assert codes(find_blockers(inst, schedule(), "a", "r1:0:AM")) == []       # a trainer exists, so it's possible

    no_trainer = instance([rotation("r1", blocks=AM_ONLY)],
                          [employee("x"), employee("a", trained=(), in_training=("r1",))], num_days=1)
    assert codes(find_blockers(no_trainer, schedule(), "a", "r1:0:AM")) == ["no_trainer"]


def test_pair_exists_agrees_with_the_static_reasons_everywhere():
    for seed in range(3):
        inst = generate_instance(seed=seed, num_rotations=3, num_days=3, tightness=0.8)
        for e in inst.employees:
            for s in inst.slots:
                assert pair_exists(inst, e, s) == (not static_blockers(inst, e, s)), (seed, e.id, s.id)


def test_check_overrides_accepts_compatible_overrides():
    assert check_overrides(world(), Overrides(pins=frozenset({("sam", "r1:0:AM"), ("ann", "r1:0:PM")}))) == []


def test_check_overrides_finds_each_kind_of_problem():
    inst = world()
    def rules(**kw):
        return {v.rule for v in check_overrides(inst, Overrides(**kw))}
    assert rules(pins=frozenset({("ghost", "r1:0:AM")})) == {"override_unknown_reference"}
    assert rules(pins=frozenset({("tom", "r1:0:AM")})) == {"pin_ineligible"}
    assert rules(pins=frozenset({("sam", "r1:0:AM")}), bans=frozenset({("sam", "r1:0:AM")})) == {"pin_and_ban"}
    assert rules(pins=frozenset({("ann", "r1:0:PM"), ("ann", "r2:0:Late")})) == {"pin_conflict"}      # overlapping shifts
    assert rules(pins=frozenset({("sam", "r1:0:AM"), ("ann", "r1:0:AM")})) == {"pin_overstaffed"}


def test_diff_and_descriptions():
    inst = world()
    changes = diff_schedules(schedule(("sam", "r1:0:AM"), ("ann", "r1:1:AM")), schedule(("ann", "r1:1:AM"), ("lee", "r1:1:PM")))
    assert changes == [Change("removed", "sam", "r1:0:AM", "worker"), Change("added", "lee", "r1:1:PM", "worker")]
    assert describe_change(inst, changes[0]).startswith("Remove SAM from R1 AM on Mon")
    assert describe_change(inst, changes[1]).startswith("Add LEE to R1 PM on Tue")


def test_stability_cost_counts_added_and_removed_minutes():
    inst = instance([rotation("r1", blocks=AM_ONLY)], [employee("e1", target=16), employee("e2", target=16)], num_days=2)
    before = schedule(("e1", "r1:0:AM"), ("e2", "r1:1:AM"))
    after = schedule(("e1", "r1:0:AM"), ("e1", "r1:1:AM"))                      # e2 removed, e1 added: 2 x 240 minutes
    w = Weights(stability=3)
    assert schedule_cost(inst, after, w).stability == 0
    assert schedule_cost(inst, after, w, previous=before).stability == 3 * 480
    assert schedule_cost(inst, before, w, previous=before).stability == 0
    assert schedule_cost(inst, after, w, previous=before).total == schedule_cost(inst, after, w).total + 1440
