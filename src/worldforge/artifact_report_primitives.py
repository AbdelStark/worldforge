"""Shared helpers for local artifact and report generation."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from worldforge.provider_redaction import _redact_observable_text

SECRET_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\s+[a-z0-9._~-]+|password|secret|signature|token=|"
    r"x-amz-signature|nvidia_api_key)",
    re.IGNORECASE,
)
HOST_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:])/(?:Users|private|Volumes|var/folders)/[^\s)`|]+")
HOST_PATH_WITH_TMP_PATTERN = re.compile(
    r"(?<![A-Za-z0-9:])/(?:Users|private|Volumes|var/folders|tmp)/[^\s)`|]+"
)
SIGNED_URL_PATTERN = re.compile(
    r"https?://[^\s)`|]*(?:X-Amz-Signature|sig=|signature=|token=|secret=)[^\s)`|]*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ReportTextRedaction:
    """Text redaction policy for attachable artifact reports."""

    signed_url_pattern: re.Pattern[str] | None = SIGNED_URL_PATTERN
    observable_redactor: Callable[[str], str] | None = None
    host_path_pattern: re.Pattern[str] | None = HOST_PATH_PATTERN
    secret_pattern: re.Pattern[str] | None = None


SECURITY_REPORT_TEXT_REDACTION = ReportTextRedaction(secret_pattern=SECRET_PATTERN)
OBSERVABLE_REPORT_TEXT_REDACTION = ReportTextRedaction(
    signed_url_pattern=None,
    observable_redactor=_redact_observable_text,
)
RELEASE_NOTES_TEXT_REDACTION = ReportTextRedaction(
    observable_redactor=_redact_observable_text,
    host_path_pattern=HOST_PATH_WITH_TMP_PATTERN,
)


def sanitize_report_text(
    value: str,
    *,
    redaction: ReportTextRedaction = SECURITY_REPORT_TEXT_REDACTION,
) -> str:
    """Return report text with signed URLs, host-local paths, and configured secrets redacted."""

    sanitized = value
    if redaction.signed_url_pattern is not None:
        sanitized = redaction.signed_url_pattern.sub("[redacted-url]", sanitized)
    if redaction.observable_redactor is not None:
        sanitized = redaction.observable_redactor(sanitized)
    if redaction.host_path_pattern is not None:
        sanitized = redaction.host_path_pattern.sub("<host-local-path>", sanitized)
    if redaction.secret_pattern is not None:
        sanitized = redaction.secret_pattern.sub("[redacted]", sanitized)
    return sanitized


def sanitize_report_json(
    value: Any,
    *,
    redaction: ReportTextRedaction = SECURITY_REPORT_TEXT_REDACTION,
) -> Any:
    """Recursively redact JSON-like report payloads without dropping colliding keys."""

    if isinstance(value, str):
        return sanitize_report_text(value, redaction=redaction)
    if isinstance(value, list):
        return [sanitize_report_json(item, redaction=redaction) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            sanitized_key = sanitize_report_text(str(key), redaction=redaction)
            unique_key = sanitized_key
            suffix = 2
            while unique_key in sanitized:
                unique_key = f"{sanitized_key}#{suffix}"
                suffix += 1
            sanitized[unique_key] = sanitize_report_json(item, redaction=redaction)
        return sanitized
    return value


def display_report_path(path: Path, *, root: Path) -> str:
    """Return a repo-relative path or a host-local placeholder for report output."""

    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(root.expanduser().resolve()))
    except ValueError:
        return f"<host-local-path>/{resolved.name}"


def utc_now() -> datetime:
    """Return a whole-second UTC timestamp for deterministic report schemas."""

    return datetime.now(UTC).replace(microsecond=0)


def isoformat_utc(value: datetime) -> str:
    """Return an ISO-8601 UTC timestamp rounded to whole seconds."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()
