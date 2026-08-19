"""
OpenAgents API Entry Point
@contributor ARO-Agentic
@platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
@env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
@timestamp 2026-08-19T02:50:00Z
"""
from fastapi import FastAPI
from datetime import datetime
from .routes import agents, tasks
from .models.database import init_db

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

app.include_router(agents.router)
app.include_router(tasks.router)

@app.on_event("startup")
async def startup_event():
    init_db()

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }
