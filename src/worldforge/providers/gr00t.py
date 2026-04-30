"""NVIDIA Isaac GR00T policy-client provider."""

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
)

from ._config import (
    ProviderConfigSummary,
    config_source,
    env_value,
    optional_bool,
    optional_non_empty,
    optional_positive_int,
)
from ._policy import json_compatible, json_object, normalize_policy_action_candidates
from .base import BaseProvider, ProviderError, ProviderProfileSpec, _field_summary
from .runtime_manifest import (
    missing_optional_dependency_detail,
    missing_runtime_configuration_detail,
)

GROOT_POLICY_HOST_ENV_VAR = "GROOT_POLICY_HOST"
GROOT_POLICY_PORT_ENV_VAR = "GROOT_POLICY_PORT"
GROOT_POLICY_TIMEOUT_MS_ENV_VAR = "GROOT_POLICY_TIMEOUT_MS"
GROOT_POLICY_API_TOKEN_ENV_VAR = "GROOT_POLICY_API_TOKEN"
GROOT_POLICY_STRICT_ENV_VAR = "GROOT_POLICY_STRICT"
GROOT_EMBODIMENT_TAG_ENV_VAR = "GROOT_EMBODIMENT_TAG"
DEFAULT_GROOT_POLICY_PORT = 5555
DEFAULT_GROOT_POLICY_TIMEOUT_MS = 15_000

ActionTranslator = Callable[
    [object, JSONDict, JSONDict],
    Sequence[Action] | Sequence[Sequence[Action]],
]


class GrootPolicyClientProvider(BaseProvider):
    """Adapter for NVIDIA Isaac GR00T policy-server inference.

    GR00T is modeled as an embodied policy: observations and language go in, action chunks come
    out. It is not a future-state predictor or candidate scorer.
    """

    def __init__(
        self,
        name: str = "gr00t",
        *,
        host: str | None = None,
        port: int | str | None = None,
        timeout_ms: int | str | None = None,
        api_token: str | None = None,
        strict: bool | str | None = None,
        embodiment_tag: str | None = None,
        policy_client: Any | None = None,
        action_translator: ActionTranslator | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        self.host = optional_non_empty(
            host if host is not None else env_value(GROOT_POLICY_HOST_ENV_VAR),
            name="GR00T policy host",
        )
        self.port = (
            optional_positive_int(
                port if port is not None else env_value(GROOT_POLICY_PORT_ENV_VAR),
                name="GR00T policy port",
            )
            or DEFAULT_GROOT_POLICY_PORT
        )
        self.timeout_ms = (
            optional_positive_int(
                timeout_ms
                if timeout_ms is not None
                else env_value(GROOT_POLICY_TIMEOUT_MS_ENV_VAR),
                name="GR00T policy timeout_ms",
            )
            or DEFAULT_GROOT_POLICY_TIMEOUT_MS
        )
        self.api_token = optional_non_empty(
            api_token if api_token is not None else env_value(GROOT_POLICY_API_TOKEN_ENV_VAR),
            name="GR00T policy api_token",
        )
        parsed_strict = optional_bool(
            strict if strict is not None else env_value(GROOT_POLICY_STRICT_ENV_VAR),
            name="GR00T policy strict",
        )
        self.strict = False if parsed_strict is None else parsed_strict
        self.embodiment_tag = optional_non_empty(
            embodiment_tag
            if embodiment_tag is not None
            else env_value(GROOT_EMBODIMENT_TAG_ENV_VAR),
            name="GR00T embodiment_tag",
        )
        self._policy_client = policy_client
        self._action_translator = action_translator
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
                description=(
                    "NVIDIA Isaac GR00T policy-client adapter for selecting embodied action chunks."
                ),
                package="worldforge + host-supplied Isaac-GR00T runtime",
                implementation_status="experimental",
                requires_credentials=self.api_token is not None,
                required_env_vars=(GROOT_POLICY_HOST_ENV_VAR,),
                supported_modalities=("video", "state", "language", "actions"),
                artifact_types=("action_policy",),
                notes=(
                    "Wraps the host-owned GR00T PolicyClient server/client API.",
                    "Does not import gr00t unless a non-injected client is used.",
                    "Requires an action_translator to map embodiment-specific raw actions to "
                    "WorldForge Action objects.",
                    "GR00T is an embodied policy provider, not a future-state world model.",
                ),
                default_model=self.embodiment_tag,
                supported_models=(self.embodiment_tag,) if self.embodiment_tag else (),
            ),
            event_handler=event_handler,
        )

    def configured(self) -> bool:
        return self._policy_client is not None or self.host is not None

    def config_summary(self) -> ProviderConfigSummary:
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=(
                _field_summary(
                    GROOT_POLICY_HOST_ENV_VAR,
                    required=True,
                    source=config_source(
                        GROOT_POLICY_HOST_ENV_VAR,
                        direct=self.host is not None or self._policy_client is not None,
                    ),
                    present=self.host is not None or self._policy_client is not None,
                ),
                _field_summary(
                    GROOT_POLICY_PORT_ENV_VAR,
                    required=False,
                    source=config_source(
                        GROOT_POLICY_PORT_ENV_VAR,
                        direct=self.port != DEFAULT_GROOT_POLICY_PORT,
                        default=True,
                    ),
                    present=self.port != DEFAULT_GROOT_POLICY_PORT,
                ),
                _field_summary(
                    GROOT_POLICY_TIMEOUT_MS_ENV_VAR,
                    required=False,
                    source=config_source(
                        GROOT_POLICY_TIMEOUT_MS_ENV_VAR,
                        direct=self.timeout_ms != DEFAULT_GROOT_POLICY_TIMEOUT_MS,
                        default=True,
                    ),
                    present=self.timeout_ms != DEFAULT_GROOT_POLICY_TIMEOUT_MS,
                ),
                _field_summary(
                    GROOT_POLICY_API_TOKEN_ENV_VAR,
                    required=False,
                    secret=True,
                    source=config_source(
                        GROOT_POLICY_API_TOKEN_ENV_VAR,
                        direct=self.api_token is not None,
                    ),
                    present=self.api_token is not None,
                ),
                _field_summary(
                    GROOT_POLICY_STRICT_ENV_VAR,
                    required=False,
                    source=config_source(
                        GROOT_POLICY_STRICT_ENV_VAR,
                        direct=self.strict,
                        default=True,
                    ),
                    present=self.strict,
                ),
                _field_summary(
                    GROOT_EMBODIMENT_TAG_ENV_VAR,
                    required=False,
                    source=config_source(
                        GROOT_EMBODIMENT_TAG_ENV_VAR,
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
                missing_runtime_configuration_detail("gr00t"),
                healthy=False,
            )
        if self._policy_client is None:
            dependency_error = self._runtime_dependency_error()
            if dependency_error is not None:
                return self._health(started, dependency_error, healthy=False)
        try:
            client = self._load_client()
            ping = getattr(client, "ping", None)
            if callable(ping) and not ping():
                return self._health(started, "policy server ping failed", healthy=False)
        except ProviderError as exc:
            return self._health(started, str(exc), healthy=False)
        return self._health(
            started,
            f"configured for {self.host or 'injected policy client'}:{self.port}",
            healthy=True,
        )

    def _runtime_dependency_error(self) -> str | None:
        try:
            policy_module = importlib.import_module("gr00t.policy.server_client")
        except ImportError:
            return missing_optional_dependency_detail("gr00t", "gr00t.policy.server_client")
        except Exception as exc:
            message = str(exc).strip()
            suffix = f": {message}" if message else ""
            return (
                "GR00T optional dependency import failed "
                f"(gr00t.policy.server_client: {type(exc).__name__}{suffix})"
            )
        if not hasattr(policy_module, "PolicyClient"):
            return "gr00t.policy.server_client.PolicyClient is unavailable"
        return None

    def _load_client(self) -> Any:
        if self._policy_client is not None:
            return self._policy_client
        if self.host is None:
            raise ProviderError(
                f"Provider '{self.name}' is unavailable: missing {GROOT_POLICY_HOST_ENV_VAR}."
            )
        try:
            policy_module = importlib.import_module("gr00t.policy.server_client")
            client_type = policy_module.PolicyClient
            self._policy_client = client_type(
                host=self.host,
                port=self.port,
                timeout_ms=self.timeout_ms,
                api_token=self.api_token,
                strict=self.strict,
            )
        except Exception as exc:
            raise ProviderError(f"Failed to create GR00T PolicyClient: {exc}") from exc
        return self._policy_client

    def _validate_info(self, info: JSONDict) -> tuple[JSONDict, JSONDict | None]:
        if not isinstance(info, dict):
            raise ProviderError("GR00T policy info must be a JSON object.")
        observation = info.get("observation")
        if not isinstance(observation, dict):
            raise ProviderError("GR00T policy info.observation must be a JSON object.")
        if not any(key in observation for key in ("video", "state", "language")):
            raise ProviderError(
                "GR00T policy observation must include at least one of video, state, or language."
            )
        options = info.get("options")
        if options is not None and not isinstance(options, dict):
            raise ProviderError("GR00T policy info.options must be a JSON object when provided.")
        return dict(observation), dict(options) if isinstance(options, dict) else None

    def _translate_actions(
        self,
        *,
        raw_actions: object,
        info: JSONDict,
        provider_info: JSONDict,
    ) -> list[list[Action]]:
        if self._action_translator is None:
            raise ProviderError(
                "GR00T policy actions are embodiment-specific; provide action_translator to map "
                "raw policy actions into WorldForge Action objects."
            )
        try:
            translated = self._action_translator(raw_actions, info, provider_info)
        except Exception as exc:
            raise ProviderError(f"GR00T action translation failed: {exc}") from exc
        return normalize_policy_action_candidates(translated, provider_label="GR00T")

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        started = perf_counter()
        try:
            observation, options = self._validate_info(info)
            client = self._load_client()
            get_action = getattr(client, "get_action", None)
            if not callable(get_action):
                raise ProviderError("GR00T policy client does not expose get_action().")
            try:
                response = (
                    get_action(observation, options=options)
                    if options is not None
                    else get_action(observation)
                )
            except Exception as exc:
                raise ProviderError(f"GR00T policy inference failed: {exc}") from exc

            if isinstance(response, tuple):
                if len(response) != 2:
                    raise ProviderError(
                        "GR00T policy client tuple response must contain actions and info."
                    )
                raw_actions, raw_provider_info = response
            else:
                raw_actions = response
                raw_provider_info = {}

            raw_actions_value = json_compatible(raw_actions, name="GR00T raw_actions")
            if isinstance(raw_actions_value, dict):
                normalized_raw_actions = raw_actions_value
            elif isinstance(raw_actions_value, list):
                normalized_raw_actions = {"actions": raw_actions_value}
            else:
                raise ProviderError("GR00T raw_actions must be a JSON object or action array.")
            normalized_provider_info = json_object(
                raw_provider_info,
                name="GR00T provider_info",
            )
            candidate_plans = self._translate_actions(
                raw_actions=raw_actions,
                info=info,
                provider_info=normalized_provider_info,
            )
            action_horizon_value = info.get("action_horizon")
            action_horizon = (
                optional_positive_int(action_horizon_value, name="GR00T action_horizon")
                if action_horizon_value is not None
                else len(candidate_plans[0])
            )
            embodiment_tag = str(info.get("embodiment_tag") or self.embodiment_tag or "").strip()
            result = ActionPolicyResult(
                provider=self.name,
                actions=list(candidate_plans[0]),
                raw_actions=normalized_raw_actions,
                action_horizon=action_horizon,
                embodiment_tag=embodiment_tag or None,
                metadata={
                    "runtime": "gr00t-policy-client",
                    "provider_info": normalized_provider_info,
                    "candidate_count": len(candidate_plans),
                },
                action_candidates=candidate_plans,
            )
            self._emit_operation_event(
                "policy",
                phase="success",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                metadata={
                    "candidate_count": len(result.action_candidates),
                    "action_horizon": result.action_horizon,
                    "embodiment_tag": result.embodiment_tag,
                },
            )
            return result
        except ProviderError as exc:
            self._emit_operation_event(
                "policy",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(exc),
            )
            raise
        except Exception as exc:
            error = ProviderError(f"GR00T policy selection failed: {exc}")
            self._emit_operation_event(
                "policy",
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(error),
            )
            raise error from exc
