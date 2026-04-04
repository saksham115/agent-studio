from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agent_studio"
    REDIS_URL: str = "redis://localhost:6379/0"
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    AUTH_SECRET: str = "change-me-in-production"
    AWS_S3_BUCKET: str = "agent-studio-uploads"
    AWS_REGION: str = "ap-south-1"
    SARVAM_API_KEY: str = ""
    EXOTEL_API_KEY: str = ""
    GUPSHUP_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
