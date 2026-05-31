from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from api import main


client = TestClient(main.app)


def setup_function():
    main.admin_parameters.clear()
    main.users_cache.clear()
    main.audit_logs.clear()
    main.audit_log_seq = 0


def test_admin_actions_create_audit_records_with_before_after():
    first = client.put(
        "/admin/parameters/maxAgents",
        json={"value": 10},
        headers={"X-Admin-Actor": "alice"},
    )
    assert first.status_code == 200

    second = client.put(
        "/admin/parameters/maxAgents",
        json={"value": 12},
        headers={"X-Admin-Actor": "alice"},
    )
    assert second.status_code == 200

    third = client.put(
        "/admin/users/u-1",
        json={"active": False, "roles": ["moderator"]},
        headers={"X-Admin-Actor": "bob"},
    )
    assert third.status_code == 200

    logs = client.get("/admin/audit-log").json()["records"]
    assert len(logs) == 3

    parameter_update = logs[1]
    assert parameter_update["action"] == "parameter_update"
    assert parameter_update["before"] == 10
    assert parameter_update["after"] == 12
    assert parameter_update["ip"] == "testclient"


def test_admin_audit_log_filters_by_actor_action_and_date_range():
    client.put(
        "/admin/parameters/feeBps",
        json={"value": 200},
        headers={"X-Admin-Actor": "alice"},
    )
    client.put(
        "/admin/users/u-2",
        json={"active": False},
        headers={"X-Admin-Actor": "bob"},
    )

    filtered = client.get("/admin/audit-log?actor=alice&action=parameter_update").json()
    assert filtered["total"] == 1
    assert filtered["records"][0]["target"] == "parameter:feeBps"

    second_ts = datetime.fromisoformat(main.audit_logs[1]["timestamp"].isoformat())
    start_date = (second_ts - timedelta(seconds=1)).isoformat()
    end_date = (second_ts + timedelta(seconds=1)).isoformat()

    by_range = client.get(
        f"/admin/audit-log?start_date={start_date}&end_date={end_date}&action=user_update"
    ).json()
    assert by_range["total"] == 1
    assert by_range["records"][0]["actor"] == "bob"


def test_admin_audit_log_is_immutable():
    client.put(
        "/admin/parameters/maxTasks",
        json={"value": 5},
        headers={"X-Admin-Actor": "alice"},
    )

    patch_resp = client.patch("/admin/audit-log/1", json={"action": "tampered"})
    delete_resp = client.delete("/admin/audit-log/1")

    assert patch_resp.status_code == 405
    assert delete_resp.status_code == 405

    logs = client.get("/admin/audit-log").json()["records"]
    assert len(logs) == 1
    assert logs[0]["action"] == "parameter_update"
