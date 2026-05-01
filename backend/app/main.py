import logging
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.router import v1_router
from app.observability import init_tracing

# Configure app loggers — uvicorn overrides basicConfig, so set explicitly
_log_handler = logging.StreamHandler(sys.stderr)
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("app").addHandler(_log_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown events."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Agent Studio API",
    version="0.1.0",
    description="Internal platform for creating, configuring, and deploying AI-powered sales agents across voice, WhatsApp, and chatbot channels for Indian insurance companies.",
    lifespan=lifespan,
)

# Tracing must be initialised after `app` is created (FastAPI auto-instrumentation
# attaches middleware to it) but before any requests are served.
init_tracing(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
