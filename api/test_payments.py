import os
os.environ["DATABASE_URL"] = "sqlite:///./test_payments.db"
os.environ["JWT_SECRET"] = "test-secret-key-123"

import unittest
from datetime import datetime, timedelta
import jwt
from fastapi.testclient import TestClient

from api.models.database import SessionLocal, engine, Base, User, Task, Payment
import api.main

class TestPayments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Recreate tables in test database
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(api.main.app)

    def setUp(self):
        # Clear tables
        db = SessionLocal()
        db.query(Payment).delete()
        db.query(Task).delete()
        db.query(User).delete()
        db.commit()
        db.close()

    def test_escrow_deposit_and_process_expired(self):
        db = SessionLocal()
        
        # 1. Create a user
        user = User(address="0x1111111111111111111111111111111111111111", username="testuser")
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # 2. Create a task owned by the user
        task = Task(
            title="Test Task",
            description="Testing payments",
            reward_amount=100.0,
            status="open",
            creator_id=user.id
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # Save necessary variables locally before closing session
        user_id = user.id
        user_address = user.address
        task_id = task.id
        
        db.close()

        # Generate JWT token for the user
        payload = {
            "sub": str(user_id),
            "address": user_address,
            "roles": ["user"],
            "type": "access"
        }
        token = jwt.encode(payload, "test-secret-key-123", algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create a fresh escrow deposit (release_time = now + 1 day)
        # So expired_at = now + 31 days. It should not be expired yet.
        now = datetime.utcnow()
        release_time_fresh = now + timedelta(days=1)
        
        response = self.client.post(
            "/payments/escrow/deposit",
            json={
                "task_id": task_id,
                "amount": 50.0,
                "release_time": release_time_fresh.isoformat()
            },
            headers=headers
        )
        self.assertEqual(response.status_code, 200)
        fresh_payment_id = response.json()["payment_id"]

        # 4. Create an expired escrow deposit (release_time = now - 32 days)
        # So expired_at = now - 2 days. It should be expired.
        release_time_expired = now - timedelta(days=32)
        response_expired = self.client.post(
            "/payments/escrow/deposit",
            json={
                "task_id": task_id,
                "amount": 75.0,
                "release_time": release_time_expired.isoformat()
            },
            headers=headers
        )
        self.assertEqual(response_expired.status_code, 200)
        expired_payment_id = response_expired.json()["payment_id"]

        # Verify initial database state
        db = SessionLocal()
        fresh_payment = db.query(Payment).filter(Payment.id == fresh_payment_id).first()
        expired_payment = db.query(Payment).filter(Payment.id == expired_payment_id).first()
        
        # Verify expired_at calculation on the model
        self.assertIsNotNone(fresh_payment.expired_at)
        self.assertIsNotNone(expired_payment.expired_at)
        self.assertTrue(fresh_payment.expired_at > now)
        self.assertTrue(expired_payment.expired_at < now)
        
        db.close()

        # 5. Process expired payments
        process_res = self.client.post("/payments/process-expired")
        self.assertEqual(process_res.status_code, 200)
        
        res_json = process_res.json()
        self.assertEqual(res_json["processed_count"], 1)
        self.assertEqual(res_json["refunded_payment_ids"], [expired_payment_id])

        # 6. Verify final database state
        db = SessionLocal()
        fresh_payment_after = db.query(Payment).filter(Payment.id == fresh_payment_id).first()
        expired_payment_after = db.query(Payment).filter(Payment.id == expired_payment_id).first()
        
        self.assertEqual(fresh_payment_after.status, "escrowed")
        self.assertEqual(expired_payment_after.status, "refunded")
        self.assertIsNotNone(expired_payment_after.claimed_at)
        db.close()
