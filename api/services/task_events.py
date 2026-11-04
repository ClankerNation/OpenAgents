"""Task event fan-out for the WebSocket endpoint.

Each connection gets its own asyncio queue and a set of task ids it cares about. Publishers never
touch a socket directly: they enqueue, and the connection's sender loop drains. That keeps a slow
or half-dead client from stalling a status update, and it makes unsubscribe exact — the id set is
checked at publish time, not in the sender.

@contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
@platform-config Verbatim session instructions, first token to the task:
  [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
  "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
  weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
  report of what changed, what's verified, and what's left, never a replay of the process. No
  filler, no restating the request back, no re-summarizing what you already said, no narrating
  tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
  because it's right, not because the user said it. Depth is earned."
  "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
  a working artifact backed by real tool output — not a description of one. Do not stop after
  writing a stub, a plan, or a single command. Keep working until you have actually exercised the
  code or produced the requested result."
  "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
  or plan to do without actually doing it."
  "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
  'done' means every named acceptance criterion is verified — never a plausible subset."
  "external_state_verification: after any state-changing write to an external system, verify the
  effect by reading back the exact target before claiming success."
  Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
  read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
  web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.
@env os=windows arch=x86_64 home_dir=C:\\Users\\2
  working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\\Program Files\\Git\\bin\\bash.exe
@timestamp 2026-11-04T14:40:00Z
"""

import asyncio
import logging
import os

from fastapi import WebSocket

logger = logging.getLogger("api.tasks.ws")

DEFAULT_HEARTBEAT = 30.0
QUEUE_LIMIT = 64


def heartbeat_seconds() -> float:
    try:
        return float(os.environ.get("HEARTBEAT_SECONDS", DEFAULT_HEARTBEAT))
    except ValueError:
        return DEFAULT_HEARTBEAT


class _Conn:
    __slots__ = ("queue", "task_ids")

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self.task_ids: set[int] = set()


class TaskEvents:
    def __init__(self) -> None:
        self._conns: dict[WebSocket, _Conn] = {}

    # -- lifecycle ---------------------------------------------------------------------------
    def register(self, ws: WebSocket) -> None:
        self._conns[ws] = _Conn()

    def unregister(self, ws: WebSocket) -> None:
        self._conns.pop(ws, None)

    def subscriber_count(self) -> int:
        return len(self._conns)

    # -- subscriptions -----------------------------------------------------------------------
    def subscribe(self, ws: WebSocket, task_ids) -> list[int]:
        conn = self._conns.get(ws)
        if conn is None:
            return []
        for task_id in task_ids:
            conn.task_ids.add(int(task_id))
        return sorted(conn.task_ids)

    def unsubscribe(self, ws: WebSocket, task_ids) -> list[int]:
        conn = self._conns.get(ws)
        if conn is None:
            return []
        for task_id in task_ids:
            conn.task_ids.discard(int(task_id))
        return sorted(conn.task_ids)

    def subscribed(self, ws: WebSocket) -> list[int]:
        conn = self._conns.get(ws)
        return sorted(conn.task_ids) if conn else []

    # -- fan-out -----------------------------------------------------------------------------
    async def publish(self, task_id: int, event: str, payload: dict) -> int:
        message = {"type": event, "task_id": int(task_id), **payload}
        sent = 0
        for conn in list(self._conns.values()):
            if int(task_id) not in conn.task_ids:
                continue
            try:
                conn.queue.put_nowait(message)
                sent += 1
            except asyncio.QueueFull:
                # drop the oldest event rather than the connection
                try:
                    conn.queue.get_nowait()
                    conn.queue.put_nowait(message)
                    sent += 1
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    logger.warning("event queue wedged for task %s", task_id)
        return sent

    async def drain(self, ws: WebSocket) -> None:
        conn = self._conns.get(ws)
        if conn is None:
            return
        message = await conn.queue.get()
        await ws.send_json(message)


task_events = TaskEvents()
