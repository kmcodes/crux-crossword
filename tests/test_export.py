import sqlite3
from pathlib import Path

from crossworder.export import PACK_SCHEMA, validate_pack


# Rows TEN / ARE / RAT, columns TAR / ERA / NET — six distinct words.
SOLUTION = "TENARERAT"

# True crossword numbering: 1-Across and 1-Down share the cell (0,0).
FULL_CLUES = [
    (1, "A", 1, 0, 0, 3, "Count", "TEN"),
    (1, "A", 4, 1, 0, 3, "Exist", "ARE"),
    (1, "A", 5, 2, 0, 3, "Rodent", "RAT"),
    (1, "D", 1, 0, 0, 3, "Pitch", "TAR"),
    (1, "D", 2, 0, 1, 3, "Age", "ERA"),
    (1, "D", 3, 0, 2, 3, "Court divider", "NET"),
]


def _make_pack(path: Path, clues: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.executescript(PACK_SCHEMA)
    con.execute(
        "INSERT INTO puzzles VALUES (1, 3, 4, ?, ?, '2026-07-20')",
        ("." * 9, SOLUTION),
    )
    con.executemany("INSERT INTO puzzle_clues VALUES (?,?,?,?,?,?,?,?)", clues)
    con.commit()
    con.close()


def test_validate_pack_accepts_a_consistent_puzzle(tmp_path: Path):
    path = tmp_path / "pack.sqlite"
    _make_pack(path, FULL_CLUES)
    assert validate_pack(path) == []


def test_validate_pack_flags_solution_mismatch(tmp_path: Path):
    path = tmp_path / "pack.sqlite"
    wrong = list(FULL_CLUES)
    wrong[0] = (1, "A", 1, 0, 0, 3, "Wrong", "DOG")
    _make_pack(path, wrong)
    assert any("does not match solution" in p for p in validate_pack(path))


def test_validate_pack_flags_unclued_slot(tmp_path: Path):
    path = tmp_path / "pack.sqlite"
    _make_pack(path, FULL_CLUES[:1])
    assert any("unclued" in p for p in validate_pack(path))
