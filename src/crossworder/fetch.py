"""Download and unpack the free corpus and wordlists.

All URLs verified reachable 2026-07-20. peterbroda.me is dead and is
deliberately absent; the two wordlists here cover the need.
"""
from __future__ import annotations

import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple


class Source(NamedTuple):
    url: str
    filename: str
    note: str


SOURCES: dict[str, Source] = {
    "xd_puzzles": Source(
        "https://xd.saul.pw/xd-puzzles.zip",
        "xd-puzzles.zip",
        "89,662 puzzles incl. 28,337 NYT 1942-2025; grids + clues + dates",
    ),
    "collaborative_wordlist": Source(
        "https://raw.githubusercontent.com/Crossword-Nexus"
        "/collaborative-word-list/main/xwordlist.dict",
        "xwordlist.dict",
        "566,665 scored entries, MIT",
    ),
    "spread_the_wordlist": Source(
        "https://drive.google.com/uc?export=download&id=1f0XZ0xRJ37UdxbLsmckYqUJUf_R7pQcs",
        "spreadthewordlist.dict",
        "315,899 scored entries, CC BY-NC-SA 4.0 (non-commercial)",
    ),
}


def download_all(dest: Path, skip_existing: bool = True) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for key, src in SOURCES.items():
        target = dest / src.filename
        if target.exists() and skip_existing and target.stat().st_size > 0:
            print(f"skip {key}: already at {target}")
        else:
            print(f"downloading {key} -> {target}")
            urllib.request.urlretrieve(src.url, target)
        paths.append(target)
    return paths


def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
    return dest
