"""Tests for download validation in crossworder.fetch.

These exercise the fix for the Task 1 code review finding: download_all()
must not leave a truncated or corrupt (e.g. HTML interstitial) file in place
that a later run would mistake for a valid, already-downloaded source.

No network access is used - urllib.request.urlretrieve is monkeypatched.
"""
from __future__ import annotations

import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from crossworder import fetch
from crossworder.fetch import Source, download_all


HTML_INTERSTITIAL = (
    "<!DOCTYPE html>\n"
    "<html><head><title>Google Drive - Virus scan warning</title></head>"
    "<body>Google Drive can't scan this file for viruses.</body></html>\n"
)

VALID_DICT = "ABACUS;50\nZEBRA;40\n"


def _make_source(tmp_path: Path, filename: str) -> tuple[dict, Path]:
    """Build a single-entry SOURCES dict pointing at `filename`."""
    src = Source(url=f"https://example.com/{filename}", filename=filename, note="test")
    return {"only_source": src}, tmp_path / filename


class TestDictValidation:
    def test_html_payload_rejected_for_dict_source(self, tmp_path, monkeypatch):
        """A Google-Drive-style HTML interstitial saved as a .dict must be rejected."""
        sources, target = _make_source(tmp_path, "spreadthewordlist.dict")

        def fake_urlretrieve(url, filename):
            Path(filename).write_text(HTML_INTERSTITIAL, encoding="utf-8")
            return filename, None

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        with pytest.raises(Exception) as excinfo:
            download_all(tmp_path / "dest")

        message = str(excinfo.value)
        assert "only_source" in message
        # The bad file must not be left behind for a later run to "skip".
        assert not (tmp_path / "dest" / "spreadthewordlist.dict").exists()

    def test_valid_dict_accepted(self, tmp_path, monkeypatch):
        sources, target = _make_source(tmp_path, "xwordlist.dict")

        def fake_urlretrieve(url, filename):
            Path(filename).write_text(VALID_DICT, encoding="utf-8")
            return filename, None

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        paths = download_all(tmp_path / "dest")

        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].read_text(encoding="utf-8") == VALID_DICT

    def test_empty_dict_rejected(self, tmp_path, monkeypatch):
        sources, target = _make_source(tmp_path, "xwordlist.dict")

        def fake_urlretrieve(url, filename):
            Path(filename).write_text("", encoding="utf-8")
            return filename, None

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        with pytest.raises(Exception) as excinfo:
            download_all(tmp_path / "dest")
        assert "only_source" in str(excinfo.value)
        assert not (tmp_path / "dest" / "xwordlist.dict").exists()


class TestZipValidation:
    def test_truncated_zip_rejected(self, tmp_path, monkeypatch):
        sources, target = _make_source(tmp_path, "xd-puzzles.zip")

        def fake_urlretrieve(url, filename):
            # Not a valid zip - simulates a truncated/corrupt download.
            Path(filename).write_bytes(b"PK\x03\x04not really a zip file")
            return filename, None

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        with pytest.raises(Exception) as excinfo:
            download_all(tmp_path / "dest")

        message = str(excinfo.value)
        assert "only_source" in message
        assert not (tmp_path / "dest" / "xd-puzzles.zip").exists()

    def test_html_payload_rejected_for_zip_source(self, tmp_path, monkeypatch):
        sources, target = _make_source(tmp_path, "xd-puzzles.zip")

        def fake_urlretrieve(url, filename):
            Path(filename).write_text(HTML_INTERSTITIAL, encoding="utf-8")
            return filename, None

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        with pytest.raises(Exception) as excinfo:
            download_all(tmp_path / "dest")
        assert not (tmp_path / "dest" / "xd-puzzles.zip").exists()

    def test_valid_zip_accepted(self, tmp_path, monkeypatch):
        sources, target = _make_source(tmp_path, "xd-puzzles.zip")

        def fake_urlretrieve(url, filename):
            with zipfile.ZipFile(filename, "w") as z:
                z.writestr("a.xd", "Date: 2015-01-03\n")
            return filename, None

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        paths = download_all(tmp_path / "dest")
        assert paths[0].exists()
        assert zipfile.is_zipfile(paths[0])


class TestNetworkFailure:
    def test_network_error_leaves_no_file_behind(self, tmp_path, monkeypatch):
        sources, target = _make_source(tmp_path, "xd-puzzles.zip")

        def failing_urlretrieve(url, filename):
            raise urllib.error.URLError("simulated network failure mid-download")

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", failing_urlretrieve)

        with pytest.raises(Exception) as excinfo:
            download_all(tmp_path / "dest")

        message = str(excinfo.value)
        assert "only_source" in message
        dest_dir = tmp_path / "dest"
        # Either the dest dir wasn't created, or it has no leftover target file.
        assert not (dest_dir / "xd-puzzles.zip").exists()

    def test_partial_download_not_skipped_on_rerun(self, tmp_path, monkeypatch):
        """Regression for the core bug: a failed/invalid download must never
        leave a file that a later run's skip_existing check would accept."""
        sources, target = _make_source(tmp_path, "xd-puzzles.zip")
        dest = tmp_path / "dest"

        call_count = {"n": 0}

        def fake_urlretrieve(url, filename):
            call_count["n"] += 1
            # First call: simulate corrupt/truncated download.
            Path(filename).write_bytes(b"not a zip")
            return filename, None

        monkeypatch.setattr(fetch, "SOURCES", sources)
        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        with pytest.raises(Exception):
            download_all(dest)

        # Nothing valid should be sitting at the target path.
        assert not (dest / "xd-puzzles.zip").exists()

        # A second run (e.g. after fixing the network) must attempt to
        # download again rather than silently "skip existing".
        def fake_urlretrieve_2(url, filename):
            call_count["n"] += 1
            with zipfile.ZipFile(filename, "w") as z:
                z.writestr("a.xd", "Date: 2015-01-03\n")
            return filename, None

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve_2)
        paths = download_all(dest)
        assert paths[0].exists()
        assert zipfile.is_zipfile(paths[0])
        assert call_count["n"] == 2
