from typing import Any, Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agent_studio"
    REDIS_URL: str = "redis://localhost:6379/0"
    LLM_PROVIDER: Literal["pellet", "anthropic"] = "pellet"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    PELLET_API_KEY: str = ""
    PELLET_BASE_URL: str = "https://getpellet.io/v1"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    AUTH_SECRET: str = "change-me-in-production"
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "agent-studio-uploads"
    AWS_REGION: str = "ap-south-1"
    SARVAM_API_KEY: str = ""
    EXOTEL_API_KEY: str = ""
    EXOTEL_API_TOKEN: str = ""
    EXOTEL_SID: str = ""
    EXOTEL_SUBDOMAIN: str = ""
    GUPSHUP_API_KEY: str = ""
    GUPSHUP_APP_NAME: str = ""
    GUPSHUP_SOURCE_PHONE: str = ""
    OPENAI_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""
    PUBLIC_API_URL: str = "http://localhost:8000"
    BOLNA_API_URL: str = "http://localhost:5001"
    BOLNA_WS_URL: str = "ws://localhost:5001"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    def model_post_init(self, __context: Any) -> None:
        if self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
            raise ValueError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set."
            )
        if self.LLM_PROVIDER == "pellet" and not (
            self.PELLET_API_KEY or self.OPENAI_API_KEY
        ):
            raise ValueError(
                "LLM_PROVIDER=pellet requires PELLET_API_KEY "
                "(or OPENAI_API_KEY as fallback)."
            )


settings = Settings()
