"""Loader for the WorldForge capability fixture corpus.

The corpus is a small set of JSON fixtures that name canonical input shapes for each provider
capability — ``predict``, ``embed``, ``score``, and
``policy``. Every capability ships at least one valid baseline fixture and two invalid boundary
fixtures so conformance tests, evaluation suites, and provider authors can exercise public
input validation without re-deriving payloads each time.

Fixtures live under :mod:`worldforge.testing.fixtures` (the package, with capability-named
subpackages) so they are part of the wheel and stable across release branches. Consumers
should call the public helpers exposed through :mod:`worldforge.testing` (e.g.
:func:`load_capability_fixture`).

Each fixture file follows this envelope shape::

    {
      "schema_version": 1,
      "id": "<capability>.<name>",
      "capability": "<predict|embed|score|policy>",
      "data_class": "synthetic" | "captured" | "host-supplied",
      "expected": "valid" | "invalid",
      "expected_error_pattern": "<regex>" | null,
      "description": "...",
      "payload": { ... capability-specific shape ... }
    }

The ``payload`` keys map directly onto the keyword arguments of the matching
``assert_*_conformance()`` helpers in :mod:`worldforge.testing.providers` so a caller can pass
``fixture.payload`` straight through.

Cardinality and ownership are documented in
``src/worldforge/testing/fixtures/README.md``; new contributors should read that file before
adding fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

from worldforge.models import JSONDict, WorldForgeError

CAPABILITY_FIXTURE_NAMES: tuple[str, ...] = (
    "predict",
    "embed",
    "score",
    "policy",
)
"""Capabilities covered by the fixture corpus, in deterministic load order."""

FIXTURE_SCHEMA_VERSION = 1
"""Schema version every corpus fixture file declares."""

_DATA_CLASSES = ("synthetic", "captured", "host-supplied")
_EXPECTED_OUTCOMES = ("valid", "invalid")

_FIXTURE_PACKAGE = "worldforge.testing.fixtures"


@dataclass(frozen=True, slots=True)
class CapabilityFixture:
    """A validated fixture envelope from the WorldForge capability corpus."""

    id: str
    capability: str
    data_class: str
    expected: str
    expected_error_pattern: str | None
    description: str
    payload: JSONDict
    schema_version: int = FIXTURE_SCHEMA_VERSION

    def is_valid(self) -> bool:
        """Return ``True`` if the fixture represents a valid public input."""

        return self.expected == "valid"

    def to_dict(self) -> JSONDict:
        """Return the canonical envelope shape backing this fixture."""

        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "capability": self.capability,
            "data_class": self.data_class,
            "expected": self.expected,
            "expected_error_pattern": self.expected_error_pattern,
            "description": self.description,
            "payload": dict(self.payload),
        }


def _capability_root(capability: str) -> Traversable:
    if capability not in CAPABILITY_FIXTURE_NAMES:
        known = ", ".join(CAPABILITY_FIXTURE_NAMES)
        raise WorldForgeError(
            f"Unknown capability '{capability}' for fixture corpus. Known capabilities: {known}."
        )
    return resources.files(f"{_FIXTURE_PACKAGE}.{capability}")


def _parse_fixture(payload: Mapping[str, Any], *, source: str) -> CapabilityFixture:
    _require_fixture_mapping(payload, source=source)
    schema_version = _fixture_schema_version(payload, source=source)
    fixture_id = _fixture_required_text(payload, "id", source=source)
    capability = _fixture_choice(
        payload,
        "capability",
        choices=CAPABILITY_FIXTURE_NAMES,
        source=source,
    )
    data_class = _fixture_choice(payload, "data_class", choices=_DATA_CLASSES, source=source)
    expected = _fixture_choice(payload, "expected", choices=_EXPECTED_OUTCOMES, source=source)
    expected_error_pattern = _fixture_expected_error_pattern(
        payload,
        expected=expected,
        source=source,
    )
    description = _fixture_required_text(payload, "description", source=source)
    fixture_payload = _fixture_payload(payload, source=source)
    return CapabilityFixture(
        id=fixture_id,
        capability=capability,
        data_class=data_class,
        expected=expected,
        expected_error_pattern=expected_error_pattern,
        description=description,
        payload=dict(fixture_payload),
        schema_version=schema_version,
    )


def _require_fixture_mapping(payload: object, *, source: str) -> None:
    if not isinstance(payload, Mapping):
        raise WorldForgeError(f"{source} must contain a JSON object.")


def _fixture_schema_version(payload: Mapping[str, Any], *, source: str) -> int:
    schema_version = payload.get("schema_version")
    if schema_version != FIXTURE_SCHEMA_VERSION:
        raise WorldForgeError(
            f"{source} schema_version must be {FIXTURE_SCHEMA_VERSION}, got {schema_version!r}."
        )
    return schema_version


def _fixture_required_text(payload: Mapping[str, Any], key: str, *, source: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{source} '{key}' must be a non-empty string.")
    return value


def _fixture_choice(
    payload: Mapping[str, Any],
    key: str,
    *,
    choices: tuple[str, ...],
    source: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value not in choices:
        raise WorldForgeError(f"{source} '{key}' must be one of {', '.join(choices)}.")
    return value


def _fixture_expected_error_pattern(
    payload: Mapping[str, Any],
    *,
    expected: str,
    source: str,
) -> str | None:
    expected_error_pattern = payload.get("expected_error_pattern")
    if expected == "invalid":
        return _invalid_fixture_error_pattern(expected_error_pattern, source=source)
    if expected_error_pattern is not None:
        raise WorldForgeError(f"{source} valid fixtures must leave expected_error_pattern null.")
    return None


def _invalid_fixture_error_pattern(value: object, *, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(
            f"{source} invalid fixtures must declare a non-empty expected_error_pattern."
        )
    return value


def _fixture_payload(payload: Mapping[str, Any], *, source: str) -> JSONDict:
    fixture_payload = payload.get("payload")
    if not isinstance(fixture_payload, dict):
        raise WorldForgeError(f"{source} 'payload' must be a JSON object.")
    return dict(fixture_payload)


def list_fixture_names(capability: str) -> tuple[str, ...]:
    """Return the sorted fixture names available for a capability."""

    root = _capability_root(capability)
    names = sorted(
        entry.name.removesuffix(".json") for entry in root.iterdir() if entry.name.endswith(".json")
    )
    return tuple(names)


def load_capability_fixture(capability: str, name: str) -> CapabilityFixture:
    """Load and validate a single capability fixture by name.

    ``name`` is the file stem (e.g. ``valid_baseline``); it does not include the ``.json``
    extension. Raises :class:`WorldForgeError` for unknown capabilities, missing files,
    malformed JSON, or envelopes that fail validation.
    """

    if not isinstance(name, str) or not name.strip():
        raise WorldForgeError("Fixture name must be a non-empty string.")
    root = _capability_root(capability)
    source = f"{capability}/{name}.json"
    try:
        text = root.joinpath(f"{name}.json").read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorldForgeError(f"Capability fixture not found: {source}.") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Capability fixture {source} contains invalid JSON.") from exc
    return _parse_fixture(payload, source=source)


def iter_capability_fixtures(capability: str) -> Iterator[CapabilityFixture]:
    """Yield every fixture for ``capability`` in deterministic name order."""

    for name in list_fixture_names(capability):
        yield load_capability_fixture(capability, name)


def iter_all_fixtures() -> Iterator[CapabilityFixture]:
    """Yield every fixture across every capability in deterministic order."""

    for capability in CAPABILITY_FIXTURE_NAMES:
        yield from iter_capability_fixtures(capability)


__all__ = [
    "CAPABILITY_FIXTURE_NAMES",
    "FIXTURE_SCHEMA_VERSION",
    "CapabilityFixture",
    "iter_all_fixtures",
    "iter_capability_fixtures",
    "list_fixture_names",
    "load_capability_fixture",
]
