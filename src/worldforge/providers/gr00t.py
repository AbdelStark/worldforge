"""NVIDIA Isaac GR00T policy-client provider."""

from __future__ import annotations

import importlib
import io
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
    _redact_observable_text,
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
DEFAULT_GROOT_POLICY_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
DEFAULT_GROOT_POLICY_MAX_ARRAY_BYTES = 64 * 1024 * 1024
_FALLBACK_CLIENT_IMPORTS = {
    "msgpack": "msgpack",
    "numpy": "numpy",
    "pyzmq": "zmq",
}

ActionTranslator = Callable[
    [object, JSONDict, JSONDict],
    Sequence[Action] | Sequence[Sequence[Action]],
]


class _GrootZmqPolicyClient:
    """Small GR00T PolicyClient-compatible fallback for Python 3.13 clients.

    NVIDIA's full `gr00t` package is currently pinned to Python 3.10, while WorldForge is
    packaged for Python 3.13. This fallback implements the documented ZMQ/msgpack client protocol
    so a WorldForge process can call a host-owned GR00T server without installing the full runtime.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout_ms: int,
        api_token: str | None = None,
        strict: bool = False,
        max_response_bytes: int = DEFAULT_GROOT_POLICY_MAX_RESPONSE_BYTES,
        max_array_bytes: int = DEFAULT_GROOT_POLICY_MAX_ARRAY_BYTES,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_ms = timeout_ms
        self.api_token = api_token
        self.strict = strict
        self.max_response_bytes = max_response_bytes
        self.max_array_bytes = max_array_bytes
        self._msgpack = importlib.import_module("msgpack")
        self._np = importlib.import_module("numpy")
        self._zmq = importlib.import_module("zmq")
        self._context = self._zmq.Context()
        self._init_socket()

    def _init_socket(self) -> None:
        self._socket = self._context.socket(self._zmq.REQ)
        self._socket.setsockopt(self._zmq.RCVTIMEO, self.timeout_ms)
        self._socket.setsockopt(self._zmq.SNDTIMEO, self.timeout_ms)
        if hasattr(self._zmq, "MAXMSGSIZE"):
            self._socket.setsockopt(self._zmq.MAXMSGSIZE, self.max_response_bytes)
        self._socket.connect(f"tcp://{self.host}:{self.port}")

    def _encode_custom(self, obj: object) -> object:
        if isinstance(obj, self._np.ndarray):
            output = io.BytesIO()
            self._np.save(output, obj, allow_pickle=False)
            return {"__ndarray_class__": True, "as_npy": output.getvalue()}
        return obj

    def _decode_custom(self, obj: object) -> object:
        if not isinstance(obj, dict):
            return obj
        if "__ndarray_class__" in obj:
            as_npy = obj.get("as_npy")
            if not isinstance(as_npy, bytes | bytearray | memoryview):
                raise RuntimeError("GR00T PolicyServer returned an invalid ndarray payload.")
            if len(as_npy) > self.max_array_bytes:
                raise RuntimeError(
                    f"GR00T PolicyServer ndarray payload exceeds {self.max_array_bytes} bytes."
                )
            return self._np.load(io.BytesIO(as_npy), allow_pickle=False)
        if "__ModalityConfig_class__" in obj:
            return obj["as_json"]
        return obj

    def _to_bytes(self, payload: object) -> bytes:
        return self._msgpack.packb(payload, default=self._encode_custom)

    def _from_bytes(self, payload: bytes) -> object:
        if isinstance(payload, bytes | bytearray | memoryview) and (
            len(payload) > self.max_response_bytes
        ):
            raise RuntimeError(
                f"GR00T PolicyServer response exceeds {self.max_response_bytes} bytes."
            )
        return self._msgpack.unpackb(
            payload,
            object_hook=self._decode_custom,
            raw=False,
        )

    def call_endpoint(
        self,
        endpoint: str,
        data: dict[str, object] | None = None,
        *,
        requires_input: bool = True,
    ) -> object:
        request: dict[str, object] = {"endpoint": endpoint}
        if requires_input:
            request["data"] = dict(data or {})
        if self.api_token is not None:
            request["api_token"] = self.api_token
        self._socket.send(self._to_bytes(request))
        response = self._from_bytes(self._socket.recv())
        if isinstance(response, dict) and "error" in response:
            detail = _redact_observable_text(str(response["error"])).strip()
            raise RuntimeError(f"Server error: {detail}")
        return response

    def ping(self) -> bool:
        try:
            self.call_endpoint("ping", requires_input=False)
            return True
        except Exception:
            self._init_socket()
            return False

    def get_action(
        self,
        observation: object,
        options: dict[str, object] | None = None,
    ) -> object:
        payload: dict[str, object] = {"observation": observation}
        if options is not None:
            payload["options"] = options
        response = self.call_endpoint("get_action", payload)
        return tuple(response) if isinstance(response, list) else response

    def reset(self, options: dict[str, object] | None = None) -> object:
        payload: dict[str, object] = {}
        if options is not None:
            payload["options"] = options
        return self.call_endpoint("reset", payload)

    def get_modality_config(self) -> object:
        return self.call_endpoint("get_modality_config", requires_input=False)


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
                implementation_status="beta",
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
        except Exception as exc:
            return self._health(
                started,
                f"GR00T policy server health check failed: {exc}",
                healthy=False,
            )
        return self._health(
            started,
            f"configured for {self.host or 'injected policy client'}:{self.port}",
            healthy=True,
        )

    def _event_target(self) -> str:
        if self.host is None:
            return "injected-policy-client"
        return f"{self.host}:{self.port}"

    def _emit_policy_event(
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
                operation="policy",
                phase=phase,
                attempt=1,
                max_attempts=1,
                method="POLICYCLIENT.GET_ACTION",
                target=self._event_target(),
                duration_ms=duration_ms,
                message=message,
                metadata={
                    "timeout_ms": self.timeout_ms,
                    "strict": self.strict,
                    "embodiment_tag": self.embodiment_tag,
                    **dict(metadata or {}),
                },
            )
        )

    def _runtime_dependency_error(self) -> str | None:
        try:
            policy_module = importlib.import_module("gr00t.policy.server_client")
        except ImportError:
            return self._fallback_dependency_error()
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

    def _fallback_dependency_error(self) -> str | None:
        missing: list[str] = []
        for package, module_name in _FALLBACK_CLIENT_IMPORTS.items():
            try:
                importlib.import_module(module_name)
            except ImportError:
                missing.append(package)
            except Exception as exc:
                message = str(exc).strip()
                suffix = f": {message}" if message else ""
                return (
                    "GR00T fallback ZMQ client optional dependency import failed "
                    f"({module_name}: {type(exc).__name__}{suffix})"
                )
        if missing:
            packages = ", ".join(missing)
            return (
                missing_optional_dependency_detail("gr00t", "gr00t.policy.server_client")
                + f"; alternatively install fallback client packages: {packages}"
            )
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
        except ImportError as exc:
            dependency_error = self._fallback_dependency_error()
            if dependency_error is not None:
                raise ProviderError(dependency_error) from exc
            client_type = _GrootZmqPolicyClient
        except Exception as exc:
            detail = _redact_observable_text(str(exc)).strip()
            suffix = f": {detail}" if detail else ""
            raise ProviderError(f"Failed to import GR00T PolicyClient{suffix}") from exc
        try:
            self._policy_client = client_type(
                host=self.host,
                port=self.port,
                timeout_ms=self.timeout_ms,
                api_token=self.api_token,
                strict=self.strict,
            )
        except Exception as exc:
            detail = _redact_observable_text(str(exc)).strip()
            suffix = f": {detail}" if detail else ""
            raise ProviderError(f"Failed to create GR00T PolicyClient{suffix}") from exc
        return self._policy_client

    def _validate_info(
        self,
        info: JSONDict,
    ) -> tuple[JSONDict, JSONDict | None, int | None, str | None]:
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
        action_horizon_value = info.get("action_horizon")
        try:
            action_horizon = (
                optional_positive_int(action_horizon_value, name="GR00T action_horizon")
                if action_horizon_value is not None
                else None
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        embodiment_tag = info.get("embodiment_tag")
        if embodiment_tag is not None:
            if not isinstance(embodiment_tag, str) or not embodiment_tag.strip():
                raise ProviderError(
                    "GR00T policy info.embodiment_tag must be a non-empty string when provided."
                )
            embodiment_tag = embodiment_tag.strip()
        return (
            dict(observation),
            dict(options) if isinstance(options, dict) else None,
            action_horizon,
            embodiment_tag,
        )

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
            (
                observation,
                options,
                requested_action_horizon,
                requested_embodiment_tag,
            ) = self._validate_info(info)
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
            translated_action_horizon = len(candidate_plans[0])
            if (
                requested_action_horizon is not None
                and requested_action_horizon != translated_action_horizon
            ):
                raise ProviderError(
                    "GR00T policy info.action_horizon must match the translated action count."
                )
            action_horizon = requested_action_horizon or translated_action_horizon
            embodiment_tag = requested_embodiment_tag or self.embodiment_tag
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
            self._emit_policy_event(
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
            self._emit_policy_event(
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(exc),
            )
            raise
        except Exception as exc:
            error = ProviderError(f"GR00T policy selection failed: {exc}")
            self._emit_policy_event(
                phase="failure",
                duration_ms=max(0.1, (perf_counter() - started) * 1000),
                message=str(error),
            )
            raise error from exc
