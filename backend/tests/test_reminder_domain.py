"""Pure unit tests for reminder payload generation and privacy rules."""

from datetime import date
from uuid import UUID

from app.domain.models import Subscription, Tracker
from app.domain.reminder import (
    build_medication_payload,
    build_subscription_expiry_payload,
)

DISPATCH_ID = UUID("01912345-6789-7000-8000-000000000000")


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
    assert payload["body"] == "Đã tới giờ uống thuốc"
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
    assert payload["body"] == "Đã tới giờ: Thuốc Huyết Áp"


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
    payload = build_subscription_expiry_payload(sub, parent_tracker=None, lead_days=3)

    assert payload["title"] == "Hạn đăng ký microSched"
    assert "secret_sub" not in payload["body"]
    assert "enc:v1:" not in payload["body"]
    assert "Một đăng ký sắp hết hạn" in payload["body"]
    assert payload["url"] == f"/subscription?highlight={sub.id}"
