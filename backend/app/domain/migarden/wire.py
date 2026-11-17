"""Frozen miGarden exchange v1 and clarification A. No HTTP or storage here."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

PROTOCOL = "migarden.zone-a.v1"
ZONE = "zone-a"
BINDING = "zone-a-v1"
WINDOW_SECONDS = 10_800
HOLDOFF = timedelta(seconds=45)
CLOCK_LEAD = timedelta(seconds=5)
REPORT_LIMIT = 16

Identity = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")]
Reason = Annotated[str, Field(min_length=1, max_length=256)]
Source = Literal["schedule", "remote", "local_button"]
TimeQuality = Literal["synced", "holdover", "unknown"]
Outcome = Literal["completed", "stopped", "fault", "unknown"]
LocalTime = Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
Seconds = Annotated[int, Field(strict=True, ge=15, le=WINDOW_SECONDS, multiple_of=15)]
MeasuredSeconds = Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]
Sequence = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]


def _utc(value: object) -> datetime:
    if isinstance(value, str):
        if "T" not in value or len(value) > 40:
            raise ValueError("expected UTC date and time")
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("expected UTC date and time")
    # The last UTC day might overflow when projected to Asia/Saigon.
    if value.year in {1, 9999}:
        raise ValueError("date out of range")
    return value.astimezone(UTC)


def _minute(value: object) -> datetime:
    value = _utc(value)
    if value.second or value.microsecond:
        raise ValueError("expected whole minute")
    return value


UTCDateTime = Annotated[datetime, BeforeValidator(_utc)]
UTCMinute = Annotated[datetime, BeforeValidator(_minute)]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False, frozen=True)


class Policy(WireModel):
    manual_duration_seconds: Seconds = 900
    max_session_seconds: Seconds = 1800
    window_seconds: Literal[10_800] = 10_800
    max_window_seconds: Seconds = 7200

    @model_validator(mode="after")
    def limit_order(self):
        if not (
            self.manual_duration_seconds <= self.max_session_seconds <= self.max_window_seconds
        ):
            raise ValueError("manual_duration <= max_session <= max_window")
        return self


class Once(WireModel):
    kind: Literal["once"]
    at: UTCMinute


class Daily(WireModel):
    kind: Literal["daily"]
    at_local_time: LocalTime


class Weekly(WireModel):
    kind: Literal["weekly"]
    at_local_time: LocalTime
    days_of_week: Annotated[
        list[Annotated[int, Field(strict=True, ge=1, le=7)]], Field(min_length=1, max_length=7)
    ]

    @model_validator(mode="after")
    def distinct_days(self):
        if len(set(self.days_of_week)) != len(self.days_of_week):
            raise ValueError("days_of_week must be distinct")
        return self


class Interval(WireModel):
    kind: Literal["interval"]
    anchor_at: UTCMinute
    interval_minutes: Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)]


Recurrence = Annotated[Once | Daily | Weekly | Interval, Field(discriminator="kind")]


class Schedule(WireModel):
    enabled: Annotated[bool, Field(strict=True)]
    effective_from: UTCMinute
    effective_until: UTCMinute | None
    duration_seconds: Seconds
    recurrence: Recurrence

    @model_validator(mode="after")
    def effective_range(self):
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("effective_until must be after effective_from")
        if self.enabled and isinstance(self.recurrence, Once):
            at = self.recurrence.at
            if at < self.effective_from or (
                self.effective_until is not None and at >= self.effective_until
            ):
                raise ValueError("once must be within the effective range")
        return self


class BundleContent(WireModel):
    policy: Policy
    schedule: Schedule

    @model_validator(mode="after")
    def schedule_duration(self):
        if self.schedule.duration_seconds > self.policy.max_session_seconds:
            raise ValueError("schedule duration exceeds max_session")
        return self


class ConfigurationBundle(BundleContent):
    config_ref: Identity
    zone_id: Literal["zone-a"] = ZONE
    binding_ref: Literal["zone-a-v1"] = BINDING


class ActiveSession(WireModel):
    session_id: Identity
    request_id: Identity | None
    trigger_source: Source
    started_at: UTCDateTime | None
    duration_seconds: Seconds
    elapsed_seconds: MeasuredSeconds
    config_ref: Identity


class Snapshot(WireModel):
    observed_at: UTCDateTime | None
    time_quality: TimeQuality
    output: Literal["off", "on", "unknown"]
    active_session: ActiveSession | None
    applied_config_ref: Identity | None
    ready: Annotated[bool, Field(strict=True)]
    blocked_reason: Reason | None

    @model_validator(mode="after")
    def observation_time(self):
        if self.time_quality != "unknown" and self.observed_at is None:
            raise ValueError("a usable clock needs an observation time")
        return self


class Empty(WireModel):
    pass


class OptionalReason(WireModel):
    reason: Reason | None = None


class RequiredReason(WireModel):
    reason: Reason


class Started(WireModel):
    started_at: UTCDateTime | None
    duration_seconds: Seconds


class Ended(WireModel):
    started_at: UTCDateTime | None
    ended_at: UTCDateTime | None
    output_duration_seconds: MeasuredSeconds | None
    outcome: Outcome
    reason: Reason | None


class StopProcessed(WireModel):
    outcome: Literal["close_requested", "already_off", "unconfirmed"]
    reason: Reason | None = None


class OccurrenceDecided(WireModel):
    occurrence_id: Identity
    scheduled_at: UTCMinute | None
    disposition: Literal["started", "skipped", "rejected", "unknown"]
    reason: Reason | None = None


class ReportBase(WireModel):
    event_id: Identity
    boot_id: Identity
    sequence: Sequence
    occurred_at: UTCDateTime | None
    time_quality: TimeQuality
    zone_id: Literal["zone-a"]
    binding_ref: Literal["zone-a-v1"]
    config_ref: Identity | None
    request_id: Identity | None = None
    session_id: Identity | None = None
    trigger_source: Source | None = None

    @model_validator(mode="after")
    def event_time(self):
        if self.occurred_at is None and self.time_quality != "unknown":
            raise ValueError("only an unknown clock may omit event time")
        return self


class ConfigAppliedReport(ReportBase):
    kind: Literal["config_applied"]
    config_ref: Identity
    payload: OptionalReason


class ConfigRejectedReport(ReportBase):
    kind: Literal["config_rejected"]
    config_ref: Identity
    payload: OptionalReason


class RequestReceivedReport(ReportBase):
    kind: Literal["request_received"]
    request_id: Identity
    payload: Empty


class RequestRejectedReport(ReportBase):
    kind: Literal["request_rejected"]
    request_id: Identity
    payload: RequiredReason


class StartedReport(ReportBase):
    kind: Literal["session_started"]
    config_ref: Identity
    session_id: Identity
    trigger_source: Source
    payload: Started


class EndedReport(ReportBase):
    kind: Literal["session_ended"]
    config_ref: Identity
    session_id: Identity
    trigger_source: Source
    payload: Ended


class FaultReport(ReportBase):
    kind: Literal["fault", "recovered"]
    payload: RequiredReason


class StopProcessedReport(ReportBase):
    kind: Literal["stop_processed"]
    trigger_source: Literal["remote", "local_button"]
    payload: StopProcessed

    @model_validator(mode="after")
    def remote_identity(self):
        if self.trigger_source == "remote" and self.request_id is None:
            raise ValueError("remote STOP needs its request_id")
        return self


class OccurrenceReport(ReportBase):
    kind: Literal["occurrence_decided"]
    trigger_source: Literal["schedule"]
    payload: OccurrenceDecided

    @model_validator(mode="after")
    def executing_ref(self):
        if self.payload.disposition == "started" and self.config_ref is None:
            raise ValueError("a started occurrence needs the installed config_ref")
        return self


Report = Annotated[
    ConfigAppliedReport
    | ConfigRejectedReport
    | RequestReceivedReport
    | RequestRejectedReport
    | StartedReport
    | EndedReport
    | FaultReport
    | StopProcessedReport
    | OccurrenceReport,
    Field(discriminator="kind"),
]


class ExchangeEnvelope(WireModel):
    """Validate the root separately so each bounded report can be checked in isolation."""

    protocol: Literal["migarden.zone-a.v1"]
    device_id: Identity
    boot_id: Identity
    control_epoch: Sequence
    snapshot: Snapshot
    reports: Annotated[list[object], Field(max_length=REPORT_LIMIT)]


class ExchangeIn(WireModel):
    protocol: Literal["migarden.zone-a.v1"]
    device_id: Identity
    boot_id: Identity
    control_epoch: Sequence
    snapshot: Snapshot
    reports: Annotated[list[Report], Field(max_length=REPORT_LIMIT)]


class StartContext(WireModel):
    zone_id: Literal["zone-a"] = ZONE
    binding_ref: Literal["zone-a-v1"] = BINDING
    config_ref: Identity
    boot_id: Identity
    control_epoch: Sequence


class Candidate(StartContext):
    request_id: Identity
    kind: Literal["start"] = "start"
    confirmed_at: UTCDateTime
    expires_at: UTCDateTime
    duration_seconds: Seconds


class Grant(Candidate):
    grant_id: Identity


class Stop(WireModel):
    request_id: Identity
    kind: Literal["stop"] = "stop"
    zone_id: Literal["zone-a"] = ZONE
    binding_ref: Literal["zone-a-v1"] = BINDING
    boot_id: Identity
    confirmed_at: UTCDateTime


class ExchangeOut(WireModel):
    protocol: Literal["migarden.zone-a.v1"] = PROTOCOL
    server_time: UTCDateTime
    desired_config: ConfigurationBundle | None = None
    candidates: Annotated[list[Candidate], Field(max_length=1)] = Field(default_factory=list)
    grants: Annotated[list[Grant], Field(max_length=1)] = Field(default_factory=list)
    stops: Annotated[list[Stop], Field(max_length=1)] = Field(default_factory=list)
    acked_event_ids: Annotated[list[Identity], Field(max_length=REPORT_LIMIT)] = Field(
        default_factory=list
    )
    retry_after_seconds: int | None = None
