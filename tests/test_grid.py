from collections import Counter

from crossworder.grid import (
    crossings,
    derive_slots,
    slot_length_profile,
    slot_numbers,
)

# 5x5, one black square in the centre.
PATTERN = (
    "....."
    "....."
    "..#.."
    "....."
    "....."
)


def test_derives_across_and_down_slots():
    slots = derive_slots(PATTERN, 5)
    across = [s for s in slots if s.direction == "A"]
    down = [s for s in slots if s.direction == "D"]
    # Rows 0,1,3,4 give one 5-length slot each; row 2 splits into two 2-length.
    assert sorted(s.length for s in across) == [2, 2, 5, 5, 5, 5]
    assert sorted(s.length for s in down) == [2, 2, 5, 5, 5, 5]


def test_slots_shorter_than_three_are_still_returned():
    slots = derive_slots(PATTERN, 5)
    assert any(s.length == 2 for s in slots)


def test_crossings_are_symmetric():
    slots = derive_slots(PATTERN, 5)
    cross = crossings(slots)
    for i, links in cross.items():
        for other, pos_here, pos_there in links:
            assert (i, pos_there, pos_here) in [
                (o, a, b) for o, a, b in cross[other]
            ]


def test_first_across_slot_cell_indices():
    slots = derive_slots(PATTERN, 5)
    first = next(s for s in slots if s.direction == "A" and s.row == 0)
    assert first.cells == [0, 1, 2, 3, 4]


def test_slot_length_profile_counts_lengths():
    profile = slot_length_profile(derive_slots(PATTERN, 5))
    assert profile == Counter({5: 8, 2: 4})


def test_across_and_down_starting_in_same_cell_share_a_number():
    slots = derive_slots(PATTERN, 5)
    numbers = slot_numbers(slots, 5)
    across_at_origin = next(
        s for s in slots if s.direction == "A" and (s.row, s.col) == (0, 0)
    )
    down_at_origin = next(
        s for s in slots if s.direction == "D" and (s.row, s.col) == (0, 0)
    )
    assert numbers[across_at_origin.index] == 1
    assert numbers[down_at_origin.index] == 1


def test_numbers_increase_in_reading_order():
    slots = derive_slots(PATTERN, 5)
    numbers = slot_numbers(slots, 5)
    ordered = sorted(slots, key=lambda s: (s.row, s.col))
    seen = [numbers[s.index] for s in ordered]
    assert seen == sorted(seen)
