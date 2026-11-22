"""Bounded process-local scheduling only. This state never authorizes device work."""

from dataclasses import dataclass, field
from time import monotonic

from fastapi import Request

from app.domain.migarden.wire import ExchangeEnvelope

EXTENSION = "quiet-health-v1"
RECONCILE_SECONDS = 6 * 60 * 60
HUMAN_SECONDS = 5 * 60
TAIL_SECONDS = 10 * 60


def context(packet: ExchangeEnvelope) -> tuple:
    s = packet.snapshot
    # Timestamp/elapsed and optional health cannot keep an idle database awake.
    return (
        packet.device_id,
        packet.boot_id,
        packet.control_epoch,
        s.output,
        s.applied_config_ref,
        s.ready,
        s.blocked_reason,
        s.time_quality,
        s.active_session.session_id if s.active_session else None,
    )


@dataclass
class QuietGate:
    key: tuple | None = None
    reconcile_at: float = 0
    human_until: float = 0
    tail_until: float = 0
    failures: int = 0
    retry_at: float = 0
    busy: bool = False
    active: bool = False
    routing_hash: str | None = None
    routing_device: str | None = None
    routing_loaded: bool = False
    routing_until: float = 0
    bootstrap_busy: bool = False
    bootstrap_retry_at: float = 0
    bootstrap_failures: int = 0
    # A singleton gate, no map indexed by arbitrary tokens, IDs or report bodies.
    clock: object = field(default=monotonic, repr=False)

    def now(self) -> float:
        return self.clock()

    def present(self, seconds: float = HUMAN_SECONDS) -> None:
        self.human_until = max(self.human_until, self.now() + min(HUMAN_SECONDS, max(0, seconds)))

    def known(self, token_hash: str, device_id: str) -> bool:
        return token_hash == self.routing_hash and device_id == self.routing_device

    def remember_zone(self, zone) -> None:
        # Read-only routing information, never authentication or a grant. Even a
        # bad first credential can hydrate this hint for the genuine Controller.
        self.routing_hash = zone.token_hash if zone and zone.revoked_at is None else None
        self.routing_device = zone.device_id if zone else None
        self.routing_loaded = True
        self.routing_until = self.now() + RECONCILE_SECONDS
        self.bootstrap_failures = 0
        self.bootstrap_retry_at = 0

    def bootstrap(self) -> bool:
        now = self.now()
        if self.bootstrap_busy or now < self.bootstrap_retry_at:
            return False
        if self.routing_loaded and now < self.routing_until:
            return False
        self.bootstrap_busy = True
        return True

    def bootstrap_failed(self) -> None:
        self.bootstrap_failures = min(self.bootstrap_failures + 1, 4)
        self.bootstrap_retry_at = self.now() + (5, 15, 30, 60)[self.bootstrap_failures - 1]

    def enter(self, token_hash: str, packet: ExchangeEnvelope, negotiated: bool) -> bool:
        now = self.now()
        # Even genuine activity bypasses only soft idle waiting, never fault backoff.
        if self.busy or now < self.retry_at:
            return False
        key = (token_hash, context(packet))
        work = bool(
            packet.reports or packet.snapshot.active_session or packet.snapshot.output != "off"
        )
        if (
            negotiated
            and key == self.key
            and not work
            and now < self.reconcile_at
            and now >= max(self.human_until, self.tail_until)
        ):
            return False
        self.busy = True
        return True

    def failed(self) -> None:
        self.busy = False
        self.failures = min(self.failures + 1, 4)
        # Real work recovers with short bounded backoff. Six hours is only idle.
        self.retry_at = self.now() + (5, 15, 30, 60)[self.failures - 1]

    def committed(self, token_hash: str, packet: ExchangeEnvelope, *, terminal: bool) -> None:
        now = self.now()
        active = packet.snapshot.output == "on" or packet.snapshot.active_session is not None
        if terminal or (self.active and not active):
            self.tail_until = now + TAIL_SECONDS
        self.active = active
        self.key = (token_hash, context(packet))
        self.reconcile_at = now + RECONCILE_SECONDS
        self.failures = 0
        self.retry_at = 0
        self.busy = False


def gate(request: Request) -> QuietGate:
    if not hasattr(request.app.state, "migarden_quiet"):
        request.app.state.migarden_quiet = QuietGate()
    return request.app.state.migarden_quiet
