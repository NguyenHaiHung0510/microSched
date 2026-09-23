"""Durable SQLModel rows for the bounded Mimi P1 walking skeleton."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field

from app.domain.models import SCHEMA, Gate, UUIDTimestampModel


class MimiConversation(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_conversation"
    __privacy_gate__: ClassVar[Gate] = Gate.APPLIES
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint("sensitivity IN ('standard', 'private')", name="sensitivity"),
        CheckConstraint("generation >= 1", name="generation"),
        CheckConstraint("next_message_sequence >= 1", name="next_message_sequence"),
        CheckConstraint("context_frontier_sequence >= 0", name="context_frontier_sequence"),
        CheckConstraint("dek_wrapped LIKE 'enc:v1:%'", name="wrapped_dek"),
        CheckConstraint(
            "title_ciphertext IS NULL OR title_ciphertext LIKE 'mimi:v1:%'",
            name="title_ciphertext",
        ),
        CheckConstraint("title_source IN ('auto', 'owner')", name="title_source"),
        CheckConstraint("(title_source = 'owner') = title_locked", name="title_lock"),
        CheckConstraint("metadata_version >= 1", name="metadata_version"),
        CheckConstraint("(sensitivity = 'private') = is_private", name="sensitivity_private_match"),
        Index(
            "uq_mimi_conversation_owner_client",
            "owner_id",
            "client_id",
            unique=True,
            postgresql_where=text("client_id IS NOT NULL"),
        ),
        Index(
            "ix_mimi_conversation_owner_archive_updated",
            "owner_id",
            "archived_at",
            text("updated_at DESC"),
            text("id DESC"),
        ),
        {"schema": SCHEMA},
    )

    owner_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False, index=True))
    client_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    sensitivity: str = Field(sa_column=Column(Text, nullable=False))
    generation: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default=text("1"))
    )
    next_message_sequence: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default=text("1"))
    )
    context_frontier_sequence: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
    dek_wrapped: str = Field(sa_column=Column(Text, nullable=False))
    title_ciphertext: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    title_source: str = Field(
        default="auto", sa_column=Column(Text, nullable=False, server_default=text("'auto'"))
    )
    title_locked: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    metadata_version: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default=text("1"))
    )
    archived_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    is_private: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )


class MimiMessage(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_message"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="sequence"),
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="role"),
        CheckConstraint("content_ciphertext LIKE 'mimi:v1:%'", name="ciphertext"),
        CheckConstraint("content_bytes BETWEEN 1 AND 65536", name="content_bytes"),
        UniqueConstraint(
            "conversation_id", "sequence", name="uq_mimi_message_conversation_sequence"
        ),
        UniqueConstraint(
            "conversation_id", "client_id", name="uq_mimi_message_conversation_client"
        ),
        {"schema": SCHEMA},
    )

    conversation_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_conversation.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    run_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    client_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    sequence: int = Field(sa_column=Column(Integer, nullable=False))
    role: str = Field(sa_column=Column(Text, nullable=False))
    content_ciphertext: str = Field(sa_column=Column(Text, nullable=False))
    content_bytes: int = Field(sa_column=Column(Integer, nullable=False))
    content_sha256: str = Field(sa_column=Column(Text, nullable=False))


class MimiRun(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_run"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint("generation >= 1", name="generation"),
        CheckConstraint(
            "state IN ('accepted','building','running','waiting_confirmation',"
            "'executing','completed','halted','cancelled','retryable',"
            "'outcome_unknown','deadline_exceeded','budget_exceeded')",
            name="state",
        ),
        CheckConstraint(
            "provider_outcome IS NULL OR provider_outcome IN ('succeeded','failed','unknown')",
            name="provider_outcome",
        ),
        UniqueConstraint(
            "conversation_id", "generation", name="uq_mimi_run_conversation_generation"
        ),
        {"schema": SCHEMA},
    )

    conversation_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_conversation.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    generation: int = Field(sa_column=Column(Integer, nullable=False))
    state: str = Field(sa_column=Column(Text, nullable=False))
    provider_outcome: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    execution_lease: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    source_versions: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    deadline: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    error_code: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class MimiEvent(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_event"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="sequence"),
        UniqueConstraint("run_id", "sequence", name="uq_mimi_event_run_sequence"),
        {"schema": SCHEMA},
    )

    run_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_run.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    sequence: int = Field(sa_column=Column(Integer, nullable=False))
    kind: str = Field(sa_column=Column(Text, nullable=False))
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )


class MimiProviderCall(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_provider_call"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint("attempt >= 1", name="attempt"),
        CheckConstraint(
            "state IN ('intent','dispatched','succeeded','failed','unknown','fenced')", name="state"
        ),
        UniqueConstraint("run_id", "attempt", name="uq_mimi_provider_call_run_attempt"),
        {"schema": SCHEMA},
    )

    run_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_run.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    attempt: int = Field(sa_column=Column(Integer, nullable=False))
    state: str = Field(sa_column=Column(Text, nullable=False))
    request_fingerprint: str = Field(sa_column=Column(Text, nullable=False))
    route: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    result: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    usage: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))


class MimiChangeSet(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_change_set"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','confirmed','rejected','expired','stale','executed')", name="state"
        ),
        CheckConstraint("digest_sha256 ~ '^[0-9a-f]{64}$'", name="digest"),
        CheckConstraint("operation_ciphertext LIKE 'mimi:v1:%'", name="operation_ciphertext"),
        UniqueConstraint("run_id", name="uq_mimi_change_set_run"),
        {"schema": SCHEMA},
    )

    run_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_run.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    state: str = Field(sa_column=Column(Text, nullable=False))
    digest_sha256: str = Field(sa_column=Column(Text, nullable=False))
    nonce: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    operation_ciphertext: str = Field(sa_column=Column(Text, nullable=False))
    policy_version: str = Field(sa_column=Column(Text, nullable=False))


class MimiExecutionReceipt(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_execution_receipt"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        UniqueConstraint("change_set_id", name="uq_mimi_execution_receipt_change_set"),
        UniqueConstraint("idempotency_key", name="uq_mimi_execution_receipt_idempotency"),
        {"schema": SCHEMA},
    )

    change_set_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_change_set.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    operation_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False, unique=True))
    task_id: UUID = Field(
        # An immutable receipt must outlive Task soft/hard lifecycle changes,
        # like AuditLog.entity_id; it is a historical reference, not ownership.
        sa_column=Column(PGUUID(as_uuid=True), nullable=False)
    )
    digest_sha256: str = Field(sa_column=Column(Text, nullable=False))
    idempotency_key: str = Field(sa_column=Column(Text, nullable=False))
    result: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    executed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )


class MimiRefreshMarker(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_refresh_marker"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint("state IN ('pending','reconciled')", name="state"),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        UniqueConstraint("receipt_id", name="uq_mimi_refresh_marker_receipt"),
        {"schema": SCHEMA},
    )

    receipt_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_execution_receipt.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    state: str = Field(
        default="pending", sa_column=Column(Text, nullable=False, server_default=text("'pending'"))
    )
    reason: str = Field(sa_column=Column(Text, nullable=False))
    attempt_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
    reconciled_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class MimiFeedback(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_feedback"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('turn','run','call','operation','receipt')", name="target_type"
        ),
        CheckConstraint(
            "state IN ('new','acknowledged','triaged','linked_to_fix',"
            "'linked_to_case','verified','dismissed')",
            name="state",
        ),
        CheckConstraint("comment_ciphertext LIKE 'mimi:v1:%'", name="comment_ciphertext"),
        CheckConstraint(
            "expected_ciphertext IS NULL OR expected_ciphertext LIKE 'mimi:v1:%'",
            name="expected_ciphertext",
        ),
        UniqueConstraint(
            "conversation_id", "client_id", name="uq_mimi_feedback_conversation_client"
        ),
        {"schema": SCHEMA},
    )

    conversation_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_conversation.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    client_id: str = Field(sa_column=Column(Text, nullable=False))
    target_type: str = Field(sa_column=Column(Text, nullable=False))
    target_id: str = Field(sa_column=Column(Text, nullable=False))
    comment_ciphertext: str = Field(sa_column=Column(Text, nullable=False))
    expected_ciphertext: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    evidence_bundle_ids: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    state: str = Field(
        default="new", sa_column=Column(Text, nullable=False, server_default=text("'new'"))
    )
    unresolved: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default=text("true"))
    )


class MimiEvidence(UUIDTimestampModel, table=True):
    __tablename__ = "mimi_evidence"
    __privacy_gate__: ClassVar[Gate] = Gate.VIA_PARENT
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __table_args__ = (
        CheckConstraint(
            "capture_status IN ('complete','incomplete','failed')", name="capture_status"
        ),
        CheckConstraint("content_bytes BETWEEN 0 AND 1048576", name="content_bytes"),
        {"schema": SCHEMA},
    )

    conversation_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_conversation.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    run_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.mimi_run.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    capture_status: str = Field(sa_column=Column(Text, nullable=False))
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    content_ref: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    content_bytes: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


Index(
    "ix_mimi_refresh_marker_pending",
    MimiRefreshMarker.__table__.c.created_at,
    postgresql_where=text("state = 'pending'"),
)
