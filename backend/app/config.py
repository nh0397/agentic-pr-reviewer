from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration comes from environment variables so the same code
    runs against local Docker services or their cloud free tier equivalents
    (Neon/Supabase for Postgres, Qdrant Cloud, Groq) without code changes.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/pr_reviewer"

    cors_origins: list[str] = ["http://localhost:3000"]

    # Populated in later phases (indexing, embeddings, agent). Kept here now
    # so adding those features later is a config read, not a new settings class.
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    groq_api_key: str | None = None
    github_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
