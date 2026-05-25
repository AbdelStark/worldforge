"""Observable wrapper for capability protocol implementations.

Concrete capability implementations stay pure: they take typed inputs, return result dataclasses
defined in :mod:`worldforge.models`, and never emit observability events themselves. The framework
wraps each registered implementation in :class:`_ObservableCapability` at registration time, which
adds latency timing and :class:`~worldforge.models.ProviderEvent` emission with ``success`` /
``failure`` phases around every capability method call.

The wrapper is also the single place that synthesizes the legacy ``configured()``, ``health()``,
``info()``, and ``profile()`` surfaces from the impl's ``profile`` metadata, so callers like
``worldforge doctor`` see the same shape as before the refactor.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from time import perf_counter
from typing import Any

from worldforge.capabilities import CAPABILITY_FIELD_TO_NAME
from worldforge.models import (
    ActionPolicyResult,
    ActionScoreResult,
    EmbeddingResult,
    JSONDict,
    ProviderEvent,
    ProviderHealth,
    ProviderInfo,
    ProviderLifecycleResult,
    ProviderLifecycleStatus,
    ProviderProfile,
    ReasoningResult,
    VideoClip,
    WorldForgeError,
)
from worldforge.providers.base import (
    PredictionPayload,
    ProviderError,
    ProviderProfileSpec,
    _provider_lifecycle_result,
    build_provider_lifecycle_status,
)

ProviderEventHandler = Callable[[ProviderEvent], None]


# Map from RunnableModel field names to (capability_method, operation_name). The operation name is
# what shows up in :class:`ProviderEvent.operation` so dashboards/log filters keep their existing
# vocabulary.
CAPABILITY_METHOD_MAP: dict[str, tuple[str, str]] = {
    "policy": ("select_actions", "policy"),
    "cost": ("score_actions", "score"),
    "generator": ("generate", "generate"),
    "predictor": ("predict", "predict"),
    "reasoner": ("reason", "reason"),
    "embedder": ("embed", "embed"),
    "transferer": ("transfer", "transfer"),
    "planner": ("plan", "plan"),
}
_CAPABILITY_RESULT_TYPES: dict[str, type] = {
    "policy": ActionPolicyResult,
    "cost": ActionScoreResult,
    "generator": VideoClip,
    "predictor": PredictionPayload,
    "reasoner": ReasoningResult,
    "embedder": EmbeddingResult,
    "transferer": VideoClip,
    "planner": ActionPolicyResult,
}


class _ObservableCapability:
    """Wrap a capability implementation with timing, event emission, and diagnostics surfaces.

    The wrapper preserves the wrapped implementation's call signature for the single capability
    method that matches its ``kind``. All other attribute reads are delegated to the implementation
    so it remains usable as a drop-in.
    """

    def __init__(
        self,
        impl: object,
        *,
        kind: str,
        event_handler: ProviderEventHandler | None = None,
    ) -> None:
        if kind not in CAPABILITY_METHOD_MAP:
            raise WorldForgeError(
                f"Unknown capability kind '{kind}'. "
                f"Known kinds: {', '.join(sorted(CAPABILITY_METHOD_MAP))}."
            )
        method_name, operation = CAPABILITY_METHOD_MAP[kind]
        if not callable(getattr(impl, method_name, None)):
            raise WorldForgeError(
                f"Capability impl '{type(impl).__name__}' is missing required method "
                f"'{method_name}' for kind '{kind}'."
            )
        self._impl = impl
        self._kind = kind
        self._method_name = method_name
        self._operation = operation
        self._event_handler = event_handler

    @property
    def name(self) -> str:
        return self._impl.name

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def impl(self) -> object:
        return self._impl

    @property
    def event_handler(self) -> ProviderEventHandler | None:
        return self._event_handler

    @event_handler.setter
    def event_handler(self, handler: ProviderEventHandler | None) -> None:
        self._event_handler = handler

    def _profile_spec(self) -> ProviderProfileSpec:
        spec = getattr(self._impl, "profile", None)
        if isinstance(spec, ProviderProfileSpec):
            return spec
        return ProviderProfileSpec()

    def _capabilities_dict(self) -> JSONDict:
        # The wrapped impl satisfies exactly one capability protocol. Synthesize a flag dict that
        # mirrors the legacy ``ProviderCapabilities`` shape so doctor / list_providers callers
        # render correctly during migration.
        from worldforge.models import CAPABILITY_NAMES

        capability_name = CAPABILITY_FIELD_TO_NAME[self._kind]
        return {flag: (flag == capability_name) for flag in CAPABILITY_NAMES}

    def required_env_vars(self) -> list[str]:
        spec = self._profile_spec()
        return list(spec.required_env_vars)

    def configured(self) -> bool:
        env_vars = self.required_env_vars()
        if not env_vars:
            return True
        return all(bool(os.environ.get(var)) for var in env_vars)

    def health(self) -> ProviderHealth:
        started = perf_counter()
        healthy = self.configured()
        if healthy:
            details = "configured"
        else:
            missing = [var for var in self.required_env_vars() if not os.environ.get(var)]
            details = f"missing {', '.join(missing)}"
        return ProviderHealth(
            name=self.name,
            healthy=healthy,
            latency_ms=max(0.1, (perf_counter() - started) * 1000),
            details=details,
        )

    def _missing_lifecycle_configuration(self) -> str:
        missing = [var for var in self.required_env_vars() if not os.environ.get(var)]
        return "missing " + ", ".join(missing) if missing else "provider is not configured"

    def preflight(self) -> ProviderLifecycleResult:
        hook = getattr(self._impl, "preflight", None)
        if callable(hook):
            return hook()
        started = perf_counter()
        if not self.configured():
            reason = self._missing_lifecycle_configuration()
            return _provider_lifecycle_result(
                provider=self.name,
                hook="preflight",
                status="skipped",
                started=started,
                ready=False,
                details=reason,
                skip_reason=reason,
                evidence={"configured": False},
            )
        return _provider_lifecycle_result(
            provider=self.name,
            hook="preflight",
            status="no-op",
            started=started,
            details="no provider preflight hook declared",
            evidence={"configured": True},
        )

    def warmup(self) -> ProviderLifecycleResult:
        hook = getattr(self._impl, "warmup", None)
        if callable(hook):
            return hook()
        started = perf_counter()
        if not self.configured():
            reason = self._missing_lifecycle_configuration()
            return _provider_lifecycle_result(
                provider=self.name,
                hook="warmup",
                status="skipped",
                started=started,
                ready=False,
                details=reason,
                skip_reason=reason,
                evidence={"configured": False},
            )
        return _provider_lifecycle_result(
            provider=self.name,
            hook="warmup",
            status="no-op",
            started=started,
            details="no provider warmup hook declared",
        )

    def teardown(self) -> ProviderLifecycleResult:
        hook = getattr(self._impl, "teardown", None)
        if callable(hook):
            return hook()
        return _provider_lifecycle_result(
            provider=self.name,
            hook="teardown",
            status="no-op",
            details="no provider teardown hook declared",
        )

    def lifecycle_status(
        self,
        *,
        run_warmup: bool = False,
        run_teardown: bool = False,
    ) -> ProviderLifecycleStatus:
        return build_provider_lifecycle_status(
            provider=self.name,
            preflight=self.preflight,
            warmup=self.warmup if run_warmup else None,
            teardown=self.teardown if run_teardown else None,
        )

    def info(self) -> ProviderInfo:
        from worldforge.models import ProviderCapabilities

        spec = self._profile_spec()
        return ProviderInfo(
            name=self.name,
            capabilities=ProviderCapabilities(**self._capabilities_dict()),
            is_local=spec.is_local,
            description=spec.description,
        )

    def profile(self) -> ProviderProfile:
        from worldforge.models import ProviderCapabilities

        spec = self._profile_spec()
        env_vars = list(spec.required_env_vars)
        credential_env_var = env_vars[0] if env_vars else None
        requires_credentials = (
            spec.requires_credentials if spec.requires_credentials is not None else bool(env_vars)
        )
        return ProviderProfile(
            name=self.name,
            capabilities=ProviderCapabilities(**self._capabilities_dict()),
            is_local=spec.is_local,
            description=spec.description,
            package=spec.package,
            implementation_status=spec.implementation_status,
            deterministic=spec.deterministic,
            requires_credentials=requires_credentials,
            credential_env_var=credential_env_var,
            required_env_vars=env_vars,
            supported_modalities=list(spec.supported_modalities),
            artifact_types=list(spec.artifact_types),
            notes=list(spec.notes),
            default_model=spec.default_model,
            supported_models=list(spec.supported_models),
            request_policy=getattr(self._impl, "request_policy", None),
        )

    def _emit(
        self,
        *,
        phase: str,
        duration_ms: float,
        message: str = "",
        metadata: JSONDict | None = None,
    ) -> None:
        if self._event_handler is None:
            return
        event = ProviderEvent(
            provider=self.name,
            operation=self._operation,
            phase=phase,
            duration_ms=duration_ms,
            message=message,
            metadata=dict(metadata or {}),
        )
        self._event_handler(event)

    def _validate_result_contract(self, result: object) -> None:
        expected_type = _CAPABILITY_RESULT_TYPES[self._kind]
        if not isinstance(result, expected_type):
            raise ProviderError(
                f"Provider '{self.name}' {self._operation} returned "
                f"{type(result).__name__}; expected {expected_type.__name__}."
            )

    def call(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke the wrapped capability method, emitting timing and lifecycle events."""

        method = getattr(self._impl, self._method_name)
        started = perf_counter()
        try:
            result = method(*args, **kwargs)
        except ProviderError as exc:
            duration_ms = max(0.1, (perf_counter() - started) * 1000)
            self._emit(phase="failure", duration_ms=duration_ms, message=str(exc))
            raise
        except Exception as exc:
            duration_ms = max(0.1, (perf_counter() - started) * 1000)
            wrapped = ProviderError(f"Provider '{self.name}' {self._operation} failed: {exc}")
            self._emit(phase="failure", duration_ms=duration_ms, message=str(wrapped))
            raise wrapped from exc
        try:
            self._validate_result_contract(result)
        except ProviderError as exc:
            duration_ms = max(0.1, (perf_counter() - started) * 1000)
            self._emit(phase="failure", duration_ms=duration_ms, message=str(exc))
            raise
        duration_ms = max(0.1, (perf_counter() - started) * 1000)
        self._emit(phase="success", duration_ms=duration_ms)
        return result


__all__ = ["CAPABILITY_METHOD_MAP", "_ObservableCapability"]
