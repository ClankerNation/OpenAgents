"""Audit logging utilities for admin actions."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

_audit_logs: List[Dict] = []
_MAX_LOGS = 1000


def log_action(
    actor: Optional[str],
    action: str,
    target: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "target": target,
        "ip": ip,
        "user_agent": user_agent,
        "metadata": metadata or {},
    }
    _audit_logs.append(entry)
    if len(_audit_logs) > _MAX_LOGS:
        _audit_logs.pop(0)
    return entry


def get_audit_logs(limit: int = 100) -> List[Dict]:
    return list(reversed(_audit_logs[-limit:]))


def clear_audit_logs() -> None:
    _audit_logs.clear()
