# Agent Studio — Product Specification (MVP v2)

**Version:** 0.2  
**Date:** April 2026  
**Status:** Draft  

---

## 1. Overview

Agent Studio is an internal platform for creating, configuring, and deploying AI-powered sales agents across voice (inbound + outbound), WhatsApp, and chatbot (API-based) channels. The primary use case is insurance sales in the Indian market — agents follow a configurable sales lifecycle, access product knowledge bases, and perform actions (database updates, link generation, document retrieval) on behalf of the business.

The platform is initially for internal use. Customers provide their own WhatsApp Business API / BSP credentials and limited APIs for integration. The chatbot channel is exposed as authenticated API endpoints that customers integrate into their own systems.

---

## 2. Users & Personas

| Persona | Description | MVP Access |
|---|---|---|
| **Agent Builder** | Internal team member who creates and configures agents | Full access |
| **Operations/QA** | Reviews conversations, monitors agent performance | Read-only + conversation viewer |
| **End Customer (Prospect)** | Interacts with the deployed agent via voice/WhatsApp/chat | No portal access |
| **Customer (Business)** | Insurance company we're building agents for — provides APIs, WhatsApp credentials, phone numbers | No portal access (we configure on their behalf) |

**MVP assumption:** 5–15 internal users. No external login.

---

## 3. Core Features

### 3.1 Agent Creation Wizard

A step-by-step flow to configure a new agent.

#### Step 1: Identity & System Prompt

**Inputs from user:**
- Agent name (internal label)
- Agent persona name (what the agent calls itself)
- Customer/client this agent belongs to (dropdown — we maintain a customer registry)
- System prompt (free-text, with guidance/templates for insurance sales)
- Language(s) supported (English, Hindi, Hinglish, regional — multi-language is common in India)
- Tone/style selector (formal, conversational, consultative)

**System behavior:**
- Provide starter templates for Indian insurance scenarios (health, motor, life, term, ULIP)
- Include IRDAI compliance snippets as insertable blocks
- Validate prompt length and flag common anti-patterns

#### Step 2: Knowledge Base

**Inputs from user:**

**Unstructured sources:**
- Upload documents (PDF, DOCX, XLSX, TXT, CSV)
- Paste raw text / URLs
- Tag/categorize documents (e.g., "product brochure", "FAQ", "policy terms", "claim process")
- Set retrieval priority

**Structured sources:**
- Database connection: connection string or API endpoint to query structured product data (plan tables, premium calculators, coverage matrices)
- API-based knowledge: REST endpoint that returns structured data given a query (e.g., customer's product catalog API)
- Manual structured data: JSON/CSV upload of structured records (product comparisons, rate cards)

**System behavior:**
- Parse and chunk unstructured documents, generate embeddings, store in vector DB
- For structured sources: store connection config, query at runtime (not pre-embedded)
- Show chunk preview so user can verify quality
- Allow re-upload and version tracking

#### Step 3: Actions

**Inputs from user:**
- Action name + description (in natural language — this becomes the tool description for the LLM)
- Action type:
  - **Database update** — target table/entity, fields to update, validation rules
  - **Link generation** — URL template + parameters (e.g., payment link via Razorpay, proposal link, policy PDF)
  - **Document fetch** — source system, document type, lookup key (e.g., fetch policy document by policy number)
  - **API call (customer-provided)** — endpoint URL, method, headers, auth config (API key / OAuth / basic), request/response field mapping
  - **Notification trigger** — send SMS (via MSG91/Kaleyra), email, or WhatsApp template message
- Input parameters the agent needs to collect before triggering
- Confirmation behavior (ask user to confirm before executing, or auto-execute)
- Retry config (max retries, timeout)

**System behavior:**
- Validate API endpoints on save (test call with sample payload)
- Log every action execution with input/output for audit
- Support basic retry logic for failed calls
- PII masking in logs

#### Step 4: State Diagram (Sales Lifecycle)

**Inputs from user:**
- Define states (e.g., "Greeting", "Need Discovery", "Product Pitch", "Objection Handling", "Quote Generation", "Document Collection", "Closure", "Follow-up")
- Define transitions between states (natural language conditions)
- Link actions to states (e.g., "Quote Generation" triggers the link-generation action)
- Define exit conditions (success, drop-off, escalation to human)
- Set max turns per state (prevent infinite loops)
- Optional: per-state prompt overrides (additional instructions active only in that state)

**System behavior:**
- Visual state diagram editor (drag-and-drop nodes + edges)
- Validate completeness (no orphan states, all states reachable from start)
- Auto-generate transition prompts that get injected into the system prompt at runtime
- Track current state per conversation for analytics and the conversation viewer

#### Step 5: Distribution Channel

Each agent can be deployed to one or more channels.

**Voice (Inbound + Outbound):**

*Common config:*
- Phone number assignment (from Exotel/Knowlarity number pool)
- Voice selection (TTS voice — gender, language, speed)
- STT language/dialect (Hindi, English, Hinglish, regional)
- Call timeout settings (max duration, silence timeout)
- Greeting message
- Call recording consent message (legally required in India)
- Fallback behavior on STT failure (repeat, escalate)
- Working hours / availability schedule (IST)
- Transfer-to-human number (escalation)
- DTMF handling for IVR-style fallbacks

*Outbound-specific config:*
- Contact list upload (CSV: name, phone, metadata columns)
- Campaign name and schedule (start date/time, end date/time, calling hours window)
- Call pacing: max concurrent calls, calls per minute
- Retry rules: max attempts per contact, gap between retries, retry on no-answer/busy/voicemail
- DND (Do Not Disturb) registry check — mandatory in India (TRAI DND list)
- Caller ID selection
- Campaign status controls (start, pause, resume, stop)

*Outbound campaign dashboard:*
- Total contacts, dialed, connected, completed, failed
- Disposition breakdown (sale, callback, not interested, DND, no answer)

**WhatsApp (Multi-Provider):**

*Provider config:*
- Provider type: Meta Cloud API (direct) / Gupshup / Twilio / Wati / ValueFirst / customer-provided BSP
- API credentials (API key, auth token, app ID — varies by provider)
- WhatsApp Business number
- Webhook URL configuration (we provide the URL, customer configures it in their BSP dashboard)

*Agent config:*
- Welcome message (triggered on first contact or keyword)
- Session timeout (WhatsApp 24-hour window handling)
- Template messages for re-engagement (pre-approved by Meta — customer provides template IDs)
- Media handling toggles:
  - Accept images (for document verification — Aadhaar, PAN, etc.)
  - Accept documents (PDF uploads)
  - Accept voice notes (transcribed via STT)
  - Send images/documents back
- Quick reply buttons / list messages (WhatsApp interactive messages)
- Opt-in/opt-out flow
- Language detection (auto-detect Hindi vs English from first message)

**Chatbot (API-based):**

*Instead of an embeddable widget, we expose API endpoints:*
- Generate API key per customer/agent deployment
- Endpoints provided to customer:
  - `POST /api/chat/{agent_id}/message` — send message, receive response
  - `POST /api/chat/{agent_id}/message/media` — send message with media attachment
  - `GET /api/chat/{agent_id}/session/{session_id}` — get conversation history
  - `POST /api/chat/{agent_id}/session` — create new session
  - `DELETE /api/chat/{agent_id}/session/{session_id}` — end session
- Rate limiting per API key
- CORS / IP allowlisting
- Welcome message config
- Media handling (image/document upload via multipart)
- Session timeout
- API documentation auto-generated (OpenAPI/Swagger spec)

#### Step 6: Guardrails

**Auto-generated based on prior inputs:**
- Topic boundaries (derived from KB topics)
- PII handling rules (mask Aadhaar, PAN, bank account in logs; never repeat full PII back)
- IRDAI compliance phrases (mandatory disclosures, cooling-off period, free-look period mention)
- Hallucination prevention (only answer from KB for product questions)
- Escalation triggers (frustration, legal language, explicit human request)
- Action safety (require confirmation before DB writes, payment links, document submissions)
- Rate limits (max messages per session, max sessions per number per day)
- Language boundaries
- Anti-mis-selling rules (don't guarantee returns, don't compare with competitors unless data exists in KB)
- Consent collection prompts (before collecting PII or sending documents)

**User-editable:**
- Add/remove/edit any auto-generated guardrail
- Add custom rules (free-text)
- Set severity: block (hard stop), warn (flag but continue), log (record only)
- Banned phrases / topics
- Max conversation length

---

### 3.2 Conversation Viewer

**Features:**
- **Conversation list** — filterable by agent, channel, date range, state reached, outcome, campaign (for outbound)
- **Conversation detail view:**
  - Full message thread (user + agent)
  - Voice: speaker-diarized transcript with timestamps and STT confidence scores
  - WhatsApp/chatbot: rendered thread including images, documents, voice note transcriptions
  - Sidebar: current state, actions triggered (with payloads + responses), guardrails triggered, metadata (phone/WhatsApp number, duration, message count, disposition)
- **Search** — full-text search across conversations
- **Export** — CSV/JSON export
- **Polling-based updates** — conversation list refreshes every 30s, detail view every 10s for active conversations

**Voice-specific:**
- STT transcript with speaker labels, timestamps, confidence scores
- Flag low-confidence transcriptions for QA
- No audio playback in MVP

---

### 3.3 Document & Image Processing (WhatsApp + Chatbot)

**Supported media:**
- Images (JPEG, PNG) — up to 5MB
- Documents (PDF) — up to 10MB
- Voice notes (OGG/OPUS from WhatsApp) — up to 2 min

**Processing pipeline:**
1. Receive media → store in S3 (Mumbai region)
2. Classify document type using Claude Vision (Aadhaar, PAN, driving license, RC, policy doc, etc.)
3. Extract structured data (name, DOB, document number, address)
4. Verify against expected values if available
5. Agent confirms extraction with user, proceeds or asks for re-upload

**Indian document types supported (MVP):**
- Aadhaar card (front + back)
- PAN card
- Driving license
- Voter ID
- Passport (first + last page)
- Vehicle RC
- Bank statement (first page)
- Cancelled cheque

---

### 3.4 Agent Dashboard

Per-agent overview:
- Total conversations (today / week / all time)
- Funnel by state reached
- Completion rate, escalation rate
- Average conversation length
- Guardrail trigger frequency
- For outbound: campaign progress, connect rate, disposition breakdown

---

### 3.5 Customer Registry

Simple CRUD for managing customers we're building agents for:
- Customer name, contact person, industry segment
- API credentials vault (encrypted storage of their API keys/tokens)
- WhatsApp BSP details
- Phone numbers allocated
- Active agents count

---

## 4. Out of Scope (MVP)

- Live conversation monitoring / streaming
- Customer-facing self-service portal
- A/B testing of agent configs
- Agent-to-agent handoff
- Audio recording storage/playback
- Predictive dialer (we do progressive dialing in MVP)
- WhatsApp Flows
- IVR builder (complex multi-level IVR)
- Automated evaluation / scoring of agent performance
- Multi-org tenancy

---

## 5. Success Metrics (MVP)

- Agent creation time: < 30 minutes from blank to deployed
- Conversation viewer load: < 2s list, < 1s detail
- Voice round-trip latency: < 1.5s (user stops speaking → agent starts)
- STT accuracy: > 90% for English, > 85% for Hindi/Hinglish
- Document classification accuracy: > 95% for supported Indian ID types
- Outbound connect rate tracking functional
- System uptime: 99.5%
