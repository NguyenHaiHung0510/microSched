"""Public copy completeness, private abstraction and Unicode push size contracts."""

import json
from datetime import UTC, date, datetime
from uuid import uuid7

from app.agent.notifications import visible_text
from app.domain.models import DayAnnotation, OneShotReminder, Subscription, Task, Tracker
from app.domain.notification_content import (
    MORE_TEXT,
    PRIVATE_BODY,
    PRIVATE_TITLE,
    PUSH_JSON_MAX_BYTES,
    encode_push_payload,
)
from app.domain.one_shot_delivery import build_one_shot_payload
from app.domain.reminder import build_medication_payload, build_subscription_expiry_payload


def reminder():
    return OneShotReminder(id=uuid7(), mode="absolute", due_at=datetime(2030, 1, 2, tzinfo=UTC))


def test_public_task_keeps_detail_and_checklist_beyond_old_short_copy_caps():
    body = "Nội dung đầy đủ. " * 30
    source = Task(title="Đọc tài liệu", body_md=body, due_precision="date", due_on=date(2030, 1, 3))
    payload = build_one_shot_payload(reminder(), source, ["☐ Đọc chương đầu", "☑ Ghi chú"])
    assert payload["title"] == "Nhắc: Đọc tài liệu"
    assert body.strip() in payload["body"]
    assert "☐ Đọc chương đầu" in payload["body"]
    assert "03/01/2030" in payload["body"]
    assert len(payload["body"]) > 240


def test_private_task_does_not_emit_label_body_checklist_or_time():
    source = Task(
        title="SECRET_TITLE",
        body_md="SECRET_BODY",
        is_private=True,
        due_precision="date",
        due_on=date(2030, 1, 3),
    )
    payload = build_one_shot_payload(reminder(), source, ["SECRET_CHILD"])
    assert payload["title"] == PRIVATE_TITLE and payload["body"] == PRIVATE_BODY
    assert "SECRET" not in json.dumps(payload)
    assert "2030" not in payload["body"]


def test_day_marker_public_range_note_and_private_abstraction():
    source = DayAnnotation(
        label="Ngày kỷ niệm",
        starts_on=date(2030, 1, 2),
        ends_on=date(2030, 1, 4),
        note_md="Dành thời gian cho gia đình",
    )
    payload = build_one_shot_payload(reminder(), source)
    assert payload["title"] == "Mốc ngày: Ngày kỷ niệm"
    assert "02/01/2030 – 04/01/2030" in payload["body"]
    assert source.note_md in payload["body"]
    source.is_private = True
    hidden = build_one_shot_payload(reminder(), source)
    assert hidden["body"] == PRIVATE_BODY
    assert source.label not in str(hidden) and source.note_md not in str(hidden)


def test_private_tracker_custom_reminder_text_is_not_a_public_exception():
    source = Tracker(name="PRIVATE_LABEL", reminder_text="PRIVATE_CUSTOM", is_private=True)
    payload = build_medication_payload(source, uuid7())
    assert payload["title"] == PRIVATE_TITLE and payload["body"] == PRIVATE_BODY
    assert "PRIVATE_" not in str(payload)


def test_subscription_missing_parent_cannot_be_assumed_public():
    source = Subscription(
        id=uuid7(),
        tracker_id=uuid7(),
        name="PRIVATE_NAME",
        amount="PRIVATE_AMOUNT",
        started_on=date(2029, 1, 1),
        expires_on=date(2030, 1, 3),
        note_md="PRIVATE_NOTE",
    )
    payload = build_subscription_expiry_payload(source, None, 3, date(2030, 1, 1))
    assert "PRIVATE_" not in str(payload)
    assert "2030" not in payload["body"] and "2 ngày" not in payload["body"]


def test_payload_keeps_full_copy_when_within_transport_budget():
    payload = {
        "title": "Nhắc: tiếng Việt",
        "body": "Nội dung có dấu 🌸 " * 35,
        "url": "/?reminders=1",
        "tag": "synthetic-tag",
    }
    assert len(payload["body"]) > 240
    assert json.loads(encode_push_payload(payload)) == payload


def test_long_payload_fits_utf8_transport_and_keeps_target_and_full_original():
    original = "Tiếng Việt 🌸漢字 " * 3000
    payload = {
        "title": "Nhắc công việc",
        "body": original,
        "url": "/?reminders=1&reminder=opaque-id",
        "tag": "opaque-tag",
    }
    encoded = encode_push_payload(payload)
    sent = json.loads(encoded)
    assert len(encoded.encode("utf-8")) <= PUSH_JSON_MAX_BYTES
    assert sent["url"] == payload["url"] and sent["tag"] == payload["tag"]
    assert sent["body"].endswith(MORE_TEXT) and "�" not in sent["body"]
    assert original.startswith(sent["body"][: -len(MORE_TEXT)])
    assert payload["body"] == original


def test_mimi_copy_has_no_arbitrary_80_or_240_character_cap():
    full = "Nội dung public dài " * 50
    assert len(visible_text(full)) > 240
    assert visible_text(full) == full.strip()
