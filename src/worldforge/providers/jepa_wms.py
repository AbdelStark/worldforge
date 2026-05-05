"""JEPA-WMS provider candidate contract.

This module intentionally does not import ``facebookresearch/jepa-wms``. It defines the
WorldForge-side contract around a host-supplied runtime so tests can harden input validation,
runtime response parsing, score semantics, and event emission before a real upstream adapter is
added.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from time import perf_counter
from typing import Any, Protocol

from worldforge.models import (
    ActionScoreResult,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    WorldForgeError,
    require_bool,
)

from ._config import env_value, optional_non_empty
from ._policy import no_grad_context
from ._tensor_validation import (
    _flatten_numeric,
    _require_rank,
    _shape,
    _tensor_shape,
)
from .base import BaseProvider, ProviderError, ProviderProfileSpec

JEPA_WMS_ENV_VAR = "JEPA_WMS_MODEL_PATH"
JEPA_WMS_MODEL_NAME_ENV_VAR = "JEPA_WMS_MODEL_NAME"
JEPA_WMS_DEVICE_ENV_VAR = "JEPA_WMS_DEVICE"
DEFAULT_JEPA_WMS_HUB_REPO = "facebookresearch/jepa-wms"
REQUIRED_INFO_FIELDS = ("observation", "goal")
OPTIONAL_NUMERIC_INFO_FIELDS = ("action_history",)

HubLoader = Callable[..., object]


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


class TorchHubJEPAWMSRuntime:
    """Host-owned runtime shim for upstream JEPA-WMS torch-hub models.

    The shim lazily imports ``torch`` and lazily calls ``torch.hub.load``. It is deliberately not
    used by auto-registration; hosts must instantiate it explicitly or use
    ``JEPAWMSProvider.from_torch_hub(...)``.
    """

    def __init__(
        self,
        *,
        model_name: str,
        hub_repo: str = DEFAULT_JEPA_WMS_HUB_REPO,
        device: str | None = None,
        pretrained: bool = True,
        trust_repo: bool | None = None,
        hub_loader: HubLoader | None = None,
        torch_module: Any | None = None,
    ) -> None:
        self.model_name = optional_non_empty(model_name, name="JEPA-WMS model_name")
        if self.model_name is None:
            raise WorldForgeError("JEPA-WMS model_name must be provided.")
        self.hub_repo = optional_non_empty(hub_repo, name="JEPA-WMS hub_repo")
        if self.hub_repo is None:
            raise WorldForgeError("JEPA-WMS hub_repo must be provided.")
        self.device = optional_non_empty(device, name="JEPA-WMS device")
        if not isinstance(pretrained, bool):
            raise WorldForgeError("JEPA-WMS pretrained must be a boolean.")
        if trust_repo is not None and not isinstance(trust_repo, bool):
            raise WorldForgeError("JEPA-WMS trust_repo must be a boolean when provided.")
        self.pretrained = pretrained
        self.trust_repo = trust_repo
        self._hub_loader = hub_loader
        self._torch_module = torch_module
        self._model: Any | None = None
        self._preprocessor: Any | None = None

    def _torch(self) -> Any:
        if self._torch_module is not None:
            return self._torch_module
        try:
            return importlib.import_module("torch")
        except ImportError as exc:
            raise ProviderError(
                "JEPA-WMS torch-hub runtime requires optional dependency torch in the host "
                "environment."
            ) from exc

    def _load_model(self, torch: Any) -> tuple[Any, Any | None]:
        if self._model is not None:
            return self._model, self._preprocessor

        loader = self._hub_loader
        if loader is None:
            hub = getattr(torch, "hub", None)
            loader = getattr(hub, "load", None)
        if not callable(loader):
            raise ProviderError("JEPA-WMS torch module does not expose torch.hub.load().")

        kwargs: dict[str, object] = {
            "pretrained": self.pretrained,
        }
        if self.device is not None:
            kwargs["device"] = self.device
        if self.trust_repo is not None:
            kwargs["trust_repo"] = self.trust_repo

        try:
            loaded = loader(self.hub_repo, self.model_name, **kwargs)
        except (
            AttributeError,
            ImportError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise ProviderError(
                f"Failed to load JEPA-WMS torch-hub model '{self.model_name}' "
                f"from '{self.hub_repo}': {exc}"
            ) from exc

        if isinstance(loaded, tuple):
            if not loaded:
                raise ProviderError("JEPA-WMS torch-hub loader returned an empty tuple.")
            model = loaded[0]
            preprocessor = loaded[1] if len(loaded) > 1 else None
        else:
            model = loaded
            preprocessor = getattr(model, "preprocessor", None)

        if self.device is not None and hasattr(model, "to"):
            model = model.to(self.device)
        if hasattr(model, "eval"):
            model = model.eval()
        self._model = model
        self._preprocessor = preprocessor
        return model, preprocessor

    def _as_tensor(self, torch: Any, value: object, *, name: str) -> Any:
        if hasattr(value, "to") and _tensor_shape(value) is not None:
            tensor = value
        else:
            as_tensor = getattr(torch, "as_tensor", None)
            if not callable(as_tensor):
                raise ProviderError("JEPA-WMS torch module does not expose as_tensor().")
            try:
                tensor = as_tensor(value)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                raise ProviderError(f"{name} could not be converted to a tensor: {exc}") from exc
        if self.device is not None and hasattr(tensor, "to"):
            tensor = tensor.to(self.device)
        return tensor

    def _normalize_actions_if_requested(
        self,
        *,
        action_tensor: Any,
        preprocessor: Any | None,
        actions_are_normalized: bool,
    ) -> Any:
        if actions_are_normalized:
            return action_tensor
        normalize = getattr(preprocessor, "normalize_actions", None)
        if not callable(normalize):
            raise ProviderError(
                "JEPA-WMS runtime received unnormalized actions but the loaded preprocessor does "
                "not expose normalize_actions()."
            )
        try:
            return normalize(action_tensor)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            raise ProviderError(f"JEPA-WMS action normalization failed: {exc}") from exc

    def _score_via_model_method(
        self,
        *,
        model: Any,
        model_path: str,
        info: JSONDict,
        action_candidates: object,
    ) -> object | None:
        for method_name in ("score_actions", "score_action_candidates", "compute_scores"):
            method = getattr(model, method_name, None)
            if callable(method):
                return method(
                    model_path=model_path,
                    info=info,
                    action_candidates=action_candidates,
                )
        return None

    def _select_last_timestep(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._select_last_timestep(child) for key, child in value.items()}
        try:
            return value[-1]
        except (IndexError, KeyError, TypeError):
            return value

    def _distance_scores(
        self, torch: Any, predicted: Any, target: Any, *, objective: str
    ) -> list[float]:
        if isinstance(predicted, dict) and isinstance(target, dict):
            total: Any | None = None
            for key in sorted(predicted):
                if key not in target:
                    continue
                component = self._distance_scores_tensor(
                    torch,
                    predicted[key],
                    target[key],
                    objective=objective,
                )
                total = component if total is None else total + component
            if total is None:
                raise ProviderError("JEPA-WMS encoded dictionaries had no shared keys to score.")
            return _flatten_numeric(total, name="JEPA-WMS scores")
        return _flatten_numeric(
            self._distance_scores_tensor(torch, predicted, target, objective=objective),
            name="JEPA-WMS scores",
        )

    def _distance_scores_tensor(
        self, torch: Any, predicted: Any, target: Any, *, objective: str
    ) -> Any:
        if objective not in {"l1", "l2"}:
            raise ProviderError("JEPA-WMS objective must be 'l1' or 'l2'.")
        diff = predicted - target
        if objective == "l1":
            abs_fn = getattr(torch, "abs", None)
            diff = abs_fn(diff) if callable(abs_fn) else abs(diff)
        else:
            pow_method = getattr(diff, "pow", None)
            diff = pow_method(2) if callable(pow_method) else diff * diff

        ndim = getattr(diff, "ndim", None)
        if ndim is None:
            shape = _tensor_shape(diff)
            ndim = len(shape) if shape is not None else None
        if ndim is None or int(ndim) <= 1:
            return diff
        mean = getattr(diff, "mean", None)
        if not callable(mean):
            raise ProviderError("JEPA-WMS distance tensor does not expose mean().")
        return mean(dim=tuple(range(1, int(ndim))))

    def _encode(self, model: Any, value: Any, *, act: bool) -> Any:
        encode = getattr(model, "encode", None)
        if not callable(encode):
            raise ProviderError("JEPA-WMS loaded model does not expose encode().")
        try:
            return encode(value, act=act)
        except TypeError:
            return encode(value)
        except (AttributeError, RuntimeError, ValueError) as exc:
            raise ProviderError(f"JEPA-WMS model encoding failed: {exc}") from exc

    def _unroll(self, model: Any, z_init: Any, action_suffix: Any) -> Any:
        unroll = getattr(model, "unroll", None)
        if not callable(unroll):
            raise ProviderError("JEPA-WMS loaded model does not expose unroll().")
        try:
            return unroll(z_init, act_suffix=action_suffix)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            raise ProviderError(f"JEPA-WMS model unroll failed: {exc}") from exc

    def score_actions(
        self,
        *,
        model_path: str,
        info: JSONDict,
        action_candidates: object,
    ) -> object:
        torch = self._torch()
        model, preprocessor = self._load_model(torch)

        direct_result = self._score_via_model_method(
            model=model,
            model_path=model_path,
            info=info,
            action_candidates=action_candidates,
        )
        if direct_result is not None:
            return direct_result

        objective = str(info.get("objective", "l2")).lower()
        try:
            actions_are_normalized = require_bool(
                info.get("actions_are_normalized", True),
                name="JEPA-WMS actions_are_normalized",
            )
        except WorldForgeError as exc:
            raise ProviderError(str(exc)) from exc

        observation = self._as_tensor(torch, info["observation"], name="JEPA-WMS observation")
        goal = self._as_tensor(torch, info["goal"], name="JEPA-WMS goal")
        action_tensor = self._as_tensor(
            torch,
            action_candidates,
            name="JEPA-WMS action_candidates",
        )
        try:
            model_actions = action_tensor[0]
            model_actions = self._normalize_actions_if_requested(
                action_tensor=model_actions,
                preprocessor=preprocessor,
                actions_are_normalized=actions_are_normalized,
            )
            model_actions = model_actions.permute(1, 0, 2)
        except ProviderError:
            raise
        except (
            AttributeError,
            IndexError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise ProviderError(f"JEPA-WMS action tensor preparation failed: {exc}") from exc

        with no_grad_context(torch):
            z_init = self._encode(model, observation, act=True)
            target = self._encode(model, goal, act=False)
            predicted = self._unroll(model, z_init, model_actions)

        scores = self._distance_scores(
            torch,
            self._select_last_timestep(predicted),
            self._select_last_timestep(target),
            objective=objective,
        )
        return {
            "scores": scores,
            "lower_is_better": True,
            "metadata": {
                "runtime": "torchhub",
                "hub_repo": self.hub_repo,
                "model_name": self.model_name,
                "objective": objective,
                "actions_are_normalized": actions_are_normalized,
            },
        }


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
        self.model_path = optional_non_empty(
            model_path if model_path is not None else env_value(JEPA_WMS_ENV_VAR),
            name="JEPA-WMS model_path",
        )
        if (
            runtime is not None
            and not callable(runtime)
            and not callable(getattr(runtime, "score_actions", None))
        ):
            raise WorldForgeError("JEPA-WMS runtime must be callable or expose score_actions().")
        self._runtime = runtime
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(predict=False, score=runtime is not None),
            profile=ProviderProfileSpec(
                is_local=True,
                description=(
                    "JEPA-WMS candidate adapter for scoring action candidates through an "
                    "injected runtime."
                ),
                package="worldforge + host-supplied jepa-wms runtime",
                implementation_status="scaffold",
                deterministic=True,
                requires_credentials=False,
                required_env_vars=(JEPA_WMS_ENV_VAR,),
                supported_modalities=("observations", "goals", "actions") if runtime else (),
                artifact_types=("action_scores",) if runtime else (),
                notes=(
                    "Candidate contract only; not exported or auto-registered.",
                    "The optional torch-hub runtime is host-owned and lazily imported only when "
                    "used.",
                    "Inject runtime= in tests or use from_torch_hub(...) for host experiments.",
                    "Runtime scores default to costs: lower values are better.",
                ),
                default_model=self.model_path,
                supported_models=(self.model_path,) if self.model_path else (),
            ),
            event_handler=event_handler,
        )

    @classmethod
    def from_torch_hub(
        cls,
        *,
        model_name: str | None = None,
        model_path: str | None = None,
        hub_repo: str = DEFAULT_JEPA_WMS_HUB_REPO,
        device: str | None = None,
        pretrained: bool = True,
        trust_repo: bool | None = None,
        hub_loader: HubLoader | None = None,
        torch_module: Any | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> JEPAWMSProvider:
        """Create a direct JEPA-WMS provider backed by an explicit torch-hub runtime."""

        resolved_model_name = optional_non_empty(
            model_name if model_name is not None else env_value(JEPA_WMS_MODEL_NAME_ENV_VAR),
            name="JEPA-WMS model_name",
        )
        if resolved_model_name is None:
            raise WorldForgeError(
                f"JEPA-WMS torch-hub runtime requires model_name or {JEPA_WMS_MODEL_NAME_ENV_VAR}."
            )
        resolved_device = optional_non_empty(
            device if device is not None else env_value(JEPA_WMS_DEVICE_ENV_VAR),
            name="JEPA-WMS device",
        )
        runtime = TorchHubJEPAWMSRuntime(
            model_name=resolved_model_name,
            hub_repo=hub_repo,
            device=resolved_device,
            pretrained=pretrained,
            trust_repo=trust_repo,
            hub_loader=hub_loader,
            torch_module=torch_module,
        )
        return cls(
            model_path=model_path or resolved_model_name,
            runtime=runtime,
            event_handler=event_handler,
        )

    def configured(self) -> bool:
        return self.model_path is not None and self._runtime is not None

    def health(self) -> ProviderHealth:
        started = perf_counter()
        if self.model_path is None:
            return self._health(started, f"missing {JEPA_WMS_ENV_VAR}", healthy=False)
        if self._runtime is None:
            return self._health(
                started,
                "scaffold generated; no runtime adapter implemented",
                healthy=False,
            )
        return self._health(
            started,
            f"configured for model path {self.model_path}",
            healthy=True,
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
        if shape[0] != 1:
            raise ProviderError(
                "JEPA-WMS action_candidates supports exactly one batch for "
                "WorldForge score planning."
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
            self._emit_operation_event(
                "score",
                phase="success",
                duration_ms=duration_ms,
                metadata={
                    "model_configured": self.model_path is not None,
                    "candidate_count": len(result.scores),
                    "best_index": result.best_index,
                },
            )
            return result
        except ProviderError as exc:
            self._emit_operation_event(
                "score",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(exc),
                metadata={"model_configured": self.model_path is not None},
            )
            raise
        except (
            ArithmeticError,
            AttributeError,
            BufferError,
            ImportError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            error = ProviderError(f"JEPA-WMS scoring failed for configured model: {exc}")
            self._emit_operation_event(
                "score",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(error),
                metadata={"model_configured": self.model_path is not None},
            )
            raise error from exc
