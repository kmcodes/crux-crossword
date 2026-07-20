"""Download and unpack the free corpus and wordlists.

All URLs verified reachable 2026-07-20. peterbroda.me is dead and is
deliberately absent; the two wordlists here cover the need.
"""
from __future__ import annotations

import os
import re
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple


class DownloadValidationError(Exception):
    """Raised when a downloaded source fails content validation."""


# WORD;score - e.g. "ABACUS;50". Scores are typically 0-100 but we only
# anchor on the shape (word, separator, digits) to avoid being brittle.
_DICT_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z'.\- ]*;\d+\s*$")


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


def _validate_zip(key: str, path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise DownloadValidationError(
            f"download for {key!r} is not a valid zip archive "
            f"(got {path.stat().st_size} bytes at {path}); "
            "the source may have served an error page or a truncated file"
        )


def _validate_dict(key: str, path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8", errors="strict") as f:
            first_line = f.readline()
    except UnicodeDecodeError as exc:
        raise DownloadValidationError(
            f"download for {key!r} is not valid UTF-8 text "
            f"(expected a WORD;score wordlist) at {path}: {exc}"
        ) from exc

    if not first_line:
        raise DownloadValidationError(
            f"download for {key!r} is empty at {path}; expected a non-empty "
            "WORD;score wordlist"
        )

    stripped = first_line.strip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        raise DownloadValidationError(
            f"download for {key!r} looks like an HTML page, not a wordlist "
            f"(at {path}). This commonly happens when a Google Drive link "
            "serves a virus-scan interstitial instead of the file - "
            "download it manually and place it at the target path."
        )

    if not _DICT_LINE_RE.match(first_line):
        raise DownloadValidationError(
            f"download for {key!r} does not look like a WORD;score wordlist "
            f"(first line: {first_line.strip()!r} at {path})"
        )


def _validate_download(key: str, src: Source, path: Path) -> None:
    if src.filename.endswith(".zip"):
        _validate_zip(key, path)
    elif src.filename.endswith(".dict"):
        _validate_dict(key, path)


def download_all(dest: Path, skip_existing: bool = True) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for key, src in SOURCES.items():
        target = dest / src.filename
        if target.exists() and skip_existing and target.stat().st_size > 0:
            print(f"skip {key}: already at {target}")
            paths.append(target)
            continue

        print(f"downloading {key} -> {target}")
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{src.filename}.", suffix=".part", dir=dest
        )
        tmp_path = Path(tmp_name)
        try:
            os.close(fd)
            try:
                urllib.request.urlretrieve(src.url, tmp_path)
            except urllib.error.URLError as exc:
                raise DownloadValidationError(
                    f"failed to download {key!r} from {src.url}: {exc}"
                ) from exc

            _validate_download(key, src, tmp_path)
            tmp_path.replace(target)
        finally:
            tmp_path.unlink(missing_ok=True)
        paths.append(target)
    return paths


def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
    return dest
