"""Utilities for generating human or AI-assisted summaries of patch sessions."""

from __future__ import annotations

import json
import logging
import os
from typing import Callable, Mapping, MutableMapping, Sequence
from urllib import error, request

from .localization import gettext as _
from .patcher import ApplySession, FileResult

logger = logging.getLogger(__name__)

AI_SUMMARY_ENDPOINT_ENV = "PATCH_GUI_AI_SUMMARY_ENDPOINT"
AI_SUMMARY_TIMEOUT_ENV = "PATCH_GUI_AI_SUMMARY_TIMEOUT"
AI_SUMMARY_TOKEN_ENV = "PATCH_GUI_AI_SUMMARY_TOKEN"
_DEFAULT_TIMEOUT = 10.0


def _parse_timeout(raw_timeout: str | None) -> float:
    if not raw_timeout:
        return _DEFAULT_TIMEOUT
    try:
        value = float(raw_timeout)
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT
    if value <= 0:
        return _DEFAULT_TIMEOUT
    return value


def _default_file_label(result: FileResult) -> str:
    name = result.relative_to_root or result.file_path.name
    if result.hunks_total:
        return _("{name} ({applied}/{total})").format(
            name=name,
            applied=result.hunks_applied,
            total=result.hunks_total,
        )
    return name


def _format_changed_files(results: Sequence[FileResult]) -> str:
    changed: list[str] = []
    total_changed = 0
    for item in results:
        if not item.hunks_applied:
            continue
        total_changed += 1
        if len(changed) < 5:
            changed.append(_default_file_label(item))
    if not changed:
        return _("(none)")
    if total_changed > len(changed):
        changed.append(_("… (+{count} more)").format(count=total_changed - len(changed)))
    return ", ".join(changed)


def _format_skipped_files(results: Sequence[FileResult]) -> str:
    skipped: list[str] = []
    total_skipped = 0
    for item in results:
        if not item.skipped_reason:
            continue
        total_skipped += 1
        if len(skipped) < 5:
            label = _default_file_label(item)
            skipped.append(
                _("{label} – {reason}").format(label=label, reason=item.skipped_reason)
            )
    if not skipped:
        return _("(none)")
    if total_skipped > len(skipped):
        skipped.append(_("… (+{count} more)").format(count=total_skipped - len(skipped)))
    return "; ".join(skipped)


def build_local_summary(session: ApplySession) -> str:
    """Produce a concise textual overview of ``session``."""

    total_files = len(session.results)
    total_hunks = sum(result.hunks_total for result in session.results)
    applied_hunks = sum(result.hunks_applied for result in session.results)
    changed_summary = _format_changed_files(session.results)
    skipped_summary = _format_skipped_files(session.results)

    lines = [
        _("Patch application summary"),
        _("Files processed: {count}").format(count=total_files),
        _("Files with changes: {count}").format(
            count=sum(1 for item in session.results if item.hunks_applied)
        ),
        _("Hunks applied: {applied}/{total}").format(
            applied=applied_hunks, total=total_hunks
        ),
        _("Changed files: {details}").format(details=changed_summary),
        _("Skipped files: {details}").format(details=skipped_summary),
    ]

    return "\n".join(lines)


def _decode_response_body(body: bytes, headers: Mapping[str, str]) -> str:
    charset = "utf-8"
    content_type = headers.get("Content-Type", "")
    if "charset=" in content_type:
        charset_part = content_type.split("charset=", 1)[1]
        charset = charset_part.split(";", 1)[0].strip() or charset
    try:
        return body.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace")


def _extract_summary_from_payload(payload: object, session: ApplySession) -> str:
    if isinstance(payload, str):
        text = payload.strip()
        return text or build_local_summary(session)
    if isinstance(payload, Mapping):
        for key in ("summary", "text", "message"):
            value = payload.get(key)  # type: ignore[arg-type]
            if isinstance(value, str) and value.strip():
                return value.strip()
        if "choices" in payload:
            choices = payload["choices"]  # type: ignore[index]
            if isinstance(choices, Sequence):
                for item in choices:
                    if isinstance(item, Mapping):
                        message = item.get("message")
                        if isinstance(message, Mapping):
                            content = message.get("content")
                            if isinstance(content, str) and content.strip():
                                return content.strip()
    return build_local_summary(session)


def generate_ai_summary(
    session: ApplySession,
    *,
    environ: Mapping[str, str] | None = None,
    opener: Callable[[request.Request, float], request.addinfourl] | None = None,
) -> str:
    """Return a summary derived from an optional external AI service."""

    env = environ or os.environ
    endpoint = env.get(AI_SUMMARY_ENDPOINT_ENV)
    if not endpoint:
        return build_local_summary(session)

    timeout = _parse_timeout(env.get(AI_SUMMARY_TIMEOUT_ENV))
    token = env.get(AI_SUMMARY_TOKEN_ENV)
    payload = json.dumps({"session": session.to_json()}).encode("utf-8")
    req = request.Request(endpoint, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", token)

    open_fn = opener or request.urlopen
    try:
        with open_fn(req, timeout=timeout) as response:  # type: ignore[arg-type]
            raw_body = response.read()
            try:
                headers: MutableMapping[str, str] = dict(response.headers.items())
            except AttributeError:
                headers = {}
    except error.URLError as exc:
        logger.warning(
            _("AI summary request failed: %s"),
            exc.reason if hasattr(exc, "reason") else exc,
        )
        return build_local_summary(session)
    except OSError as exc:
        logger.warning(_("AI summary request failed: %s"), exc)
        return build_local_summary(session)

    text = _decode_response_body(raw_body, headers)
    try:
        payload_obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        payload_obj = text

    return _extract_summary_from_payload(payload_obj, session)


__all__ = [
    "AI_SUMMARY_ENDPOINT_ENV",
    "AI_SUMMARY_TIMEOUT_ENV",
    "AI_SUMMARY_TOKEN_ENV",
    "build_local_summary",
    "generate_ai_summary",
]
