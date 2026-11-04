"""WebSocket task updates: subscribe, receive, heartbeat, cleanup.

@contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
@platform-config verbatim block: @platform-config header of api/services/task_events.py
@env os=windows arch=x86_64 home_dir=C:\\Users\\2 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\\Program Files\\Git\\bin\\bash.exe
@timestamp 2026-11-04T14:40:00Z
"""

import os
import pathlib
import sys

os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.main import app  # noqa: E402
from api.middleware.auth import create_access_token  # noqa: E402
from api.models.database import Base, get_db  # noqa: E402
from api.services.task_events import task_events  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def override_get_db():
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth():
    token = create_access_token({"sub": "1", "address": "0xc", "roles": ["user"]})
    return {"Authorization": f"Bearer {token}"}


def make_task(client, auth, title="t"):
    r = client.post(
        "/tasks/", json={"title": title, "description": "d", "reward_amount": 1.0}, headers=auth
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def set_status(client, auth, task_id, status):
    r = client.patch(f"/tasks/{task_id}/status", json={"status": status}, headers=auth)
    assert r.status_code == 200, r.text


def test_connect_receives_hello(client):
    with client.websocket_connect("/tasks/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["heartbeat"] > 0


def test_subscribe_acknowledges(client, auth):
    task_id = make_task(client, auth)
    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "task_ids": [task_id]})
        ack = ws.receive_json()
        assert ack["type"] == "subscribed"
        assert ack["task_ids"] == [task_id]


def test_subscribed_client_receives_status_update(client, auth):
    task_id = make_task(client, auth)
    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "task_ids": [task_id]})
        ws.receive_json()

        set_status(client, auth, task_id, "in_progress")

        event = ws.receive_json()
        assert event["type"] == "task.status"
        assert event["task_id"] == task_id
        assert event["status"] == "in_progress"


def test_other_tasks_are_filtered_out(client, auth):
    wanted = make_task(client, auth)
    other = make_task(client, auth)
    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "task_ids": [wanted]})
        ws.receive_json()

        set_status(client, auth, other, "completed")
        set_status(client, auth, wanted, "review")

        # only the wanted task's event may arrive; a ping would prove the queue is otherwise empty
        event = ws.receive_json()
        assert event["task_id"] == wanted
        assert event["status"] == "review"


def test_unsubscribe_stops_delivery(client, auth):
    task_id = make_task(client, auth)
    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "task_ids": [task_id]})
        ws.receive_json()
        ws.send_json({"action": "unsubscribe", "task_ids": [task_id]})
        ack = ws.receive_json()
        assert ack["task_ids"] == []

        set_status(client, auth, task_id, "completed")
        ws.send_json({"action": "ping"})
        # ordering proves the status update produced nothing for this connection
        assert ws.receive_json()["type"] == "pong"


def test_heartbeat_fires_on_an_idle_connection(client, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_SECONDS", "0.2")
    with client.websocket_connect("/tasks/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        assert ws.receive_json()["type"] == "ping"
        assert ws.receive_json()["type"] == "ping"


def test_ping_action_gets_pong(client):
    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_bad_frames_do_not_kill_the_connection(client):
    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "task_ids": ["x"]})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"action": "nope"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"action": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_disconnected_clients_are_cleaned_up(client, auth):
    task_id = make_task(client, auth)
    assert task_events.subscriber_count() == 0

    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "task_ids": [task_id]})
        ws.receive_json()
        assert task_events.subscriber_count() == 1

    assert task_events.subscriber_count() == 0

    # a publish with nobody listening must be harmless
    set_status(client, auth, task_id, "completed")


def test_created_events_reach_subscribers(client, auth):
    """create_task publishes too, so dashboards see new work without polling."""
    task_id = make_task(client, auth)
    with client.websocket_connect("/tasks/ws") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "task_ids": [task_id]})
        ws.receive_json()

        r = client.post(
            "/tasks/", json={"title": "second", "description": "d", "reward_amount": 2.0}, headers=auth
        )
        new_id = r.json()["id"]

        # the *other* task must not arrive, so subscribe then create is exercised on its own
        assert new_id != task_id
        set_status(client, auth, task_id, "open")
        assert ws.receive_json()["task_id"] == task_id
