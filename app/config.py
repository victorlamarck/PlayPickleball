"""Application settings loaded from environment variables (and `.env` in development)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_API_KEY = "dev-scorekeeper-key"
DEV_INTERNAL_TOKEN = "dev-internal-token"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://scores:scores@localhost:5432/scores"
    gcp_project_id: str = "demo-live-scores"
    firestore_emulator_host: str | None = None
    api_key: str = DEV_API_KEY
    internal_token: str = DEV_INTERNAL_TOKEN
    fcm_enabled: bool = False
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _reject_dev_secrets_in_prod(self) -> Self:
        if self.env == "prod":
            if self.api_key == DEV_API_KEY:
                raise ValueError("API_KEY must be set to a non-default value in prod")
            if self.internal_token == DEV_INTERNAL_TOKEN:
                raise ValueError("INTERNAL_TOKEN must be set to a non-default value in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
