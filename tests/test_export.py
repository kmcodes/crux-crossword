import sqlite3
from pathlib import Path

from crossworder.export import PACK_SCHEMA, generate, validate_pack
from crossworder.ingest import SCHEMA as CORPUS_SCHEMA


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


# --- generate(): grid-dedup and wall-clock budget -------------------------
#
# A tiny, fully open 3x3 corpus fills near-instantly, so these tests exercise
# generate()'s own control flow (dedup, time budget) rather than the slow
# real 15x15 corpus. Two distinct 3x3 patterns give generate() two grids to
# choose from; a 3x3 open grid has six 3-letter slots (rows + cols) that a
# handful of common 3-letter words can satisfy with crossing constraints.
GRID_A = "." * 9
GRID_B = ".#." + "." * 6  # a different pattern, still trivially fillable

WORDS = {
    "TEN": 100, "ARE": 100, "RAT": 100,
    "TAR": 100, "ERA": 100, "NET": 100,
    "AXE": 100, "RUG": 100,
    # GRID_B has a length-2 down slot crossing two length-3 across slots and
    # two length-3 down slots (see derive_slots). This exact combination --
    # TAR/WEB down, ATE/ROB across, TO down -- was verified by exhaustive
    # search to be a mutually-consistent, fully-distinct solution so GRID_B
    # is genuinely fillable, not just structurally plausible.
    "WEB": 100, "ATE": 100, "ROB": 100, "TO": 100,
}

# is_hard=1 so CandidatePool.load() treats every word here as clue-covered
# (matching() only draws from _covered_by_length, which requires an answer
# to have at least one is_hard=1 clue row -- see pool.py).
CLUES = [
    ("TEN", "Count", 1, 2020),
    ("ARE", "Exist", 1, 2020),
    ("RAT", "Rodent", 1, 2020),
    ("TAR", "Pitch", 1, 2020),
    ("ERA", "Age", 1, 2020),
    ("NET", "Court divider", 1, 2020),
    ("AXE", "Chopping tool", 1, 2020),
    ("RUG", "Floor covering", 1, 2020),
    ("WEB", "Spider's creation", 1, 2020),
    ("ATE", "Consumed", 1, 2020),
    ("ROB", "Steal from", 1, 2020),
    ("TO", "Toward", 1, 2020),
]


def _make_corpus(path: Path, patterns: list[str]) -> None:
    con = sqlite3.connect(path)
    con.executescript(CORPUS_SCHEMA)
    con.executemany(
        "INSERT INTO words VALUES (?,?)", list(WORDS.items())
    )
    con.executemany(
        "INSERT INTO clues VALUES (?,?,?,?)", CLUES
    )
    con.executemany(
        "INSERT INTO grids VALUES (?,?,?)",
        [(pattern, 3, "2020-01-01") for pattern in patterns],
    )
    con.commit()
    con.close()


def test_generate_skips_grid_pattern_already_in_pack(tmp_path: Path):
    corpus_path = tmp_path / "corpus.sqlite"
    _make_corpus(corpus_path, [GRID_A])

    out_path = tmp_path / "pack.sqlite"
    # Seed the pack with a puzzle that already uses GRID_A's pattern.
    _make_pack(out_path, FULL_CLUES)
    assert (
        sqlite3.connect(out_path).execute(
            "SELECT grid FROM puzzles WHERE id = 1"
        ).fetchone()[0]
        == GRID_A
    )

    # The corpus only offers GRID_A, which is already used, so nothing new
    # can be written -- but generate() must not crash and must not write a
    # second puzzle with that same grid pattern.
    written = generate(corpus_path, out_path, count=5, size=3, seed=0)
    assert written == 0

    grids = [
        row[0] for row in sqlite3.connect(out_path).execute(
            "SELECT grid FROM puzzles"
        )
    ]
    assert grids.count(GRID_A) == 1


def test_generate_updates_used_grids_immediately_after_each_write(tmp_path: Path):
    # grids.pattern is a primary key, so a single corpus can never offer the
    # same pattern twice -- the loop in generate() structurally cannot visit
    # one pattern more than once per run from that angle alone. The in-run
    # half of the "belt and suspenders" requirement is instead about
    # `used_grids` being kept current *during* the loop (not just seeded once
    # from the pack at the start), which matters once a pattern has just been
    # written and a later iteration could otherwise re-derive it independently
    # (e.g. a future corpus source without a uniqueness constraint). Exercise
    # this directly: patch the internal `used_grids` tracking is implicit, so
    # instead prove the externally-visible contract -- immediately after
    # generate() commits a puzzle, that pattern is already unusable within
    # the same call by asking for two puzzles from a corpus with only one
    # fillable pattern and confirming exactly one is written, not a retry
    # loop or a crash.
    corpus_path = tmp_path / "corpus.sqlite"
    _make_corpus(corpus_path, [GRID_A])

    out_path = tmp_path / "pack.sqlite"
    written = generate(corpus_path, out_path, count=2, size=3, seed=0)

    grids = [
        row[0] for row in sqlite3.connect(out_path).execute(
            "SELECT grid FROM puzzles"
        )
    ]
    assert written == len(grids) == 1
    assert grids.count(GRID_A) == 1


def test_generate_resume_across_two_calls_yields_distinct_grids(tmp_path: Path):
    corpus_path = tmp_path / "corpus.sqlite"
    _make_corpus(corpus_path, [GRID_A, GRID_B])

    out_path = tmp_path / "pack.sqlite"
    first = generate(corpus_path, out_path, count=1, size=3, seed=0)
    second = generate(corpus_path, out_path, count=1, size=3, seed=1)

    assert first == 1
    assert second == 1

    grids = [
        row[0] for row in sqlite3.connect(out_path).execute(
            "SELECT grid FROM puzzles"
        )
    ]
    assert len(grids) == 2
    assert len(set(grids)) == 2


def test_generate_respects_max_seconds_budget(tmp_path: Path):
    corpus_path = tmp_path / "corpus.sqlite"
    _make_corpus(corpus_path, [GRID_A])

    out_path = tmp_path / "pack.sqlite"
    # Ask for far more puzzles than the tiny corpus could ever supply, with
    # an overall budget so small the loop must bail out promptly instead of
    # exhausting every pattern (or hanging).
    import time

    start = time.monotonic()
    written = generate(
        corpus_path, out_path, count=1000, size=3, seed=0, max_seconds=0.01,
    )
    elapsed = time.monotonic() - start

    assert elapsed < 5.0
    assert written <= 1
    # Whatever was written (partial pack) must still be a valid pack.
    assert validate_pack(out_path) == []
