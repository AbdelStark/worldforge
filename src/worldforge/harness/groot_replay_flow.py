"""Checkout-safe GR00T replay flow."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from worldforge.artifact_io import write_json_artifact
from worldforge.framework import WorldForge
from worldforge.harness.flow_artifacts import GROOT_REPLAY_ARTIFACT
from worldforge.harness.flow_rendering import transcript_for as _transcript_for
from worldforge.harness.flow_replay_utils import (
    read_replay_artifact as _read_replay_artifact,
)
from worldforge.harness.flow_replay_utils import (
    require_exact_keys as _require_exact_keys,
)
from worldforge.harness.flow_replay_utils import (
    require_json_object as _require_json_object,
)
from worldforge.harness.flow_replay_utils import (
    validate_numeric_tensor as _validate_numeric_tensor,
)
from worldforge.harness.groot_replay_payload import groot_replay_raw_actions
from worldforge.models import Action, JSONDict, ProviderEvent, WorldStateError
from worldforge.providers.base import ProviderError

EefRowsReader = Callable[[JSONDict], list[list[float]]]

_GROOT_REPLAY_MODEL = "nvidia/GR00T-N1.7-3B"
_GROOT_REPLAY_RUNTIME = "gr00t-policy-client"
_GROOT_REPLAY_ACTION_HORIZON = 40
_GROOT_REPLAY_SCHEMA_VERSION = 1
_GROOT_REPLAY_EMBODIMENT_TAG = "OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT"
_GROOT_REPLAY_TASK = "fold cloth"
_GROOT_REPLAY_LATENCY_MS = 933.7297500460409
_GROOT_REPLAY_RESULT_DIGEST = (
    "sha256:cccfed332ffc54e1a4ff6afdb17e1e5aae6c73cb433b74cfe3a2e7bed62ac1f5"
)
_GROOT_REPLAY_OBSERVATION_FIELDS = ("language", "state", "video")
_GROOT_REPLAY_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "source",
        "manifest",
        "request",
        "policy_output",
        "response",
        "translated_actions",
        "provider_events",
    }
)
_GROOT_REPLAY_MANIFEST_KEYS = frozenset(
    {
        "flow_id",
        "provider",
        "model",
        "runtime",
        "task_description",
        "action_horizon",
        "embodiment_tag",
        "raw_action_shapes",
        "source_validation",
    }
)
_GROOT_REPLAY_REQUEST_KEYS = frozenset(
    {
        "observation_fields",
        "observation_summary",
        "task_description",
        "action_horizon",
        "embodiment_tag",
    }
)
_GROOT_REPLAY_POLICY_OUTPUT_KEYS = frozenset({"raw_actions", "provider_info"})
_GROOT_REPLAY_PROVIDER_INFO_KEYS = frozenset({"model", "latency_ms", "runtime"})
_GROOT_REPLAY_RESPONSE_KEYS = frozenset(
    {
        "raw_action_shapes",
        "translated_action_count",
        "raw_action_preview",
        "selected_action_preview",
        "latency_ms",
    }
)
_GROOT_REPLAY_RAW_ACTION_SHAPES: JSONDict = {
    "eef_9d": [1, _GROOT_REPLAY_ACTION_HORIZON, 9],
    "gripper_position": [1, _GROOT_REPLAY_ACTION_HORIZON, 1],
    "joint_position": [1, _GROOT_REPLAY_ACTION_HORIZON, 7],
}


@dataclass
class _GrootReplayPolicyClient:
    raw_actions: JSONDict
    provider_info: JSONDict
    get_action_calls: int = 0

    def ping(self) -> bool:
        return True

    def get_action(self, _observation: object, options: object | None = None) -> object:
        self.get_action_calls += 1
        if options not in (None, {}):
            raise ProviderError("GR00T replay does not support policy options.")
        return (
            json.loads(json.dumps(self.raw_actions)),
            json.loads(json.dumps(self.provider_info)),
        )


def run_groot_replay_demo(
    *,
    state_dir: Path,
    emit: bool = False,
    eef_rows: EefRowsReader | None = None,
) -> JSONDict:
    events: list[ProviderEvent] = []
    replay_source_path = _write_prepared_groot_replay_artifact(state_dir)
    saved_replay = load_groot_replay_artifact(replay_source_path)
    policy_info = _groot_policy_info_from_replay(saved_replay)
    policy_output = _require_json_object(saved_replay["policy_output"], "GR00T replay output")
    raw_actions = _require_json_object(policy_output["raw_actions"], "GR00T replay raw actions")
    provider_info = _require_json_object(
        policy_output.get("provider_info", {}),
        "GR00T replay provider_info",
    )
    client = _GrootReplayPolicyClient(raw_actions=raw_actions, provider_info=provider_info)
    provider = _groot_replay_provider(
        client=client,
        event_handler=events.append,
        eef_rows=eef_rows or groot_eef_rows,
    )
    forge = WorldForge(state_dir=state_dir, auto_register_remote=False)
    forge.register_provider(provider)
    health = None
    try:
        health = provider.health()
        result = forge.select_actions("gr00t", info=policy_info)
    except Exception as exc:
        failure_event = ProviderEvent(
            provider="gr00t",
            operation="policy",
            phase="failure",
            message=str(exc),
            metadata={"stage": "harness-replay"},
        )
        if not events or events[-1].message != failure_event.message:
            events.append(failure_event)
        replay_artifact = _groot_failure_replay_artifact(
            saved_replay,
            replay_source_path=replay_source_path,
            events=events,
            error=exc,
        )
        summary = _groot_replay_failure_summary(
            state_dir=state_dir,
            saved_replay=saved_replay,
            replay_source_path=replay_source_path,
            health=health.to_dict() if health is not None else None,
            events=events,
            replay_artifact=replay_artifact,
            error=exc,
            policy_select_calls=client.get_action_calls,
        )
        if emit:
            print("\n".join(_transcript_for("gr00t-replay", summary)))
        return summary

    summary = _groot_replay_success_summary(
        state_dir=state_dir,
        saved_replay=saved_replay,
        replay_source_path=replay_source_path,
        health=health.to_dict(),
        events=events,
        result=result,
        policy_select_calls=client.get_action_calls,
    )
    if emit:
        print("\n".join(_transcript_for("gr00t-replay", summary)))
    return summary


def _groot_replay_provider(
    *,
    client: _GrootReplayPolicyClient,
    event_handler: Callable[[ProviderEvent], None],
    eef_rows: EefRowsReader,
):
    from worldforge.providers import GrootPolicyClientProvider

    return GrootPolicyClientProvider(
        policy_client=client,
        embodiment_tag=_GROOT_REPLAY_EMBODIMENT_TAG,
        action_translator=_groot_action_translator(eef_rows),
        event_handler=event_handler,
    )


def _groot_action_translator(
    eef_rows: EefRowsReader,
) -> Callable[[object, JSONDict, JSONDict], list[Action]]:
    def translate(raw: object, _info: JSONDict, _provider_info: JSONDict) -> list[Action]:
        actions = _require_json_object(raw, "GR00T replay translator raw actions")
        _validate_groot_raw_actions(actions)
        return [
            Action.move_to(float(row[0]), float(row[1]), float(row[2])) for row in eef_rows(actions)
        ]

    return translate


def _groot_replay_success_summary(
    *,
    state_dir: Path,
    saved_replay: JSONDict,
    replay_source_path: Path,
    health: JSONDict,
    events: Sequence[ProviderEvent],
    result: object,
    policy_select_calls: int,
) -> JSONDict:
    metadata = result.metadata
    normalized_raw_actions = _require_json_object(result.raw_actions, "GR00T raw actions")
    raw_action_shapes = _groot_raw_action_shapes(normalized_raw_actions)
    raw_action_preview = _groot_action_preview(normalized_raw_actions)
    selected_action_preview = [action.to_dict() for action in result.actions[:8]]
    replay_artifact = _groot_success_replay_artifact(
        saved_replay=saved_replay,
        replay_source_path=replay_source_path,
        events=events,
        result=result,
        raw_action_shapes=raw_action_shapes,
        raw_action_preview=raw_action_preview,
        selected_action_preview=selected_action_preview,
    )
    return {
        "demo_kind": "gr00t_saved_replay",
        "state_dir": str(state_dir),
        "providers": [result.provider],
        "model": _GROOT_REPLAY_MODEL,
        "task_description": _GROOT_REPLAY_TASK,
        "runtime": metadata.get("runtime"),
        "runtime_contract": "saved PolicyClient replay through GrootPolicyClientProvider",
        "loaded_replay_artifact": replay_source_path.name,
        "health": health,
        "raw_action_shapes": raw_action_shapes,
        "translated_action_count": len(result.actions),
        "action_horizon": result.action_horizon,
        "embodiment_tag": result.embodiment_tag,
        "candidate_count": metadata.get("candidate_count"),
        "policy_select_calls": policy_select_calls,
        "latency_ms": _GROOT_REPLAY_LATENCY_MS,
        "result_digest": _GROOT_REPLAY_RESULT_DIGEST,
        "selected_actions": [action.to_dict() for action in result.actions],
        "selected_action_preview": selected_action_preview,
        "raw_action_preview": raw_action_preview,
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "harness_artifacts": {
            GROOT_REPLAY_ARTIFACT.name: GROOT_REPLAY_ARTIFACT.descriptor(replay_artifact),
        },
    }


def _groot_success_replay_artifact(
    *,
    saved_replay: JSONDict,
    replay_source_path: Path,
    events: Sequence[ProviderEvent],
    result: object,
    raw_action_shapes: JSONDict,
    raw_action_preview: list[list[float]],
    selected_action_preview: list[JSONDict],
) -> JSONDict:
    metadata = result.metadata
    replay_artifact = dict(saved_replay)
    manifest = dict(_require_json_object(saved_replay["manifest"], "GR00T replay manifest"))
    manifest.update(
        {
            "flow_id": "gr00t-replay",
            "provider": result.provider,
            "model": _GROOT_REPLAY_MODEL,
            "runtime": metadata.get("runtime"),
            "task_description": _GROOT_REPLAY_TASK,
            "action_horizon": result.action_horizon,
            "embodiment_tag": result.embodiment_tag,
            "source_artifact": replay_source_path.name,
            "source_validation": "validated live on RTX A6000; committed artifact is sanitized",
            "result_digest": _GROOT_REPLAY_RESULT_DIGEST,
        }
    )
    response = dict(_require_json_object(saved_replay["response"], "GR00T replay response"))
    response.update(
        {
            "raw_action_shapes": raw_action_shapes,
            "translated_action_count": len(result.actions),
            "raw_action_preview": raw_action_preview,
            "selected_action_preview": selected_action_preview,
            "latency_ms": _GROOT_REPLAY_LATENCY_MS,
        }
    )
    replay_artifact.update(
        {
            "manifest": manifest,
            "response": response,
            "translated_actions": [action.to_dict() for action in result.actions],
            "provider_events": [event.to_dict() for event in events],
        }
    )
    return replay_artifact


def _write_prepared_groot_replay_artifact(state_dir: Path) -> Path:
    replay_path = state_dir / "gr00t-prepared-replay.json"
    return write_json_artifact(replay_path, groot_saved_replay_payload())


def groot_saved_replay_payload() -> JSONDict:
    raw_actions = groot_replay_raw_actions(action_horizon=_GROOT_REPLAY_ACTION_HORIZON)
    return {
        "schema_version": _GROOT_REPLAY_SCHEMA_VERSION,
        "source": "sanitized GR00T N1.7 live PolicyClient response shape",
        "manifest": {
            "flow_id": "gr00t-replay",
            "provider": "gr00t",
            "model": _GROOT_REPLAY_MODEL,
            "runtime": "saved replay",
            "task_description": _GROOT_REPLAY_TASK,
            "action_horizon": _GROOT_REPLAY_ACTION_HORIZON,
            "embodiment_tag": _GROOT_REPLAY_EMBODIMENT_TAG,
            "raw_action_shapes": dict(_GROOT_REPLAY_RAW_ACTION_SHAPES),
            "source_validation": "validated live on RTX A6000; committed artifact is sanitized",
        },
        "request": {
            "observation_fields": list(_GROOT_REPLAY_OBSERVATION_FIELDS),
            "observation_summary": _groot_redacted_observation_summary(),
            "task_description": _GROOT_REPLAY_TASK,
            "action_horizon": _GROOT_REPLAY_ACTION_HORIZON,
            "embodiment_tag": _GROOT_REPLAY_EMBODIMENT_TAG,
        },
        "policy_output": {
            "raw_actions": raw_actions,
            "provider_info": {
                "model": _GROOT_REPLAY_MODEL,
                "latency_ms": _GROOT_REPLAY_LATENCY_MS,
                "runtime": "remote PolicyServer replay",
            },
        },
        "response": {
            "raw_action_shapes": dict(_GROOT_REPLAY_RAW_ACTION_SHAPES),
            "translated_action_count": 0,
            "raw_action_preview": [],
            "selected_action_preview": [],
            "latency_ms": _GROOT_REPLAY_LATENCY_MS,
        },
        "translated_actions": [],
        "provider_events": [],
    }


def load_groot_replay_artifact(path: Path) -> JSONDict:
    payload = _read_replay_artifact(path, "GR00T")
    _validate_groot_replay_root(payload)
    _validate_groot_replay_manifest(payload)
    _validate_groot_replay_request(payload)
    _validate_groot_replay_policy_output(payload)
    _validate_groot_replay_response(payload)
    _validate_groot_replay_seed_outputs(payload)
    return payload


def _validate_groot_replay_root(payload: JSONDict) -> None:
    _require_exact_keys(
        payload,
        _GROOT_REPLAY_TOP_LEVEL_KEYS,
        "GR00T replay artifact contains unsupported top-level fields.",
    )
    if payload.get("schema_version") != _GROOT_REPLAY_SCHEMA_VERSION:
        raise WorldStateError("GR00T replay artifact schema_version is unsupported.")
    if not isinstance(payload.get("source"), str) or not payload["source"]:
        raise WorldStateError("GR00T replay artifact source must be a non-empty string.")


def _validate_groot_replay_manifest(payload: JSONDict) -> None:
    manifest = _require_json_object(payload.get("manifest"), "GR00T replay manifest")
    _require_exact_keys(
        manifest,
        _GROOT_REPLAY_MANIFEST_KEYS,
        "GR00T replay manifest contains unsupported fields.",
    )
    if manifest.get("flow_id") != "gr00t-replay":
        raise WorldStateError("GR00T replay artifact flow_id must be 'gr00t-replay'.")
    if manifest.get("provider") != "gr00t":
        raise WorldStateError("GR00T replay artifact provider is unsupported.")
    if manifest.get("model") != _GROOT_REPLAY_MODEL:
        raise WorldStateError("GR00T replay artifact model is unsupported.")
    if manifest.get("action_horizon") != _GROOT_REPLAY_ACTION_HORIZON:
        raise WorldStateError("GR00T replay artifact action_horizon is unsupported.")
    if manifest.get("embodiment_tag") != _GROOT_REPLAY_EMBODIMENT_TAG:
        raise WorldStateError("GR00T replay artifact embodiment_tag is unsupported.")
    if manifest.get("raw_action_shapes") != _GROOT_REPLAY_RAW_ACTION_SHAPES:
        raise WorldStateError("GR00T replay artifact raw_action_shapes are unsupported.")


def _validate_groot_replay_request(payload: JSONDict) -> None:
    request = _require_json_object(payload.get("request"), "GR00T replay request")
    _require_exact_keys(
        request,
        _GROOT_REPLAY_REQUEST_KEYS,
        "GR00T replay request contains unsupported fields.",
    )
    if request.get("observation_fields") != list(_GROOT_REPLAY_OBSERVATION_FIELDS):
        raise WorldStateError("GR00T replay observation fields are unsupported.")
    _validate_groot_observation_summary(request.get("observation_summary"))
    if not isinstance(request.get("task_description"), str) or not request["task_description"]:
        raise WorldStateError("GR00T replay task_description must be a non-empty string.")
    if request.get("action_horizon") != _GROOT_REPLAY_ACTION_HORIZON:
        raise WorldStateError("GR00T replay request action_horizon is unsupported.")
    if request.get("embodiment_tag") != _GROOT_REPLAY_EMBODIMENT_TAG:
        raise WorldStateError("GR00T replay request embodiment_tag is unsupported.")


def _validate_groot_replay_policy_output(payload: JSONDict) -> None:
    policy_output = _require_json_object(payload.get("policy_output"), "GR00T replay output")
    _require_exact_keys(
        policy_output,
        _GROOT_REPLAY_POLICY_OUTPUT_KEYS,
        "GR00T replay policy_output contains unsupported fields.",
    )
    raw_actions = _require_json_object(policy_output.get("raw_actions"), "GR00T replay raw_actions")
    _validate_groot_raw_actions(raw_actions)
    _validate_groot_provider_info(policy_output.get("provider_info", {}))


def _validate_groot_replay_response(payload: JSONDict) -> None:
    response = _require_json_object(payload.get("response"), "GR00T replay response")
    _require_exact_keys(
        response,
        _GROOT_REPLAY_RESPONSE_KEYS,
        "GR00T replay response contains unsupported fields.",
    )
    if response.get("raw_action_shapes") != _GROOT_REPLAY_RAW_ACTION_SHAPES:
        raise WorldStateError("GR00T replay response raw_action_shapes are unsupported.")
    if response.get("translated_action_count") != 0:
        raise WorldStateError("GR00T replay seed response translated_action_count must be zero.")
    if response.get("raw_action_preview") != [] or response.get("selected_action_preview") != []:
        raise WorldStateError("GR00T replay seed response previews must be empty.")
    _validate_groot_latency(response.get("latency_ms"), "GR00T replay response latency_ms")


def _validate_groot_replay_seed_outputs(payload: JSONDict) -> None:
    if payload.get("translated_actions") != []:
        raise WorldStateError("GR00T replay seed translated_actions must be empty.")
    if payload.get("provider_events") != []:
        raise WorldStateError("GR00T replay seed provider_events must be empty.")


def _groot_policy_info_from_replay(replay_artifact: JSONDict) -> JSONDict:
    request = _require_json_object(replay_artifact.get("request"), "GR00T replay request")
    return {
        "observation": {
            "video": {"exterior_image": [[[[[0, 0, 0]]]]]},
            "state": {
                "eef_9d": [[[0.0 for _ in range(9)]]],
                "joint_position": [[[0.0 for _ in range(7)]]],
            },
            "language": {"task": [[request["task_description"]]]},
        },
        "action_horizon": request["action_horizon"],
        "embodiment_tag": request["embodiment_tag"],
    }


def _groot_failure_replay_artifact(
    saved_replay: JSONDict,
    *,
    replay_source_path: Path,
    events: Sequence[ProviderEvent],
    error: Exception,
) -> JSONDict:
    replay_artifact = dict(saved_replay)
    manifest = dict(_require_json_object(saved_replay["manifest"], "GR00T replay manifest"))
    manifest.update(
        {
            "flow_id": "gr00t-replay",
            "status": "failed",
            "source_artifact": replay_source_path.name,
        }
    )
    response = dict(_require_json_object(saved_replay["response"], "GR00T replay response"))
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


def _groot_replay_failure_summary(
    *,
    state_dir: Path,
    saved_replay: JSONDict,
    replay_source_path: Path,
    health: JSONDict | None,
    events: Sequence[ProviderEvent],
    replay_artifact: JSONDict,
    error: Exception,
    policy_select_calls: int,
) -> JSONDict:
    manifest = _require_json_object(saved_replay["manifest"], "GR00T replay manifest")
    request = _require_json_object(saved_replay["request"], "GR00T replay request")
    response = _require_json_object(saved_replay["response"], "GR00T replay response")
    return {
        "demo_kind": "gr00t_saved_replay",
        "status": "failed",
        "state_dir": str(state_dir),
        "providers": ["gr00t"],
        "model": manifest.get("model"),
        "task_description": request.get("task_description"),
        "runtime": manifest.get("runtime"),
        "runtime_contract": "saved PolicyClient replay through GrootPolicyClientProvider",
        "loaded_replay_artifact": replay_source_path.name,
        "health": health or {"healthy": False, "message": "not checked"},
        "raw_action_shapes": response.get("raw_action_shapes", {}),
        "translated_action_count": 0,
        "action_horizon": request.get("action_horizon"),
        "embodiment_tag": request.get("embodiment_tag"),
        "candidate_count": 0,
        "policy_select_calls": policy_select_calls,
        "latency_ms": response.get("latency_ms"),
        "selected_actions": [],
        "selected_action_preview": [],
        "raw_action_preview": [],
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "validation_errors": [str(error)],
        "harness_artifacts": {
            GROOT_REPLAY_ARTIFACT.name: GROOT_REPLAY_ARTIFACT.descriptor(replay_artifact),
        },
    }


def _validate_groot_raw_actions(raw_actions: JSONDict) -> None:
    if set(raw_actions) != set(_GROOT_REPLAY_RAW_ACTION_SHAPES):
        raise WorldStateError("GR00T replay raw_actions contain unsupported fields.")
    for key, expected_shape in _GROOT_REPLAY_RAW_ACTION_SHAPES.items():
        _validate_numeric_tensor(
            raw_actions.get(key),
            expected_shape=expected_shape,
            name=f"GR00T replay raw_actions.{key}",
        )


def _validate_groot_provider_info(value: object) -> JSONDict:
    provider_info = _require_json_object(value, "GR00T replay provider_info")
    if set(provider_info) != _GROOT_REPLAY_PROVIDER_INFO_KEYS:
        raise WorldStateError("GR00T replay provider_info contains unsupported fields.")
    if provider_info.get("model") != _GROOT_REPLAY_MODEL:
        raise WorldStateError("GR00T replay provider_info model is unsupported.")
    _validate_groot_latency(
        provider_info.get("latency_ms"),
        "GR00T replay provider_info latency_ms",
    )
    if not isinstance(provider_info.get("runtime"), str) or not provider_info["runtime"]:
        raise WorldStateError("GR00T replay provider_info runtime must be a non-empty string.")
    return provider_info


def _validate_groot_latency(value: object, name: str) -> None:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise WorldStateError(f"{name} must be a finite number.")


def _groot_raw_action_shapes(raw_actions: JSONDict) -> JSONDict:
    _validate_groot_raw_actions(raw_actions)
    return dict(_GROOT_REPLAY_RAW_ACTION_SHAPES)


def groot_eef_rows(raw_actions: JSONDict) -> list[list[float]]:
    eef = raw_actions["eef_9d"]
    if not isinstance(eef, list) or not eef or not isinstance(eef[0], list):
        raise WorldStateError("GR00T replay eef_9d must contain one batch of action rows.")
    rows = eef[0]
    if not all(isinstance(row, list) for row in rows):
        raise WorldStateError("GR00T replay eef_9d rows must be lists.")
    return rows


def _groot_action_preview(raw_actions: JSONDict, *, limit: int = 8) -> list[list[float]]:
    _validate_groot_raw_actions(raw_actions)
    eef_rows = groot_eef_rows(raw_actions)
    gripper_rows = raw_actions["gripper_position"][0]
    joint_rows = raw_actions["joint_position"][0]
    preview: list[list[float]] = []
    for index, eef_row in enumerate(eef_rows[:limit]):
        gripper = gripper_rows[index][0]
        joints = joint_rows[index]
        preview.append(
            [
                round(float(eef_row[0]), 5),
                round(float(eef_row[1]), 5),
                round(float(eef_row[2]), 5),
                round(float(gripper), 5),
                round(float(joints[0]), 5),
                round(float(joints[1]), 5),
            ]
        )
    return preview


def _validate_groot_observation_summary(value: object) -> None:
    observation_summary = _require_json_object(value, "GR00T replay observation_summary")
    if set(observation_summary) != set(_GROOT_REPLAY_OBSERVATION_FIELDS):
        raise WorldStateError("GR00T replay observation_summary contains unsupported fields.")
    expected_shapes = {
        "video": {"exterior_image": [1, 1, 1, 1, 3]},
        "state": {"eef_9d": [1, 1, 9], "joint_position": [1, 1, 7]},
        "language": {"task": [1, 1]},
    }
    for field in _GROOT_REPLAY_OBSERVATION_FIELDS:
        field_summary = _require_json_object(
            observation_summary.get(field),
            f"GR00T replay observation_summary.{field}",
        )
        if set(field_summary) != {"redacted", "shape"}:
            raise WorldStateError(
                f"GR00T replay observation_summary.{field} contains unsupported fields."
            )
        if field_summary.get("redacted") is not True:
            raise WorldStateError(f"GR00T replay observation field {field} must be redacted.")
        if field_summary.get("shape") != expected_shapes[field]:
            raise WorldStateError(f"GR00T replay observation_summary.{field}.shape is unsupported.")


def _groot_redacted_observation_summary() -> JSONDict:
    return {
        "video": {"redacted": True, "shape": {"exterior_image": [1, 1, 1, 1, 3]}},
        "state": {
            "redacted": True,
            "shape": {"eef_9d": [1, 1, 9], "joint_position": [1, 1, 7]},
        },
        "language": {"redacted": True, "shape": {"task": [1, 1]}},
    }
