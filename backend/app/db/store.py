"""In-memory store for the skeleton.

Contract boundary: all domain services read/write through `Store`.
Swapping this for SQLAlchemy/Postgres later must not change service code.
"""
from __future__ import annotations

from threading import RLock
from typing import Any


class Store:
    """Simple namespaced key-value store with list semantics.

    Not safe for multi-process; intended for the skeleton.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._tables: dict[str, dict[str, Any]] = {}
        self._lists: dict[str, list[Any]] = {}

    # --- keyed tables ---
    def put(self, table: str, key: str, value: Any) -> None:
        with self._lock:
            self._tables.setdefault(table, {})[key] = value

    def get(self, table: str, key: str) -> Any | None:
        with self._lock:
            return self._tables.get(table, {}).get(key)

    def delete(self, table: str, key: str) -> None:
        with self._lock:
            self._tables.get(table, {}).pop(key, None)

    def list(self, table: str) -> list[Any]:
        with self._lock:
            return list(self._tables.get(table, {}).values())

    # --- append-only lists (for audit, events) ---
    def append(self, stream: str, value: Any) -> None:
        with self._lock:
            self._lists.setdefault(stream, []).append(value)

    def stream(self, stream: str) -> list[Any]:
        with self._lock:
            return list(self._lists.get(stream, []))


_store = Store()


def get_store() -> Store:
    return _store
