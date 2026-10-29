from tests.api.conftest import MONDAY, make_employee, make_rotation, small_team


def solve(client, days=3, **extra):
    r = client.post("/api/schedules", json=dict(name="Test week", start_date=MONDAY, num_days=days, time_limit=10) | extra)
    assert r.status_code == 201, r.text
    return r.json()


def assigned_ids(detail, slot_id):
    slot = next(s for s in detail["view"]["slots"] if s["id"] == slot_id)
    return {a["employee_id"] for a in slot["assignments"] if a["role"] == "worker"}


def test_solving_staffs_every_slot_and_stores_the_result(client):
    small_team(client)
    detail = solve(client)
    view = detail["view"]
    assert len(view["slots"]) == 6 and all(s["short"] == 0 for s in view["slots"])
    assert view["summary"]["valid"] and view["violations"] == []
    assert detail["schedule"]["solver_status"] in ("OPTIMAL", "FEASIBLE") and detail["locks"] == []

    again = client.get(f"/api/schedules/{detail['schedule']['id']}").json()
    assert again["view"]["slots"] == view["slots"]
    assert [s["id"] for s in client.get("/api/schedules").json()] == [detail["schedule"]["id"]]
    assert client.get("/api/schedules/999").status_code == 404


def test_scheduling_needs_a_workforce(client):
    r = client.post("/api/schedules", json=dict(start_date=MONDAY, num_days=3))
    assert r.status_code == 422 and "at least one rotation" in r.json()["detail"]


def test_candidates_mark_who_is_assigned_eligible_or_blocked(client):
    _, ava, ben, cy, dee = small_team(client)
    detail = solve(client)
    sid = detail["schedule"]["id"]
    rows = {r["employee_id"]: r for r in client.get(f"/api/schedules/{sid}/slots/r1:0:AM/candidates").json()}
    worker_ids = assigned_ids(detail, "r1:0:AM")
    assert len(worker_ids) == 1
    other = ({ava["id"], ben["id"]} - worker_ids).pop()
    assert rows[next(iter(worker_ids))]["status"] == "assigned"
    assert rows[other]["status"] == "eligible" and rows[other]["needs_change"] is True
    assert rows[dee["id"]]["status"] == "blocked" and "isn't trained" in rows[dee["id"]]["reasons"][0]
    assert rows[cy["id"]]["role"] == "trainee"
    assert client.get(f"/api/schedules/{sid}/slots/r9:0:AM/candidates").status_code == 404


def test_pinning_moves_someone_in_and_is_remembered(client):
    _, ava, ben, *_ = small_team(client)
    detail = solve(client)
    sid = detail["schedule"]["id"]
    current = next(iter(assigned_ids(detail, "r1:0:AM")))
    other = ({ava["id"], ben["id"]} - {current}).pop()

    r = client.post(f"/api/schedules/{sid}/overrides", json=dict(pins=[dict(employee_id=other, slot_id="r1:0:AM")]))
    assert r.status_code == 200, r.text
    revised = r.json()
    assert assigned_ids(revised, "r1:0:AM") == {other} and revised["view"]["violations"] == []
    assert any("Add" in c for c in revised["changes"]) and any("Remove" in c for c in revised["changes"])
    assert [(l["kind"], l["employee_id"], l["slot_id"]) for l in revised["locks"]] == [("pin", other, "r1:0:AM")]

    # A second override keeps the first pin in force.
    r = client.post(f"/api/schedules/{sid}/overrides", json=dict(bans=[dict(employee_id=ava["id"], slot_id="r1:1:AM")]))
    assert r.status_code == 200, r.text
    again = r.json()
    assert assigned_ids(again, "r1:0:AM") == {other} and ava["id"] not in assigned_ids(again, "r1:1:AM")
    assert {l["kind"] for l in again["locks"]} == {"pin", "ban"}


def test_the_latest_decision_about_an_assignment_wins(client):
    _, ava, ben, *_ = small_team(client)
    sid = solve(client)["schedule"]["id"]
    pair = dict(employee_id=ava["id"], slot_id="r1:0:AM")
    client.post(f"/api/schedules/{sid}/overrides", json=dict(pins=[pair]))
    r = client.post(f"/api/schedules/{sid}/overrides", json=dict(bans=[pair]))
    assert r.status_code == 200 and ava["id"] not in assigned_ids(r.json(), "r1:0:AM")
    assert [l["kind"] for l in r.json()["locks"]] == ["ban"]


def test_impossible_overrides_are_rejected_and_nothing_changes(client):
    _, ava, _, _, dee = small_team(client)
    detail = solve(client)
    sid = detail["schedule"]["id"]
    r = client.post(f"/api/schedules/{sid}/overrides", json=dict(pins=[dict(employee_id=dee["id"], slot_id="r1:0:AM")]))
    assert r.status_code == 422 and "isn't trained" in r.json()["detail"]
    r = client.post(f"/api/schedules/{sid}/overrides", json=dict(pins=[dict(employee_id=999, slot_id="r1:0:AM")]))
    assert r.status_code == 422
    assert client.get(f"/api/schedules/{sid}").json()["view"]["slots"] == detail["view"]["slots"]
    assert client.get(f"/api/schedules/{sid}").json()["locks"] == []


def test_removing_a_lock_forgets_the_decision_but_not_the_assignments(client):
    _, ava, *_ = small_team(client)
    sid = solve(client)["schedule"]["id"]
    locked = client.post(f"/api/schedules/{sid}/overrides", json=dict(pins=[dict(employee_id=ava["id"], slot_id="r1:0:AM")])).json()
    lock_id = locked["locks"][0]["id"]
    assert client.delete(f"/api/schedules/{sid}/locks/{lock_id}").status_code == 204
    after = client.get(f"/api/schedules/{sid}").json()
    assert after["locks"] == [] and after["view"]["slots"] == locked["view"]["slots"]
    assert client.delete(f"/api/schedules/{sid}/locks/{lock_id}").status_code == 404


def test_explanations_cover_assigned_blocked_and_possible(client):
    _, ava, ben, _, dee = small_team(client)
    detail = solve(client)
    sid = detail["schedule"]["id"]
    current = next(iter(assigned_ids(detail, "r1:0:AM")))
    other = ({ava["id"], ben["id"]} - {current}).pop()

    def ask(employee_id):
        r = client.get(f"/api/schedules/{sid}/explain", params=dict(employee_id=employee_id, slot_id="r1:0:AM"))
        assert r.status_code == 200, r.text
        return r.json()
    assert ask(current)["status"] == "assigned"
    assert ask(dee["id"])["status"] == "blocked" and "isn't trained" in ask(dee["id"])["summary"]
    possible = ask(other)
    assert possible["status"] in ("tradeoff", "improvement", "neutral") and possible["changes"] and possible["cost_delta"] is not None
    assert client.get(f"/api/schedules/{sid}/explain", params=dict(employee_id=999, slot_id="r1:0:AM")).status_code == 404


def test_explanations_respect_existing_bans(client):
    _, ava, ben, *_ = small_team(client)
    detail = solve(client)
    sid = detail["schedule"]["id"]
    victim = next(iter(assigned_ids(detail, "r1:0:AM")))
    client.post(f"/api/schedules/{sid}/overrides", json=dict(bans=[dict(employee_id=victim, slot_id="r1:0:AM")]))
    x = client.get(f"/api/schedules/{sid}/explain", params=dict(employee_id=victim, slot_id="r1:0:AM")).json()
    assert x["status"] == "blocked" and "manually kept off" in x["summary"]


def test_a_schedule_is_flagged_when_the_workforce_changes_underneath_it(client):
    small_team(client)
    detail = solve(client)
    sid = detail["schedule"]["id"]
    someone = next(iter(assigned_ids(detail, "r1:0:AM")))
    client.delete(f"/api/employees/{someone}")                       # archive a person who has shifts
    stale = client.get(f"/api/schedules/{sid}").json()["view"]
    assert stale["summary"]["valid"] is False and any(v["rule"] == "unknown_reference" for v in stale["violations"])


def test_the_audit_log_records_what_happened(client):
    small_team(client)
    sid = solve(client)["schedule"]["id"]
    client.post(f"/api/schedules/{sid}/overrides", json=dict(bans=[dict(employee_id=1, slot_id="r1:2:PM")]))
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert {"rotation.created", "employee.created", "schedule.created", "schedule.revised"} <= set(actions)
    revised = next(a for a in client.get("/api/audit").json() if a["action"] == "schedule.revised")
    assert revised["details"]["bans"] == ["e1:r1:2:PM"]
