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
    # Honeycomb tracing. Empty key disables tracing entirely (no-op).
    HONEYCOMB_API_KEY: str = ""
    OTEL_SERVICE_NAME: str = "agent-studio-backend"

    # Postgres connection components — Agno's AsyncPostgresDb wants a
    # SQLAlchemy-style URL via async_pg_url (psycopg3 async). Discrete fields
    # also let other consumers (mem0 historically, future migrations) build
    # their own connections. Defaults match docker-compose's local Postgres.
    PG_HOST: str = "localhost"
    PG_PORT: int = 5432
    PG_USER: str = "postgres"
    PG_PASSWORD: str = "postgres"
    PG_DATABASE: str = "agent_studio"

    # Phone normalization region default — Indian numbers without a country
    # code parse correctly when this is "IN".
    DEFAULT_PHONE_REGION: str = "IN"

    # Memory layer (Agno).
    # MEMORY_LLM_PROVIDER drives the extraction LLM. Pellet is the dev default
    # (free via mentor's gateway); production targets Anthropic Haiku 4.5
    # for stronger instruction-following on the prompt-injection defense.
    MEMORY_LLM_PROVIDER: Literal["pellet", "anthropic"] = "pellet"
    ANTHROPIC_MEMORY_MODEL: str = "claude-haiku-4-5-20251001"
    # Idle threshold for the WhatsApp/chatbot sweep Celery task. Default 10
    # min. Dev override to 1 min for fast verification; production has a
    # 5-min floor below — see effective_idle_threshold_minutes.
    MEMORY_IDLE_THRESHOLD_MINUTES: int = 10
    # Bounded retry counter on memory extraction. A row exceeding this cap
    # is excluded from the partial index → sweep stops retrying. Operator
    # path to reset via ~/agent-studio-scratch/reset_memory_attempts.py.
    MEMORY_MAX_EXTRACTION_ATTEMPTS: int = 5

    # Environment marker — drives the production floor on idle-threshold.
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Dev-only SIP → phone alias. Lets a Plivo SIP softphone test caller
    # unify EndUser identity with their WhatsApp/chatbot phone number
    # without needing a real PSTN DID (which requires Indian DLT/KYC).
    # ALWAYS empty in production: real PSTN inbound calls present a
    # phone-formatted From natively, so EndUser unification works
    # automatically.
    DEV_SIP_ALIAS_URI: str = ""
    DEV_SIP_ALIAS_PHONE: str = ""

    @property
    def dev_sip_phone_aliases(self) -> dict[str, str]:
        """Empty in production. Wired only when both DEV_SIP_ALIAS_* are set."""
        if self.DEV_SIP_ALIAS_URI and self.DEV_SIP_ALIAS_PHONE:
            return {self.DEV_SIP_ALIAS_URI.strip(): self.DEV_SIP_ALIAS_PHONE.strip()}
        return {}

    @property
    def async_pg_url(self) -> str:
        """SQLAlchemy URL for Agno's AsyncPostgresDb (psycopg3 async).

        Distinct from DATABASE_URL (which uses asyncpg for our app). Agno
        manages its own engine; we don't share pools.
        """
        return (
            f"postgresql+psycopg_async://{self.PG_USER}:{self.PG_PASSWORD}"
            f"@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DATABASE}"
        )

    @property
    def effective_idle_threshold_minutes(self) -> int:
        """Idle threshold honoring a 5-min floor in production.

        Protects against a leaked dev override (MEMORY_IDLE_THRESHOLD_MINUTES=1
        would close every WA conversation within a minute of silence).
        """
        if self.ENVIRONMENT == "production":
            return max(self.MEMORY_IDLE_THRESHOLD_MINUTES, 5)
        return self.MEMORY_IDLE_THRESHOLD_MINUTES

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
