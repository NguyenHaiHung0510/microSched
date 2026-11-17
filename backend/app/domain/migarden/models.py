"""Persisted state, immutable configuration and reports for the single binding."""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.domain.models import SCHEMA, Gate, UUIDTimestampModel


def timestamp(*, optional: bool = True):
    return Field(
        default=None if optional else ..., sa_type=DateTime(timezone=True), nullable=optional
    )


def document(*, optional: bool = True):
    return Field(
        default=None if optional else ...,
        sa_column=Column(JSONB(none_as_null=True), nullable=optional),
    )


class ConfigRecord(UUIDTimestampModel, table=True):
    __privacy_gate__: ClassVar[Gate] = Gate.NONE
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __tablename__ = "migarden_config"
    __table_args__ = {"schema": SCHEMA}

    config_ref: str = Field(unique=True, max_length=128)
    saved_at: datetime = timestamp(optional=False)
    bundle: dict = document(optional=False)


class ZoneState(UUIDTimestampModel, table=True):
    __privacy_gate__: ClassVar[Gate] = Gate.NONE
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __tablename__ = "migarden_zone"
    __table_args__ = (
        CheckConstraint("zone_id = 'zone-a'", name="single_binding"),
        CheckConstraint("device_environment IN ('qa', 'production')", name="device_environment"),
        CheckConstraint(
            "(device_id IS NULL) = (device_environment IS NULL)"
            " AND (device_id IS NULL) = (token_hash IS NULL)",
            name="credential_complete",
        ),
        {"schema": SCHEMA},
    )

    zone_id: str = Field(unique=True, max_length=32)
    device_id: str | None = Field(default=None, max_length=128)
    device_environment: str | None = Field(default=None, max_length=16)
    token_hash: str | None = Field(default=None, max_length=64)
    revoked_at: datetime | None = timestamp()
    desired_ref: str | None = Field(
        default=None, foreign_key=f"{SCHEMA}.migarden_config.config_ref"
    )
    applied_ref: str | None = Field(
        default=None, foreign_key=f"{SCHEMA}.migarden_config.config_ref"
    )
    applied_confirmed_at: datetime | None = timestamp()
    boot_id: str | None = Field(default=None, max_length=128)
    control_epoch: int | None = Field(default=None, sa_type=BigInteger)
    last_seen_at: datetime | None = timestamp()
    snapshot_received_at: datetime | None = timestamp()
    last_observed_at: datetime | None = timestamp()
    snapshot: dict | None = document()
    unidentified_execution: bool = Field(
        default=False, sa_type=Boolean, sa_column_kwargs={"server_default": text("false")}
    )
    stop_target_boot_id: str | None = Field(default=None, max_length=128)
    stop_target_epoch: int | None = Field(default=None, sa_type=BigInteger)
    report_reconciliation: dict | None = document()
    preview: dict | None = document()


class BootRecord(UUIDTimestampModel, table=True):
    __privacy_gate__: ClassVar[Gate] = Gate.NONE
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __tablename__ = "migarden_boot"
    __table_args__ = {"schema": SCHEMA}

    boot_id: str = Field(unique=True, max_length=128)
    first_seen_at: datetime = timestamp(optional=False)


class CommandRecord(UUIDTimestampModel, table=True):
    __privacy_gate__: ClassVar[Gate] = Gate.NONE
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __tablename__ = "migarden_command"
    __table_args__ = (
        CheckConstraint("kind IN ('start', 'stop')", name="kind"),
        Index("ix_migarden_command_kind_confirmed", "kind", "confirmed_at", "request_id"),
        Index(
            "ix_migarden_command_inflight",
            "kind",
            "status",
            postgresql_where=text(
                "status IN ('pending', 'received', 'granted', 'started', 'unknown', "
                "'stop_requested', 'stop_received', 'stop_unconfirmed')"
            ),
        ),
        {"schema": SCHEMA},
    )

    request_id: str = Field(unique=True, max_length=128)
    kind: str = Field(max_length=8)
    status: str = Field(max_length=24)
    session_owner_id: str = Field(max_length=36)
    reason: str | None = Field(default=None, max_length=256)
    confirmed_at: datetime = timestamp(optional=False)
    expires_at: datetime | None = timestamp()
    duration_seconds: int | None = None
    config_ref: str | None = Field(default=None, foreign_key=f"{SCHEMA}.migarden_config.config_ref")
    boot_id: str = Field(max_length=128)
    control_epoch: int = Field(sa_type=BigInteger)
    candidate_offered_at: datetime | None = timestamp()
    grant_id: str | None = Field(default=None, max_length=128)
    last_report_sequence: int | None = Field(default=None, sa_type=BigInteger)


class ReportRecord(UUIDTimestampModel, table=True):
    __privacy_gate__: ClassVar[Gate] = Gate.NONE
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __tablename__ = "migarden_report"
    __table_args__ = (
        UniqueConstraint("boot_id", "sequence", name="uq_migarden_report_boot_sequence"),
        Index("ix_migarden_report_kind_ref", "kind", "config_ref"),
        Index("ix_migarden_report_history", "kind", "sort_at", "event_id"),
        {"schema": SCHEMA},
    )

    event_id: str = Field(unique=True, max_length=128)
    boot_id: str = Field(max_length=128)
    sequence: int = Field(sa_type=BigInteger)
    kind: str = Field(max_length=24)
    config_ref: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default=None, max_length=16)
    result: str | None = Field(default=None, max_length=24)
    occurred_at: datetime | None = timestamp()
    sort_at: datetime = timestamp(optional=False)
    received_at: datetime = timestamp(optional=False)
    body: dict = document(optional=False)


class SessionRecord(UUIDTimestampModel, table=True):
    __privacy_gate__: ClassVar[Gate] = Gate.NONE
    __delete_gate__: ClassVar[Gate] = Gate.NONE
    __tablename__ = "migarden_session"
    __table_args__ = (
        Index("ix_migarden_session_terminal", "ended_at", "session_id"),
        Index("ix_migarden_session_start_history", "start_sort_at", "session_id"),
        Index("ix_migarden_session_end_history", "end_sort_at", "session_id"),
        Index(
            "ix_migarden_session_unresolved",
            "session_id",
            postgresql_where=text("outcome IS NULL OR outcome = 'unknown'"),
        ),
        {"schema": SCHEMA},
    )

    session_id: str = Field(unique=True, max_length=128)
    request_id: str | None = Field(default=None, unique=True, max_length=128)
    boot_id: str = Field(max_length=128)
    source: str = Field(max_length=16)
    config_ref: str = Field(max_length=128)
    planned_duration_seconds: int | None = None
    started_at: datetime | None = timestamp()
    ended_at: datetime | None = timestamp()
    output_duration_seconds: int | None = None
    outcome: str | None = Field(default=None, max_length=16)
    reason: str | None = Field(default=None, max_length=256)
    started_event_id: str | None = Field(
        default=None, foreign_key=f"{SCHEMA}.migarden_report.event_id"
    )
    ended_event_id: str | None = Field(
        default=None, foreign_key=f"{SCHEMA}.migarden_report.event_id"
    )
    start_sort_at: datetime | None = timestamp()
    end_sort_at: datetime | None = timestamp()
