"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Environment settings for the backend."""

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anonymous key")
    supabase_service_key: str = Field(..., description="Supabase service role key")
    redis_url: str = Field(..., description="Redis connection URL for streaming/cache")
    google_api_key: str = Field(..., description="Google Gemini API key for future RAG modules")

    @property
    def cors_origins(self) -> list[str]:
        """Allowed origins for browser requests."""
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()  # type: ignore[call-arg]
