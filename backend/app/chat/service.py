from __future__ import annotations

import json
import uuid

from groq import AsyncGroq

from app.auth.models import User
from app.chat.tools import TOOLS, execute_tool
from app.core.settings import get_settings

_SYSTEM_PROMPT = """You are Brindle Assistant, an AI operator for the Brindle paper-trading platform.
You help users manage trading bots, monitor performance, and execute operations via natural language.

Capabilities:
- List, create, start, stop, and pause trading bots
- View and acknowledge alerts
- Read the audit log
- Check open positions and recent orders
- Run backtests for strategies (available: 'trend')
- Answer questions about the platform state

Rules:
- This is a paper-trading platform — no real money is at risk.
- Always confirm destructive actions (stop/archive) before executing if the user hasn't been explicit.
- Be concise. Use bullet points for lists of data.
- When showing bot IDs or other identifiers, show them so the user can reference them.
- If a tool returns an error, explain it clearly and suggest next steps.
"""

# In-memory session store: session_id → message history
_sessions: dict[str, list[dict]] = {}

_MODEL = "llama-3.3-70b-versatile"


async def process_message(
    message: str,
    session_id: str | None,
    user: User,
) -> tuple[str, str, list[str]]:
    """Process a user message and return (reply, session_id, actions_taken)."""
    settings = get_settings()
    if not settings.groq_api_key:
        return (
            "Groq API key is not configured. Please set GROQ_API_KEY in the backend environment.",
            session_id or str(uuid.uuid4()),
            [],
        )

    client = AsyncGroq(api_key=settings.groq_api_key)

    if session_id and session_id in _sessions:
        history = _sessions[session_id]
    else:
        session_id = str(uuid.uuid4())
        history = []
        _sessions[session_id] = history

    history.append({"role": "user", "content": message})
    messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}] + history

    actions_taken: list[str] = []

    # Tool-calling loop — iterate until the model stops calling tools
    for _ in range(8):
        response = await client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1024,
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            # Append assistant message with tool calls to context
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}
                result = await execute_tool(tool_name, tool_args, user)
                actions_taken.append(tool_name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )
        else:
            reply = msg.content or ""
            history.append({"role": "assistant", "content": reply})
            return reply, session_id, actions_taken

    # Fallback if loop limit hit
    reply = "I ran into a processing limit. Please try a simpler request."
    history.append({"role": "assistant", "content": reply})
    return reply, session_id, actions_taken


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
