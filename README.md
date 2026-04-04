# Agent Studio

AI-powered sales agent platform for Indian insurance companies. Create, configure, and deploy conversational agents across Voice, WhatsApp, and Chatbot channels.

## Architecture

```
Frontend (Next.js)          Backend (FastAPI)
 Dashboard                   Conversation Orchestrator
 Agent Wizard                 ├── Claude API (LLM reasoning)
 Conversation Viewer          ├── KB Vector Search (pgvector)
 ───────────────────          ├── Action Executor
       │                      ├── Guardrail Service (PII, compliance)
       │  /api/v1/*           └── State Machine
       └──────────────────►
                              Channel Gateway
                               ├── Chatbot REST API
                               ├── WhatsApp (Gupshup)
                               └── Voice (Exotel + Sarvam AI)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React, TypeScript, Tailwind CSS, shadcn/ui |
| State Diagram Editor | React Flow (@xyflow/react) |
| Charts | Recharts |
| Auth | NextAuth.js v5 (Google SSO) |
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 16 + pgvector |
| Cache/Queue | Redis + Celery |
| Object Storage | MinIO (S3-compatible) |
| LLM | Anthropic Claude (Sonnet) |
| Embeddings | Voyage AI (voyage-3, 1024 dims) |
| Voice | Exotel (telephony) + Sarvam AI (STT/TTS) |
| WhatsApp | Gupshup BSP |

## Prerequisites

- Node.js 18+
- Python 3.12+
- Docker & Docker Compose

## Local Setup

### 1. Clone and install frontend dependencies

```bash
git clone <repo-url> agent-studio
cd agent-studio
npm install
```

### 2. Start infrastructure (Postgres + Redis + MinIO)

```bash
cd backend
docker compose up -d postgres redis minio minio-init
```

This starts:
- **PostgreSQL 16** with pgvector at `localhost:5432`
- **Redis 7** at `localhost:6379`
- **MinIO** (S3-compatible storage) at `localhost:9000` (console at `localhost:9001`)

### 3. Set up Python backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure environment variables

**Frontend** — create `agent-studio/.env.local`:
```bash
cp .env.example .env.local
```

Fill in:
```env
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
AUTH_SECRET=<generate with: npx auth secret>
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Backend** — create `backend/.env`:
```bash
cd backend
cp .env.example .env
```

Fill in (minimum for chatbot channel):
```env
ANTHROPIC_API_KEY=sk-ant-...      # Required — Claude API
VOYAGE_API_KEY=pa-...              # Required — KB embeddings
AUTH_SECRET=<same value as frontend>
```

Optional (for WhatsApp/Voice):
```env
GUPSHUP_API_KEY=...               # WhatsApp via Gupshup
GUPSHUP_APP_NAME=...
GUPSHUP_SOURCE_PHONE=...
EXOTEL_API_KEY=...                 # Voice via Exotel
EXOTEL_API_TOKEN=...
EXOTEL_SID=...
EXOTEL_SUBDOMAIN=...
SARVAM_API_KEY=...                 # STT/TTS via Sarvam AI
```

### 5. Run database migrations

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

### 6. Set up Google OAuth (for login)

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create an OAuth 2.0 Client ID (Web application)
3. Add authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
4. Copy Client ID and Secret to `.env.local`

### 7. Start the application

Open 3 terminals:

```bash
# Terminal 1: Backend API
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2: Celery worker (background jobs)
cd backend && source venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info

# Terminal 3: Frontend
npm run dev
```

### 8. Access the app

- **Frontend**: http://localhost:3000
- **Backend API docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (login: minioadmin/minioadmin)

## Project Structure

```
agent-studio/
├── src/                          # Next.js frontend
│   ├── app/
│   │   ├── (dashboard)/          # Protected pages
│   │   │   ├── page.tsx          # Dashboard
│   │   │   ├── agents/           # Agent list, detail, wizard
│   │   │   └── conversations/    # Conversation list, detail
│   │   ├── login/                # Login page
│   │   └── api/auth/             # NextAuth routes
│   ├── components/
│   │   ├── agent-wizard/         # 6-step creation wizard
│   │   ├── app-sidebar.tsx       # Navigation sidebar
│   │   └── ui/                   # shadcn components
│   └── lib/
│       ├── api.ts                # Backend API client
│       ├── auth.ts               # NextAuth config
│       └── utils.ts
├── backend/                      # FastAPI backend
│   ├── app/
│   │   ├── main.py               # FastAPI app
│   │   ├── config.py             # Settings (pydantic-settings)
│   │   ├── database.py           # SQLAlchemy async engine
│   │   ├── models/               # 17 SQLAlchemy models
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── api/v1/               # 36 API endpoints across 10 routers
│   │   ├── services/
│   │   │   ├── orchestrator.py   # Core conversation loop
│   │   │   ├── llm_client.py     # Claude API wrapper
│   │   │   ├── prompt_builder.py # System prompt assembler
│   │   │   ├── knowledge_base_service.py
│   │   │   ├── embeddings.py     # Voyage AI embeddings
│   │   │   ├── action_executor.py
│   │   │   ├── guardrail_service.py
│   │   │   ├── state_machine.py
│   │   │   ├── storage.py        # S3/MinIO file storage
│   │   │   ├── channels/
│   │   │   │   ├── whatsapp/     # Gupshup adapter
│   │   │   │   └── voice/        # Exotel + Sarvam STT/TTS
│   │   │   └── ...
│   │   └── workers/              # Celery background tasks
│   ├── alembic/                  # Database migrations
│   ├── docker-compose.yml        # Postgres + Redis + MinIO
│   ├── Dockerfile
│   └── requirements.txt
└── package.json
```

## API Overview

All backend endpoints at `/api/v1/`. Full interactive docs at `/docs`.

| Area | Endpoints | Description |
|------|-----------|-------------|
| Agents | 6 | CRUD + publish |
| Knowledge Base | 5 | Doc upload, structured sources |
| Actions | 4 | Agent action CRUD |
| State Diagram | 2 | Save/load state machine |
| Channels | 2 | Configure voice/WhatsApp/chatbot |
| Guardrails | 3 | List, bulk update, auto-generate |
| Conversations | 3 | List, search, detail |
| Dashboard | 2 | Org overview, agent stats |
| Chatbot API | 4 | Public REST API for customers |
| Webhooks | 5 | WhatsApp + Voice inbound |

## Troubleshooting

**"Cannot connect to database"** — Make sure Postgres is running: `docker compose up -d postgres`

**"Migration failed"** — Make sure the pgvector extension is available. The `pgvector/pgvector:pg16` Docker image includes it.

**"CORS error"** — The Next.js dev server proxies `/api/v1/*` to the backend via rewrites in `next.config.ts`. Make sure the backend is running on port 8000.

**"Google login not working"** — Verify redirect URI in Google Cloud Console matches `http://localhost:3000/api/auth/callback/google`. Make sure `AUTH_SECRET` is set.
