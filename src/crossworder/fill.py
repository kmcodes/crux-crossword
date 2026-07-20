"""Backtracking crossword filler."""
from __future__ import annotations

import enum
import random
import time
from dataclasses import dataclass, field

from crossworder.grid import Slot, derive_slots
from crossworder.pool import CandidatePool

BLACK = "#"

# Restarts before the full-wordlist fallback is offered as a last resort. Early
# attempts stay purely clue-covered so a grid that can be filled from the hard
# clue bank alone always is; only once fresh seeds have failed on their own do
# we widen the pool and accept answers Task 7 will penalise.
FALLBACK_AFTER_ATTEMPTS = 2


class Outcome(enum.Enum):
    """Why `_solve` returned.

    The caller must tell these apart: EXHAUSTED means this seed's search tree
    was fully explored and a different seed is worth trying, while DEADLINE
    means we ran out of time and any further attempt would be cut short too.
    Collapsing both into `False` is what made restarts dead code previously.
    """

    SOLVED = "solved"
    EXHAUSTED = "exhausted"
    DEADLINE = "deadline"


@dataclass
class FillResult:
    letters: str
    answers: dict[int, str]
    used_fallback: set[int] = field(default_factory=set)


def _pattern_for(slot: Slot, cells: list[str]) -> str:
    return "".join(cells[c] if cells[c] else "?" for c in slot.cells)


def _domain_for(
    slot: Slot,
    cells: list[str],
    pool: CandidatePool,
    allow_fallback: bool,
) -> list[str]:
    """Candidates for a slot given the letters currently on the grid.

    The clue-covered pool is strongly preferred; the full wordlist is consulted
    only when the covered pool has nothing for this pattern. This has to happen
    here, inside propagation, rather than at slot-selection time: forward
    checking abandons a branch the moment any crossing slot's domain empties, so
    a slot whose covered domain is empty is never reached by selection at all.
    """
    covered = pool.matching(_pattern_for(slot, cells))
    if covered or not allow_fallback:
        return covered
    return pool.fallback_matching(_pattern_for(slot, cells))


def _solve(
    slots: list[Slot],
    by_index: dict[int, Slot],
    cell_slots: dict[int, list[Slot]],
    cells: list[str],
    domains: dict[int, list[str]],
    pool: CandidatePool,
    used: set[str],
    answers: dict[int, str],
    fallback_slots: set[int],
    rng: random.Random,
    deadline: float,
    allow_fallback: bool,
) -> Outcome:
    if time.monotonic() > deadline:
        return Outcome.DEADLINE

    unfilled = [s for s in slots if s.index not in answers]
    if not unfilled:
        return Outcome.SOLVED

    # Most-constrained slot first, using the maintained domains.
    slot = min(unfilled, key=lambda s: len(domains[s.index]))
    options = [w for w in domains[slot.index] if w not in used]
    if not options:
        return Outcome.EXHAUSTED
    options.sort(key=lambda w: -pool.score(w))

    # Explore best-scoring candidates first, lightly shuffled so restarts with
    # a different seed take different paths.
    head = options[:10]
    rng.shuffle(head)

    hit_deadline = False
    for word in head:
        saved_cells = [cells[c] for c in slot.cells]
        for pos, cell_idx in enumerate(slot.cells):
            cells[cell_idx] = word[pos]
        answers[slot.index] = word
        used.add(word)
        # A placed word without a hard clue can only have come from
        # `fallback_matching`, since `matching` draws solely from the
        # clue-covered pool. Record it so Task 7 can penalise it.
        if not pool.has_hard_clue(word):
            fallback_slots.add(slot.index)

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
        dead = False
        for other_index in touched:
            # Saved by reference, not copied: the loop below rebinds
            # `domains[other_index]` to a fresh list returned by
            # `pool.matching` rather than mutating the existing list in place,
            # so the saved alias still refers to the untouched pre-propagation
            # list and restoring it is sound.
            saved_domains[other_index] = domains[other_index]
            domains[other_index] = _domain_for(
                by_index[other_index], cells, pool, allow_fallback
            )
            if not domains[other_index]:
                dead = True
                break

        if not dead:
            result = _solve(
                slots, by_index, cell_slots, cells, domains, pool, used,
                answers, fallback_slots, rng, deadline, allow_fallback,
            )
            if result is Outcome.SOLVED:
                return Outcome.SOLVED
            if result is Outcome.DEADLINE:
                hit_deadline = True

        for other_index, saved in saved_domains.items():
            domains[other_index] = saved
        for pos, cell_idx in enumerate(slot.cells):
            cells[cell_idx] = saved_cells[pos]
        del answers[slot.index]
        used.discard(word)
        fallback_slots.discard(slot.index)

        if hit_deadline:
            return Outcome.DEADLINE

    return Outcome.EXHAUSTED


def fill_grid(
    pattern: str,
    size: int,
    pool: CandidatePool,
    seed: int = 0,
    max_restarts: int = 4,
    time_budget_s: float = 60.0,
) -> FillResult | None:
    slots = derive_slots(pattern, size)
    by_index = {s.index: s for s in slots}
    cell_slots: dict[int, list[Slot]] = {}
    for slot in slots:
        for cell_idx in slot.cells:
            cell_slots.setdefault(cell_idx, []).append(slot)

    start = time.monotonic()
    overall_deadline = start + time_budget_s
    # Each attempt gets its own slice of the budget so a single hard seed
    # cannot consume the whole allowance and starve every restart. The total
    # stays bounded by `time_budget_s` because every per-attempt deadline is
    # clamped to `overall_deadline`.
    attempts = max(1, max_restarts)
    slice_s = time_budget_s / attempts

    base_domains = {s.index: pool.matching("?" * s.length) for s in slots}
    # A slot with no clue-covered candidates at all is only hopeless if the
    # fallback cannot serve it either; otherwise the later fallback-enabled
    # attempts still stand a chance.
    if any(not d for d in base_domains.values()):
        if max_restarts <= FALLBACK_AFTER_ATTEMPTS or any(
            not pool.fallback_matching("?" * s.length) for s in slots
        ):
            return None

    for attempt in range(attempts):
        now = time.monotonic()
        if now >= overall_deadline:
            return None
        attempt_deadline = min(now + slice_s, overall_deadline)
        rng = random.Random(seed + attempt)
        cells = ["" if ch != BLACK else BLACK for ch in pattern]
        answers: dict[int, str] = {}
        fallback_slots: set[int] = set()
        allow_fallback = attempt >= FALLBACK_AFTER_ATTEMPTS
        if allow_fallback:
            domains = {
                s.index: _domain_for(s, cells, pool, True) for s in slots
            }
        else:
            domains = {i: list(d) for i, d in base_domains.items()}
        outcome = _solve(
            slots, by_index, cell_slots, cells, domains, pool, set(), answers,
            fallback_slots, rng, attempt_deadline, allow_fallback,
        )
        if outcome is Outcome.SOLVED:
            return FillResult(
                letters="".join(cells),
                answers=answers,
                used_fallback=fallback_slots,
            )
        # EXHAUSTED: this seed's tree is fully explored, so a fresh seed is
        # worth trying. DEADLINE: only this attempt's slice ran out, so keep
        # going while the overall budget survives.
    return None
