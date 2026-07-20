"""Turn a black-square pattern into the slots a filler must satisfy."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

BLACK = "#"


@dataclass(frozen=True)
class Slot:
    index: int
    direction: str
    row: int
    col: int
    length: int
    cells: list[int]


def derive_slots(pattern: str, size: int) -> list[Slot]:
    slots: list[Slot] = []

    def cell(r: int, c: int) -> str:
        return pattern[r * size + c]

    idx = 0
    for r in range(size):
        c = 0
        while c < size:
            if cell(r, c) == BLACK:
                c += 1
                continue
            start = c
            while c < size and cell(r, c) != BLACK:
                c += 1
            length = c - start
            if length >= 2:
                slots.append(
                    Slot(idx, "A", r, start, length,
                         [r * size + x for x in range(start, c)])
                )
                idx += 1

    for c in range(size):
        r = 0
        while r < size:
            if cell(r, c) == BLACK:
                r += 1
                continue
            start = r
            while r < size and cell(r, c) != BLACK:
                r += 1
            length = r - start
            if length >= 2:
                slots.append(
                    Slot(idx, "D", start, c, length,
                         [x * size + c for x in range(start, r)])
                )
                idx += 1

    return slots


def crossings(slots: list[Slot]) -> dict[int, list[tuple[int, int, int]]]:
    """Map each slot to the slots it intersects and where they touch."""
    cell_to_slots: dict[int, list[tuple[int, int]]] = {}
    for slot in slots:
        for pos, cell_idx in enumerate(slot.cells):
            cell_to_slots.setdefault(cell_idx, []).append((slot.index, pos))

    result: dict[int, list[tuple[int, int, int]]] = {s.index: [] for s in slots}
    for occupants in cell_to_slots.values():
        for i, (slot_i, pos_i) in enumerate(occupants):
            for slot_j, pos_j in occupants[i + 1:]:
                result[slot_i].append((slot_j, pos_i, pos_j))
                result[slot_j].append((slot_i, pos_j, pos_i))
    return result


def slot_length_profile(slots: list[Slot]) -> Counter:
    return Counter(s.length for s in slots)


def slot_numbers(slots: list[Slot], size: int) -> dict[int, int]:
    """Assign true crossword numbers: slot index -> printed number.

    Crossword numbering is a property of the grid, not of the clue list. Cells
    are scanned in reading order and each cell that starts an entry takes the
    next number, so an across and a down entry beginning in the same cell share
    one number (1-Across and 1-Down). Numbering each direction separately is a
    common and very visible bug.
    """
    starts: dict[int, list[int]] = {}
    for slot in slots:
        starts.setdefault(slot.row * size + slot.col, []).append(slot.index)

    numbers: dict[int, int] = {}
    next_number = 1
    for cell_idx in sorted(starts):
        for slot_index in starts[cell_idx]:
            numbers[slot_index] = next_number
        next_number += 1
    return numbers
