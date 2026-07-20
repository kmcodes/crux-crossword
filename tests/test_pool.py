import random
import sqlite3
from pathlib import Path

import pytest

from crossworder.ingest import SCHEMA
from crossworder.pool import CandidatePool


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "corpus.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT INTO words VALUES (?,?)",
        [("CAT", 80), ("COT", 70), ("DOG", 60), ("EEL", 55), ("XYZ", 20)],
    )
    con.executemany(
        "INSERT INTO clues VALUES (?,?,?,?)",
        [
            ("CAT", "Feline", 1, 2015),
            ("COT", "Camp bed", 1, 2016),
            ("DOG", "Pet", 0, 2015),   # exists but not a hard clue
            ("EEL", "Slippery one", 1, 2017),
        ],
    )
    con.commit()
    con.close()
    return path


def test_pool_excludes_words_without_hard_clues(db: Path):
    pool = CandidatePool.load(db)
    assert "DOG" not in pool.by_length(3)   # no hard clue
    assert "XYZ" not in pool.by_length(3)   # score below threshold
    assert set(pool.by_length(3)) == {"CAT", "COT", "EEL"}


def test_by_length_orders_by_score_desc(db: Path):
    assert CandidatePool.load(db).by_length(3)[0] == "CAT"


def test_matching_respects_known_letters(db: Path):
    pool = CandidatePool.load(db)
    assert set(pool.matching("C?T")) == {"CAT", "COT"}
    assert pool.matching("???") == pool.by_length(3)
    assert pool.matching("Z??") == []


def test_fallback_includes_words_without_hard_clues(db: Path):
    pool = CandidatePool.load(db)
    assert "DOG" in pool.fallback_matching("DO?")
    assert pool.has_hard_clue("DOG") is False
    assert pool.has_hard_clue("CAT") is True


@pytest.fixture
def big_db(tmp_path: Path) -> Path:
    # A fixture at real-corpus scale, needed to actually expose the ordering
    # bug: CPython's set iteration order for a *dense/small* range of int
    # offsets happens to come out ascending, which is why a handful of
    # words never reproduces the defect (silently passes even against the
    # buggy code). At a few thousand words with a sparse match rate, the
    # offsets matching a given letter are scattered across a much larger
    # hash table and set iteration order visibly diverges from insertion
    # (== score-descending) order -- this is what the real corpus does at
    # matching('C????') (see task-5 defect report). Fixed seed for
    # determinism.
    path = tmp_path / "big_corpus.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    rng = random.Random(7)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    words: list[tuple[str, int]] = []
    seen: set[str] = set()
    while len(words) < 2000:
        first = "C" if rng.random() < 0.15 else rng.choice(letters)
        w = first + "".join(rng.choice(letters) for _ in range(4))
        if w in seen:
            continue
        seen.add(w)
        words.append((w, rng.randint(1, 100)))
    con.executemany("INSERT INTO words VALUES (?,?)", words)
    con.executemany(
        "INSERT INTO clues VALUES (?,?,?,?)",
        [(w, "c", 1, 2020) for w, _ in words],
    )
    con.commit()
    con.close()
    return path


def test_matching_is_score_descending_with_known_letters(big_db: Path):
    # Regression test for the Critical defect: matching() must preserve
    # score-descending order even when the pattern has known letters, not
    # just in the all-unknown fast path. Reproduces the real-corpus failure
    # mode (matching('C????') was not score-descending) at fixture scale.
    pool = CandidatePool.load(big_db)
    result = pool.matching("C????")
    assert len(result) > 50  # sanity: fixture actually exercises the index
    scores = [pool.score(w) for w in result]
    assert scores == sorted(scores, reverse=True), (
        f"matching() with known letters is not score-descending: "
        f"first 15 scores = {scores[:15]}"
    )


def test_matching_is_score_descending_all_unknown(big_db: Path):
    pool = CandidatePool.load(big_db)
    result = pool.matching("?????")
    scores = [pool.score(w) for w in result]
    assert scores == sorted(scores, reverse=True)


def test_matching_result_is_not_aliased_to_internal_state(db: Path):
    pool = CandidatePool.load(db)
    result = pool.matching("C?T")
    result.append("MUTATED")
    result.clear()
    assert pool.matching("C?T") == ["CAT", "COT"]


def test_by_length_result_is_not_aliased_to_internal_state(db: Path):
    pool = CandidatePool.load(db)
    result = pool.by_length(3)
    result.append("MUTATED")
    result.clear()
    assert set(pool.by_length(3)) == {"CAT", "COT", "EEL"}


def test_matching_matches_naive_scan(db: Path):
    pool = CandidatePool.load(db)
    for pattern in ["C?T", "???", "?A?", "??T", "Z??", "C??"]:
        naive = {
            a for a in pool.by_length(len(pattern))
            if CandidatePool._matches(a, pattern)
        }
        assert set(pool.matching(pattern)) == naive
