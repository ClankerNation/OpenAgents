import time

from fastapi.testclient import TestClient

from api.main import admin_settings, admin_users, app, audit_logs


client = TestClient(app)


def setup_function():
    admin_settings.clear()
    admin_users.clear()
    audit_logs.clear()


def test_admin_write_actions_create_audit_logs():
    settings_resp = client.put(
        "/admin/settings/max_agents",
        json={"value": 25},
        headers={"X-Admin-Actor": "alice"},
    )
    assert settings_resp.status_code == 200

    role_resp = client.put(
        "/admin/users/user-1/role",
        json={"role": "moderator"},
        headers={"X-Admin-Actor": "alice"},
    )
    assert role_resp.status_code == 200

    logs_resp = client.get("/admin/audit-log")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert len(logs) == 2

    assert logs[0]["action"] == "settings.update"
    assert logs[0]["actor"] == "alice"
    assert logs[0]["target"] == "settings:max_agents"
    assert logs[0]["before"] is None
    assert logs[0]["after"] == 25
    assert logs[0]["ip"]

    assert logs[1]["action"] == "user.role.update"
    assert logs[1]["before"] is None
    assert logs[1]["after"] == {"user_id": "user-1", "role": "moderator"}


def test_audit_log_supports_actor_action_and_date_filters():
    client.put(
        "/admin/settings/feature_flag",
        json={"value": True},
        headers={"X-Admin-Actor": "alice"},
    )
    time.sleep(0.01)
    client.put(
        "/admin/users/user-2/role",
        json={"role": "admin"},
        headers={"X-Admin-Actor": "bob"},
    )

    all_logs = client.get("/admin/audit-log").json()
    first_ts = all_logs[0]["timestamp"]

    by_actor = client.get("/admin/audit-log", params={"actor": "alice"}).json()
    assert len(by_actor) == 1
    assert by_actor[0]["actor"] == "alice"

    by_action = client.get(
        "/admin/audit-log", params={"action": "user.role.update"}
    ).json()
    assert len(by_action) == 1
    assert by_action[0]["action"] == "user.role.update"

    by_date = client.get(
        "/admin/audit-log",
        params={"start_date": first_ts, "end_date": first_ts},
    ).json()
    assert len(by_date) == 1
    assert by_date[0]["timestamp"] == first_ts


def test_audit_log_records_are_immutable_via_api():
    client.put(
        "/admin/settings/rate_limit",
        json={"value": 100},
        headers={"X-Admin-Actor": "alice"},
    )

    put_resp = client.put("/admin/audit-log", json={"actor": "mallory"})
    delete_resp = client.delete("/admin/audit-log")

    assert put_resp.status_code == 405
    assert delete_resp.status_code == 405
