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
    frontend_url: str = "http://localhost:3000"

    session_secret_key: str = "dev-only-secret-change-me"
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_redirect_uri: str = "http://localhost:8000/api/auth/github/callback"

    # Populated in later phases (indexing, embeddings, agent). Kept here now
    # so adding those features later is a config read, not a new settings class.
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None

    groq_api_key: str | None = None
    # Which model the review agent runs on. Kept in config because the
    # free tier's available models change over time.
    llm_model: str = "openai/gpt-oss-120b"
    # Ceiling on tool-calling rounds in one review. Without it a model that
    # keeps asking for tools would loop until the rate limit stops it.
    agent_max_steps: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
