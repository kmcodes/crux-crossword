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
