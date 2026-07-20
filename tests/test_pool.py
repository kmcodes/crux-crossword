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
