"""Completion groups, snapshot validation and deterministic move-to-top semantics."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domain.notes import NoteMoveToTop, NoteOrderEntry, move_to_top_order


def entries():
    return [
        NoteOrderEntry(id=UUID(int=index + 1), position=index * 3, is_completed=index % 2 == 1)
        for index in range(5)
    ]


@pytest.mark.parametrize("target,expected", [(5, [5, 2, 1, 4, 3]), (4, [1, 4, 3, 2, 5])])
def test_move_preserves_other_group_slots_and_relative_order(target, expected):
    before = entries()
    moved = move_to_top_order(before, UUID(int=target))
    assert [item.id.int for item in moved] == expected
    assert [item.position for item in moved] == list(range(5))
    assert {item.id: item.is_completed for item in moved} == {
        item.id: item.is_completed for item in before
    }
    assert move_to_top_order(moved, UUID(int=target)) == moved
    assert [item.position for item in before] == [0, 3, 6, 9, 12]


def test_already_first_is_a_true_noop_even_with_gapped_positions():
    before = entries()
    assert move_to_top_order(before, before[0].id) is before


@pytest.mark.parametrize("bad", [[], [entries()[0], entries()[0]]])
def test_snapshot_rejects_empty_or_duplicate_members(bad):
    with pytest.raises(ValidationError):
        NoteMoveToTop(expected_items=bad)


@pytest.mark.parametrize("position,completed", [(-1, False), (True, False), (1, "false")])
def test_snapshot_requires_typed_nonnegative_rank_and_boolean(position, completed):
    with pytest.raises(ValidationError):
        NoteOrderEntry(id=UUID(int=1), position=position, is_completed=completed)
