"""
Tests for UUID migration.

@contributor tufstraka
@platform OpenClaw Gateway (amazon-bedrock/global.anthropic.claude-opus-4-5-20251101-v1:0)
@runtime Linux 6.17.0-1013-aws (arm64), /home/ubuntu/.openclaw/workspace
@date 2026-05-27T10:30:00Z
"""

import re
import uuid
import pytest
from api.models.database import User, Agent, Task, Payment, generate_uuid


UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE
)


def test_generate_uuid_returns_valid_v4():
    result = generate_uuid()
    assert UUID_V4_PATTERN.match(result), f"Invalid UUID v4: {result}"


def test_generate_uuid_is_unique():
    uuids = [generate_uuid() for _ in range(100)]
    assert len(set(uuids)) == 100


def test_user_has_uuid_column():
    assert hasattr(User, "uuid")


def test_agent_has_uuid_column():
    assert hasattr(Agent, "uuid")


def test_task_has_uuid_column():
    assert hasattr(Task, "uuid")


def test_payment_has_uuid_column():
    assert hasattr(Payment, "uuid")


def test_uuid_is_version_4():
    for _ in range(10):
        u = generate_uuid()
        parsed = uuid.UUID(u)
        assert parsed.version == 4
