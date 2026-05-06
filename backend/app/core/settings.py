from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_UNSAFE_JWT_SECRET = "change-me-please-long-random-string"
_UNSAFE_ADMIN_PASSWORDS = {"changeme", "admin", "password", "12345"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    jwt_secret: str = _UNSAFE_JWT_SECRET
    jwt_algo: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours — fewer "signature expired" interruptions

    super_admin_email: str = "admin@example.com"
    super_admin_password: str = "changeme"

    seed_demo_users: bool = False
    seed_demo_password: str = "demo-changeme-1"

    # Paper-first safety locks — cannot be overridden from API/UI.
    paper_trading_only: bool = True
    live_trading_enabled: bool = False
    # Hard mode: when true, ALL bots are forced to use the paper adapter
    # regardless of broker config. Use during the multi-week validation
    # period before any real-broker deployment.
    force_paper_only: bool = False

    cors_origins: str = "http://localhost:3000"

    groq_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Hard invariants: paper-first. Fail to boot if overridden.
    assert s.paper_trading_only is True, "PAPER_TRADING_ONLY must be true"
    assert s.live_trading_enabled is False, "LIVE_TRADING_ENABLED must be false"
    # Refuse to start in production with the default insecure JWT secret.
    if s.app_env != "development" and s.jwt_secret == _UNSAFE_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is still the default placeholder. "
            "Set a strong random secret via the JWT_SECRET env var before deploying."
        )
    # Refuse to start in production with a known-weak admin password.
    if s.app_env != "development" and s.super_admin_password.lower() in _UNSAFE_ADMIN_PASSWORDS:
        raise RuntimeError(
            "SUPER_ADMIN_PASSWORD is set to a known-weak default. "
            "Set a strong password via the SUPER_ADMIN_PASSWORD env var before deploying."
        )
    return s
