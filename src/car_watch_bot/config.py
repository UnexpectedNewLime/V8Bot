"""Application configuration loaded from environment variables."""

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the bot."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    discord_guild_id: int | None = Field(default=None, alias="DISCORD_GUILD_ID")
    database_url: str = Field(
        default="sqlite:///./car_watch_bot.sqlite3",
        alias="DATABASE_URL",
    )
    default_timezone: str = Field(default="Australia/Sydney", alias="DEFAULT_TIMEZONE")
    default_currency: str = Field(default="AUD", alias="DEFAULT_CURRENCY")
    default_distance_unit: Literal["km", "mi"] = Field(
        default="km",
        alias="DEFAULT_DISTANCE_UNIT",
    )
    usd_to_aud_rate: Decimal = Field(default=Decimal("1.50"), alias="USD_TO_AUD_RATE")
    scrape_interval_minutes: int = Field(default=60, alias="SCRAPE_INTERVAL_MINUTES")
    digest_poll_interval_minutes: int = Field(
        default=1,
        alias="DIGEST_POLL_INTERVAL_MINUTES",
    )
    scraper_user_agent: str = Field(
        default="V8Bot/0.1 (+https://github.com/local/v8bot; contact: local-dev)",
        alias="SCRAPER_USER_AGENT",
    )
    scraper_timeout_seconds: float = Field(default=10.0, alias="SCRAPER_TIMEOUT_SECONDS")
    scraper_min_interval_seconds: float = Field(
        default=2.0,
        alias="SCRAPER_MIN_INTERVAL_SECONDS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("discord_guild_id", mode="before")
    @classmethod
    def _empty_guild_id_is_none(cls, value: object) -> object:
        """Treat an empty env var as no guild override."""

        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
