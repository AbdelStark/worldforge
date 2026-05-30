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
    "generate": ("GenerationOptions", "VideoClip"),
    "transfer": ("GenerationOptions", "VideoClip"),
    "reason": ("JSONDict", "ReasoningResult"),
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
        capability="generate",
        source="""
    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        raise ProviderError(
            f"Provider '{self.name}' generate() scaffold is not implemented yet."
        )
""",
    ),
    CapabilityStubTemplate(
        capability="transfer",
        source="""
    def transfer(
        self,
        clip: VideoClip,
        *,
        width: int,
        height: int,
        fps: float,
        prompt: str = "",
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        raise ProviderError(
            f"Provider '{self.name}' transfer() scaffold is not implemented yet."
        )
""",
    ),
    CapabilityStubTemplate(
        capability="reason",
        source="""
    def reason(self, query: str, *, world_state: JSONDict | None = None) -> ReasoningResult:
        raise ProviderError(
            f"Provider '{self.name}' reason() scaffold is not implemented yet."
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
        capability="generate",
        function_suffix="generate",
        setup_lines=(),
        call_lines=('        provider.generate("prompt", 1.0)',),
    ),
    CapabilityTestTemplate(
        capability="transfer",
        function_suffix="transfer",
        setup_lines=(
            "    clip = VideoClip(",
            '        frames=[b"frame"],',
            "        fps=1.0,",
            "        resolution=(1, 1),",
            "        duration_seconds=1.0,",
            "    )",
            "",
        ),
        call_lines=("        provider.transfer(clip, width=1, height=1, fps=1.0)",),
    ),
    CapabilityTestTemplate(
        capability="reason",
        function_suffix="reason",
        setup_lines=(),
        call_lines=('        provider.reason("query")',),
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
