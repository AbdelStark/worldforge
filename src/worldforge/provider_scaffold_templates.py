"""Capability templates used by provider scaffold rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityTestTemplate:
    capability: str
    function_suffix: str
    setup_lines: tuple[str, ...]
    call_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityStubTemplate:
    capability: str
    source: str


CAPABILITY_MODEL_IMPORTS: dict[str, tuple[str, ...]] = {
    "predict": ("Action", "JSONDict"),
    "embed": ("EmbeddingResult",),
    "score": ("ActionScoreResult", "JSONDict"),
    "policy": ("ActionPolicyResult", "JSONDict"),
}


CAPABILITY_STUB_TEMPLATES = (
    CapabilityStubTemplate(
        capability="predict",
        source="""
    def predict(self, world_state: JSONDict, action: Action, steps: int) -> PredictionPayload:
        raise ProviderError(
            f"Provider '{self.name}' predict() scaffold is not implemented yet."
        )
""",
    ),
    CapabilityStubTemplate(
        capability="embed",
        source="""
    def embed(self, *, text: str) -> EmbeddingResult:
        raise ProviderError(
            f"Provider '{self.name}' embed() scaffold is not implemented yet."
        )
""",
    ),
    CapabilityStubTemplate(
        capability="score",
        source="""
    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        raise ProviderError(
            f"Provider '{self.name}' score_actions() scaffold is not implemented yet."
        )
""",
    ),
    CapabilityStubTemplate(
        capability="policy",
        source="""
    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        raise ProviderError(
            f"Provider '{self.name}' select_actions() scaffold is not implemented yet."
        )
""",
    ),
)


CAPABILITY_TEST_TEMPLATES = (
    CapabilityTestTemplate(
        capability="predict",
        function_suffix="predict",
        setup_lines=(),
        call_lines=("        provider.predict({}, Action.noop(), 1)",),
    ),
    CapabilityTestTemplate(
        capability="embed",
        function_suffix="embed",
        setup_lines=(),
        call_lines=('        provider.embed(text="query")',),
    ),
    CapabilityTestTemplate(
        capability="score",
        function_suffix="score_actions",
        setup_lines=(),
        call_lines=("        provider.score_actions(info={}, action_candidates=[])",),
    ),
    CapabilityTestTemplate(
        capability="policy",
        function_suffix="select_actions",
        setup_lines=(),
        call_lines=("        provider.select_actions(info={})",),
    ),
)


__all__ = [
    "CAPABILITY_MODEL_IMPORTS",
    "CAPABILITY_STUB_TEMPLATES",
    "CAPABILITY_TEST_TEMPLATES",
    "CapabilityStubTemplate",
    "CapabilityTestTemplate",
]
