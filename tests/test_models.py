import pytest

from scheduler.models import Block, Employee, Interval, Rotation
from tests.helpers import employee, instance, rotation


def raises_value_error(fn):
    with pytest.raises(ValueError):
        fn()


def test_invalid_values_are_rejected():
    raises_value_error(lambda: Interval(600, 600))
    raises_value_error(lambda: Interval(-5, 100))
    raises_value_error(lambda: Interval(0, 1441))
    raises_value_error(lambda: Block("AM", 420, 660, 0))
    raises_value_error(lambda: Rotation("r", "R", (Block("A", 420, 660, 1), Block("A", 700, 800, 1))))  # duplicate names
    raises_value_error(lambda: Rotation("r", "R", (Block("A", 420, 660, 1), Block("B", 600, 800, 1))))  # overlap
    raises_value_error(lambda: Rotation("r", "R", ()))


def test_employee_validation():
    raises_value_error(lambda: employee("e1", color="blue"))
    raises_value_error(lambda: employee("e1", color="#12345"))
    raises_value_error(lambda: employee("e1", trained=("r1",), trainer_for=("r2",)))   # can't train what you can't do
    raises_value_error(lambda: employee("e1", trained=("r1",), in_training=("r1",)))   # can't be both
    raises_value_error(lambda: employee("e1", max_hours=10, target=20))
    assert employee("e1", color="#aBc123").color == "#aBc123"


def test_instance_validation():
    raises_value_error(lambda: instance([rotation("r1"), rotation("r1")], []))
    raises_value_error(lambda: instance([rotation("r1")], [employee("e1"), employee("e1")]))
    raises_value_error(lambda: instance([rotation("r1")], [employee("e1", trained=("nope",))]))


def test_slots_expand_blocks_across_weekdays_only():
    inst = instance([rotation("r1")], [employee("e1")], num_days=7, start_weekday=5)  # starts on a Saturday
    assert len(inst.slots) == 10                      # 5 weekdays x 2 blocks
    assert inst.slots[0].day == 2                     # first Monday
    assert inst.slots[0].id == "r1:2:AM"
    assert {s.rotation_id for s in inst.slots} == {"r1"}


def test_availability_must_contain_the_whole_slot():
    slot = instance([rotation("r1")], [employee("e1")]).slots_by_id["r1:0:AM"]  # 07:00-11:00
    short = instance([rotation("r1")], [employee("e1", windows=((360, 600),))])      # until 10:00
    long = instance([rotation("r1")], [employee("e1", windows=((360, 720),))])       # until 12:00
    assert not short.can_work(short.employees[0], slot)
    assert long.can_work(long.employees[0], slot)


def test_eligibility_checks_training_days_off_and_weekday():
    inst = instance(
        [rotation("r1"), rotation("r2")],
        [employee("a", trained=("r1",)), employee("b", trained=("r2",)), employee("c", trained=("r1",), days_off=(0,)),
         employee("d", trained=("r1",), weekdays=(1, 2)), employee("t", trained=(), in_training=("r1",))])
    slot = inst.slots_by_id["r1:0:AM"]
    assert [e.id for e in inst.eligible_workers(slot)] == ["a"]       # b untrained, c off, d not available Mondays
    assert [e.id for e in inst.eligible_trainees(slot)] == ["t"]
