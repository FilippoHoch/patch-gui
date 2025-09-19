"""Tests for the release asset downloader helpers."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, List
from urllib.error import HTTPError

import pytest

from patch_gui import downloader


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def close(self) -> None:  # pragma: no cover - ``BytesIO`` does not require closing
        self._buffer.close()


class _FakeOpener:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses: List[_FakeResponse] = list(responses)
        self.requests: list[str] = []

    def __call__(self, request: Any) -> _FakeResponse:
        self.requests.append(request.full_url)
        if not self._responses:
            raise AssertionError("No fake responses left for opener")
        return self._responses.pop(0)


def _release_payload(url: str) -> bytes:
    body = {
        "assets": [
            {
                "name": downloader.DEFAULT_ASSET_NAME,
                "browser_download_url": url,
            }
        ]
    }
    return json.dumps(body).encode("utf-8")


def test_download_latest_release_exe_saves_file(tmp_path: Path) -> None:
    download_url = "https://example.test/patch-gui.exe"
    responses = _FakeOpener(
        [
            _FakeResponse(_release_payload(download_url)),
            _FakeResponse(b"binary-data"),
        ]
    )
    destination = tmp_path / "artifacts" / "PatchGUI.exe"

    saved = downloader.download_latest_release_exe(
        destination=destination,
        overwrite=True,
        opener=responses,
    )

    assert saved == destination
    assert saved.read_bytes() == b"binary-data"
    assert responses.requests[0].endswith("/releases/latest")
    assert responses.requests[1] == download_url


def test_download_latest_release_exe_appends_asset_name_when_directory(
    tmp_path: Path,
) -> None:
    download_url = "https://example.test/patch-gui.exe"
    responses = _FakeOpener(
        [
            _FakeResponse(_release_payload(download_url)),
            _FakeResponse(b"payload"),
        ]
    )
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()

    saved = downloader.download_latest_release_exe(
        destination=target_dir,
        overwrite=True,
        opener=responses,
    )

    expected = target_dir / downloader.DEFAULT_ASSET_NAME
    assert saved == expected
    assert saved.read_bytes() == b"payload"


def test_download_latest_release_exe_raises_when_asset_missing(tmp_path: Path) -> None:
    body = json.dumps({"assets": []}).encode("utf-8")
    responses = _FakeOpener([_FakeResponse(body)])

    with pytest.raises(downloader.DownloadError) as excinfo:
        downloader.download_latest_release_exe(opener=responses)

    assert "Asset" in str(excinfo.value)


def test_download_latest_release_exe_requires_force_for_existing_file(
    tmp_path: Path,
) -> None:
    existing = tmp_path / downloader.DEFAULT_ASSET_NAME
    existing.write_bytes(b"old")

    responses = _FakeOpener([_FakeResponse(_release_payload("https://example.test"))])

    with pytest.raises(downloader.DownloadError) as excinfo:
        downloader.download_latest_release_exe(destination=existing, opener=responses)

    assert "Use --force" in str(excinfo.value)


def test_download_latest_release_exe_wraps_http_error(tmp_path: Path) -> None:
    download_url = "https://example.test/patch-gui.exe"
    release_response = _FakeResponse(_release_payload(download_url))
    http_error = HTTPError(
        download_url, 404, "Not Found", hdrs=None, fp=io.BytesIO(b"missing")
    )
    requests: list[str] = []

    def fake_opener(request: Any) -> _FakeResponse:
        requests.append(request.full_url)
        if len(requests) == 1:
            return release_response
        raise http_error

    with pytest.raises(downloader.DownloadError) as excinfo:
        downloader.download_latest_release_exe(
            destination=tmp_path / "artifact.exe",
            overwrite=True,
            opener=fake_opener,
        )

    assert (
        str(excinfo.value)
        == "Failed to download release asset: HTTP Error 404: Not Found"
    )
