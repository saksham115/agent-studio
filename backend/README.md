# Agent Studio Backend

FastAPI backend for Agent Studio -- an internal platform for creating, configuring, and deploying AI-powered sales agents across voice, WhatsApp, and chatbot channels for Indian insurance companies.

## Prerequisites

- Python 3.12+
- PostgreSQL 16 with pgvector extension
- Redis 7+

## Quick Start

### Using Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env with your actual credentials
docker compose up -d
```

The API will be available at http://localhost:8000. Interactive docs at http://localhost:8000/docs.

### Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your actual credentials and local DB URL
uvicorn app.main:app --reload
```

## Database Migrations

```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, lifespan
│   ├── config.py            # Settings via pydantic-settings
│   ├── database.py          # SQLAlchemy async engine + session
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── api/                 # Route handlers
│   │   ├── deps.py          # Dependency injection
│   │   └── v1/              # API v1 routes
│   └── services/            # Business logic
├── alembic/                 # Database migrations
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## API Endpoints

All endpoints are prefixed with `/api/v1`.

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /agents | Create agent |
| GET | /agents | List agents |
| GET | /agents/:id | Get agent |
| PUT | /agents/:id | Update agent |
| DELETE | /agents/:id | Delete agent |
| POST | /agents/:id/publish | Publish agent |
| POST | /agents/:id/kb/documents | Upload KB document |
| GET | /agents/:id/kb/documents | List KB documents |
| DELETE | /agents/:id/kb/documents/:doc_id | Delete KB document |
| POST | /agents/:id/kb/structured | Add structured source |
| PUT | /agents/:id/kb/structured/:source_id | Update structured source |
| POST | /agents/:id/actions | Create action |
| GET | /agents/:id/actions | List actions |
| PUT | /agents/:id/actions/:action_id | Update action |
| DELETE | /agents/:id/actions/:action_id | Delete action |
| PUT | /agents/:id/states | Save state diagram |
| GET | /agents/:id/states | Load state diagram |
| PUT | /agents/:id/channels/:type | Configure channel |
| GET | /agents/:id/channels | List channels |
| POST | /agents/:id/guardrails/generate | Auto-generate guardrails |
| PUT | /agents/:id/guardrails | Update guardrails |
| GET | /agents/:id/guardrails | List guardrails |
| GET | /conversations | List conversations |
| GET | /conversations/search | Search conversations |
| GET | /conversations/:id | Get conversation detail |
| GET | /dashboard/overview | Dashboard stats |
| GET | /dashboard/:id/stats | Agent stats |
