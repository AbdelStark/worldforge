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
    require_positive_int,
)

from ._config import (
    ProviderConfigSummary,
    config_source,
    env_value,
    first_env_value,
    optional_non_empty,
)
from ._policy import json_object, no_grad_context, normalize_policy_action_candidates, prepare_model
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
        self.policy_path = optional_non_empty(
            policy_path
            if policy_path is not None
            else first_env_value(LEROBOT_POLICY_PATH_ENV_ALIASES),
            name="LeRobot policy_path",
        )
        self.policy_type = _optional_policy_type(
            policy_type if policy_type is not None else env_value(LEROBOT_POLICY_TYPE_ENV_VAR),
            name="LeRobot policy_type",
        )
        self.device = optional_non_empty(
            device if device is not None else env_value(LEROBOT_DEVICE_ENV_VAR),
            name="LeRobot device",
        )
        self.cache_dir = optional_non_empty(
            cache_dir if cache_dir is not None else env_value(LEROBOT_CACHE_DIR_ENV_VAR),
            name="LeRobot cache_dir",
        )
        self.embodiment_tag = optional_non_empty(
            embodiment_tag
            if embodiment_tag is not None
            else env_value(LEROBOT_EMBODIMENT_TAG_ENV_VAR),
            name="LeRobot embodiment_tag",
        )
        self._policy = policy
        self._policy_loader = policy_loader
        self._action_translator = action_translator

        supported_models = (self.policy_path,) if self.policy_path else ()
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(
                predict=False,
                generate=False,
                reason=False,
                embed=False,
                plan=False,
                transfer=False,
                score=False,
                policy=True,
            ),
            profile=ProviderProfileSpec(
                is_local=True,
                description=(
                    "Hugging Face LeRobot pretrained-policy adapter for embodied action selection."
                ),
                package="worldforge + lerobot",
                implementation_status="beta",
                requires_credentials=False,
                required_env_vars=tuple(LEROBOT_POLICY_PATH_ENV_ALIASES),
                supported_modalities=("state", "images", "language", "actions"),
                artifact_types=("action_policy",),
                notes=(
                    "Loads policies with lerobot.policies.PreTrainedPolicy.from_pretrained.",
                    "Supports ACT, Diffusion, TDMPC, VQBet, Pi0, Pi0Fast, SAC, SmolVLA policies.",
                    "Set LEROBOT_POLICY_PATH to a Hugging Face repo id or local checkpoint "
                    "directory.",
                    "Requires a host-supplied action_translator to map raw policy tensors to "
                    "WorldForge Action objects; LeRobot policies are embodiment-specific.",
                    "LeRobot is an action-policy provider, not a predictive world model.",
                ),
                default_model=self.policy_path,
                supported_models=supported_models,
            ),
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
                    source=config_source(LEROBOT_DEVICE_ENV_VAR, direct=self.device is not None),
                    present=self.device is not None,
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
            dependency_error = self._runtime_dependency_error()
            if dependency_error is not None:
                return self._health(started, dependency_error, healthy=False)
        detail_source = "injected policy"
        if self._policy is None:
            detail_source = self.policy_path or detail_source
        return self._health(started, f"configured for {detail_source}", healthy=True)

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
        if not isinstance(info, dict):
            raise ProviderError("LeRobot policy info must be a JSON object.")
        observation = info.get("observation")
        if not isinstance(observation, dict) or not observation:
            raise ProviderError("LeRobot policy info.observation must be a non-empty JSON object.")
        for key in observation:
            if not isinstance(key, str) or not key.strip():
                raise ProviderError("LeRobot policy observation keys must be non-empty strings.")
        options = info.get("options")
        if options is not None and not isinstance(options, dict):
            raise ProviderError("LeRobot policy info.options must be a JSON object when provided.")
        mode = info.get("mode", "select_action")
        if not isinstance(mode, str) or mode.strip() not in {"select_action", "predict_chunk"}:
            raise ProviderError(
                "LeRobot policy info.mode must be 'select_action' or 'predict_chunk'."
            )
        return dict(observation), dict(options) if isinstance(options, dict) else None, mode.strip()

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

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        started = perf_counter()
        try:
            observation, _options, mode = self._validate_info(info)
            policy = self._load_policy()
            try:
                raw = self._invoke_policy(policy, observation, mode)
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderError(f"LeRobot policy inference failed: {exc}") from exc

            if isinstance(raw, tuple):
                if len(raw) != 2:
                    raise ProviderError(
                        "LeRobot policy tuple response must contain (actions, info)."
                    )
                raw_actions, raw_provider_info = raw
            else:
                raw_actions = raw
                raw_provider_info = {}

            normalized_raw_actions = json_object(
                {"actions": raw_actions},
                name="LeRobot raw_actions",
            )
            normalized_provider_info = json_object(
                raw_provider_info,
                name="LeRobot provider_info",
            )
            candidate_plans = self._translate_actions(
                raw_actions=raw_actions,
                info=info,
                provider_info=normalized_provider_info,
            )
            translator_contract = None
            contract_summary = getattr(self._action_translator, "contract_summary", None)
            if callable(contract_summary):
                translator_contract = json_object(
                    contract_summary(),
                    name="LeRobot translator_contract",
                )
            action_horizon_value = info.get("action_horizon")
            if action_horizon_value is None:
                action_horizon = len(candidate_plans[0])
            elif isinstance(action_horizon_value, bool) or not isinstance(
                action_horizon_value, int
            ):
                raise ProviderError(
                    "LeRobot info.action_horizon must be an integer greater than 0."
                )
            else:
                action_horizon = require_positive_int(
                    action_horizon_value,
                    name="LeRobot action_horizon",
                )
            embodiment_tag = str(info.get("embodiment_tag") or self.embodiment_tag or "").strip()
            result = ActionPolicyResult(
                provider=self.name,
                actions=list(candidate_plans[0]),
                raw_actions=normalized_raw_actions,
                action_horizon=action_horizon,
                embodiment_tag=embodiment_tag or None,
                metadata={
                    "runtime": "lerobot",
                    "policy_path": self.policy_path,
                    "policy_type": self.policy_type,
                    "device": self.device,
                    "mode": mode,
                    "provider_info": normalized_provider_info,
                    "candidate_count": len(candidate_plans),
                    "translator_contract": translator_contract,
                },
                action_candidates=candidate_plans,
            )
            self._emit_operation_event(
                "policy",
                phase="success",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                metadata={
                    "policy_path": self.policy_path,
                    "policy_type": self.policy_type,
                    "candidate_count": len(result.action_candidates),
                    "action_horizon": result.action_horizon,
                    "embodiment_tag": result.embodiment_tag,
                    "mode": mode,
                },
            )
            return result
        except ProviderError as exc:
            self._emit_operation_event(
                "policy",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(exc),
                metadata={"policy_path": self.policy_path, "policy_type": self.policy_type},
            )
            raise
        except Exception as exc:
            error = ProviderError(f"LeRobot policy selection failed: {exc}")
            self._emit_operation_event(
                "policy",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(error),
                metadata={"policy_path": self.policy_path, "policy_type": self.policy_type},
            )
            raise error from exc
