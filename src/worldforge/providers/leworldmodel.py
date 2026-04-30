"""LeWorldModel provider adapter."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from time import perf_counter
from typing import Any

from worldforge.models import (
    ActionScoreResult,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    WorldForgeError,
    require_finite_number,
)

from ._config import env_value, first_env_value, optional_non_empty
from ._policy import no_grad_context, prepare_model
from ._tensor_validation import _is_sequence, _shape
from .base import BaseProvider, ProviderError, ProviderProfileSpec
from .runtime_manifest import (
    missing_optional_dependency_detail,
    missing_runtime_configuration_detail,
)

LEWORLDMODEL_OFFICIAL_REPO_URL = "https://github.com/lucas-maes/le-wm"
LEWORLDMODEL_RUNTIME_API = "stable_worldmodel.policy.AutoCostModel"
LEWORLDMODEL_POLICY_ENV_VAR = "LEWORLDMODEL_POLICY"
LEWORLDMODEL_POLICY_ENV_ALIASES = (LEWORLDMODEL_POLICY_ENV_VAR, "LEWM_POLICY")
LEWORLDMODEL_CACHE_DIR_ENV_VAR = "LEWORLDMODEL_CACHE_DIR"
LEWORLDMODEL_DEVICE_ENV_VAR = "LEWORLDMODEL_DEVICE"
REQUIRED_INFO_FIELDS = ("pixels", "goal", "action")

ModelLoader = Callable[[str, str | None], Any]


def _import_failure_detail(module_name: str, exc: Exception) -> str:
    message = str(exc).strip()
    suffix = f": {message}" if message else ""
    return f"{module_name}: {type(exc).__name__}{suffix}"


def _missing_import_detail(module_name: str, exc: ImportError) -> str:
    missing = exc.name or module_name
    if missing == module_name:
        return f"missing optional dependency {module_name}"
    return (
        f"{module_name} import failed because optional dependency {missing} is missing "
        f"({_import_failure_detail(missing, exc)})"
    )


class LeWorldModelProvider(BaseProvider):
    """Adapter for LeWorldModel JEPA action-candidate cost inference.

    With a real host-owned ``stable_worldmodel`` runtime and checkpoint, this adapter
    loads ``stable_worldmodel.policy.AutoCostModel`` and runs ``get_cost(...)`` over
    checkpoint-native observation, goal, action-history, and candidate-action tensors.
    WorldForge exposes that real model call as the ``score`` capability because the
    checkpoint returns action costs; it does not generate video, predict full world
    state, or answer text queries.
    """

    def __init__(
        self,
        name: str = "leworldmodel",
        *,
        policy: str | None = None,
        cache_dir: str | None = None,
        device: str | None = None,
        model_loader: ModelLoader | None = None,
        tensor_module: Any | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        self.policy = optional_non_empty(
            policy if policy is not None else first_env_value(LEWORLDMODEL_POLICY_ENV_ALIASES),
            name="LeWorldModel policy",
        )
        self.cache_dir = optional_non_empty(
            cache_dir if cache_dir is not None else env_value(LEWORLDMODEL_CACHE_DIR_ENV_VAR),
            name="LeWorldModel cache_dir",
        )
        self.device = optional_non_empty(
            device if device is not None else env_value(LEWORLDMODEL_DEVICE_ENV_VAR),
            name="LeWorldModel device",
        )
        self._model_loader = model_loader
        self._tensor_module = tensor_module
        self._model: Any | None = None
        supported_models = (self.policy,) if self.policy else ()
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(
                predict=False,
                generate=False,
                reason=False,
                embed=False,
                plan=False,
                transfer=False,
                score=True,
            ),
            profile=ProviderProfileSpec(
                is_local=True,
                description=(
                    "LeWorldModel JEPA adapter for scoring action candidates from pixel, "
                    "action, and goal tensors."
                ),
                package="worldforge + stable_worldmodel AutoCostModel",
                implementation_status="beta",
                deterministic=True,
                requires_credentials=False,
                required_env_vars=tuple(LEWORLDMODEL_POLICY_ENV_ALIASES),
                supported_modalities=("pixels", "actions", "goals"),
                artifact_types=("action_scores",),
                notes=(
                    "LeWorldModel official code: https://github.com/lucas-maes/le-wm.",
                    "Loads LeWM object checkpoints with stable_worldmodel.policy.AutoCostModel, "
                    "the loading API documented by the official LeWorldModel repository.",
                    "Runs real AutoCostModel.get_cost(...) inference when the host supplies the "
                    "optional runtime and checkpoint.",
                    "Set LEWORLDMODEL_POLICY to the checkpoint run name relative to STABLEWM_HOME.",
                    "Input tensors or nested numeric arrays must already match the checkpoint "
                    "task.",
                    "Scores are costs: lower values are better and best_index is the argmin.",
                ),
                default_model=self.policy,
                supported_models=supported_models,
            ),
            event_handler=event_handler,
        )

    def configured(self) -> bool:
        return self.policy is not None

    def health(self) -> ProviderHealth:
        started = perf_counter()
        if not self.configured():
            return self._health(
                started,
                missing_runtime_configuration_detail("leworldmodel"),
                healthy=False,
            )
        dependency_error = self._runtime_dependency_error()
        if dependency_error is not None:
            return self._health(started, dependency_error, healthy=False)
        return self._health(
            started,
            f"configured for LeWorldModel policy {self.policy}",
            healthy=True,
        )

    def _runtime_dependency_error(self) -> str | None:
        if self._model_loader is not None and self._tensor_module is not None:
            return None
        if self._tensor_module is None:
            try:
                importlib.import_module("torch")
            except ImportError:
                return missing_optional_dependency_detail("leworldmodel", "torch")
            except Exception as exc:
                return (
                    "LeWorldModel optional dependency torch import failed ("
                    + _import_failure_detail("torch", exc)
                    + ")"
                )
        if self._model_loader is None:
            try:
                stable_worldmodel = importlib.import_module("stable_worldmodel")
            except ImportError as exc:
                return (
                    missing_optional_dependency_detail(
                        "leworldmodel",
                        "stable_worldmodel",
                    )
                    + f" ({_missing_import_detail('stable_worldmodel', exc)})"
                )
            except Exception as exc:
                return (
                    "LeWorldModel optional dependency stable_worldmodel import failed ("
                    + _import_failure_detail("stable_worldmodel", exc)
                    + ")"
                )
            policy_module = getattr(stable_worldmodel, "policy", None)
            if policy_module is None or not hasattr(policy_module, "AutoCostModel"):
                return "stable_worldmodel.policy.AutoCostModel is unavailable"
        return None

    def _torch(self) -> Any:
        if self._tensor_module is not None:
            return self._tensor_module
        try:
            return importlib.import_module("torch")
        except ImportError as exc:
            raise ProviderError(
                "Provider 'leworldmodel' requires optional dependency torch. "
                "Run the documented host-owned uv wrapper with stable-worldmodel[train]."
            ) from exc
        except Exception as exc:
            raise ProviderError(
                "Provider 'leworldmodel' optional dependency torch import failed ("
                + _import_failure_detail("torch", exc)
                + ")."
            ) from exc

    def _load_model(self) -> Any:
        if not self.configured():
            raise ProviderError(
                "Provider 'leworldmodel' is unavailable: set LEWORLDMODEL_POLICY or LEWM_POLICY."
            )
        if self._model is not None:
            return self._model

        try:
            if self._model_loader is not None:
                model = self._model_loader(self.policy or "", self.cache_dir)
            else:
                stable_worldmodel = importlib.import_module("stable_worldmodel")
                loader = stable_worldmodel.policy.AutoCostModel
                if self.cache_dir is None:
                    model = loader(self.policy)
                else:
                    model = loader(self.policy, cache_dir=self.cache_dir)
        except Exception as exc:
            raise ProviderError(
                f"Failed to load LeWorldModel policy '{self.policy}': {exc}"
            ) from exc

        model = prepare_model(model, device=self.device)
        if hasattr(model, "interpolate_pos_encoding"):
            model.interpolate_pos_encoding = True
        self._model = model
        return model

    def _is_tensor(self, torch: Any, value: object) -> bool:
        is_tensor = getattr(torch, "is_tensor", None)
        if callable(is_tensor):
            return bool(is_tensor(value))
        tensor_type = getattr(torch, "Tensor", None)
        if tensor_type is not None:
            return isinstance(value, tensor_type)
        return hasattr(value, "to") and hasattr(value, "tolist")

    def _nested_numeric_depth(self, value: object, *, name: str) -> int:
        if _is_sequence(value):
            if not value:
                raise ProviderError(f"{name} must not contain empty sequences.")
            depths = {
                self._nested_numeric_depth(item, name=f"{name}[{index}]")
                for index, item in enumerate(value)
            }
            if len(depths) != 1:
                raise ProviderError(f"{name} must be a rectangular nested numeric sequence.")
            return next(iter(depths)) + 1

        try:
            require_finite_number(value, name=name)  # type: ignore[arg-type]
        except WorldForgeError as exc:
            raise ProviderError(f"{name} must contain only finite numbers.") from exc
        return 0

    def _tensor_rank(self, value: object) -> int | None:
        rank = getattr(value, "ndim", None)
        if rank is None:
            dim = getattr(value, "dim", None)
            if callable(dim):
                rank = dim()
        if rank is None:
            return None
        try:
            return int(rank)
        except (TypeError, ValueError):
            return None

    def _as_tensor(self, torch: Any, value: object, *, name: str) -> Any:
        if self._is_tensor(torch, value):
            return value
        if not _is_sequence(value):
            raise ProviderError(f"{name} must be a tensor or nested numeric sequence.")
        self._nested_numeric_depth(value, name=name)
        as_tensor = getattr(torch, "as_tensor", None)
        if not callable(as_tensor):
            raise ProviderError("Configured tensor module does not expose as_tensor().")
        return as_tensor(value)

    def _tensorize_info(self, torch: Any, info: JSONDict) -> dict[str, Any]:
        if not isinstance(info, dict):
            raise ProviderError("LeWorldModel info must be a JSON object.")
        missing = [field for field in REQUIRED_INFO_FIELDS if field not in info]
        if missing:
            raise ProviderError(
                f"LeWorldModel info missing required input fields: {', '.join(missing)}."
            )

        tensorized: dict[str, Any] = {}
        for key, value in info.items():
            if not isinstance(key, str) or not key.strip():
                raise ProviderError("LeWorldModel info field names must be non-empty strings.")
            tensorized[key] = self._as_tensor(torch, value, name=f"LeWorldModel info.{key}")

        for key in REQUIRED_INFO_FIELDS:
            rank = self._tensor_rank(tensorized[key])
            if rank is not None and rank < 3:
                raise ProviderError(
                    f"LeWorldModel info.{key} must have at least 3 dimensions for JEPA scoring."
                )
        return tensorized

    def _tensorize_action_candidates(self, torch: Any, action_candidates: object) -> Any:
        tensor = self._as_tensor(
            torch,
            action_candidates,
            name="LeWorldModel action_candidates",
        )
        rank = self._tensor_rank(tensor)
        if rank is not None and rank != 4:
            raise ProviderError(
                "LeWorldModel action_candidates must be four-dimensional: "
                "(batch, samples, horizon, action_dim)."
            )
        return tensor

    def _candidate_sample_count(self, action_candidates: object) -> int:
        shape = _shape(action_candidates, name="LeWorldModel action_candidates")
        if len(shape) != 4:
            raise ProviderError(
                "LeWorldModel action_candidates must be four-dimensional: "
                "(batch, samples, horizon, action_dim)."
            )
        batch, samples, _horizon, _action_dim = shape
        if batch != 1:
            raise ProviderError("LeWorldModel action_candidates batch dimension must be 1.")
        if samples <= 0:
            raise ProviderError("LeWorldModel action_candidates sample dimension must be positive.")
        return samples

    def _tensor_to_scores(self, raw_scores: object) -> list[float]:
        value = raw_scores
        for method_name in ("detach", "cpu"):
            method = getattr(value, method_name, None)
            if callable(method):
                value = method()
        reshape = getattr(value, "reshape", None)
        if callable(reshape):
            value = reshape(-1)
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            value = tolist()

        scores: list[float] = []

        def visit(item: object, *, name: str) -> None:
            if _is_sequence(item):
                for index, child in enumerate(item):
                    visit(child, name=f"{name}[{index}]")
                return
            try:
                scores.append(require_finite_number(item, name=name))  # type: ignore[arg-type]
            except WorldForgeError as exc:
                raise ProviderError(f"{name} must contain only finite score values.") from exc

        visit(value, name="LeWorldModel scores")
        if not scores:
            raise ProviderError("LeWorldModel returned no action scores.")
        return scores

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        started = perf_counter()
        try:
            torch = self._torch()
            model = self._load_model()
            tensor_info = self._tensorize_info(torch, info)
            candidate_count = self._candidate_sample_count(action_candidates)
            action_tensor = self._tensorize_action_candidates(torch, action_candidates)
            with no_grad_context(torch):
                raw_scores = model.get_cost(tensor_info, action_tensor)
            scores = self._tensor_to_scores(raw_scores)
            if len(scores) != candidate_count:
                raise ProviderError(
                    f"LeWorldModel returned {len(scores)} score(s) for "
                    f"{candidate_count} candidate action sample(s)."
                )
            best_index = min(range(len(scores)), key=scores.__getitem__)
            duration_ms = max(0.1, (perf_counter() - started) * 1000)
            result = ActionScoreResult(
                provider=self.name,
                scores=scores,
                best_index=best_index,
                lower_is_better=True,
                metadata={
                    "policy": self.policy,
                    "cache_dir": self.cache_dir,
                    "device": self.device,
                    "score_type": "cost",
                    "model_family": "LeWorldModel (LeWM)",
                    "official_code": LEWORLDMODEL_OFFICIAL_REPO_URL,
                    "runtime_api": LEWORLDMODEL_RUNTIME_API,
                    "checkpoint_format": "<policy>_object.ckpt",
                    "candidate_count": candidate_count,
                },
            )
            self._emit_operation_event(
                "score",
                phase="success",
                duration_ms=duration_ms,
                metadata={
                    "policy": self.policy,
                    "candidate_count": candidate_count,
                    "best_index": best_index,
                },
            )
            return result
        except ProviderError as exc:
            self._emit_operation_event(
                "score",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(exc),
                metadata={"policy": self.policy},
            )
            raise
        except Exception as exc:
            error = ProviderError(f"LeWorldModel scoring failed for policy '{self.policy}': {exc}")
            self._emit_operation_event(
                "score",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(error),
                metadata={"policy": self.policy},
            )
            raise error from exc
