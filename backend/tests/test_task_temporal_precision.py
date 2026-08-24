"""Pure temporal-precision contracts for Task DTOs and expand-phase reads."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.domain.models import Task
from app.domain.tasks import (
    TaskCreate,
    TaskScheduleShapeError,
    TaskUpdate,
    _stored_schedule,
)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ("none", None, None)),
        ({"due_at": None}, ("none", None, None)),
        (
            {"due_at": datetime(2026, 8, 24, 2, 30, tzinfo=UTC)},
            ("datetime", None, datetime(2026, 8, 24, 2, 30, tzinfo=UTC)),
        ),
        (
            {"due_precision": "date", "due_on": date(2026, 8, 24)},
            ("date", date(2026, 8, 24), None),
        ),
        (
            {
                "due_precision": "datetime",
                "due_at": datetime(2026, 8, 24, 2, 30, tzinfo=UTC),
            },
            ("datetime", None, datetime(2026, 8, 24, 2, 30, tzinfo=UTC)),
        ),
        ({"due_precision": "none"}, ("none", None, None)),
    ],
)
def test_create_canonicalizes_legacy_and_v2_schedule_shapes(kwargs, expected):
    payload = TaskCreate(title="fixture", **kwargs)
    assert (payload.due_precision, payload.due_on, payload.due_at) == expected
    assert {"due_precision", "due_on", "due_at"} <= payload.model_fields_set


@pytest.mark.parametrize(
    "kwargs",
    [
        {"due_precision": None},
        {"due_on": date(2026, 8, 24)},
        {"due_precision": "date"},
        {
            "due_precision": "date",
            "due_on": date(2026, 8, 24),
            "due_at": datetime(2026, 8, 24, 2, 30, tzinfo=UTC),
        },
        {"due_precision": "datetime"},
        {"due_precision": "datetime", "due_at": datetime(2026, 8, 24, 2, 30)},
        {"due_precision": "none", "due_on": date(2026, 8, 24)},
    ],
)
def test_invalid_schedule_shapes_have_a_stable_machine_error(kwargs):
    with pytest.raises(ValidationError) as caught:
        TaskCreate(title="fixture", **kwargs)
    assert any(error["type"] == "task_schedule_invalid" for error in caught.value.errors())


def test_patch_distinguishes_preserve_from_legacy_clear():
    preserve = TaskUpdate(title="new title")
    assert preserve.model_fields_set == {"title"}
    assert not ({"due_precision", "due_on", "due_at"} & preserve.model_fields_set)

    clear = TaskUpdate(due_at=None)
    assert (clear.due_precision, clear.due_on, clear.due_at) == ("none", None, None)
    assert {"due_precision", "due_on", "due_at"} <= clear.model_fields_set


@pytest.mark.parametrize(
    "payload_type, kwargs",
    [(TaskCreate, {"title": "   "}), (TaskUpdate, {"title": "\t\n"})],
)
def test_task_title_cannot_be_whitespace_only(payload_type, kwargs):
    """The API-side contract matches the disabled whitespace-only form submit."""
    with pytest.raises(ValidationError):
        payload_type(**kwargs)


def test_expand_phase_dual_read_maps_legacy_rows_without_guessing_2359():
    exact_legacy = datetime(2026, 8, 24, 16, 59, tzinfo=UTC)
    assert _stored_schedule(Task(due_precision=None, due_at=None)) == ("none", None, None)
    assert _stored_schedule(Task(due_precision=None, due_at=exact_legacy)) == (
        "datetime",
        None,
        exact_legacy,
    )


def test_expand_phase_read_fails_closed_for_an_invalid_explicit_v2_shape():
    with pytest.raises(TaskScheduleShapeError, match="invalid due schedule shape"):
        _stored_schedule(
            Task(
                due_precision="date",
                due_on=date(2026, 8, 24),
                due_at=datetime(2026, 8, 24, 2, 30, tzinfo=UTC),
            )
        )
