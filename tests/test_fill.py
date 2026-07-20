import random
import time
from unittest import mock

from crossworder import fill
from crossworder.fill import fill_grid
from crossworder.grid import derive_slots
from crossworder.pool import CandidatePool

# 3x3 open grid: three across slots, three down slots, all length 3.
PATTERN = "........."


def make_pool(words: list[str]) -> CandidatePool:
    scores = {w: 60 for w in words}
    return CandidatePool(scores, set(words))


# Six distinct words forming a double word square:
#   rows TEN / ARE / RAT  ->  cols TAR / ERA / NET
# Distinctness matters: the filler forbids repeating a word inside one puzzle,
# so a set whose only solution reuses words (e.g. CAT/ARE/TEN) is unfillable.
SQUARE = ["TEN", "ARE", "RAT", "TAR", "ERA", "NET"]


def test_fills_a_solvable_grid():
    result = fill_grid(PATTERN, 3, make_pool(SQUARE), seed=1)
    assert result is not None
    assert "#" not in result.letters
    assert len(result.letters) == 9


def test_filled_grid_is_internally_consistent():
    result = fill_grid(PATTERN, 3, make_pool(SQUARE), seed=1)
    assert result is not None
    slots = derive_slots(PATTERN, 3)
    for slot in slots:
        word = "".join(result.letters[c] for c in slot.cells)
        assert word == result.answers[slot.index]


def test_no_duplicate_answers_in_one_puzzle():
    result = fill_grid(PATTERN, 3, make_pool(SQUARE), seed=1)
    assert result is not None
    answers = list(result.answers.values())
    assert len(answers) == len(set(answers))


def test_returns_none_when_unfillable():
    pool = make_pool(["XXX"])  # cannot interlock
    assert fill_grid(PATTERN, 3, pool, seed=1, max_restarts=2) is None


# --- Regression tests for the restart / fallback defects -------------------
#
# The tests above only exercise a 3x3 that fills on attempt 0, which is why two
# Critical defects survived: restarts never ran, and `used_fallback` was
# provably always empty. These cover both.


def test_restarts_actually_run_when_a_seed_is_exhausted():
    """Attempt 0 must not consume the whole budget.

    Previously `fill_grid` shared one deadline across all attempts and could not
    tell "search exhausted" from "deadline hit", so the restart loop returned
    None immediately after attempt 0 and the per-attempt seeds were dead code.
    We count distinct rng seeds reaching `_solve` to prove restarts occur.
    """
    seeds_seen = []
    real_solve = fill.__dict__["_solve"]

    def spy(*args, **kwargs):
        rng = args[9] if len(args) > 9 else kwargs["rng"]
        seeds_seen.append(rng.random())
        return real_solve(*args, **kwargs)

    pool = make_pool(["XXX"])  # unfillable: cannot interlock
    with mock.patch.object(fill, "_solve", side_effect=spy):
        result = fill_grid(
            PATTERN, 3, pool, seed=1, max_restarts=5, time_budget_s=5.0
        )

    assert result is None
    # One top-level call per attempt (recursion is via the real function), so
    # more than one distinct starting seed proves restarts executed.
    assert len(set(seeds_seen)) > 1, "restarts did not run"


def test_total_wall_clock_respects_time_budget():
    """The budget is a total across restarts, not per attempt."""
    pool = make_pool(["XXX"])
    start = time.monotonic()
    result = fill_grid(
        PATTERN, 3, pool, seed=1, max_restarts=50, time_budget_s=1.0
    )
    elapsed = time.monotonic() - start
    assert result is None
    assert elapsed < 3.0, f"overran budget: {elapsed:.2f}s"


def test_backtrack_restores_state_after_failed_solve():
    """A failed `_solve` must leave cells/answers/used/domains untouched.

    Domains are saved by reference during propagation; this pins down that the
    restore is genuine and that nothing leaks out of an abandoned branch.
    """
    pool = make_pool(["XXX"])
    slots = derive_slots(PATTERN, 3)
    by_index = {s.index: s for s in slots}
    cell_slots: dict[int, list] = {}
    for slot in slots:
        for cell_idx in slot.cells:
            cell_slots.setdefault(cell_idx, []).append(slot)

    cells = ["" for _ in PATTERN]
    domains = {s.index: pool.matching("?" * s.length) for s in slots}
    answers: dict[int, str] = {}
    used: set[str] = set()
    fallback_slots: set[int] = set()

    cells_before = list(cells)
    domains_before = {i: list(d) for i, d in domains.items()}

    outcome = fill._solve(
        slots, by_index, cell_slots, cells, domains, pool, used, answers,
        fallback_slots, random.Random(0), time.monotonic() + 5.0, False,
    )

    assert outcome is fill.Outcome.EXHAUSTED
    assert cells == cells_before
    assert answers == {}
    assert used == set()
    assert fallback_slots == set()
    assert {i: list(d) for i, d in domains.items()} == domains_before


def test_exhausted_and_deadline_are_distinguishable():
    """The restart loop depends on telling these two apart."""
    pool = make_pool(["XXX"])
    slots = derive_slots(PATTERN, 3)
    by_index = {s.index: s for s in slots}
    cell_slots: dict[int, list] = {}
    for slot in slots:
        for cell_idx in slot.cells:
            cell_slots.setdefault(cell_idx, []).append(slot)

    def run(deadline):
        cells = ["" for _ in PATTERN]
        return fill._solve(
            slots, by_index, cell_slots, cells,
            {s.index: pool.matching("?" * s.length) for s in slots},
            pool, set(), {}, set(), random.Random(0), deadline, False,
        )

    assert run(time.monotonic() + 5.0) is fill.Outcome.EXHAUSTED
    assert run(time.monotonic() - 1.0) is fill.Outcome.DEADLINE


def test_fallback_answers_are_used_and_marked():
    """A grid solvable only via an unclued answer fills and marks that slot.

    NET has no hard clue, so it is absent from the clue-covered pool and the
    square is unfillable from clues alone. The fallback path must supply it and
    `used_fallback` must name exactly that slot.
    """
    pool = CandidatePool({w: 60 for w in SQUARE}, set(SQUARE) - {"NET"})
    assert "NET" not in pool.matching("???")

    result = fill_grid(
        PATTERN, 3, pool, seed=1, max_restarts=5, time_budget_s=5.0
    )
    assert result is not None

    fallback_answers = {result.answers[i] for i in result.used_fallback}
    assert fallback_answers == {"NET"}
    for index, word in result.answers.items():
        assert (index in result.used_fallback) == (not pool.has_hard_clue(word))


def test_early_attempts_stay_purely_clue_covered():
    """Fallback is a last resort: a clue-fillable grid uses none of it."""
    result = fill_grid(PATTERN, 3, make_pool(SQUARE), seed=1)
    assert result is not None
    assert result.used_fallback == set()
