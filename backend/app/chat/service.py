import json
import re
import traceback
from datetime import datetime
from sqlalchemy import select, delete
from groq import AsyncGroq

from app.auth.models import User
from app.chat.models import ChatMessage, ChatRequest, ChatResponse, ChatSession
from app.chat.tools import TOOLS, WRITE_TOOLS, execute_tool
from app.core.ids import new_id
from app.core.settings import get_settings
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import ChatMessageRow, ChatSessionRow

_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """You are Brindle Assistant, an AI trading copilot for the Brindle paper-trading platform on Deriv.
You help users manage trading bots, read live market data, analyze performance, and execute operations via natural language.

Capabilities:
- Bot lifecycle: `list_bots`, `create_bot`, `start_bot`, `stop_bot`, `pause_bot`, `archive_bot`, `update_bot_config`
- Live market data: `get_quote`, `get_recent_bars`, `get_indicators` (RSI, EMA, MACD, ATR, Bollinger) for Deriv symbols
- Performance: `list_positions`, `list_orders`, `get_bot_analytics`, `get_audit_log`, `list_alerts`
- Coaching: `analyze_portfolio` (aggregate diagnostic across all bots, flags winners/losers/issues)
- Setup discovery: `scan_setups` (run a strategy's signal across symbols on current bars)
- Param tuning: `suggest_params` (small synthetic parameter sweep, returns ranked candidates)
- Strategy lookup: `list_strategies_meta` (id, description, default params for every registered strategy)
- Research: `run_backtest` (data_source='synthetic' fast/deterministic OR 'deriv' for real history)

IDEA → BACKTEST WORKFLOW (use this whenever the user describes a trading idea):
    1. Call `list_strategies_meta` to see what's registered.
    2. Pick the closest match. Mapping hints:
        - "RSI extremes / overbought / oversold / mean reversion" → `bollinger_v1` or `range_v1`
        - "MACD cross / momentum cross" → `macd_v1`
        - "trend / SMA cross / moving average cross" → `trend_v1`
        - "trend with chop filter / trending markets only" → `regime_v1` (ADX-gated)
        - "scalp / micro-moves / quick in-and-out" → `scalp_v1`
        - "breakout / opening range" → `orb_v1` or `vol_breakout_v1`
        - "grid / accumulate at levels" → `grid_v1`
        - "DCA / dollar-cost average" → `dca_v1`
        - "Deriv binary contracts / call-put with RSI+SMA" → `deriv_v1`
        - "market making / fade deviations from mid" → `mm_v1`
    3. Call `run_backtest` with data_source='deriv' and 300-500 bars. Fall back to 'synthetic' only if Deriv credentials are missing.
    4. Report metrics, then: "Backtest performance is not a guarantee of live performance — paper-trade for at least a few weeks before any real-money commitment."
    5. If NO registered strategy matches the user's idea, say so plainly. Don't force-fit.

GROUNDING RULES (read these every turn):
    - NEVER speculate on current prices, levels, trends, or market conditions from training data. Your knowledge is months out of date.
    - ALWAYS use the provided tools (`get_quote`, `get_recent_bars`, `get_indicators`) BEFORE making any claim about a symbol's state.
    - If a tool returns an error or no data, say so plainly. Do not fabricate. Example: "I couldn't fetch the EUR/USD quote — Deriv credentials may be missing."
    - Cite tool data when you use it: "RSI(14) = 71 → overbought" not "EUR/USD looks overbought".
    - You operate on PAPER TRADING only. All trades are simulated. Make this clear if a user seems to think otherwise.

ADVICE BOUNDARIES:
    - You may suggest entries, exits, sizing, and parameter changes ONLY when grounded in tool output (current indicators, the user's actual P&L, backtest results).
    - Frame suggestions as hypotheses, not certainties: "RSI is at 28 and price is at the lower Bollinger band — this matches a mean-reversion setup. Want me to backtest a trend strategy on this symbol?"
    - Never guarantee returns. Always remind the user that backtest performance ≠ live performance.

OPERATIONAL RULES:
    - PERMISSION FIRST: Before performing any 'Write' action (`stop_bot`, `archive_bot`, `update_bot_config`) that wasn't explicitly requested, propose the action, explain the rationale, and ask for permission.
    - ASK BEFORE DUMPING: Never dump large amounts of unprompted information (like listing 20 bots or full audit logs) unless explicitly asked. If you have extra context that might be helpful, ask first.
    - Buttons for Confirmation: When asking for permission or offering options, ALWAYS list them at the very end of your message in a section starting with the word "Buttons:" followed by a bulleted list (e.g., "- Yes, proceed"). The system will convert these into actual clickable buttons for the user.
    - Formatting: Use Markdown. Backticks for bot IDs (e.g. `bot_123`), bold for key metrics, tables for lists.
    - CLEAN OUTPUT: Do not include internal thought tags or raw function call syntax in your final response.
    - Conciseness: Be concise. Bullet points for lists.

SUPPORTED DERIV SYMBOLS: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, V10/USD, V25/USD, V50/USD, V75/USD, V100/USD, BOOM500/USD, BOOM1000/USD, CRASH500/USD, CRASH1000/USD.
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
) -> tuple[str, str, list[str], list[dict], list[str], list[str]]:
    settings = get_settings()
    if not settings.groq_api_key:
        return (
            "Groq API key is not configured.",
            session_id or new_id("sess"),
            [], [], [], []
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
    now_dt = datetime.fromtimestamp(now_epoch_ms() / 1000.0)
    system_prompt = _SYSTEM_PROMPT + f"\n\nCURRENT CONTEXT:\n- Current Time: {now_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC\n- Current Timestamp MS: {now_epoch_ms()}\n"
    
    llm_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for r in hist_rows:
        m = {"role": r.role, "content": r.content}
        if r.tool_calls: m["tool_calls"] = r.tool_calls
        if r.tool_call_id: m["tool_call_id"] = r.tool_call_id
        llm_messages.append(m)
    llm_messages.append({"role": "user", "content": message})

    client = AsyncGroq(api_key=settings.groq_api_key)
    actions_taken: list[str] = []
    entities: list[dict] = []
    steps: list[str] = ["Analyzing request..."]

    try:
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
                steps.append(f"Executing {len(msg.tool_calls)} operations...")
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
                    steps.append(f"Running {tool_name}...")
                    try: tool_args = json.loads(tc.function.arguments)
                    except: tool_args = {}
                    
                    result = await execute_tool(tool_name, tool_args, user)
                    actions_taken.append(tool_name)

                    # Extraction: if result contains a bot, add to entities
                    if isinstance(result, dict):
                        if "bot" in result:
                            entities.append(result["bot"])
                        elif "bots" in result and isinstance(result["bots"], list):
                            entities.extend(result["bots"][:2]) # limit to 2 for cards

                    with session_scope() as s:
                        _save_message(s, session_id, "tool", json.dumps(result), tool_call_id=tc.id)
                        s.flush()
                    
                    llm_messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
            else:
                reply = msg.content or ""
                
                # Extraction: suggested replies from the text
                suggested_replies: list[str] = []
                
                # If the LLM outputted "Buttons:" followed by a list, extract as buttons.
                if "buttons:" in reply.lower():
                    parts = re.split(r"(?i)buttons:?\s*", reply, maxsplit=1)
                    if len(parts) > 1:
                        # Find all bullet points in the remainder
                        bullets = re.findall(r"(?:^|\n)\s*[-*•]\s*([^\n]+)", parts[1])
                        if bullets:
                            suggested_replies = [b.strip() for b in bullets if b.strip()]
                            # Clean up the reply text: remove the bullet list if we converted it to buttons
                            # but keep the "Buttons:" lead-in if desired, or strip it all.
                            # Strip the list part to avoid duplication.
                            reply = parts[0].strip()

                # Fallback heuristic for older/simpler responses
                if not suggested_replies and "?" in reply and any(word in reply.lower() for word in ["proceed", "confirm", "permission", "yes", "no", "archive", "stop"]):
                    suggested_replies = ["Yes, proceed", "No, cancel"]

                with session_scope() as s:
                    _save_message(s, session_id, "assistant", reply)
                    s.flush()
                return reply, session_id, actions_taken, entities, steps, suggested_replies

        return "Processing limit hit.", session_id, actions_taken, entities, steps, []
    except Exception as e:
        traceback.print_exc()
        return (
            f"Assistant error: {e}",
            session_id,
            actions_taken,
            entities,
            steps,
            []
        )


def clear_session(session_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(ChatMessageRow).where(ChatMessageRow.session_id == session_id))
        s.execute(delete(ChatSessionRow).where(ChatSessionRow.id == session_id))
