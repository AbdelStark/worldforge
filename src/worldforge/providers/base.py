"""Provider primitives for WorldForge."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    EmbeddingResult,
    GenerationOptions,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    ProviderInfo,
    ProviderProfile,
    ProviderRequestPolicy,
    ReasoningResult,
    VideoClip,
    WorldForgeError,
    require_finite_number,
    require_json_dict,
    require_positive_int,
    require_probability,
)

from ._config import (
    ConfigFieldSummary,
    ProviderConfigSummary,
    config_field_summary,
)


class ProviderError(RuntimeError):
    """Raised when a provider cannot satisfy a request."""


def validate_generation_request(
    prompt: object,
    duration_seconds: object,
    *,
    options: object | None = None,
) -> tuple[str, float, GenerationOptions | None]:
    """Validate common provider generation inputs before adapter execution."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise WorldForgeError("generate() prompt must be a non-empty string.")
    duration = require_finite_number(duration_seconds, name="generate() duration_seconds")
    if duration <= 0.0:
        raise WorldForgeError("generate() duration_seconds must be greater than 0.")
    if options is not None and not isinstance(options, GenerationOptions):
        raise WorldForgeError("generate() options must be a GenerationOptions instance.")
    return prompt.strip(), duration, options


def validate_transfer_request(
    clip: object,
    *,
    width: object,
    height: object,
    fps: object,
    prompt: object = "",
    options: object | None = None,
) -> tuple[VideoClip, int, int, float, str, GenerationOptions | None]:
    """Validate common provider transfer inputs before adapter execution."""

    if not isinstance(clip, VideoClip):
        raise WorldForgeError("transfer() clip must be a VideoClip.")
    resolved_width = require_positive_int(width, name="transfer() width")
    resolved_height = require_positive_int(height, name="transfer() height")
    resolved_fps = require_finite_number(fps, name="transfer() fps")
    if resolved_fps <= 0.0:
        raise WorldForgeError("transfer() fps must be greater than 0.")
    if not isinstance(prompt, str):
        raise WorldForgeError("transfer() prompt must be a string.")
    if options is not None and not isinstance(options, GenerationOptions):
        raise WorldForgeError("transfer() options must be a GenerationOptions instance.")
    return clip, resolved_width, resolved_height, resolved_fps, prompt.strip(), options


@dataclass(slots=True, frozen=True)
class ProviderProfileSpec:
    """Documentation and lifecycle metadata for a :class:`BaseProvider`.

    Groups the descriptive fields that used to live as a dozen optional kwargs on
    ``BaseProvider.__init__``. Every field is optional; concrete adapters declare
    only what's meaningful for their runtime.
    """

    description: str = ""
    package: str = "worldforge"
    implementation_status: str = "experimental"
    deterministic: bool = False
    is_local: bool = False
    supported_modalities: tuple[str, ...] = ()
    artifact_types: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    default_model: str | None = None
    supported_models: tuple[str, ...] = ()
    required_env_vars: tuple[str, ...] = ()
    requires_credentials: bool | None = None


@dataclass(slots=True)
class PredictionPayload:
    """Serialized prediction data returned by providers."""

    state: JSONDict
    confidence: float
    physics_score: float
    frames: list[bytes]
    metadata: JSONDict
    latency_ms: float

    def __post_init__(self) -> None:
        self.state = require_json_dict(self.state, name="PredictionPayload state")
        self.confidence = require_probability(
            self.confidence,
            name="PredictionPayload confidence",
        )
        self.physics_score = require_probability(
            self.physics_score,
            name="PredictionPayload physics_score",
        )
        if not isinstance(self.frames, list) or not all(
            isinstance(frame, bytes) for frame in self.frames
        ):
            raise WorldForgeError("PredictionPayload frames must be a list of bytes.")
        self.metadata = require_json_dict(self.metadata, name="PredictionPayload metadata")
        self.latency_ms = require_finite_number(
            self.latency_ms,
            name="PredictionPayload latency_ms",
        )
        if self.latency_ms < 0.0:
            raise WorldForgeError("PredictionPayload latency_ms must be non-negative.")
        self.frames = list(self.frames)


class BaseProvider:
    """Base class for WorldForge providers.

    Subclasses declare identity, profile metadata, and the exact capabilities they implement.
    Capability methods are intentionally fail-closed: if an adapter advertises no implementation,
    calling that surface raises ``ProviderError`` with provider context.
    """

    env_var: str | None = None

    def __init__(
        self,
        name: str,
        *,
        capabilities: ProviderCapabilities | None = None,
        profile: ProviderProfileSpec | None = None,
        request_policy: ProviderRequestPolicy | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        spec = profile or ProviderProfileSpec()
        self.name = name
        self.capabilities = capabilities or ProviderCapabilities()
        self.is_local = spec.is_local
        self.description = spec.description
        self.package = spec.package
        self.implementation_status = spec.implementation_status
        self.deterministic = spec.deterministic
        self.supported_modalities = list(spec.supported_modalities)
        self.artifact_types = list(spec.artifact_types)
        self.notes = list(spec.notes)
        self.default_model = spec.default_model
        self.supported_models = list(spec.supported_models)
        # Use the profile's required_env_vars if given, otherwise fall back to the
        # class-level single `env_var` declaration (kept for simple remote adapters).
        if spec.required_env_vars:
            self.required_env_vars = list(spec.required_env_vars)
        elif self.env_var:
            self.required_env_vars = [self.env_var]
        else:
            self.required_env_vars = []
        self.requires_credentials = (
            spec.requires_credentials
            if spec.requires_credentials is not None
            else self.env_var is not None
        )
        self.request_policy = request_policy
        self.event_handler = event_handler

    def info(self) -> ProviderInfo:
        """Return the lightweight summary used by listings and CLI output.

        :class:`ProviderInfo` carries only the fields needed to describe a provider in a list
        (name, capabilities, locality, description); for the full declaration including
        modalities, models, and request policy, use :meth:`profile`.
        """

        return ProviderInfo(
            name=self.name,
            capabilities=self.capabilities,
            is_local=self.is_local,
            description=self.description,
        )

    def profile(self) -> ProviderProfile:
        """Return the full provider declaration used by diagnostics and contract tests.

        :class:`ProviderProfile` includes the capability matrix, credential requirements,
        supported modalities and models, request policy, and free-form notes. This is the
        authoritative description of what an adapter promises and is the input to
        :func:`worldforge.testing.assert_provider_contract`.
        """

        return ProviderProfile(
            name=self.name,
            capabilities=self.capabilities,
            is_local=self.is_local,
            description=self.description,
            package=self.package,
            implementation_status=self.implementation_status,
            deterministic=self.deterministic,
            requires_credentials=self.requires_credentials,
            credential_env_var=self.env_var,
            required_env_vars=list(self.required_env_vars),
            supported_modalities=list(self.supported_modalities),
            artifact_types=list(self.artifact_types),
            notes=list(self.notes),
            default_model=self.default_model,
            supported_models=list(self.supported_models),
            request_policy=self.request_policy,
        )

    def configured(self) -> bool:
        """Return whether the provider has every credential it needs to run.

        Resolution order:

        1. If a single ``env_var`` was declared, it must be set and non-empty.
        2. Otherwise, every entry in ``required_env_vars`` must be set and non-empty.
        3. Providers with no credential requirements always report ``True``.

        Auto-registration in the catalog uses this signal: an unconfigured provider is not
        registered automatically and surfaces in ``worldforge doctor`` as ``missing``.
        """

        if self.env_var is not None:
            return bool(os.environ.get(self.env_var))
        if self.required_env_vars:
            return all(bool(os.environ.get(env_var)) for env_var in self.required_env_vars)
        return True

    def config_summary(self) -> ProviderConfigSummary:
        """Return value-free provider configuration status safe for diagnostics.

        The summary reports names, aliases, source, presence, and validation status only.
        It never includes raw environment values, endpoints, tokens, checkpoint paths, or
        constructor-provided values.
        """

        names = (self.env_var,) if self.env_var is not None else tuple(self.required_env_vars)
        fields = tuple(
            config_field_summary(
                name,
                required=True,
                secret=_looks_secret_name(name),
            )
            for name in names
        )
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=fields,
        )

    def health(self) -> ProviderHealth:
        started = perf_counter()
        healthy = self.configured()
        if healthy:
            details = "configured"
        else:
            missing = [env_var for env_var in self.required_env_vars if not os.environ.get(env_var)]
            if not missing and self.env_var is not None:
                missing = [self.env_var]
            details = f"missing {', '.join(missing)}"
        return self._health(started, details, healthy=healthy)

    def _emit_event(self, event: ProviderEvent) -> None:
        if self.event_handler is not None:
            self.event_handler(event)

    def _emit_operation_event(
        self,
        operation: str,
        *,
        phase: str,
        duration_ms: float,
        message: str = "",
        metadata: JSONDict | None = None,
    ) -> None:
        """Emit a :class:`ProviderEvent` tagged with this provider's ``name``."""

        self._emit_event(
            ProviderEvent(
                provider=self.name,
                operation=operation,
                phase=phase,
                duration_ms=duration_ms,
                message=message,
                metadata=dict(metadata or {}),
            )
        )

    def _health(
        self,
        started: float,
        details: str,
        *,
        healthy: bool,
    ) -> ProviderHealth:
        """Build a :class:`ProviderHealth` using ``started`` as the latency origin.

        The ``max(0.1, ...)`` floor keeps the serialized latency strictly positive
        for fast-returning healthchecks (validators reject ``latency_ms <= 0``).
        """

        return ProviderHealth(
            name=self.name,
            healthy=healthy,
            latency_ms=max(0.1, (perf_counter() - started) * 1000),
            details=details,
        )

    # Default capability stubs. Subclasses override the methods matching the capability flags
    # they declared in ``ProviderCapabilities``. Calling an unsupported capability must raise
    # ``ProviderError`` rather than returning empty or mock results, so callers see a fail-fast
    # boundary instead of silently degraded behavior.

    def predict(self, world_state: JSONDict, action: Action, steps: int) -> PredictionPayload:
        """Predict the world state ``steps`` ahead from ``world_state`` after applying ``action``.

        Override when the adapter's capabilities declare ``predict=True``. Implementations
        must return a :class:`PredictionPayload` with finite ``physics_score``,
        ``confidence``, and ``latency_ms``. Adapters that do not support predict must leave
        this method untouched so calls raise :class:`ProviderError`.
        """

        raise ProviderError(f"Provider '{self.name}' does not implement predict().")

    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        """Generate a video clip from ``prompt`` with the given duration.

        Override when ``generate=True``. Implementations should respect ``options.width``,
        ``options.height``, and ``options.fps`` when supplied, and raise
        :class:`ProviderError` on upstream failures, expired artifacts, or unsupported flows.
        """

        raise ProviderError(f"Provider '{self.name}' does not implement generate().")

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
        """Transfer the visual content of ``clip`` to a new style or modality.

        Override when ``transfer=True``. The output clip dimensions and fps are caller-set
        contract values; adapters that cannot honor them must raise :class:`ProviderError`
        rather than silently returning a clip with different parameters.
        """

        raise ProviderError(f"Provider '{self.name}' does not implement transfer().")

    def reason(self, query: str, *, world_state: JSONDict | None = None) -> ReasoningResult:
        """Answer a structured reasoning ``query`` over an optional ``world_state``.

        Override when ``reason=True``. Implementations should populate
        :class:`ReasoningResult` with concrete evidence; placeholder or unverifiable evidence
        is a contract violation.
        """

        raise ProviderError(f"Provider '{self.name}' does not implement reason().")

    def embed(self, *, text: str) -> EmbeddingResult:
        """Return a fixed-dimension embedding for ``text``.

        Override when ``embed=True``. The embedding dimension must be stable per provider
        configuration; callers rely on it for indexing and benchmarking.
        """

        raise ProviderError(f"Provider '{self.name}' does not implement embed().")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        """Rank a batch of candidate actions for cost/score-model providers.

        Override when ``score=True``. ``action_candidates`` is provider-shaped (typically a
        nested tensor or sequence) and must be validated by the adapter; ``info`` carries the
        observation context required to produce comparable scores across candidates.
        """

        raise ProviderError(f"Provider '{self.name}' does not implement score_actions().")

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        """Propose actions for an embodied policy provider.

        Override when ``policy=True``. ``info`` carries the observation payload required by
        the policy server; the result must include the proposed action chunk and any policy
        metadata callers need to log or replay the decision.
        """

        raise ProviderError(f"Provider '{self.name}' does not implement select_actions().")


class RemoteProvider(BaseProvider):
    """Base class for providers that depend on third-party credentials."""

    def _require_credentials(self) -> None:
        if not self.configured():
            raise ProviderError(f"Provider '{self.name}' is unavailable: missing {self.env_var}.")

    def _require_request_policy(self) -> ProviderRequestPolicy:
        if self.request_policy is None:
            raise ProviderError(f"Provider '{self.name}' does not define a request policy.")
        return self.request_policy


def _looks_secret_name(name: str) -> bool:
    return any(
        marker in name.lower()
        for marker in ("api_key", "api_secret", "secret", "token", "password", "credential")
    )


def _field_summary(
    name: str,
    *,
    aliases: tuple[str, ...] = (),
    required: bool = True,
    secret: bool = False,
    source: str | None = None,
    present: bool | None = None,
    valid: bool | None = None,
    detail: str = "",
) -> ConfigFieldSummary:
    """Internal adapter helper kept here so providers can share summary semantics."""

    return config_field_summary(
        name,
        aliases=aliases,
        required=required,
        secret=secret,
        source=source,
        present=present,
        valid=valid,
        detail=detail,
    )
