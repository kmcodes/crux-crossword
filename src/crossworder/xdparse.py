"""Parse xd-format crossword files.

Format: header lines (Key: value), then a grid of equal-length rows using
'#' for black squares, then clue lines of the form 'A1. Clue text ~ ANSWER'.
Sections are separated by blank lines.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

CLUE_RE = re.compile(r"^([AD])(\d+)\.\s*(.*?)\s*~\s*(.+)$")
GRID_ROW_RE = re.compile(r"^[A-Z0-9#_.]+$")


@dataclass(frozen=True)
class ParsedClue:
    direction: str
    number: int
    text: str
    answer: str


@dataclass(frozen=True)
class Puzzle:
    date: datetime.date
    width: int
    height: int
    rows: list[str]
    clues: list[ParsedClue]
    author: str


def _parse_headers(text: str) -> dict[str, str]:
    headers = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z]+):\s*(.*)$", line)
        if not m:
            break
        headers[m.group(1).lower()] = m.group(2).strip()
    return headers


def parse_xd(text: str) -> Puzzle | None:
    headers = _parse_headers(text)
    raw_date = headers.get("date", "")
    try:
        date = datetime.date.fromisoformat(raw_date)
    except ValueError:
        return None

    clues: list[ParsedClue] = []
    grid_candidates: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        m = CLUE_RE.match(stripped)
        if m:
            answer = re.sub(r"[^A-Z]", "", m.group(4).upper())
            if answer:
                clues.append(
                    ParsedClue(m.group(1), int(m.group(2)), m.group(3), answer)
                )
            continue
        if stripped and GRID_ROW_RE.match(stripped) and ":" not in stripped:
            grid_candidates.append(stripped)

    if not grid_candidates:
        return None

    width = len(grid_candidates[0])
    rows = [r for r in grid_candidates if len(r) == width]
    # Real grids are square; irregular files are a small minority and are dropped.
    if len(rows) != width:
        return None
    if not clues:
        return None

    return Puzzle(
        date=date,
        width=width,
        height=len(rows),
        rows=rows,
        clues=clues,
        author=headers.get("author", ""),
    )


def is_hard(p: Puzzle) -> bool:
    """Shortz-era Friday/Saturday NYT puzzles are the hard-difficulty source."""
    return p.date.year >= 1994 and p.date.weekday() in (4, 5)
