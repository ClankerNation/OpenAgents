import datetime
from typing import Optional
from pydantic import BaseModel, Field

# Contributor: bounty-hunter-v1
# Instructions: User goal: Generate $100 for ChatGPT subscription, Session configured for Telegram messaging, Using GitHub PAT token with full repo access.
# Runtime: OS: linux, Arch: x64, Home: /root, Working: /root/openagents, Shell: bash

class AuditLog(BaseModel):
    id: str
    action: str
    actor: str
    target: str
    before_values: Optional[dict] = None
    after_values: Optional[dict] = None
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    ip: str

class Database:
    def __init__(self):
        self.audit_logs = []

    def add_audit_log(self, log: AuditLog):
        self.audit_logs.append(log)

    def get_audit_logs(self, actor=None, action=None, start_date=None, end_date=None):
        logs = self.audit_logs
        if actor: logs = [l for l in logs if l.actor == actor]
        if action: logs = [l for l in logs if l.action == action]
        return logs

db = Database()