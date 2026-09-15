"""Add the durable Mimi P1 conversation and execution ledger."""

# SQL CHECK expressions stay on one line inside the executable DDL receipt.
# ruff: noqa: E501

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE microsched.mimi_conversation (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    owner_id UUID NOT NULL,
    sensitivity TEXT NOT NULL CHECK (sensitivity IN ('standard', 'private')),
    generation INTEGER DEFAULT 1 NOT NULL CHECK (generation >= 1),
    next_message_sequence INTEGER DEFAULT 1 NOT NULL CHECK (next_message_sequence >= 1),
    context_frontier_sequence INTEGER DEFAULT 0 NOT NULL CHECK (context_frontier_sequence >= 0),
    dek_wrapped TEXT NOT NULL CHECK (dek_wrapped LIKE 'enc:v1:%'),
    is_private BOOLEAN DEFAULT false NOT NULL,
    CONSTRAINT ck_mimi_conversation_sensitivity_private_match
        CHECK ((sensitivity = 'private') = is_private)
);
CREATE INDEX ix_mimi_conversation_owner_id ON microsched.mimi_conversation(owner_id);

CREATE TABLE microsched.mimi_run (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    conversation_id UUID NOT NULL REFERENCES microsched.mimi_conversation(id) ON DELETE CASCADE,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state IN ('accepted','building','running','waiting_confirmation','executing','completed','halted','cancelled','retryable','outcome_unknown','deadline_exceeded','budget_exceeded')),
    provider_outcome TEXT CHECK (provider_outcome IS NULL OR provider_outcome IN ('succeeded','failed','unknown')),
    execution_lease JSONB DEFAULT '{}'::jsonb NOT NULL,
    source_versions JSONB DEFAULT '{}'::jsonb NOT NULL,
    deadline timestamptz NOT NULL,
    error_code TEXT,
    completed_at timestamptz,
    CONSTRAINT uq_mimi_run_conversation_generation UNIQUE (conversation_id, generation)
);

CREATE TABLE microsched.mimi_message (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    conversation_id UUID NOT NULL REFERENCES microsched.mimi_conversation(id) ON DELETE CASCADE,
    run_id UUID REFERENCES microsched.mimi_run(id) ON DELETE SET NULL,
    client_id TEXT,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content_ciphertext TEXT NOT NULL CHECK (content_ciphertext LIKE 'mimi:v1:%'),
    content_bytes INTEGER NOT NULL CHECK (content_bytes BETWEEN 1 AND 65536),
    content_sha256 TEXT NOT NULL,
    CONSTRAINT uq_mimi_message_conversation_sequence UNIQUE (conversation_id, sequence),
    CONSTRAINT uq_mimi_message_conversation_client UNIQUE (conversation_id, client_id)
);

CREATE TABLE microsched.mimi_event (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    run_id UUID NOT NULL REFERENCES microsched.mimi_run(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    kind TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT uq_mimi_event_run_sequence UNIQUE (run_id, sequence)
);

CREATE TABLE microsched.mimi_provider_call (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    run_id UUID NOT NULL REFERENCES microsched.mimi_run(id) ON DELETE CASCADE,
    attempt INTEGER NOT NULL CHECK (attempt >= 1),
    state TEXT NOT NULL CHECK (state IN ('intent','dispatched','succeeded','failed','unknown','fenced')),
    request_fingerprint TEXT NOT NULL,
    route JSONB DEFAULT '{}'::jsonb NOT NULL,
    result JSONB,
    usage JSONB,
    CONSTRAINT uq_mimi_provider_call_run_attempt UNIQUE (run_id, attempt)
);

CREATE TABLE microsched.mimi_change_set (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    run_id UUID NOT NULL REFERENCES microsched.mimi_run(id) ON DELETE CASCADE,
    state TEXT NOT NULL CHECK (state IN ('pending','confirmed','rejected','expired','stale','executed')),
    digest_sha256 TEXT NOT NULL CHECK (digest_sha256 ~ '^[0-9a-f]{64}$'),
    nonce UUID NOT NULL,
    expires_at timestamptz NOT NULL,
    operation_ciphertext TEXT NOT NULL CHECK (operation_ciphertext LIKE 'mimi:v1:%'),
    policy_version TEXT NOT NULL,
    CONSTRAINT uq_mimi_change_set_run UNIQUE (run_id)
);

CREATE TABLE microsched.mimi_execution_receipt (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    change_set_id UUID NOT NULL REFERENCES microsched.mimi_change_set(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL UNIQUE,
    task_id UUID NOT NULL,
    digest_sha256 TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    result JSONB DEFAULT '{}'::jsonb NOT NULL,
    executed_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_mimi_execution_receipt_change_set UNIQUE (change_set_id)
);

CREATE TABLE microsched.mimi_refresh_marker (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    receipt_id UUID NOT NULL REFERENCES microsched.mimi_execution_receipt(id) ON DELETE CASCADE,
    state TEXT DEFAULT 'pending' NOT NULL CHECK (state IN ('pending','reconciled')),
    reason TEXT NOT NULL,
    attempt_count INTEGER DEFAULT 0 NOT NULL CHECK (attempt_count >= 0),
    reconciled_at timestamptz,
    CONSTRAINT uq_mimi_refresh_marker_receipt UNIQUE (receipt_id)
);
CREATE INDEX ix_mimi_refresh_marker_pending ON microsched.mimi_refresh_marker(created_at)
WHERE state = 'pending';

CREATE TABLE microsched.mimi_feedback (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    conversation_id UUID NOT NULL REFERENCES microsched.mimi_conversation(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('turn','run','call','operation','receipt')),
    target_id TEXT NOT NULL,
    comment_ciphertext TEXT NOT NULL CHECK (comment_ciphertext LIKE 'mimi:v1:%'),
    expected_ciphertext TEXT CHECK (expected_ciphertext IS NULL OR expected_ciphertext LIKE 'mimi:v1:%'),
    evidence_bundle_ids JSONB DEFAULT '[]'::jsonb NOT NULL,
    state TEXT DEFAULT 'new' NOT NULL CHECK (state IN ('new','acknowledged','triaged','linked_to_fix','linked_to_case','verified','dismissed')),
    unresolved BOOLEAN DEFAULT true NOT NULL,
    CONSTRAINT uq_mimi_feedback_conversation_client UNIQUE (conversation_id, client_id)
);

CREATE TABLE microsched.mimi_evidence (
    id UUID DEFAULT uuidv7() NOT NULL PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    conversation_id UUID NOT NULL REFERENCES microsched.mimi_conversation(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES microsched.mimi_run(id) ON DELETE CASCADE,
    capture_status TEXT NOT NULL CHECK (capture_status IN ('complete','incomplete','failed')),
    metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
    content_ref TEXT,
    content_bytes INTEGER DEFAULT 0 NOT NULL CHECK (content_bytes BETWEEN 0 AND 1048576),
    expires_at timestamptz NOT NULL
);

CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_conversation
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_run
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_message
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_event
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_provider_call
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_change_set
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_execution_receipt
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_refresh_marker
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_feedback
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_evidence
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();
    """)


def downgrade():
    from sqlalchemy import text

    bind = op.get_bind()
    occupied = bind.execute(
        text("SELECT EXISTS(SELECT 1 FROM microsched.mimi_conversation)")
    ).scalar_one()
    if occupied:
        raise RuntimeError("cannot downgrade 0014 with Mimi conversation data")
    for table in (
        "mimi_evidence",
        "mimi_feedback",
        "mimi_refresh_marker",
        "mimi_execution_receipt",
        "mimi_change_set",
        "mimi_provider_call",
        "mimi_event",
        "mimi_message",
        "mimi_run",
        "mimi_conversation",
    ):
        op.drop_table(table, schema="microsched")
