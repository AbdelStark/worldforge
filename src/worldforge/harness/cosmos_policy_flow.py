"""Checkout-safe Cosmos-Policy replay flow."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from worldforge.artifact_io import write_json_artifact
from worldforge.framework import WorldForge
from worldforge.harness.flow_artifacts import COSMOS_POLICY_REPLAY_ARTIFACT
from worldforge.harness.flow_rendering import transcript_for as _transcript_for
from worldforge.harness.flow_replay_utils import (
    decode_json_numpy_action_row,
    encode_json_numpy_action_row,
)
from worldforge.harness.flow_replay_utils import (
    is_finite_number as _is_finite_number,
)
from worldforge.harness.flow_replay_utils import (
    preview_action_rows as _preview_action_rows,
)
from worldforge.harness.flow_replay_utils import (
    read_replay_artifact as _read_replay_artifact,
)
from worldforge.harness.flow_replay_utils import (
    require_json_native_value as _require_json_native_value,
)
from worldforge.harness.flow_replay_utils import (
    require_json_object as _require_json_object,
)
from worldforge.models import Action, JSONDict, ProviderEvent, WorldStateError
from worldforge.providers.base import ProviderError

ResponsePayloadBuilder = Callable[[JSONDict], JSONDict]

_COSMOS_POLICY_REPLAY_BASE_URL = "http://93.184.216.34"
_COSMOS_POLICY_MODEL = "nvidia/Cosmos-Policy-ALOHA-Predict2-2B"
_COSMOS_POLICY_ACTION_HORIZON = 50
_COSMOS_POLICY_ACTION_DIM = 14
_COSMOS_POLICY_VALUE_PREDICTION = 0.190714
_COSMOS_POLICY_REPLAY_SCHEMA_VERSION = 1
_COSMOS_POLICY_OBSERVATION_FIELDS = (
    "left_wrist_image",
    "primary_image",
    "proprio",
    "right_wrist_image",
)
_COSMOS_POLICY_REPLAY_REQUEST_KEYS = frozenset(
    {
        "observation_fields",
        "observation_summary",
        "proprio_dim",
        "task_description",
        "action_horizon",
        "embodiment_tag",
    }
)
_COSMOS_POLICY_PREVIEW_ROWS = (
    (0.01227, -0.02509, -0.00844, -0.04266, 0.05760, 0.01356),
    (0.00180, -0.02080, -0.01734, -0.03035, 0.05673, 0.00983),
    (0.01250, -0.02521, -0.00710, -0.04928, 0.05478, 0.01556),
    (0.00418, -0.02012, -0.01506, -0.03610, 0.06206, 0.01546),
    (0.01023, -0.02691, -0.01081, -0.05677, 0.06027, 0.01551),
    (0.00377, -0.02269, -0.01370, -0.04925, 0.06735, 0.01213),
)


@dataclass
class _ReplayRequestCounter:
    count: int = 0


def run_cosmos_policy_demo(
    *,
    state_dir: Path,
    emit: bool = False,
    response_payload: ResponsePayloadBuilder | None = None,
) -> JSONDict:
    response_payload_builder = response_payload or cosmos_policy_response_payload
    events: list[ProviderEvent] = []
    request_counter = _ReplayRequestCounter()
    replay_source_path = _write_prepared_cosmos_policy_replay_artifact(state_dir)
    saved_replay = load_cosmos_policy_replay_artifact(replay_source_path)
    saved_request = _require_json_object(saved_replay["request"], "Cosmos-Policy replay request")
    policy_info = cosmos_policy_policy_info_from_replay(saved_replay)
    policy_output = response_payload_builder(saved_replay)
    provider = _cosmos_policy_replay_provider(
        saved_request=saved_request,
        policy_output=policy_output,
        request_counter=request_counter,
        event_handler=events.append,
    )
    forge = WorldForge(state_dir=state_dir, auto_register_remote=False)
    forge.register_provider(provider)
    health = None
    try:
        health = provider.health()
        result = forge.select_actions("cosmos-policy", info=policy_info)
    except Exception as exc:
        failure_event = ProviderEvent(
            provider="cosmos-policy",
            operation="policy",
            phase="failure",
            message=str(exc),
            metadata={"stage": "harness-replay"},
        )
        if not events or events[-1].message != failure_event.message:
            events.append(failure_event)
        replay_artifact = _cosmos_policy_failure_replay_artifact(
            saved_replay,
            replay_source_path=replay_source_path,
            events=events,
            error=exc,
        )
        summary = _cosmos_policy_replay_failure_summary(
            state_dir=state_dir,
            saved_replay=saved_replay,
            replay_source_path=replay_source_path,
            health=health.to_dict() if health is not None else None,
            request_count=request_counter.count,
            events=events,
            replay_artifact=replay_artifact,
            error=exc,
        )
        if emit:
            print("\n".join(_transcript_for("cosmos-policy", summary)))
        return summary
    summary = _cosmos_policy_replay_success_summary(
        state_dir=state_dir,
        saved_replay=saved_replay,
        replay_source_path=replay_source_path,
        health=health.to_dict(),
        request_count=request_counter.count,
        events=events,
        result=result,
    )
    if emit:
        print("\n".join(_transcript_for("cosmos-policy", summary)))
    return summary


def _cosmos_policy_replay_provider(
    *,
    saved_request: JSONDict,
    policy_output: JSONDict,
    request_counter: _ReplayRequestCounter,
    event_handler: Callable[[ProviderEvent], None],
):
    import httpx

    from worldforge.providers import CosmosPolicyProvider

    return CosmosPolicyProvider(
        base_url=_COSMOS_POLICY_REPLAY_BASE_URL,
        model=_COSMOS_POLICY_MODEL,
        return_all_query_results=False,
        allowed_hosts=("93.184.216.34",),
        transport=httpx.MockTransport(
            _cosmos_policy_replay_handler(
                saved_request=saved_request,
                policy_output=policy_output,
                request_counter=request_counter,
            )
        ),
        action_translator=_cosmos_policy_action_translator,
        event_handler=event_handler,
    )


def _cosmos_policy_replay_handler(
    *,
    saved_request: JSONDict,
    policy_output: JSONDict,
    request_counter: _ReplayRequestCounter,
):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        request_counter.count += 1
        try:
            payload = json.loads(request.content.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WorldStateError("Cosmos-Policy replay request body must be JSON.") from exc
        if request.method != "POST":
            raise WorldStateError(f"Cosmos-Policy replay expected POST, got {request.method}.")
        if request.url.path != "/act":
            raise WorldStateError(f"Cosmos-Policy replay expected /act, got {request.url.path}.")
        validate_cosmos_policy_replay_request(payload, saved_request)
        return httpx.Response(200, json=policy_output)

    return handler


def _cosmos_policy_action_translator(
    raw_actions: object,
    _info: JSONDict,
    _provider_info: JSONDict,
) -> list[Action]:
    if not isinstance(raw_actions, dict):
        raise ProviderError("Cosmos-Policy replay translator expected raw action metadata.")
    matrix = raw_actions.get("actions")
    if not isinstance(matrix, list):
        raise ProviderError("Cosmos-Policy replay translator expected action rows.")
    return [_cosmos_policy_action_from_row(row, index=index) for index, row in enumerate(matrix)]


def _cosmos_policy_action_from_row(row: object, *, index: int) -> Action:
    if not isinstance(row, list):
        raise ProviderError(f"Cosmos-Policy replay action row {index} must be a list.")
    if len(row) != _COSMOS_POLICY_ACTION_DIM:
        raise ProviderError(
            f"Cosmos-Policy replay action row {index} must be {_COSMOS_POLICY_ACTION_DIM}D."
        )
    return Action.move_to(float(row[0]), float(row[1]), float(row[2]))


def _cosmos_policy_replay_success_summary(
    *,
    state_dir: Path,
    saved_replay: JSONDict,
    replay_source_path: Path,
    health: JSONDict,
    request_count: int,
    events: Sequence[ProviderEvent],
    result: object,
) -> JSONDict:
    metadata = result.metadata
    provider_info = metadata.get("provider_info", {})
    raw_action_summary = metadata.get("raw_action_summary", {})
    raw_actions = result.raw_actions.get("actions", [])
    raw_action_shape = list(raw_action_summary.get("actions_shape", []))
    selected_action_preview = [action.to_dict() for action in result.actions[:6]]
    raw_action_preview = _preview_action_rows(raw_actions)
    replay_artifact = _cosmos_policy_success_replay_artifact(
        saved_replay=saved_replay,
        replay_source_path=replay_source_path,
        events=events,
        result=result,
        raw_action_shape=raw_action_shape,
        raw_action_preview=raw_action_preview,
        selected_action_preview=selected_action_preview,
    )
    return {
        "demo_kind": "cosmos_policy_saved_replay",
        "state_dir": str(state_dir),
        "providers": [result.provider],
        "model": metadata.get("model"),
        "task_description": metadata.get("task_description"),
        "runtime": metadata.get("runtime"),
        "server_path": metadata.get("server_path"),
        "runtime_contract": "saved /act replay through CosmosPolicyProvider",
        "loaded_replay_artifact": replay_source_path.name,
        "health": health,
        "request_count": request_count,
        "raw_action_shape": raw_action_shape,
        "translated_action_count": len(result.actions),
        "action_horizon": result.action_horizon,
        "selected_candidate_index": metadata.get("selected_candidate_index"),
        "candidate_count": metadata.get("candidate_count"),
        "value_prediction": provider_info.get("value_prediction"),
        "selected_actions": [action.to_dict() for action in result.actions],
        "selected_action_preview": selected_action_preview,
        "raw_action_preview": raw_action_preview,
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "harness_artifacts": {
            COSMOS_POLICY_REPLAY_ARTIFACT.name: COSMOS_POLICY_REPLAY_ARTIFACT.descriptor(
                replay_artifact
            ),
        },
    }


def _cosmos_policy_success_replay_artifact(
    *,
    saved_replay: JSONDict,
    replay_source_path: Path,
    events: Sequence[ProviderEvent],
    result: object,
    raw_action_shape: list[object],
    raw_action_preview: list[list[float]],
    selected_action_preview: list[JSONDict],
) -> JSONDict:
    metadata = result.metadata
    provider_info = metadata.get("provider_info", {})
    replay_artifact = dict(saved_replay)
    replay_artifact.update(
        {
            "manifest": {
                "flow_id": "cosmos-policy",
                "provider": result.provider,
                "model": metadata.get("model"),
                "server_path": metadata.get("server_path"),
                "runtime": metadata.get("runtime"),
                "task_description": metadata.get("task_description"),
                "action_horizon": result.action_horizon,
                "action_dim": _COSMOS_POLICY_ACTION_DIM,
                "source_artifact": replay_source_path.name,
            },
            "response": {
                "json_numpy_rows": True,
                "raw_action_shape": raw_action_shape,
                "value_prediction": provider_info.get("value_prediction"),
                "translated_action_count": len(result.actions),
                "raw_action_preview": raw_action_preview,
                "selected_action_preview": selected_action_preview,
            },
            "translated_actions": [action.to_dict() for action in result.actions],
            "provider_events": [event.to_dict() for event in events],
        }
    )
    return replay_artifact


def _cosmos_policy_policy_info() -> JSONDict:
    return {
        "observation": {
            "primary_image": [[[[0, 0, 0]]]],
            "left_wrist_image": [[[[1, 1, 1]]]],
            "right_wrist_image": [[[[2, 2, 2]]]],
            "proprio": [0.0 for _ in range(_COSMOS_POLICY_ACTION_DIM)],
        },
        "task_description": "fold shirt",
        "embodiment_tag": "aloha",
        "action_horizon": _COSMOS_POLICY_ACTION_HORIZON,
    }


def _write_prepared_cosmos_policy_replay_artifact(state_dir: Path) -> Path:
    replay_path = state_dir / "cosmos-policy-prepared-replay.json"
    return write_json_artifact(replay_path, cosmos_policy_saved_replay_payload())


def cosmos_policy_saved_replay_payload() -> JSONDict:
    encoded_rows = [_json_numpy_action_row(row) for row in _cosmos_policy_action_rows()]
    task_description = "fold shirt"
    observation_fields = list(_COSMOS_POLICY_OBSERVATION_FIELDS)
    return {
        "schema_version": _COSMOS_POLICY_REPLAY_SCHEMA_VERSION,
        "source": "sanitized Cosmos-Policy live /act response shape",
        "manifest": {
            "flow_id": "cosmos-policy",
            "provider": "cosmos-policy",
            "model": _COSMOS_POLICY_MODEL,
            "server_path": "/act",
            "runtime": "saved replay",
            "task_description": task_description,
            "action_horizon": _COSMOS_POLICY_ACTION_HORIZON,
            "action_dim": _COSMOS_POLICY_ACTION_DIM,
        },
        "request": {
            "observation_fields": observation_fields,
            "observation_summary": _cosmos_policy_redacted_observation_summary(),
            "proprio_dim": _COSMOS_POLICY_ACTION_DIM,
            "task_description": task_description,
            "action_horizon": _COSMOS_POLICY_ACTION_HORIZON,
            "embodiment_tag": "aloha",
        },
        "policy_output": {
            "actions": encoded_rows,
            "value_prediction": _COSMOS_POLICY_VALUE_PREDICTION,
            "future_image_predictions": {
                "summary": "omitted from checkout-safe replay artifact",
                "source": "sanitized-live-shape",
            },
        },
        "response": {
            "json_numpy_rows": True,
            "raw_action_shape": [_COSMOS_POLICY_ACTION_HORIZON, _COSMOS_POLICY_ACTION_DIM],
            "value_prediction": _COSMOS_POLICY_VALUE_PREDICTION,
            "translated_action_count": 0,
            "raw_action_preview": [],
            "selected_action_preview": [],
        },
        "translated_actions": [],
        "provider_events": [],
    }


def load_cosmos_policy_replay_artifact(path: Path) -> JSONDict:
    payload = _read_replay_artifact(path, "Cosmos-Policy")
    _validate_cosmos_policy_replay_root(payload)
    _validate_cosmos_policy_replay_manifest(payload)
    _validate_cosmos_policy_replay_saved_request(payload)
    _validate_cosmos_policy_replay_policy_output(payload)
    return payload


def _validate_cosmos_policy_replay_root(payload: JSONDict) -> None:
    if payload.get("schema_version") != _COSMOS_POLICY_REPLAY_SCHEMA_VERSION:
        raise WorldStateError("Cosmos-Policy replay artifact schema_version is unsupported.")


def _validate_cosmos_policy_replay_manifest(payload: JSONDict) -> None:
    manifest = _require_json_object(payload.get("manifest"), "Cosmos-Policy replay manifest")
    if manifest.get("flow_id") != "cosmos-policy":
        raise WorldStateError("Cosmos-Policy replay artifact flow_id must be 'cosmos-policy'.")
    if manifest.get("server_path") != "/act":
        raise WorldStateError("Cosmos-Policy replay artifact server_path must be '/act'.")
    if manifest.get("action_horizon") != _COSMOS_POLICY_ACTION_HORIZON:
        raise WorldStateError("Cosmos-Policy replay artifact action_horizon is unsupported.")
    if manifest.get("action_dim") != _COSMOS_POLICY_ACTION_DIM:
        raise WorldStateError("Cosmos-Policy replay artifact action_dim is unsupported.")


def _validate_cosmos_policy_replay_saved_request(payload: JSONDict) -> None:
    request = _require_json_object(payload.get("request"), "Cosmos-Policy replay request")
    if set(request) != _COSMOS_POLICY_REPLAY_REQUEST_KEYS:
        raise WorldStateError("Cosmos-Policy replay request contains unsupported fields.")
    expected_fields = list(_COSMOS_POLICY_OBSERVATION_FIELDS)
    if request.get("observation_fields") != expected_fields:
        raise WorldStateError(
            "Cosmos-Policy replay observation is missing fields or has unsupported fields."
        )
    _validate_cosmos_policy_observation_summary(
        request.get("observation_summary"),
        expected_fields=expected_fields,
    )
    if request.get("proprio_dim") != _COSMOS_POLICY_ACTION_DIM:
        raise WorldStateError("Cosmos-Policy replay proprio_dim is unsupported.")
    if not isinstance(request.get("task_description"), str) or not request["task_description"]:
        raise WorldStateError("Cosmos-Policy replay task_description must be a non-empty string.")
    if request.get("action_horizon") != _COSMOS_POLICY_ACTION_HORIZON:
        raise WorldStateError("Cosmos-Policy replay request action_horizon is unsupported.")
    if request.get("embodiment_tag") != "aloha":
        raise WorldStateError("Cosmos-Policy replay embodiment_tag must be 'aloha'.")


def _validate_cosmos_policy_replay_policy_output(payload: JSONDict) -> None:
    policy_output = _require_json_object(
        payload.get("policy_output"),
        "Cosmos-Policy replay policy_output",
    )
    actions = policy_output.get("actions")
    if not isinstance(actions, list) or len(actions) != _COSMOS_POLICY_ACTION_HORIZON:
        raise WorldStateError("Cosmos-Policy replay policy_output.actions must contain 50 rows.")
    for index, row in enumerate(actions):
        _decode_json_numpy_action_row(row, row_index=index)
    value_prediction = policy_output.get("value_prediction")
    if value_prediction is not None:
        _validate_cosmos_policy_value_prediction(value_prediction)


def _validate_cosmos_policy_value_prediction(value: object) -> None:
    try:
        value_prediction_float = float(value)
    except (TypeError, ValueError) as exc:
        raise WorldStateError(
            "Cosmos-Policy replay value_prediction must be numeric when present."
        ) from exc
    if not math.isfinite(value_prediction_float):
        raise WorldStateError("Cosmos-Policy replay value_prediction must be finite when present.")


def _cosmos_policy_failure_replay_artifact(
    saved_replay: JSONDict,
    *,
    replay_source_path: Path,
    events: Sequence[ProviderEvent],
    error: Exception,
) -> JSONDict:
    replay_artifact = dict(saved_replay)
    manifest = dict(_require_json_object(saved_replay["manifest"], "Cosmos-Policy replay manifest"))
    manifest.update(
        {
            "flow_id": "cosmos-policy",
            "status": "failed",
            "source_artifact": replay_source_path.name,
        }
    )
    response = dict(_require_json_object(saved_replay["response"], "Cosmos-Policy replay response"))
    response.update({"translated_action_count": 0, "error": str(error)})
    replay_artifact.update(
        {
            "manifest": manifest,
            "response": response,
            "translated_actions": [],
            "provider_events": [event.to_dict() for event in events],
        }
    )
    return replay_artifact


def _cosmos_policy_replay_failure_summary(
    *,
    state_dir: Path,
    saved_replay: JSONDict,
    replay_source_path: Path,
    health: JSONDict | None,
    request_count: int,
    events: Sequence[ProviderEvent],
    replay_artifact: JSONDict,
    error: Exception,
) -> JSONDict:
    manifest = _require_json_object(saved_replay["manifest"], "Cosmos-Policy replay manifest")
    request = _require_json_object(saved_replay["request"], "Cosmos-Policy replay request")
    response = _require_json_object(saved_replay["response"], "Cosmos-Policy replay response")
    return {
        "demo_kind": "cosmos_policy_saved_replay",
        "status": "failed",
        "state_dir": str(state_dir),
        "providers": ["cosmos-policy"],
        "model": manifest.get("model"),
        "task_description": request.get("task_description"),
        "runtime": manifest.get("runtime"),
        "server_path": manifest.get("server_path"),
        "runtime_contract": "saved /act replay through CosmosPolicyProvider",
        "loaded_replay_artifact": replay_source_path.name,
        "health": health or {"healthy": False, "message": "not checked"},
        "request_count": request_count,
        "raw_action_shape": response.get("raw_action_shape", []),
        "translated_action_count": 0,
        "action_horizon": request.get("action_horizon"),
        "selected_candidate_index": None,
        "candidate_count": 0,
        "value_prediction": response.get("value_prediction"),
        "selected_actions": [],
        "selected_action_preview": [],
        "raw_action_preview": [],
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "validation_errors": [str(error)],
        "harness_artifacts": {
            COSMOS_POLICY_REPLAY_ARTIFACT.name: COSMOS_POLICY_REPLAY_ARTIFACT.descriptor(
                replay_artifact
            ),
        },
    }


def validate_cosmos_policy_replay_request(payload: object, saved_request: JSONDict) -> None:
    if not isinstance(payload, dict):
        raise WorldStateError("Cosmos-Policy replay request payload must be a JSON object.")
    _require_json_native_value(payload, "Cosmos-Policy replay request payload")
    expected_fields = _cosmos_policy_expected_observation_fields(saved_request)
    expected_payload_keys = set(expected_fields) | {"task_description", "action_horizon"}
    payload_keys = _cosmos_policy_request_payload_keys(payload)
    _validate_cosmos_policy_request_keys(
        payload_keys,
        expected_payload_keys=expected_payload_keys,
    )
    _validate_cosmos_policy_request_scalars(payload, saved_request)
    _validate_cosmos_policy_request_proprio(payload.get("proprio"), saved_request["proprio_dim"])


def _cosmos_policy_expected_observation_fields(saved_request: JSONDict) -> list[str]:
    expected_fields_value = saved_request.get("observation_fields")
    if not isinstance(expected_fields_value, list) or not all(
        isinstance(field, str) for field in expected_fields_value
    ):
        raise WorldStateError("Cosmos-Policy replay saved observation fields are invalid.")
    expected_fields = sorted(expected_fields_value)
    if expected_fields != expected_fields_value:
        raise WorldStateError("Cosmos-Policy replay saved observation fields are invalid.")
    return expected_fields


def _cosmos_policy_request_payload_keys(payload: JSONDict) -> set[str]:
    payload_keys = set(payload)
    if "return_all_query_results" in payload:
        if not isinstance(payload["return_all_query_results"], bool):
            raise WorldStateError(
                "Cosmos-Policy replay request return_all_query_results must be boolean."
            )
        payload_keys.remove("return_all_query_results")
    return payload_keys


def _validate_cosmos_policy_request_keys(
    payload_keys: set[str],
    *,
    expected_payload_keys: set[str],
) -> None:
    if payload_keys != expected_payload_keys:
        missing = sorted(expected_payload_keys - payload_keys)
        extra = sorted(payload_keys - expected_payload_keys)
        detail = []
        if missing:
            detail.append(f"missing={missing}")
        if extra:
            detail.append(f"extra={extra}")
        raise WorldStateError(
            "Cosmos-Policy replay request keys drifted"
            + (f" ({'; '.join(detail)})" if detail else "")
            + "."
        )


def _validate_cosmos_policy_request_scalars(
    payload: JSONDict,
    saved_request: JSONDict,
) -> None:
    if payload.get("task_description") != saved_request["task_description"]:
        raise WorldStateError("Cosmos-Policy replay request task_description drifted.")
    if payload.get("action_horizon") != saved_request["action_horizon"]:
        raise WorldStateError("Cosmos-Policy replay request action_horizon drifted.")


def _validate_cosmos_policy_request_proprio(value: object, expected_dim: object) -> None:
    if not isinstance(value, list) or len(value) != expected_dim:
        raise WorldStateError("Cosmos-Policy replay request proprio shape drifted.")
    for index, item in enumerate(value):
        if not _is_finite_number(item):
            raise WorldStateError(
                f"Cosmos-Policy replay request proprio[{index}] must be finite numeric."
            )


def cosmos_policy_policy_info_from_replay(replay_artifact: JSONDict) -> JSONDict:
    request = _require_json_object(
        replay_artifact.get("request"),
        "Cosmos-Policy replay request",
    )
    policy_info = _cosmos_policy_policy_info()
    policy_info["task_description"] = request["task_description"]
    policy_info["action_horizon"] = request["action_horizon"]
    policy_info["embodiment_tag"] = request["embodiment_tag"]
    return policy_info


def cosmos_policy_response_payload(replay_artifact: JSONDict) -> JSONDict:
    policy_output = _require_json_object(
        replay_artifact.get("policy_output"),
        "Cosmos-Policy replay policy_output",
    )
    response: JSONDict = {"actions": policy_output["actions"]}
    if "value_prediction" in policy_output:
        response["value_prediction"] = policy_output["value_prediction"]
    if "future_image_predictions" in policy_output:
        response["future_image_predictions"] = policy_output["future_image_predictions"]
    return response


def _validate_cosmos_policy_observation_summary(
    value: object,
    *,
    expected_fields: Sequence[str],
) -> None:
    observation_summary = _require_json_object(
        value,
        "Cosmos-Policy replay observation_summary",
    )
    if set(observation_summary) != set(expected_fields):
        raise WorldStateError(
            "Cosmos-Policy replay observation_summary contains unsupported fields."
        )
    expected_shapes = {
        "primary_image": [1, 1, 1, 3],
        "left_wrist_image": [1, 1, 1, 3],
        "right_wrist_image": [1, 1, 1, 3],
        "proprio": [_COSMOS_POLICY_ACTION_DIM],
    }
    for field in expected_fields:
        field_summary = _require_json_object(
            observation_summary.get(field),
            f"Cosmos-Policy replay observation_summary.{field}",
        )
        if set(field_summary) != {"redacted", "shape"}:
            raise WorldStateError(
                f"Cosmos-Policy replay observation_summary.{field} contains unsupported fields."
            )
        if field_summary.get("redacted") is not True:
            raise WorldStateError(
                f"Cosmos-Policy replay observation field {field} must be redacted."
            )
        if field_summary.get("shape") != expected_shapes[field]:
            raise WorldStateError(
                f"Cosmos-Policy replay observation_summary.{field}.shape is unsupported."
            )


def _cosmos_policy_redacted_observation_summary() -> JSONDict:
    return {
        "primary_image": {"redacted": True, "shape": [1, 1, 1, 3]},
        "left_wrist_image": {
            "redacted": True,
            "shape": [1, 1, 1, 3],
        },
        "right_wrist_image": {
            "redacted": True,
            "shape": [1, 1, 1, 3],
        },
        "proprio": {"redacted": True, "shape": [_COSMOS_POLICY_ACTION_DIM]},
    }


def _cosmos_policy_action_rows() -> list[list[float]]:
    rows: list[list[float]] = []
    for index in range(_COSMOS_POLICY_ACTION_HORIZON):
        if index < len(_COSMOS_POLICY_PREVIEW_ROWS):
            prefix = list(_COSMOS_POLICY_PREVIEW_ROWS[index])
        else:
            prefix = [
                _bounded_action_value(index, dimension)
                for dimension in range(len(_COSMOS_POLICY_PREVIEW_ROWS[0]))
            ]
        row = list(prefix)
        row.extend(
            _bounded_action_value(index, dimension)
            for dimension in range(len(prefix), _COSMOS_POLICY_ACTION_DIM)
        )
        rows.append(row)
    return rows


def _bounded_action_value(index: int, dimension: int) -> float:
    magnitude = ((index * 17 + dimension * 31) % 90 + 5) / 1500.0
    sign = -1.0 if dimension in {1, 2, 3, 6, 8, 11, 13} else 1.0
    return round(sign * magnitude, 5)


def _json_numpy_action_row(row: Sequence[float]) -> JSONDict:
    return encode_json_numpy_action_row(row, action_dim=_COSMOS_POLICY_ACTION_DIM)


def _decode_json_numpy_action_row(value: object, *, row_index: int) -> list[float]:
    return decode_json_numpy_action_row(
        value,
        row_index=row_index,
        action_dim=_COSMOS_POLICY_ACTION_DIM,
    )
