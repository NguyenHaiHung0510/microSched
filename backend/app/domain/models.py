"""SQLModel definitions for the complete initial microSched schema."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

SCHEMA = "microsched"

SQLModel.metadata.naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def uuid_primary_key() -> Field:
    """Build the UUIDv7 primary-key field shared by every table."""
    return Field(
        default=None,
        primary_key=True,
        nullable=False,
        sa_type=PGUUID,
        sa_column_kwargs={"server_default": text("uuidv7()")},
    )


def created_timestamp() -> Field:
    """Build a database-owned creation timestamp field."""
    return Field(
        default=None,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )


def updated_timestamp() -> Field:
    """Build the timestamp maintained by the shared database trigger."""
    return Field(
        default=None,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )


def deleted_timestamp() -> Field:
    """Build a nullable soft-delete marker."""
    return Field(
        default=None,
        nullable=True,
        sa_type=DateTime(timezone=True),
    )


class UUIDTimestampModel(SQLModel):
    """Fields required on every persisted entity by B1 and B2."""

    id: UUID | None = uuid_primary_key()
    created_at: datetime | None = created_timestamp()
    updated_at: datetime | None = updated_timestamp()


class Task(UUIDTimestampModel, table=True):
    """A task with structured scheduling fields and optionally encrypted prose."""

    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'completed')", name="status_values"),
        CheckConstraint(
            "priority IS NULL OR priority IN ('p1', 'p2', 'p3')",
            name="priority_values",
        ),
        CheckConstraint(
            "NOT is_private OR ("
            "title LIKE 'enc:v1:%' "
            "AND (body_md IS NULL OR body_md LIKE 'enc:v1:%'))",
            name="private_ciphertext",
        ),
        {"schema": SCHEMA},
    )

    title: str = Field(sa_column=Column(Text, nullable=False))
    body_md: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(
        default="open",
        sa_column=Column(Text, nullable=False, server_default=text("'open'")),
    )
    priority: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    due_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    is_private: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    deleted_at: datetime | None = deleted_timestamp()


class TaskItem(UUIDTimestampModel, table=True):
    """An ordered checklist item belonging to a task."""

    __tablename__ = "task_item"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        {"schema": SCHEMA},
    )

    task_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.task.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    is_completed: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    position: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )


class Note(UUIDTimestampModel, table=True):
    """A note with an intentionally unbounded, unindexed vector placeholder."""

    __tablename__ = "note"
    __table_args__ = (
        CheckConstraint(
            "NOT is_private OR body_md IS NULL OR body_md LIKE 'enc:v1:%'",
            name="private_body_ciphertext",
        ),
        {"schema": SCHEMA},
    )

    title: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    body_md: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(), nullable=True),
    )
    is_private: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    deleted_at: datetime | None = deleted_timestamp()


class NoteItem(UUIDTimestampModel, table=True):
    """An ordered checklist item belonging to a note."""

    __tablename__ = "note_item"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        {"schema": SCHEMA},
    )

    note_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.note.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    is_completed: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    position: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )


class CalendarSource(UUIDTimestampModel, table=True):
    """A uniquely named import or manual calendar source."""

    __tablename__ = "calendar_source"
    __table_args__ = (
        CheckConstraint("kind IN ('ics', 'excel', 'manual')", name="kind_values"),
        {"schema": SCHEMA},
    )

    name: str = Field(sa_column=Column(Text, nullable=False))
    kind: str = Field(sa_column=Column(Text, nullable=False))
    color: str | None = Field(default=None, sa_column=Column(Text, nullable=True))


class CalendarEvent(UUIDTimestampModel, table=True):
    """A timezone-aware event generated by a calendar source."""

    __tablename__ = "calendar_event"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="positive_duration"),
        {"schema": SCHEMA},
    )

    source_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.calendar_source.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    title: str = Field(sa_column=Column(Text, nullable=False))
    location: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    starts_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    ends_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    is_hidden: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )


class TrackerGroup(UUIDTimestampModel, table=True):
    """The optional single grouping layer for trackers."""

    __tablename__ = "tracker_group"
    __table_args__ = (
        CheckConstraint("kind IN ('health', 'finance')", name="kind_values"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        UniqueConstraint("id", "kind", name="uq_tracker_group_id_kind"),
        {"schema": SCHEMA},
    )

    name: str = Field(sa_column=Column(Text, nullable=False))
    kind: str = Field(sa_column=Column(Text, nullable=False))
    color: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    position: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )


class Tracker(UUIDTimestampModel, table=True):
    """A health or finance stream whose sensitive name is always ciphertext."""

    __tablename__ = "tracker"
    __table_args__ = (
        CheckConstraint("name LIKE 'enc:v1:%'", name="name_ciphertext"),
        CheckConstraint("kind IN ('health', 'finance')", name="kind_values"),
        CheckConstraint("direction IN ('in', 'out')", name="direction_values"),
        CheckConstraint(
            "input_mode IN ('event', 'money', 'quantity')",
            name="input_mode_values",
        ),
        CheckConstraint(
            "(input_mode = 'quantity' AND unit IS NOT NULL) OR "
            "(input_mode <> 'quantity' AND unit IS NULL)",
            name="unit_matches_input_mode",
        ),
        ForeignKeyConstraint(
            ["group_id", "kind"],
            [f"{SCHEMA}.tracker_group.id", f"{SCHEMA}.tracker_group.kind"],
            name="fk_tracker_group_kind",
            ondelete="SET NULL (group_id)",
        ),
        {"schema": SCHEMA},
    )

    name: str = Field(sa_column=Column(Text, nullable=False))
    kind: str = Field(sa_column=Column(Text, nullable=False))
    direction: str = Field(
        default="out",
        sa_column=Column(Text, nullable=False, server_default=text("'out'")),
    )
    input_mode: str = Field(
        default="event",
        sa_column=Column(Text, nullable=False, server_default=text("'event'")),
    )
    group_id: UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), nullable=True),
    )
    unit: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    color: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    reminder_time: time | None = Field(default=None, sa_column=Column(Time, nullable=True))
    reminder_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_private: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    deleted_at: datetime | None = deleted_timestamp()


class Subscription(UUIDTimestampModel, table=True):
    """A time-bounded recurring or prepaid agreement."""

    __tablename__ = "subscription"
    __table_args__ = (
        CheckConstraint("name LIKE 'enc:v1:%'", name="name_ciphertext"),
        CheckConstraint("amount LIKE 'enc:v1:%'", name="amount_ciphertext"),
        CheckConstraint(
            "list_amount IS NULL OR list_amount LIKE 'enc:v1:%'",
            name="list_amount_ciphertext",
        ),
        CheckConstraint("period_count > 0", name="period_count_positive"),
        CheckConstraint(
            "period_unit IN ('day', 'week', 'month', 'year')",
            name="period_unit_values",
        ),
        CheckConstraint("expires_on >= started_on", name="date_order"),
        {"schema": SCHEMA},
    )

    name: str = Field(sa_column=Column(Text, nullable=False))
    tracker_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.tracker.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    amount: str = Field(sa_column=Column(Text, nullable=False))
    list_amount: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    period_count: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )
    period_unit: str = Field(
        default="month",
        sa_column=Column(Text, nullable=False, server_default=text("'month'")),
    )
    started_on: date = Field(sa_column=Column(Date, nullable=False))
    expires_on: date = Field(sa_column=Column(Date, nullable=False))
    auto_renew: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    canceled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    note_md: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    deleted_at: datetime | None = deleted_timestamp()


class Entry(UUIDTimestampModel, table=True):
    """A timestamped tracker event with optional quantity or encrypted money."""

    __tablename__ = "entry"
    __table_args__ = (
        CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "amount IS NULL OR amount LIKE 'enc:v1:%'",
            name="amount_ciphertext",
        ),
        CheckConstraint(
            "list_amount IS NULL OR list_amount LIKE 'enc:v1:%'",
            name="list_amount_ciphertext",
        ),
        CheckConstraint(
            "note_md IS NULL OR note_md LIKE 'enc:v1:%'",
            name="note_ciphertext",
        ),
        {"schema": SCHEMA},
    )

    tracker_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.tracker.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    subscription_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(f"{SCHEMA}.subscription.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    quantity: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(10, 2), nullable=True),
    )
    amount: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    list_amount: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    occurred_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    note_md: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    deleted_at: datetime | None = deleted_timestamp()


class AppSetting(UUIDTimestampModel, table=True):
    """A JSON setting addressed by a stable unique key."""

    __tablename__ = "app_setting"
    __table_args__ = (
        UniqueConstraint("key", name="uq_app_setting_key"),
        {"schema": SCHEMA},
    )

    key: str = Field(sa_column=Column(Text, nullable=False))
    value: dict = Field(sa_column=Column(JSONB, nullable=False))


class Message(UUIDTimestampModel, table=True):
    """Encrypted tier-one conversation content."""

    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role_values"),
        CheckConstraint("content LIKE 'enc:v1:%'", name="content_ciphertext"),
        {"schema": SCHEMA},
    )

    role: str = Field(sa_column=Column(Text, nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    is_private: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    trace_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))


class AuditLog(UUIDTimestampModel, table=True):
    """Compact tier-two trace and tool metadata; raw replay remains off-database."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            "(entity_type IS NULL) = (entity_id IS NULL)",
            name="entity_reference_complete",
        ),
        {"schema": SCHEMA},
    )

    trace_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    turn_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    action: str = Field(sa_column=Column(Text, nullable=False))
    tool: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    entity_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    entity_id: UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), nullable=True),
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
    )


class AuthSession(UUIDTimestampModel, table=True):
    """A server-side login session identified by an opaque-token hash."""

    __tablename__ = "session"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_session_token_hash"),
        {"schema": SCHEMA},
    )

    token_hash: str = Field(sa_column=Column(Text, nullable=False))
    user_email: str = Field(sa_column=Column(Text, nullable=False))
    last_seen_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    private_until: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


Index("ix_task_due_at", Task.__table__.c.due_at)
Index("ix_task_item_task_id", TaskItem.__table__.c.task_id)
Index("ix_note_item_note_id", NoteItem.__table__.c.note_id)
Index(
    "uq_calendar_source_name_lower",
    func.lower(CalendarSource.__table__.c.name),
    unique=True,
)
Index("ix_calendar_event_source_id", CalendarEvent.__table__.c.source_id)
Index("ix_calendar_event_starts_at", CalendarEvent.__table__.c.starts_at)
Index(
    "uq_tracker_group_name_lower",
    func.lower(TrackerGroup.__table__.c.name),
    unique=True,
)
Index("ix_tracker_group_id", Tracker.__table__.c.group_id)
Index("ix_subscription_tracker_id", Subscription.__table__.c.tracker_id)
Index("ix_subscription_expires_on", Subscription.__table__.c.expires_on)
Index(
    "ix_entry_tracker_occurred_at",
    Entry.__table__.c.tracker_id,
    Entry.__table__.c.occurred_at.desc(),
)
Index("ix_entry_occurred_at", Entry.__table__.c.occurred_at)
Index("ix_entry_subscription_id", Entry.__table__.c.subscription_id)
Index("ix_message_trace_id", Message.__table__.c.trace_id)
Index("ix_audit_log_trace_id", AuditLog.__table__.c.trace_id)
Index("ix_audit_log_turn_id", AuditLog.__table__.c.turn_id)
