"""Provider-facing redaction and observable-target sanitization helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from worldforge._model_utils import WorldForgeError

_REDACTED_OBSERVABLE_VALUE = "[redacted]"
_SENSITIVE_FIELD_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|secret|signature|signed[_-]?url|token)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"\b([A-Za-z0-9_-]*(?:api[_-]?key|authorization|credential|password|secret|signature|signed[_-]?url|token)[A-Za-z0-9_-]*)=([^&\s,;]+)",
    re.IGNORECASE,
)
_SENSITIVE_COLON_PATTERN = re.compile(
    r"(?P<key_quote>[\"']?)"
    r"(?P<key>[A-Za-z0-9_-]*(?:api[_-]?key|authorization|bearer|credential|password|secret|signature|signed[_-]?url|token)[A-Za-z0-9_-]*)"
    r"(?P=key_quote)\s*:\s*"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^,\s;}]+)",
    re.IGNORECASE,
)
_BEARER_VALUE_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_URL_IN_TEXT_PATTERN = re.compile(r"https?://[^\s\"'<>]+")


def _sanitize_observable_target(value: object | None) -> str | None:
    """Return a provider event target safe for logs and metrics."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise WorldForgeError("ProviderEvent target must be a string when provided.")
    target = value.strip()
    if not target:
        return None
    try:
        parts = urlsplit(target)
    except ValueError:
        stripped = target.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
        return stripped or _REDACTED_OBSERVABLE_VALUE
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        # Signed artifact URLs and bearer-style presigned URLs keep credentials in
        # query strings. Provider events need route-level context, not secrets.
        netloc = parts.netloc.rsplit("@", maxsplit=1)[-1]
        sanitized = urlunsplit((parts.scheme, netloc, parts.path, "", ""))
        return sanitized or _REDACTED_OBSERVABLE_VALUE
    return target


def _sanitize_observable_id(value: object | None, *, name: str) -> str | None:
    """Return a provider event correlation identifier safe for logs."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise WorldForgeError(f"{name} must be a string when provided.")
    sanitized = _redact_observable_text(value.strip())
    return sanitized or None


def _redact_observable_text(value: str) -> str:
    """Redact common secret shapes from provider event text."""

    def _redact_colon_assignment(match: re.Match[str]) -> str:
        raw_value = match.group("value")
        quote = raw_value[0] if raw_value[:1] in {"'", '"'} else ""
        redacted_value = f"{quote}{_REDACTED_OBSERVABLE_VALUE}{quote}"
        key_quote = match.group("key_quote")
        return f"{key_quote}{match.group('key')}{key_quote}: {redacted_value}"

    redacted = _URL_IN_TEXT_PATTERN.sub(
        lambda match: _sanitize_observable_target(match.group(0)) or _REDACTED_OBSERVABLE_VALUE,
        value,
    )
    redacted = _BEARER_VALUE_PATTERN.sub("Bearer [redacted]", redacted)
    redacted = _SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}={_REDACTED_OBSERVABLE_VALUE}",
        redacted,
    )
    return _SENSITIVE_COLON_PATTERN.sub(_redact_colon_assignment, redacted)


def _redact_observable_value(value: Any, *, key: str | None = None) -> Any:
    """Redact obvious secrets from nested provider event metadata."""

    if key is not None and _SENSITIVE_FIELD_PATTERN.search(key):
        return _REDACTED_OBSERVABLE_VALUE
    if isinstance(value, str):
        return _redact_observable_text(value)
    if isinstance(value, dict):
        return {
            item_key: _redact_observable_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_observable_value(item) for item in value]
    return value
