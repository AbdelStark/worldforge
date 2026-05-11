"""Flow definitions and runners for TheWorldHarness."""

from __future__ import annotations

import base64
import binascii
import json
import math
import struct
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from worldforge.benchmark import BenchmarkReport, BenchmarkResult, ProviderBenchmarkHarness
from worldforge.evaluation import EvaluationReport, EvaluationResult, EvaluationSuite
from worldforge.framework import WorldForge
from worldforge.harness.models import HarnessFlow, HarnessMetric, HarnessRun, HarnessStep
from worldforge.harness.workspace import (
    RunWorkspace,
    create_run_workspace,
    workspace_root_for_state_dir,
    write_run_manifest,
)
from worldforge.models import JSONDict, ProviderEvent, WorldForgeError, WorldStateError
from worldforge.provenance import ProvenanceEnvelope
from worldforge.providers.base import ProviderError

FlowRunner = Callable[..., JSONDict]

FLOWS: tuple[HarnessFlow, ...] = (
    HarnessFlow(
        id="leworldmodel",
        title="LeWorldModel Score Planning",
        short_title="LeWorldModel",
        focus="score planning",
        provider="LeWorldModelProvider",
        capability="score",
        command="uv run worldforge-demo-leworldmodel",
        accent="#d8c46a",
        summary=(
            "Inject a deterministic LeWorldModel-shaped cost runtime, score three action "
            "candidates, execute the selected plan, and verify persisted world state."
        ),
    ),
    HarnessFlow(
        id="lerobot",
        title="LeRobot Policy + Score Planning",
        short_title="LeRobot",
        focus="policy plus score planning",
        provider="LeRobotPolicyProvider",
        capability="policy",
        command="uv run worldforge-demo-lerobot",
        accent="#8ec5a3",
        summary=(
            "Inject a deterministic LeRobot-shaped policy, translate raw action chunks, rank "
            "them with a score provider, execute, persist, and reload the resulting world."
        ),
    ),
    HarnessFlow(
        id="cosmos-policy",
        title="Cosmos-Policy ALOHA Replay",
        short_title="Cosmos",
        focus="saved ALOHA /act replay",
        provider="CosmosPolicyProvider",
        capability="policy",
        command="uv run --extra harness worldforge-harness --flow cosmos-policy",
        accent="#74d7f7",
        summary=(
            "Replay a sanitized NVIDIA Cosmos-Policy ALOHA /act response through the real "
            "provider boundary, decode 50 x 14 json_numpy actions, translate them, and preserve "
            "an inspectable run artifact without requiring a live GPU."
        ),
    ),
    HarnessFlow(
        id="gr00t",
        title="GR00T Policy Replay",
        short_title="GR00T",
        focus="saved PolicyClient replay",
        provider="GrootPolicyClientProvider",
        capability="policy",
        command="uv run --extra harness worldforge-harness --flow gr00t",
        accent="#b9a7ff",
        summary=(
            "Replay a sanitized NVIDIA Isaac GR00T PolicyClient action response through the "
            "real provider boundary, validate named tensors, translate the policy output, and "
            "preserve an inspectable artifact without requiring a live CUDA server."
        ),
    ),
    HarnessFlow(
        id="diagnostics",
        title="Provider Diagnostics + Benchmark",
        short_title="Diagnostics",
        focus="provider diagnostics and benchmark comparison",
        provider="WorldForge + ProviderBenchmarkHarness",
        capability="diagnostics",
        command="uv run worldforge harness --flow diagnostics",
        accent="#91b7ff",
        summary=(
            "Inspect the provider catalog, surface registered and unavailable adapters, run the "
            "mock provider benchmark matrix, and compare latency, throughput, and emitted events."
        ),
    ),
    HarnessFlow(
        id="workbench",
        title="Adapter Author Workbench",
        short_title="Workbench",
        focus="adapter authoring evidence",
        provider="Provider workbench",
        capability="authoring",
        command="uv run worldforge provider workbench mock",
        accent="#f0a35e",
        summary=(
            "Run the checkout-safe provider workbench against the stable mock provider and the "
            "direct-construction jepa-wms candidate, then collect promotion evidence, safe "
            "artifact references, and validation commands."
        ),
    ),
)

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
_FLOW_ARTIFACT_RESERVED_NAMES = frozenset(
    {"summary", "steps", "metrics", "transcript", "inspector"}
)
_COSMOS_POLICY_PREVIEW_ROWS = (
    (0.01227, -0.02509, -0.00844, -0.04266, 0.05760, 0.01356),
    (0.00180, -0.02080, -0.01734, -0.03035, 0.05673, 0.00983),
    (0.01250, -0.02521, -0.00710, -0.04928, 0.05478, 0.01556),
    (0.00418, -0.02012, -0.01506, -0.03610, 0.06206, 0.01546),
    (0.01023, -0.02691, -0.01081, -0.05677, 0.06027, 0.01551),
    (0.00377, -0.02269, -0.01370, -0.04925, 0.06735, 0.01213),
)
_GROOT_REPLAY_SCHEMA_VERSION = 1
_GROOT_MODEL = "nvidia/GR00T-N1.7-3B"
_GROOT_EMBODIMENT_TAG = "GR1"
_GROOT_ACTION_HORIZON = 4
_GROOT_TENSOR_DIMS = {
    "eef_9d": 9,
    "gripper_position": 1,
    "joint_position": 7,
}
_GROOT_REQUIRED_TENSORS = tuple(_GROOT_TENSOR_DIMS)
_GROOT_REPLAY_REQUEST_KEYS = frozenset(
    {
        "observation_summary",
        "task_instruction",
        "action_horizon",
        "embodiment_tag",
    }
)
_GROOT_EEF_9D_ROWS = (
    (0.18, 0.46, 0.22, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    (0.24, 0.47, 0.20, 1.0, 0.0, 0.0, 0.0, 0.98, 0.02),
    (0.31, 0.48, 0.18, 0.99, 0.01, 0.0, 0.0, 0.96, 0.04),
    (0.38, 0.50, 0.16, 0.98, 0.02, 0.0, 0.0, 0.94, 0.06),
)
_GROOT_GRIPPER_POSITION_ROWS = (
    (0.045,),
    (0.038,),
    (0.030,),
    (0.022,),
)
_GROOT_JOINT_POSITION_ROWS = (
    (0.12, -0.41, 0.05, -1.82, 0.04, 1.41, 0.28),
    (0.14, -0.39, 0.04, -1.79, 0.05, 1.38, 0.26),
    (0.16, -0.36, 0.03, -1.75, 0.06, 1.35, 0.24),
    (0.18, -0.34, 0.02, -1.71, 0.07, 1.31, 0.21),
)


def _run_diagnostics_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    forge = WorldForge(state_dir=state_dir, auto_register_remote=False)
    doctor = forge.doctor(registered_only=False)
    registered_doctor = forge.doctor(registered_only=True)
    benchmark = ProviderBenchmarkHarness(forge=forge)
    operations = benchmark.supported_operations("mock")
    report = benchmark.run(
        "mock",
        operations=operations,
        iterations=2,
        concurrency=1,
    )
    benchmark_results = report.to_dict()["results"]
    fastest = min(
        benchmark_results,
        key=lambda result: float(result.get("average_latency_ms") or 0.0),
    )
    highest_throughput = max(
        benchmark_results,
        key=lambda result: float(result.get("throughput_per_second") or 0.0),
    )
    event_count = sum(
        int(event["request_count"])
        for result in benchmark_results
        for event in result["operation_metrics"]["events"]
    )
    summary = {
        "demo_kind": "provider_diagnostics_benchmark",
        "state_dir": str(state_dir),
        "registered_providers": forge.providers(),
        "known_provider_count": doctor.provider_count,
        "healthy_provider_count": doctor.healthy_provider_count,
        "registered_provider_count": registered_doctor.registered_provider_count,
        "issue_count": len(doctor.issues),
        "issues": list(doctor.issues),
        "mock_supported_operations": operations,
        "benchmark_iterations": 2,
        "benchmark_concurrency": 1,
        "benchmark_results": benchmark_results,
        "benchmark_operation_count": len(benchmark_results),
        "fastest_operation": str(fastest["operation"]),
        "fastest_average_latency_ms": float(fastest["average_latency_ms"] or 0.0),
        "highest_throughput_operation": str(highest_throughput["operation"]),
        "highest_throughput_per_second": float(highest_throughput["throughput_per_second"]),
        "benchmark_event_count": event_count,
        "commands": [
            "uv run worldforge doctor",
            "uv run worldforge provider list",
            "uv run worldforge benchmark --provider mock --iterations 2 --format json",
        ],
    }
    if emit:
        print(report.to_markdown())
    return summary


def _run_workbench_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    from worldforge.harness.workbench import (
        provider_workbench_markdown,
        provider_workbench_report,
    )

    reports = [
        provider_workbench_report("mock", docs_root=Path.cwd()),
        provider_workbench_report("jepa-wms", docs_root=Path.cwd()),
    ]
    providers = [str(report["provider"]) for report in reports]
    passed = sum(1 for report in reports if report.get("status") == "passed")
    safe_artifacts = [
        artifact
        for report in reports
        for artifact in report.get("safe_artifacts", [])
        if isinstance(artifact, dict)
    ]
    validation_commands = sorted(
        {str(command) for report in reports for command in report.get("validation_commands", [])}
    )
    missing_by_provider = {
        str(report["provider"]): report["promotion"]["missing_evidence_by_status"]
        for report in reports
    }
    summary: JSONDict = {
        "demo_kind": "provider_workbench",
        "state_dir": str(state_dir),
        "providers": providers,
        "report_count": len(reports),
        "passed_count": passed,
        "failed_count": len(reports) - passed,
        "reports": reports,
        "safe_artifact_count": len(safe_artifacts),
        "safe_artifacts": safe_artifacts,
        "validation_commands": validation_commands,
        "missing_evidence_by_provider": missing_by_provider,
        "provider_events": [],
    }
    if emit:
        print("\n\n".join(provider_workbench_markdown(report) for report in reports))
    return summary


def _run_cosmos_policy_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    import httpx

    from worldforge.models import Action
    from worldforge.providers import CosmosPolicyProvider

    events: list[ProviderEvent] = []
    request_count = 0
    replay_source_path = _write_prepared_cosmos_policy_replay_artifact(state_dir)
    saved_replay = _load_cosmos_policy_replay_artifact(replay_source_path)
    saved_request = _require_json_object(saved_replay["request"], "Cosmos-Policy replay request")
    policy_info = _cosmos_policy_policy_info_from_replay(saved_replay)
    policy_output = _cosmos_policy_response_payload(saved_replay)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        try:
            payload = json.loads(request.content.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WorldStateError("Cosmos-Policy replay request body must be JSON.") from exc
        if request.method != "POST":
            raise WorldStateError(f"Cosmos-Policy replay expected POST, got {request.method}.")
        if request.url.path != "/act":
            raise WorldStateError(f"Cosmos-Policy replay expected /act, got {request.url.path}.")
        _validate_cosmos_policy_replay_request(payload, saved_request)
        return httpx.Response(200, json=policy_output)

    def translator(raw_actions: object, _info: JSONDict, _provider_info: JSONDict):
        if not isinstance(raw_actions, dict):
            raise ProviderError("Cosmos-Policy replay translator expected raw action metadata.")
        matrix = raw_actions.get("actions")
        if not isinstance(matrix, list):
            raise ProviderError("Cosmos-Policy replay translator expected action rows.")
        actions: list[Action] = []
        for index, row in enumerate(matrix):
            if not isinstance(row, list):
                raise ProviderError(f"Cosmos-Policy replay action row {index} must be a list.")
            if len(row) != _COSMOS_POLICY_ACTION_DIM:
                raise ProviderError(
                    f"Cosmos-Policy replay action row {index} must be {_COSMOS_POLICY_ACTION_DIM}D."
                )
            actions.append(Action.move_to(float(row[0]), float(row[1]), float(row[2])))
        return actions

    provider = CosmosPolicyProvider(
        base_url=_COSMOS_POLICY_REPLAY_BASE_URL,
        model=_COSMOS_POLICY_MODEL,
        return_all_query_results=False,
        allowed_hosts=("93.184.216.34",),
        transport=httpx.MockTransport(handler),
        action_translator=translator,
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
            request_count=request_count,
            events=events,
            replay_artifact=replay_artifact,
            error=exc,
        )
        if emit:
            print("\n".join(_transcript_for("cosmos-policy", summary)))
        return summary
    metadata = result.metadata
    provider_info = metadata.get("provider_info", {})
    raw_action_summary = metadata.get("raw_action_summary", {})
    raw_actions = result.raw_actions.get("actions", [])
    raw_action_shape = list(raw_action_summary.get("actions_shape", []))
    selected_action_preview = [action.to_dict() for action in result.actions[:6]]
    raw_action_preview = _preview_action_rows(raw_actions)
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
    summary: JSONDict = {
        "demo_kind": "cosmos_policy_saved_replay",
        "state_dir": str(state_dir),
        "providers": [result.provider],
        "model": metadata.get("model"),
        "task_description": metadata.get("task_description"),
        "runtime": metadata.get("runtime"),
        "server_path": metadata.get("server_path"),
        "runtime_contract": "saved /act replay through CosmosPolicyProvider",
        "loaded_replay_artifact": replay_source_path.name,
        "health": health.to_dict(),
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
            "cosmos_policy_replay": {
                "path": "artifacts/cosmos-policy-replay.json",
                "payload": replay_artifact,
            },
        },
    }
    if emit:
        print("\n".join(_transcript_for("cosmos-policy", summary)))
    return summary


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
    state_dir.mkdir(parents=True, exist_ok=True)
    replay_path = state_dir / "cosmos-policy-prepared-replay.json"
    replay_path.write_text(
        json.dumps(_cosmos_policy_saved_replay_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return replay_path


def _cosmos_policy_saved_replay_payload() -> JSONDict:
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


def _load_cosmos_policy_replay_artifact(path: Path) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorldStateError(f"Cosmos-Policy replay artifact is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise WorldStateError("Cosmos-Policy replay artifact must be a JSON object.")
    if payload.get("schema_version") != _COSMOS_POLICY_REPLAY_SCHEMA_VERSION:
        raise WorldStateError("Cosmos-Policy replay artifact schema_version is unsupported.")

    manifest = _require_json_object(payload.get("manifest"), "Cosmos-Policy replay manifest")
    if manifest.get("flow_id") != "cosmos-policy":
        raise WorldStateError("Cosmos-Policy replay artifact flow_id must be 'cosmos-policy'.")
    if manifest.get("server_path") != "/act":
        raise WorldStateError("Cosmos-Policy replay artifact server_path must be '/act'.")
    if manifest.get("action_horizon") != _COSMOS_POLICY_ACTION_HORIZON:
        raise WorldStateError("Cosmos-Policy replay artifact action_horizon is unsupported.")
    if manifest.get("action_dim") != _COSMOS_POLICY_ACTION_DIM:
        raise WorldStateError("Cosmos-Policy replay artifact action_dim is unsupported.")

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
        try:
            value_prediction_float = float(value_prediction)
        except (TypeError, ValueError) as exc:
            raise WorldStateError(
                "Cosmos-Policy replay value_prediction must be numeric when present."
            ) from exc
        if not math.isfinite(value_prediction_float):
            raise WorldStateError(
                "Cosmos-Policy replay value_prediction must be finite when present."
            )
    return payload


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
            "cosmos_policy_replay": {
                "path": "artifacts/cosmos-policy-replay.json",
                "payload": replay_artifact,
            },
        },
    }


def _validate_cosmos_policy_replay_request(payload: object, saved_request: JSONDict) -> None:
    if not isinstance(payload, dict):
        raise WorldStateError("Cosmos-Policy replay request payload must be a JSON object.")
    _require_json_native_value(payload, "Cosmos-Policy replay request payload")
    expected_fields_value = saved_request.get("observation_fields")
    if not isinstance(expected_fields_value, list) or not all(
        isinstance(field, str) for field in expected_fields_value
    ):
        raise WorldStateError("Cosmos-Policy replay saved observation fields are invalid.")
    expected_fields = sorted(expected_fields_value)
    if expected_fields != expected_fields_value:
        raise WorldStateError("Cosmos-Policy replay saved observation fields are invalid.")
    expected_payload_keys = set(expected_fields) | {"task_description", "action_horizon"}
    payload_keys = set(payload)
    if "return_all_query_results" in payload:
        if not isinstance(payload["return_all_query_results"], bool):
            raise WorldStateError(
                "Cosmos-Policy replay request return_all_query_results must be boolean."
            )
        payload_keys.remove("return_all_query_results")
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
    if payload.get("task_description") != saved_request["task_description"]:
        raise WorldStateError("Cosmos-Policy replay request task_description drifted.")
    if payload.get("action_horizon") != saved_request["action_horizon"]:
        raise WorldStateError("Cosmos-Policy replay request action_horizon drifted.")
    proprio = payload.get("proprio")
    if not isinstance(proprio, list) or len(proprio) != saved_request["proprio_dim"]:
        raise WorldStateError("Cosmos-Policy replay request proprio shape drifted.")
    for index, value in enumerate(proprio):
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise WorldStateError(
                f"Cosmos-Policy replay request proprio[{index}] must be finite numeric."
            )


def _cosmos_policy_policy_info_from_replay(replay_artifact: JSONDict) -> JSONDict:
    request = _require_json_object(
        replay_artifact.get("request"),
        "Cosmos-Policy replay request",
    )
    policy_info = _cosmos_policy_policy_info()
    policy_info["task_description"] = request["task_description"]
    policy_info["action_horizon"] = request["action_horizon"]
    policy_info["embodiment_tag"] = request["embodiment_tag"]
    return policy_info


def _cosmos_policy_response_payload(replay_artifact: JSONDict) -> JSONDict:
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


def _require_json_object(value: object, name: str) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldStateError(f"{name} must be a JSON object.")
    return value


def _require_json_native_value(value: object, name: str) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int | float):
        if isinstance(value, bool) or not math.isfinite(value):
            raise WorldStateError(f"{name} must be JSON-native and finite.")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_json_native_value(item, f"{name}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise WorldStateError(f"{name} keys must be strings.")
            _require_json_native_value(item, f"{name}.{key}")
        return
    raise WorldStateError(f"{name} must be JSON-native.")


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
    raw = struct.pack(f"<{_COSMOS_POLICY_ACTION_DIM}f", *row)
    return {
        "__numpy__": base64.b64encode(raw).decode("ascii"),
        "dtype": "<f4",
        "shape": [_COSMOS_POLICY_ACTION_DIM],
    }


def _decode_json_numpy_action_row(value: object, *, row_index: int) -> list[float]:
    if not isinstance(value, dict):
        raise WorldStateError(f"Cosmos-Policy replay action row {row_index} must be JSON numpy.")
    encoded = value.get("__numpy__")
    if not isinstance(encoded, str) or not encoded:
        raise WorldStateError(f"Cosmos-Policy replay action row {row_index} is missing __numpy__.")
    dtype = value.get("dtype")
    if not isinstance(dtype, str) or not dtype:
        raise WorldStateError(
            f"Cosmos-Policy replay action row {row_index} must include a numeric dtype."
        )
    endian_prefix, item_format, item_size = _json_numpy_float_format_for_replay(
        dtype,
        row_index=row_index,
    )
    if value.get("shape") != [_COSMOS_POLICY_ACTION_DIM]:
        raise WorldStateError(
            f"Cosmos-Policy replay action row {row_index} must have shape "
            f"[{_COSMOS_POLICY_ACTION_DIM}]."
        )
    expected_bytes = _COSMOS_POLICY_ACTION_DIM * item_size
    expected_encoded_length = 4 * math.ceil(expected_bytes / 3)
    if len(encoded) > expected_encoded_length:
        raise WorldStateError(
            f"Cosmos-Policy replay action row {row_index} base64 payload is too large."
        )
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise WorldStateError(
            f"Cosmos-Policy replay action row {row_index} has invalid base64."
        ) from exc
    if len(raw) != expected_bytes:
        raise WorldStateError(
            f"Cosmos-Policy replay action row {row_index} must contain {expected_bytes} bytes."
        )
    decoded = list(struct.unpack(f"{endian_prefix}{_COSMOS_POLICY_ACTION_DIM}{item_format}", raw))
    if not all(math.isfinite(value) for value in decoded):
        raise WorldStateError(f"Cosmos-Policy replay action row {row_index} must be finite.")
    return decoded


def _json_numpy_float_format_for_replay(
    dtype: str,
    *,
    row_index: int,
) -> tuple[str, str, int]:
    normalized = dtype.strip().lower()
    if not normalized:
        raise WorldStateError(
            f"Cosmos-Policy replay action row {row_index} must include a numeric dtype."
        )
    endian_prefix = "<"
    if normalized[0] in ("<", ">", "=", "|"):
        endian_prefix = "=" if normalized[0] == "|" else normalized[0]
        normalized = normalized[1:]
    if normalized in ("f4", "float32"):
        return endian_prefix, "f", 4
    if normalized in ("f8", "float64"):
        return endian_prefix, "d", 8
    raise WorldStateError(
        f"Cosmos-Policy replay action row {row_index} dtype must be float32 or float64."
    )


def _preview_action_rows(rows: object, *, limit: int = 6, columns: int = 6) -> list[list[float]]:
    if not isinstance(rows, list):
        return []
    preview: list[list[float]] = []
    for row in rows[:limit]:
        if not isinstance(row, list):
            continue
        preview.append([round(float(value), 5) for value in row[:columns]])
    return preview


class _SavedGrootReplayClient:
    """PolicyClient-shaped object that replays a sanitized GR00T response."""

    def __init__(self, replay_artifact: JSONDict) -> None:
        self.replay_artifact = replay_artifact
        self.ping_calls = 0
        self.get_action_calls = 0

    def ping(self) -> bool:
        self.ping_calls += 1
        return True

    def get_action(self, observation: object, options: object | None = None) -> object:
        self.get_action_calls += 1
        request = _require_json_object(
            self.replay_artifact.get("request"),
            "GR00T replay request",
        )
        _validate_gr00t_replay_observation(observation, request)
        if options is not None:
            _require_json_native_value(options, "GR00T replay options")
        policy_output = _require_json_object(
            self.replay_artifact.get("policy_output"),
            "GR00T replay policy_output",
        )
        return policy_output["raw_actions"], dict(
            _require_json_object(policy_output.get("provider_info"), "GR00T provider_info")
        )


def _run_gr00t_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    from worldforge.models import Action
    from worldforge.providers import GrootPolicyClientProvider

    events: list[ProviderEvent] = []
    replay_source_path = _write_prepared_gr00t_replay_artifact(state_dir)
    saved_replay = _load_gr00t_replay_artifact(replay_source_path)
    policy_info = _gr00t_policy_info_from_replay(saved_replay)
    replay_client = _SavedGrootReplayClient(saved_replay)

    def translator(raw_actions: object, _info: JSONDict, _provider_info: JSONDict):
        tensor_rows = _validate_gr00t_raw_actions(raw_actions)
        return [
            Action.move_to(float(row[0]), float(row[1]), float(row[2]))
            for row in tensor_rows["eef_9d"]
        ]

    provider = GrootPolicyClientProvider(
        policy_client=replay_client,
        embodiment_tag=str(policy_info["embodiment_tag"]),
        action_translator=translator,
        event_handler=events.append,
    )
    forge = WorldForge(state_dir=state_dir, auto_register_remote=False)
    forge.register_provider(provider)
    health = provider.health()
    result = forge.select_actions("gr00t", info=policy_info)

    raw_tensor_shapes = _gr00t_tensor_shapes(result.raw_actions)
    selected_action_preview = [action.to_dict() for action in result.actions]
    replay_artifact = dict(saved_replay)
    replay_artifact.update(
        {
            "manifest": {
                **dict(_require_json_object(saved_replay["manifest"], "GR00T replay manifest")),
                "source_artifact": replay_source_path.name,
            },
            "response": {
                "raw_tensor_shapes": raw_tensor_shapes,
                "validated_tensors": list(_GROOT_REQUIRED_TENSORS),
                "translated_action_count": len(result.actions),
                "selected_action_preview": selected_action_preview,
                "provider_info": result.metadata.get("provider_info", {}),
            },
            "translated_actions": selected_action_preview,
            "provider_events": [event.to_dict() for event in events],
        }
    )
    summary: JSONDict = {
        "demo_kind": "gr00t_saved_policy_replay",
        "state_dir": str(state_dir),
        "providers": [result.provider],
        "model": _GROOT_MODEL,
        "task_instruction": policy_info["observation"]["language"]["task"][0][0],
        "runtime": "saved PolicyClient replay",
        "runtime_contract": "saved GR00T PolicyClient response through GrootPolicyClientProvider",
        "live_validation_boundary": (
            "A prepared GPU host validates the GR00T server shape; this harness flow replays only "
            "the sanitized policy output contract."
        ),
        "loaded_replay_artifact": replay_source_path.name,
        "health": health.to_dict(),
        "policy_client_calls": replay_client.get_action_calls,
        "raw_tensor_shapes": raw_tensor_shapes,
        "validated_tensors": list(_GROOT_REQUIRED_TENSORS),
        "translated_action_count": len(result.actions),
        "action_horizon": result.action_horizon,
        "embodiment_tag": result.embodiment_tag,
        "candidate_count": result.metadata.get("candidate_count"),
        "selected_actions": selected_action_preview,
        "selected_action_preview": selected_action_preview,
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "harness_artifacts": {
            "gr00t_policy_replay": {
                "path": "artifacts/gr00t-policy-replay.json",
                "payload": replay_artifact,
            },
        },
    }
    if emit:
        print("\n".join(_transcript_for("gr00t", summary)))
    return summary


def _write_prepared_gr00t_replay_artifact(state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    replay_path = state_dir / "gr00t-prepared-replay.json"
    replay_path.write_text(
        json.dumps(_gr00t_saved_replay_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return replay_path


def _gr00t_saved_replay_payload() -> JSONDict:
    raw_actions = {
        "eef_9d": [_rows_to_lists(_GROOT_EEF_9D_ROWS)],
        "gripper_position": [_rows_to_lists(_GROOT_GRIPPER_POSITION_ROWS)],
        "joint_position": [_rows_to_lists(_GROOT_JOINT_POSITION_ROWS)],
    }
    return {
        "schema_version": _GROOT_REPLAY_SCHEMA_VERSION,
        "source": "sanitized GR00T live PolicyClient response shape",
        "manifest": {
            "flow_id": "gr00t",
            "provider": "gr00t",
            "model": _GROOT_MODEL,
            "runtime": "saved PolicyClient replay",
            "embodiment_tag": _GROOT_EMBODIMENT_TAG,
            "action_horizon": _GROOT_ACTION_HORIZON,
            "tensor_shapes": {
                name: [1, _GROOT_ACTION_HORIZON, dim] for name, dim in _GROOT_TENSOR_DIMS.items()
            },
            "live_validation": (
                "GR00T server shape validated on a prepared GPU host; replay is checkout-safe."
            ),
        },
        "request": {
            "observation_summary": _gr00t_redacted_observation_summary(),
            "task_instruction": "move the end effector toward the cube and close the gripper",
            "action_horizon": _GROOT_ACTION_HORIZON,
            "embodiment_tag": _GROOT_EMBODIMENT_TAG,
        },
        "policy_output": {
            "raw_actions": raw_actions,
            "provider_info": {
                "model": _GROOT_MODEL,
                "runtime": "saved PolicyClient replay",
                "latency_ms": 18.4,
                "server": "redacted",
            },
        },
        "response": {
            "raw_tensor_shapes": {
                name: [1, _GROOT_ACTION_HORIZON, dim] for name, dim in _GROOT_TENSOR_DIMS.items()
            },
            "validated_tensors": [],
            "translated_action_count": 0,
            "selected_action_preview": [],
        },
        "translated_actions": [],
        "provider_events": [],
    }


def _load_gr00t_replay_artifact(path: Path) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorldStateError(f"GR00T replay artifact is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise WorldStateError("GR00T replay artifact must be a JSON object.")
    if payload.get("schema_version") != _GROOT_REPLAY_SCHEMA_VERSION:
        raise WorldStateError("GR00T replay artifact schema_version is unsupported.")

    manifest = _require_json_object(payload.get("manifest"), "GR00T replay manifest")
    if manifest.get("flow_id") != "gr00t":
        raise WorldStateError("GR00T replay artifact flow_id must be 'gr00t'.")
    if manifest.get("provider") != "gr00t":
        raise WorldStateError("GR00T replay artifact provider must be 'gr00t'.")
    if manifest.get("action_horizon") != _GROOT_ACTION_HORIZON:
        raise WorldStateError("GR00T replay artifact action_horizon is unsupported.")
    if manifest.get("embodiment_tag") != _GROOT_EMBODIMENT_TAG:
        raise WorldStateError("GR00T replay artifact embodiment_tag is unsupported.")
    tensor_shapes = _require_json_object(
        manifest.get("tensor_shapes"),
        "GR00T replay tensor_shapes",
    )
    expected_shapes = {
        name: [1, _GROOT_ACTION_HORIZON, dim] for name, dim in _GROOT_TENSOR_DIMS.items()
    }
    if tensor_shapes != expected_shapes:
        raise WorldStateError("GR00T replay artifact tensor_shapes drifted.")

    request = _require_json_object(payload.get("request"), "GR00T replay request")
    if set(request) != _GROOT_REPLAY_REQUEST_KEYS:
        raise WorldStateError("GR00T replay request contains unsupported fields.")
    _validate_gr00t_observation_summary(request.get("observation_summary"))
    if not isinstance(request.get("task_instruction"), str) or not request["task_instruction"]:
        raise WorldStateError("GR00T replay task_instruction must be a non-empty string.")
    if request.get("action_horizon") != _GROOT_ACTION_HORIZON:
        raise WorldStateError("GR00T replay request action_horizon is unsupported.")
    if request.get("embodiment_tag") != _GROOT_EMBODIMENT_TAG:
        raise WorldStateError("GR00T replay request embodiment_tag is unsupported.")

    policy_output = _require_json_object(payload.get("policy_output"), "GR00T replay policy_output")
    _validate_gr00t_raw_actions(policy_output.get("raw_actions"))
    provider_info = _require_json_object(
        policy_output.get("provider_info"),
        "GR00T replay provider_info",
    )
    _require_json_native_value(provider_info, "GR00T replay provider_info")
    return payload


def _gr00t_policy_info_from_replay(replay_artifact: JSONDict) -> JSONDict:
    request = _require_json_object(replay_artifact.get("request"), "GR00T replay request")
    return {
        "observation": {
            "video": {"front": [[[[[0, 0, 0]]]]]},
            "state": {
                "eef_9d": [[[0.0 for _ in range(_GROOT_TENSOR_DIMS["eef_9d"])]]],
                "gripper_position": [
                    [[0.0 for _ in range(_GROOT_TENSOR_DIMS["gripper_position"])]]
                ],
                "joint_position": [[[0.0 for _ in range(_GROOT_TENSOR_DIMS["joint_position"])]]],
            },
            "language": {"task": [[request["task_instruction"]]]},
        },
        "embodiment_tag": request["embodiment_tag"],
        "action_horizon": request["action_horizon"],
    }


def _validate_gr00t_replay_observation(observation: object, saved_request: JSONDict) -> None:
    if not isinstance(observation, dict):
        raise WorldStateError("GR00T replay observation must be a JSON object.")
    _require_json_native_value(observation, "GR00T replay observation")
    if set(observation) != {"video", "state", "language"}:
        raise WorldStateError("GR00T replay observation keys drifted.")
    language = _require_json_object(observation.get("language"), "GR00T replay language")
    if language.get("task") != [[saved_request["task_instruction"]]]:
        raise WorldStateError("GR00T replay task instruction drifted.")


def _validate_gr00t_observation_summary(value: object) -> None:
    observation_summary = _require_json_object(value, "GR00T replay observation_summary")
    expected_shapes = {
        "video.front": [1, 1, 1, 1, 3],
        "state.eef_9d": [1, 1, _GROOT_TENSOR_DIMS["eef_9d"]],
        "state.gripper_position": [1, 1, _GROOT_TENSOR_DIMS["gripper_position"]],
        "state.joint_position": [1, 1, _GROOT_TENSOR_DIMS["joint_position"]],
        "language.task": [1, 1],
    }
    if set(observation_summary) != set(expected_shapes):
        raise WorldStateError("GR00T replay observation_summary contains unsupported fields.")
    for field, expected_shape in expected_shapes.items():
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
        if field_summary.get("shape") != expected_shape:
            raise WorldStateError(f"GR00T replay observation_summary.{field}.shape is unsupported.")


def _gr00t_redacted_observation_summary() -> JSONDict:
    return {
        "video.front": {"redacted": True, "shape": [1, 1, 1, 1, 3]},
        "state.eef_9d": {
            "redacted": True,
            "shape": [1, 1, _GROOT_TENSOR_DIMS["eef_9d"]],
        },
        "state.gripper_position": {
            "redacted": True,
            "shape": [1, 1, _GROOT_TENSOR_DIMS["gripper_position"]],
        },
        "state.joint_position": {
            "redacted": True,
            "shape": [1, 1, _GROOT_TENSOR_DIMS["joint_position"]],
        },
        "language.task": {"redacted": True, "shape": [1, 1]},
    }


def _validate_gr00t_raw_actions(raw_actions: object) -> dict[str, list[list[float]]]:
    if not isinstance(raw_actions, dict):
        raise WorldStateError("GR00T replay raw_actions must be a JSON object.")
    if set(raw_actions) != set(_GROOT_REQUIRED_TENSORS):
        raise WorldStateError(
            "GR00T replay raw_actions must include eef_9d, gripper_position, and joint_position."
        )
    return {
        name: _validate_gr00t_tensor(raw_actions.get(name), name=name, dim=dim)
        for name, dim in _GROOT_TENSOR_DIMS.items()
    }


def _validate_gr00t_tensor(value: object, *, name: str, dim: int) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != 1:
        raise WorldStateError(
            f"GR00T replay tensor {name} must have shape [1, {_GROOT_ACTION_HORIZON}, {dim}]."
        )
    rows = value[0]
    if not isinstance(rows, list) or len(rows) != _GROOT_ACTION_HORIZON:
        raise WorldStateError(
            f"GR00T replay tensor {name} must have shape [1, {_GROOT_ACTION_HORIZON}, {dim}]."
        )
    parsed_rows: list[list[float]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != dim:
            raise WorldStateError(
                f"GR00T replay tensor {name}[0][{row_index}] must have {dim} finite values."
            )
        parsed_row: list[float] = []
        for column_index, raw_value in enumerate(row):
            if (
                not isinstance(raw_value, int | float)
                or isinstance(raw_value, bool)
                or not math.isfinite(raw_value)
            ):
                raise WorldStateError(
                    f"GR00T replay tensor {name}[0][{row_index}][{column_index}] must be finite."
                )
            parsed_row.append(float(raw_value))
        parsed_rows.append(parsed_row)
    return parsed_rows


def _gr00t_tensor_shapes(raw_actions: JSONDict) -> JSONDict:
    tensors = _validate_gr00t_raw_actions(raw_actions)
    return {name: [1, len(rows), len(rows[0]) if rows else 0] for name, rows in tensors.items()}


def _rows_to_lists(rows: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[float(value) for value in row] for row in rows]


# Demo modules import the optional-runtime provider classes at module scope, so
# keep these imports lazy: loading the harness should not pull LeRobot/LeWorldModel
# adapters into the base cold-start path.
def _run_leworldmodel_demo(**kwargs: object) -> JSONDict:
    from worldforge.demos import leworldmodel_e2e

    return leworldmodel_e2e.run_demo(**kwargs)  # type: ignore[arg-type]


def _run_lerobot_demo(**kwargs: object) -> JSONDict:
    from worldforge.demos import lerobot_e2e

    return lerobot_e2e.run_demo(**kwargs)  # type: ignore[arg-type]


_RUNNERS: dict[str, FlowRunner] = {
    "leworldmodel": _run_leworldmodel_demo,
    "lerobot": _run_lerobot_demo,
    "cosmos-policy": _run_cosmos_policy_demo,
    "gr00t": _run_gr00t_demo,
    "diagnostics": _run_diagnostics_demo,
    "workbench": _run_workbench_demo,
}


def available_flows() -> tuple[HarnessFlow, ...]:
    """Return flows available through TheWorldHarness."""

    return FLOWS


def flow_index() -> dict[str, HarnessFlow]:
    """Return available flows keyed by id."""

    return {flow.id: flow for flow in FLOWS}


def flow_to_dicts() -> tuple[JSONDict, ...]:
    """Return flow metadata for CLI JSON output."""

    return tuple(flow.to_dict() for flow in FLOWS)


def run_flow(flow_id: str, *, state_dir: Path | None = None) -> HarnessRun:
    """Execute one harness flow and return visualizable run data."""

    flows = flow_index()
    if flow_id not in flows:
        valid = ", ".join(sorted(flows))
        raise WorldForgeError(f"unknown harness flow '{flow_id}'. Valid flows: {valid}.")

    flow = flows[flow_id]
    resolved_state_dir = state_dir or Path(
        tempfile.mkdtemp(prefix=f"worldforge-harness-{flow_id}-")
    )
    workspace = create_run_workspace(
        workspace_root_for_state_dir(resolved_state_dir),
        kind="flow",
        command=flow.command,
        provider=flow.provider,
        operation=flow.id,
    )
    try:
        summary = _RUNNERS[flow_id](state_dir=resolved_state_dir, emit=False)
    except Exception as exc:
        summary = _failed_flow_summary(flow_id, resolved_state_dir, exc)
        run = HarnessRun(
            flow=flow,
            state_dir=resolved_state_dir,
            summary=summary,
            steps=_steps_for(flow_id, summary),
            metrics=_metrics_for(flow_id, summary),
            transcript=_transcript_for(flow_id, summary),
            workspace_path=workspace.path,
            provider_events=_provider_events_for(flow_id, summary),
            validation_errors=tuple(str(error) for error in summary.get("validation_errors", [])),
        )
        _write_flow_workspace(workspace, run)
        return run
    run = HarnessRun(
        flow=flow,
        state_dir=resolved_state_dir,
        summary=summary,
        steps=_steps_for(flow_id, summary),
        metrics=_metrics_for(flow_id, summary),
        transcript=_transcript_for(flow_id, summary),
        workspace_path=workspace.path,
        provider_events=_provider_events_for(flow_id, summary),
        validation_errors=tuple(str(error) for error in summary.get("validation_errors", [])),
    )
    _write_flow_workspace(workspace, run)
    return run


def _failed_flow_summary(flow_id: str, state_dir: Path, exc: Exception) -> JSONDict:
    event = ProviderEvent(
        provider=flow_index()[flow_id].provider,
        operation=flow_id,
        phase="failure",
        message=str(exc),
    )
    return {
        "demo_kind": "harness_flow",
        "state_dir": str(state_dir),
        "status": "failed",
        "event_phases": [event.phase],
        "provider_events": [event.to_dict()],
        "validation_errors": [event.message],
    }


def eval_run_artifacts(
    forge: WorldForge,
    suite_id: str,
    providers: str | Sequence[str],
    *,
    world=None,
) -> tuple[dict[str, str], EvaluationReport]:
    """Run an evaluation suite and return canonical report artifacts.

    This helper is intentionally Textual-free. The TUI and tests both call it so
    the strings shown in TheWorldHarness stay byte-identical to the CLI report
    renderers.
    """

    suite = EvaluationSuite.from_builtin(suite_id)
    report = suite.run_report(providers=providers, world=world, forge=forge)
    return report.artifacts(), report


def benchmark_run_artifacts(
    forge: WorldForge,
    providers: str | Sequence[str],
    *,
    operations: Sequence[str] | None = None,
    iterations: int = 5,
    concurrency: int = 1,
    on_sample: Callable[[JSONDict], None] | None = None,
) -> tuple[dict[str, str], BenchmarkReport]:
    """Run the benchmark harness and return canonical report artifacts."""

    report = ProviderBenchmarkHarness(forge=forge).run(
        providers,
        operations=operations,
        iterations=iterations,
        concurrency=concurrency,
        on_sample=on_sample,
    )
    return (
        {
            "json": report.to_json(),
            "markdown": report.to_markdown(),
            "csv": report.to_csv(),
            "html": report.to_html(),
        },
        report,
    )


def write_report(forge: WorldForge, kind: str, artifacts: dict[str, str]) -> Path:
    """Persist a canonical JSON report under ``<state-dir>/reports``."""

    if "json" not in artifacts:
        raise ValueError("report artifacts must include a json entry")
    reports_dir = forge.state_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    safe_kind = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in kind).strip("-")
    path = reports_dir / f"{safe_kind}-{timestamp}-{run_id}.json"
    path.write_text(artifacts["json"], encoding="utf-8")
    return path.resolve()


def preserve_eval_run_workspace(
    workspace_dir: Path,
    *,
    suite_id: str,
    providers: Sequence[str],
    artifacts: dict[str, str],
    report: EvaluationReport,
    command: str,
    config_profile: JSONDict | None = None,
) -> RunWorkspace:
    """Preserve an evaluation report in the shared run workspace layout."""

    input_summary: dict[str, object] = {"suite_id": suite_id, "providers": list(providers)}
    if report.provenance is not None and report.provenance.dataset_manifests:
        input_summary["dataset_manifests"] = [
            ref["id"] for ref in report.provenance.dataset_manifests
        ]
    workspace = create_run_workspace(
        workspace_dir,
        kind="eval",
        command=command,
        provider=", ".join(providers),
        operation=suite_id,
        input_summary=input_summary,
    )
    paths = _write_report_artifacts(workspace, artifacts)
    result_summary = {
        "suite_id": report.suite_id,
        "suite": report.suite,
        "result_count": len(report.results),
        "passed_count": sum(1 for result in report.results if result.passed),
    }
    workspace.write_json("results/summary.json", result_summary)
    write_run_manifest(
        workspace,
        kind="eval",
        command=command,
        provider=", ".join(providers),
        operation=suite_id,
        status="completed",
        input_summary=input_summary,
        result_summary=result_summary,
        artifact_paths=paths,
        config_profile=config_profile,
    )
    return workspace


def preserve_benchmark_run_workspace(
    workspace_dir: Path,
    *,
    providers: Sequence[str],
    operations: Sequence[str] | None,
    artifacts: dict[str, str],
    report: BenchmarkReport,
    command: str,
    budget_passed: bool | None = None,
    config_profile: JSONDict | None = None,
) -> RunWorkspace:
    """Preserve a benchmark report in the shared run workspace layout."""

    operation_label = ", ".join(operations or ProviderBenchmarkHarness.benchmarkable_operations)
    input_summary = {"providers": list(providers), "operations": list(operations or [])}
    workspace = create_run_workspace(
        workspace_dir,
        kind="benchmark",
        command=command,
        provider=", ".join(providers),
        operation=operation_label,
        input_summary=input_summary,
    )
    paths = _write_report_artifacts(workspace, artifacts)
    result_summary = {
        "result_count": len(report.results),
        "error_count": sum(result.error_count for result in report.results),
        "retry_count": sum(result.retry_count for result in report.results),
        "budget_passed": budget_passed,
    }
    workspace.write_json("results/summary.json", result_summary)
    write_run_manifest(
        workspace,
        kind="benchmark",
        command=command,
        provider=", ".join(providers),
        operation=operation_label,
        status="completed" if budget_passed is not False else "failed",
        input_summary=input_summary,
        result_summary=result_summary,
        artifact_paths=paths,
        config_profile=config_profile,
        event_count=sum(
            int(event.get("request_count", 0))
            for result in report.results
            for event in result.operation_metrics.get("events", [])
            if isinstance(event, dict)
        ),
    )
    return workspace


def report_run_from_path(path: Path, *, state_dir: Path) -> HarnessRun:
    """Build a ``HarnessRun`` for a saved eval or benchmark JSON report."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if "suite_id" in payload:
        return _eval_run_from_payload(payload, path=path, state_dir=state_dir)
    if "results" in payload:
        return _benchmark_run_from_payload(payload, path=path, state_dir=state_dir)
    raise ValueError(f"unsupported harness report payload at {path}")


def recent_report_paths(state_dir: Path, *, limit: int = 5) -> tuple[Path, ...]:
    """Return recent preserved report files from ``<state-dir>/reports``."""

    reports_dir = state_dir / "reports"
    try:
        candidates = list(reports_dir.glob("*.json"))
    except OSError:
        return ()
    paths = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    return tuple(paths[:limit])


def _eval_run_from_payload(payload: JSONDict, *, path: Path, state_dir: Path) -> HarnessRun:
    suite_id = str(payload.get("suite_id", "evaluation"))
    suite_name = str(payload.get("suite", suite_id))
    results = list(payload.get("results", []))
    summaries = list(payload.get("provider_summaries", []))
    passed = sum(1 for result in results if result.get("passed"))
    total = len(results)
    flow = HarnessFlow(
        id=f"eval-{suite_id}",
        title=f"Evaluation: {suite_name}",
        short_title=f"Eval {suite_id}",
        focus="evaluation report",
        provider=", ".join(str(summary.get("provider")) for summary in summaries) or "provider",
        capability="evaluation",
        command=f"worldforge eval --suite {suite_id}",
        accent="",
        summary=f"{passed}/{total} scenarios passed.",
    )
    return HarnessRun(
        flow=flow,
        state_dir=state_dir,
        summary=payload,
        steps=(
            HarnessStep(
                "Load evaluation report",
                "Read preserved JSON from the harness reports directory.",
                f"{path.name}",
                str(path),
            ),
            HarnessStep(
                "Inspect verdict",
                "Summarise deterministic adapter-suite results.",
                f"{passed}/{total} scenarios passed.",
            ),
        ),
        metrics=tuple(
            HarnessMetric(
                str(summary.get("provider", "provider")),
                f"{summary.get('passed_scenario_count', 0)}/{summary.get('scenario_count', 0)}",
                f"average_score={float(summary.get('average_score', 0.0)):.2f}",
            )
            for summary in summaries
        )
        or (HarnessMetric("Scenarios", f"{passed}/{total}", "evaluation results"),),
        transcript=(
            "kind: eval",
            f"suite: {suite_name} ({suite_id})",
            f"report_path: {path}",
            f"passed: {passed}/{total}",
        ),
        kind="eval",
        report_path=path,
        artifacts=_eval_artifacts_from_payload(payload),
    )


def _benchmark_run_from_payload(payload: JSONDict, *, path: Path, state_dir: Path) -> HarnessRun:
    results = list(payload.get("results", []))
    flow = HarnessFlow(
        id="benchmark-report",
        title="Benchmark Report",
        short_title="Benchmark",
        focus="latency / retry / throughput",
        provider=", ".join(sorted({str(result.get("provider")) for result in results}))
        or "provider",
        capability="benchmark",
        command="worldforge benchmark",
        accent="",
        summary=f"{len(results)} benchmark rows.",
    )
    metrics = tuple(
        HarnessMetric(
            f"{result.get('provider')}.{result.get('operation')}",
            f"{float(result.get('average_latency_ms') or 0.0):.2f} ms",
            f"ok={result.get('success_count')}/{result.get('iterations')} "
            f"p95={float(result.get('p95_latency_ms') or 0.0):.2f} ms",
        )
        for result in results
    )
    return HarnessRun(
        flow=flow,
        state_dir=state_dir,
        summary=payload,
        steps=(
            HarnessStep(
                "Load benchmark report",
                "Read preserved JSON from the harness reports directory.",
                path.name,
                str(path),
            ),
            HarnessStep(
                "Inspect benchmark rows",
                "Summarise latency, retry, and throughput results.",
                f"{len(results)} operation rows.",
            ),
        ),
        metrics=metrics or (HarnessMetric("Rows", "0", "benchmark results"),),
        transcript=(
            "kind: benchmark",
            f"report_path: {path}",
            f"rows: {len(results)}",
        ),
        kind="benchmark",
        report_path=path,
        artifacts=_benchmark_artifacts_from_payload(payload),
    )


def _eval_artifacts_from_payload(payload: JSONDict) -> dict[str, str]:
    suite_id = str(payload.get("suite_id", "evaluation"))
    suite = str(payload.get("suite", suite_id))
    provenance = (
        ProvenanceEnvelope.from_dict(payload["provenance"])
        if isinstance(payload.get("provenance"), dict)
        else None
    )
    report_kwargs: dict[str, object] = {}
    workflow_trace = payload.get("workflow_trace")
    if isinstance(workflow_trace, dict):
        report_kwargs["workflow_trace"] = workflow_trace
    if isinstance(payload.get("claim_boundary"), str):
        report_kwargs["claim_boundary"] = payload["claim_boundary"]
    if isinstance(payload.get("metric_semantics"), str):
        report_kwargs["metric_semantics"] = payload["metric_semantics"]
    report = EvaluationReport(
        suite_id=suite_id,
        suite=suite,
        results=[
            EvaluationResult(
                suite_id=str(result.get("suite_id", suite_id)),
                suite=str(result.get("suite", suite)),
                scenario=str(result.get("scenario", "scenario")),
                provider=str(result.get("provider", "provider")),
                score=result.get("score", 0.0),
                passed=result.get("passed", False),
                metrics=dict(result.get("metrics", {})),
            )
            for result in payload.get("results", [])
        ],
        provenance=provenance,
        **report_kwargs,
    )
    return report.artifacts()


def _benchmark_artifacts_from_payload(payload: JSONDict) -> dict[str, str]:
    provenance = (
        ProvenanceEnvelope.from_dict(payload["provenance"])
        if isinstance(payload.get("provenance"), dict)
        else None
    )
    report = BenchmarkReport(
        results=[
            BenchmarkResult(
                provider=str(result.get("provider", "provider")),
                operation=str(result.get("operation", "predict")),
                iterations=result.get("iterations", 1),
                concurrency=result.get("concurrency", 1),
                success_count=result.get("success_count", 0),
                error_count=result.get("error_count", 1),
                retry_count=result.get("retry_count", 0),
                total_time_ms=result.get("total_time_ms", 0.0),
                average_latency_ms=result.get("average_latency_ms"),
                min_latency_ms=result.get("min_latency_ms"),
                max_latency_ms=result.get("max_latency_ms"),
                p50_latency_ms=result.get("p50_latency_ms"),
                p95_latency_ms=result.get("p95_latency_ms"),
                throughput_per_second=result.get("throughput_per_second", 0.0),
                operation_metrics=dict(result.get("operation_metrics", {})),
                errors=list(result.get("errors", [])),
            )
            for result in payload.get("results", [])
        ],
        run_metadata=dict(payload.get("run_metadata", {})),
        provenance=provenance,
    )
    return report.artifacts()


def _write_flow_workspace(workspace: RunWorkspace, run: HarnessRun) -> None:
    summary_path = workspace.write_json("results/summary.json", run.summary)
    steps_path = workspace.write_json("results/steps.json", [step.to_dict() for step in run.steps])
    metrics_path = workspace.write_json(
        "results/metrics.json",
        [metric.to_dict() for metric in run.metrics],
    )
    transcript_path = workspace.write_text("logs/transcript.txt", "\n".join(run.transcript))
    inspector_path = workspace.write_json(
        "results/inspector.json",
        _inspector_payload(run),
    )
    provider_events = run.provider_events
    event_count = len(provider_events)
    if provider_events:
        workspace.write_text(
            "logs/provider-events.jsonl",
            "\n".join(json.dumps(event, sort_keys=True) for event in provider_events),
        )
    artifact_paths = {
        "summary": str(summary_path.relative_to(workspace.path)),
        "steps": str(steps_path.relative_to(workspace.path)),
        "metrics": str(metrics_path.relative_to(workspace.path)),
        "transcript": str(transcript_path.relative_to(workspace.path)),
        "inspector": str(inspector_path.relative_to(workspace.path)),
    }
    artifact_paths.update(_write_flow_artifacts(workspace, run.summary))
    write_run_manifest(
        workspace,
        kind="flow",
        command=run.flow.command,
        provider=run.flow.provider,
        operation=run.flow.id,
        status="failed" if run.validation_errors else "completed",
        input_summary={"flow_id": run.flow.id, "state_dir": str(run.state_dir)},
        result_summary={
            "step_count": len(run.steps),
            "metric_count": len(run.metrics),
            "summary_keys": sorted(run.summary),
            "validation_error_count": len(run.validation_errors),
        },
        artifact_paths=artifact_paths,
        event_count=event_count,
    )


def _inspector_payload(run: HarnessRun) -> JSONDict:
    return {
        "flow": run.flow.to_dict(),
        "status": "failed" if run.validation_errors else "completed",
        "metrics": [metric.to_dict() for metric in run.metrics],
        "steps": [step.to_dict() for step in run.steps],
        "provider_events": [dict(event) for event in run.provider_events],
        "validation_errors": list(run.validation_errors),
        "workspace_path": str(run.workspace_path) if run.workspace_path is not None else None,
    }


def _write_flow_artifacts(workspace: RunWorkspace, summary: JSONDict) -> JSONDict:
    descriptors = summary.get("harness_artifacts")
    if not isinstance(descriptors, dict):
        return {}
    paths: JSONDict = {}
    for name, descriptor in descriptors.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("harness artifact names must be non-empty strings")
        if name in _FLOW_ARTIFACT_RESERVED_NAMES:
            raise ValueError(f"harness artifact '{name}' uses a reserved manifest key")
        if not isinstance(descriptor, dict):
            raise ValueError(f"harness artifact '{name}' descriptor must be a JSON object")
        relative_path = descriptor.get("path")
        payload = descriptor.get("payload")
        if not isinstance(relative_path, str) or not relative_path.startswith("artifacts/"):
            raise ValueError(f"harness artifact '{name}' path must be under artifacts/")
        path = workspace.write_json(relative_path, payload)
        paths[name] = str(path.relative_to(workspace.path))
    return paths


def _write_report_artifacts(workspace: RunWorkspace, artifacts: dict[str, str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for name, content in artifacts.items():
        suffix = "md" if name == "markdown" else name
        path = workspace.write_text(f"reports/report.{suffix}", content)
        paths[name] = str(path.relative_to(workspace.path))
    return paths


def _format_optional_float(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.6f}"


def _steps_for(flow_id: str, summary: JSONDict) -> tuple[HarnessStep, ...]:
    validation_errors = summary.get("validation_errors")
    if isinstance(validation_errors, list) and validation_errors:
        return (
            HarnessStep(
                "Start flow",
                "Create a run workspace and record the command before invoking providers.",
                "Run workspace preserved.",
                f"state_dir={Path(str(summary.get('state_dir', ''))).name}",
            ),
            HarnessStep(
                "Capture failure",
                "Persist sanitized provider events and validation errors for triage.",
                str(validation_errors[0]),
                "artifact=run_manifest.json results/inspector.json",
            ),
        )
    if flow_id == "leworldmodel":
        return (
            HarnessStep(
                "Register provider surface",
                "LeWorldModelProvider receives an injected deterministic cost runtime.",
                (
                    "Provider health is configured; optional checkpoint inference stays outside "
                    "the base package."
                ),
                "provider=leworldmodel capability=score",
            ),
            HarnessStep(
                "Build planning world",
                "Create a local world, add blue_cube, and encode an object_at goal.",
                _goal_result(summary),
                "world=leworldmodel-score-planning-demo",
            ),
            HarnessStep(
                "Score candidate futures",
                "Send pixel/action/goal tensors through score_actions.",
                _cost_result(summary),
                f"selected_candidate={summary['selected_candidate_index']}",
            ),
            HarnessStep(
                "Plan and execute",
                "World.plan consumes the score result and mock executes the selected actions.",
                _action_result(summary),
                f"planner={summary['plan']['planner']}",
            ),
            HarnessStep(
                "Persist and reload",
                "Save the final world to local JSON and reload it through WorldForge.",
                _final_position_result(summary),
                f"saved_world_id={summary['saved_world_id']}",
            ),
            HarnessStep(
                "Inspect provider events",
                "Capture emitted provider phases from the model boundary.",
                _event_result(summary),
                "event_handler=recording",
            ),
        )
    if flow_id == "lerobot":
        return (
            HarnessStep(
                "Register policy surface",
                (
                    "LeRobotPolicyProvider receives an injected deterministic policy and action "
                    "translator."
                ),
                "Provider health is configured; torch and policy checkpoints remain host-owned.",
                "provider=lerobot capability=policy",
            ),
            HarnessStep(
                "Build task world",
                "Create a local world, add blue_cube, and define the placement goal.",
                _goal_result(summary),
                "world=lerobot-policy-plus-score-demo",
            ),
            HarnessStep(
                "Select action chunks",
                "Call select_actions and preserve raw policy candidates before translation.",
                f"{summary['policy_candidate_count']} translated action chunks returned.",
                f"policy_select_calls={summary['policy_select_calls']}",
            ),
            HarnessStep(
                "Rank policy candidates",
                "Score translated action chunks by final distance to the goal.",
                _cost_result(summary),
                f"selected_candidate={summary['selected_candidate_index']}",
            ),
            HarnessStep(
                "Execute and persist",
                (
                    "Execute selected WorldForge actions, save the final world, and reload it "
                    "from disk."
                ),
                _final_position_result(summary),
                f"saved_world_id={summary['saved_world_id']}",
            ),
            HarnessStep(
                "Inspect provider events",
                "Capture provider phases and policy lifecycle calls.",
                _event_result(summary),
                f"reset_calls={summary['policy_reset_calls']}",
            ),
        )
    if flow_id == "cosmos-policy":
        return (
            HarnessStep(
                "Load saved /act replay",
                "Use a sanitized Cosmos-Policy response shape from a prepared smoke replay.",
                "Checkout-safe replay loaded; no GPU or network call is required.",
                f"task={summary['task_description']}",
            ),
            HarnessStep(
                "Check provider boundary",
                "Instantiate CosmosPolicyProvider with the same remote-server contract.",
                "Provider health is configured for /act.",
                f"model={summary['model']}",
            ),
            HarnessStep(
                "Call Cosmos adapter",
                "Route the replay through the real HTTP policy adapter and event path.",
                f"{summary['request_count']} POST /act request handled.",
                f"server_path={summary['server_path']}",
            ),
            HarnessStep(
                "Decode action rows",
                "Validate and decode json_numpy ALOHA action rows before translation.",
                f"raw action shape {summary['raw_action_shape']}.",
                "json_numpy_rows=true",
            ),
            HarnessStep(
                "Translate ALOHA actions",
                "Map raw 14D bimanual rows into executable WorldForge Action objects.",
                f"{summary['translated_action_count']} move_to actions produced.",
                f"value_prediction={_format_optional_float(summary['value_prediction'])}",
            ),
            HarnessStep(
                "Preserve replay artifact",
                "Write the inspector state, provider events, and sanitized replay artifact.",
                "artifact=artifacts/cosmos-policy-replay.json",
                f"events={', '.join(summary['event_phases'])}",
            ),
        )
    if flow_id == "gr00t":
        return (
            HarnessStep(
                "Load saved PolicyClient replay",
                "Use a sanitized GR00T action response from a prepared live-server shape.",
                "Checkout-safe replay loaded; no CUDA server or checkpoint is required.",
                f"task={summary['task_instruction']}",
            ),
            HarnessStep(
                "Check provider boundary",
                "Instantiate GrootPolicyClientProvider with an injected PolicyClient replay.",
                "Provider health is configured for the injected client.",
                f"model={summary['model']}",
            ),
            HarnessStep(
                "Call GR00T adapter",
                "Route the replay through the real policy provider and event path.",
                f"{summary['policy_client_calls']} get_action call handled.",
                f"embodiment={summary['embodiment_tag']}",
            ),
            HarnessStep(
                "Validate named tensors",
                "Check eef_9d, gripper_position, and joint_position shapes before translation.",
                f"raw tensor shapes {summary['raw_tensor_shapes']}.",
                f"validated={', '.join(summary['validated_tensors'])}",
            ),
            HarnessStep(
                "Translate policy output",
                "Map eef_9d trajectory rows into executable WorldForge Action objects.",
                f"{summary['translated_action_count']} move_to actions produced.",
                f"action_horizon={summary['action_horizon']}",
            ),
            HarnessStep(
                "Preserve replay artifact",
                "Write the inspector state, provider events, and sanitized GR00T replay artifact.",
                "artifact=artifacts/gr00t-policy-replay.json",
                f"events={', '.join(summary['event_phases'])}",
            ),
        )
    if flow_id == "diagnostics":
        return (
            HarnessStep(
                "Create isolated forge",
                "Start WorldForge with remote auto-registration disabled for a stable scan.",
                (
                    f"{summary['registered_provider_count']} registered provider, "
                    f"{summary['known_provider_count']} known provider profiles inspected."
                ),
                f"state_dir={Path(str(summary['state_dir'])).name}",
            ),
            HarnessStep(
                "Run provider diagnostics",
                "Call doctor() over registered and known provider profiles.",
                (
                    f"{summary['healthy_provider_count']} healthy providers, "
                    f"{summary['issue_count']} configuration issues reported."
                ),
                "command=uv run worldforge doctor",
            ),
            HarnessStep(
                "Inspect benchmark surface",
                "Resolve supported benchmark operations from ProviderBenchmarkHarness.",
                ", ".join(summary["mock_supported_operations"]),
                "provider=mock",
            ),
            HarnessStep(
                "Run benchmark matrix",
                (
                    "Execute mock benchmark samples across predict, reason, generate, "
                    "transfer, and embed."
                ),
                (
                    f"{summary['benchmark_operation_count']} operations, "
                    f"{summary['benchmark_iterations']} iterations each."
                ),
                "concurrency=1",
            ),
            HarnessStep(
                "Compare operations",
                "Compare average latency and throughput for the benchmark report.",
                (
                    f"Fastest average latency: {summary['fastest_operation']} "
                    f"({_format_ms(summary['fastest_average_latency_ms'])})."
                ),
                (
                    f"highest_throughput={summary['highest_throughput_operation']} "
                    f"{summary['highest_throughput_per_second']:.2f}/s"
                ),
            ),
            HarnessStep(
                "Inspect provider events",
                "Read emitted provider benchmark events captured by operation metrics.",
                f"{summary['benchmark_event_count']} provider events captured.",
                "artifact=benchmark report json/markdown/csv",
            ),
        )
    if flow_id == "workbench":
        candidate_missing = summary["missing_evidence_by_provider"]["jepa-wms"]
        return (
            HarnessStep(
                "Select authoring targets",
                "Use one stable catalog provider and one direct-construction candidate.",
                f"{', '.join(summary['providers'])} selected.",
                "providers=mock,jepa-wms",
            ),
            HarnessStep(
                "Run checkout-safe workbench",
                "Invoke non-Textual provider_workbench_report without live provider calls.",
                f"{summary['passed_count']}/{summary['report_count']} reports passed.",
                "live=false",
            ),
            HarnessStep(
                "Inspect promotion evidence",
                "Group missing evidence by target promotion status.",
                (
                    "jepa-wms stable gaps: "
                    f"{', '.join(candidate_missing.get('stable', [])) or 'none'}."
                ),
                "promotion=experimental,beta,stable",
            ),
            HarnessStep(
                "Check runtime and fixtures",
                "Read runtime manifest status and provider fixture coverage.",
                f"{summary['safe_artifact_count']} safe artifact references collected.",
                "fixtures=tests/fixtures/providers",
            ),
            HarnessStep(
                "Render issue output",
                "Preserve validation commands and safe artifact references for PRs or issues.",
                f"{len(summary['validation_commands'])} validation commands listed.",
                "format=markdown,json",
            ),
        )
    raise ValueError(f"unknown harness flow '{flow_id}'")


def _metrics_for(flow_id: str, summary: JSONDict) -> tuple[HarnessMetric, ...]:
    validation_errors = summary.get("validation_errors")
    if isinstance(validation_errors, list) and validation_errors:
        return (
            HarnessMetric("Status", "failed", "run manifest preserved for reproduction"),
            HarnessMetric("Events", str(len(summary.get("event_phases", []))), "failure"),
            HarnessMetric("Errors", str(len(validation_errors)), str(validation_errors[0])),
        )
    if flow_id == "diagnostics":
        return (
            HarnessMetric(
                "Known profiles",
                str(summary["known_provider_count"]),
                "registered plus unregistered catalog entries",
            ),
            HarnessMetric(
                "Registered",
                str(summary["registered_provider_count"]),
                ", ".join(summary["registered_providers"]),
            ),
            HarnessMetric("Issues", str(summary["issue_count"]), "doctor() configuration findings"),
            HarnessMetric(
                "Benchmarks",
                str(summary["benchmark_operation_count"]),
                ", ".join(summary["mock_supported_operations"]),
            ),
            HarnessMetric(
                "Fastest avg",
                str(summary["fastest_operation"]),
                _format_ms(summary["fastest_average_latency_ms"]),
            ),
            HarnessMetric(
                "Events",
                str(summary["benchmark_event_count"]),
                "provider events captured during benchmark samples",
            ),
        )
    if flow_id == "workbench":
        candidate_missing = summary["missing_evidence_by_provider"]["jepa-wms"]
        stable_missing = candidate_missing.get("stable", [])
        return (
            HarnessMetric(
                "Targets",
                str(summary["report_count"]),
                ", ".join(summary["providers"]),
            ),
            HarnessMetric(
                "Passed",
                f"{summary['passed_count']}/{summary['report_count']}",
                "checkout-safe reports",
            ),
            HarnessMetric(
                "Candidate gaps",
                str(len(stable_missing)),
                ", ".join(stable_missing) or "none",
            ),
            HarnessMetric(
                "Artifacts",
                str(summary["safe_artifact_count"]),
                "safe issue references",
            ),
            HarnessMetric(
                "Commands",
                str(len(summary["validation_commands"])),
                "validation commands",
            ),
        )
    if flow_id == "cosmos-policy":
        return (
            HarnessMetric("Flow", "policy", "Cosmos-Policy /act contract replay"),
            HarnessMetric(
                "Raw shape",
                " x ".join(str(item) for item in summary["raw_action_shape"]),
                "decoded json_numpy action rows",
            ),
            HarnessMetric(
                "Translated",
                str(summary["translated_action_count"]),
                "WorldForge Action objects",
            ),
            HarnessMetric(
                "Value",
                _format_optional_float(summary["value_prediction"]),
                "provider value_prediction",
            ),
            HarnessMetric(
                "Events",
                str(len(summary["event_phases"])),
                ", ".join(summary["event_phases"]),
            ),
            HarnessMetric("Artifact", "replay", "artifacts/cosmos-policy-replay.json"),
        )
    if flow_id == "gr00t":
        return (
            HarnessMetric("Flow", "policy", "GR00T PolicyClient replay"),
            HarnessMetric(
                "Tensors",
                str(len(summary["validated_tensors"])),
                ", ".join(summary["validated_tensors"]),
            ),
            HarnessMetric(
                "Horizon",
                str(summary["action_horizon"]),
                "translated action rows",
            ),
            HarnessMetric(
                "Translated",
                str(summary["translated_action_count"]),
                "WorldForge Action objects",
            ),
            HarnessMetric(
                "Events",
                str(len(summary["event_phases"])),
                ", ".join(summary["event_phases"]),
            ),
            HarnessMetric("Artifact", "replay", "artifacts/gr00t-policy-replay.json"),
        )

    flow_label = "score" if flow_id == "leworldmodel" else "policy+score"
    return (
        HarnessMetric("Flow", flow_label, "WorldForge planning mode"),
        HarnessMetric("Candidates", str(len(summary["candidate_costs"])), "ranked action paths"),
        HarnessMetric("Selected", f"#{summary['selected_candidate_index']}", "lowest-cost path"),
        HarnessMetric("Final position", _position(summary), "reloaded world state"),
        HarnessMetric(
            "Events",
            str(len(summary["event_phases"])),
            ", ".join(summary["event_phases"]),
        ),
        HarnessMetric("State", Path(str(summary["state_dir"])).name, "local persistence root"),
    )


def _transcript_for(flow_id: str, summary: JSONDict) -> tuple[str, ...]:
    validation_errors = summary.get("validation_errors")
    if isinstance(validation_errors, list) and validation_errors:
        return (
            f"flow: {flow_id}",
            "status: failed",
            f"state_dir: {summary.get('state_dir', '')}",
            f"validation_errors: {' | '.join(str(error) for error in validation_errors)}",
            f"events: {', '.join(str(phase) for phase in summary.get('event_phases', []))}",
        )
    if flow_id == "diagnostics":
        return (
            "flow: diagnostics",
            f"registered_providers: {', '.join(summary['registered_providers'])}",
            f"known_provider_count: {summary['known_provider_count']}",
            f"healthy_provider_count: {summary['healthy_provider_count']}",
            f"issue_count: {summary['issue_count']}",
            f"benchmark_operations: {', '.join(summary['mock_supported_operations'])}",
            f"benchmark_iterations: {summary['benchmark_iterations']}",
            f"fastest_operation: {summary['fastest_operation']}",
            f"highest_throughput_operation: {summary['highest_throughput_operation']}",
            f"benchmark_event_count: {summary['benchmark_event_count']}",
            f"commands: {' | '.join(summary['commands'])}",
        )
    if flow_id == "workbench":
        candidate_missing = summary["missing_evidence_by_provider"]["jepa-wms"]
        return (
            "flow: workbench",
            f"providers: {', '.join(summary['providers'])}",
            f"passed: {summary['passed_count']}/{summary['report_count']}",
            f"jepa-wms_missing_stable: {', '.join(candidate_missing.get('stable', [])) or 'none'}",
            f"safe_artifacts: {summary['safe_artifact_count']}",
            f"validation_commands: {' | '.join(summary['validation_commands'])}",
        )
    if flow_id == "cosmos-policy":
        return (
            "flow: cosmos-policy",
            f"provider: {', '.join(summary['providers'])}",
            f"model: {summary['model']}",
            f"server_path: {summary['server_path']}",
            f"task: {summary['task_description']}",
            f"health: {summary['health']['healthy']}",
            f"raw_action_shape: {summary['raw_action_shape']}",
            f"translated_actions: {summary['translated_action_count']}",
            f"value_prediction: {_format_optional_float(summary['value_prediction'])}",
            "saved_replay_artifact: artifacts/cosmos-policy-replay.json",
            f"events: {', '.join(summary['event_phases'])}",
        )
    if flow_id == "gr00t":
        return (
            "flow: gr00t",
            f"provider: {', '.join(summary['providers'])}",
            f"model: {summary['model']}",
            f"task: {summary['task_instruction']}",
            f"health: {summary['health']['healthy']}",
            f"raw_tensor_shapes: {summary['raw_tensor_shapes']}",
            f"validated_tensors: {', '.join(summary['validated_tensors'])}",
            f"translated_actions: {summary['translated_action_count']}",
            "saved_replay_artifact: artifacts/gr00t-policy-replay.json",
            f"events: {', '.join(summary['event_phases'])}",
        )

    lines = [
        f"flow: {flow_id}",
        f"providers: {', '.join(summary['providers'])}",
        f"candidate_costs: {', '.join(str(score) for score in summary['candidate_costs'])}",
        f"selected_candidate: {summary['selected_candidate_index']}",
        f"selected_actions: {len(summary['selected_actions'])}",
        f"final_position: {_position(summary)}",
        f"saved_world_id: {summary['saved_world_id']}",
        f"events: {', '.join(summary['event_phases'])}",
    ]
    if flow_id == "lerobot":
        lines.extend(
            [
                f"policy_candidate_count: {summary['policy_candidate_count']}",
                f"policy_select_calls: {summary['policy_select_calls']}",
                f"policy_reset_calls: {summary['policy_reset_calls']}",
            ]
        )
    return tuple(lines)


def _goal_result(summary: JSONDict) -> str:
    goal = summary["goal"]["position"]
    return f"Goal position encoded at ({goal['x']:.2f}, {goal['y']:.2f}, {goal['z']:.2f})."


def _cost_result(summary: JSONDict) -> str:
    costs = ", ".join(f"{cost:.4f}" for cost in summary["candidate_costs"])
    return f"Costs [{costs}], selected #{summary['selected_candidate_index']}."


def _action_result(summary: JSONDict) -> str:
    return f"{len(summary['selected_actions'])} actions selected for execution."


def _final_position_result(summary: JSONDict) -> str:
    return f"Final cube position {_position(summary)} after reload."


def _event_result(summary: JSONDict) -> str:
    return f"Provider phases: {', '.join(summary['event_phases'])}."


def _provider_events_for(flow_id: str, summary: JSONDict) -> tuple[JSONDict, ...]:
    events = summary.get("provider_events")
    if isinstance(events, list):
        return tuple(dict(event) for event in events if isinstance(event, dict))
    benchmark_results = summary.get("benchmark_results")
    if isinstance(benchmark_results, list):
        synthesized: list[JSONDict] = []
        for result in benchmark_results:
            if not isinstance(result, dict):
                continue
            metrics = result.get("operation_metrics")
            if not isinstance(metrics, dict):
                continue
            for metric_event in metrics.get("events", []):
                if not isinstance(metric_event, dict):
                    continue
                request_count = int(metric_event.get("request_count", 0) or 0)
                retry_count = int(metric_event.get("retry_count", 0) or 0)
                error_count = int(metric_event.get("error_count", 0) or 0)
                phase = "failure" if error_count else "retry" if retry_count else "success"
                synthesized.append(
                    ProviderEvent(
                        provider=str(metric_event.get("provider", result.get("provider", "mock"))),
                        operation=str(
                            metric_event.get("operation", result.get("operation", flow_id))
                        ),
                        phase=phase,
                        metadata={
                            "request_count": request_count,
                            "retry_count": retry_count,
                            "error_count": error_count,
                        },
                    ).to_dict()
                )
        return tuple(synthesized)
    phases = summary.get("event_phases")
    if not isinstance(phases, list):
        return ()
    flow = flow_index()[flow_id]
    return tuple(
        ProviderEvent(
            provider=flow.provider,
            operation=flow.id,
            phase=str(phase),
        ).to_dict()
        for phase in phases
    )


def _position(summary: JSONDict) -> str:
    final = summary["final_cube_position"]
    return f"({final['x']:.2f}, {final['y']:.2f}, {final['z']:.2f})"


def _format_ms(value: object) -> str:
    return f"{float(value):.2f} ms"
