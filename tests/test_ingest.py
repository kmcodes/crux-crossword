import sqlite3
from pathlib import Path

from crossworder.ingest import build_corpus, is_usable_clue, load_wordlist

XD = """Title: Test
Author: A Constructor
Date: 2015-01-03


CAT
ARE
TEN


A1. Feline ~ CAT
A4. Exist ~ ARE
D1. Sum ~ CAT
"""


def test_load_wordlist_normalises(tmp_path: Path):
    p = tmp_path / "w.dict"
    p.write_text("cat;50\nCAT;70\nbad-word;90\nDOG;30\n")
    wl = load_wordlist(p)
    assert wl["CAT"] == 70          # max score wins on duplicates
    assert "BADWORD" not in wl      # non A-Z rejected, not silently mangled
    assert wl["DOG"] == 30


def test_is_usable_clue_rejects_cross_references():
    assert is_usable_clue("Bollix") is True
    assert is_usable_clue("9-Down item") is False
    assert is_usable_clue("Profession of 36-Across: Abbr.") is False
    assert is_usable_clue("") is False
    assert is_usable_clue("   ") is False


def test_is_usable_clue_rejects_space_separated_cross_references():
    assert is_usable_clue("See 63 Down") is False
    assert is_usable_clue("Info on 37 Across") is False
    assert is_usable_clue("Alternative name for 21 Across") is False
    assert (
        is_usable_clue(
            '"And Then There Were None" director, with 12 Down'
        )
        is False
    )


def test_is_usable_clue_accepts_legitimate_digit_clues():
    assert is_usable_clue("1980s dance") is True
    assert is_usable_clue("Catch-22") is True
    assert is_usable_clue("3-D movie") is True
    assert is_usable_clue("W-2 form") is True
    assert is_usable_clue("Apollo 11 org.") is True


def test_build_corpus_populates_tables(tmp_path: Path):
    pdir = tmp_path / "gxd" / "nytimes" / "2015"
    pdir.mkdir(parents=True)
    (pdir / "nyt2015-01-03.xd").write_text(XD)

    wl = tmp_path / "w.dict"
    wl.write_text("CAT;80\nACE;60\nTEN;55\n")

    db = tmp_path / "corpus.sqlite"
    build_corpus(tmp_path, [wl], db)

    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM clues").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM words").fetchone()[0] == 3
    # 2015-01-03 is a Saturday in the Shortz era, so clues are hard.
    assert con.execute("SELECT COUNT(*) FROM clues WHERE is_hard=1").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM grids").fetchone()[0] == 1


def test_build_corpus_only_marks_nyt_puzzles_as_hard(tmp_path: Path):
    # Same Shortz-era Saturday grid/clues, ingested once under nytimes and
    # once under a non-NYT publisher. Only the NYT copy may be hard.
    nyt_dir = tmp_path / "gxd" / "nytimes" / "2015"
    nyt_dir.mkdir(parents=True)
    (nyt_dir / "nyt2015-01-03.xd").write_text(XD)

    other_dir = tmp_path / "gxd" / "latimes" / "2015"
    other_dir.mkdir(parents=True)
    (other_dir / "lat2015-01-03.xd").write_text(XD)

    wl = tmp_path / "w.dict"
    wl.write_text("CAT;80\nACE;60\nTEN;55\n")

    db = tmp_path / "corpus.sqlite"
    build_corpus(tmp_path, [wl], db)

    con = sqlite3.connect(db)
    # 3 clues per puzzle x 2 puzzles = 6 total, but only the NYT 3 are hard.
    assert con.execute("SELECT COUNT(*) FROM clues").fetchone()[0] == 6
    assert con.execute("SELECT COUNT(*) FROM clues WHERE is_hard=1").fetchone()[0] == 3
    # Only the NYT puzzle contributes a grid pattern.
    assert con.execute("SELECT COUNT(*) FROM grids").fetchone()[0] == 1


def test_build_corpus_hard_count_identical_regardless_of_root(tmp_path: Path):
    # Pointing build_corpus at the full multi-publisher tree vs. directly at
    # the nytimes subdirectory must yield the same hard-clue count -- the
    # NYT-only restriction must be structural, not a caller convention.
    nyt_dir = tmp_path / "gxd" / "nytimes" / "2015"
    nyt_dir.mkdir(parents=True)
    (nyt_dir / "nyt2015-01-03.xd").write_text(XD)

    other_dir = tmp_path / "gxd" / "latimes" / "2015"
    other_dir.mkdir(parents=True)
    (other_dir / "lat2015-01-03.xd").write_text(XD)

    wl = tmp_path / "w.dict"
    wl.write_text("CAT;80\nACE;60\nTEN;55\n")

    db_full = tmp_path / "corpus_full.sqlite"
    build_corpus(tmp_path, [wl], db_full)

    db_nyt = tmp_path / "corpus_nyt.sqlite"
    build_corpus(tmp_path / "gxd" / "nytimes", [wl], db_nyt)

    con_full = sqlite3.connect(db_full)
    con_nyt = sqlite3.connect(db_nyt)

    hard_full = con_full.execute(
        "SELECT COUNT(*) FROM clues WHERE is_hard=1"
    ).fetchone()[0]
    hard_nyt = con_nyt.execute(
        "SELECT COUNT(*) FROM clues WHERE is_hard=1"
    ).fetchone()[0]

    assert hard_full == hard_nyt == 3
