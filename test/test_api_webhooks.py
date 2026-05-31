import os
import hashlib
import hmac
import unittest
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models.database import Base, Task, WebhookDelivery, WebhookSubscription
from api.routes.tasks import TaskCreate, TaskStatusUpdate, create_task, update_task_status
from api.services import webhooks


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class FakeAsyncClient:
    posts = []
    responses = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, content=None, json=None, headers=None):
        self.posts.append({"url": url, "content": content, "json": json, "headers": headers})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse()


class WebhookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        FakeAsyncClient.posts = []
        FakeAsyncClient.responses = []

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def add_subscription(self, event_types=None):
        subscription = WebhookSubscription(
            owner_id=1,
            target_url="https://example.com/webhook",
            secret="shared-secret",
            event_types=event_types or ["created", "assigned", "completed", "disputed"],
            active=1,
        )
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    @patch("api.services.webhooks.asyncio.sleep")
    @patch("api.services.webhooks.httpx.AsyncClient", FakeAsyncClient)
    async def test_create_task_fires_created_and_assigned_webhooks(self, sleep_mock):
        self.add_subscription()

        result = await create_task(
            TaskCreate(
                title="Build it",
                description="Webhook task",
                reward_amount=10,
                agent_id=7,
            ),
            user={"id": 1, "address": "0xabc"},
            db=self.db,
        )

        self.assertEqual(result["status"], "assigned")
        deliveries = self.db.query(WebhookDelivery).order_by(WebhookDelivery.id).all()
        self.assertEqual([d.event_type for d in deliveries], ["created", "assigned"])
        self.assertEqual(len(FakeAsyncClient.posts), 2)
        for post in FakeAsyncClient.posts:
            expected = hmac.new(
                b"shared-secret",
                post["content"].encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            self.assertEqual(post["headers"]["X-OpenAgents-Signature"], f"sha256={expected}")

    @patch("api.services.webhooks.asyncio.sleep")
    @patch("api.services.webhooks.httpx.AsyncClient", FakeAsyncClient)
    async def test_completed_and_disputed_status_changes_fire_webhooks(self, sleep_mock):
        self.add_subscription()
        task = Task(title="Review", description="", reward_amount=1, creator_id=1, status="open")
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        await update_task_status(
            task.id,
            TaskStatusUpdate(status="completed"),
            user={"id": 1, "address": "0xabc"},
            db=self.db,
        )
        await update_task_status(
            task.id,
            TaskStatusUpdate(status="disputed"),
            user={"id": 1, "address": "0xabc"},
            db=self.db,
        )

        deliveries = self.db.query(WebhookDelivery).order_by(WebhookDelivery.id).all()
        self.assertEqual([d.event_type for d in deliveries], ["completed", "disputed"])

    @patch("api.services.webhooks.asyncio.sleep")
    @patch("api.services.webhooks.httpx.AsyncClient", FakeAsyncClient)
    async def test_delivery_retries_five_times_and_records_history(self, sleep_mock):
        self.add_subscription(["completed"])
        FakeAsyncClient.responses = [
            FakeResponse(500, "bad"),
            FakeResponse(500, "bad"),
            FakeResponse(500, "bad"),
            FakeResponse(500, "bad"),
            FakeResponse(204, ""),
        ]
        task = Task(title="Retry", description="", reward_amount=1, creator_id=1, status="completed")
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        await webhooks.fire_task_webhooks(self.db, task, "completed")

        delivery = self.db.query(WebhookDelivery).one()
        self.assertEqual(delivery.status, "delivered")
        self.assertEqual(delivery.attempts, 5)
        self.assertEqual(delivery.response_status, 204)
        self.assertEqual(len(FakeAsyncClient.posts), 5)
        self.assertEqual(sleep_mock.await_count, 4)


if __name__ == "__main__":
    unittest.main()
