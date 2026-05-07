"""Generate a Strategy plugin .py file from a natural-language description.

End-to-end:
  1. User submits a description like "buy when EUR/USD's 50-period SMA
     crosses above its 200-period SMA, sell on the reverse"
  2. We send a structured prompt to Groq with the Strategy contract +
     a reference example (trend.py)
  3. Groq returns Python code
  4. We extract just the code (in case the model wraps in markdown fences)
  5. We AST-validate the result:
       - parses
       - defines exactly one class with `id`, `PARAM_SCHEMA`, `on_data`
       - imports are restricted to a safe whitelist
       - no calls to dangerous names (eval, exec, __import__, open, etc.)
  6. We write to app/strategies/user/{slug}.py
  7. The plugin loader will pick it up on next backend restart

Returns either {ok: true, strategy_id, file_path} or
{ok: false, errors: [...]}.

This is admin-gated. Non-admins should never reach this endpoint.
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from app.llm import client as llm_client

log = logging.getLogger("llm.strategy_gen")

USER_STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "strategies" / "user"

# Modules a generated strategy may import. Anything else is rejected.
_IMPORT_WHITELIST: set[str] = {
    "math",
    "dataclasses",
    "typing",
    "__future__",
    "app.core.ids",
    "app.execution.models",
    "app.strategies.base",
}

# Names that, if called, mean the model is doing something dangerous.
_BANNED_CALLS: set[str] = {
    "eval", "exec", "compile", "__import__", "open",
    "input", "globals", "locals", "vars",
}

_REFERENCE_TREND_V1 = '''
"""Reference example: trend_v1 strategy (truncated for brevity)."""
from __future__ import annotations
from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


class TrendV1:
    id = "trend_v1"
    PARAM_SCHEMA: dict[str, object] = {
        "fast": 5, "slow": 20, "qty": 1000.0,
        "min_cross_pct": 0.02, "cooldown_ticks": 10,
    }
    def __init__(self) -> None:
        self._cooldown: dict[str, int] = {}
    def debug_state(self, ctx: StrategyContext) -> dict:
        # ... returns {bars_available, bars_needed, indicators, signal}
        return {}
    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        fast_n = int(params.get("fast", 5))
        slow_n = int(params.get("slow", 20))
        qty = float(params.get("qty", 1000))
        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        if len(closes) < slow_n + 1: return []
        # ... compute SMAs, detect crossover, return list of OrderIntent
        return []
'''.strip()


_SYSTEM = f"""You are a strategy code generator for the Brindle trading platform.

Your job: given a natural-language description, produce a single Python file
that implements the Strategy contract. The file will be saved to
app/strategies/user/ and registered automatically on backend restart.

CONTRACT (mandatory):
- Define exactly ONE class.
- Class must have:
    id: str  (unique strategy id, lowercase snake_case ending in _v1)
    PARAM_SCHEMA: dict[str, object]  (defaults for every param)
    def __init__(self) -> None
    def on_data(self, ctx) -> list[OrderIntent]
    def debug_state(self, ctx) -> dict   (optional, for the live UI panel)
- ctx.bars is a list of Bar objects with attributes: symbol, ts_ms, open,
  high, low, close, volume.
- Filter ctx.bars by ctx.symbol — only this symbol's bars matter.
- Return OrderIntent list (empty list = no action).
- OrderIntent constructor:
    OrderIntent(bot_id=ctx.bot_id, strategy_id=ctx.strategy_id,
                client_order_id=new_id("coid"), symbol=ctx.symbol,
                side=Side.BUY|Side.SELL, order_type=OrderType.MARKET,
                quantity=..., config_version=ctx.config_version)

IMPORT RULES (strict — code will be rejected otherwise):
- ALLOWED: math, dataclasses, typing, __future__,
           app.core.ids, app.execution.models, app.strategies.base
- FORBIDDEN: anything else, especially: os, sys, subprocess, requests,
             httpx, websockets, pickle, asyncio, threading, sqlalchemy

CODE RULES (strict):
- No calls to: eval, exec, __import__, open, input, globals, locals, compile.
- Do NOT issue network calls, file I/O, or background threads.
- Pure logic only — no side effects beyond returning OrderIntent.

OUTPUT FORMAT:
- Return ONLY Python code. No prose, no markdown fences, no explanation.
- The file must be self-contained and syntactically valid.

REFERENCE EXAMPLE (for shape, not content):

{_REFERENCE_TREND_V1}
"""


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:40] or "custom"


def _strip_markdown_fences(text: str) -> str:
    """Some models wrap code in ```python ... ``` even when told not to."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def _ast_validate(code: str) -> tuple[bool, list[str], str | None, dict | None]:
    """Returns (ok, errors, strategy_id, param_schema)."""
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"syntax error: {e}"], None, None

    # 1) Imports must be on the whitelist
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in _IMPORT_WHITELIST:
                    errors.append(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod not in _IMPORT_WHITELIST:
                errors.append(f"forbidden import-from: {mod}")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name): name = fn.id
            elif isinstance(fn, ast.Attribute): name = fn.attr
            if name in _BANNED_CALLS:
                errors.append(f"forbidden call: {name}")

    # 2) Exactly one class with required attributes
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if len(classes) != 1:
        errors.append(f"expected exactly 1 class, found {len(classes)}")
        return False, errors, None, None
    cls = classes[0]

    # 3) Find id, PARAM_SCHEMA, on_data
    strategy_id: str | None = None
    param_schema: dict | None = None
    has_on_data = False
    for item in cls.body:
        if isinstance(item, ast.Assign):
            for tgt in item.targets:
                if isinstance(tgt, ast.Name):
                    if tgt.id == "id" and isinstance(item.value, ast.Constant):
                        if isinstance(item.value.value, str):
                            strategy_id = item.value.value
                    elif tgt.id == "PARAM_SCHEMA":
                        try:
                            param_schema = ast.literal_eval(item.value)
                        except (ValueError, SyntaxError):
                            errors.append("PARAM_SCHEMA must be a literal dict")
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            if item.target.id == "id" and isinstance(item.value, ast.Constant):
                if isinstance(item.value.value, str):
                    strategy_id = item.value.value
            elif item.target.id == "PARAM_SCHEMA" and item.value is not None:
                try:
                    param_schema = ast.literal_eval(item.value)
                except (ValueError, SyntaxError):
                    errors.append("PARAM_SCHEMA must be a literal dict")
        elif isinstance(item, ast.FunctionDef) and item.name == "on_data":
            has_on_data = True

    if not strategy_id:
        errors.append("class is missing required `id: str` attribute")
    if not isinstance(param_schema, dict):
        errors.append("class is missing required `PARAM_SCHEMA: dict` attribute")
    if not has_on_data:
        errors.append("class is missing required `on_data(self, ctx)` method")

    return (len(errors) == 0), errors, strategy_id, param_schema if isinstance(param_schema, dict) else None


async def generate_strategy(description: str) -> dict[str, Any]:
    """Generate, validate, and persist a strategy from a natural-language description.

    Returns:
      {ok: True, strategy_id, param_schema, file_path}  on success
      {ok: False, errors: [...], code?: "..."}          on failure
    """
    if not description or not description.strip():
        return {"ok": False, "errors": ["description is empty"]}

    raw = await llm_client.complete(
        system=_SYSTEM,
        user=f"Description:\n{description.strip()}\n\nProduce the Python file now.",
        temperature=0.3, max_tokens=3000,
    )
    code = _strip_markdown_fences(raw)

    ok, errors, strategy_id, param_schema = _ast_validate(code)
    if not ok:
        return {"ok": False, "errors": errors, "code": code}

    # Refuse to overwrite a built-in strategy id
    from app.strategies.registry import STRATEGY_REGISTRY
    if strategy_id in STRATEGY_REGISTRY:
        return {"ok": False, "errors": [
            f"id '{strategy_id}' is already taken by a built-in strategy"
        ], "code": code}

    # Persist
    USER_STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{_slugify(strategy_id)}.py"
    file_path = USER_STRATEGIES_DIR / fname
    if file_path.exists():
        return {"ok": False, "errors": [
            f"a file already exists at {file_path.name} — choose a different id"
        ], "code": code}
    header = (f"# Auto-generated by Brindle strategy generator.\n"
              f"# Source description (for human reference, not parsed):\n"
              + "\n".join(f"# {ln}" for ln in description.strip().splitlines()) + "\n\n")
    file_path.write_text(header + code, encoding="utf-8")
    log.info("generated strategy id=%s file=%s", strategy_id, file_path)

    return {
        "ok": True,
        "strategy_id": strategy_id,
        "param_schema": param_schema,
        "file_path": str(file_path.relative_to(file_path.parents[3])),
        "note": "Restart the backend to load the new strategy into the registry.",
    }
