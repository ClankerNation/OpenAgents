from fastapi import FastAPI, Request, Depends, HTTPException
from api.models.database import db, AuditLog
import uuid

app = FastAPI()

@app.get("/admin/audit-log")
def get_audit_logs(actor: str = None, action: str = None):
    return db.get_audit_logs(actor=actor, action=action)

@app.post("/admin/action")
def log_admin_action(request: Request, action: str, target: str, before: dict = None, after: dict = None):
    # Simplified admin check
    actor = request.headers.get("X-Admin-User", "unknown")
    log = AuditLog(
        id=str(uuid.uuid4()),
        action=action,
        actor=actor,
        target=target,
        before_values=before,
        after_values=after,
        ip=request.client.host
    )
    db.add_audit_log(log)
    return {"status": "logged"}