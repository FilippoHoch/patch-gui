"""Integration helpers for AI-generated summaries of patch results."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from .localization import gettext as _
from .patcher import FileResult


logger = logging.getLogger(__name__)


DEFAULT_PROVIDER_ENV = "PATCH_GUI_SUMMARY_PROVIDER"
DEFAULT_MODEL_ENV = "PATCH_GUI_OPENAI_MODEL"
DEFAULT_LANGUAGE_ENV = "PATCH_GUI_SUMMARY_LANGUAGE"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"


@dataclass(slots=True)
class AISummaryResult:
    """Container for AI summary metadata."""

    summary: Optional[str]
    provider: Optional[str] = None
    error: Optional[str] = None


def generate_ai_summary(
    results: Sequence[FileResult],
    *,
    provider: str | None = None,
    model: str | None = None,
    language: str | None = None,
) -> AISummaryResult:
    """Return a concise AI-generated summary for ``results`` when possible."""

    provider_name = provider or os.getenv(DEFAULT_PROVIDER_ENV, "openai")
    language = language or os.getenv(DEFAULT_LANGUAGE_ENV, "it")

    ai_result: AISummaryResult | None = None

    if provider_name == "openai":
        ai_result = _generate_openai_summary(results, model=model, language=language)

    if ai_result and ai_result.summary:
        return ai_result

    fallback = _generate_fallback_summary(results, language=language)
    error_message = None
    if ai_result and ai_result.error:
        error_message = ai_result.error
    elif provider_name == "openai" and ai_result is None:
        error_message = _(
            "Dipendenza 'openai' non disponibile o API key mancante."
        )

    return AISummaryResult(
        summary=fallback,
        provider="local-fallback" if fallback else provider_name,
        error=error_message,
    )


def _generate_openai_summary(
    results: Sequence[FileResult],
    *,
    model: str | None,
    language: str,
) -> AISummaryResult | None:
    api_key = os.getenv(OPENAI_API_KEY_ENV)
    if not api_key:
        return AISummaryResult(summary=None, provider="openai", error=_("Variabile OPENAI_API_KEY non impostata."))

    try:
        import openai  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.debug("Modulo openai non disponibile: %s", exc)
        return AISummaryResult(summary=None, provider="openai", error=str(exc))

    target_model = model or os.getenv(DEFAULT_MODEL_ENV) or "gpt-4o-mini"
    prompt = _build_prompt(results, language=language)

    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(api_key=api_key)
            response = client.responses.create(
                model=target_model,
                input=[
                    {
                        "role": "system",
                        "content": _(
                            "Sei un assistente che riassume applicazioni di patch. "
                            "Produci al massimo 5 punti concisi in {language}."
                        ).format(language=language),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_output_tokens=250,
                temperature=0.2,
            )
            summary_text = getattr(response, "output_text", "").strip()
        else:  # pragma: no cover - legacy API path
            openai.api_key = api_key
            chat = openai.ChatCompletion.create(
                model=target_model,
                messages=[
                    {
                        "role": "system",
                        "content": _(
                            "Sei un assistente che riassume applicazioni di patch. "
                            "Produci al massimo 5 punti concisi in {language}."
                        ).format(language=language),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.2,
            )
            choices = chat.get("choices", [])
            if choices:
                summary_text = (
                    choices[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
            else:
                summary_text = ""
    except Exception as exc:  # pragma: no cover - network/runtime failures
        logger.warning("Generazione riepilogo AI fallita: %s", exc)
        return AISummaryResult(summary=None, provider="openai", error=str(exc))

    if not summary_text:
        return AISummaryResult(summary=None, provider="openai", error=_("Risposta vuota dal provider OpenAI."))

    return AISummaryResult(summary=summary_text, provider="openai", error=None)


def _build_prompt(results: Sequence[FileResult], *, language: str) -> str:
    payload: list[dict[str, object]] = []
    for fr in results:
        decisions = [
            {
                "header": d.hunk_header,
                "strategy": d.strategy,
                "selected_pos": d.selected_pos,
                "similarity": d.similarity,
                "message": d.message,
            }
            for d in fr.decisions
        ]
        payload.append(
            {
                "path": fr.relative_to_root or str(fr.file_path),
                "file_type": fr.file_type,
                "hunks_applied": fr.hunks_applied,
                "hunks_total": fr.hunks_total,
                "skipped_reason": fr.skipped_reason,
                "decisions": decisions,
            }
        )

    description = json.dumps(payload, ensure_ascii=False, indent=2)
    return _(
        "Riassumi il seguente risultato di applicazione patch in {language} "
        "con poche frasi o punti elenco:\n{description}"
    ).format(language=language, description=description)


def _generate_fallback_summary(
    results: Iterable[FileResult],
    *,
    language: str,
) -> str | None:
    entries: list[str] = []
    for fr in results:
        display_path = fr.relative_to_root or str(fr.file_path)
        if fr.skipped_reason:
            entries.append(
                _("{path}: saltato ({reason})").format(
                    path=display_path, reason=fr.skipped_reason
                )
            )
            continue
        if fr.hunks_total == 0:
            entries.append(
                _("{path}: nessuna modifica da applicare").format(path=display_path)
            )
            continue
        entries.append(
            _("{path}: applicati {applied}/{total} hunk").format(
                path=display_path,
                applied=fr.hunks_applied,
                total=fr.hunks_total,
            )
        )

    if not entries:
        return None

    limited = entries[:5]
    bullets = "\n".join(f"- {entry}" for entry in limited)
    if language.lower().startswith("it"):
        heading = _("Riepilogo automatico")
    else:
        heading = "Automatic summary"
    return f"{heading}:\n{bullets}"


__all__ = ["AISummaryResult", "generate_ai_summary"]

