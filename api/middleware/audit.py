"""Audit logging for admin actions."""
import time, json
from pathlib import Path

AUDIT_LOG = Path("logs/audit.jsonl")

def log_admin_action(admin_id: str, action: str, target: str, details: dict = None):
    """Log admin action to JSONL audit file."""
    entry = {
        "timestamp": int(time.time()),
        "admin_id": admin_id,
        "action": action,
        "target": target,
        "details": details or {},
    }
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def get_audit_logs(limit: int = 100):
    """Read recent audit log entries."""
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text().strip().split("\n")
    return [json.loads(line) for line in lines[-limit:]]
