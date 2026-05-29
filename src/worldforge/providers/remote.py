"""Scaffold adapters for providers that are not yet fully implemented."""

from __future__ import annotations

import os
from collections.abc import Callable
from time import perf_counter

from worldforge.models import (
    Action,
    ActionScoreResult,
    EmbeddingResult,
    GenerationOptions,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ReasoningResult,
    VideoClip,
    WorldForgeError,
)

from ._config import (
    ProviderConfigSummary,
    config_field_summary,
    config_source,
    env_value,
    optional_non_empty,
)
from .base import PredictionPayload, ProviderError, ProviderProfileSpec, RemoteProvider
from .jepa_wms import JEPAWMSProvider, TorchHubJEPAWMSRuntime
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


JEPA_MODEL_NAME_ENV_VAR = "JEPA_MODEL_NAME"
JEPA_MODEL_PATH_ENV_VAR = "JEPA_MODEL_PATH"
JEPA_DEVICE_ENV_VAR = "JEPA_DEVICE"
DEFAULT_JEPA_HUB_REPO = "facebookresearch/jepa-wms"


class JepaProvider(JEPAWMSProvider):
    """Score-only JEPA adapter backed by the upstream JEPA-WMS torch-hub API."""

    env_var = None

    def __init__(
        self,
        name: str = "jepa",
        *,
        model_name: str | None = None,
        model_path: str | None = None,
        hub_repo: str = DEFAULT_JEPA_HUB_REPO,
        device: str | None = None,
        pretrained: bool = True,
        trust_repo: bool | None = None,
        hub_loader: Callable[..., object] | None = None,
        torch_module: object | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        self.model_name = optional_non_empty(
            model_name if model_name is not None else env_value(JEPA_MODEL_NAME_ENV_VAR),
            name="JEPA model_name",
        )
        self.legacy_model_path = optional_non_empty(
            model_path if model_path is not None else env_value(JEPA_MODEL_PATH_ENV_VAR),
            name="JEPA model_path",
        )
        self.device = optional_non_empty(
            device if device is not None else env_value(JEPA_DEVICE_ENV_VAR),
            name="JEPA device",
        )
        self.hub_repo = optional_non_empty(hub_repo, name="JEPA hub_repo")
        if self.hub_repo is None:
            raise WorldForgeError("JEPA hub_repo must be provided.")
        runtime = None
        if self.model_name is not None:
            runtime = TorchHubJEPAWMSRuntime(
                model_name=self.model_name,
                hub_repo=self.hub_repo,
                device=self.device,
                pretrained=pretrained,
                trust_repo=trust_repo,
                hub_loader=hub_loader,
                torch_module=torch_module,
            )
        super().__init__(
            name=name,
            model_path=self.model_name or self.legacy_model_path,
            runtime=runtime,
            event_handler=event_handler,
        )
        self.capabilities = ProviderCapabilities(score=True)
        profile = ProviderProfileSpec(
            is_local=True,
            description=(
                "Score-only JEPA adapter backed by facebookresearch/jepa-wms torch-hub models."
            ),
            package="worldforge + host-supplied torch + facebookresearch/jepa-wms",
            implementation_status="experimental",
            deterministic=True,
            requires_credentials=False,
            required_env_vars=(JEPA_MODEL_NAME_ENV_VAR,),
            supported_modalities=("observations", "goals", "actions"),
            artifact_types=("action_scores",),
            notes=(
                "Selected upstream: facebookresearch/jepa-wms via torch.hub.load(...).",
                "The public jepa adapter exposes only score; it does not expose predict, "
                "embed, generation, or reasoning.",
                f"{JEPA_MODEL_PATH_ENV_VAR} was the old scaffold reservation variable. It is "
                f"accepted only as legacy model-path metadata; set {JEPA_MODEL_NAME_ENV_VAR} "
                "to load a real upstream model such as jepa_wm_pusht.",
                "PyTorch, upstream dependencies, checkpoints, and task preprocessing remain "
                "host-owned.",
            ),
            default_model=self.model_name or self.legacy_model_path,
            supported_models=(self.model_name,) if self.model_name else (),
        )
        self.is_local = profile.is_local
        self.description = profile.description
        self.package = profile.package
        self.implementation_status = profile.implementation_status
        self.deterministic = profile.deterministic
        self.requires_credentials = profile.requires_credentials
        self.required_env_vars = list(profile.required_env_vars)
        self.supported_modalities = list(profile.supported_modalities)
        self.artifact_types = list(profile.artifact_types)
        self.notes = list(profile.notes)
        self.default_model = profile.default_model
        self.supported_models = list(profile.supported_models)

    def configured(self) -> bool:
        return self.model_name is not None

    def config_summary(self) -> ProviderConfigSummary:
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=(
                config_field_summary(
                    JEPA_MODEL_NAME_ENV_VAR,
                    required=True,
                    source=config_source(
                        JEPA_MODEL_NAME_ENV_VAR,
                        direct=self.model_name is not None
                        and env_value(JEPA_MODEL_NAME_ENV_VAR) is None,
                    ),
                    present=self.model_name is not None,
                ),
                config_field_summary(
                    JEPA_MODEL_PATH_ENV_VAR,
                    required=False,
                    source=config_source(
                        JEPA_MODEL_PATH_ENV_VAR,
                        direct=self.legacy_model_path is not None
                        and env_value(JEPA_MODEL_PATH_ENV_VAR) is None,
                    ),
                    present=self.legacy_model_path is not None,
                    detail="legacy scaffold variable; set JEPA_MODEL_NAME for runtime loading"
                    if self.legacy_model_path is not None and self.model_name is None
                    else "",
                ),
                config_field_summary(
                    JEPA_DEVICE_ENV_VAR,
                    required=False,
                    source=config_source(
                        JEPA_DEVICE_ENV_VAR,
                        direct=self.device is not None and env_value(JEPA_DEVICE_ENV_VAR) is None,
                    ),
                    present=self.device is not None,
                ),
            ),
        )

    def health(self):
        if self.model_name is None:
            started = perf_counter()
            detail = f"missing {JEPA_MODEL_NAME_ENV_VAR}"
            if self.legacy_model_path is not None:
                detail += f"; {JEPA_MODEL_PATH_ENV_VAR} is legacy scaffold metadata only"
            return self._health(started, detail, healthy=False)
        return super().health()

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        result = super().score_actions(info=info, action_candidates=action_candidates)
        result.metadata.setdefault("runtime", "torchhub")
        if self.model_name is not None:
            result.metadata.setdefault("model_name", self.model_name)
        result.metadata.setdefault("hub_repo", self.hub_repo)
        if self.device is not None:
            result.metadata.setdefault("device", self.device)
        return result


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
