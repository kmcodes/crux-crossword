"""Generate puzzles and write the app-facing pack."""
from __future__ import annotations

import datetime
import random
import sqlite3
import time
from pathlib import Path

from crossworder.clue import ClueBank, score_difficulty
from crossworder.fill import fill_grid
from crossworder.grid import derive_slots, slot_numbers
from crossworder.pool import CandidatePool

PACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS puzzles (
    id         INTEGER PRIMARY KEY,
    size       INTEGER NOT NULL,
    difficulty INTEGER NOT NULL,
    grid       TEXT NOT NULL,
    solution   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS puzzle_clues (
    puzzle_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    number    INTEGER NOT NULL,
    row       INTEGER NOT NULL,
    col       INTEGER NOT NULL,
    length    INTEGER NOT NULL,
    clue      TEXT NOT NULL,
    answer    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clues_puzzle ON puzzle_clues(puzzle_id);
"""


def generate(
    corpus_db: Path,
    out_db: Path,
    count: int,
    size: int = 15,
    seed: int = 0,
    max_seconds: float | None = None,
    pattern_time_budget_s: float = 6.0,
) -> int:
    # Start the overall clock before loading so max_seconds bounds total
    # wall-clock, not just the generation loop. ClueBank.load reads the full
    # clue table (~11s), which would otherwise sit outside the cap.
    deadline = None if max_seconds is None else time.monotonic() + max_seconds

    pool = CandidatePool.load(corpus_db)
    bank = ClueBank.load(corpus_db)
    rng = random.Random(seed)

    corpus = sqlite3.connect(corpus_db)
    patterns = [
        row[0]
        for row in corpus.execute(
            "SELECT pattern FROM grids WHERE size = ?", (size,)
        )
    ]
    corpus.close()
    rng.shuffle(patterns)

    out_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out_db)
    con.executescript(PACK_SCHEMA)
    next_id = (
        con.execute("SELECT COALESCE(MAX(id), 0) FROM puzzles").fetchone()[0] + 1
    )

    # Grid patterns already committed to this pack (from this run or an
    # earlier one) must never be regenerated -- otherwise a rerun or a
    # resumed overnight build can silently duplicate a puzzle. `used_grids`
    # is seeded from the pack and then grown in-run as each pattern is
    # written, so both "already in the pack" and "already used earlier in
    # this same loop" are covered by one check.
    used_grids = {
        row[0] for row in con.execute("SELECT grid FROM puzzles")
    }

    written = 0
    for pattern in patterns:
        if written >= count:
            break
        if deadline is not None and time.monotonic() >= deadline:
            break
        if pattern in used_grids:
            continue
        # Short per-pattern budget on purpose: roughly half of themeless grids
        # fill almost instantly and the rest can burn minutes. Abandoning a slow
        # pattern and trying the next of ~2,900 is far cheaper than persisting.
        # Clamp to whatever overall time remains so the max_seconds cap is
        # honoured tightly rather than overshooting by a full pattern budget.
        budget = pattern_time_budget_s
        if deadline is not None:
            budget = min(budget, max(0.0, deadline - time.monotonic()))
        result = fill_grid(
            pattern,
            size,
            pool,
            seed=rng.randrange(1 << 30),
            max_restarts=4,
            time_budget_s=budget,
        )
        if result is None:
            continue

        slots = derive_slots(pattern, size)
        numbers = slot_numbers(slots, size)
        rows = []
        hard_flags: dict[int, bool] = {}
        ok = True
        for slot in slots:
            number = numbers[slot.index]
            answer = result.answers[slot.index]
            picked = bank.pick(answer, rng)
            if picked is None:
                ok = False
                break
            text, from_hard = picked
            hard_flags[slot.index] = from_hard
            rows.append(
                (next_id, slot.direction, number, slot.row, slot.col,
                 slot.length, text, answer)
            )
        if not ok:
            continue

        difficulty = score_difficulty(result.answers, hard_flags, bank, slots)
        con.execute(
            "INSERT INTO puzzles VALUES (?,?,?,?,?,?)",
            (next_id, size, difficulty, pattern, result.letters,
             datetime.date.today().isoformat()),
        )
        con.executemany("INSERT INTO puzzle_clues VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
        used_grids.add(pattern)
        print(f"wrote puzzle {next_id} (difficulty {difficulty})")
        next_id += 1
        written += 1

    con.close()
    return written


def validate_pack(out_db: Path) -> list[str]:
    """Return a list of problems; empty means the pack is sound."""
    problems: list[str] = []
    con = sqlite3.connect(out_db)
    for pid, size, grid, solution in con.execute(
        "SELECT id, size, grid, solution FROM puzzles"
    ):
        if len(grid) != size * size or len(solution) != size * size:
            problems.append(f"puzzle {pid}: grid/solution wrong length")
            continue

        slots = derive_slots(grid, size)
        # Map each clue to the slot it claims, so a clue attached to the wrong
        # slot is caught rather than passing because the word exists elsewhere.
        clued: dict[tuple[str, int, int, int], str] = {}
        for direction, row, col, length, answer in con.execute(
            "SELECT direction, row, col, length, answer FROM puzzle_clues "
            "WHERE puzzle_id = ?",
            (pid,),
        ):
            clued[(direction, row, col, length)] = answer

        for slot in slots:
            key = (slot.direction, slot.row, slot.col, slot.length)
            if key not in clued:
                problems.append(f"puzzle {pid}: unclued slot {key}")
                continue
            expected = "".join(solution[i] for i in slot.cells)
            if clued[key] != expected:
                problems.append(
                    f"puzzle {pid}: answer {clued[key]} at {key} "
                    f"does not match solution ({expected})"
                )

        # Two different slots must not hold the same word. An across and a down
        # slot crossing at one cell are still two distinct entries, so this
        # compares per-slot words, not clue rows.
        words = [
            "".join(solution[i] for i in slot.cells)
            for slot in slots
            if (slot.direction, slot.row, slot.col, slot.length) in clued
        ]
        if len(words) != len(set(words)):
            duplicates = {w for w in words if words.count(w) > 1}
            problems.append(
                f"puzzle {pid}: duplicate answers {sorted(duplicates)}"
            )
    con.close()
    return problems
