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
