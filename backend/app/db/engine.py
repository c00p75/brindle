"""Database engine + session factory.

Single source of truth for how services obtain a DB session.
Default: local SQLite file under `data/`.
Swap to Postgres by setting `DATABASE_URL=postgresql+psycopg://...`.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

_state: dict = {"engine": None, "SessionLocal": None}


def _default_sqlite_url() -> str:
    # Relative to backend/ working dir. `chown` the data/ dir to the service user.
    return "sqlite:///./data/trading-bot.db"


def _build() -> tuple[Engine, sessionmaker[Session]]:
    url = os.getenv("DATABASE_URL") or _default_sqlite_url()
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            path = Path(url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)

    is_sqlite = url.startswith("sqlite")
    pool_kwargs: dict = {}
    if is_sqlite:
        pool_kwargs["poolclass"] = StaticPool if ":memory:" in url else NullPool
    else:
        pool_kwargs["poolclass"] = QueuePool
        pool_kwargs["pool_size"] = 5
        pool_kwargs["max_overflow"] = 10
        pool_kwargs["pool_pre_ping"] = True

    engine = create_engine(
        url,
        connect_args=connect_args,
        future=True,
        **pool_kwargs,
    )
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )
    return engine, SessionLocal


def get_engine() -> Engine:
    if _state["engine"] is None:
        eng, sf = _build()
        _state["engine"] = eng
        _state["SessionLocal"] = sf
    return _state["engine"]


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    return _state["SessionLocal"]  # type: ignore[return-value]


def reset_engine() -> None:
    """Force re-creation of the engine on next access (for tests / env reload)."""
    eng = _state["engine"]
    if eng is not None:
        try:
            eng.dispose()
        except Exception:  # noqa: BLE001
            pass
    _state["engine"] = None
    _state["SessionLocal"] = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope around a series of operations."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    from app.db.orm import Base  # local import to avoid cycles

    Base.metadata.create_all(get_engine())


def use_test_database() -> None:
    """Switch to a shared in-memory SQLite for tests. Drops previous schema."""
    from app.db.orm import Base

    reset_engine()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )
    _state["engine"] = engine
    _state["SessionLocal"] = SessionLocal
    Base.metadata.create_all(engine)
