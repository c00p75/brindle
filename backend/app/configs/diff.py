from __future__ import annotations

from typing import Any


def _flatten(d: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            out.update(_flatten(v, key))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = d
    return out


def diff(a: dict | None, b: dict) -> list[dict[str, Any]]:
    """Return a list of {path, before, after} changes from a to b."""
    fa = _flatten(a or {})
    fb = _flatten(b or {})
    keys = sorted(set(fa) | set(fb))
    out: list[dict[str, Any]] = []
    for k in keys:
        before = fa.get(k)
        after = fb.get(k)
        if before != after:
            out.append({"path": k, "before": before, "after": after})
    return out


RISKY_PATHS_PREFIX = ("broker.", "risk.", "strategy.strategy_id")


def contains_risky_change(changes: list[dict[str, Any]]) -> bool:
    for c in changes:
        p = c["path"]
        if any(p.startswith(prefix) or p == prefix.rstrip(".") for prefix in RISKY_PATHS_PREFIX):
            return True
    return False
