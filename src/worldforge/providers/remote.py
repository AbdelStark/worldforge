"""Scaffold adapters for providers that are not yet fully implemented."""

from __future__ import annotations

import os
from collections.abc import Callable

from worldforge.models import (
    Action,
    EmbeddingResult,
    GenerationOptions,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ReasoningResult,
    VideoClip,
)

from .base import PredictionPayload, ProviderError, ProviderProfileSpec, RemoteProvider
from .mock import MockProvider

SCAFFOLD_SURROGATE_ENV_VAR = "WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


class StubRemoteProvider(RemoteProvider):
    """Shared behavior for credential-gated providers still backed by local surrogates."""

    _mock_surrogate: MockProvider | None = None

    @property
    def _surrogate(self) -> MockProvider:
        if self._mock_surrogate is None:
            self._mock_surrogate = MockProvider(
                name=self.name,
                event_handler=self.event_handler,
            )
        return self._mock_surrogate

    def _require_scaffold_surrogate_enabled(self) -> None:
        enabled = os.environ.get(SCAFFOLD_SURROGATE_ENV_VAR, "").strip().lower()
        if enabled not in _TRUTHY_ENV_VALUES:
            raise ProviderError(
                f"Provider '{self.name}' is a scaffold and does not advertise executable "
                f"capabilities. Set {SCAFFOLD_SURROGATE_ENV_VAR}=1 only for local "
                "surrogate testing."
            )

    def predict(self, world_state: JSONDict, action: Action, steps: int) -> PredictionPayload:
        self._require_scaffold_surrogate_enabled()
        self._require_credentials()
        payload = self._surrogate.predict(world_state, action, steps)
        payload.metadata["mode"] = "stub-remote-adapter"
        payload.metadata["credential_env"] = self.env_var
        return payload

    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        self._require_scaffold_surrogate_enabled()
        self._require_credentials()
        clip = self._surrogate.generate(prompt, duration_seconds, options=options)
        clip.metadata["mode"] = "stub-remote-adapter"
        clip.metadata["credential_env"] = self.env_var
        return clip

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
        self._require_scaffold_surrogate_enabled()
        self._require_credentials()
        transferred = self._surrogate.transfer(
            clip,
            width=width,
            height=height,
            fps=fps,
            prompt=prompt,
            options=options,
        )
        transferred.metadata["mode"] = "stub-remote-adapter"
        transferred.metadata["credential_env"] = self.env_var
        return transferred

    def reason(self, query: str, *, world_state: JSONDict | None = None) -> ReasoningResult:
        self._require_scaffold_surrogate_enabled()
        self._require_credentials()
        result = self._surrogate.reason(query, world_state=world_state)
        result.evidence.append(f"Executed via stub adapter gated by {self.env_var}")
        return result

    def embed(self, *, text: str) -> EmbeddingResult:
        self._require_scaffold_surrogate_enabled()
        self._require_credentials()
        return self._surrogate.embed(text=text)


class JepaProvider(StubRemoteProvider):
    """Python adapter placeholder for JEPA-family models."""

    env_var = "JEPA_MODEL_PATH"

    def __init__(
        self,
        name: str = "jepa",
        *,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(),
            profile=ProviderProfileSpec(
                description="Python adapter surface for JEPA-family models.",
                implementation_status="scaffold",
                supported_modalities=("world_state", "text"),
                artifact_types=(),
                notes=(
                    "Capability-fail-closed scaffold adapter; it is not a real JEPA runtime.",
                    "A deterministic local surrogate exists only behind "
                    f"{SCAFFOLD_SURROGATE_ENV_VAR}=1 for adapter testing.",
                ),
                default_model="jepa-scaffold-v1",
                supported_models=("jepa-scaffold-v1",),
            ),
            event_handler=event_handler,
        )


class GenieProvider(StubRemoteProvider):
    """Python adapter placeholder for Genie-family models."""

    env_var = "GENIE_API_KEY"

    def __init__(
        self,
        name: str = "genie",
        *,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(),
            profile=ProviderProfileSpec(
                description="Python adapter surface for Genie-family models.",
                implementation_status="scaffold",
                supported_modalities=("world_state", "text", "video"),
                artifact_types=(),
                notes=(
                    "Capability-fail-closed scaffold adapter; it is not a real Genie runtime.",
                    "Project Genie is currently documented as an experimental web prototype, "
                    "not a supported automation API.",
                    "A deterministic local surrogate exists only behind "
                    f"{SCAFFOLD_SURROGATE_ENV_VAR}=1 for adapter testing.",
                ),
                default_model="genie-scaffold-v1",
                supported_models=("genie-scaffold-v1",),
            ),
            event_handler=event_handler,
        )
