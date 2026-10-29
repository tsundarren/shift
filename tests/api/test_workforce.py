from tests.api.conftest import make_employee, make_rotation


def test_a_rotation_round_trips_with_times_as_hhmm(client):
    created = make_rotation(client, name="Processing", blocks=(("Early", "06:30", "10:00", 2), ("Late", "10:00", "14:00", 3)))
    assert created["id"] == 1 and created["active"] is True
    listed = client.get("/api/rotations").json()
    assert [b["start"] for b in listed[0]["blocks"]] == ["06:30", "10:00"] and listed[0]["blocks"][1]["headcount"] == 3


def test_bad_rotations_are_rejected_with_a_reason(client):
    def post(**changes):
        body = dict(name="X", weekdays=[0], max_trainees=1, blocks=[dict(name="AM", start="07:00", end="11:00", headcount=1)]) | changes
        return client.post("/api/rotations", json=body)
    overlapping = post(blocks=[dict(name="A", start="07:00", end="11:00", headcount=1), dict(name="B", start="10:00", end="12:00", headcount=1)])
    assert overlapping.status_code == 422 and "overlap" in overlapping.json()["detail"]
    assert post(blocks=[dict(name="AM", start="7pm", end="11:00", headcount=1)]).status_code == 422
    assert post(blocks=[dict(name="AM", start="11:00", end="07:00", headcount=1)]).status_code == 422
    assert post(weekdays=[9]).status_code == 422
    assert post(blocks=[]).status_code == 422


def test_an_employee_round_trips_with_levels_availability_and_time_off(client):
    rotation = make_rotation(client)
    made = make_employee(client, "Ava", [(rotation["id"], "trainer")], color="#36B37E", rank="Senior", window=("06:00", "12:00"),
                         weekdays=[0, 2], time_off=[("2026-11-04", "approved"), ("2026-11-05", "preferred")])
    got = client.get("/api/employees").json()[0]
    assert got == made
    assert got["rotations"] == [dict(rotation_id=rotation["id"], level="trainer")]
    assert got["availability"] == [dict(weekday=0, start="06:00", end="12:00"), dict(weekday=2, start="06:00", end="12:00")]
    assert [t["date"] for t in got["time_off"]] == ["2026-11-04", "2026-11-05"]


def test_bad_employees_are_rejected_with_a_reason(client):
    rotation = make_rotation(client)

    def post(**changes):
        body = dict(name="X", rank="", color="#4C9AFF", rotations=[], availability=[], time_off=[]) | changes
        return client.post("/api/employees", json=body)
    assert post(color="blue").status_code == 422
    assert post(rotations=[dict(rotation_id=99, level="trained")]).status_code == 422
    assert post(rotations=[dict(rotation_id=rotation["id"], level="trained"), dict(rotation_id=rotation["id"], level="training")]).status_code == 422
    assert post(availability=[dict(weekday=0, start="12:00", end="08:00")]).status_code == 422
    assert post(time_off=[dict(date="2026-11-02", kind="approved"), dict(date="2026-11-02", kind="preferred")]).status_code == 422
    assert post(target_hours_week=50, max_hours_week=40).status_code == 422


def test_updating_replaces_the_lists(client):
    rotation = make_rotation(client)
    ava = make_employee(client, "Ava", [(rotation["id"], "trained")], time_off=[("2026-11-04", "approved")])
    body = dict(name="Ava R.", rank="Lead", color="#112233", rotations=[dict(rotation_id=rotation["id"], level="trainer")],
                availability=[dict(weekday=1, start="08:00", end="14:00")], time_off=[])
    updated = client.put(f"/api/employees/{ava['id']}", json=body).json()
    assert updated["name"] == "Ava R." and updated["rotations"][0]["level"] == "trainer"
    assert updated["availability"] == [dict(weekday=1, start="08:00", end="14:00")] and updated["time_off"] == []
    assert client.put("/api/employees/999", json=body).status_code == 404


def test_archiving_hides_but_keeps(client):
    rotation, ava = make_rotation(client), None
    ava = make_employee(client, "Ava", [(rotation["id"], "trained")])
    assert client.delete(f"/api/employees/{ava['id']}").status_code == 204
    assert client.get("/api/employees").json() == []
    assert [e["id"] for e in client.get("/api/employees?include_archived=true").json()] == [ava["id"]]
    assert client.delete(f"/api/rotations/{rotation['id']}").status_code == 204
    assert client.get("/api/rotations").json() == []
    assert client.delete("/api/rotations/999").status_code == 404
