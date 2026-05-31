import asyncio
import hashlib
import hmac
import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-secret")

from api.models import database as db_models
from api.middleware.auth import get_current_user
from api.models.database import Task, User, WebhookDelivery, WebhookSubscription
from api.routes.tasks import router as tasks_router
from api.routes.webhooks import router as webhooks_router
from api.services import webhooks


def _make_session_local():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_models.Base.metadata.create_all(bind=engine)
    return session_local, engine, db_path


def test_task_routes_emit_webhook_events(monkeypatch):
    session_local, engine, db_path = _make_session_local()
    fired_events = []

    async def fake_notify(db, task, event):
        fired_events.append(event)
        return 1

    monkeypatch.setattr("api.routes.tasks.notify_task_state_change", fake_notify)

    app = FastAPI()
    app.include_router(tasks_router)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    async def override_get_current_user():
        return {"id": 1, "address": "0x1", "roles": []}

    app.dependency_overrides[db_models.get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)

    db = session_local()
    db.add(User(id=1, address="0x1111111111111111111111111111111111111111", username="u1"))
    db.commit()
    db.close()

    create_resp = client.post(
        "/tasks/",
        json={
            "title": "test-task",
            "description": "desc",
            "reward_amount": 1.0,
        },
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["id"]

    for status in ("assigned", "completed", "disputed"):
        update_resp = client.patch(f"/tasks/{task_id}/status", json={"status": status})
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == status

    assert fired_events == ["created", "assigned", "completed", "disputed"]

    engine.dispose()
    os.remove(db_path)


def test_webhook_retries_hmac_and_history(monkeypatch):
    session_local, engine, db_path = _make_session_local()
    db = session_local()
    user = User(id=1, address="0x2222222222222222222222222222222222222222", username="u2")
    db.add(user)
    db.flush()
    task = Task(
        title="notify-task",
        description="desc",
        reward_amount=2.0,
        creator_id=user.id,
        status="completed",
    )
    db.add(task)
    db.flush()
    subscription = WebhookSubscription(
        creator_id=user.id,
        target_url="https://example.com/hook",
        secret="supersecret",
        events=["completed"],
        enabled=True,
    )
    db.add(subscription)
    db.commit()

    calls = []

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = f"status={status_code}"

    class FakeAsyncClient:
        def __init__(self):
            self._statuses = [500, 500, 500, 500, 200]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, content, headers, timeout):
            calls.append({"url": url, "content": content, "headers": headers, "timeout": timeout})
            return FakeResponse(self._statuses.pop(0))

    monkeypatch.setattr(webhooks.httpx, "AsyncClient", FakeAsyncClient)

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    original_deliver = webhooks._deliver_with_retries

    async def wrapped_deliver(*args, **kwargs):
        kwargs["sleep"] = fake_sleep
        return await original_deliver(*args, **kwargs)

    monkeypatch.setattr(webhooks, "_deliver_with_retries", wrapped_deliver)

    delivered = asyncio.run(webhooks.notify_task_state_change(db, task, "completed"))
    assert delivered == 1

    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == subscription.id)
        .order_by(WebhookDelivery.attempt.asc())
        .all()
    )
    assert len(deliveries) == 5
    assert [d.attempt for d in deliveries] == [1, 2, 3, 4, 5]
    assert deliveries[-1].success is True
    assert sleeps == [1, 2, 4, 8]

    assert len(calls) == 5
    first_call = calls[0]
    expected_sig = "sha256=" + hmac.new(
        b"supersecret", first_call["content"], hashlib.sha256
    ).hexdigest()
    assert first_call["headers"]["X-OpenAgents-Signature"] == expected_sig

    db.close()
    engine.dispose()
    os.remove(db_path)


def test_webhook_crud_endpoints():
    session_local, engine, db_path = _make_session_local()

    app = FastAPI()
    app.include_router(webhooks_router)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    async def override_get_current_user():
        return {"id": 1, "address": "0x1", "roles": []}

    app.dependency_overrides[db_models.get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)

    db = session_local()
    db.add(User(id=1, address="0x3333333333333333333333333333333333333333", username="u3"))
    db.commit()
    db.close()

    create_resp = client.post(
        "/webhooks/",
        json={
            "target_url": "https://example.com/webhook",
            "secret": "secret-12345",
            "events": ["created", "completed"],
            "enabled": True,
        },
    )
    assert create_resp.status_code == 200
    webhook_id = create_resp.json()["id"]

    list_resp = client.get("/webhooks/")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    update_resp = client.patch(
        f"/webhooks/{webhook_id}",
        json={"events": ["assigned", "disputed"], "enabled": False},
    )
    assert update_resp.status_code == 200
    assert sorted(update_resp.json()["events"]) == ["assigned", "disputed"]
    assert update_resp.json()["enabled"] is False

    delete_resp = client.delete(f"/webhooks/{webhook_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    engine.dispose()
    os.remove(db_path)
