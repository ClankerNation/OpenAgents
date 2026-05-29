import asyncio
import json
import os

os.environ.setdefault("JWT_SECRET", "test-secret")

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models.database import Base, Task, User, WebhookDelivery, WebhookSubscription
from api.routes.tasks import TaskCreate, TaskStatusUpdate, create_task, update_task_status
from api.routes.webhooks import (
    WebhookCreate,
    create_webhook,
    deliver_task_webhooks,
    sign_payload,
)


class RecordingClient:
    def __init__(self, failures=0):
        self.failures = failures
        self.posts = []

    async def post(self, url, content, headers):
        self.posts.append({"url": url, "content": content, "headers": headers})
        request = httpx.Request("POST", url)
        if len(self.posts) <= self.failures:
            return httpx.Response(500, request=request)
        return httpx.Response(200, request=request)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_user(db):
    user = User(address="0x1111111111111111111111111111111111111111", username="creator")
    db.add(user)
    db.commit()
    return user


def test_sign_payload_is_hmac_sha256_and_stable():
    payload = {"task": {"id": 1}, "event": "completed"}
    signature, body = sign_payload("secret", payload)

    assert signature.startswith("sha256=")
    assert json.loads(body) == payload
    assert signature == sign_payload("secret", payload)[0]


def test_create_webhook_stores_subscription_secret_and_events():
    db = make_session()
    user = seed_user(db)

    result = asyncio.run(create_webhook(
        WebhookCreate(url="https://example.com/hook", events=["created"], secret="1234567890abcdef"),
        user={"id": user.id, "address": user.address},
        db=db,
    ))

    assert result["events"] == ["created"]
    assert result["secret"] == "1234567890abcdef"
    assert db.query(WebhookSubscription).count() == 1


def test_delivery_retries_and_records_history():
    db = make_session()
    user = seed_user(db)
    task = Task(title="task", reward_amount=1.0, status="completed", creator_id=user.id)
    subscription = WebhookSubscription(
        owner_id=user.id,
        url="https://example.com/hook",
        secret="1234567890abcdef",
        events=["completed"],
        active=1,
    )
    db.add_all([task, subscription])
    db.commit()
    client = RecordingClient(failures=2)

    asyncio.run(deliver_task_webhooks(task, "completed", db, client=client))

    delivery = db.query(WebhookDelivery).one()
    assert len(client.posts) == 3
    assert delivery.status == "delivered"
    assert delivery.attempts == 3
    assert client.posts[-1]["headers"]["X-OpenAgents-Event"] == "completed"
    assert client.posts[-1]["headers"]["X-OpenAgents-Signature"].startswith("sha256=")


def test_task_create_and_completed_status_fire_webhooks():
    db = make_session()
    user = seed_user(db)
    db.add(WebhookSubscription(
        owner_id=user.id,
        url="https://example.com/hook",
        secret="1234567890abcdef",
        events=["created", "completed"],
        active=1,
    ))
    db.commit()

    created = asyncio.run(create_task(
        TaskCreate(title="task", description="desc", reward_amount=1.0),
        user={"id": user.id, "address": user.address},
        db=db,
    ))
    asyncio.run(update_task_status(
        created["id"],
        TaskStatusUpdate(status="completed"),
        user={"id": user.id, "address": user.address},
        db=db,
    ))

    events = [delivery.event for delivery in db.query(WebhookDelivery).order_by(WebhookDelivery.id).all()]
    assert events == ["created", "completed"]
