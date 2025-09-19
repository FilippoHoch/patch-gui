"""Helpers to download pre-built binaries distributed with the project."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .localization import gettext as _

__all__ = [
    "DEFAULT_REPO",
    "DEFAULT_ASSET_NAME",
    "DownloadError",
    "download_latest_release_exe",
]


# GitHub repository holding the Windows binary. The value can be overridden via the
# command-line but defaults to the upstream project.
DEFAULT_REPO = "patch-gui/patch-gui"
# Conventional filename for the Windows executable asset shipped in releases.
DEFAULT_ASSET_NAME = "patch-gui.exe"


class _Opener(Protocol):
    """Protocol describing the ``urllib.request.urlopen`` compatible callable."""

    def __call__(self, request: Request) -> Any: ...


def _default_urlopen(request: Request) -> Any:
    """Wrapper around :func:`urllib.request.urlopen` matching ``_Opener``."""

    return urlopen(request)


class DownloadError(Exception):
    """Raised when a release asset cannot be retrieved."""


@dataclass
class _ReleaseAsset:
    name: str
    download_url: str


def download_latest_release_exe(
    *,
    repo: str = DEFAULT_REPO,
    asset_name: str = DEFAULT_ASSET_NAME,
    destination: Path | None = None,
    overwrite: bool = False,
    token: str | None = None,
    tag: str | None = None,
    opener: _Opener | None = None,
) -> Path:
    """Download ``asset_name`` from the latest release of ``repo``.

    Parameters
    ----------
    repo:
        Repository in the form ``"owner/name"``.
    asset_name:
        Name of the asset to search for. Matching is case-insensitive and exact.
    destination:
        Path where the executable should be stored. When omitted the file is
        written inside the current working directory using ``asset_name``.
        If ``destination`` points to an existing directory the asset name is
        appended to that path.
    overwrite:
        When ``True`` the destination file is replaced if present. Otherwise a
        ``DownloadError`` is raised when the path already exists.
    token:
        Optional GitHub token to authenticate against private repositories.
    tag:
        Specific release tag to download instead of the latest published
        release.
    opener:
        Callable compatible with :func:`urllib.request.urlopen` used mostly for
        testing.

    Returns
    -------
    Path
        The location of the downloaded executable.
    """

    opener_fn = opener or _default_urlopen
    release = _fetch_release(repo=repo, token=token, tag=tag, opener=opener_fn)
    asset = _select_asset(release, asset_name)

    destination_path = _resolve_destination(destination, asset.name)
    if destination_path.exists() and not overwrite:
        raise DownloadError(
            _(
                "Destination file already exists: {path}. Use --force to overwrite."
            ).format(path=destination_path)
        )

    request = _build_request(asset.download_url, token=token)
    try:
        response = opener_fn(request)
    except HTTPError as exc:
        _close_response(exc)
        raise DownloadError(
            _("Failed to download release asset: {error}").format(error=exc)
        ) from exc
    except URLError as exc:
        raise DownloadError(
            _("Unable to reach the download URL: {error}").format(error=exc)
        ) from exc
    try:
        data_stream = _ensure_binary_stream(response)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with destination_path.open("wb") as handle:
            _copy_stream(data_stream, handle)
    finally:
        _close_response(response)

    return destination_path


def _fetch_release(
    *,
    repo: str,
    token: str | None,
    tag: str | None,
    opener: _Opener,
) -> dict[str, object]:
    suffix = f"/tags/{tag}" if tag else "/latest"
    request = _build_request(
        f"https://api.github.com/repos/{repo}/releases{suffix}", token=token
    )
    try:
        response = opener(request)
    except HTTPError as exc:  # pragma: no cover - network failures are rare
        raise DownloadError(
            _("Failed to query release metadata: {error}").format(error=exc)
        )
    except URLError as exc:  # pragma: no cover - network failures are rare
        raise DownloadError(_("Unable to reach GitHub: {error}").format(error=exc))

    try:
        payload = response.read()
    finally:
        try:
            response.close()
        except AttributeError:
            pass

    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DownloadError(
            _("Unexpected response received from GitHub: {error}").format(error=exc)
        ) from exc

    if isinstance(data, dict) and data.get("message") == "Not Found":
        if tag:
            raise DownloadError(
                _("Release with tag '{tag}' was not found for {repo}.").format(
                    tag=tag, repo=repo
                )
            )
        raise DownloadError(
            _("Latest release for {repo} was not found.").format(repo=repo)
        )

    if not isinstance(data, dict):
        raise DownloadError(_("Malformed release information returned by GitHub."))

    return data


def _select_asset(data: dict[str, object], asset_name: str) -> _ReleaseAsset:
    assets_obj = data.get("assets")
    if not isinstance(assets_obj, Iterable):
        raise DownloadError(_("Release data does not contain any assets."))

    normalized = asset_name.lower()
    matched = None
    for entry in assets_obj:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        download_url = entry.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(download_url, str):
            continue
        if name.lower() == normalized:
            matched = _ReleaseAsset(name=name, download_url=download_url)
            break

    if matched is None:
        raise DownloadError(
            _("Asset '{asset}' was not found in the selected release.").format(
                asset=asset_name
            )
        )

    return matched


def _close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        with contextlib.suppress(AttributeError):
            close()


def _resolve_destination(destination: Path | None, asset_name: str) -> Path:
    if destination is None:
        return Path.cwd() / asset_name

    path = Path(destination)
    if path.exists() and path.is_dir():
        return path / asset_name

    return path


def _build_request(url: str, token: str | None = None) -> Request:
    request = Request(url)
    request.add_header("User-Agent", "patch-gui-downloader")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def _ensure_binary_stream(handle: BinaryIO) -> BinaryIO:
    # ``urllib`` returns objects implementing a ``read`` method but not typing's
    # ``BinaryIO`` protocol. The helper acts as documentation and a central
    # assertion point.
    if not hasattr(handle, "read"):
        raise DownloadError(_("GitHub response is missing the download body."))
    return handle


def _copy_stream(
    source: BinaryIO, destination: BinaryIO, chunk_size: int = 64 * 1024
) -> None:
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            break
        destination.write(chunk)
