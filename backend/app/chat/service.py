import json
from sqlalchemy import select, delete
from groq import AsyncGroq

from app.auth.models import User
from app.chat.tools import TOOLS, execute_tool
from app.core.settings import get_settings

_SYSTEM_PROMPT = """You are Brindle Assistant, an AI operator for the Brindle paper-trading platform.
You help users manage trading bots, monitor performance, and execute operations via natural language.

Capabilities:
- List, create, start, stop, pause, and archive trading bots
- Update bot configurations (stake, strategy, risk)
- View and acknowledge alerts
- Read the audit log
- Check open positions, recent orders, and performance analytics
- Run backtests for strategies (available: 'trend')
- Answer questions about the platform state

Rules:
- PERMISSION FIRST: Before performing any 'Write' action (stop, archive, update_config) that wasn't explicitly and specifically requested (e.g. user said "Stop bot_1"), you MUST first propose the action, explain the rationale, and wait for the user to say "Yes" or "Go ahead".
- Deep Analysis: When asked to analyze performance, use 'get_bot_analytics' and 'list_orders' to look for patterns. Suggest improvements if win rate is low.
- Formatting: Use Markdown for all technical data. Use backticks for bot IDs (e.g. `bot_123`), bold for key metrics, and tables for lists of performance data.
- CLEAN OUTPUT: NEVER output internal tool call tags like `<function=...>` or `</function>` in your natural language response. Only provide the human-readable explanation of what you are doing or the data you found.
- Conciseness: Be concise. Use bullet points for lists.
"""

from app.auth.models import User
from app.chat.models import ChatMessage, ChatSession
from app.chat.tools import TOOLS, WRITE_TOOLS, execute_tool
from app.core.ids import new_id
from app.core.settings import get_settings
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import ChatMessageRow, ChatSessionRow

_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """You are Brindle Assistant, an AI operator for the Brindle paper-trading platform.
You help users manage trading bots, monitor performance, and execute operations via natural language.

Capabilities:
- List, create, start, stop, pause, and archive trading bots
- Update bot configurations (stake, strategy, risk)
- View and acknowledge alerts
- Read the audit log
- Check open positions, recent orders, and performance analytics
- Run backtests for strategies (available: 'trend')
- Answer questions about the platform state

Rules:
- PERMISSION FIRST: Before performing any 'Write' action (stop, archive, update_config) that wasn't explicitly and specifically requested (e.g. user said "Stop bot_1"), you MUST first propose the action, explain the rationale, and wait for the user to say "Yes" or "Go ahead".
- Formatting: Use Markdown for all technical data. Use backticks for bot IDs (e.g. `bot_123`), bold for key metrics, and tables for lists of performance data.
- CLEAN OUTPUT: NEVER output internal tool call tags like `<function=...>` or `</function>` in your natural language response.
- Conciseness: Be concise. Use bullet points for lists.
"""


async def list_sessions(user_id: str) -> list[ChatSession]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(ChatSessionRow)
                .where(ChatSessionRow.user_id == user_id)
                .order_by(ChatSessionRow.updated_at_ms.desc())
            )
            .scalars()
            .all()
        )
        return [
            ChatSession(
                id=r.id,
                title=r.title,
                created_at_ms=r.created_at_ms,
                updated_at_ms=r.updated_at_ms,
            )
            for r in rows
        ]


async def get_history(session_id: str) -> list[ChatMessage]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == session_id)
                .order_by(ChatMessageRow.at_ms.asc())
            )
            .scalars()
            .all()
        )
        return [
            ChatMessage(
                role=r.role,
                content=r.content,
                tool_calls=r.tool_calls,
                tool_call_id=r.tool_call_id,
                at_ms=r.at_ms,
            )
            for r in rows
        ]


def _save_message(s, session_id: str, role: str, content: str, **kwargs) -> None:
    row = ChatMessageRow(
        id=new_id("msg"),
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=kwargs.get("tool_calls"),
        tool_call_id=kwargs.get("tool_call_id"),
        at_ms=now_epoch_ms(),
    )
    s.add(row)


async def process_message(
    message: str,
    session_id: str | None,
    user: User,
) -> tuple[str, str, list[str]]:
    settings = get_settings()
    if not settings.groq_api_key:
        return (
            "Groq API key is not configured.",
            session_id or new_id("sess"),
            [],
        )

    with session_scope() as s:
        if session_id:
            session = s.get(ChatSessionRow, session_id)
            if not session:
                session_id = None
        
        if not session_id:
            session_id = new_id("sess")
            session = ChatSessionRow(
                id=session_id,
                user_id=user.id,
                title=message[:50] + ("..." if len(message) > 50 else ""),
                created_at_ms=now_epoch_ms(),
                updated_at_ms=now_epoch_ms(),
            )
            s.add(session)
        else:
            session.updated_at_ms = now_epoch_ms()

        # Load history
        hist_rows = (
            s.execute(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == session_id)
                .order_by(ChatMessageRow.at_ms.asc())
            )
            .scalars()
            .all()
        )
        
        # Save user message
        _save_message(s, session_id, "user", message)
        s.flush()

    # Prep messages for LLM
    llm_messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for r in hist_rows:
        m = {"role": r.role, "content": r.content}
        if r.tool_calls: m["tool_calls"] = r.tool_calls
        if r.tool_call_id: m["tool_call_id"] = r.tool_call_id
        llm_messages.append(m)
    llm_messages.append({"role": "user", "content": message})

    client = AsyncGroq(api_key=settings.groq_api_key)
    actions_taken: list[str] = []

    for _ in range(8):
        response = await client.chat.completions.create(
            model=_MODEL,
            messages=llm_messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1024,
        )

        msg = response.choices[0].message
        
        if msg.tool_calls:
            tool_calls_data = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
            
            with session_scope() as s:
                _save_message(s, session_id, "assistant", msg.content or "", tool_calls=tool_calls_data)
                s.flush()

            llm_messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": tool_calls_data})

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try: tool_args = json.loads(tc.function.arguments)
                except: tool_args = {}
                
                result = await execute_tool(tool_name, tool_args, user)
                actions_taken.append(tool_name)
                
                with session_scope() as s:
                    _save_message(s, session_id, "tool", json.dumps(result), tool_call_id=tc.id)
                    s.flush()
                
                llm_messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
        else:
            reply = msg.content or ""
            with session_scope() as s:
                _save_message(s, session_id, "assistant", reply)
                s.flush()
            return reply, session_id, actions_taken

    return "Processing limit hit.", session_id, actions_taken


def clear_session(session_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(ChatMessageRow).where(ChatMessageRow.session_id == session_id))
        s.execute(delete(ChatSessionRow).where(ChatSessionRow.id == session_id))
