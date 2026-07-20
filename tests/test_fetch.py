import zipfile
from pathlib import Path

from crossworder.fetch import SOURCES, extract_zip


def test_sources_have_required_entries():
    assert "xd_puzzles" in SOURCES
    assert "collaborative_wordlist" in SOURCES
    assert "spread_the_wordlist" in SOURCES
    assert SOURCES["xd_puzzles"].url.endswith("xd-puzzles.zip")


def test_extract_zip_returns_destination(tmp_path: Path):
    src = tmp_path / "a.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("gxd/nytimes/2015/nyt2015-01-03.xd", "Date: 2015-01-03\n")
    out = extract_zip(src, tmp_path / "out")
    assert (out / "gxd/nytimes/2015/nyt2015-01-03.xd").exists()
