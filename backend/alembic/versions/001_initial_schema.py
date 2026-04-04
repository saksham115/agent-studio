"""Initial schema — all tables for Agent Studio.

Revision ID: 001_initial
Revises:
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # === Organizations ===
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === Users ===
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === Agents ===
    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("persona", sa.Text, nullable=True),
        sa.Column("status", sa.Enum("draft", "published", "archived", name="agent_status_enum"), nullable=False, server_default="draft"),
        sa.Column("languages", ARRAY(sa.String(10)), nullable=True),
        sa.Column("model_config", JSONB, nullable=True),
        sa.Column("welcome_message", sa.Text, nullable=True),
        sa.Column("fallback_message", sa.Text, nullable=True),
        sa.Column("escalation_message", sa.Text, nullable=True),
        sa.Column("max_turns", sa.Integer, nullable=True, server_default="50"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_version", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === Knowledge Base ===
    op.create_table(
        "kb_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("source_type", sa.Enum("pdf", "docx", "txt", "csv", "url", name="source_type_enum"), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("status", sa.Enum("pending", "processing", "completed", "failed", name="document_status_enum"), nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "kb_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("embedding", sa.Text, nullable=True),  # Will be altered to vector(1024) after pgvector extension is created
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "kb_structured_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.Enum("api", "database", "spreadsheet", name="structured_source_type_enum"), nullable=False),
        sa.Column("connection_config", JSONB, nullable=False),
        sa.Column("query_template", sa.Text, nullable=True),
        sa.Column("refresh_interval_minutes", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === Actions ===
    op.create_table(
        "actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("action_type", sa.Enum("api_call", "tool_call", "handoff", "data_lookup", "send_message", "custom", name="action_type_enum"), nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("input_params", JSONB, nullable=True),
        sa.Column("output_schema", JSONB, nullable=True),
        sa.Column("requires_confirmation", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === States & Transitions ===
    op.create_table(
        "states",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("instructions", sa.Text, nullable=True),
        sa.Column("is_initial", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_terminal", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("position_x", sa.Integer, nullable=True),
        sa.Column("position_y", sa.Integer, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "transitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_state_id", UUID(as_uuid=True), sa.ForeignKey("states.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_state_id", UUID(as_uuid=True), sa.ForeignKey("states.id", ondelete="CASCADE"), nullable=False),
        sa.Column("condition", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === Channels ===
    op.create_table(
        "channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_type", sa.Enum("voice", "whatsapp", "chatbot", name="channel_type_enum"), nullable=False),
        sa.Column("status", sa.Enum("inactive", "active", "error", name="channel_status_enum"), nullable=False, server_default="inactive"),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column("webhook_url", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_id", "channel_type", name="uq_agent_channel_type"),
    )

    op.create_table(
        "whatsapp_providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel_id", UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("api_key_encrypted", sa.Text, nullable=True),
        sa.Column("phone_number_id", sa.String(100), nullable=True),
        sa.Column("business_account_id", sa.String(100), nullable=True),
        sa.Column("webhook_verify_token", sa.String(255), nullable=True),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chatbot_api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(512), nullable=False),
        sa.Column("key_prefix", sa.String(10), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === Guardrails ===
    op.create_table(
        "guardrails",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("guardrail_type", sa.Enum("input", "output", "topic", "compliance", "pii", "custom", name="guardrail_type_enum"), nullable=False),
        sa.Column("rule", sa.Text, nullable=False),
        sa.Column("action", sa.Enum("block", "warn", "redirect", "log", name="guardrail_action_enum"), nullable=False, server_default="block"),
        sa.Column("action_config", JSONB, nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_auto_generated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === Conversations & Messages ===
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_user_id", sa.String(255), nullable=True),
        sa.Column("external_user_phone", sa.String(20), nullable=True),
        sa.Column("external_user_name", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("active", "completed", "escalated", "abandoned", name="conversation_status_enum"), nullable=False, server_default="active"),
        sa.Column("current_state_id", UUID(as_uuid=True), sa.ForeignKey("states.id", ondelete="SET NULL"), nullable=True),
        sa.Column("context", JSONB, nullable=True),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("sentiment_score", sa.Float, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_conversations_agent", "conversations", ["agent_id", "started_at"])
    op.create_index("idx_conversations_status", "conversations", ["status"])

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum("user", "assistant", "system", "tool", name="message_role_enum"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("tool_calls", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_messages_conversation", "messages", ["conversation_id", "created_at"])

    # === Audit Tables ===
    op.create_table(
        "action_executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", UUID(as_uuid=True), sa.ForeignKey("actions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_name", sa.String(255), nullable=False),
        sa.Column("input_data", JSONB, nullable=True),
        sa.Column("output_data", JSONB, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "guardrail_triggers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guardrail_id", UUID(as_uuid=True), sa.ForeignKey("guardrails.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("guardrail_name", sa.String(255), nullable=False),
        sa.Column("triggered_rule", sa.Text, nullable=False),
        sa.Column("action_taken", sa.String(50), nullable=False),
        sa.Column("original_content", sa.Text, nullable=True),
        sa.Column("modified_content", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Alter embedding column to proper vector type (must come after pgvector extension is created)
    op.execute("ALTER TABLE kb_chunks ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)")
    op.execute("CREATE INDEX idx_kb_chunks_embedding ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")

    # Full-text search index on messages
    op.execute("CREATE INDEX idx_messages_content_fts ON messages USING GIN (to_tsvector('english', content))")

    op.create_table(
        "state_transitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_state_id", UUID(as_uuid=True), sa.ForeignKey("states.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_state_id", UUID(as_uuid=True), sa.ForeignKey("states.id", ondelete="SET NULL"), nullable=False),
        sa.Column("transition_id", UUID(as_uuid=True), sa.ForeignKey("transitions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("state_transitions")
    op.drop_table("guardrail_triggers")
    op.drop_table("action_executions")
    op.drop_index("idx_messages_conversation", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_conversations_status", table_name="conversations")
    op.drop_index("idx_conversations_agent", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("guardrails")
    op.drop_table("chatbot_api_keys")
    op.drop_table("whatsapp_providers")
    op.drop_table("channels")
    op.drop_table("transitions")
    op.drop_table("states")
    op.drop_table("actions")
    op.drop_table("kb_structured_sources")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")
    op.drop_table("agents")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute("DROP TYPE IF EXISTS agent_status_enum")
    op.execute("DROP TYPE IF EXISTS source_type_enum")
    op.execute("DROP TYPE IF EXISTS document_status_enum")
    op.execute("DROP TYPE IF EXISTS structured_source_type_enum")
    op.execute("DROP TYPE IF EXISTS action_type_enum")
    op.execute("DROP TYPE IF EXISTS channel_type_enum")
    op.execute("DROP TYPE IF EXISTS channel_status_enum")
    op.execute("DROP TYPE IF EXISTS guardrail_type_enum")
    op.execute("DROP TYPE IF EXISTS guardrail_action_enum")
    op.execute("DROP TYPE IF EXISTS conversation_status_enum")
    op.execute("DROP TYPE IF EXISTS message_role_enum")
    op.execute("DROP EXTENSION IF EXISTS vector")
