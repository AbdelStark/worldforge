"""Hugging Face LeRobot policy provider adapter.

LeRobot ships pretrained robot policies (``ACT``, ``Diffusion``, ``TDMPC``, ``VQBet``,
``Pi0``, ``SmolVLA``, ...) that subclass :class:`lerobot.policies.pretrained.PreTrainedPolicy`.
Every policy exposes the same inference surface:

* ``policy.reset()`` resets any internal action-chunk or stepper state.
* ``policy.select_action(observation)`` returns a single-step action tensor.
* ``policy.predict_action_chunk(observation)`` (optional) returns an action chunk.

WorldForge models LeRobot as an embodied :class:`policy` provider, not a predictive world
model. Observations and optional language go in, raw robot action tensors come out, and a
host-supplied :data:`ActionTranslator` turns the embodiment-specific tensor into executable
WorldForge :class:`Action` objects. The provider never touches real hardware; it only
evaluates the policy.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from worldforge.models import (
    Action,
    ActionPolicyResult,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    WorldForgeError,
)

from ._config import (
    ProviderConfigSummary,
    config_source,
    env_value,
    first_env_value,
    optional_non_empty,
)
from ._policy import (
    json_object,
    no_grad_context,
    normalize_policy_action_candidates,
    policy_action_horizon,
    policy_info_object,
    policy_mode,
    policy_observation,
    policy_options,
    prepare_model,
)
from .base import BaseProvider, ProviderError, ProviderProfileSpec, _field_summary
from .runtime_manifest import (
    missing_optional_dependency_detail,
    missing_runtime_configuration_detail,
)

LEROBOT_POLICY_PATH_ENV_VAR = "LEROBOT_POLICY_PATH"
LEROBOT_POLICY_PATH_ENV_ALIASES = (LEROBOT_POLICY_PATH_ENV_VAR, "LEROBOT_POLICY")
LEROBOT_POLICY_TYPE_ENV_VAR = "LEROBOT_POLICY_TYPE"
LEROBOT_DEVICE_ENV_VAR = "LEROBOT_DEVICE"
LEROBOT_CACHE_DIR_ENV_VAR = "LEROBOT_CACHE_DIR"
LEROBOT_EMBODIMENT_TAG_ENV_VAR = "LEROBOT_EMBODIMENT_TAG"
LEROBOT_DEFAULT_DEVICE = "cpu"

SUPPORTED_POLICY_TYPES: tuple[str, ...] = (
    "act",
    "diffusion",
    "pi0",
    "pi0fast",
    "sac",
    "smolvla",
    "tdmpc",
    "vqbet",
)
PRETRAINED_POLICY_MODULE_CANDIDATES: tuple[str, ...] = (
    "lerobot.policies.pretrained",
    "lerobot.common.policies.pretrained",
)

PolicyLoader = Callable[[str, str | None, str | None, str | None], Any]
ActionTranslator = Callable[
    [object, JSONDict, JSONDict],
    Sequence[Action] | Sequence[Sequence[Action]],
]


@dataclass(frozen=True, slots=True)
class _LeRobotConfig:
    policy_path: str | None
    policy_type: str | None
    device: str | None
    device_direct: bool
    device_configured: bool
    cache_dir: str | None
    embodiment_tag: str | None


def _optional_policy_type(value: str | None, *, name: str) -> str | None:
    normalized = optional_non_empty(value, name=name)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if lowered not in SUPPORTED_POLICY_TYPES:
        supported = ", ".join(SUPPORTED_POLICY_TYPES)
        raise WorldForgeError(f"{name} must be one of: {supported}. Got '{normalized}'.")
    return lowered


def _import_failure_detail(module_name: str, exc: Exception) -> str:
    message = str(exc).strip()
    suffix = f": {message}" if message else ""
    return f"{module_name}: {type(exc).__name__}{suffix}"


def _import_pretrained_policy_module() -> tuple[Any | None, str | None]:
    failures: list[str] = []
    for module_name in PRETRAINED_POLICY_MODULE_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            failures.append(_import_failure_detail(module_name, exc))
            continue
        if not hasattr(module, "PreTrainedPolicy"):
            failures.append(f"{module_name}: PreTrainedPolicy is unavailable")
            continue
        return module, None
    return None, "LeRobot PreTrainedPolicy import unavailable (" + "; ".join(failures) + ")"


def _looks_like_local_checkpoint(path: str) -> bool:
    return path.startswith((".", "~")) or Path(path).is_absolute() or Path(path).exists()


def _checkpoint_missing_detail(path: str) -> str | None:
    if not _looks_like_local_checkpoint(path):
        return None
    if Path(path).expanduser().exists():
        return None
    return "LeRobot local checkpoint path does not exist."


def _json_shape(value: object) -> list[int] | None:
    if not isinstance(value, list):
        return []
    length = len(value)
    if length == 0:
        return [0]
    child_shapes = [_json_shape(child) for child in value]
    if any(shape is None for shape in child_shapes):
        return None
    first_shape = child_shapes[0]
    if any(shape != first_shape for shape in child_shapes[1:]):
        return None
    return [length, *(first_shape or [])]


def _json_preview(value: object, *, max_items: int = 3, depth: int = 0) -> object:
    if depth >= 3:
        return "..."
    if isinstance(value, list):
        preview = [
            _json_preview(child, max_items=max_items, depth=depth + 1)
            for child in value[:max_items]
        ]
        if len(value) > max_items:
            preview.append("...")
        return preview
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        preview = {
            key: _json_preview(child, max_items=max_items, depth=depth + 1) for key, child in items
        }
        if len(value) > max_items:
            preview["..."] = "..."
        return preview
    return value


def _raw_action_summary(actions: object) -> JSONDict:
    return {
        "type": type(actions).__name__,
        "shape": _json_shape(actions),
        "preview": _json_preview(actions),
    }


def _validated_policy_loader(policy_loader: PolicyLoader | None) -> PolicyLoader | None:
    if policy_loader is not None and not callable(policy_loader):
        raise WorldForgeError("LeRobot policy_loader must be callable when provided.")
    return policy_loader


def _validated_action_translator(
    action_translator: ActionTranslator | None,
) -> ActionTranslator | None:
    if action_translator is not None and not callable(action_translator):
        raise WorldForgeError("LeRobot action_translator must be callable when provided.")
    return action_translator


def _lerobot_policy_path(policy_path: str | None) -> str | None:
    return optional_non_empty(
        policy_path
        if policy_path is not None
        else first_env_value(LEROBOT_POLICY_PATH_ENV_ALIASES),
        name="LeRobot policy_path",
    )


def _lerobot_policy_type(policy_type: str | None) -> str | None:
    return _optional_policy_type(
        policy_type if policy_type is not None else env_value(LEROBOT_POLICY_TYPE_ENV_VAR),
        name="LeRobot policy_type",
    )


def _lerobot_device(device: str | None) -> tuple[str | None, bool, bool]:
    configured_device = device if device is not None else env_value(LEROBOT_DEVICE_ENV_VAR)
    return (
        optional_non_empty(
            device if device is not None else configured_device or LEROBOT_DEFAULT_DEVICE,
            name="LeRobot device",
        ),
        device is not None,
        configured_device is not None,
    )


def _lerobot_cache_dir(cache_dir: str | None) -> str | None:
    return optional_non_empty(
        cache_dir if cache_dir is not None else env_value(LEROBOT_CACHE_DIR_ENV_VAR),
        name="LeRobot cache_dir",
    )


def _lerobot_embodiment_tag(embodiment_tag: str | None) -> str | None:
    return optional_non_empty(
        embodiment_tag if embodiment_tag is not None else env_value(LEROBOT_EMBODIMENT_TAG_ENV_VAR),
        name="LeRobot embodiment_tag",
    )


def _resolve_lerobot_config(
    *,
    policy_path: str | None,
    policy_type: str | None,
    device: str | None,
    cache_dir: str | None,
    embodiment_tag: str | None,
) -> _LeRobotConfig:
    resolved_device, device_direct, device_configured = _lerobot_device(device)
    return _LeRobotConfig(
        policy_path=_lerobot_policy_path(policy_path),
        policy_type=_lerobot_policy_type(policy_type),
        device=resolved_device,
        device_direct=device_direct,
        device_configured=device_configured,
        cache_dir=_lerobot_cache_dir(cache_dir),
        embodiment_tag=_lerobot_embodiment_tag(embodiment_tag),
    )


def _lerobot_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        predict=False,
        embed=False,
        plan=False,
        score=False,
        policy=True,
    )


def _lerobot_profile(config: _LeRobotConfig) -> ProviderProfileSpec:
    supported_models = (config.policy_path,) if config.policy_path else ()
    return ProviderProfileSpec(
        is_local=True,
        description="Hugging Face LeRobot pretrained-policy adapter for embodied action selection.",
        package="worldforge + lerobot",
        implementation_status="stable",
        requires_credentials=False,
        required_env_vars=tuple(LEROBOT_POLICY_PATH_ENV_ALIASES),
        supported_modalities=("state", "images", "language", "actions"),
        artifact_types=("action_policy",),
        notes=(
            "Loads policies with lerobot.policies.PreTrainedPolicy.from_pretrained.",
            "Defaults to CPU unless LEROBOT_DEVICE or device= selects another runtime.",
            "Supports ACT, Diffusion, TDMPC, VQBet, Pi0, Pi0Fast, SAC, SmolVLA policies.",
            "Set LEROBOT_POLICY_PATH to a Hugging Face repo id or local checkpoint directory.",
            "Requires a host-supplied action_translator to map raw policy tensors to WorldForge "
            "Action objects; LeRobot policies are embodiment-specific.",
            "LeRobot is an action-policy provider, not a predictive world model.",
        ),
        default_model=config.policy_path,
        supported_models=supported_models,
    )


class LeRobotPolicyProvider(BaseProvider):
    """Adapter for Hugging Face LeRobot pretrained policies.

    LeRobot is modeled as an embodied policy: observations (and optional language instructions)
    go in, action tensors come out. The adapter keeps the LeRobot runtime optional by loading
    policies lazily through ``PreTrainedPolicy.from_pretrained`` or a host-supplied
    ``policy_loader``.
    """

    def __init__(
        self,
        name: str = "lerobot",
        *,
        policy_path: str | None = None,
        policy_type: str | None = None,
        device: str | None = None,
        cache_dir: str | None = None,
        embodiment_tag: str | None = None,
        policy: Any | None = None,
        policy_loader: PolicyLoader | None = None,
        action_translator: ActionTranslator | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        config = _resolve_lerobot_config(
            policy_path=policy_path,
            policy_type=policy_type,
            device=device,
            cache_dir=cache_dir,
            embodiment_tag=embodiment_tag,
        )
        self.policy_path = config.policy_path
        self.policy_type = config.policy_type
        self._device_direct = config.device_direct
        self._device_configured = config.device_configured
        self.device = config.device
        self.cache_dir = config.cache_dir
        self.embodiment_tag = config.embodiment_tag
        self._policy = policy
        self._loaded_policy_mode = "injected_policy" if policy is not None else None
        self._policy_loader = _validated_policy_loader(policy_loader)
        self._action_translator = _validated_action_translator(action_translator)

        super().__init__(
            name=name,
            capabilities=_lerobot_capabilities(),
            profile=_lerobot_profile(config),
            event_handler=event_handler,
        )

    def configured(self) -> bool:
        return self._policy is not None or self.policy_path is not None

    def config_summary(self) -> ProviderConfigSummary:
        policy_source = next(
            (env_name for env_name in LEROBOT_POLICY_PATH_ENV_ALIASES if env_value(env_name)),
            None,
        )
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=(
                _field_summary(
                    LEROBOT_POLICY_PATH_ENV_VAR,
                    aliases=("LEROBOT_POLICY",),
                    required=True,
                    source=f"env:{policy_source}"
                    if policy_source
                    else config_source(
                        LEROBOT_POLICY_PATH_ENV_VAR,
                        direct=self.policy_path is not None or self._policy is not None,
                    ),
                    present=self.policy_path is not None or self._policy is not None,
                ),
                _field_summary(
                    LEROBOT_POLICY_TYPE_ENV_VAR,
                    required=False,
                    source=config_source(
                        LEROBOT_POLICY_TYPE_ENV_VAR,
                        direct=self.policy_type is not None,
                    ),
                    present=self.policy_type is not None,
                ),
                _field_summary(
                    LEROBOT_DEVICE_ENV_VAR,
                    required=False,
                    source=config_source(
                        LEROBOT_DEVICE_ENV_VAR,
                        direct=self._device_direct,
                        default=not self._device_configured,
                    ),
                    present=self.device is not None,
                    detail="defaults to cpu" if self.device == LEROBOT_DEFAULT_DEVICE else "",
                ),
                _field_summary(
                    LEROBOT_CACHE_DIR_ENV_VAR,
                    required=False,
                    source=config_source(
                        LEROBOT_CACHE_DIR_ENV_VAR,
                        direct=self.cache_dir is not None,
                    ),
                    present=self.cache_dir is not None,
                ),
                _field_summary(
                    LEROBOT_EMBODIMENT_TAG_ENV_VAR,
                    required=False,
                    source=config_source(
                        LEROBOT_EMBODIMENT_TAG_ENV_VAR,
                        direct=self.embodiment_tag is not None,
                    ),
                    present=self.embodiment_tag is not None,
                ),
            ),
        )

    def health(self) -> ProviderHealth:
        started = perf_counter()
        if not self.configured():
            return self._health(
                started,
                missing_runtime_configuration_detail("lerobot") + " (or injected policy)",
                healthy=False,
            )
        if self._policy is None:
            if self.policy_path is not None:
                checkpoint_error = _checkpoint_missing_detail(self.policy_path)
                if checkpoint_error is not None:
                    return self._health(started, checkpoint_error, healthy=False)
            dependency_error = self._runtime_dependency_error()
            if dependency_error is not None:
                return self._health(started, dependency_error, healthy=False)
        detail_source = "injected policy"
        if self._policy is None:
            detail_source = self.policy_path or detail_source
        return self._health(
            started,
            f"configured for {detail_source}; loader={self._loader_mode()}; device={self.device}",
            healthy=True,
        )

    def _loader_mode(self) -> str:
        if self._loaded_policy_mode is not None:
            return self._loaded_policy_mode
        if self._policy_loader is not None:
            return "policy_loader"
        if self.policy_type is not None:
            return "typed_from_pretrained"
        return "pretrained_policy"

    def _runtime_dependency_error(self) -> str | None:
        if self._policy_loader is not None:
            return None
        try:
            importlib.import_module("lerobot")
        except ImportError:
            return missing_optional_dependency_detail("lerobot", "lerobot")
        except Exception as exc:
            return (
                "LeRobot optional dependency import failed ("
                + _import_failure_detail(
                    "lerobot",
                    exc,
                )
                + ")"
            )
        _pretrained_module, dependency_error = _import_pretrained_policy_module()
        if dependency_error is not None:
            return dependency_error
        return None

    def _load_policy(self) -> Any:
        if self._policy is not None:
            return self._policy
        if self.policy_path is None:
            raise ProviderError(
                f"Provider '{self.name}' is unavailable: set {LEROBOT_POLICY_PATH_ENV_VAR}."
            )
        loader_mode = self._loader_mode()
        try:
            if self._policy_loader is not None:
                loaded = self._policy_loader(
                    self.policy_path,
                    self.policy_type,
                    self.device,
                    self.cache_dir,
                )
            else:
                loaded = self._load_policy_from_lerobot()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Failed to load LeRobot policy '{self.policy_path}': {exc}"
            ) from exc
        loaded = prepare_model(loaded, device=self.device)
        if hasattr(loaded, "reset"):
            loaded.reset()
        self._policy = loaded
        self._loaded_policy_mode = loader_mode
        return loaded

    def _load_policy_from_lerobot(self) -> Any:
        if self.policy_path is None:
            raise ProviderError(
                f"Provider '{self.name}' is unavailable: set {LEROBOT_POLICY_PATH_ENV_VAR}."
            )
        kwargs: dict[str, Any] = {}
        if self.cache_dir is not None:
            kwargs["cache_dir"] = self.cache_dir
        if self.policy_type is not None:
            policy_class = self._import_policy_class(self.policy_type)
            return policy_class.from_pretrained(self.policy_path, **kwargs)
        pretrained_module, dependency_error = _import_pretrained_policy_module()
        if dependency_error is not None:
            raise ProviderError(dependency_error)
        if pretrained_module is None:
            raise ProviderError("LeRobot PreTrainedPolicy module was not loaded.")
        base_class = pretrained_module.PreTrainedPolicy
        return base_class.from_pretrained(self.policy_path, **kwargs)

    def _import_policy_class(self, policy_type: str) -> Any:
        class_suffix = {
            "act": ("act", "ACTPolicy"),
            "diffusion": ("diffusion", "DiffusionPolicy"),
            "pi0": ("pi0", "PI0Policy"),
            "pi0fast": ("pi0fast", "PI0FASTPolicy"),
            "sac": ("sac", "SACPolicy"),
            "smolvla": ("smolvla", "SmolVLAPolicy"),
            "tdmpc": ("tdmpc", "TDMPCPolicy"),
            "vqbet": ("vqbet", "VQBeTPolicy"),
        }[policy_type]
        submodule, class_name = class_suffix
        candidates = (
            f"lerobot.policies.{submodule}.modeling_{submodule}",
            f"lerobot.policies.{submodule}",
            f"lerobot.common.policies.{submodule}.modeling_{submodule}",
            f"lerobot.common.policies.{submodule}",
        )
        last_error: Exception | None = None
        for module_name in candidates:
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                last_error = exc
                continue
            policy_class = getattr(module, class_name, None)
            if policy_class is not None:
                return policy_class
        raise ProviderError(
            f"Could not import LeRobot policy class '{class_name}' for type "
            f"'{policy_type}': {last_error}"
        )

    def _validate_info(self, info: JSONDict) -> tuple[JSONDict, JSONDict | None, str]:
        info = policy_info_object(info, provider_label="LeRobot")
        observation = policy_observation(
            info,
            provider_label="LeRobot",
            require_non_empty=True,
            validate_keys=True,
        )
        options = policy_options(info, provider_label="LeRobot")
        mode = policy_mode(
            info,
            provider_label="LeRobot",
            default="select_action",
            choices=("select_action", "predict_chunk"),
        )
        return observation, options, mode

    def _translate_actions(
        self,
        *,
        raw_actions: object,
        info: JSONDict,
        provider_info: JSONDict,
    ) -> list[list[Action]]:
        if self._action_translator is None:
            raise ProviderError(
                "LeRobot policy actions are embodiment-specific; provide action_translator to "
                "map raw policy actions into WorldForge Action objects."
            )
        try:
            translated = self._action_translator(raw_actions, info, provider_info)
        except Exception as exc:
            raise ProviderError(f"LeRobot action translation failed: {exc}") from exc
        return normalize_policy_action_candidates(translated, provider_label="LeRobot")

    def _no_grad_context(self) -> Any:
        try:
            torch = importlib.import_module("torch")
        except ImportError:
            return no_grad_context(None)
        return no_grad_context(torch)

    def _invoke_policy(self, policy: Any, observation: JSONDict, mode: str) -> object:
        if mode == "predict_chunk":
            predictor = getattr(policy, "predict_action_chunk", None)
            if not callable(predictor):
                raise ProviderError(
                    "LeRobot policy does not implement predict_action_chunk(); use "
                    "mode='select_action' instead."
                )
            with self._no_grad_context():
                return predictor(observation)
        selector = getattr(policy, "select_action", None)
        if not callable(selector):
            raise ProviderError("LeRobot policy does not implement select_action().")
        with self._no_grad_context():
            return selector(observation)

    def reset(self) -> None:
        """Reset the underlying policy's internal action-chunk/stepper state, when available."""

        if self._policy is None:
            return
        reset = getattr(self._policy, "reset", None)
        if callable(reset):
            reset()

    def _policy_duration_ms(self, started: float) -> float:
        return max(0.1, (perf_counter() - started) * 1000)

    def _validated_action_horizon(self, info: JSONDict) -> int | None:
        return policy_action_horizon(
            info,
            provider_label="LeRobot",
            value_name="LeRobot action_horizon",
        )

    def _policy_response(self, *, observation: JSONDict, mode: str) -> object:
        policy = self._load_policy()
        try:
            return self._invoke_policy(policy, observation, mode)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"LeRobot policy inference failed: {exc}") from exc

    def _raw_action_response_parts(self, response: object) -> tuple[object, object]:
        if not isinstance(response, tuple):
            return response, {}
        if len(response) != 2:
            raise ProviderError("LeRobot policy tuple response must contain (actions, info).")
        raw_actions, raw_provider_info = response
        return raw_actions, raw_provider_info

    def _normalized_raw_actions(self, raw_actions: object) -> JSONDict:
        return json_object({"actions": raw_actions}, name="LeRobot raw_actions")

    def _translator_contract_summary(self) -> JSONDict | None:
        contract_summary = getattr(self._action_translator, "contract_summary", None)
        if not callable(contract_summary):
            return None
        return json_object(contract_summary(), name="LeRobot translator_contract")

    def _resolved_action_horizon(
        self,
        *,
        requested_action_horizon: int | None,
        candidate_plans: list[list[Action]],
    ) -> int:
        if requested_action_horizon is not None:
            return requested_action_horizon
        return len(candidate_plans[0])

    def _build_policy_result(
        self,
        *,
        info: JSONDict,
        mode: str,
        raw_actions: object,
        raw_provider_info: object,
        requested_action_horizon: int | None,
    ) -> ActionPolicyResult:
        normalized_raw_actions = self._normalized_raw_actions(raw_actions)
        normalized_provider_info = json_object(raw_provider_info, name="LeRobot provider_info")
        candidate_plans = self._translate_actions(
            raw_actions=raw_actions,
            info=info,
            provider_info=normalized_provider_info,
        )
        embodiment_tag = str(info.get("embodiment_tag") or self.embodiment_tag or "").strip()
        return ActionPolicyResult(
            provider=self.name,
            actions=list(candidate_plans[0]),
            raw_actions=normalized_raw_actions,
            action_horizon=self._resolved_action_horizon(
                requested_action_horizon=requested_action_horizon,
                candidate_plans=candidate_plans,
            ),
            embodiment_tag=embodiment_tag or None,
            metadata={
                "runtime": "lerobot",
                "loader_mode": self._loader_mode(),
                "policy_path": self.policy_path,
                "policy_type": self.policy_type,
                "device": self.device,
                "mode": mode,
                "provider_info": normalized_provider_info,
                "raw_action_summary": _raw_action_summary(normalized_raw_actions["actions"]),
                "candidate_count": len(candidate_plans),
                "translator_contract": self._translator_contract_summary(),
            },
            action_candidates=candidate_plans,
        )

    def _select_actions_result(self, *, info: JSONDict) -> tuple[ActionPolicyResult, str]:
        observation, _options, mode = self._validate_info(info)
        requested_action_horizon = self._validated_action_horizon(info)
        response = self._policy_response(observation=observation, mode=mode)
        raw_actions, raw_provider_info = self._raw_action_response_parts(response)
        return (
            self._build_policy_result(
                info=info,
                mode=mode,
                raw_actions=raw_actions,
                raw_provider_info=raw_provider_info,
                requested_action_horizon=requested_action_horizon,
            ),
            mode,
        )

    def _emit_policy_success(
        self,
        *,
        started: float,
        result: ActionPolicyResult,
        mode: str,
    ) -> None:
        self._emit_operation_event(
            "policy",
            phase="success",
            duration_ms=self._policy_duration_ms(started),
            metadata={
                "policy_path": self.policy_path,
                "policy_type": self.policy_type,
                "loader_mode": self._loader_mode(),
                "candidate_count": len(result.action_candidates),
                "action_horizon": result.action_horizon,
                "embodiment_tag": result.embodiment_tag,
                "mode": mode,
            },
        )

    def _emit_policy_failure(self, *, started: float, error: ProviderError) -> None:
        self._emit_operation_event(
            "policy",
            phase="failure",
            duration_ms=self._policy_duration_ms(started),
            message=str(error),
            metadata={"policy_path": self.policy_path, "policy_type": self.policy_type},
        )

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        started = perf_counter()
        try:
            result, mode = self._select_actions_result(info=info)
            self._emit_policy_success(started=started, result=result, mode=mode)
            return result
        except ProviderError as exc:
            self._emit_policy_failure(started=started, error=exc)
            raise
        except Exception as exc:
            error = ProviderError(f"LeRobot policy selection failed: {exc}")
            self._emit_policy_failure(started=started, error=error)
            raise error from exc
