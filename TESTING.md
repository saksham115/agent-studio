# Agent Studio — Testing Scenarios

## Prerequisites

Before running any tests, ensure the full stack is up:

1. Infrastructure: `cd backend && docker compose up -d postgres redis minio minio-init`
2. Migrations: `cd backend && alembic upgrade head`
3. Backend: `uvicorn app.main:app --reload --port 8000`
4. Celery: `celery -A app.workers.celery_app worker --loglevel=info`
5. Frontend: `npm run dev`
6. Env vars: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `AUTH_SECRET` configured

Backend API docs available at http://localhost:8000/docs for manual endpoint testing.

---

## 1. Authentication

### 1.1 Google SSO Login
- [ ] Navigate to http://localhost:3000
- [ ] Verify redirect to `/login` page
- [ ] Verify "Agent Studio" branding, Zap icon, "Sign in with Google" button
- [ ] Click "Sign in with Google" — complete OAuth flow
- [ ] Verify redirect to dashboard after login
- [ ] Verify user avatar + name appears in sidebar footer
- [ ] Verify "Sign Out" works and redirects to login

### 1.2 Route Protection
- [ ] Open a private/incognito browser window
- [ ] Navigate to http://localhost:3000/agents — should redirect to `/login`
- [ ] Navigate to http://localhost:3000/conversations — should redirect to `/login`
- [ ] Navigate to http://localhost:3000/agents/new — should redirect to `/login`

### 1.3 Session Persistence
- [ ] Log in, close the tab, reopen — should still be logged in
- [ ] Refresh any dashboard page — should not redirect to login

---

## 2. Dashboard

### 2.1 Empty State
- [ ] On a fresh database, navigate to dashboard
- [ ] Verify KPI cards show zeros (0 agents, 0 conversations, -- completion rate, -- avg response time)
- [ ] Verify charts render empty gracefully (no errors)
- [ ] Verify "No conversations yet" and "No agents yet" empty states

### 2.2 With Data
- [ ] Create 2+ agents and run some conversations via chatbot API
- [ ] Verify KPI cards update with correct counts
- [ ] Verify "Conversations Over Time" chart shows data
- [ ] Verify "Conversation Funnel" shows stage progression
- [ ] Verify "Recent Conversations" table populates
- [ ] Verify "Top Agents" list shows agents ranked by conversation volume

---

## 3. Agent CRUD

### 3.1 Create Agent
- [ ] Navigate to `/agents` — verify empty state with "Create Agent" button
- [ ] Click "Create Agent" — verify wizard opens at Step 1
- [ ] Fill in: Agent Name = "Health Insurance Advisor", Persona = "Priya"
- [ ] Select Customer = "HDFC Ergo"
- [ ] Enter a system prompt (or click "Insert Template" → Health Insurance)
- [ ] Select languages: English, Hindi
- [ ] Select tone: Conversational
- [ ] Click "Save Draft" — verify success, agent saved with draft status

### 3.2 Agent List
- [ ] Navigate to `/agents` — verify the created agent appears as a card
- [ ] Verify status badge shows "Draft"
- [ ] Test search: type "Health" — agent should appear; type "Motor" — should not
- [ ] Test status filter: select "Draft" — agent appears; select "Active" — empty

### 3.3 Agent Detail
- [ ] Click "Configure" on the agent card
- [ ] Verify Overview tab shows correct info (name, persona, customer, languages)
- [ ] Verify Configuration tab shows step summary cards
- [ ] Verify API Keys tab shows empty state

### 3.4 Publish Agent
- [ ] Agent must have a system prompt to publish
- [ ] Test publishing via API: `POST /api/v1/agents/{id}/publish`
- [ ] Verify status changes to "Published"
- [ ] Verify `published_at` and `published_version` are set

### 3.5 Delete Agent
- [ ] Delete an agent via the API: `DELETE /api/v1/agents/{id}`
- [ ] Verify agent disappears from the list (soft-deleted/archived)

---

## 4. Agent Wizard — Full Configuration

### 4.1 Step 1: Identity & Prompt
- [ ] Verify all form fields render: name, persona, customer, system prompt, languages, tone
- [ ] Test "Insert Template" dropdown — verify 4 templates load (Health, Motor, Term Life, ULIP)
- [ ] Selecting a template should populate the system prompt textarea
- [ ] Verify character count on system prompt updates

### 4.2 Step 2: Knowledge Base
- [ ] Upload a PDF document (any insurance brochure)
- [ ] Verify upload progress indicator
- [ ] Verify document appears in the list with status "Processing" → "Ready"
- [ ] Verify chunk count is populated after processing
- [ ] Test deleting a document
- [ ] Add a structured source (API type) — verify it appears in the list

### 4.3 Step 3: Actions
- [ ] Add an action: Name = "Generate Quote", Type = "api_call"
- [ ] Set description, parameters, and config
- [ ] Verify action card renders with correct type badge
- [ ] Toggle "Requires Confirmation" switch
- [ ] Delete an action — verify it's removed

### 4.4 Step 4: State Diagram
- [ ] Verify React Flow canvas renders
- [ ] Default template states should appear (if navigated from a template)
- [ ] Test adding a new state via toolbar
- [ ] Test connecting two states (drag from handle to handle)
- [ ] Click a state node — verify side panel shows properties
- [ ] Edit state name and description in the side panel
- [ ] Verify one state is marked as "Start" (green header)
- [ ] Verify terminal states have red headers
- [ ] Save the diagram — verify it persists on reload

### 4.5 Step 5: Channels
- [ ] Toggle Voice channel — verify config form expands
- [ ] Fill in phone number, select TTS voice, set working hours
- [ ] Toggle WhatsApp — verify BSP provider dropdown (Gupshup, Meta, Twilio, Wati, ValueFirst)
- [ ] Toggle Chatbot — verify rate limit and CORS config fields
- [ ] Toggle all off — verify forms collapse

### 4.6 Step 6: Guardrails
- [ ] Click "Auto-generate" — verify guardrails are generated based on agent config
- [ ] Verify 6+ guardrails appear (IRDAI compliance, PII, topic boundary, etc.)
- [ ] Toggle a guardrail on/off
- [ ] Change severity (Block → Warn → Log)
- [ ] Add a custom guardrail rule
- [ ] Delete a guardrail

### 4.7 Full Save Flow
- [ ] Complete all 6 steps with valid data
- [ ] Click "Save Agent" on the final step
- [ ] Verify agent is created with all associated data (KB, actions, states, channels, guardrails)
- [ ] Verify redirect to agent detail page

---

## 5. Knowledge Base Pipeline

### 5.1 Document Upload and Ingestion
- [ ] Upload a PDF document via API: `POST /api/v1/agents/{id}/kb/documents`
- [ ] Verify document record created with status `pending`
- [ ] Verify Celery worker picks up the ingestion job
- [ ] Verify status changes to `processing` → `completed`
- [ ] Verify `chunk_count` is populated (> 0)
- [ ] Verify chunks are stored in `kb_chunks` table with embeddings

### 5.2 Supported File Types
- [ ] Upload a PDF — verify parsed correctly
- [ ] Upload a TXT file — verify parsed
- [ ] Upload a CSV file — verify parsed as readable text
- [ ] Upload a DOCX file — verify parsed (paragraphs + tables extracted)
- [ ] Upload an XLSX file — verify parsed (sheets and rows extracted)

### 5.3 Vector Search
- [ ] Upload a document about "health insurance for families"
- [ ] Call the chatbot API with a relevant question: "What health insurance plans do you have for families?"
- [ ] Verify the agent's response references content from the uploaded document
- [ ] Call with an irrelevant question: "What is the capital of France?"
- [ ] Verify the agent does NOT hallucinate insurance content

### 5.4 Document Deletion
- [ ] Delete a KB document via API
- [ ] Verify all associated chunks are also deleted
- [ ] Verify vector search no longer returns content from the deleted document

---

## 6. Chatbot API (End-to-End Agent Conversation)

### 6.1 Session Management
```bash
# Create a chatbot API key first (via DB or API)
# Then test:

# Create session
curl -X POST http://localhost:8000/api/v1/chat/{agent_id}/sessions \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user", "user_name": "Test User"}'

# Response should include session_id and welcome_message
```

### 6.2 Conversation Flow
```bash
# Send a message
curl -X POST http://localhost:8000/api/v1/chat/{agent_id}/sessions/{session_id}/messages \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"content": "I want health insurance for my family of 4"}'

# Response should include: content, state, actions_executed, status
```

- [ ] Send "Hello" — verify agent responds with greeting
- [ ] Send "I want health insurance for my family" — verify needs discovery questions
- [ ] Answer discovery questions — verify agent recommends plans
- [ ] Ask about premium — verify quote generation (if action configured)
- [ ] Verify state transitions occur (check `state` field in response)
- [ ] Verify conversation shows in the Conversations list page

### 6.3 Multi-Turn Context
- [ ] Send 5+ messages in the same session
- [ ] Verify the agent maintains context across turns
- [ ] Verify earlier information is remembered (family details, preferences)

### 6.4 Session Retrieval
```bash
# Get session with message history
curl http://localhost:8000/api/v1/chat/{agent_id}/sessions/{session_id} \
  -H "X-API-Key: your-api-key"
```
- [ ] Verify all messages are returned in order
- [ ] Verify both user and assistant messages are included

### 6.5 Session End
```bash
curl -X DELETE http://localhost:8000/api/v1/chat/{agent_id}/sessions/{session_id} \
  -H "X-API-Key: your-api-key"
```
- [ ] Verify session status changes to "completed"
- [ ] Verify sending messages to ended session returns 400

### 6.6 API Key Validation
- [ ] Send request without X-API-Key header — verify 401
- [ ] Send request with invalid API key — verify 401
- [ ] Send request with revoked API key — verify 401
- [ ] Send request to unpublished agent — verify 404

---

## 7. Guardrails

### 7.1 PII Detection (Input)
- [ ] Send message containing an Aadhaar number: "My Aadhaar is 1234 5678 9012"
- [ ] Verify the guardrail triggers (check guardrail_triggers in conversation detail)
- [ ] If guardrail action is "block" — verify the message is blocked with an explanation
- [ ] If guardrail action is "warn" — verify the message is processed but logged

### 7.2 PII Masking (Output)
- [ ] Configure agent to handle PII data
- [ ] Verify that if the agent's response contains Aadhaar/PAN numbers, they are masked
- [ ] Verify Aadhaar masking: `1234 5678 9012` → `XXXX XXXX 9012`
- [ ] Verify PAN masking: `ABCDE1234F` → `XXXXX1234X`
- [ ] Verify phone masking: `+91 9876543210` → `[REDACTED PHONE]`

### 7.3 Topic Boundary
- [ ] Configure a topic boundary guardrail: "Only discuss insurance products"
- [ ] Ask the agent: "What is the recipe for butter chicken?"
- [ ] Verify the agent redirects the conversation back to insurance topics

### 7.4 IRDAI Compliance
- [ ] Configure compliance guardrail: "Always mention free-look period"
- [ ] Have the agent discuss policy purchase
- [ ] Verify the compliance rule is checked in the output

### 7.5 Auto-Generate Guardrails
- [ ] Create an agent with a health insurance system prompt
- [ ] Call `POST /api/v1/agents/{id}/guardrails/generate`
- [ ] Verify 5+ guardrails are generated with appropriate types
- [ ] Verify IRDAI-specific rules are included (cooling-off period, free-look, anti-misselling)
- [ ] Verify generated guardrails are created as inactive drafts

---

## 8. State Machine

### 8.1 State Transitions
- [ ] Configure an agent with states: Greeting → Needs Discovery → Product Pitch → Closure
- [ ] Start a conversation and progress through each state
- [ ] Verify `state` field in chatbot API response changes as transitions occur
- [ ] Verify state transition audit logs are created

### 8.2 Terminal State
- [ ] Configure a "Closure" state as terminal
- [ ] Progress conversation to the terminal state
- [ ] Verify conversation status changes to "completed"
- [ ] Verify no further messages can be sent

### 8.3 Stateless Agent
- [ ] Create an agent with no states defined
- [ ] Verify the agent works correctly without a state machine
- [ ] Verify `state` field in response is null

---

## 9. Actions

### 9.1 API Call Action
- [ ] Configure an action of type `api_call` with a valid endpoint
- [ ] During conversation, trigger the action (agent should call the tool)
- [ ] Verify action execution is logged in `action_executions` table
- [ ] Verify the result is fed back to the agent for response generation

### 9.2 Action with Confirmation
- [ ] Configure an action with `requires_confirmation = true`
- [ ] Trigger the action during conversation
- [ ] Verify the agent asks for user confirmation before executing
- [ ] Confirm — verify action executes
- [ ] In a new conversation, deny — verify action is skipped

### 9.3 Action Failure
- [ ] Configure an action pointing to an invalid/down endpoint
- [ ] Trigger the action
- [ ] Verify graceful failure — error logged, agent provides fallback response
- [ ] Verify `action_executions` record shows `success = false`

---

## 10. Conversations Viewer

### 10.1 Conversation List
- [ ] Navigate to `/conversations`
- [ ] Verify conversations appear with correct columns (contact, agent, channel, state, status, time)
- [ ] Test channel filter (Voice, WhatsApp, Chatbot)
- [ ] Test status filter (Active, Completed, Escalated)
- [ ] Test search — search by contact name or message content
- [ ] Test pagination — verify page controls work

### 10.2 Conversation Detail
- [ ] Click on a conversation in the list
- [ ] Verify message thread renders with correct alignment (user left, agent right)
- [ ] Verify system messages (state transitions, action triggers) render centered
- [ ] Verify metadata sidebar shows: conversation info, current state, state timeline
- [ ] Verify actions triggered section shows executed actions
- [ ] Verify guardrails triggered section shows any violations

---

## 11. WhatsApp Channel (Gupshup)

### 11.1 Webhook Verification
```bash
# Simulate Gupshup webhook verification
curl "http://localhost:8000/api/v1/webhooks/whatsapp/{agent_id}?hub.challenge=test123&hub.verify_token=token"
# Should return: test123
```

### 11.2 Incoming Text Message
```bash
# Simulate Gupshup incoming message webhook
curl -X POST http://localhost:8000/api/v1/webhooks/whatsapp/{agent_id} \
  -H "Content-Type: application/json" \
  -d '{
    "type": "message",
    "payload": {
      "type": "text",
      "payload": {"text": "I want health insurance"},
      "sender": {"phone": "919876543210", "name": "Rajesh Kumar"}
    }
  }'
```
- [ ] Verify a new conversation is created
- [ ] Verify the orchestrator processes the message
- [ ] Verify a response is sent back via Gupshup API
- [ ] Send another message from the same phone — verify it's routed to the same conversation

### 11.3 Media Messages
- [ ] Send an image message via webhook — verify it's acknowledged
- [ ] Send a document message — verify it's logged

### 11.4 Session Continuity
- [ ] Send multiple messages from the same phone number
- [ ] Verify all messages go to the same active conversation
- [ ] End the conversation — verify next message starts a new conversation

---

## 12. Voice Channel (Exotel + Sarvam AI)

### 12.1 Incoming Call Webhook
```bash
# Simulate Exotel incoming call
curl -X POST http://localhost:8000/api/v1/webhooks/voice/incoming \
  -d "CallSid=test123&From=919876543210&To=918001234567&CallStatus=ringing"
```
- [ ] Verify a new conversation is created
- [ ] Verify ExoML response is returned with welcome audio

### 12.2 Audio Processing (STT → LLM → TTS)
- [ ] Simulate audio input via `/webhooks/voice/audio`
- [ ] Verify Sarvam STT transcribes the audio
- [ ] Verify the transcribed text is processed by the orchestrator
- [ ] Verify Sarvam TTS generates response audio
- [ ] Verify ExoML response with audio URL is returned

### 12.3 Call End
```bash
# Simulate Exotel call end
curl -X POST http://localhost:8000/api/v1/webhooks/voice/status \
  -d "CallSid=test123&CallStatus=completed&Duration=120"
```
- [ ] Verify conversation status changes to "completed"
- [ ] Verify call metadata is stored (duration, recording URL)

---

## 13. Storage (MinIO/S3)

### 13.1 File Upload
- [ ] Upload a document via KB endpoint
- [ ] Verify the file is stored in MinIO bucket `agent-studio-uploads`
- [ ] Check MinIO console (localhost:9001) — verify file appears under `agents/{agent_id}/documents/`

### 13.2 File Download
- [ ] Verify the backend can download the file from MinIO for ingestion
- [ ] Generate a presigned URL — verify it's accessible

### 13.3 File Deletion
- [ ] Delete a KB document
- [ ] Verify the file is removed from MinIO (or marked for cleanup)

---

## 14. Background Jobs (Celery)

### 14.1 Document Ingestion Job
- [ ] Upload a large PDF (10+ pages)
- [ ] Verify the Celery worker picks up the `ingest_document_task`
- [ ] Check Celery logs — verify chunking and embedding steps
- [ ] Verify document status changes to "completed" after processing
- [ ] Verify retry on transient failure (kill worker mid-processing, restart)

### 14.2 Media Processing Job
- [ ] Trigger a media processing task (voice note transcription)
- [ ] Verify Celery worker processes it
- [ ] Check task result

---

## 15. Edge Cases and Error Handling

### 15.1 Empty/Invalid Input
- [ ] Send empty message to chatbot API — verify 422 validation error
- [ ] Send message > 10000 chars — verify 422
- [ ] Upload file > 50MB — verify rejection
- [ ] Upload unsupported file type (.exe, .zip) — verify rejection

### 15.2 Rate Limiting
- [ ] Send 100+ rapid requests to the chatbot API
- [ ] Verify the system handles load gracefully (no crashes)

### 15.3 Concurrent Sessions
- [ ] Create 5 chatbot sessions simultaneously
- [ ] Send messages to all sessions in parallel
- [ ] Verify each session maintains independent state and conversation

### 15.4 Agent Not Published
- [ ] Try to create a chatbot session for a draft agent — verify 404
- [ ] Try to send a WhatsApp message to a draft agent — verify handled

### 15.5 Database Connection Failure
- [ ] Stop Postgres, make a request — verify graceful error (500 with clear message)
- [ ] Restart Postgres — verify automatic recovery

### 15.6 LLM API Failure
- [ ] Set invalid ANTHROPIC_API_KEY
- [ ] Send a chatbot message — verify graceful fallback message (not a crash)
- [ ] Verify the fallback_message from agent config is used

---

## 16. Performance Benchmarks

### 16.1 Response Latency
- [ ] Measure end-to-end chatbot API response time (message → response)
- [ ] Target: < 3 seconds for text-only (no actions, no KB)
- [ ] Target: < 5 seconds with KB search + 1 action
- [ ] Target: < 8 seconds with KB search + tool use loop

### 16.2 KB Search Performance
- [ ] Upload 50 documents (mix of PDF, DOCX, CSV)
- [ ] Measure vector search time — target: < 200ms for top-5 results

### 16.3 Concurrent Load
- [ ] Simulate 10 concurrent chatbot sessions
- [ ] Verify all sessions respond within acceptable latency
- [ ] Monitor backend memory and CPU usage

---

## Quick Smoke Test (5 minutes)

For a rapid sanity check after deployment:

1. [ ] Login via Google SSO
2. [ ] Create an agent with the Health Insurance template
3. [ ] Upload one PDF document to the KB
4. [ ] Add one action (any type)
5. [ ] Create a simple state diagram (Greeting → Discovery → Closure)
6. [ ] Enable the Chatbot channel
7. [ ] Publish the agent
8. [ ] Generate a chatbot API key
9. [ ] Send 3 messages via the chatbot API
10. [ ] Check the conversation appears in the Conversations viewer
