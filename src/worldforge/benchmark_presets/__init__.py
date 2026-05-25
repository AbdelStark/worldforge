"""Named benchmark presets for release regressions and provider evidence.

Presets bundle a deterministic input fixture, an optional budget file, and a runtime-profile
gate so maintainers can run "named" benchmark workloads without re-deriving inputs and
budgets each time. Each preset belongs to one of four categories:

- ``checkout-safe``: runs without credentials, network, GPUs, or optional runtimes; safe to
  invoke from a clean checkout and from CI.
- ``remote-media``: requires a remote-media provider (Cosmos or Runway) with its environment
  configured; the CLI skips with a typed reason when the env is missing.
- ``prepared-host``: requires a host that owns the optional runtime (LeWorldModel for ``score``;
  LeRobot or GR00T for ``policy``); the CLI skips with a typed reason when the env is missing.
- ``release``: gated regression check used for release evidence; bundles strict budgets that
  fail the run when threshold violations land.

The data files under :mod:`worldforge.benchmark_presets._data` are JSON documents that match
the wire format of ``--input-file`` and ``--budget-file``. The presets ship with the wheel so
``worldforge benchmark --preset <name>`` works from a ``pip install`` without checkout-time
discovery.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from worldforge.benchmark import (
    BENCHMARKABLE_OPERATIONS,
    BenchmarkBudget,
    BenchmarkInputs,
    load_benchmark_budgets,
    load_benchmark_inputs,
)
from worldforge.models import JSONDict, WorldForgeError
from worldforge.testing.runtime_profiles import (
    PROVIDER_RUNTIME_PROFILES_BY_NAME,
    provider_profile_skip_reason,
)

PRESET_CATEGORIES: tuple[str, ...] = (
    "checkout-safe",
    "remote-media",
    "prepared-host",
    "release",
)
"""Categories every preset belongs to. The CLI list output groups by category."""

_DATA_PACKAGE = "worldforge.benchmark_presets._data"


@dataclass(frozen=True, slots=True)
class BenchmarkPreset:
    """A named benchmark configuration suitable for release regressions or provider evidence."""

    name: str
    title: str
    summary: str
    category: str
    providers: tuple[str, ...]
    operations: tuple[str, ...]
    iterations: int
    concurrency: int
    inputs_file: str | None
    budget_file: str | None
    failure_tolerance: str
    requires_provider_profiles: tuple[str, ...] = ()
    requires_provider_choice: tuple[str, ...] = ()
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise WorldForgeError("BenchmarkPreset name must be a non-empty string.")
        if self.category not in PRESET_CATEGORIES:
            known = ", ".join(PRESET_CATEGORIES)
            raise WorldForgeError(f"BenchmarkPreset category must be one of: {known}.")
        if not self.providers:
            raise WorldForgeError("BenchmarkPreset must declare at least one provider.")
        if not self.operations:
            raise WorldForgeError("BenchmarkPreset must declare at least one operation.")
        unknown = [op for op in self.operations if op not in BENCHMARKABLE_OPERATIONS]
        if unknown:
            joined = ", ".join(unknown)
            raise WorldForgeError(f"BenchmarkPreset has unknown operations: {joined}.")
        if self.iterations <= 0:
            raise WorldForgeError("BenchmarkPreset iterations must be greater than 0.")
        if self.concurrency <= 0:
            raise WorldForgeError("BenchmarkPreset concurrency must be greater than 0.")
        if self.failure_tolerance not in {"fail-on-violation", "skip-when-env-missing"}:
            raise WorldForgeError(
                "BenchmarkPreset failure_tolerance must be 'fail-on-violation' "
                "or 'skip-when-env-missing'."
            )
        unknown_profiles = [
            profile
            for profile in (*self.requires_provider_profiles, *self.requires_provider_choice)
            if profile not in PROVIDER_RUNTIME_PROFILES_BY_NAME
        ]
        if unknown_profiles:
            joined = ", ".join(unknown_profiles)
            raise WorldForgeError(
                f"BenchmarkPreset references unknown provider runtime profiles: {joined}."
            )

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "providers": list(self.providers),
            "operations": list(self.operations),
            "iterations": self.iterations,
            "concurrency": self.concurrency,
            "inputs_file": self.inputs_file,
            "budget_file": self.budget_file,
            "failure_tolerance": self.failure_tolerance,
            "requires_provider_profiles": list(self.requires_provider_profiles),
            "requires_provider_choice": list(self.requires_provider_choice),
            "notes": self.notes,
            "tags": list(self.tags),
        }

    def skip_reason(self, environ: Mapping[str, str] | None = None) -> str | None:
        """Return a typed skip reason when a required runtime profile is unconfigured.

        Presets in the ``checkout-safe`` and ``release`` categories never skip; ``remote-media``
        and ``prepared-host`` presets skip with the first unmet provider profile reason.
        """

        env = os.environ if environ is None else environ
        for profile in self.requires_provider_profiles:
            reason = provider_profile_skip_reason(profile, env)
            if reason is not None:
                return reason
        if self.requires_provider_choice:
            reasons: list[str] = []
            for profile in self.requires_provider_choice:
                reason = provider_profile_skip_reason(profile, env)
                if reason is None:
                    return None
                reasons.append(reason)
            return "no eligible provider profile is configured: " + "; ".join(reasons)
        return None

    def configured_providers(
        self,
        environ: Mapping[str, str] | None = None,
    ) -> tuple[str, ...]:
        """Return the subset of ``providers`` whose runtime profile is configured.

        Always returns the full ``providers`` tuple for presets that do not gate on a
        provider runtime profile (``checkout-safe`` and ``release`` categories).
        """

        env = os.environ if environ is None else environ
        gated = set(self.requires_provider_profiles) | set(self.requires_provider_choice)
        if not gated:
            return self.providers
        configured = [
            provider
            for provider in self.providers
            if provider not in gated or provider_profile_skip_reason(provider, env) is None
        ]
        return tuple(configured)


def _data_text(filename: str) -> str:
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorldForgeError(f"Benchmark preset data file not found: {filename}") from exc


def _data_payload(filename: str) -> Any:
    try:
        return json.loads(_data_text(filename))
    except json.JSONDecodeError as exc:
        raise WorldForgeError(
            f"Benchmark preset data file {filename} contains invalid JSON."
        ) from exc


def load_preset_inputs(preset: BenchmarkPreset) -> BenchmarkInputs:
    """Return validated :class:`BenchmarkInputs` for a preset.

    Returns the default ``BenchmarkInputs()`` when the preset does not bundle an inputs file
    (e.g. presets that exercise only operations whose mock defaults are sufficient).
    """

    if preset.inputs_file is None:
        return BenchmarkInputs()
    return load_benchmark_inputs(_data_payload(preset.inputs_file))


def load_preset_budgets(preset: BenchmarkPreset) -> list[BenchmarkBudget]:
    """Return validated :class:`BenchmarkBudget` entries for a preset, or ``[]`` when absent."""

    if preset.budget_file is None:
        return []
    return load_benchmark_budgets(_data_payload(preset.budget_file))


def preset_inputs_payload(preset: BenchmarkPreset) -> JSONDict | None:
    """Return the raw inputs JSON for a preset, useful for digesting in run manifests."""

    if preset.inputs_file is None:
        return None
    payload = _data_payload(preset.inputs_file)
    if not isinstance(payload, dict):
        raise WorldForgeError(f"Preset inputs payload {preset.inputs_file} must be a JSON object.")
    return payload


def preset_budget_payload(preset: BenchmarkPreset) -> JSONDict | None:
    """Return the raw budget JSON for a preset, or ``None`` when no budget is bundled."""

    if preset.budget_file is None:
        return None
    payload = _data_payload(preset.budget_file)
    if not isinstance(payload, dict):
        raise WorldForgeError(f"Preset budget payload {preset.budget_file} must be a JSON object.")
    return payload


_BENCHMARK_PRESETS: tuple[BenchmarkPreset, ...] = (
    BenchmarkPreset(
        name="mock-smoke",
        title="Mock provider smoke",
        summary=(
            "Fast checkout-safe regression check: runs the mock provider across predict, generate, "
            "and embed with five iterations and a tight success-rate gate."
        ),
        category="checkout-safe",
        providers=("mock",),
        operations=("predict", "generate", "embed"),
        iterations=5,
        concurrency=1,
        inputs_file="inputs-mock.json",
        budget_file="budget-mock-smoke.json",
        failure_tolerance="fail-on-violation",
        notes="Use this preset for every-branch CI regression checks.",
        tags=("ci", "smoke"),
    ),
    BenchmarkPreset(
        name="parser-overhead",
        title="Provider parser overhead",
        summary=(
            "Latency-bounded measurement of WorldForge adapter-path overhead. Runs every "
            "mock-supported operation with twenty serial iterations to stabilise latency stats."
        ),
        category="checkout-safe",
        providers=("mock",),
        operations=("predict", "reason", "generate", "transfer", "embed"),
        iterations=20,
        concurrency=1,
        inputs_file="inputs-mock.json",
        budget_file="budget-parser-overhead.json",
        failure_tolerance="fail-on-violation",
        notes=(
            "Latencies above the documented thresholds usually mean an unrelated import or "
            "validation regression in the adapter path; preserve the run workspace before "
            "loosening budgets."
        ),
        tags=("ci", "latency"),
    ),
    BenchmarkPreset(
        name="remote-media-dryrun",
        title="Remote media dry-run",
        summary=(
            "Single-iteration dry-run for remote media providers. Skips with a typed reason when "
            "neither Cosmos nor Runway is configured."
        ),
        category="remote-media",
        providers=("cosmos", "runway"),
        operations=("generate",),
        iterations=1,
        concurrency=1,
        inputs_file="inputs-remote-media.json",
        budget_file=None,
        failure_tolerance="skip-when-env-missing",
        requires_provider_choice=("cosmos", "runway"),
        notes=(
            "Configure COSMOS_BASE_URL, RUNWAYML_API_SECRET, or RUNWAY_API_SECRET on a host "
            "that is allowed to reach the upstream API. The preset does not assert latency or "
            "throughput claims; treat the report as informational evidence."
        ),
        tags=("remote",),
    ),
    BenchmarkPreset(
        name="prepared-host",
        title="Prepared-host score and policy",
        summary=(
            "Three-iteration evidence run for prepared-host providers. Skips with a typed reason "
            "when no eligible runtime (LeWorldModel for score; LeRobot or GR00T for policy) is "
            "configured."
        ),
        category="prepared-host",
        providers=("leworldmodel", "lerobot", "gr00t"),
        operations=("score", "policy"),
        iterations=3,
        concurrency=1,
        inputs_file="inputs-prepared-host.json",
        budget_file=None,
        failure_tolerance="skip-when-env-missing",
        requires_provider_choice=("leworldmodel", "lerobot", "gr00t"),
        notes=(
            "Score and policy expectations vary across runtimes. The preset emits sanitized "
            "ProviderEvent metadata only and does not capture raw checkpoint contents."
        ),
        tags=("optional-runtime",),
    ),
    BenchmarkPreset(
        name="release-evidence",
        title="Release evidence",
        summary=(
            "Release-gated regression check across every mock-supported operation with strict "
            "latency, throughput, and success-rate budgets. Pair with --run-workspace to "
            "preserve manifests for release attestation."
        ),
        category="release",
        providers=("mock",),
        operations=("predict", "reason", "generate", "transfer", "embed"),
        iterations=10,
        concurrency=2,
        inputs_file="inputs-mock.json",
        budget_file="budget-release-evidence.json",
        failure_tolerance="fail-on-violation",
        notes=(
            "Failures must be triaged with preserved artifacts before threshold loosening; the "
            "release-evidence budget tracks deliberate, machine-class-aware regressions only."
        ),
        tags=("release",),
    ),
)


_BENCHMARK_PRESETS_BY_NAME: dict[str, BenchmarkPreset] = {
    preset.name: preset for preset in _BENCHMARK_PRESETS
}


def list_preset_names() -> tuple[str, ...]:
    """Return the canonical preset names in display order."""

    return tuple(preset.name for preset in _BENCHMARK_PRESETS)


def list_presets() -> tuple[BenchmarkPreset, ...]:
    """Return every preset in display order."""

    return _BENCHMARK_PRESETS


def get_preset(name: str) -> BenchmarkPreset:
    """Return one preset by name. Raises :class:`WorldForgeError` for unknown names."""

    try:
        return _BENCHMARK_PRESETS_BY_NAME[name]
    except KeyError as exc:
        known = ", ".join(_BENCHMARK_PRESETS_BY_NAME)
        raise WorldForgeError(
            f"Unknown benchmark preset '{name}'. Known presets: {known}."
        ) from exc


__all__ = [
    "PRESET_CATEGORIES",
    "BenchmarkPreset",
    "get_preset",
    "list_preset_names",
    "list_presets",
    "load_preset_budgets",
    "load_preset_inputs",
    "preset_budget_payload",
    "preset_inputs_payload",
]
