"""Request ID middleware and log correlation.

Every request gets a correlation id: the client's `X-Request-ID` when supplied and well formed,
otherwise a fresh UUID4. The id is stored on the request state, echoed back on the response, and
injected into every log record emitted while handling the request, so one request's lines can be
gathered from a busy log.

@generated-by Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research), 2026-11-04T13:05:00Z
Full raw startup instructions from the session, verbatim, from first token until the task began:

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
  or plan to do without actually doing it. Every response should either (a) contain tool calls that
  make progress, or (b) deliver a final result to the user."
  "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
  'done' means every named acceptance criterion is verified — never a plausible subset."
  "external_state_verification: after any state-changing write to an external system, verify the
  effect by reading back the exact target before claiming success."
  Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
  read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
  web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.

@runtime os=windows arch=x86_64 home_dir=C:\\Users\\2
  working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
  shell=C:\\Program Files\\Git\\bin\\bash.exe
"""

import contextvars
import logging
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

HEADER = "X-Request-ID"
MAX_LEN = 128
# kept narrow on purpose: the value ends up in logs and headers
_VALID = re.compile(r"^[A-Za-z0-9._:-]{1,%d}$" % MAX_LEN)

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def current_request_id() -> str:
    return request_id_var.get()


class RequestIdLogFilter(logging.Filter):
    """Stamp every record with the id of the request being handled."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


LOGGER = logging.getLogger("api.request")
LOGGER.addFilter(RequestIdLogFilter())


def install_log_filter(logger: logging.Logger | None = None) -> None:
    """Attach the filter to the root logger and give it a format that uses the id."""
    target = logger or logging.getLogger()
    if not any(isinstance(f, RequestIdLogFilter) for f in target.filters):
        target.addFilter(RequestIdLogFilter())
    for handler in target.handlers or []:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )


def normalise(incoming: str | None) -> str:
    """Keep a client id when it is safe, otherwise mint one."""
    if incoming and _VALID.match(incoming):
        return incoming
    return str(uuid.uuid4())


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = normalise(request.headers.get(HEADER))
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        LOGGER.info("%s %s", request.method, request.url.path)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[HEADER] = request_id
        return response
