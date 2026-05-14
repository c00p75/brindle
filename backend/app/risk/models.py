from pydantic import BaseModel, Field, field_validator


class RiskLimits(BaseModel):
    """Per-bot risk limits. Enforced before every execution."""

    max_position_notional: float = Field(gt=0, description="max notional per single position, USD")
    max_total_exposure: float = Field(gt=0, description="max total gross exposure, USD")
    max_daily_loss: float = Field(gt=0, description="max realized + unrealized loss per day, USD")
    max_drawdown_pct: float = Field(gt=0, le=100, description="max drawdown percent")
    max_open_orders: int = Field(gt=0, le=1000)
    kill_switch: bool = False
    # Pause the bot if the last N settled trades are all losses. 0 disables.
    # Catches "running into a wall" failure modes that the daily-loss limit
    # might not catch quickly enough.
    max_consecutive_losses: int = Field(default=0, ge=0, le=100,
        description="Pause bot after N consecutive losing trades. 0=disabled.")
    risk_per_trade_pct: float | None = Field(default=None, ge=0, le=100,
        description="Dynamic sizing: risk X% of effective balance per trade.")
    max_stake: float | None = Field(default=None, gt=0,
        description="Hard cap on per-trade stake in USD. Overrides risk_per_trade_pct sizing.")

    @field_validator("max_total_exposure")
    @classmethod
    def _exposure_gte_position(cls, v: float, info) -> float:
        pos = info.data.get("max_position_notional")
        if pos is not None and v < pos:
            raise ValueError("max_total_exposure must be >= max_position_notional")
        return v
