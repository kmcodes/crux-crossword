import random
import sqlite3
from pathlib import Path

import pytest

from crossworder.clue import ClueBank, score_difficulty
from crossworder.grid import derive_slots
from crossworder.ingest import SCHEMA


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "corpus.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT INTO clues VALUES (?,?,?,?)",
        [
            ("CAT", "Feline", 1, 2015),
            ("CAT", "A CAT is this", 1, 2016),   # contains its own answer
            ("CAT", "Common pet", 0, 2010),
            ("ARE", "Exist", 0, 2011),
        ],
    )
    con.commit()
    con.close()
    return path


def test_pick_prefers_hard_clues(db: Path):
    bank = ClueBank.load(db)
    text, from_hard = bank.pick("CAT", random.Random(0))
    assert from_hard is True
    assert text == "Feline"


def test_pick_never_returns_clue_containing_answer(db: Path):
    bank = ClueBank.load(db)
    for seed in range(20):
        text, _ = bank.pick("CAT", random.Random(seed))
        assert "CAT" not in text.upper()


def test_pick_falls_back_to_easy_clue(db: Path):
    bank = ClueBank.load(db)
    text, from_hard = bank.pick("ARE", random.Random(0))
    assert text == "Exist"
    assert from_hard is False


def test_pick_returns_none_for_unknown_answer(db: Path):
    assert ClueBank.load(db).pick("ZZZZ", random.Random(0)) is None


def test_difficulty_rises_when_all_clues_are_hard(db: Path):
    bank = ClueBank.load(db)
    slots = derive_slots("." * 9, 3)
    answers = {s.index: "CAT" for s in slots}
    all_hard = score_difficulty(answers, {s.index: True for s in slots}, bank, slots)
    none_hard = score_difficulty(answers, {s.index: False for s in slots}, bank, slots)
    assert 1 <= none_hard <= all_hard <= 5
    assert all_hard > none_hard
