"""Safe report renderer registration for preserved artifacts."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from worldforge.models import (
    JSONDict,
    WorldForgeError,
    _redact_observable_text,
    require_json_dict,
)

RendererPayload = Mapping[str, Any]
RendererCallable = Callable[[RendererPayload], "ReportRenderResult | str"]

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MEDIA_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
_REGISTRY: dict[tuple[str, str], ReportRenderer] = {}


@dataclass(frozen=True, slots=True)
class ReportRenderResult:
    """Rendered report content with an explicit attachment-safety boundary."""

    content: str
    media_type: str
    safe_to_attach: bool
    local_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise WorldForgeError("Report renderer content must be a string.")
        _validate_media_type(self.media_type)
        if not isinstance(self.safe_to_attach, bool):
            raise WorldForgeError("Report renderer safe_to_attach must be a boolean.")
        if not isinstance(self.local_only, bool):
            raise WorldForgeError("Report renderer local_only must be a boolean.")
        if self.safe_to_attach == self.local_only:
            raise WorldForgeError(
                "Report renderer output must be exactly one of safe-to-attach or local-only."
            )
        if self.safe_to_attach and _redact_observable_text(self.content) != self.content:
            raise WorldForgeError("Report renderer safe output contains secret-like material.")

    def to_dict(self) -> JSONDict:
        return {
            "media_type": self.media_type,
            "safe_to_attach": self.safe_to_attach,
            "local_only": self.local_only,
            "size_bytes": len(self.content.encode("utf-8")),
        }


@dataclass(frozen=True, slots=True)
class ReportRenderer:
    """Metadata and callback for one report renderer extension point."""

    artifact_family: str
    output_format: str
    media_type: str
    supported_schemas: tuple[str, ...]
    safe_to_attach: bool
    render: RendererCallable
    description: str = ""

    def __post_init__(self) -> None:
        _validate_identifier(self.artifact_family, field="artifact_family")
        _validate_identifier(self.output_format, field="output_format")
        _validate_media_type(self.media_type)
        if not self.supported_schemas or any(
            not isinstance(schema, str) or not schema.strip() for schema in self.supported_schemas
        ):
            raise WorldForgeError(
                "Report renderer supported_schemas must be a non-empty string tuple."
            )
        if not isinstance(self.safe_to_attach, bool):
            raise WorldForgeError("Report renderer safe_to_attach must be a boolean.")
        if not callable(self.render):
            raise WorldForgeError("Report renderer render must be callable.")
        if not isinstance(self.description, str):
            raise WorldForgeError("Report renderer description must be a string.")

    @property
    def key(self) -> tuple[str, str]:
        return (self.artifact_family, self.output_format)

    def metadata(self) -> JSONDict:
        return {
            "artifact_family": self.artifact_family,
            "output_format": self.output_format,
            "media_type": self.media_type,
            "supported_schemas": list(self.supported_schemas),
            "safe_to_attach": self.safe_to_attach,
            "local_only": not self.safe_to_attach,
            "description": self.description,
        }


def register_report_renderer(renderer: ReportRenderer, *, replace: bool = False) -> None:
    """Register a report renderer for one artifact family and output format."""

    if not isinstance(renderer, ReportRenderer):
        raise WorldForgeError("register_report_renderer requires a ReportRenderer instance.")
    if renderer.key in _REGISTRY and not replace:
        family, output_format = renderer.key
        raise WorldForgeError(f"Report renderer already registered for {family}:{output_format}.")
    _REGISTRY[renderer.key] = renderer


def get_report_renderer(artifact_family: str, output_format: str) -> ReportRenderer:
    """Return a registered report renderer or fail explicitly."""

    key = (
        _validate_identifier(artifact_family, field="artifact_family"),
        _validate_identifier(output_format, field="output_format"),
    )
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise WorldForgeError(
            f"No report renderer registered for {artifact_family}:{output_format}."
        ) from exc


def list_report_renderers(*, artifact_family: str | None = None) -> tuple[JSONDict, ...]:
    """List registered renderer metadata without exposing callbacks."""

    if artifact_family is not None:
        artifact_family = _validate_identifier(artifact_family, field="artifact_family")
    renderers = sorted(_REGISTRY.values(), key=lambda item: item.key)
    if artifact_family is not None:
        renderers = [
            renderer for renderer in renderers if renderer.artifact_family == artifact_family
        ]
    return tuple(renderer.metadata() for renderer in renderers)


def render_report_artifact(
    artifact_family: str,
    output_format: str,
    payload: Mapping[str, Any],
) -> ReportRenderResult:
    """Render one payload through a registered renderer and validate output safety."""

    renderer = get_report_renderer(artifact_family, output_format)
    safe_payload = require_json_dict(dict(payload), name="Report renderer payload")
    rendered = renderer.render(safe_payload)
    if isinstance(rendered, ReportRenderResult):
        result = rendered
    elif isinstance(rendered, str):
        result = ReportRenderResult(
            content=rendered,
            media_type=renderer.media_type,
            safe_to_attach=renderer.safe_to_attach,
            local_only=not renderer.safe_to_attach,
        )
    else:
        raise WorldForgeError("Report renderer must return a string or ReportRenderResult.")
    if result.media_type != renderer.media_type:
        raise WorldForgeError("Report renderer output media_type must match renderer metadata.")
    return result


def _validate_identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise WorldForgeError(
            f"Report renderer {field} must use lowercase letters, numbers, '_' or '-'."
        )
    return value


def _validate_media_type(value: object) -> str:
    if not isinstance(value, str) or not _MEDIA_TYPE_PATTERN.fullmatch(value):
        raise WorldForgeError("Report renderer media_type must be a valid type/subtype string.")
    return value


__all__ = [
    "ReportRenderResult",
    "ReportRenderer",
    "get_report_renderer",
    "list_report_renderers",
    "register_report_renderer",
    "render_report_artifact",
]
