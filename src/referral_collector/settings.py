"""Runtime configuration for the collector."""

from pathlib import Path

from pydantic import AmqpDsn, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read required infrastructure settings when instantiated."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="REFERRAL_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: PostgresDsn = Field(repr=False)
    rabbitmq_url: AmqpDsn = Field(repr=False)
    storage_dir: Path
