from scheduler.generate import generate_instance


def test_same_seed_gives_the_same_instance_and_different_seeds_differ():
    assert generate_instance(seed=3) == generate_instance(seed=3)
    assert generate_instance(seed=3) != generate_instance(seed=4)


def test_higher_tightness_means_fewer_employees():
    sizes = [len(generate_instance(seed=5, tightness=t).employees) for t in (0.4, 0.7, 1.0)]
    assert sizes[0] > sizes[1] > sizes[2]


def test_explicit_employee_count_overrides_tightness():
    assert len(generate_instance(seed=1, num_employees=12).employees) == 12


def test_every_rotation_has_trained_staff_and_trainers_exist():
    for seed in range(8):
        inst = generate_instance(seed=seed, tightness=0.7)
        for rot in inst.rotations:
            trained = [e for e in inst.employees if rot.id in e.trained]
            assert len(trained) >= 2, (seed, rot.id)
        assert any(e.trainer_for for e in inst.employees)


def test_generated_data_has_the_features_the_solver_will_need():
    inst = generate_instance(seed=2, num_employees=30)
    assert any(e.in_training for e in inst.employees)                       # trainees exist
    assert any(len(e.availability) < 5 for e in inst.employees)             # part-time staff exist
    assert any(e.days_off for e in inst.employees) or any(e.preferred_days_off for e in inst.employees)
    assert len({e.color for e in inst.employees}) >= 2 and len({e.rank for e in inst.employees}) >= 3
