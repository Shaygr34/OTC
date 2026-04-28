"""Application settings loaded from environment variables via Pydantic."""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


_ENV_FILE = ".env"


class IBKRSettings(BaseSettings):
    model_config = {"env_prefix": "IBKR_", "env_file": _ENV_FILE, "extra": "ignore"}

    host: str = "127.0.0.1"
    port: int = 7497
    client_id_scanner: int = 1
    client_id_data: int = 2
    timeout: int = 30
    max_l2_subscriptions: int = 2


class TelegramSettings(BaseSettings):
    model_config = {"env_prefix": "TELEGRAM_", "env_file": _ENV_FILE, "extra": "ignore"}

    bot_token: str = ""
    chat_id: str = ""
    enabled: bool = False


class DatabaseSettings(BaseSettings):
    model_config = {"env_prefix": "DATABASE_", "env_file": _ENV_FILE, "extra": "ignore"}

    url: str = "sqlite+aiosqlite:///data/atm.db"


class RiskSettings(BaseSettings):
    model_config = {"env_prefix": "RISK_", "env_file": _ENV_FILE, "extra": "ignore"}

    max_position_pct: Decimal = Field(default=Decimal("0.05"))
    max_loss_pct: Decimal = Field(default=Decimal("0.02"))
    portfolio_value: Decimal = Field(default=Decimal("10000"))


class LogSettings(BaseSettings):
    model_config = {"env_prefix": "LOG_", "env_file": _ENV_FILE, "extra": "ignore"}

    level: str = "INFO"
    format: str = "json"


class Settings(BaseSettings):
    ibkr: IBKRSettings = Field(default_factory=IBKRSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    log: LogSettings = Field(default_factory=LogSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings singleton. Call _reset_settings() in tests."""
    return Settings()


def _reset_settings() -> None:
    """Clear the settings cache. For testing only."""
    get_settings.cache_clear()
