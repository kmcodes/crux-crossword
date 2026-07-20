"""Normalise the corpus and wordlists into a single SQLite database."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from crossworder.xdparse import is_hard, parse_xd

SCHEMA = """
CREATE TABLE IF NOT EXISTS clues (
    answer  TEXT NOT NULL,
    clue    TEXT NOT NULL,
    is_hard INTEGER NOT NULL,
    year    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clues_answer ON clues(answer);
CREATE INDEX IF NOT EXISTS idx_clues_hard ON clues(is_hard);

CREATE TABLE IF NOT EXISTS words (
    answer TEXT PRIMARY KEY,
    score  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS grids (
    pattern     TEXT PRIMARY KEY,
    size        INTEGER NOT NULL,
    source_date TEXT NOT NULL
);
"""

CROSSREF_RE = re.compile(r"\b\d+-(Across|Down)\b", re.IGNORECASE)

# The hard-difficulty bank (Shortz-era Fri/Sat) is scoped to NYT puzzles only
# -- xdparse.is_hard() has no notion of publisher, so that restriction is
# enforced here structurally, from the file path, so it cannot be bypassed by
# pointing build_corpus at a broader root. Corpus layout is always
# <root>/gxd/<publication>/<year>/<file>.xd, so the publication segment is
# derivable from the path regardless of which root the caller passes.
NYT_PUBLICATION = "nytimes"


def _publication(path: Path) -> str | None:
    """Return the publication directory name from a corpus-layout path.

    Path is <root>/gxd/<publication>/<year>/<file>.xd; the publication is the
    path segment immediately following "gxd", found by scanning from the
    file so it works no matter how far up the tree `root` sits.
    """
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "gxd" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def is_nyt(path: Path) -> bool:
    return _publication(path) == NYT_PUBLICATION


def is_usable_clue(text: str) -> bool:
    """Reject clues that cannot survive being moved to a different grid."""
    if not text or not text.strip():
        return False
    return CROSSREF_RE.search(text) is None


def load_wordlist(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            word, _, score = line.strip().partition(";")
            word = word.upper()
            if not re.fullmatch(r"[A-Z]+", word):
                continue
            try:
                value = int(score)
            except ValueError:
                continue
            if value > out.get(word, -1):
                out[word] = value
    return out


def build_corpus(puzzle_dir: Path, wordlists: list[Path], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    clue_rows: list[tuple[str, str, int, int]] = []
    grid_rows: dict[str, tuple[int, str]] = {}

    for path in sorted(puzzle_dir.rglob("*.xd")):
        puzzle = parse_xd(path.read_text(encoding="utf-8", errors="replace"))
        if puzzle is None:
            continue
        # Grid patterns and the hard-clue bank are NYT-only; non-NYT clues
        # still enter the corpus (as not-hard) since answer frequency across
        # the full corpus is used as a difficulty signal.
        hard = is_hard(puzzle) and is_nyt(path)
        for clue in puzzle.clues:
            if not is_usable_clue(clue.text):
                continue
            clue_rows.append((clue.answer, clue.text, int(hard), puzzle.date.year))
        # Only hard puzzles supply grid patterns: themeless, wide open.
        if hard:
            pattern = "".join(
                "#" if ch == "#" else "." for row in puzzle.rows for ch in row
            )
            grid_rows[pattern] = (puzzle.width, puzzle.date.isoformat())

    con.executemany("INSERT INTO clues VALUES (?,?,?,?)", clue_rows)
    con.executemany(
        "INSERT OR IGNORE INTO grids VALUES (?,?,?)",
        [(p, s, d) for p, (s, d) in grid_rows.items()],
    )

    merged: dict[str, int] = {}
    for wl_path in wordlists:
        for word, score in load_wordlist(wl_path).items():
            if score > merged.get(word, -1):
                merged[word] = score
    con.executemany(
        "INSERT OR REPLACE INTO words VALUES (?,?)", list(merged.items())
    )

    con.commit()
    con.close()
