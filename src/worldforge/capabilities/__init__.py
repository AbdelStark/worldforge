"""Capability protocols for WorldForge.

A capability is a single, narrow surface a provider can implement: scoring actions, selecting
actions, predicting world state, embedding text, etc. Each capability is a
``runtime_checkable`` :class:`typing.Protocol` so the framework can dispatch a registered
implementation into the matching registry by structural membership rather than by an explicit flag.

Implementations declare two attributes — ``name`` and ``profile`` — and exactly one capability
method matching the protocol's signature. Implementations stay pure: they return result
dataclasses defined in :mod:`worldforge.models` and never emit observability events themselves.
The framework wraps each registered implementation in an internal observable decorator that adds
:class:`~worldforge.models.ProviderEvent` emission, latency timing, and health tracking.

Composing several capabilities into one logical "model" is optional; use :class:`RunnableModel`
when a single thing genuinely implements multiple capabilities (the mock model is the canonical
example). Single-capability adapters need no wrapper.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    EmbeddingResult,
    JSONDict,
)

if TYPE_CHECKING:
    from worldforge.providers.base import PredictionPayload, ProviderProfileSpec


@dataclass(frozen=True, slots=True)
class _CapabilityDescriptor:
    """Canonical vocabulary for one capability surface.

    The descriptor is the single place that relates the framework's internal field name
    (``cost``), public provider capability name (``score``), protocol, method name, event
    operation, and validated result type. Callers should depend on this descriptor instead of
    carrying local maps that can drift.
    """

    field_name: str
    name: str
    protocol: type
    method_name: str
    operation: str
    result_type_name: str
    benchmarkable: bool = True
    benchmark_order: int | None = None

    @property
    def result_type(self) -> type:
        if self.result_type_name == "PredictionPayload":
            from worldforge.providers.base import PredictionPayload

            return PredictionPayload
        result_types = {
            "ActionPolicyResult": ActionPolicyResult,
            "ActionScoreResult": ActionScoreResult,
            "EmbeddingResult": EmbeddingResult,
        }
        return result_types[self.result_type_name]


CAPABILITY_FIELD_NAMES = (
    "policy",
    "cost",
    "predictor",
    "embedder",
    "planner",
)

# Each protocol is documented in its docstring, including the result type and the call shape the
# framework dispatches. ``runtime_checkable`` enables ``isinstance(x, Cost)`` at registration time.


@runtime_checkable
class Policy(Protocol):
    """Capability that selects actions for a given world snapshot."""

    name: str
    profile: ProviderProfileSpec | None

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult: ...


@runtime_checkable
class Cost(Protocol):
    """Capability that scores a batch of candidate actions or plans."""

    name: str
    profile: ProviderProfileSpec | None

    def score_actions(
        self,
        *,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult: ...


@runtime_checkable
class Predictor(Protocol):
    """Capability that advances world state by ``steps`` under an action."""

    name: str
    profile: ProviderProfileSpec | None

    def predict(
        self,
        world_state: JSONDict,
        action: Action,
        steps: int,
    ) -> PredictionPayload: ...


@runtime_checkable
class Embedder(Protocol):
    """Capability that turns text into a fixed-dimensional embedding."""

    name: str
    profile: ProviderProfileSpec | None

    def embed(self, *, text: str) -> EmbeddingResult: ...


@runtime_checkable
class Planner(Protocol):
    """Capability that composes a multi-step plan; reserved for future composition."""

    name: str
    profile: ProviderProfileSpec | None

    def plan(self, *, info: JSONDict) -> ActionPolicyResult: ...


_CAPABILITY_DESCRIPTORS: dict[str, _CapabilityDescriptor] = {
    "policy": _CapabilityDescriptor(
        field_name="policy",
        name="policy",
        protocol=Policy,
        method_name="select_actions",
        operation="policy",
        result_type_name="ActionPolicyResult",
        benchmark_order=4,
    ),
    "cost": _CapabilityDescriptor(
        field_name="cost",
        name="score",
        protocol=Cost,
        method_name="score_actions",
        operation="score",
        result_type_name="ActionScoreResult",
        benchmark_order=3,
    ),
    "predictor": _CapabilityDescriptor(
        field_name="predictor",
        name="predict",
        protocol=Predictor,
        method_name="predict",
        operation="predict",
        result_type_name="PredictionPayload",
        benchmark_order=1,
    ),
    "embedder": _CapabilityDescriptor(
        field_name="embedder",
        name="embed",
        protocol=Embedder,
        method_name="embed",
        operation="embed",
        result_type_name="EmbeddingResult",
        benchmark_order=2,
    ),
    "planner": _CapabilityDescriptor(
        field_name="planner",
        name="plan",
        protocol=Planner,
        method_name="plan",
        operation="plan",
        result_type_name="ActionPolicyResult",
        benchmarkable=False,
    ),
}
CAPABILITY_FIELD_TO_NAME: dict[str, str] = {
    field_name: descriptor.name for field_name, descriptor in _CAPABILITY_DESCRIPTORS.items()
}
CAPABILITY_NAME_TO_FIELD: dict[str, str] = {
    descriptor.name: field_name for field_name, descriptor in _CAPABILITY_DESCRIPTORS.items()
}
CAPABILITY_PROTOCOLS: dict[str, type] = {
    field_name: descriptor.protocol for field_name, descriptor in _CAPABILITY_DESCRIPTORS.items()
}
_CAPABILITY_METHOD_MAP: dict[str, tuple[str, str]] = {
    field_name: (descriptor.method_name, descriptor.operation)
    for field_name, descriptor in _CAPABILITY_DESCRIPTORS.items()
}
_BENCHMARKABLE_CAPABILITY_NAMES = tuple(
    descriptor.name
    for descriptor in sorted(
        _CAPABILITY_DESCRIPTORS.values(),
        key=lambda descriptor: descriptor.benchmark_order or 999,
    )
    if descriptor.benchmarkable
)


def _capability_descriptor(field_name: str) -> _CapabilityDescriptor:
    """Return the canonical descriptor for a capability field name."""

    return _CAPABILITY_DESCRIPTORS[field_name]


@dataclass(slots=True)
class RunnableModel:
    """Optional bundle that groups several capability implementations under one name.

    Use this for adapters that genuinely implement multiple capabilities (mock, multi-modal
    vendors). For single-capability adapters, prefer registering the implementation directly.
    Registration of a ``RunnableModel`` walks each non-``None`` capability slot and indexes it into
    the matching per-capability registry.
    """

    name: str
    policy: Policy | None = None
    cost: Cost | None = None
    predictor: Predictor | None = None
    embedder: Embedder | None = None
    planner: Planner | None = None
    profile: ProviderProfileSpec | None = None

    def capability_fields(self) -> Iterator[tuple[str, object]]:
        """Yield ``(field_name, impl)`` pairs for every non-``None`` capability slot."""

        for field_name in CAPABILITY_FIELD_NAMES:
            impl = getattr(self, field_name)
            if impl is not None:
                yield field_name, impl


__all__ = [
    "CAPABILITY_FIELD_NAMES",
    "CAPABILITY_FIELD_TO_NAME",
    "CAPABILITY_NAME_TO_FIELD",
    "CAPABILITY_PROTOCOLS",
    "Cost",
    "Embedder",
    "Planner",
    "Policy",
    "Predictor",
    "RunnableModel",
]
