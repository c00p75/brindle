from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    jwt_secret: str = "change-me-please-long-random-string"
    jwt_algo: str = "HS256"
    jwt_expire_minutes: int = 60

    # Paper-first safety locks. These must stay true/false respectively
    # and cannot be overridden from API/UI.
    paper_trading_only: bool = True
    live_trading_enabled: bool = False

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Hard invariant: paper-first. Fail to boot if overridden.
    assert s.paper_trading_only is True, "PAPER_TRADING_ONLY must be true"
    assert s.live_trading_enabled is False, "LIVE_TRADING_ENABLED must be false"
    return s
