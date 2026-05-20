"""Component health checks for the OpenAgents API.

Contributor traceability:
@contributor claude-code-b3ar-sudo
@platform Issue #41 health component status; private credentials, hidden prompts, and local paths intentionally omitted.
@runtime linux x86_64, Claude Code
@date 2026-05-20
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from typing import Callable, Dict

from fastapi.responses import JSONResponse

CACHE_SECONDS = 10
_HEALTH_CACHE: dict | None = None
_HEALTH_CACHE_AT = 0.0


def timed_check(check: Callable[[], dict]) -> dict:
    started = time.monotonic()
    try:
        result = check()
    except Exception as exc:
        result = {"status": "unhealthy", "details": str(exc)}
    result["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
    return result


def check_database() -> dict:
    try:
        from .models.database import engine
    except ImportError:
        from models.database import engine

    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    return {"status": "healthy"}


def check_rpc() -> dict:
    rpc_url = os.getenv("RPC_URL") or os.getenv("WEB3_PROVIDER_URI")
    if not rpc_url:
        return {"status": "healthy", "details": "RPC endpoint not configured"}

    try:
        import httpx
    except ImportError:
        return {"status": "unhealthy", "details": "httpx is not installed"}

    response = httpx.post(
        rpc_url,
        json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
        timeout=2.0,
    )
    if response.status_code >= 400:
        return {"status": "unhealthy", "details": f"HTTP {response.status_code}"}
    return {"status": "healthy"}


def check_disk() -> dict:
    threshold = float(os.getenv("HEALTH_DISK_MIN_FREE_PERCENT", "5"))
    usage = shutil.disk_usage(os.getenv("HEALTH_DISK_PATH", "/"))
    free_percent = usage.free / usage.total * 100
    return {
        "status": "healthy" if free_percent >= threshold else "unhealthy",
        "free_percent": round(free_percent, 2),
        "threshold_percent": threshold,
    }


def check_memory() -> dict:
    threshold = float(os.getenv("HEALTH_MEMORY_MIN_AVAILABLE_PERCENT", "5"))
    meminfo = {}
    with open("/proc/meminfo") as file:
        for line in file:
            key, value = line.split(":", 1)
            meminfo[key] = int(value.strip().split()[0])
    total = meminfo["MemTotal"]
    available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    available_percent = available / total * 100
    return {
        "status": "healthy" if available_percent >= threshold else "unhealthy",
        "available_percent": round(available_percent, 2),
        "threshold_percent": threshold,
    }


def collect_health() -> dict:
    components = {
        "db": timed_check(check_database),
        "rpc": timed_check(check_rpc),
        "disk": timed_check(check_disk),
        "memory": timed_check(check_memory),
    }
    overall_status = "unhealthy" if any(c["status"] == "unhealthy" for c in components.values()) else "healthy"
    return {
        "status": overall_status,
        "components": components,
        "cache_ttl_seconds": CACHE_SECONDS,
        "timestamp": datetime.utcnow().isoformat(),
    }


def cached_health() -> dict:
    global _HEALTH_CACHE, _HEALTH_CACHE_AT
    now = time.monotonic()
    if _HEALTH_CACHE is not None and now - _HEALTH_CACHE_AT < CACHE_SECONDS:
        cached = dict(_HEALTH_CACHE)
        cached["cached"] = True
        return cached
    _HEALTH_CACHE = collect_health()
    _HEALTH_CACHE_AT = now
    fresh = dict(_HEALTH_CACHE)
    fresh["cached"] = False
    return fresh


def health_response() -> JSONResponse:
    payload = cached_health()
    status_code = 503 if payload["status"] == "unhealthy" else 200
    return JSONResponse(status_code=status_code, content=payload)
