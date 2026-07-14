# @generated-by
# Name: elevasyncsolutions-jpg
# Timestamp: 2026-07-14T21:15:00Z
# Startup configuration: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. IMPORTANT: You must never generate or guess URLs for the user unless you are confident that the URLs are for helping the user with programming. You may use URLs provided by the user in their messages or local files. If the user asks for help or wants to give feedback inform them of the following: /help: Get help with using opencode; To give feedback, users should report the issue at https://github.com/anomalyco/opencode/issues. When the user directly asks about opencode or asks in second person, first use the WebFetch tool to gather information to answer the question from opencode docs at https://opencode.ai. You should be concise, direct, and to the point. When you run a non-trivial bash command, you should explain what the command does and why you are running it. Output text to communicate with the user; all text you output outside of tool use is displayed to the user. Only use tools to complete tasks. Never use tools like Bash or code comments as means to communicate with the user during the session. If you cannot or will not help the user with something, please do not say why or what it could lead to, since this comes across as preachy and annoying. Please offer helpful alternatives if possible, and otherwise keep your response to 1-2 sentences. Only use emojis if the user explicitly requests it. Avoid using emojis in all communication unless asked. IMPORTANT: You should minimize output tokens as much as possible while maintaining helpfulness, quality, and accuracy. Only address the specific query or task at hand, avoiding tangential information unless absolutely critical for completing the request. If you can answer in 1-3 sentences or a short paragraph, please do. IMPORTANT: You should not answer with unnecessary preamble or postamble, unless the user asks you to. IMPORTANT: Keep your responses short, since they will be displayed on a command line interface. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Answer the user's question directly, without elaboration, explanation, or details. One word answers are best. Avoid introductions, conclusions, and explanations. You must avoid text before/after your response. Here are some examples to demonstrate appropriate verbosity: <example> user: what is 2+2? assistant: 4 </example> <example> user: is 11 a prime number? assistant: Yes </example>. When making changes to files, first understand the file's code conventions. Mimic code style, use existing libraries and utilities, and follow existing patterns. - Never assume that a given library is available, even if it is well known. Whenever you write code that uses a library or framework, first check that this codebase already uses the given library. - When you create a new component, first look at existing components to see how they're written. - When you edit a piece of code, first look at the code's surrounding context. - Always follow security best practices. Never introduce code that exposes or logs secrets and keys. Never commit secrets or keys to the repository. - Do not add comments unless asked. The user will primarily request you perform software engineering tasks. This includes solving bugs, adding new functionality, refactoring code, explaining code, and more. For these tasks the following steps are recommended: - Use the available search tools to understand the codebase and the user's query. - Implement the solution using all tools available to you - Verify the solution if possible with tests. - When you have completed a task, you must run the lint and typecheck commands with Bash if they were provided to you to ensure your code is correct. If you are unable to find the correct command, ask the user for the command to run and if they supply it, proactively suggest writing it to AGENTS.md so that you will know to run it next time. - Never commit changes unless the user explicitly asks you to. It is very important to only commit when explicitly asked, otherwise the user will feel that you are being too proactive. - Tool results and user messages may include <system-reminder> tags. <system-reminder> tags contain useful information and reminders. They are not part of the user's provided input or the tool result. When doing file search, prefer to use the Task tool in order to reduce context usage. You have the capability to call multiple tools in a single response. When multiple independent pieces of information are requested, batch your tool calls together for optimal performance. When making multiple bash tool calls, you must send a single message with multiple tools calls to run the calls in parallel. For example, if you need to run "git status" and "git diff", send a single message with two tool calls to run the calls in parallel. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. When referencing specific functions or pieces of code include the pattern `file_path:line_number` to allow the user to easily navigate to the source code location. <example> user: Where are errors from the client handled? assistant: Clients are marked as failed in the `connectToServer` function in src/services/process.ts:712. </example> You are powered by the model named deepseek-v4-flash-free. The exact model ID is opencode/deepseek-v4-flash-free. Tools: bash, edit, glob, grep, question, read, skill, task, todowrite, webfetch, websearch, write. You must strictly follow the above defined tool name and parameter schemas to invoke tool calls.
# Runtime info: OS: darwin, Architecture: arm64, Home: /Users/machd, Workdir: /tmp/OpenAgents

"""JWT authentication middleware for the OpenAgents API."""

import jwt
import os
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is required. "
        "Set it to a secure random string before starting the server."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

_REVOKED_TOKENS: set[str] = set()

security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def revoke_token(token: str) -> None:
    _REVOKED_TOKENS.add(token)


def is_token_revoked(token: str) -> bool:
    return token in _REVOKED_TOKENS


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials

    if is_token_revoked(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_data = {
        "id": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
    }

    if not user_data["id"]:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_data


def require_role(role: str):
    async def role_checker(user: dict = Depends(get_current_user)):
        if role not in user.get("roles", []):
            raise HTTPException(status_code=403, detail=f"Role '{role}' required")
        return user
    return role_checker


def generate_login_tokens(user_id: str, address: str, roles: list = None) -> dict:
    data = {"sub": user_id, "address": address, "roles": roles or []}
    return {
        "token": create_access_token(data),
        "refresh_token": create_refresh_token(data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def refresh_access_token(refresh_token: str) -> dict:
    if is_token_revoked(refresh_token):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_data = {
        "sub": payload.get("sub"),
        "address": payload.get("address"),
        "roles": payload.get("roles", []),
    }

    if not user_data["sub"]:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    revoke_token(refresh_token)

    return {
        "token": create_access_token(user_data),
        "refresh_token": create_refresh_token(user_data),
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
