"""
Tests for UUID migration — validates UUID generation and API exposure.

@contributor tufstraka
@platform OpenClaw Gateway (amazon-bedrock/global.anthropic.claude-opus-4-5-20251101-v1:0)
@runtime Linux 6.17.0-1013-aws (arm64), /home/ubuntu/.openclaw/workspace
@date 2026-05-27T10:21:00Z
"""

import re
import uuid
import pytest
from api.models.database import User, Agent, Task, Payment, generate_uuid


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE
)


class TestUUIDGeneration:
    """Test that models generate valid UUID v4 identifiers."""

    def test_generate_uuid_returns_valid_v4(self):
        """generate_uuid() should return a valid UUID v4 string."""
        result = generate_uuid()
        assert UUID_PATTERN.match(result), f"Invalid UUID v4: {result}"

    def test_generate_uuid_is_random(self):
        """Each call to generate_uuid() should return a unique value."""
        uuids = [generate_uuid() for _ in range(100)]
        assert len(set(uuids)) == 100, "UUIDs are not unique"

    def test_user_model_has_uuid_column(self):
        """User model should have a uuid column."""
        user = User(address="0x1234567890123456789012345678901234567890")
        assert hasattr(user, "uuid")
        # Default should be set
        assert user.uuid is not None or User.uuid.default is not None

    def test_agent_model_has_uuid_column(self):
        """Agent model should have a uuid column."""
        agent = Agent(name="TestAgent", owner_id=1)
        assert hasattr(agent, "uuid")

    def test_task_model_has_uuid_column(self):
        """Task model should have a uuid column."""
        task = Task(title="Test", reward_amount=100.0, creator_id=1)
        assert hasattr(task, "uuid")

    def test_payment_model_has_uuid_column(self):
        """Payment model should have a uuid column."""
        payment = Payment(task_id=1, from_address="0x123", amount=50.0)
        assert hasattr(payment, "uuid")


class TestNoIntegerIDLeak:
    """Test that integer IDs are not exposed in API responses."""

    def test_agent_response_uses_uuid(self):
        """Agent API responses should use UUID, not integer ID."""
        from api.routes.agents import agent_to_response
        
        # Create a mock agent with both id and uuid
        class MockAgent:
            id = 42
            uuid = "550e8400-e29b-41d4-a716-446655440000"
            name = "TestAgent"
            description = "A test agent"
            model_type = "gpt-4"
            config = {}
            created_at = None
        
        response = agent_to_response(MockAgent())
        
        # Response should have UUID as "id"
        assert response["id"] == "550e8400-e29b-41d4-a716-446655440000"
        # Integer ID should not be present
        assert 42 not in response.values()

    def test_task_response_uses_uuid(self):
        """Task API responses should use UUID, not integer ID."""
        from api.routes.tasks import task_to_response
        
        class MockTask:
            id = 99
            uuid = "660e8400-e29b-41d4-a716-446655440001"
            title = "Test Task"
            description = "A test task"
            reward_amount = 100.0
            status = "open"
            created_at = None
            updated_at = None
            deadline = None
        
        response = task_to_response(MockTask())
        
        assert response["id"] == "660e8400-e29b-41d4-a716-446655440001"
        assert 99 not in response.values()

    def test_payment_response_uses_uuid(self):
        """Payment API responses should use UUID, not integer ID."""
        from api.routes.payments import payment_to_response
        
        class MockPayment:
            id = 123
            uuid = "770e8400-e29b-41d4-a716-446655440002"
            amount = 50.0
            status = "escrowed"
            token_address = "0x0000000000000000000000000000000000000000"
            created_at = None
            claimed_at = None
        
        response = payment_to_response(MockPayment())
        
        assert response["id"] == "770e8400-e29b-41d4-a716-446655440002"
        assert 123 not in response.values()


class TestUUIDValidation:
    """Test that UUIDs are properly validated."""

    def test_uuid_v4_format(self):
        """Generated UUIDs should be version 4 (random)."""
        for _ in range(10):
            u = generate_uuid()
            # Parse and check version
            parsed = uuid.UUID(u)
            assert parsed.version == 4, f"UUID is not v4: {u}"

    def test_uuid_uniqueness_constraint(self):
        """UUID columns should have unique constraint."""
        # Check column properties
        assert User.uuid.unique is True or User.uuid.property.columns[0].unique
        assert Agent.uuid.unique is True or Agent.uuid.property.columns[0].unique
        assert Task.uuid.unique is True or Task.uuid.property.columns[0].unique
        assert Payment.uuid.unique is True or Payment.uuid.property.columns[0].unique
