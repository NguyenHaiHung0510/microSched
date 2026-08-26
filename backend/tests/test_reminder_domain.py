"""Pure unit tests for reminder payload generation and privacy rules."""

import inspect
from datetime import date
from uuid import UUID

import app.domain.reminder as reminder_module
from app.domain.models import Subscription, Tracker
from app.domain.reminder import (
    build_medication_payload,
    build_subscription_expiry_payload,
    build_tracker_reminder_payload,
    confirm_reminder_dispatch,
)

DISPATCH_ID = UUID("01912345-6789-7000-8000-000000000000")


def test_confirmation_requires_the_verified_auth_session() -> None:
    """Confirmation must not recreate a session from a boolean unlock hint."""
    parameters = inspect.signature(confirm_reminder_dispatch).parameters

    assert "is_private_unlocked" not in parameters
    assert parameters["auth"].default is inspect.Parameter.empty


def test_medication_payload_private_tracker_without_text():
    """Private tracker without custom text MUST NOT leak tracker name or ciphertext."""
    tracker = Tracker(
        id=UUID("01912345-6789-7000-8000-000000000001"),
        name="enc:v1:secretname",
        kind="health",
        input_mode="event",
        is_private=True,
        reminder_text=None,
    )
    payload = build_medication_payload(tracker, DISPATCH_ID)

    assert payload["title"] == "Nhắc nhở microSched"
    assert payload["body"] == "Đã tới hạn ghi nhận."
    assert "secretname" not in payload["body"]
    assert "enc:v1:" not in payload["body"]
    assert payload["url"] == f"/reminder-confirm?dispatch={DISPATCH_ID}"


def test_medication_payload_private_tracker_with_text():
    """Private tracker with reminder_text uses public user-chosen text."""
    tracker = Tracker(
        id=UUID("01912345-6789-7000-8000-000000000002"),
        name="enc:v1:secretname",
        kind="health",
        input_mode="event",
        is_private=True,
        reminder_text="Uống 1 viên sau ăn sáng",
    )
    payload = build_medication_payload(tracker, DISPATCH_ID)

    assert payload["title"] == "Nhắc nhở microSched"
    assert payload["body"] == "Uống 1 viên sau ăn sáng"
    assert "secretname" not in payload["body"]


def test_medication_payload_public_tracker():
    """Public tracker displays tracker name in payload."""
    tracker = Tracker(
        id=UUID("01912345-6789-7000-8000-000000000003"),
        name="Thuốc Huyết Áp",
        kind="health",
        input_mode="event",
        is_private=False,
        reminder_text=None,
    )
    payload = build_medication_payload(tracker, DISPATCH_ID)

    assert payload["title"] == "Nhắc nhở microSched"
    assert payload["body"] == "Đã tới hạn: Thuốc Huyết Áp"


def test_medication_payload_decrypts_public_tracker_name(monkeypatch):
    """A public stored name is ciphertext at rest but must be readable in its push."""
    tracker = Tracker(
        id=UUID("01912345-6789-7000-8000-000000000013"),
        name="enc:v1:stored-name",
        kind="health",
        input_mode="event",
        is_private=False,
        reminder_text=None,
    )
    monkeypatch.setattr(reminder_module.crypto, "decrypt", lambda _: "Thuốc Huyết Áp")
    payload = build_medication_payload(tracker, DISPATCH_ID)

    assert payload["body"] == "Đã tới hạn: Thuốc Huyết Áp"


def test_generic_open_tracker_payload_never_uses_confirmation_url():
    tracker = Tracker(
        id=UUID("01912345-6789-7000-8000-000000000016"),
        name="Việc chung",
        kind="general",
        input_mode="money",
        is_private=False,
    )

    payload = build_tracker_reminder_payload(
        tracker,
        DISPATCH_ID,
        reminder_mode="fixed",
        reminder_interval_days=3,
        reminder_action="open_tracker",
        today_vn=date(2026, 8, 26),
    )

    assert payload["url"] == "/trackers"
    assert "reminder-confirm" not in payload["url"]


def test_after_entry_payload_uses_vn_freshness_for_public_tracker():
    tracker = Tracker(
        id=UUID("01912345-6789-7000-8000-000000000017"),
        name="Tập luyện",
        kind="general",
        input_mode="event",
        is_private=False,
    )
    payload = build_tracker_reminder_payload(
        tracker,
        DISPATCH_ID,
        reminder_mode="after_entry",
        reminder_interval_days=3,
        reminder_action="confirm_event",
        today_vn=date(2026, 8, 26),
        last_entry_date=date(2026, 8, 20),
    )

    assert payload["body"] == "Đã 6 ngày chưa ghi nhận: Tập luyện"
    assert payload["url"] == f"/reminder-confirm?dispatch={DISPATCH_ID}"
    assert "enc:v1:" not in payload["body"]


def test_subscription_expiry_payload_private():
    """Private subscription payload MUST NOT leak subscription name."""
    sub = Subscription(
        id=UUID("01912345-6789-7000-8000-000000000004"),
        tracker_id=UUID("01912345-6789-7000-8000-000000000005"),
        name="enc:v1:secret_sub",
        started_on=date(2026, 1, 1),
        expires_on=date(2026, 8, 10),
        period_count=1,
        period_unit="month",
        is_private=True,
    )
    parent = Tracker(
        id=sub.tracker_id,
        name="enc:v1:private-parent",
        kind="finance",
        input_mode="money",
        is_private=True,
    )
    payload = build_subscription_expiry_payload(sub, parent_tracker=parent, lead_days=3)

    assert payload["title"] == "Hạn đăng ký microSched"
    assert "secret_sub" not in payload["body"]
    assert "enc:v1:" not in payload["body"]
    assert "Một đăng ký sắp hết hạn" in payload["body"]


def test_subscription_expiry_payload_decrypts_public_name(monkeypatch):
    sub = Subscription(
        id=UUID("01912345-6789-7000-8000-000000000014"),
        tracker_id=UUID("01912345-6789-7000-8000-000000000015"),
        name="enc:v1:stored-subscription",
        started_on=date(2026, 1, 1),
        expires_on=date(2026, 8, 10),
        period_count=1,
        period_unit="month",
    )
    parent = Tracker(
        id=sub.tracker_id,
        name="enc:v1:public-parent",
        kind="finance",
        input_mode="money",
        is_private=False,
    )
    monkeypatch.setattr(reminder_module.crypto, "decrypt", lambda _: "Netflix")
    payload = build_subscription_expiry_payload(
        sub, parent_tracker=parent, lead_days=3, today=date(2026, 8, 6)
    )

    assert payload["body"] == "Đăng ký Netflix sắp hết hạn trong 4 ngày"
    assert "enc:v1:" not in payload["body"]
    assert payload["url"] == f"/subscription?highlight={sub.id}"


def test_subscription_expiry_payload_days_left_uses_vn_today():
    """days_left must follow the VN business day passed in, not the server clock.

    Boundary (F13): at 00:00 UTC (07:00 VN) ``date.today()`` in UTC is still
    yesterday, so a naive implementation reports one extra day. The function
    takes ``today`` explicitly; the caller passes ``datetime.now(+07:00).date()``.
    """
    sub = Subscription(
        id=UUID("01912345-6789-7000-8000-000000000006"),
        tracker_id=UUID("01912345-6789-7000-8000-000000000007"),
        name="enc:v1:secret_sub",
        started_on=date(2026, 1, 1),
        expires_on=date(2026, 8, 10),
        period_count=1,
        period_unit="month",
        is_private=True,
    )
    # VN "today" is 2026-08-06 → exactly 4 days left.
    payload = build_subscription_expiry_payload(
        sub, parent_tracker=None, lead_days=3, today=date(2026, 8, 6)
    )
    assert "trong 4 ngày" in payload["body"]

    # A UTC-naive date.today() on 2026-08-05 23:00 UTC (2026-08-06 06:00 VN)
    # would report 5 days — the explicit VN date keeps it at 4.
    payload_next = build_subscription_expiry_payload(
        sub, parent_tracker=None, lead_days=3, today=date(2026, 8, 7)
    )
    assert "trong 3 ngày" in payload_next["body"]
