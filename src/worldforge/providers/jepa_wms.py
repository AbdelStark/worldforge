"""JEPA-WMS provider candidate contract.

This module intentionally does not import ``facebookresearch/jepa-wms``. It defines the
WorldForge-side contract around a host-supplied runtime so tests can harden input validation,
runtime response parsing, score semantics, and event emission before a real upstream adapter is
added.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from time import perf_counter
from typing import Protocol

from worldforge.models import (
    ActionScoreResult,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    WorldForgeError,
    require_finite_number,
)

from .base import BaseProvider, ProviderError

JEPA_WMS_ENV_VAR = "JEPA_WMS_MODEL_PATH"
REQUIRED_INFO_FIELDS = ("observation", "goal")
OPTIONAL_NUMERIC_INFO_FIELDS = ("action_history",)


class JEPAWMSRuntime(Protocol):
    """Runtime object expected by the JEPA-WMS candidate adapter."""

    def score_actions(
        self,
        *,
        model_path: str,
        info: JSONDict,
        action_candidates: object,
    ) -> object:
        """Return a raw JEPA-WMS score response for already validated inputs."""


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _optional_non_empty(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string when provided.")
    return value.strip()


def _is_sequence(value: object) -> bool:
    return isinstance(value, list | tuple)


def _shape_from_sequence(value: object, *, name: str) -> tuple[int, ...]:
    if _is_sequence(value):
        if not value:
            raise ProviderError(f"{name} must not contain empty sequences.")
        child_shapes = [
            _shape_from_sequence(child, name=f"{name}[{index}]")
            for index, child in enumerate(value)
        ]
        first_shape = child_shapes[0]
        if any(shape != first_shape for shape in child_shapes):
            raise ProviderError(f"{name} must be a rectangular nested numeric sequence.")
        return (len(value), *first_shape)

    try:
        require_finite_number(value, name=name)  # type: ignore[arg-type]
    except WorldForgeError as exc:
        raise ProviderError(f"{name} must contain only finite numbers.") from exc
    return ()


def _shape_from_attr(value: object, *, name: str) -> tuple[int, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        rank = getattr(value, "ndim", None)
        if rank is None:
            dim = getattr(value, "dim", None)
            if callable(dim):
                rank = dim()
        if rank is None:
            return None
        try:
            rank_int = int(rank)
        except (TypeError, ValueError):
            raise ProviderError(f"{name} tensor rank must be an integer.") from None
        if rank_int <= 0:
            raise ProviderError(f"{name} tensor rank must be positive.")
        return tuple(-1 for _ in range(rank_int))

    try:
        parsed = tuple(int(dimension) for dimension in shape)
    except (TypeError, ValueError):
        raise ProviderError(f"{name} tensor shape must contain integer dimensions.") from None
    if not parsed or any(dimension == 0 for dimension in parsed):
        raise ProviderError(f"{name} tensor shape must contain non-zero dimensions.")
    return parsed


def _shape(value: object, *, name: str) -> tuple[int, ...]:
    attr_shape = _shape_from_attr(value, name=name)
    if attr_shape is not None:
        return attr_shape

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _shape(tolist(), name=name)

    if not _is_sequence(value):
        raise ProviderError(f"{name} must be a tensor-like object or nested numeric sequence.")
    return _shape_from_sequence(value, name=name)


def _require_rank(value: object, *, name: str, min_rank: int | None = None) -> tuple[int, ...]:
    shape = _shape(value, name=name)
    if min_rank is not None and len(shape) < min_rank:
        raise ProviderError(f"{name} must have at least {min_rank} dimensions.")
    return shape


def _flatten_numeric(value: object, *, name: str) -> list[float]:
    if _is_sequence(value):
        flattened: list[float] = []
        for index, child in enumerate(value):
            flattened.extend(_flatten_numeric(child, name=f"{name}[{index}]"))
        return flattened

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _flatten_numeric(tolist(), name=name)

    try:
        return [require_finite_number(value, name=name)]  # type: ignore[arg-type]
    except WorldForgeError as exc:
        raise ProviderError(f"{name} must contain only finite numbers.") from exc


class JEPAWMSProvider(BaseProvider):
    """Candidate adapter for JEPA-WMS action-candidate scoring.

    The provider is intentionally not exported from ``worldforge.providers`` and is not
    auto-registered by ``WorldForge``. Inject ``runtime=`` in tests or host experiments to exercise
    the WorldForge-side contract without importing the upstream research repository.
    """

    planned_capabilities = ("score",)
    taxonomy_category = "JEPA latent predictive world model"

    def __init__(
        self,
        name: str = "jepa-wms",
        *,
        model_path: str | None = None,
        runtime: JEPAWMSRuntime | Callable[..., object] | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        self.model_path = _optional_non_empty(
            model_path if model_path is not None else _env_value(JEPA_WMS_ENV_VAR),
            name="JEPA-WMS model_path",
        )
        self._runtime = runtime
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(predict=False, score=runtime is not None),
            is_local=True,
            description=(
                "JEPA-WMS candidate adapter for scoring action candidates through an "
                "injected runtime."
            ),
            package="worldforge + host-supplied jepa-wms runtime",
            implementation_status="scaffold",
            deterministic=True,
            requires_credentials=False,
            required_env_vars=[JEPA_WMS_ENV_VAR],
            supported_modalities=["observations", "goals", "actions"] if runtime else [],
            artifact_types=["action_scores"] if runtime else [],
            notes=[
                "Candidate contract only; not exported or auto-registered.",
                "No upstream facebookresearch/jepa-wms import is performed by WorldForge.",
                "Inject runtime= in tests or host experiments before implementing a real adapter.",
                "Runtime scores default to costs: lower values are better.",
            ],
            default_model=self.model_path,
            supported_models=[self.model_path] if self.model_path else [],
            event_handler=event_handler,
        )

    def configured(self) -> bool:
        return self.model_path is not None and self._runtime is not None

    def health(self) -> ProviderHealth:
        started = perf_counter()
        if self.model_path is None:
            return ProviderHealth(
                name=self.name,
                healthy=False,
                latency_ms=max(0.1, (perf_counter() - started) * 1000),
                details=f"missing {JEPA_WMS_ENV_VAR}",
            )
        if self._runtime is None:
            return ProviderHealth(
                name=self.name,
                healthy=False,
                latency_ms=max(0.1, (perf_counter() - started) * 1000),
                details="scaffold generated; no runtime adapter implemented",
            )
        return ProviderHealth(
            name=self.name,
            healthy=True,
            latency_ms=max(0.1, (perf_counter() - started) * 1000),
            details=f"configured for model path {self.model_path}",
        )

    def _validate_info(self, info: JSONDict) -> JSONDict:
        if not isinstance(info, dict):
            raise ProviderError("JEPA-WMS info must be a JSON object.")
        missing = [field for field in REQUIRED_INFO_FIELDS if field not in info]
        if missing:
            raise ProviderError(
                f"JEPA-WMS info missing required input fields: {', '.join(missing)}."
            )
        for key in info:
            if not isinstance(key, str) or not key.strip():
                raise ProviderError("JEPA-WMS info field names must be non-empty strings.")

        for key in REQUIRED_INFO_FIELDS:
            _require_rank(info[key], name=f"JEPA-WMS info.{key}", min_rank=2)
        for key in OPTIONAL_NUMERIC_INFO_FIELDS:
            if key in info:
                _require_rank(info[key], name=f"JEPA-WMS info.{key}", min_rank=2)
        return dict(info)

    def _validate_action_candidates(self, action_candidates: object) -> int:
        shape = _shape(action_candidates, name="JEPA-WMS action_candidates")
        if len(shape) != 4:
            raise ProviderError(
                "JEPA-WMS action_candidates must be four-dimensional: "
                "(batch, samples, horizon, action_dim)."
            )
        candidate_count = shape[1]
        if candidate_count <= 0:
            raise ProviderError("JEPA-WMS action_candidates must contain at least one sample.")
        return candidate_count

    def _call_runtime(self, *, info: JSONDict, action_candidates: object) -> object:
        if self.model_path is None:
            raise ProviderError(
                f"Provider '{self.name}' is unavailable: missing {JEPA_WMS_ENV_VAR}."
            )
        if self._runtime is None:
            raise ProviderError(
                f"Provider '{self.name}' score_actions() has no runtime adapter implemented yet."
            )

        runtime_score = getattr(self._runtime, "score_actions", None)
        if callable(runtime_score):
            return runtime_score(
                model_path=self.model_path,
                info=info,
                action_candidates=action_candidates,
            )
        if callable(self._runtime):
            return self._runtime(
                model_path=self.model_path,
                info=info,
                action_candidates=action_candidates,
            )
        raise ProviderError("JEPA-WMS runtime must be callable or expose score_actions().")

    def _parse_error_response(self, raw: JSONDict) -> None:
        error = raw.get("error")
        if error is None:
            return
        if not isinstance(error, dict):
            raise ProviderError("JEPA-WMS runtime error response must be a JSON object.")
        error_type = str(error.get("type") or "runtime_error")
        message = str(error.get("message") or "runtime returned an error")
        raise ProviderError(f"JEPA-WMS runtime returned {error_type}: {message}")

    def _parse_runtime_response(self, raw: object, *, candidate_count: int) -> ActionScoreResult:
        if isinstance(raw, ActionScoreResult):
            if raw.provider != self.name:
                raise ProviderError(
                    f"JEPA-WMS runtime result provider must be '{self.name}', got '{raw.provider}'."
                )
            if len(raw.scores) != candidate_count:
                raise ProviderError(
                    "JEPA-WMS runtime score count must match action candidate sample count."
                )
            return raw

        if not isinstance(raw, dict):
            raise ProviderError("JEPA-WMS runtime response must be a JSON object.")
        self._parse_error_response(raw)

        scores_value = raw.get("scores")
        if scores_value is None:
            raise ProviderError("JEPA-WMS runtime response missing required scores field.")
        scores = _flatten_numeric(scores_value, name="JEPA-WMS scores")
        if not scores:
            raise ProviderError("JEPA-WMS runtime returned no action scores.")
        if len(scores) != candidate_count:
            raise ProviderError(
                "JEPA-WMS runtime score count must match action candidate sample count."
            )

        lower_is_better = raw.get("lower_is_better", True)
        if not isinstance(lower_is_better, bool):
            raise ProviderError("JEPA-WMS runtime lower_is_better must be a boolean.")

        metadata = raw.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ProviderError("JEPA-WMS runtime metadata must be a JSON object.")

        best_index_value = raw.get("best_index")
        if best_index_value is None:
            selector = min if lower_is_better else max
            best_score = selector(scores)
            best_index = scores.index(best_score)
        elif (
            isinstance(best_index_value, bool)
            or not isinstance(best_index_value, int)
            or best_index_value < 0
            or best_index_value >= len(scores)
        ):
            raise ProviderError("JEPA-WMS runtime best_index is out of range.")
        else:
            best_index = best_index_value

        return ActionScoreResult(
            provider=self.name,
            scores=scores,
            best_index=best_index,
            lower_is_better=lower_is_better,
            metadata={
                "model_path": self.model_path,
                "score_type": "cost" if lower_is_better else "utility",
                "candidate_count": len(scores),
                **metadata,
            },
        )

    def _emit_score_event(
        self,
        *,
        phase: str,
        duration_ms: float,
        message: str = "",
        metadata: JSONDict | None = None,
    ) -> None:
        self._emit_event(
            ProviderEvent(
                provider=self.name,
                operation="score",
                phase=phase,
                duration_ms=duration_ms,
                message=message,
                metadata=dict(metadata or {}),
            )
        )

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        started = perf_counter()
        try:
            validated_info = self._validate_info(info)
            candidate_count = self._validate_action_candidates(action_candidates)
            raw_result = self._call_runtime(
                info=validated_info,
                action_candidates=action_candidates,
            )
            result = self._parse_runtime_response(raw_result, candidate_count=candidate_count)
            duration_ms = max(0.1, (perf_counter() - started) * 1000)
            self._emit_score_event(
                phase="success",
                duration_ms=duration_ms,
                metadata={
                    "model_path": self.model_path,
                    "candidate_count": len(result.scores),
                    "best_index": result.best_index,
                },
            )
            return result
        except ProviderError as exc:
            self._emit_score_event(
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(exc),
                metadata={"model_path": self.model_path},
            )
            raise
        except Exception as exc:
            error = ProviderError(
                f"JEPA-WMS scoring failed for model path '{self.model_path}': {exc}"
            )
            self._emit_score_event(
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(error),
                metadata={"model_path": self.model_path},
            )
            raise error from exc
