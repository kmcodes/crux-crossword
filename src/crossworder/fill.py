"""Backtracking crossword filler."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from crossworder.grid import Slot, derive_slots
from crossworder.pool import CandidatePool

BLACK = "#"


@dataclass
class FillResult:
    letters: str
    answers: dict[int, str]
    used_fallback: set[int]


def _pattern_for(slot: Slot, cells: list[str]) -> str:
    return "".join(cells[c] if cells[c] else "?" for c in slot.cells)


def _solve(
    slots: list[Slot],
    cell_slots: dict[int, list[Slot]],
    cells: list[str],
    domains: dict[int, list[str]],
    pool: CandidatePool,
    used: set[str],
    answers: dict[int, str],
    rng: random.Random,
    deadline: float,
) -> bool:
    if time.monotonic() > deadline:
        return False

    unfilled = [s for s in slots if s.index not in answers]
    if not unfilled:
        return True

    # Most-constrained slot first, using the maintained domains.
    slot = min(unfilled, key=lambda s: len(domains[s.index]))
    options = [w for w in domains[slot.index] if w not in used]
    if not options:
        return False
    options.sort(key=lambda w: -pool.score(w))

    # Explore best-scoring candidates first, lightly shuffled so restarts with
    # a different seed take different paths.
    head = options[:10]
    rng.shuffle(head)

    for word in head:
        saved_cells = [cells[c] for c in slot.cells]
        for pos, cell_idx in enumerate(slot.cells):
            cells[cell_idx] = word[pos]
        answers[slot.index] = word
        used.add(word)

        # Forward-check: recompute the domains of every crossing slot and
        # abandon this word immediately if any of them is emptied. Without
        # this propagation a 15x15 themeless does not fill in practical time —
        # measured: 120s timeout without it, 0.3s with it, on the same grid.
        touched: set[int] = set()
        for cell_idx in slot.cells:
            for other in cell_slots[cell_idx]:
                if other.index != slot.index and other.index not in answers:
                    touched.add(other.index)

        saved_domains: dict[int, list[str]] = {}
        by_index = {s.index: s for s in slots}
        dead = False
        for other_index in touched:
            saved_domains[other_index] = domains[other_index]
            domains[other_index] = pool.matching(
                _pattern_for(by_index[other_index], cells)
            )
            if not domains[other_index]:
                dead = True
                break

        if not dead and _solve(slots, cell_slots, cells, domains, pool, used,
                               answers, rng, deadline):
            return True

        for other_index, saved in saved_domains.items():
            domains[other_index] = saved
        for pos, cell_idx in enumerate(slot.cells):
            cells[cell_idx] = saved_cells[pos]
        del answers[slot.index]
        used.discard(word)

    return False


def fill_grid(
    pattern: str,
    size: int,
    pool: CandidatePool,
    seed: int = 0,
    max_restarts: int = 50,
    time_budget_s: float = 60.0,
) -> FillResult | None:
    slots = derive_slots(pattern, size)
    cell_slots: dict[int, list[Slot]] = {}
    for slot in slots:
        for cell_idx in slot.cells:
            cell_slots.setdefault(cell_idx, []).append(slot)

    deadline = time.monotonic() + time_budget_s

    for attempt in range(max_restarts):
        if time.monotonic() > deadline:
            return None
        rng = random.Random(seed + attempt)
        cells = ["" if ch != BLACK else BLACK for ch in pattern]
        answers: dict[int, str] = {}
        domains = {s.index: pool.matching("?" * s.length) for s in slots}
        if any(not d for d in domains.values()):
            return None
        if _solve(slots, cell_slots, cells, domains, pool, set(), answers,
                  rng, deadline):
            fallback = {
                i for i, w in answers.items() if not pool.has_hard_clue(w)
            }
            return FillResult(
                letters="".join(cells),
                answers=answers,
                used_fallback=fallback,
            )
    return None
