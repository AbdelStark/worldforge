"""NVIDIA Cosmos-Policy server provider."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
    WorldStateError,
    _redact_observable_text,
    require_json_dict,
    require_positive_int,
)

from ._config import (
    ConfigFieldSummary,
    ProviderConfigSummary,
    config_source,
    env_value,
    optional_bool,
    optional_non_empty,
)
from ._policy import normalize_policy_action_candidates
from .base import ProviderError, ProviderProfileSpec, RemoteProvider, _field_summary
from .cosmos_policy_payload import (
    _apply_cosmos_policy_return_all,
    _cosmos_policy_action_horizon,
    _cosmos_policy_observation,
    _cosmos_policy_options,
    _cosmos_policy_payload,
    _cosmos_policy_task_description,
    _is_malformed_json_response_error,
    _optional_host_patterns,
    _optional_positive_float,
    _validate_cosmos_policy_embodiment_tag,
)
from .cosmos_policy_response import (
    CosmosPolicyResponse,
    _selected_action_index,
)
from .cosmos_policy_response import (
    _summarize_prediction_payload as _summarize_prediction_payload,
)
from .cosmos_policy_result import (
    _cosmos_policy_raw_actions,
    _cosmos_policy_result_metadata,
    _validate_translated_candidate_count,
)
from .http_utils import request_json_with_policy, validate_remote_base_url

COSMOS_POLICY_BASE_URL_ENV_VAR = "COSMOS_POLICY_BASE_URL"
COSMOS_POLICY_API_TOKEN_ENV_VAR = "COSMOS_POLICY_API_TOKEN"
COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR = "COSMOS_POLICY_TIMEOUT_SECONDS"
COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR = "COSMOS_POLICY_EMBODIMENT_TAG"
COSMOS_POLICY_MODEL_ENV_VAR = "COSMOS_POLICY_MODEL"
COSMOS_POLICY_RETURN_ALL_ENV_VAR = "COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS"
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR = "COSMOS_POLICY_ALLOW_LOCAL_BASE_URL"
COSMOS_POLICY_ALLOWED_HOSTS_ENV_VAR = "COSMOS_POLICY_ALLOWED_HOSTS"
DEFAULT_COSMOS_POLICY_TIMEOUT_SECONDS = 600.0
DEFAULT_COSMOS_POLICY_ACTION_DIM = 14
DEFAULT_COSMOS_POLICY_EMBODIMENT_TAG = "aloha"
DEFAULT_COSMOS_POLICY_MODEL = "nvidia/Cosmos-Policy-ALOHA-Predict2-2B"

ActionTranslator = Callable[
    [object, JSONDict, JSONDict],
    Sequence[Action] | Sequence[Sequence[Action]],
]

_TRANSLATOR_REQUIRED_MESSAGE = (
    "Cosmos-Policy actions are embodiment-specific; provide action_translator "
    "to map raw policy actions into WorldForge Action objects."
)


@dataclass(slots=True, frozen=True)
class _CosmosPolicyConfig:
    base_url: str | None
    base_url_direct: bool
    api_token: str | None
    api_token_direct: bool
    timeout_seconds: float
    timeout_direct: bool
    embodiment_tag: str | None
    embodiment_direct: bool
    model: str | None
    model_direct: bool
    return_all_query_results: bool | None
    return_all_query_results_direct: bool
    allow_local_base_url: bool
    allow_local_base_url_direct: bool
    allowed_hosts: tuple[str, ...] | None
    allowed_hosts_direct: bool
    expected_action_dim: int | None


def _validated_action_translator(action_translator: ActionTranslator | None) -> None:
    if action_translator is not None and not callable(action_translator):
        raise WorldForgeError("Cosmos-Policy action_translator must be callable.")


def _resolved_expected_action_dim(value: int | None) -> int | None:
    if value is None:
        return None
    return require_positive_int(value, name="Cosmos-Policy expected_action_dim")


def _resolved_timeout_seconds(value: float | str | None) -> float:
    timeout = _optional_positive_float(value, name="Cosmos-Policy timeout_seconds")
    return timeout if timeout is not None else DEFAULT_COSMOS_POLICY_TIMEOUT_SECONDS


def _resolved_allow_local_base_url(value: bool | str | None) -> bool:
    return bool(optional_bool(value, name="Cosmos-Policy allow_local_base_url"))


def _cosmos_policy_base_url(value: str | None) -> str | None:
    return optional_non_empty(
        value if value is not None else env_value(COSMOS_POLICY_BASE_URL_ENV_VAR),
        name="Cosmos-Policy base_url",
    )


def _cosmos_policy_api_token(value: str | None) -> str | None:
    return optional_non_empty(
        value if value is not None else env_value(COSMOS_POLICY_API_TOKEN_ENV_VAR),
        name="Cosmos-Policy api_token",
    )


def _cosmos_policy_timeout_seconds(value: float | str | None) -> float:
    configured = value if value is not None else env_value(COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR)
    return _resolved_timeout_seconds(configured)


def _cosmos_policy_embodiment_tag(value: str | None) -> str | None:
    configured = (
        value
        if value is not None
        else env_value(COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR) or DEFAULT_COSMOS_POLICY_EMBODIMENT_TAG
    )
    return optional_non_empty(configured, name="Cosmos-Policy embodiment_tag")


def _cosmos_policy_model(value: str | None) -> str | None:
    configured = (
        value
        if value is not None
        else env_value(COSMOS_POLICY_MODEL_ENV_VAR) or DEFAULT_COSMOS_POLICY_MODEL
    )
    return optional_non_empty(configured, name="Cosmos-Policy model")


def _cosmos_policy_return_all(value: bool | str | None) -> bool | None:
    configured = value if value is not None else env_value(COSMOS_POLICY_RETURN_ALL_ENV_VAR)
    return optional_bool(configured, name="Cosmos-Policy return_all_query_results")


def _cosmos_policy_allow_local_base_url(value: bool | str | None) -> bool:
    configured = (
        value if value is not None else env_value(COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR)
    )
    return _resolved_allow_local_base_url(configured)


def _cosmos_policy_allowed_hosts(
    value: Sequence[str] | str | None,
) -> tuple[str, ...] | None:
    configured = value if value is not None else env_value(COSMOS_POLICY_ALLOWED_HOSTS_ENV_VAR)
    return _optional_host_patterns(configured, name="Cosmos-Policy allowed_hosts")


def _resolve_cosmos_policy_config(
    *,
    base_url: str | None,
    api_token: str | None,
    timeout_seconds: float | str | None,
    embodiment_tag: str | None,
    model: str | None,
    expected_action_dim: int | None,
    return_all_query_results: bool | str | None,
    allow_local_base_url: bool | str | None,
    allowed_hosts: Sequence[str] | str | None,
) -> _CosmosPolicyConfig:
    return _CosmosPolicyConfig(
        base_url=_cosmos_policy_base_url(base_url),
        base_url_direct=base_url is not None,
        api_token=_cosmos_policy_api_token(api_token),
        api_token_direct=api_token is not None,
        timeout_seconds=_cosmos_policy_timeout_seconds(timeout_seconds),
        timeout_direct=timeout_seconds is not None,
        embodiment_tag=_cosmos_policy_embodiment_tag(embodiment_tag),
        embodiment_direct=embodiment_tag is not None,
        model=_cosmos_policy_model(model),
        model_direct=model is not None,
        return_all_query_results=_cosmos_policy_return_all(return_all_query_results),
        return_all_query_results_direct=return_all_query_results is not None,
        allow_local_base_url=_cosmos_policy_allow_local_base_url(allow_local_base_url),
        allow_local_base_url_direct=allow_local_base_url is not None,
        allowed_hosts=_cosmos_policy_allowed_hosts(allowed_hosts),
        allowed_hosts_direct=allowed_hosts is not None,
        expected_action_dim=_resolved_expected_action_dim(expected_action_dim),
    )


def _cosmos_policy_capabilities(
    action_translator: ActionTranslator | None,
) -> ProviderCapabilities:
    return ProviderCapabilities(
        predict=False,
        embed=False,
        plan=False,
        score=False,
        policy=action_translator is not None,
    )


def _cosmos_policy_profile(model: str | None) -> ProviderProfileSpec:
    return ProviderProfileSpec(
        description=(
            "NVIDIA Cosmos-Policy server adapter for selecting embodied ALOHA action chunks."
        ),
        package="worldforge + host-supplied Cosmos-Policy server",
        implementation_status="beta",
        requires_credentials=False,
        required_env_vars=(COSMOS_POLICY_BASE_URL_ENV_VAR,),
        supported_modalities=("images", "state", "language", "actions"),
        artifact_types=("action_policy",),
        notes=(
            "Targets the Cosmos-Policy ALOHA `/act` server contract.",
            "Does not import cosmos_policy, torch, CUDA, Docker, or robot runtime dependencies.",
            "Requires a host-supplied action_translator to map raw 14D bimanual actions to "
            "WorldForge Action objects.",
            "Rejects localhost, private, and link-local base URLs during URL preflight unless "
            f"{COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR}=1 is explicitly set.",
            f"Supports {COSMOS_POLICY_ALLOWED_HOSTS_ENV_VAR} for deployments that require "
            "an explicit host allowlist.",
            "DNS checks are a best-effort preflight, not a pinned-connection or network "
            "egress control.",
            "Cosmos-Policy is an embodied policy/planning runtime, not the existing Cosmos "
            "media-generation NIM adapter.",
        ),
        default_model=model,
        supported_models=(model,) if model else (),
    )


def _cosmos_policy_request_policy(
    request_policy: ProviderRequestPolicy | None,
    *,
    timeout_seconds: float,
) -> ProviderRequestPolicy:
    return request_policy or ProviderRequestPolicy.remote_defaults(
        request_timeout_seconds=timeout_seconds
    )


def _config_env_present(name: str) -> bool:
    return env_value(name) is not None


def _cosmos_policy_required_config_field(
    name: str,
    *,
    direct: bool,
    present: bool,
) -> ConfigFieldSummary:
    return _field_summary(
        name,
        required=True,
        source=config_source(name, direct=direct),
        present=present,
    )


def _cosmos_policy_optional_config_field(
    name: str,
    *,
    direct: bool,
    present: bool | None = None,
    secret: bool = False,
) -> ConfigFieldSummary:
    resolved_present = (direct or _config_env_present(name)) if present is None else present
    return _field_summary(
        name,
        required=False,
        secret=secret,
        source=config_source(name, direct=direct),
        present=resolved_present,
    )


def _cosmos_policy_defaulted_config_field(
    name: str,
    *,
    direct: bool,
    present: bool | None = None,
) -> ConfigFieldSummary:
    env_present = _config_env_present(name)
    resolved_present = (direct or env_present) if present is None else present
    return _field_summary(
        name,
        required=False,
        source=config_source(name, direct=direct, default=not direct and not env_present),
        present=resolved_present,
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
        allowed_hosts: Sequence[str] | str | None = None,
        action_translator: ActionTranslator | None = None,
        request_policy: ProviderRequestPolicy | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        _validated_action_translator(action_translator)
        config = _resolve_cosmos_policy_config(
            base_url=base_url,
            api_token=api_token,
            timeout_seconds=timeout_seconds,
            embodiment_tag=embodiment_tag,
            model=model,
            expected_action_dim=expected_action_dim,
            return_all_query_results=return_all_query_results,
            allow_local_base_url=allow_local_base_url,
            allowed_hosts=allowed_hosts,
        )
        self._base_url_direct = config.base_url_direct
        self._base_url = config.base_url
        self._api_token_direct = config.api_token_direct
        self.api_token = config.api_token
        self._timeout_direct = config.timeout_direct
        self.timeout_seconds = config.timeout_seconds
        self._embodiment_direct = config.embodiment_direct
        self.embodiment_tag = config.embodiment_tag
        self._model_direct = config.model_direct
        self.model = config.model
        self.return_all_query_results = config.return_all_query_results
        self._return_all_query_results_direct = config.return_all_query_results_direct
        self._allow_local_base_url_direct = config.allow_local_base_url_direct
        self.allow_local_base_url = config.allow_local_base_url
        self._allowed_hosts_direct = config.allowed_hosts_direct
        self.allowed_hosts = config.allowed_hosts
        self.expected_action_dim = config.expected_action_dim
        self._action_translator = action_translator
        self._transport = transport
        super().__init__(
            name=name,
            capabilities=_cosmos_policy_capabilities(action_translator),
            profile=_cosmos_policy_profile(self.model),
            request_policy=_cosmos_policy_request_policy(
                request_policy,
                timeout_seconds=self.timeout_seconds,
            ),
            event_handler=event_handler,
        )

    def configured(self) -> bool:
        return self._resolved_base_url() is not None

    def config_summary(self) -> ProviderConfigSummary:
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=self._config_summary_fields(),
        )

    def _config_summary_fields(self) -> tuple[ConfigFieldSummary, ...]:
        return (
            _cosmos_policy_required_config_field(
                COSMOS_POLICY_BASE_URL_ENV_VAR,
                direct=self._base_url_direct,
                present=self._resolved_base_url() is not None,
            ),
            _cosmos_policy_optional_config_field(
                COSMOS_POLICY_API_TOKEN_ENV_VAR,
                direct=self._api_token_direct,
                present=self.api_token is not None,
                secret=True,
            ),
            _cosmos_policy_defaulted_config_field(
                COSMOS_POLICY_TIMEOUT_SECONDS_ENV_VAR,
                direct=self._timeout_direct,
            ),
            _cosmos_policy_defaulted_config_field(
                COSMOS_POLICY_EMBODIMENT_TAG_ENV_VAR,
                direct=self._embodiment_direct,
                present=self.embodiment_tag is not None,
            ),
            _cosmos_policy_defaulted_config_field(
                COSMOS_POLICY_MODEL_ENV_VAR,
                direct=self._model_direct,
                present=self.model is not None,
            ),
            _cosmos_policy_optional_config_field(
                COSMOS_POLICY_RETURN_ALL_ENV_VAR,
                direct=self._return_all_query_results_direct,
            ),
            _cosmos_policy_defaulted_config_field(
                COSMOS_POLICY_ALLOW_LOCAL_BASE_URL_ENV_VAR,
                direct=self._allow_local_base_url_direct,
            ),
            _cosmos_policy_optional_config_field(
                COSMOS_POLICY_ALLOWED_HOSTS_ENV_VAR,
                direct=self._allowed_hosts_direct,
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
        validated_base_url = validate_remote_base_url(
            base_url,
            provider_name=self.name,
            env_var=COSMOS_POLICY_BASE_URL_ENV_VAR,
            allow_local_network=self.allow_local_base_url,
            allowed_hosts=self.allowed_hosts,
        )
        return httpx.Client(
            base_url=validated_base_url,
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
        base_url = self._resolved_base_url()
        if base_url is not None:
            try:
                validate_remote_base_url(
                    base_url,
                    provider_name=self.name,
                    env_var=COSMOS_POLICY_BASE_URL_ENV_VAR,
                    allow_local_network=self.allow_local_base_url,
                    allowed_hosts=self.allowed_hosts,
                )
            except ProviderError as exc:
                return self._health(started, str(exc), healthy=False)
        return self._health(
            started,
            "configured for Cosmos-Policy /act; upstream exposes no non-mutating health endpoint",
            healthy=True,
        )

    def _validate_info(self, info: JSONDict) -> tuple[JSONDict, str, int | None]:
        normalized_info = require_json_dict(info, name="Cosmos-Policy policy info")
        observation = _cosmos_policy_observation(normalized_info)
        task_description = _cosmos_policy_task_description(normalized_info, observation)
        _validate_cosmos_policy_embodiment_tag(normalized_info)
        options = _cosmos_policy_options(normalized_info)
        payload = _cosmos_policy_payload(
            observation=observation,
            task_description=task_description,
            options=options,
        )
        _apply_cosmos_policy_return_all(
            payload=payload,
            normalized_info=normalized_info,
            default_return_all=self.return_all_query_results,
        )
        action_horizon = _cosmos_policy_action_horizon(
            normalized_info=normalized_info,
            observation=observation,
            options=options,
            payload=payload,
        )
        if action_horizon is not None:
            payload["action_horizon"] = action_horizon
        return payload, task_description, action_horizon

    def _translate_actions(
        self,
        *,
        raw_actions: object,
        info: JSONDict,
        provider_info: JSONDict,
    ) -> list[list[Action]]:
        if self._action_translator is None:
            raise ProviderError(_TRANSLATOR_REQUIRED_MESSAGE)
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
        payload, task_description, action_horizon_override = self._validate_info(info)
        self._require_action_translator()
        try:
            parsed = self._request_policy_response(payload)
            raw_actions = _cosmos_policy_raw_actions(parsed)
            candidate_plans, selected_index = self._translated_candidate_plans(
                parsed=parsed,
                raw_actions=raw_actions,
                info=info,
            )
            return self._policy_result(
                info=info,
                task_description=task_description,
                action_horizon_override=action_horizon_override,
                parsed=parsed,
                raw_actions=raw_actions,
                candidate_plans=candidate_plans,
                selected_index=selected_index,
            )
        except (ProviderError, WorldStateError) as exc:
            self._emit_policy_failure(started=started, exc=exc)
            raise
        except Exception as exc:
            error = ProviderError(
                f"Cosmos-Policy action selection failed: {_redact_observable_text(str(exc))}"
            )
            self._emit_policy_failure(started=started, exc=error)
            raise error from exc

    def _require_action_translator(self) -> None:
        if self._action_translator is None:
            raise ProviderError(_TRANSLATOR_REQUIRED_MESSAGE)

    def _request_policy_response(self, payload: JSONDict) -> CosmosPolicyResponse:
        request_policy = self._require_request_policy()
        with self._client() as client:
            try:
                response_payload = request_json_with_policy(
                    client,
                    method="POST",
                    url="/act",
                    provider_name=self.name,
                    operation_name="policy",
                    policy=request_policy.request,
                    emit_event=self._emit_event,
                    accepted_content_types=("application/json",),
                    json=payload,
                )
            except ProviderError as exc:
                if _is_malformed_json_response_error(str(exc)):
                    raise WorldStateError(str(exc)) from exc
                raise
        try:
            return CosmosPolicyResponse.from_payload(
                response_payload,
                provider_name=self.name,
                expected_action_dim=self.expected_action_dim,
            )
        except (ProviderError, WorldForgeError) as exc:
            raise WorldStateError(str(exc)) from exc

    def _translated_candidate_plans(
        self,
        *,
        parsed: CosmosPolicyResponse,
        raw_actions: JSONDict,
        info: JSONDict,
    ) -> tuple[list[list[Action]], int]:
        candidate_plans = self._translate_actions(
            raw_actions=raw_actions,
            info=info,
            provider_info=parsed.provider_info,
        )
        _validate_translated_candidate_count(parsed=parsed, candidate_plans=candidate_plans)
        selected_index = _selected_action_index(parsed.actions, parsed.all_actions)
        if selected_index >= len(candidate_plans):
            raise ProviderError(
                "Cosmos-Policy selected candidate index "
                f"{selected_index} is outside the translated candidate count "
                f"{len(candidate_plans)}."
            )
        return candidate_plans, selected_index

    def _policy_result(
        self,
        *,
        info: JSONDict,
        task_description: str,
        action_horizon_override: int | None,
        parsed: CosmosPolicyResponse,
        raw_actions: JSONDict,
        candidate_plans: list[list[Action]],
        selected_index: int,
    ) -> ActionPolicyResult:
        selected_actions = candidate_plans[selected_index]
        action_horizon = len(selected_actions)
        return ActionPolicyResult(
            provider=self.name,
            actions=list(selected_actions),
            raw_actions=raw_actions,
            action_horizon=action_horizon,
            embodiment_tag=self._result_embodiment_tag(info),
            metadata=_cosmos_policy_result_metadata(
                model=self.model,
                task_description=task_description,
                expected_action_dim=self.expected_action_dim,
                selected_index=selected_index,
                candidate_count=len(candidate_plans),
                action_horizon_override=action_horizon_override,
                parsed=parsed,
            ),
            action_candidates=candidate_plans,
        )

    def _result_embodiment_tag(self, info: JSONDict) -> str | None:
        embodiment_tag_value = info.get("embodiment_tag")
        if embodiment_tag_value is not None:
            return embodiment_tag_value.strip()
        return self.embodiment_tag or None

    def _emit_policy_failure(self, *, started: float, exc: BaseException) -> None:
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
