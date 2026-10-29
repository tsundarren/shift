import statistics
from scheduler.generate import generate_instance

def ceiling(inst):
    need = sum(s.headcount for s in inst.slots)
    possible = sum(min(s.headcount, len(inst.eligible_workers(s))) for s in inst.slots)
    return 100 * possible / need

for t in (0.5, 0.7, 1.0, 1.3):
    print(t, round(statistics.fmean(
        ceiling(generate_instance(seed=s, num_rotations=5, num_days=7, tightness=t)) for s in range(10)), 1))