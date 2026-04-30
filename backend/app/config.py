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
    PLIVO_AUTH_ID: str = ""
    PLIVO_AUTH_TOKEN: str = ""
    PLIVO_APPLICATION_ID: str = ""
    # Log-only first; flip to True after demo confirms signatures work behind ngrok.
    PLIVO_VERIFY_SIGNATURES: bool = False
    GUPSHUP_API_KEY: str = ""
    GUPSHUP_APP_NAME: str = ""
    GUPSHUP_SOURCE_PHONE: str = ""
    OPENAI_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""
    PUBLIC_API_URL: str = "http://localhost:8000"
    # Plivo dials this URL for the bidirectional audio WebSocket. If unset,
    # auto-derived from PUBLIC_API_URL via the public_ws_url property.
    PUBLIC_WS_URL: str = ""
    BOLNA_API_URL: str = "http://localhost:5001"
    BOLNA_WS_URL: str = "ws://localhost:5001"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @property
    def public_ws_url(self) -> str:
        """Public WebSocket URL Plivo uses to reach our backend.

        Defaults to PUBLIC_API_URL with the scheme rewritten (https→wss, http→ws).
        Override via PUBLIC_WS_URL env var if backend is fronted by a different
        host for WebSocket traffic.
        """
        if self.PUBLIC_WS_URL:
            return self.PUBLIC_WS_URL
        return (
            self.PUBLIC_API_URL
            .replace("https://", "wss://", 1)
            .replace("http://", "ws://", 1)
        )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        # Tolerate stale env vars (e.g. EXOTEL_* left over from the Plivo
        # migration). Operators get a clean cutover; they can prune later.
        "extra": "ignore",
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
