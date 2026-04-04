# Agent Studio — Technical Specification (MVP v2)

**Version:** 0.2  
**Date:** April 2026  
**Status:** Draft  

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                           │
│  Agent Wizard │ Conversation Viewer │ Dashboard │ Campaign Manager  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                     API LAYER (Next.js Route Handlers)              │
│  Agent CRUD │ Conversation API │ Action Executor │ Campaign API     │
│  Chatbot Public API (keyed)                                         │
└──────┬──────────┬──────────────┬──────────────┬─────────────────────┘
       │          │              │              │
  ┌────▼───┐ ┌───▼────┐  ┌─────▼─────┐  ┌────▼──────┐
  │Postgres│ │pgvector│  │ AWS S3    │  │ Redis     │
  │(Prisma)│ │(in PG) │  │ (Mumbai)  │  │ (BullMQ)  │
  └────────┘ └────────┘  └───────────┘  └───────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    CHANNEL GATEWAY LAYER                             │
│                                                                      │
│  ┌────────────┐  ┌───────────────────┐  ┌──────────────────┐       │
│  │  Voice      │  │   WhatsApp        │  │  Chatbot API     │       │
│  │  Exotel /   │  │   Provider        │  │  REST endpoints  │       │
│  │  Knowlarity │  │   Abstraction     │  │  (API key auth)  │       │
│  │  Webhooks   │  │   Layer           │  │                  │       │
│  └──────┬──────┘  └────────┬──────────┘  └────────┬─────────┘       │
│         │                  │                      │                  │
│         │    ┌─────────────┴──────────────┐       │                  │
│         │    │ Adapters:                  │       │                  │
│         │    │  - Meta Cloud API (direct) │       │                  │
│         │    │  - Gupshup                 │       │                  │
│         │    │  - Twilio                  │       │                  │
│         │    │  - Wati                    │       │                  │
│         │    │  - ValueFirst              │       │                  │
│         │    └────────────────────────────┘       │                  │
│         │                  │                      │                  │
│         └──────────────────┼──────────────────────┘                  │
│                            ▼                                         │
│              ┌───────────────────────┐                               │
│              │  CONVERSATION         │                               │
│              │  ORCHESTRATOR         │                               │
│              │  (State Machine       │                               │
│              │   + LLM Engine)       │                               │
│              └───────────┬───────────┘                               │
│                          │                                           │
│         ┌────────────────┼────────────────┐                          │
│         ▼                ▼                ▼                           │
│   ┌──────────┐    ┌───────────┐   ┌───────────┐                    │
│   │ Claude   │    │ Sarvam AI │   │ Sarvam AI │                    │
│   │ API      │    │ STT       │   │ TTS       │                    │
│   └──────────┘    └───────────┘   └───────────┘                    │
│                                                                      │
│   ┌──────────────────────────────┐                                  │
│   │  OUTBOUND DIALER             │                                  │
│   │  Campaign scheduler          │                                  │
│   │  Contact list manager        │                                  │
│   │  Call pacing engine          │                                  │
│   │  DND registry checker        │                                  │
│   └──────────────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Tech Stack (India-Optimized)

| Layer | Technology | Rationale |
|---|---|---|
| **Frontend** | Next.js 14+ (App Router), React, TypeScript | SSR + API in one repo |
| **UI** | shadcn/ui + Tailwind CSS | Fast iteration |
| **State Diagram Editor** | React Flow (@xyflow/react) | Drag-and-drop node editor |
| **Database** | PostgreSQL 16 + pgvector | Relational + vector in single DB |
| **ORM** | Prisma | Type-safe, migrations |
| **Cache / Queue** | Redis + BullMQ | Job queue for async work |
| **Object Storage** | AWS S3 (ap-south-1 Mumbai) | Low latency for Indian users |
| **Auth** | NextAuth.js | Google SSO for internal team |
| **LLM** | Anthropic Claude API (Sonnet) | Reasoning + vision + tool use |
| **Voice Telephony** | **Exotel** (primary) or Knowlarity | Indian telephony, cheaper than Twilio, easy Indian number provisioning, TRAI compliant, DND checking built-in |
| **STT** | **Sarvam AI** Saarika v2 | Best Hindi/Hinglish/Indian English accuracy, built for Indian languages, streaming support, much cheaper than Deepgram for Indian use |
| **TTS** | **Sarvam AI** Bulbul v2 | Natural Indian-accented voices (Hindi, English, regional), low latency, Indian pricing |
| **WhatsApp** | **Gupshup** (default) + provider abstraction layer | India's largest WhatsApp BSP, cheapest per-message rates, most customers already on Gupshup. Abstraction layer supports Meta direct, Twilio, Wati, ValueFirst |
| **SMS** | **MSG91** or Kaleyra | Indian SMS gateway, DLT registered |
| **Embeddings** | Voyage AI or OpenAI text-embedding-3-small | KB vectorization |
| **Doc Processing** | Claude Vision + pdf-parse | Indian ID verification |
| **Deployment** | Docker on AWS (ap-south-1) | Mumbai region, low latency |
| **Monitoring** | Sentry + PostHog | Errors + analytics |

### Why India-specific vendors?

| Vendor | vs. Global Alternative | Advantage |
|---|---|---|
| **Exotel** vs Twilio | 40-60% cheaper per-minute, Indian number provisioning in hours (not weeks), built-in DND check, TRAI compliant out of box, local support |
| **Sarvam AI** vs Deepgram/ElevenLabs | Purpose-built for Indian languages (Hindi, Tamil, Telugu, Kannada, Bengali, Marathi, Gujarati, Malayalam + Hinglish), significantly better accuracy on Indian accents, Indian pricing (₹ not $) |
| **Gupshup** vs Twilio WhatsApp | Cheapest WhatsApp rates in India, most Indian businesses already have Gupshup accounts, faster template approval, local support |
| **MSG91** vs Twilio SMS | DLT pre-registered, cheaper Indian SMS, better deliverability on Indian carriers |

---

## 3. Third-Party Dependencies

### 3.1 External Services (API Keys Required)

| Service | Purpose | Est. Monthly Cost (MVP) | Day 1? |
|---|---|---|---|
| **Anthropic Claude API** | LLM reasoning, vision, tool use | ₹15,000–40,000 ($180–480) | Yes |
| **Exotel** | Voice telephony (inbound + outbound) | ₹8,000–25,000 ($100–300) | Yes |
| **Sarvam AI** | STT (Saarika) + TTS (Bulbul) | ₹4,000–12,000 ($50–150) | Yes (voice) |
| **Gupshup** | WhatsApp Business API (default BSP) | ₹2,000–8,000 ($25–100) + per-msg | Yes (WhatsApp) |
| **Voyage AI / OpenAI** | Text embeddings | ₹800–2,500 ($10–30) | Yes |
| **AWS S3 (Mumbai)** | File storage | ₹400–1,600 ($5–20) | Yes |
| **AWS / Railway** | Hosting (compute) | ₹1,600–4,000 ($20–50) | Yes |
| **Neon / Supabase / RDS** | Managed Postgres + pgvector | ₹1,600–4,000 ($20–50) | Yes |
| **Upstash / ElastiCache** | Managed Redis | ₹800–2,500 ($10–30) | Yes |
| **MSG91** | SMS notifications | ₹500–2,000 ($6–25) | Optional |
| **Sentry** | Error monitoring | Free tier | Optional |
| **PostHog** | Product analytics | Free tier | Optional |

**Estimated total MVP infra: ₹30,000–80,000/month ($360–960)**

### 3.2 NPM Packages

```
# === Framework & Core ===
next                        # React meta-framework
react / react-dom           # UI
typescript                  # Type safety
prisma / @prisma/client     # ORM + migrations
zod                         # Runtime schema validation
pgvector                    # pgvector support for Prisma

# === UI ===
tailwindcss                 # Utility CSS
@radix-ui/*                 # Primitives (via shadcn/ui)
@xyflow/react               # State diagram visual editor (React Flow)
lucide-react                # Icons
react-hook-form             # Forms
@hookform/resolvers         # Zod resolver for react-hook-form
@tanstack/react-table       # Data tables (conversation list)
@tanstack/react-query       # Server state, polling
sonner                      # Toasts
cmdk                        # Command palette (optional, nice for search)
next-themes                 # Dark mode

# === Auth ===
next-auth                   # Authentication (Google SSO)

# === LLM & AI ===
@anthropic-ai/sdk           # Claude API client
openai                      # Embedding generation (if OpenAI embeddings)
                            # (or Voyage AI REST calls — no official SDK, use fetch)

# === Telephony ===
exotel                      # Exotel SDK (or REST API via fetch)
                            # Note: Exotel's Node SDK is limited;
                            # you'll likely wrap their REST API

# === WhatsApp (Provider Abstraction) ===
# No single SDK — each provider adapter uses fetch against their REST API:
#   - Gupshup: REST API (fetch)
#   - Meta Cloud API: REST API (fetch)  
#   - Twilio: twilio npm package
#   - Wati: REST API (fetch)
#   - ValueFirst: REST API (fetch)
twilio                      # Only if Twilio adapter needed

# === Speech (Sarvam AI) ===
# Sarvam AI has a REST API — use fetch, no npm package needed
# Fallback: @deepgram/sdk if Sarvam unavailable for a language

# === Document Processing ===
pdf-parse                   # PDF text extraction
mammoth                     # DOCX to text/HTML
sharp                       # Image resize/processing
csv-parse                   # CSV parsing
xlsx                        # Excel file parsing (for rate cards, product data)

# === Storage ===
@aws-sdk/client-s3          # S3 upload/download
@aws-sdk/s3-request-presigner  # Pre-signed URLs for media viewer

# === Queue & Background Jobs ===
bullmq                      # Job queue
ioredis                     # Redis client

# === State Machine ===
xstate                      # Conversation state machine runtime

# === Security ===
bcrypt                      # API key hashing
crypto (built-in)           # AES encryption for customer credentials
helmet                      # HTTP security headers
rate-limiter-flexible       # Rate limiting for public API + webhooks

# === Utilities ===
nanoid                      # Short ID generation
date-fns                    # Date utilities
date-fns-tz                 # Timezone handling (IST)
lodash                      # General utilities
pino                        # Structured logging
pino-pretty                 # Dev log formatting
libphonenumber-js           # Indian phone number parsing/validation
```

---

## 4. Database Schema

```sql
-- ============================================================
-- ORGANIZATION & USERS
-- ============================================================

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'builder', -- builder, viewer, admin
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- CUSTOMERS (businesses we build agents for)
-- ============================================================

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    name TEXT NOT NULL,
    contact_person TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    industry TEXT DEFAULT 'insurance',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- AGENTS
-- ============================================================

CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    customer_id UUID REFERENCES customers(id),
    name TEXT NOT NULL,
    persona_name TEXT,
    system_prompt TEXT NOT NULL,
    languages TEXT[] DEFAULT '{en}',
    tone TEXT DEFAULT 'conversational',
    status TEXT DEFAULT 'draft', -- draft, active, paused, archived
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- KNOWLEDGE BASE
-- ============================================================

-- Unstructured documents
CREATE TABLE kb_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_url TEXT NOT NULL,
    file_type TEXT NOT NULL,        -- pdf, docx, txt, csv, xlsx
    category TEXT,                  -- product_brochure, faq, policy_terms, claim_process
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'processing',
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE kb_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES kb_documents(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_kb_chunks_embedding ON kb_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Structured data sources (queried at runtime)
CREATE TABLE kb_structured_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,             -- "Product Catalog API", "Premium Rate Card"
    source_type TEXT NOT NULL,      -- api, database, static_json
    config JSONB NOT NULL,          -- connection details, query templates, field mappings
    description TEXT,               -- natural language description for LLM
    cache_ttl_seconds INTEGER DEFAULT 3600,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- ACTIONS
-- ============================================================

CREATE TABLE actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,      -- becomes tool description for Claude
    action_type TEXT NOT NULL,      -- db_update, link_generation, doc_fetch, api_call, notification
    config JSONB NOT NULL,          -- endpoint, method, headers, field mappings, template
    input_params JSONB NOT NULL,    -- { "param_name": { "type": "string", "description": "...", "required": true } }
    requires_confirmation BOOLEAN DEFAULT true,
    max_retries INTEGER DEFAULT 2,
    timeout_ms INTEGER DEFAULT 10000,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- STATE DIAGRAM
-- ============================================================

CREATE TABLE states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    instructions TEXT,              -- state-specific prompt additions
    is_start BOOLEAN DEFAULT false,
    is_terminal BOOLEAN DEFAULT false,
    max_turns INTEGER DEFAULT 10,
    position_x FLOAT,
    position_y FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    from_state_id UUID REFERENCES states(id) ON DELETE CASCADE,
    to_state_id UUID REFERENCES states(id) ON DELETE CASCADE,
    condition TEXT NOT NULL,        -- natural language condition
    action_id UUID REFERENCES actions(id) ON DELETE SET NULL,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- CHANNELS
-- ============================================================

CREATE TABLE channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL,     -- voice, whatsapp, chatbot
    config JSONB NOT NULL,          -- all channel-specific settings
    status TEXT DEFAULT 'inactive',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(agent_id, channel_type)
);

-- WhatsApp provider configs (separate because one customer might have multiple)
CREATE TABLE whatsapp_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id),
    provider_type TEXT NOT NULL,    -- gupshup, meta_cloud, twilio, wati, valuefirst
    phone_number TEXT NOT NULL,
    credentials BYTEA NOT NULL,     -- encrypted
    webhook_secret TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Chatbot API keys
CREATE TABLE chatbot_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id),
    key_hash TEXT NOT NULL,         -- bcrypt hash of the API key
    key_prefix TEXT NOT NULL,       -- first 8 chars for identification (e.g., "ask_live_")
    name TEXT,                      -- "Production Key", "Staging Key"
    rate_limit_per_minute INTEGER DEFAULT 60,
    allowed_ips TEXT[],             -- IP allowlist (empty = allow all)
    status TEXT DEFAULT 'active',   -- active, revoked
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- GUARDRAILS
-- ============================================================

CREATE TABLE guardrails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rule TEXT NOT NULL,
    category TEXT,                  -- compliance, pii, topic_boundary, safety, custom
    severity TEXT DEFAULT 'block',
    is_auto_generated BOOLEAN DEFAULT false,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- CUSTOMER API CREDENTIALS (encrypted vault)
-- ============================================================

CREATE TABLE api_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    credential_type TEXT NOT NULL,  -- api_key, oauth2, basic_auth, bearer
    credential_data BYTEA NOT NULL, -- AES-256 encrypted JSON
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- OUTBOUND CAMPAIGNS
-- ============================================================

CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'draft',    -- draft, scheduled, running, paused, completed, cancelled
    schedule_start TIMESTAMPTZ,
    schedule_end TIMESTAMPTZ,
    calling_hours_start TIME DEFAULT '09:00', -- IST
    calling_hours_end TIME DEFAULT '21:00',
    max_concurrent_calls INTEGER DEFAULT 5,
    calls_per_minute INTEGER DEFAULT 2,
    max_retry_attempts INTEGER DEFAULT 3,
    retry_gap_minutes INTEGER DEFAULT 60,
    check_dnd BOOLEAN DEFAULT true,
    total_contacts INTEGER DEFAULT 0,
    dialed_count INTEGER DEFAULT 0,
    connected_count INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE campaign_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    phone_number TEXT NOT NULL,
    name TEXT,
    metadata JSONB DEFAULT '{}',   -- any extra columns from CSV
    status TEXT DEFAULT 'pending',  -- pending, dnd_blocked, dialing, connected, completed, failed, retry
    attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    disposition TEXT,              -- sale, callback, not_interested, no_answer, busy, voicemail, dnd
    conversation_id UUID REFERENCES conversations(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_campaign_contacts_status ON campaign_contacts(campaign_id, status);

-- ============================================================
-- CONVERSATIONS
-- ============================================================

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    channel_type TEXT NOT NULL,
    channel_identifier TEXT,        -- phone number, WhatsApp number, session ID
    current_state_id UUID REFERENCES states(id),
    status TEXT DEFAULT 'active',   -- active, completed, escalated, dropped
    direction TEXT,                 -- inbound, outbound (for voice)
    outcome TEXT,
    metadata JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    message_count INTEGER DEFAULT 0
);

CREATE INDEX idx_conversations_agent ON conversations(agent_id, started_at DESC);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_channel ON conversations(channel_type, channel_identifier);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,             -- user, assistant, system
    content TEXT NOT NULL,
    media_url TEXT,
    media_type TEXT,               -- image, document, voice_note
    media_extracted_text TEXT,      -- OCR/STT result from media
    stt_confidence FLOAT,
    token_count INTEGER,
    state_id UUID REFERENCES states(id),
    latency_ms INTEGER,            -- time to generate response
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_fulltext ON messages USING gin(to_tsvector('english', content));

-- ============================================================
-- AUDIT LOGS
-- ============================================================

CREATE TABLE action_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    action_id UUID REFERENCES actions(id),
    input_payload JSONB,           -- PII-masked
    output_payload JSONB,
    status TEXT NOT NULL,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE guardrail_triggers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    guardrail_id UUID REFERENCES guardrails(id),
    message_id UUID REFERENCES messages(id),
    severity TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    from_state_id UUID REFERENCES states(id),
    to_state_id UUID REFERENCES states(id),
    trigger_message_id UUID REFERENCES messages(id),
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. Key System Flows

### 5.1 Conversation Orchestrator (Core Loop)

```
Incoming message (any channel)
    │
    ▼
Channel Adapter: normalize to { text, media[], sessionId, metadata }
    │
    ▼
Load conversation (by channel_identifier) or create new
    │
    ▼
If media attached:
    ├── Store original in S3 (Mumbai)
    ├── Queue media processing job (BullMQ):
    │   ├── Image → sharp (resize) → Claude Vision (classify + extract)
    │   ├── PDF → pdf-parse → Claude (extract structured data)
    │   └── Voice note → Sarvam STT (transcribe)
    └── Append extracted content to user message
    │
    ▼
Build LLM prompt:
    ├── System prompt (agent config)
    ├── Current state instructions
    ├── Guardrails (as system-level constraints)
    ├── KB context: vector search (top 5–8 chunks by cosine similarity)
    ├── Structured KB: if relevant, query structured sources and include results
    ├── Available actions (as Claude tool definitions)
    ├── Conversation history (last 20 messages; summarize older if > 20)
    └── User's latest message (with any media-extracted text)
    │
    ▼
Call Claude API (with tools enabled)
    │
    ├── If tool_use in response:
    │   ├── Check guardrails on action
    │   ├── If requires_confirmation → respond asking user to confirm
    │   ├── Execute action (API call / DB write / link gen / notification)
    │   ├── Log in action_executions table
    │   └── Feed result back to Claude for final response text
    │
    ▼
State transition check:
    ├── After response, evaluate transition conditions
    │   (lightweight Claude call: "Given this conversation, has the condition
    │    '[transition condition]' been met? Reply YES or NO.")
    ├── If YES → update current_state, log in state_transitions
    └── If terminal state → mark conversation completed
    │
    ▼
Guardrail post-check on final response:
    ├── PII scan (regex for Aadhaar pattern, PAN pattern, phone, email) → mask in logs
    ├── Compliance phrase check (IRDAI disclaimers if product was discussed)
    ├── Topic boundary check
    └── Log any triggers in guardrail_triggers
    │
    ▼
Store messages (user + assistant) in DB
    │
    ▼
Channel Adapter: format response for channel
    ├── Voice → Sarvam TTS → audio stream → Exotel
    ├── WhatsApp → format as text/interactive/media → send via provider API
    └── Chatbot → JSON response via REST API
```

### 5.2 Voice Inbound Flow

```
Inbound call → Exotel webhook → POST /api/channels/voice/incoming
    │
    ▼
Identify agent by called number (channel config lookup)
    │
    ▼
Create conversation (direction: inbound)
    │
    ▼
Exotel connects call to our media stream endpoint (WebSocket)
    │
    ▼
Bidirectional audio stream:
    ┌──────────────────────────────────────────────────┐
    │  User audio                                       │
    │    → Sarvam STT (streaming WebSocket)             │
    │    → transcript text                              │
    │    → Orchestrator                                 │
    │    → response text                                │
    │    → Sarvam TTS (streaming)                       │
    │    → audio bytes                                  │
    │    → back to Exotel stream                        │
    └──────────────────────────────────────────────────┘
    │
    ▼
On call end (Exotel status callback):
    → Close conversation
    → Store final transcript
    → Update metrics
```

### 5.3 Voice Outbound Flow (Campaign Dialer)

```
Campaign starts (scheduler picks up from BullMQ):
    │
    ▼
Dialer worker loop:
    ├── Check: within calling hours (IST)?
    ├── Check: campaign status == running?
    ├── Check: concurrent calls < max_concurrent?
    │
    ▼
Pick next pending contact:
    ├── Filter: status = 'pending' or 'retry' (if retry_gap elapsed)
    ├── If check_dnd → verify against DND list (Exotel DND API)
    ├── If DND → mark as dnd_blocked, skip
    │
    ▼
Initiate outbound call via Exotel API:
    ├── Set caller ID
    ├── Set status callback URL
    ├── Set media stream URL (same WebSocket handler as inbound)
    │
    ▼
Update contact status → 'dialing'
    │
    ▼
On connect → same bidirectional audio flow as inbound
On no-answer / busy / failed:
    ├── Update contact status
    ├── If attempts < max_retries → status = 'retry', schedule next attempt
    └── Else → status = 'failed'
    │
    ▼
On call end:
    ├── Agent or orchestrator sets disposition
    ├── Update campaign counters
    └── If all contacts processed → campaign status = 'completed'
```

### 5.4 WhatsApp Provider Abstraction

```typescript
// All WhatsApp providers implement this interface:

interface WhatsAppProvider {
  sendTextMessage(to: string, text: string): Promise<MessageResult>;
  sendInteractiveMessage(to: string, interactive: InteractiveMessage): Promise<MessageResult>;
  sendMediaMessage(to: string, mediaUrl: string, caption?: string): Promise<MessageResult>;
  sendTemplateMessage(to: string, templateId: string, params: Record<string, string>): Promise<MessageResult>;
  downloadMedia(mediaId: string): Promise<Buffer>;
  verifyWebhook(request: Request): boolean;  // signature validation
  parseIncomingMessage(body: any): NormalizedMessage;
}

// Provider factory:
function getWhatsAppProvider(providerConfig: WhatsAppProviderConfig): WhatsAppProvider {
  switch (providerConfig.provider_type) {
    case 'gupshup':    return new GupshupAdapter(providerConfig);
    case 'meta_cloud': return new MetaCloudAdapter(providerConfig);
    case 'twilio':     return new TwilioWhatsAppAdapter(providerConfig);
    case 'wati':       return new WatiAdapter(providerConfig);
    case 'valuefirst': return new ValueFirstAdapter(providerConfig);
  }
}
```

Each adapter normalizes incoming webhooks to a common format and translates outgoing messages to the provider's API format. Webhook URLs are per-agent: `/api/channels/whatsapp/{agentId}/webhook`.

### 5.5 Chatbot Public API

```
Customer integrates by calling our REST API:

POST /api/v1/chat/{agent_id}/sessions
  Headers: X-API-Key: ask_live_xxxxxxxx
  Response: { session_id: "sess_abc123" }

POST /api/v1/chat/{agent_id}/sessions/{session_id}/messages
  Headers: X-API-Key: ask_live_xxxxxxxx
  Body: { content: "I want to buy health insurance", media?: [{ type: "image", data: base64 }] }
  Response: {
    message_id: "msg_xyz",
    content: "I'd be happy to help! Could you tell me...",
    state: "need_discovery",
    interactive?: { type: "buttons", options: [...] }
  }

GET /api/v1/chat/{agent_id}/sessions/{session_id}
  Headers: X-API-Key: ask_live_xxxxxxxx
  Response: { messages: [...], state: "...", metadata: {...} }

DELETE /api/v1/chat/{agent_id}/sessions/{session_id}
  Headers: X-API-Key: ask_live_xxxxxxxx
  Response: { ended: true }
```

API key validation middleware:
- Hash incoming key with bcrypt, compare against chatbot_api_keys table
- Check rate limit (rate-limiter-flexible with Redis backend)
- Check IP allowlist if configured
- Auto-generate OpenAPI spec for customer documentation

### 5.6 Knowledge Base Ingestion

```
Upload → S3 → BullMQ job:
    │
    ├── PDF → pdf-parse (text)
    ├── DOCX → mammoth (text)
    ├── XLSX → xlsx package (parse sheets → text representation)
    ├── CSV/TXT → direct read
    │
    ▼
Chunk: recursive character splitter
    - ~500 tokens per chunk
    - 50 token overlap
    - Respect paragraph/section boundaries
    │
    ▼
Embed: batch call to Voyage/OpenAI (50 chunks per batch)
    │
    ▼
Store in kb_chunks with embedding vector
    │
    ▼
Update document status → 'ready'
```

For structured sources, no pre-ingestion — they're queried live:
```
At runtime (orchestrator):
    │
    ▼
Determine if structured source is relevant (based on user query + source description)
    │
    ▼
If relevant → execute query against source (API call or DB query)
    │
    ▼
Cache result in Redis (TTL from source config)
    │
    ▼
Include result in LLM context as structured data
```

### 5.7 Guardrail Auto-Generation

```
On completing wizard steps 1–5:
    │
    ▼
Call Claude with structured prompt:
    ├── Agent's system prompt
    ├── KB document categories + sample content
    ├── Action list with types and sensitivity
    ├── State diagram summary
    ├── Channel types
    ├── Industry: insurance (India)
    └── Instruction: "Generate guardrails as JSON array. Categories:
         compliance, pii, topic_boundary, safety, anti_misselling, custom.
         Include IRDAI-specific rules for Indian insurance."
    │
    ▼
Parse JSON response → create guardrail records
    │
    ▼
Present to user in Step 6 for review/edit
```

---

## 6. API Routes

```
# === Agent CRUD ===
POST   /api/agents                           Create agent
GET    /api/agents                           List agents (filterable by customer, status)
GET    /api/agents/:id                       Get agent detail
PUT    /api/agents/:id                       Update agent
DELETE /api/agents/:id                       Delete agent
POST   /api/agents/:id/publish               Activate agent

# === Knowledge Base ===
POST   /api/agents/:id/kb/documents          Upload document
GET    /api/agents/:id/kb/documents          List documents
DELETE /api/agents/:id/kb/documents/:docId   Remove document
GET    /api/agents/:id/kb/documents/:docId/chunks  Preview chunks
POST   /api/agents/:id/kb/structured         Add structured source
PUT    /api/agents/:id/kb/structured/:sid    Update structured source
POST   /api/agents/:id/kb/structured/:sid/test  Test structured source query

# === Actions ===
POST   /api/agents/:id/actions               Create action
PUT    /api/agents/:id/actions/:aid          Update action
DELETE /api/agents/:id/actions/:aid          Delete action
POST   /api/agents/:id/actions/:aid/test     Test action

# === State Diagram ===
PUT    /api/agents/:id/states                Save state diagram
GET    /api/agents/:id/states                Get state diagram

# === Channels ===
PUT    /api/agents/:id/channels/:type        Configure channel
GET    /api/agents/:id/channels              List channel configs

# === Guardrails ===
POST   /api/agents/:id/guardrails/generate   Auto-generate
PUT    /api/agents/:id/guardrails            Save guardrails
GET    /api/agents/:id/guardrails            List guardrails

# === Campaigns (Outbound Voice) ===
POST   /api/campaigns                        Create campaign
GET    /api/campaigns                        List campaigns
GET    /api/campaigns/:id                    Campaign detail + stats
PUT    /api/campaigns/:id                    Update campaign
POST   /api/campaigns/:id/contacts           Upload contact list (CSV)
POST   /api/campaigns/:id/start              Start campaign
POST   /api/campaigns/:id/pause              Pause
POST   /api/campaigns/:id/resume             Resume
POST   /api/campaigns/:id/stop               Stop

# === Conversations ===
GET    /api/conversations                    List (filterable)
GET    /api/conversations/:id                Detail + messages
GET    /api/conversations/:id/actions        Action executions
GET    /api/conversations/search?q=          Full-text search

# === Customers ===
POST   /api/customers                        Create customer
GET    /api/customers                        List
PUT    /api/customers/:id                    Update
POST   /api/customers/:id/credentials        Store API credential
POST   /api/customers/:id/whatsapp-providers Add WhatsApp provider config

# === Chatbot API Keys ===
POST   /api/agents/:id/api-keys              Generate API key
GET    /api/agents/:id/api-keys              List keys
DELETE /api/agents/:id/api-keys/:kid         Revoke key

# === Channel Webhooks ===
POST   /api/channels/voice/incoming           Exotel inbound webhook
POST   /api/channels/voice/status             Exotel status callback
WS     /api/channels/voice/stream             Media stream (WebSocket)
POST   /api/channels/whatsapp/:agentId/webhook  WhatsApp inbound (per-agent)

# === Public Chatbot API (separate auth) ===
POST   /api/v1/chat/:agentId/sessions                Create session
POST   /api/v1/chat/:agentId/sessions/:sid/messages   Send message
GET    /api/v1/chat/:agentId/sessions/:sid             Get session
DELETE /api/v1/chat/:agentId/sessions/:sid             End session

# === Dashboard ===
GET    /api/dashboard/:agentId/stats         Agent analytics
GET    /api/dashboard/overview               Org-wide overview
```

---

## 7. Project Structure

```
agent-studio/
├── prisma/
│   ├── schema.prisma
│   └── migrations/
├── src/
│   ├── app/
│   │   ├── (auth)/
│   │   │   └── login/page.tsx
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx                  # Sidebar nav
│   │   │   ├── page.tsx                    # Dashboard overview
│   │   │   ├── agents/
│   │   │   │   ├── page.tsx                # Agent list
│   │   │   │   ├── new/page.tsx            # Creation wizard
│   │   │   │   └── [id]/
│   │   │   │       ├── page.tsx            # Agent detail/edit
│   │   │   │       ├── conversations/page.tsx
│   │   │   │       └── api-keys/page.tsx
│   │   │   ├── campaigns/
│   │   │   │   ├── page.tsx                # Campaign list
│   │   │   │   ├── new/page.tsx            # Create campaign
│   │   │   │   └── [id]/page.tsx           # Campaign detail
│   │   │   ├── conversations/
│   │   │   │   ├── page.tsx                # Global conversation list
│   │   │   │   └── [id]/page.tsx           # Conversation detail
│   │   │   └── customers/
│   │   │       ├── page.tsx
│   │   │       └── [id]/page.tsx
│   │   └── api/
│   │       ├── agents/
│   │       ├── campaigns/
│   │       ├── conversations/
│   │       ├── customers/
│   │       ├── dashboard/
│   │       ├── channels/
│   │       │   ├── voice/
│   │       │   │   ├── incoming/route.ts
│   │       │   │   ├── status/route.ts
│   │       │   │   └── stream/route.ts     # WebSocket
│   │       │   └── whatsapp/
│   │       │       └── [agentId]/
│   │       │           └── webhook/route.ts
│   │       └── v1/                          # Public chatbot API
│   │           └── chat/
│   │               └── [agentId]/
│   │                   ├── sessions/route.ts
│   │                   └── sessions/[sessionId]/
│   │                       ├── messages/route.ts
│   │                       └── route.ts
│   ├── lib/
│   │   ├── orchestrator/
│   │   │   ├── engine.ts                   # Core conversation loop
│   │   │   ├── state-machine.ts            # XState-based state tracking
│   │   │   ├── guardrails.ts               # Pre/post response guardrail checks
│   │   │   └── prompt-builder.ts           # Assembles full LLM prompt
│   │   ├── llm/
│   │   │   ├── client.ts                   # Claude API wrapper
│   │   │   ├── tools.ts                    # Action → Claude tool definition mapper
│   │   │   └── embeddings.ts               # Embedding generation
│   │   ├── channels/
│   │   │   ├── types.ts                    # Shared channel interfaces
│   │   │   ├── voice/
│   │   │   │   ├── exotel.ts               # Exotel API integration
│   │   │   │   ├── stt.ts                  # Sarvam STT streaming client
│   │   │   │   └── tts.ts                  # Sarvam TTS streaming client
│   │   │   ├── whatsapp/
│   │   │   │   ├── provider.interface.ts   # WhatsAppProvider interface
│   │   │   │   ├── factory.ts              # Provider factory
│   │   │   │   ├── adapters/
│   │   │   │   │   ├── gupshup.ts
│   │   │   │   │   ├── meta-cloud.ts
│   │   │   │   │   ├── twilio.ts
│   │   │   │   │   ├── wati.ts
│   │   │   │   │   └── valuefirst.ts
│   │   │   │   └── message-formatter.ts    # Normalize in/out messages
│   │   │   └── chatbot/
│   │   │       ├── auth.ts                 # API key validation middleware
│   │   │       └── handler.ts              # Request → Orchestrator → Response
│   │   ├── knowledge/
│   │   │   ├── ingest.ts                   # Document parsing + chunking
│   │   │   ├── retrieval.ts                # Vector similarity search
│   │   │   └── structured.ts               # Runtime structured source queries
│   │   ├── media/
│   │   │   ├── processor.ts                # Image/doc/voice processing pipeline
│   │   │   ├── document-classifier.ts      # Indian ID classification via Claude Vision
│   │   │   └── storage.ts                  # S3 upload/download/presign
│   │   ├── actions/
│   │   │   └── executor.ts                 # Execute actions, retry, log
│   │   ├── campaigns/
│   │   │   ├── dialer.ts                   # Outbound call pacing engine
│   │   │   ├── scheduler.ts                # Campaign schedule management
│   │   │   └── dnd-checker.ts              # TRAI DND registry check
│   │   ├── auth/
│   │   │   └── config.ts                   # NextAuth config
│   │   ├── security/
│   │   │   ├── encryption.ts               # AES-256 for credential vault
│   │   │   ├── pii-masker.ts               # Aadhaar, PAN, phone masking
│   │   │   └── rate-limiter.ts             # Rate limiting setup
│   │   └── db/
│   │       └── client.ts                   # Prisma singleton
│   ├── components/
│   │   ├── agent-wizard/
│   │   │   ├── wizard-shell.tsx            # Step navigation
│   │   │   ├── step-identity.tsx
│   │   │   ├── step-knowledge-base.tsx
│   │   │   ├── step-actions.tsx
│   │   │   ├── step-state-diagram.tsx
│   │   │   ├── step-channels.tsx
│   │   │   └── step-guardrails.tsx
│   │   ├── state-editor/
│   │   │   └── flow-editor.tsx             # React Flow diagram editor
│   │   ├── conversations/
│   │   │   ├── conversation-list.tsx
│   │   │   ├── conversation-detail.tsx
│   │   │   └── message-thread.tsx
│   │   ├── campaigns/
│   │   │   ├── campaign-dashboard.tsx
│   │   │   └── contact-upload.tsx
│   │   └── ui/                             # shadcn components
│   ├── workers/
│   │   ├── kb-processor.worker.ts          # Document ingestion jobs
│   │   ├── media-processor.worker.ts       # Media processing jobs
│   │   └── campaign-dialer.worker.ts       # Outbound campaign worker
│   └── types/
│       ├── agent.ts
│       ├── conversation.ts
│       ├── channel.ts
│       └── campaign.ts
├── docs/
│   └── chatbot-api.yaml                    # OpenAPI spec for public API
├── docker-compose.yml                      # Postgres + Redis + app
├── Dockerfile
├── .env.example
├── package.json
└── tsconfig.json
```

---

## 8. Environment Variables

```bash
# === Database ===
DATABASE_URL=postgresql://user:pass@host:5432/agent_studio

# === Redis ===
REDIS_URL=redis://host:6379

# === Auth ===
NEXTAUTH_SECRET=...
NEXTAUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# === Anthropic ===
ANTHROPIC_API_KEY=sk-ant-...

# === Embeddings ===
VOYAGE_API_KEY=...
# or OPENAI_API_KEY=sk-...

# === Exotel (Voice) ===
EXOTEL_API_KEY=...
EXOTEL_API_TOKEN=...
EXOTEL_SID=...
EXOTEL_SUBDOMAIN=...             # e.g., yourcompany.exotel.com

# === Sarvam AI (STT + TTS) ===
SARVAM_API_KEY=...

# === Gupshup (Default WhatsApp) ===
GUPSHUP_API_KEY=...
GUPSHUP_APP_NAME=...

# === MSG91 (SMS) ===
MSG91_AUTH_KEY=...
MSG91_SENDER_ID=...

# === AWS S3 ===
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=agent-studio-media

# === Security ===
CREDENTIAL_ENCRYPTION_KEY=...     # 32-byte hex for AES-256

# === App ===
APP_URL=https://studio.yourcompany.com
NODE_ENV=production
```

---

## 9. Implementation Notes

### 9.1 Voice Latency Budget (Target: < 1.5s)

```
User stops speaking
  → Sarvam STT endpointing (VAD)     ~200ms
  → Final transcript delivery          ~100ms
  → Claude API call                    ~500-800ms
  → Sarvam TTS first byte             ~200ms
  → Audio playback starts             ~100ms
                              Total:   ~1100-1400ms ✓
```

Optimizations:
- Streaming STT (don't wait for full utterance)
- Sarvam STT endpoint detection (configurable silence threshold)
- Keep-alive connections to Claude API
- Streaming TTS (play first chunk while rest generates)
- Pre-cache common phrases ("Let me look that up for you")

### 9.2 Exotel Integration Notes

Exotel works differently from Twilio:
- Uses "ExoPhone" virtual numbers for India
- Outbound calls via `POST /v1/Accounts/{sid}/Calls/connect`
- Inbound configured via "App" in Exotel dashboard → webhook URL
- Media streaming via Exotel's streaming API (WebSocket)
- DND check: `GET /v1/Accounts/{sid}/CustomerWhitelist` or use their DND API
- Call recording: built-in, optional (we skip for MVP, use STT transcript)
- Supports DTMF collection
- Rate limits: check account tier

**If Exotel's streaming API is too limited** (check their latest docs), fallback option:
- Use Exotel for call management + Knowlarity/Ozonetel for media streaming
- Or use Plivo (has good India support and Twilio-like streaming API)

### 9.3 Sarvam AI Integration Notes

```
# STT (Saarika v2)
POST https://api.sarvam.ai/speech-to-text-translate
  - Supports: Hindi, English, Tamil, Telugu, Kannada, Bengali, Marathi,
              Gujarati, Malayalam, Odia, Punjabi, Hinglish
  - Streaming: WebSocket endpoint for real-time transcription
  - Returns: transcript + confidence + detected language

# TTS (Bulbul v2)
POST https://api.sarvam.ai/text-to-speech
  - Voices: multiple Indian-accented male/female voices per language
  - Streaming: supports chunked audio response
  - Output: PCM/WAV/MP3
  - SSML support for pauses, emphasis
```

### 9.4 WhatsApp 24-Hour Window Handling

WhatsApp Business API has a 24-hour session window:
- Within 24h of last user message: send any message (session message)
- Outside 24h: only pre-approved template messages

Our handling:
- Track `last_user_message_at` per WhatsApp conversation
- If > 24h and agent needs to follow up → use template message (customer must pre-approve templates with Meta)
- Template messages stored per WhatsApp provider config
- Surface warning in conversation viewer if session expired

### 9.5 Chatbot API Design Decisions

- Synchronous request-response (no streaming for MVP — keeps integration simple)
- Session-based: customer creates session, sends messages, gets responses
- Stateless from customer's perspective — all state managed server-side
- Media: customer sends base64 in request body (up to 5MB per request)
- Rate limiting: per API key, configurable (default 60 req/min)
- Response includes: message content, current state name, interactive elements (buttons/lists) if applicable
- OpenAPI spec auto-generated so customers can generate their own client SDKs

### 9.6 Security

- Customer API credentials: AES-256-GCM encrypted at rest, decrypted only at action execution time
- Chatbot API keys: bcrypt-hashed in DB, only shown once on creation
- PII masking: Aadhaar (XXXX-XXXX-1234), PAN (XXXXX1234X), phone (+91XXXXX67890) in all logs and action payloads
- Webhook signature validation for Exotel and all WhatsApp providers
- Rate limiting on all public endpoints
- IP allowlisting option for chatbot API
- Media files: pre-signed S3 URLs with 1h expiry
- All external calls logged in action_executions

### 9.7 State Machine: Soft Guidance, Not Hard Control

The state diagram is advisory — the LLM uses it for context, not as a rigid FSM:

```typescript
// In prompt-builder.ts:
function buildStateContext(currentState: State, transitions: Transition[]) {
  return `
    You are currently in the "${currentState.name}" phase.
    ${currentState.instructions}

    You should move to the next phase when:
    ${transitions.map(t =>
      `- "${t.condition}" → move to "${t.toState.name}"${t.action ? ` and trigger "${t.action.name}"` : ''}`
    ).join('\n')}

    Stay in the current phase if none of these conditions are clearly met.
  `;
}
```

After each response, a lightweight check determines transitions:
```typescript
// Quick classifier call (low token usage)
const transitionCheck = await claude.messages.create({
  model: 'claude-sonnet-4-20250514',
  max_tokens: 50,
  messages: [{
    role: 'user',
    content: `Given this conversation summary: "${lastFewMessages}"
              Has this condition been met: "${transition.condition}"?
              Reply only YES or NO.`
  }]
});
```

---

## 10. Development Phases

| Phase | Scope | Est. Duration |
|---|---|---|
| **Phase 0** | Project setup: Next.js scaffold, Prisma schema, Docker compose, auth, basic UI shell | 3-4 days |
| **Phase 1** | Agent CRUD + system prompt + KB upload + basic orchestrator (chatbot API only) | 2-3 weeks |
| **Phase 2** | State diagram editor (React Flow) + actions framework + guardrails auto-gen | 2 weeks |
| **Phase 3** | WhatsApp channel: Gupshup adapter + provider abstraction + media processing | 1.5-2 weeks |
| **Phase 4** | Voice inbound: Exotel + Sarvam STT/TTS integration | 2 weeks |
| **Phase 5** | Voice outbound: campaign manager + dialer worker + DND check | 1.5-2 weeks |
| **Phase 6** | Conversation viewer + dashboard + customer registry | 1.5-2 weeks |
| **Phase 7** | Polish, testing, security hardening, docs | 1 week |

**Total: 10-14 weeks** with 2-3 engineers.

Recommended priority if you need to ship faster:
1. Chatbot API (fastest to test, no telephony complexity)
2. WhatsApp (highest business value for Indian insurance)
3. Voice inbound
4. Voice outbound (most complex)

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Exotel media streaming API limitations | May not support real-time bidirectional audio well | Evaluate early in Phase 4; fallback to Plivo or Ozonetel if needed |
| Sarvam STT accuracy on noisy calls | Poor voice UX | Test with real Indian call recordings early; have Deepgram as fallback |
| Hindi/Hinglish Claude performance | Incorrect responses in Hindi conversations | Test extensively; consider prompt engineering for code-switching scenarios |
| WhatsApp BSP variability | Different BSPs have different API quirks | Build robust adapter pattern; test each adapter independently |
| Customer API instability | Failed actions during live conversations | Retry + timeout + graceful degradation ("Let me note that down and our team will follow up") |
| PII handling compliance | Legal risk under Indian data protection laws (DPDP Act) | PII masking pipeline, encryption at rest, configurable retention, consent flows |
| Outbound calling regulations (TRAI) | Fines for calling DND numbers | Mandatory DND check before every outbound call, maintain audit trail |
| Voice latency in India | Network conditions can add latency | Use Mumbai-region everything; optimize for < 1.5s; have fallback "thinking" phrases |
