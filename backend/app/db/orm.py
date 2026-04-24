"""SQLAlchemy ORM models.

These are persistence-layer types only. Services read/write through these
rows but return Pydantic domain models to the rest of the app.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class BotRow(Base):
    __tablename__ = "bots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    active_config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)


class ConfigVersionRow(Base):
    __tablename__ = "config_versions"

    bot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    applied_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    validation_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_email: Mapped[str] = mapped_column(String(320), index=True)
    actor_role: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(32), index=True)
    resource_id: Mapped[str] = mapped_column(String(128), index=True)
    at_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    diff: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # 'metadata' is reserved on DeclarativeBase, so use meta_ with column name 'metadata'.
    meta_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)


# Secondary sort by id ensures deterministic order when at_ms collides.
Index("ix_audit_at_id", AuditRow.at_ms, AuditRow.id)


class OrderRow(Base):
    """An OrderIntent that was sent through ExecutionService.

    Stores the intent + the normalized ExecutionResult. One row per attempt.
    """
    __tablename__ = "orders"

    client_order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(64), index=True)
    strategy_id: Mapped[str] = mapped_column(String(64))
    config_version: Mapped[int] = mapped_column(Integer)
    adapter_id: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float | None] = mapped_column(nullable=True)
    notional: Mapped[float | None] = mapped_column(nullable=True)
    limit_price: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    submitted_at_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FillRow(Base):
    """A fill produced by an order. One row per fill (currently 1:1 with FILLED orders)."""
    __tablename__ = "fills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(64), index=True)
    client_order_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column()
    price: Mapped[float] = mapped_column()
    fees: Mapped[float] = mapped_column(default=0.0)
    filled_at_ms: Mapped[int] = mapped_column(BigInteger, index=True)


class PositionRow(Base):
    """Materialized position per (bot, symbol). Updated transactionally on fill."""
    __tablename__ = "positions"

    bot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    quantity: Mapped[float] = mapped_column(default=0.0)
    avg_price: Mapped[float | None] = mapped_column(nullable=True)
    realized_pnl: Mapped[float] = mapped_column(default=0.0)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)


class AlertRow(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(String(1024))
    bot_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    acknowledged_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    meta_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
