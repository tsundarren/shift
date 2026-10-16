"""Small builders so each test reads like a scenario instead of a wall of constructors."""
from scheduler.models import (Assignment, Block, Employee, Horizon, Instance, Interval, Rotation,
                              RuleConfig, Schedule)

AM = ("AM", 420, 660)    # 07:00-11:00
PM = ("PM", 660, 900)    # 11:00-15:00


def rotation(rid="r1", blocks=(AM, PM), headcount=1, weekdays=range(5), max_trainees=1):
    return Rotation(rid, rid.upper(), tuple(Block(n, s, e, headcount) for n, s, e in blocks),
                    frozenset(weekdays), max_trainees)


def employee(eid, trained=("r1",), trainer_for=(), in_training=(), windows=((360, 960),), weekdays=range(7),
             max_hours=40.0, target=32.0, days_off=(), preferred_off=(), rank="Associate", color="#4C9AFF"):
    availability = {wd: tuple(Interval(s, e) for s, e in windows) for wd in weekdays}
    return Employee(eid, eid.upper(), rank, color, frozenset(trained), frozenset(trainer_for), frozenset(in_training),
                    availability, max_hours, target, frozenset(days_off), frozenset(preferred_off))


def instance(rotations, employees, num_days=14, start_weekday=0, **rule_kwargs):
    return Instance(Horizon(start_weekday, num_days), tuple(rotations), tuple(employees), RuleConfig(**rule_kwargs))


def schedule(*assignments):
    return Schedule(tuple(a if isinstance(a, Assignment) else Assignment(*a) for a in assignments))


def rules(violations):
    return {v.rule for v in violations}
