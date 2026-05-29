"""Capability protocols for WorldForge.

A capability is a single, narrow surface a provider can implement: scoring actions, selecting
actions, generating video, etc. Each capability is a ``runtime_checkable`` :class:`typing.Protocol`
so the framework can dispatch a registered implementation into the matching registry by structural
membership rather than by an explicit flag.

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
    GenerationOptions,
    JSONDict,
    ReasoningResult,
    VideoClip,
)

if TYPE_CHECKING:
    from worldforge.providers.base import PredictionPayload, ProviderProfileSpec


CAPABILITY_FIELD_NAMES = (
    "policy",
    "cost",
    "generator",
    "predictor",
    "reasoner",
    "embedder",
    "transferer",
    "planner",
)

CAPABILITY_FIELD_TO_NAME: dict[str, str] = {
    "policy": "policy",
    "cost": "score",
    "generator": "generate",
    "predictor": "predict",
    "reasoner": "reason",
    "embedder": "embed",
    "transferer": "transfer",
    "planner": "plan",
}
CAPABILITY_NAME_TO_FIELD: dict[str, str] = {
    capability: field_name for field_name, capability in CAPABILITY_FIELD_TO_NAME.items()
}


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
class Generator(Protocol):
    """Capability that produces a video clip from a text prompt."""

    name: str
    profile: ProviderProfileSpec | None

    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip: ...


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
class Reasoner(Protocol):
    """Capability that answers a query over an optional world snapshot."""

    name: str
    profile: ProviderProfileSpec | None

    def reason(
        self,
        query: str,
        *,
        world_state: JSONDict | None = None,
    ) -> ReasoningResult: ...


@runtime_checkable
class Embedder(Protocol):
    """Capability that turns text into a fixed-dimensional embedding."""

    name: str
    profile: ProviderProfileSpec | None

    def embed(self, *, text: str) -> EmbeddingResult: ...


@runtime_checkable
class Transferer(Protocol):
    """Capability that re-renders a clip into a target shape and prompt."""

    name: str
    profile: ProviderProfileSpec | None

    def transfer(
        self,
        clip: VideoClip,
        *,
        width: int,
        height: int,
        fps: float,
        prompt: str = "",
        options: GenerationOptions | None = None,
    ) -> VideoClip: ...


@runtime_checkable
class Planner(Protocol):
    """Capability that composes a multi-step plan; reserved for future composition."""

    name: str
    profile: ProviderProfileSpec | None

    def plan(self, *, info: JSONDict) -> ActionPolicyResult: ...


# Mapping from RunnableModel field names to the matching capability protocol class. Used by the
# framework to dispatch a bundle into the per-capability registries; using the dict avoids a long
# chain of branches and keeps the field/protocol pairing readable.
CAPABILITY_PROTOCOLS: dict[str, type] = {
    "policy": Policy,
    "cost": Cost,
    "generator": Generator,
    "predictor": Predictor,
    "reasoner": Reasoner,
    "embedder": Embedder,
    "transferer": Transferer,
    "planner": Planner,
}


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
    generator: Generator | None = None
    predictor: Predictor | None = None
    reasoner: Reasoner | None = None
    embedder: Embedder | None = None
    transferer: Transferer | None = None
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
    "Generator",
    "Planner",
    "Policy",
    "Predictor",
    "Reasoner",
    "RunnableModel",
    "Transferer",
]
