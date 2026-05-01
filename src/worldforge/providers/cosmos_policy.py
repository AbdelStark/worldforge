"""NVIDIA Cosmos-Policy server provider."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from time import perf_counter

import httpx

from worldforge.models import (
    Action,
    ActionPolicyResult,
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    ProviderRequestPolicy,
    WorldForgeError,
    _redact_observable_text,
    require_finite_number,
    require_positive_int,
)

from ._config import (
    ProviderConfigSummary,
    config_source,
    env_value,
    optional_bool,
    optional_non_empty,
)
from ._policy import json_object, normalize_policy_action_candidates
from .base import ProviderError, ProviderProfileSpec, RemoteProvider, _field_summary
from .http_utils import request_json_with_policy, validate_remote_base_url

COSMOS_POLICY_BASE_URL_ENV_VAR = "COSMOS_POLICY_BASE_URL"
COSMOS_POLICY_API_TOKEN_ENV_VAR = "COSMOS_POLICY_API_TOKEN"
COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR = "COSMOS_POLICY_TIMEOUT_SECONDS"
COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR = "COSMOS_POLICY_EMBODIMENT_TAG"
COSMOS_POLICY_MODEL_ENV_VAR = "COSMOS_POLICY_MODEL"
COSMOS_POLICY_RETURN_ALL_ENV_VAR = "COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS"
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR = "COSMOS_POLICY_ALLOW_LOCAL_BASE_URL"
DEFAULT_COSMOS_POLICY_TIMEOUT_SECONDS = 600.0
DEFAULT_COSMOS_POLICY_ACTION_DIM = 14
DEFAULT_COSMOS_POLICY_EMBODIMENT_TAG = "aloha"
DEFAULT_COSMOS_POLICY_MODEL = "nvidia/Cosmos-Policy-ALOHA-Predict2-2B"

ActionTranslator = Callable[
    [object, JSONDict, JSONDict],
    Sequence[Action] | Sequence[Sequence[Action]],
]

_OBSERVATION_FIELDS = (
    "primary_image",
    "left_wrist_image",
    "right_wrist_image",
    "proprio",
)


@dataclass(slots=True, frozen=True)
class CosmosPolicyResponse:
    """Validated policy response from a Cosmos-Policy `/act` server."""

    actions: list[list[float]]
    value_prediction: float | None = None
    all_actions: list[list[list[float]]] = field(default_factory=list)
    all_value_predictions: list[float] = field(default_factory=list)
    future_prediction_summary: JSONDict = field(default_factory=dict)
    provider_info: JSONDict = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: JSONDict,
        *,
        provider_name: str,
        expected_action_dim: int | None,
    ) -> CosmosPolicyResponse:
        actions = _normalize_action_matrix(
            payload.get("actions"),
            name=f"Provider '{provider_name}' policy response field 'actions'",
            expected_action_dim=expected_action_dim,
        )
        all_actions = _normalize_all_actions(
            payload.get("all_actions"),
            provider_name=provider_name,
            expected_action_dim=expected_action_dim,
        )
        value_prediction = _optional_float(
            payload.get("value_prediction"),
            name=f"Provider '{provider_name}' policy response field 'value_prediction'",
        )
        all_value_predictions = _optional_float_list(
            payload.get("all_value_predictions"),
            name=f"Provider '{provider_name}' policy response field 'all_value_predictions'",
        )
        future_prediction_summary = _future_prediction_summary(payload)
        provider_info = {
            "value_prediction": value_prediction,
            "all_value_predictions": all_value_predictions,
            "future_prediction_summary": future_prediction_summary,
        }
        if "all_actions_by_depth" in payload:
            provider_info["all_actions_by_depth_shape"] = _bounded_shape(
                payload["all_actions_by_depth"]
            )
        if "all_value_predictions_by_depth" in payload:
            provider_info["all_value_predictions_by_depth"] = _optional_nested_float_lists(
                payload["all_value_predictions_by_depth"],
                name=(
                    f"Provider '{provider_name}' policy response field "
                    "'all_value_predictions_by_depth'"
                ),
            )
        return cls(
            actions=actions,
            value_prediction=value_prediction,
            all_actions=all_actions,
            all_value_predictions=all_value_predictions,
            future_prediction_summary=future_prediction_summary,
            provider_info=json_object(provider_info, name="Cosmos-Policy provider_info"),
        )


class CosmosPolicyProvider(RemoteProvider):
    """HTTP adapter for NVIDIA Cosmos-Policy ALOHA policy servers.

    Cosmos-Policy is modeled as an embodied policy server. WorldForge sends an
    ALOHA-shaped observation and task description to `/act`, preserves validated
    raw action chunks, and requires a host-supplied action translator before
    returning executable WorldForge actions.
    """

    env_var = COSMOS_POLICY_BASE_URL_ENV_VAR

    def __init__(
        self,
        name: str = "cosmos-policy",
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float | str | None = None,
        embodiment_tag: str | None = None,
        model: str | None = None,
        expected_action_dim: int | None = DEFAULT_COSMOS_POLICY_ACTION_DIM,
        return_all_query_results: bool | str | None = None,
        allow_local_base_url: bool | str | None = None,
        action_translator: ActionTranslator | None = None,
        request_policy: ProviderRequestPolicy | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if action_translator is not None and not callable(action_translator):
            raise WorldForgeError("Cosmos-Policy action_translator must be callable.")
        if expected_action_dim is not None:
            expected_action_dim = require_positive_int(
                expected_action_dim,
                name="Cosmos-Policy expected_action_dim",
            )
        self._base_url_direct = base_url is not None
        self._base_url = optional_non_empty(
            base_url if base_url is not None else env_value(COSMOS_POLICY_BASE_URL_ENV_VAR),
            name="Cosmos-Policy base_url",
        )
        self._api_token_direct = api_token is not None
        self.api_token = optional_non_empty(
            api_token if api_token is not None else env_value(COSMOS_POLICY_API_TOKEN_ENV_VAR),
            name="Cosmos-Policy api_token",
        )
        self._timeout_direct = timeout_seconds is not None
        self.timeout_seconds = _optional_positive_float(
            timeout_seconds
            if timeout_seconds is not None
            else env_value(COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR),
            name="Cosmos-Policy timeout_seconds",
        )
        if self.timeout_seconds is None:
            self.timeout_seconds = DEFAULT_COSMOS_POLICY_TIMEOUT_SECONDS
        self._embodiment_direct = embodiment_tag is not None
        self.embodiment_tag = optional_non_empty(
            embodiment_tag
            if embodiment_tag is not None
            else env_value(COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR)
            or DEFAULT_COSMOS_POLICY_EMBODIMENT_TAG,
            name="Cosmos-Policy embodiment_tag",
        )
        self._model_direct = model is not None
        self.model = optional_non_empty(
            model
            if model is not None
            else env_value(COSMOS_POLICY_MODEL_ENV_VAR) or DEFAULT_COSMOS_POLICY_MODEL,
            name="Cosmos-Policy model",
        )
        self.return_all_query_results = optional_bool(
            return_all_query_results
            if return_all_query_results is not None
            else env_value(COSMOS_POLICY_RETURN_ALL_ENV_VAR),
            name="Cosmos-Policy return_all_query_results",
        )
        self._allow_local_base_url_direct = allow_local_base_url is not None
        parsed_allow_local = optional_bool(
            allow_local_base_url
            if allow_local_base_url is not None
            else env_value(COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR),
            name="Cosmos-Policy allow_local_base_url",
        )
        self.allow_local_base_url = bool(parsed_allow_local)
        self.expected_action_dim = expected_action_dim
        self._action_translator = action_translator
        self._transport = transport
        self._validated_base_url: str | None = None

        resolved_request_policy = request_policy or ProviderRequestPolicy.remote_defaults(
            request_timeout_seconds=self.timeout_seconds
        )
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
                    "NVIDIA Cosmos-Policy server adapter for selecting embodied ALOHA "
                    "action chunks."
                ),
                package="worldforge + host-supplied Cosmos-Policy server",
                implementation_status="beta",
                requires_credentials=False,
                required_env_vars=(COSMOS_POLICY_BASE_URL_ENV_VAR,),
                supported_modalities=("images", "state", "language", "actions"),
                artifact_types=("action_policy",),
                notes=(
                    "Targets the Cosmos-Policy ALOHA `/act` server contract.",
                    "Does not import cosmos_policy, torch, CUDA, Docker, or robot runtime "
                    "dependencies.",
                    "Requires a host-supplied action_translator to map raw 14D bimanual "
                    "actions to WorldForge Action objects.",
                    "Blocks localhost, private, and link-local base URLs unless "
                    f"{COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR}=1 is explicitly set.",
                    "Cosmos-Policy is an embodied policy/planning runtime, not the existing "
                    "Cosmos media-generation NIM adapter.",
                ),
                default_model=self.model,
                supported_models=(self.model,) if self.model else (),
            ),
            request_policy=resolved_request_policy,
            event_handler=event_handler,
        )

    def configured(self) -> bool:
        return self._resolved_base_url() is not None

    def config_summary(self) -> ProviderConfigSummary:
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=(
                _field_summary(
                    COSMOS_POLICY_BASE_URL_ENV_VAR,
                    required=True,
                    source=config_source(
                        COSMOS_POLICY_BASE_URL_ENV_VAR,
                        direct=self._base_url_direct,
                    ),
                    present=self._resolved_base_url() is not None,
                ),
                _field_summary(
                    COSMOS_POLICY_API_TOKEN_ENV_VAR,
                    required=False,
                    secret=True,
                    source=config_source(
                        COSMOS_POLICY_API_TOKEN_ENV_VAR,
                        direct=self._api_token_direct,
                    ),
                    present=self.api_token is not None,
                ),
                _field_summary(
                    COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR,
                    required=False,
                    source=config_source(
                        COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR,
                        direct=self._timeout_direct,
                        default=not self._timeout_direct
                        and env_value(COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR) is None,
                    ),
                    present=self._timeout_direct
                    or env_value(COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR) is not None,
                ),
                _field_summary(
                    COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR,
                    required=False,
                    source=config_source(
                        COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR,
                        direct=self._embodiment_direct,
                        default=not self._embodiment_direct
                        and env_value(COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR) is None,
                    ),
                    present=self.embodiment_tag is not None,
                ),
                _field_summary(
                    COSMOS_POLICY_MODEL_ENV_VAR,
                    required=False,
                    source=config_source(
                        COSMOS_POLICY_MODEL_ENV_VAR,
                        direct=self._model_direct,
                        default=not self._model_direct
                        and env_value(COSMOS_POLICY_MODEL_ENV_VAR) is None,
                    ),
                    present=self.model is not None,
                ),
                _field_summary(
                    COSMOS_POLICY_RETURN_ALL_ENV_VAR,
                    required=False,
                    source=config_source(COSMOS_POLICY_RETURN_ALL_ENV_VAR),
                    present=self.return_all_query_results is not None,
                ),
                _field_summary(
                    COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR,
                    required=False,
                    source=config_source(
                        COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR,
                        direct=self._allow_local_base_url_direct,
                        default=not self._allow_local_base_url_direct
                        and env_value(COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR) is None,
                    ),
                    present=self._allow_local_base_url_direct
                    or env_value(COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR) is not None,
                ),
            ),
        )

    def _resolved_base_url(self) -> str | None:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _client(self) -> httpx.Client:
        base_url = self._resolved_base_url()
        if not base_url:
            raise ProviderError(
                f"Provider '{self.name}' is unavailable: missing {COSMOS_POLICY_BASE_URL_ENV_VAR}."
            )
        if self._validated_base_url is None:
            self._validated_base_url = validate_remote_base_url(
                base_url,
                provider_name=self.name,
                env_var=COSMOS_POLICY_BASE_URL_ENV_VAR,
                allow_local_network=self.allow_local_base_url,
            )
        return httpx.Client(
            base_url=self._validated_base_url,
            headers=self._headers(),
            transport=self._transport,
        )

    def health(self) -> ProviderHealth:
        started = perf_counter()
        if not self.configured():
            return self._health(
                started,
                f"missing {COSMOS_POLICY_BASE_URL_ENV_VAR}",
                healthy=False,
            )
        return self._health(
            started,
            "configured for Cosmos-Policy /act; upstream exposes no non-mutating health endpoint",
            healthy=True,
        )

    def _validate_info(self, info: JSONDict) -> tuple[JSONDict, str, int | None]:
        normalized_info = json_object(info, name="Cosmos-Policy policy info")
        observation = normalized_info.get("observation")
        if not isinstance(observation, dict) or not observation:
            raise ProviderError(
                "Cosmos-Policy policy info.observation must be a non-empty JSON object."
            )
        for field_name in _OBSERVATION_FIELDS:
            if field_name not in observation:
                raise ProviderError(f"Cosmos-Policy ALOHA observation must include '{field_name}'.")
        task_description = normalized_info.get("task_description") or observation.get(
            "task_description"
        )
        if not isinstance(task_description, str) or not task_description.strip():
            raise ProviderError(
                "Cosmos-Policy policy info must include a non-empty task_description."
            )
        options = normalized_info.get("options")
        if options is not None and not isinstance(options, dict):
            raise ProviderError("Cosmos-Policy policy info.options must be a JSON object.")
        payload: JSONDict = dict(observation)
        payload["task_description"] = task_description.strip()
        if options:
            for key, value in options.items():
                if key in payload and payload[key] != value:
                    raise ProviderError(
                        f"Cosmos-Policy option '{key}' conflicts with the observation payload."
                    )
                payload[key] = value
        if "return_all_query_results" in normalized_info:
            return_all = normalized_info["return_all_query_results"]
            if not isinstance(return_all, bool):
                raise ProviderError("Cosmos-Policy return_all_query_results must be a boolean.")
            payload["return_all_query_results"] = return_all
        elif self.return_all_query_results is not None:
            payload["return_all_query_results"] = self.return_all_query_results

        action_horizon_value = normalized_info.get("action_horizon")
        if action_horizon_value is None:
            action_horizon = None
        elif isinstance(action_horizon_value, bool) or not isinstance(action_horizon_value, int):
            raise ProviderError(
                "Cosmos-Policy info.action_horizon must be an integer greater than 0."
            )
        else:
            action_horizon = require_positive_int(
                action_horizon_value,
                name="Cosmos-Policy action_horizon",
            )
        return payload, task_description.strip(), action_horizon

    def _translate_actions(
        self,
        *,
        raw_actions: object,
        info: JSONDict,
        provider_info: JSONDict,
    ) -> list[list[Action]]:
        if self._action_translator is None:
            raise ProviderError(
                "Cosmos-Policy actions are embodiment-specific; provide action_translator "
                "to map raw policy actions into WorldForge Action objects."
            )
        try:
            translated = self._action_translator(raw_actions, info, provider_info)
        except Exception as exc:
            raise ProviderError("Cosmos-Policy action translation failed.") from exc
        return normalize_policy_action_candidates(
            translated,
            provider_label="Cosmos-Policy",
        )

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        started = perf_counter()
        try:
            payload, task_description, action_horizon_override = self._validate_info(info)
            request_policy = self._require_request_policy()
            with self._client() as client:
                response_payload = request_json_with_policy(
                    client,
                    method="POST",
                    url="/act",
                    provider_name=self.name,
                    operation_name="policy",
                    policy=request_policy.request,
                    emit_event=self._emit_event,
                    json=payload,
                )
            parsed = CosmosPolicyResponse.from_payload(
                response_payload,
                provider_name=self.name,
                expected_action_dim=self.expected_action_dim,
            )
            raw_actions: JSONDict = {"actions": parsed.actions}
            if parsed.all_actions:
                raw_actions["all_actions"] = parsed.all_actions
            candidate_plans = self._translate_actions(
                raw_actions=raw_actions,
                info=info,
                provider_info=parsed.provider_info,
            )
            selected_index = _selected_action_index(parsed.actions, parsed.all_actions)
            if parsed.all_actions and len(candidate_plans) != len(parsed.all_actions):
                raise ProviderError(
                    "Cosmos-Policy action translator returned "
                    f"{len(candidate_plans)} candidate(s) for "
                    f"{len(parsed.all_actions)} raw candidate(s)."
                )
            if selected_index >= len(candidate_plans):
                raise ProviderError(
                    "Cosmos-Policy selected candidate index "
                    f"{selected_index} is outside the translated candidate count "
                    f"{len(candidate_plans)}."
                )
            selected_actions = candidate_plans[selected_index]
            embodiment_tag = str(info.get("embodiment_tag") or self.embodiment_tag or "").strip()
            action_horizon = action_horizon_override or len(selected_actions)
            return ActionPolicyResult(
                provider=self.name,
                actions=list(selected_actions),
                raw_actions=raw_actions,
                action_horizon=action_horizon,
                embodiment_tag=embodiment_tag or None,
                metadata={
                    "runtime": "cosmos-policy-server",
                    "server_path": "/act",
                    "model": self.model,
                    "task_description": task_description,
                    "expected_action_dim": self.expected_action_dim,
                    "selected_candidate_index": selected_index,
                    "candidate_count": len(candidate_plans),
                    "provider_info": parsed.provider_info,
                    "raw_action_summary": {
                        "actions_shape": _bounded_shape(parsed.actions),
                        "all_actions_shape": _bounded_shape(parsed.all_actions)
                        if parsed.all_actions
                        else None,
                    },
                },
                action_candidates=candidate_plans,
            )
        except ProviderError as exc:
            self._emit_event(
                ProviderEvent(
                    provider=self.name,
                    operation="policy",
                    phase="failure",
                    attempt=1,
                    max_attempts=1,
                    method="POST",
                    target="/act",
                    duration_ms=max(0.1, (perf_counter() - started) * 1000),
                    message=str(exc),
                    metadata={"stage": "worldforge-boundary"},
                )
            )
            raise
        except Exception as exc:
            error = ProviderError(
                f"Cosmos-Policy action selection failed: {_redact_observable_text(str(exc))}"
            )
            self._emit_event(
                ProviderEvent(
                    provider=self.name,
                    operation="policy",
                    phase="failure",
                    attempt=1,
                    max_attempts=1,
                    method="POST",
                    target="/act",
                    duration_ms=max(0.1, (perf_counter() - started) * 1000),
                    message=str(error),
                    metadata={"stage": "worldforge-boundary"},
                )
            )
            raise error from exc


def _optional_positive_float(value: float | int | str | None, *, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            parsed = float(value)
        except ValueError:
            raise WorldForgeError(f"{name} must be greater than 0.") from None
        value = parsed
    number = require_finite_number(value, name=name)
    if number <= 0.0:
        raise WorldForgeError(f"{name} must be greater than 0.")
    return number


def _optional_float(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    return require_finite_number(value, name=name)


def _optional_float_list(value: object, *, name: str) -> list[float]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProviderError(f"{name} must be a list when present.")
    return [
        require_finite_number(item, name=f"{name}[{index}]") for index, item in enumerate(value)
    ]


def _optional_nested_float_lists(value: object, *, name: str) -> list[list[float]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProviderError(f"{name} must be a list when present.")
    nested: list[list[float]] = []
    for index, item in enumerate(value):
        nested.append(_optional_float_list(item, name=f"{name}[{index}]"))
    return nested


def _normalize_action_matrix(
    value: object,
    *,
    name: str,
    expected_action_dim: int | None,
) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise ProviderError(f"{name} must be a non-empty action matrix.")
    rows: list[list[float]] = []
    width: int | None = None
    for row_index, row in enumerate(value):
        if not isinstance(row, list) or not row:
            raise ProviderError(f"{name}[{row_index}] must be a non-empty action row.")
        if width is None:
            width = len(row)
            if expected_action_dim is not None and width != expected_action_dim:
                raise ProviderError(
                    f"{name} action_dim must be {expected_action_dim}; got {width}."
                )
        elif len(row) != width:
            raise ProviderError(f"{name} must be rectangular.")
        rows.append(
            [
                require_finite_number(value, name=f"{name}[{row_index}][{column_index}]")
                for column_index, value in enumerate(row)
            ]
        )
    return rows


def _normalize_all_actions(
    value: object,
    *,
    provider_name: str,
    expected_action_dim: int | None,
) -> list[list[list[float]]]:
    if value is None:
        return []
    if not isinstance(value, list) or not value:
        raise ProviderError(
            f"Provider '{provider_name}' policy response field 'all_actions' must be a "
            "non-empty list when present."
        )
    return [
        _normalize_action_matrix(
            candidate,
            name=(
                f"Provider '{provider_name}' policy response field 'all_actions'[{candidate_index}]"
            ),
            expected_action_dim=expected_action_dim,
        )
        for candidate_index, candidate in enumerate(value)
    ]


def _selected_action_index(
    actions: list[list[float]],
    all_actions: list[list[list[float]]],
) -> int:
    for index, candidate in enumerate(all_actions):
        if candidate == actions:
            return index
    return 0


def _bounded_shape(value: object, *, depth: int = 0, max_depth: int = 8) -> list[int] | None:
    if depth >= max_depth:
        return []
    if not isinstance(value, list):
        return []
    if not value:
        return [0]
    child_shape = _bounded_shape(value[0], depth=depth + 1, max_depth=max_depth)
    return [len(value), *(child_shape or [])]


def _future_prediction_summary(payload: JSONDict) -> JSONDict:
    summary: JSONDict = {}
    for key in (
        "future_image_predictions",
        "future_image_predictions_by_depth",
        "all_future_image_predictions",
        "all_future_image_predictions_by_depth",
    ):
        if key in payload:
            summary[key] = _summarize_prediction_payload(payload[key])
    return summary


def _summarize_prediction_payload(value: object) -> JSONDict:
    if isinstance(value, dict):
        return {
            key: _summarize_prediction_payload(child)
            for key, child in value.items()
            if isinstance(key, str)
        }
    return {"shape": _bounded_shape(value)}
