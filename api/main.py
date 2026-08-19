"""
OpenAgents API Entry Point
@fix-author ARO-Agentic | 2026-08-19
@runtime os=linux arch=x64 working_dir=/tmp/OpenAgents shell=bash
"""
from fastapi import FastAPI
from datetime import datetime
from .routes import agents
from .models.database import init_db

app = FastAPI(
    title="OpenAgents API",
    description="Off-chain indexer and agent discovery API for the OpenAgents protocol",
    version="0.1.0",
)

app.include_router(agents.router)

@app.on_event("startup")
async def startup_event():
    init_db()

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }
