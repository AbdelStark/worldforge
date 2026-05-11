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
        id="gr00t-replay",
        title="GR00T DROID Replay",
        short_title="GR00T",
        focus="saved GR00T PolicyClient replay",
        provider="GrootPolicyClientProvider",
        capability="policy",
        command="uv run --extra harness worldforge-harness --flow gr00t-replay",
        accent="#b6f377",
        summary=(
            "Replay a sanitized NVIDIA GR00T N1.7 PolicyClient response through the real provider "
            "boundary, validate named action tensors, translate 40 steps, and preserve an "
            "inspectable artifact without requiring a live GPU."
        ),
    ),
    HarnessFlow(
        id="robotics-compare",
        title="Robotics Policy Replay Comparison",
        short_title="Compare",
        focus="cross-provider policy inspection",
        provider="LeRobot + Cosmos-Policy + GR00T",
        capability="policy",
        command="uv run --extra harness worldforge-harness --flow robotics-compare",
        accent="#ffcc66",
        summary=(
            "Run the checkout-safe LeRobot, Cosmos-Policy, and GR00T policy paths side by side, "
            "compare action shapes and translation counts, and preserve a sanitized comparison "
            "artifact without keeping GPU servers online."
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
_GROOT_REPLAY_EEF_PREFIX_ROWS = (
    (
        0.45209485,
        -0.04993579,
        0.35151827,
        0.99991280,
        -0.00503587,
        -0.01220623,
        0.00520440,
        0.99989104,
        0.01381495,
    ),
    (
        0.45370448,
        -0.05460007,
        0.35082236,
        0.99975926,
        -0.00603632,
        -0.02109618,
        0.00664691,
        0.99955750,
        0.02899381,
    ),
    (
        0.45319659,
        -0.04851697,
        0.35273436,
        0.99879819,
        -0.01500455,
        -0.04665894,
        0.01667653,
        0.99922508,
        0.03565361,
    ),
    (
        0.45103294,
        -0.05216613,
        0.35121581,
        0.99818760,
        -0.01888346,
        -0.05713980,
        0.02149428,
        0.99873638,
        0.04542767,
    ),
    (
        0.45371175,
        -0.04883665,
        0.35304552,
        0.99673748,
        -0.02772977,
        -0.07579842,
        0.03198496,
        0.99794549,
        0.05551316,
    ),
    (
        0.45116049,
        -0.04859919,
        0.35463876,
        0.99458879,
        -0.04060974,
        -0.09562392,
        0.04728588,
        0.99652177,
        0.06861795,
    ),
    (
        0.45225149,
        -0.04907730,
        0.35640752,
        0.99183750,
        -0.05253663,
        -0.11618217,
        0.06253119,
        0.99449146,
        0.08412262,
    ),
    (
        0.45332921,
        -0.04459824,
        0.35799032,
        0.98470002,
        -0.05842229,
        -0.16417292,
        0.07588259,
        0.99186796,
        0.10217515,
    ),
)
_GROOT_REPLAY_GRIPPER_PREFIX_ROWS = (
    (0.00195312,),
    (0.0,),
    (0.00390625,),
    (0.0,),
    (0.00195312,),
    (0.0,),
    (0.0,),
    (0.00585938,),
)
_GROOT_REPLAY_JOINT_PREFIX_ROWS = (
    (-0.19574580, -0.40341792, -0.10423726, -2.19564652, -0.21871637, 2.10479379, 0.39902940),
    (-0.19844921, -0.40122452, -0.09466118, -2.19360781, -0.24168095, 2.11665559, 0.39399421),
    (-0.21554480, -0.41246665, -0.09100682, -2.19702625, -0.24528827, 2.11675787, 0.38742143),
    (-0.19939159, -0.40944505, -0.09160183, -2.19366264, -0.26949242, 2.11434579, 0.37265414),
    (-0.19068547, -0.40942037, -0.09546585, -2.19406295, -0.27474448, 2.12093925, 0.37172550),
    (-0.18911973, -0.41755563, -0.09746341, -2.19225788, -0.29558879, 2.12040114, 0.35820645),
    (-0.19144866, -0.41764820, -0.09365430, -2.18930912, -0.30929935, 2.13109922, 0.33803242),
    (-0.17990023, -0.43038398, -0.09860370, -2.18720603, -0.32697150, 2.13032913, 0.33624285),
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


def _run_gr00t_replay_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    from worldforge.models import Action
    from worldforge.providers import GrootPolicyClientProvider

    events: list[ProviderEvent] = []
    replay_source_path = _write_prepared_groot_replay_artifact(state_dir)
    saved_replay = _load_groot_replay_artifact(replay_source_path)
    policy_info = _groot_policy_info_from_replay(saved_replay)
    policy_output = _require_json_object(saved_replay["policy_output"], "GR00T replay output")
    raw_actions = _require_json_object(policy_output["raw_actions"], "GR00T replay raw actions")
    provider_info = _require_json_object(
        policy_output.get("provider_info", {}),
        "GR00T replay provider_info",
    )

    class ReplayPolicyClient:
        def __init__(self) -> None:
            self.get_action_calls = 0

        def ping(self) -> bool:
            return True

        def get_action(self, _observation: object, options: object | None = None) -> object:
            self.get_action_calls += 1
            if options not in (None, {}):
                raise ProviderError("GR00T replay does not support policy options.")
            return (
                json.loads(json.dumps(raw_actions)),
                json.loads(json.dumps(provider_info)),
            )

    def translator(raw: object, _info: JSONDict, _provider_info: JSONDict):
        actions = _require_json_object(raw, "GR00T replay translator raw actions")
        _validate_groot_raw_actions(actions)
        eef_rows = _groot_eef_rows(actions)
        return [Action.move_to(float(row[0]), float(row[1]), float(row[2])) for row in eef_rows]

    client = ReplayPolicyClient()
    provider = GrootPolicyClientProvider(
        policy_client=client,
        embodiment_tag=_GROOT_REPLAY_EMBODIMENT_TAG,
        action_translator=translator,
        event_handler=events.append,
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

    metadata = result.metadata
    normalized_raw_actions = _require_json_object(result.raw_actions, "GR00T raw actions")
    raw_action_shapes = _groot_raw_action_shapes(normalized_raw_actions)
    raw_action_preview = _groot_action_preview(normalized_raw_actions)
    selected_action_preview = [action.to_dict() for action in result.actions[:8]]
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
    summary: JSONDict = {
        "demo_kind": "gr00t_saved_replay",
        "state_dir": str(state_dir),
        "providers": [result.provider],
        "model": _GROOT_REPLAY_MODEL,
        "task_description": _GROOT_REPLAY_TASK,
        "runtime": metadata.get("runtime"),
        "runtime_contract": "saved PolicyClient replay through GrootPolicyClientProvider",
        "loaded_replay_artifact": replay_source_path.name,
        "health": health.to_dict(),
        "raw_action_shapes": raw_action_shapes,
        "translated_action_count": len(result.actions),
        "action_horizon": result.action_horizon,
        "embodiment_tag": result.embodiment_tag,
        "candidate_count": metadata.get("candidate_count"),
        "policy_select_calls": client.get_action_calls,
        "latency_ms": _GROOT_REPLAY_LATENCY_MS,
        "result_digest": _GROOT_REPLAY_RESULT_DIGEST,
        "selected_actions": [action.to_dict() for action in result.actions],
        "selected_action_preview": selected_action_preview,
        "raw_action_preview": raw_action_preview,
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "harness_artifacts": {
            "gr00t_replay": {
                "path": "artifacts/gr00t-replay.json",
                "payload": replay_artifact,
            },
        },
    }
    if emit:
        print("\n".join(_transcript_for("gr00t-replay", summary)))
    return summary


def _write_prepared_groot_replay_artifact(state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    replay_path = state_dir / "gr00t-prepared-replay.json"
    replay_path.write_text(
        json.dumps(_groot_saved_replay_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return replay_path


def _groot_saved_replay_payload() -> JSONDict:
    raw_actions = _groot_raw_actions()
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


def _load_groot_replay_artifact(path: Path) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorldStateError(f"GR00T replay artifact is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise WorldStateError("GR00T replay artifact must be a JSON object.")
    if set(payload) != _GROOT_REPLAY_TOP_LEVEL_KEYS:
        raise WorldStateError("GR00T replay artifact contains unsupported top-level fields.")
    if payload.get("schema_version") != _GROOT_REPLAY_SCHEMA_VERSION:
        raise WorldStateError("GR00T replay artifact schema_version is unsupported.")
    if not isinstance(payload.get("source"), str) or not payload["source"]:
        raise WorldStateError("GR00T replay artifact source must be a non-empty string.")

    manifest = _require_json_object(payload.get("manifest"), "GR00T replay manifest")
    if set(manifest) != _GROOT_REPLAY_MANIFEST_KEYS:
        raise WorldStateError("GR00T replay manifest contains unsupported fields.")
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

    request = _require_json_object(payload.get("request"), "GR00T replay request")
    if set(request) != _GROOT_REPLAY_REQUEST_KEYS:
        raise WorldStateError("GR00T replay request contains unsupported fields.")
    if request.get("observation_fields") != list(_GROOT_REPLAY_OBSERVATION_FIELDS):
        raise WorldStateError("GR00T replay observation fields are unsupported.")
    _validate_groot_observation_summary(request.get("observation_summary"))
    if not isinstance(request.get("task_description"), str) or not request["task_description"]:
        raise WorldStateError("GR00T replay task_description must be a non-empty string.")
    if request.get("action_horizon") != _GROOT_REPLAY_ACTION_HORIZON:
        raise WorldStateError("GR00T replay request action_horizon is unsupported.")
    if request.get("embodiment_tag") != _GROOT_REPLAY_EMBODIMENT_TAG:
        raise WorldStateError("GR00T replay request embodiment_tag is unsupported.")

    policy_output = _require_json_object(payload.get("policy_output"), "GR00T replay output")
    if set(policy_output) != _GROOT_REPLAY_POLICY_OUTPUT_KEYS:
        raise WorldStateError("GR00T replay policy_output contains unsupported fields.")
    raw_actions = _require_json_object(policy_output.get("raw_actions"), "GR00T replay raw_actions")
    _validate_groot_raw_actions(raw_actions)
    _validate_groot_provider_info(policy_output.get("provider_info", {}))
    response = _require_json_object(payload.get("response"), "GR00T replay response")
    if set(response) != _GROOT_REPLAY_RESPONSE_KEYS:
        raise WorldStateError("GR00T replay response contains unsupported fields.")
    if response.get("raw_action_shapes") != _GROOT_REPLAY_RAW_ACTION_SHAPES:
        raise WorldStateError("GR00T replay response raw_action_shapes are unsupported.")
    if response.get("translated_action_count") != 0:
        raise WorldStateError("GR00T replay seed response translated_action_count must be zero.")
    if response.get("raw_action_preview") != [] or response.get("selected_action_preview") != []:
        raise WorldStateError("GR00T replay seed response previews must be empty.")
    _validate_groot_latency(response.get("latency_ms"), "GR00T replay response latency_ms")
    if payload.get("translated_actions") != []:
        raise WorldStateError("GR00T replay seed translated_actions must be empty.")
    if payload.get("provider_events") != []:
        raise WorldStateError("GR00T replay seed provider_events must be empty.")
    return payload


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
            "gr00t_replay": {
                "path": "artifacts/gr00t-replay.json",
                "payload": replay_artifact,
            },
        },
    }


def _groot_raw_actions() -> JSONDict:
    return {
        "eef_9d": [[_groot_eef_row(index) for index in range(_GROOT_REPLAY_ACTION_HORIZON)]],
        "gripper_position": [
            [_groot_gripper_row(index) for index in range(_GROOT_REPLAY_ACTION_HORIZON)]
        ],
        "joint_position": [
            [_groot_joint_row(index) for index in range(_GROOT_REPLAY_ACTION_HORIZON)]
        ],
    }


def _groot_eef_row(index: int) -> list[float]:
    if index < len(_GROOT_REPLAY_EEF_PREFIX_ROWS):
        return list(_GROOT_REPLAY_EEF_PREFIX_ROWS[index])
    return [
        round(0.454 - index * 0.00034 + math.sin(index) * 0.0011, 8),
        round(-0.052 + index * 0.00052 + math.cos(index) * 0.0010, 8),
        round(0.351 + index * 0.00318 + math.sin(index / 2) * 0.0012, 8),
        round(0.985 - index * 0.00135, 8),
        round(-0.058 - index * 0.00195, 8),
        round(-0.164 - index * 0.00485, 8),
        round(0.076 + index * 0.0023, 8),
        round(0.992 - index * 0.0012, 8),
        round(0.102 + index * 0.0042, 8),
    ]


def _groot_gripper_row(index: int) -> list[float]:
    if index < len(_GROOT_REPLAY_GRIPPER_PREFIX_ROWS):
        return list(_GROOT_REPLAY_GRIPPER_PREFIX_ROWS[index])
    return [round(0.00195312 * (index % 4), 8)]


def _groot_joint_row(index: int) -> list[float]:
    if index < len(_GROOT_REPLAY_JOINT_PREFIX_ROWS):
        return list(_GROOT_REPLAY_JOINT_PREFIX_ROWS[index])
    return [
        round(-0.180 - index * 0.0023, 8),
        round(-0.430 - index * 0.0021, 8),
        round(-0.099 + index * 0.00035, 8),
        round(-2.187 + index * 0.00095, 8),
        round(-0.327 - index * 0.0052, 8),
        round(2.130 + index * 0.0011, 8),
        round(0.336 - index * 0.0033, 8),
    ]


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


def _validate_numeric_tensor(value: object, *, expected_shape: Sequence[int], name: str) -> None:
    if not expected_shape:
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise WorldStateError(f"{name} must contain finite numeric values.")
        return
    if not isinstance(value, list):
        raise WorldStateError(f"{name} must have shape {list(expected_shape)}.")
    if len(value) != expected_shape[0]:
        raise WorldStateError(f"{name} must have shape {list(expected_shape)}.")
    for index, item in enumerate(value):
        _validate_numeric_tensor(
            item,
            expected_shape=expected_shape[1:],
            name=f"{name}[{index}]",
        )


def _groot_raw_action_shapes(raw_actions: JSONDict) -> JSONDict:
    _validate_groot_raw_actions(raw_actions)
    return dict(_GROOT_REPLAY_RAW_ACTION_SHAPES)


def _groot_eef_rows(raw_actions: JSONDict) -> list[list[float]]:
    eef = raw_actions["eef_9d"]
    if not isinstance(eef, list) or not eef or not isinstance(eef[0], list):
        raise WorldStateError("GR00T replay eef_9d must contain one batch of action rows.")
    rows = eef[0]
    if not all(isinstance(row, list) for row in rows):
        raise WorldStateError("GR00T replay eef_9d rows must be lists.")
    return rows


def _groot_action_preview(raw_actions: JSONDict, *, limit: int = 8) -> list[list[float]]:
    _validate_groot_raw_actions(raw_actions)
    eef_rows = _groot_eef_rows(raw_actions)
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


# Demo modules import the optional-runtime provider classes at module scope, so
# keep these imports lazy: loading the harness should not pull LeRobot/LeWorldModel
# adapters into the base cold-start path.
def _run_leworldmodel_demo(**kwargs: object) -> JSONDict:
    from worldforge.demos import leworldmodel_e2e

    return leworldmodel_e2e.run_demo(**kwargs)  # type: ignore[arg-type]


def _run_lerobot_demo(**kwargs: object) -> JSONDict:
    from worldforge.demos import lerobot_e2e

    return lerobot_e2e.run_demo(**kwargs)  # type: ignore[arg-type]


def _run_robotics_compare_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    subflows = {
        "lerobot": _run_lerobot_demo(state_dir=state_dir / "lerobot", emit=False),
        "cosmos-policy": _run_cosmos_policy_demo(
            state_dir=state_dir / "cosmos-policy",
            emit=False,
        ),
        "gr00t-replay": _run_gr00t_replay_demo(
            state_dir=state_dir / "gr00t-replay",
            emit=False,
        ),
    }
    validation_errors = _robotics_compare_validation_errors(subflows)
    source_validation = _robotics_compare_source_validation()
    if validation_errors:
        comparison_payload: JSONDict = {
            "schema_version": 1,
            "flow_id": "robotics-compare",
            "status": "failed",
            "source_validation": source_validation,
            "validation_errors": validation_errors,
            "artifacts": {
                "cosmos_policy_replay": "artifacts/cosmos-policy-replay.json",
                "gr00t_replay": "artifacts/gr00t-replay.json",
            },
            "notes": [
                "At least one subflow failed before comparison rows could be normalized.",
                "Available sanitized replay artifacts are still preserved for triage.",
            ],
        }
        provider_events = _robotics_compare_provider_events(
            subflows,
            validation_errors=validation_errors,
        )
        summary: JSONDict = {
            "demo_kind": "robotics_policy_replay_comparison",
            "state_dir": str(state_dir),
            "status": "failed",
            "providers": ["lerobot", "cosmos-policy", "gr00t"],
            "flow_ids": list(subflows),
            "comparison_count": len(subflows),
            "gpu_required": False,
            "source_validation": source_validation,
            "event_phases": [str(event.get("phase", "unknown")) for event in provider_events],
            "provider_events": provider_events,
            "validation_errors": validation_errors,
            "harness_artifacts": _robotics_compare_artifacts(
                subflows,
                comparison_payload,
                require_replays=False,
            ),
        }
        if emit:
            print("\n".join(_transcript_for("robotics-compare", summary)))
        return summary

    rows = [
        _robotics_compare_lerobot_row(subflows["lerobot"]),
        _robotics_compare_cosmos_row(subflows["cosmos-policy"]),
        _robotics_compare_groot_row(subflows["gr00t-replay"]),
    ]
    provider_events = _robotics_compare_provider_events(subflows, rows=rows)
    comparison_payload: JSONDict = {
        "schema_version": 1,
        "flow_id": "robotics-compare",
        "status": "completed",
        "source_validation": source_validation,
        "rows": rows,
        "artifacts": {
            "cosmos_policy_replay": "artifacts/cosmos-policy-replay.json",
            "gr00t_replay": "artifacts/gr00t-replay.json",
        },
        "notes": [
            "WorldForge owns the common policy contract, validation, events, and replay surface.",
            "Robotics model runtimes remain host-owned and are not required for this replay.",
        ],
    }
    summary: JSONDict = {
        "demo_kind": "robotics_policy_replay_comparison",
        "state_dir": str(state_dir),
        "providers": [str(row["provider"]) for row in rows],
        "flow_ids": [str(row["flow_id"]) for row in rows],
        "comparison_count": len(rows),
        "rows": rows,
        "total_translated_actions": sum(int(row["translated_action_count"]) for row in rows),
        "gpu_required": False,
        "source_validation": comparison_payload["source_validation"],
        "event_phases": [str(event.get("phase", "unknown")) for event in provider_events],
        "provider_events": provider_events,
        "harness_artifacts": _robotics_compare_artifacts(
            subflows,
            comparison_payload,
            require_replays=True,
        ),
    }
    if emit:
        print("\n".join(_transcript_for("robotics-compare", summary)))
    return summary


def _robotics_compare_source_validation() -> JSONDict:
    return {
        "lerobot": "deterministic checkout-safe provider demo",
        "cosmos-policy": "validated live on RTX A6000; committed artifact is sanitized",
        "gr00t-replay": "validated live on RTX A6000; committed artifact is sanitized",
    }


def _robotics_compare_validation_errors(subflows: dict[str, JSONDict]) -> list[str]:
    errors: list[str] = []
    for flow_id, summary in subflows.items():
        flow_errors = summary.get("validation_errors")
        if isinstance(flow_errors, list):
            errors.extend(f"{flow_id}: {error}" for error in flow_errors)
    return errors


def _robotics_compare_provider_events(
    subflows: dict[str, JSONDict],
    *,
    rows: list[JSONDict] | None = None,
    validation_errors: list[str] | None = None,
) -> list[JSONDict]:
    events: list[JSONDict] = []
    for subflow_id, summary in subflows.items():
        events.extend(_robotics_compare_subflow_events(subflow_id, summary))
    if rows is not None:
        events.extend(
            ProviderEvent(
                provider=str(row["provider"]),
                operation="robotics-compare",
                phase="success",
                message=f"{row['flow_id']} policy output compared",
                metadata={
                    "flow_id": row["flow_id"],
                    "raw_shape": row["raw_shape"],
                    "translated_action_count": row["translated_action_count"],
                },
            ).to_dict()
            for row in rows
        )
    if validation_errors:
        events.append(
            ProviderEvent(
                provider="robotics-compare",
                operation="robotics-compare",
                phase="failure",
                message="; ".join(validation_errors),
                metadata={"failed": True},
            ).to_dict()
        )
    return events


def _robotics_compare_subflow_events(subflow_id: str, summary: JSONDict) -> list[JSONDict]:
    events = summary.get("provider_events")
    if not isinstance(events, list):
        return []
    tagged: list[JSONDict] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        copied = dict(event)
        metadata = copied.get("metadata")
        copied["metadata"] = {
            **(metadata if isinstance(metadata, dict) else {}),
            "comparison_flow_id": "robotics-compare",
            "subflow_id": subflow_id,
        }
        tagged.append(copied)
    return tagged


def _robotics_compare_artifacts(
    subflows: dict[str, JSONDict],
    comparison_payload: JSONDict,
    *,
    require_replays: bool,
) -> JSONDict:
    artifacts: JSONDict = {
        "robotics_comparison": {
            "path": "artifacts/robotics-policy-comparison.json",
            "payload": comparison_payload,
        },
    }
    replay_artifacts = (
        ("cosmos-policy", "cosmos_policy_replay", "artifacts/cosmos-policy-replay.json"),
        ("gr00t-replay", "gr00t_replay", "artifacts/gr00t-replay.json"),
    )
    for flow_id, name, path in replay_artifacts:
        try:
            payload = _harness_artifact_payload(subflows[flow_id], name)
        except WorldStateError:
            if require_replays:
                raise
            continue
        artifacts[name] = {"path": path, "payload": payload}
    return artifacts


def _robotics_compare_lerobot_row(summary: JSONDict) -> JSONDict:
    try:
        selected_index = int(summary["selected_candidate_index"])
        candidate_costs = list(summary["candidate_costs"])
        selected_cost = candidate_costs[selected_index]
        return {
            "flow_id": "lerobot",
            "provider": "lerobot",
            "model": "injected deterministic LeRobot-shaped policy",
            "source": "checkout-safe policy plus score demo",
            "raw_shape": f"{summary['policy_candidate_count']} candidate chunks",
            "candidate_count": int(summary["policy_candidate_count"]),
            "selected_candidate_index": selected_index,
            "selected_score": float(selected_cost),
            "translated_action_count": len(summary["selected_actions"]),
            "events": len(summary.get("event_phases", [])),
            "artifact": "run summary only",
        }
    except KeyError as exc:
        raise WorldStateError(f"lerobot comparison summary missing required key {exc!s}.") from exc
    except (IndexError, TypeError, ValueError) as exc:
        raise WorldStateError(f"lerobot comparison summary is malformed: {exc}") from exc


def _robotics_compare_cosmos_row(summary: JSONDict) -> JSONDict:
    try:
        raw_shape = " x ".join(str(item) for item in summary["raw_action_shape"])
        return {
            "flow_id": "cosmos-policy",
            "provider": str(summary["providers"][0]),
            "model": summary["model"],
            "source": "sanitized ALOHA /act replay",
            "raw_shape": raw_shape,
            "candidate_count": int(summary["candidate_count"]),
            "selected_candidate_index": int(summary["selected_candidate_index"]),
            "value_prediction": summary["value_prediction"],
            "translated_action_count": int(summary["translated_action_count"]),
            "events": len(summary.get("event_phases", [])),
            "artifact": "artifacts/cosmos-policy-replay.json",
        }
    except KeyError as exc:
        raise WorldStateError(
            f"cosmos-policy comparison summary missing required key {exc!s}."
        ) from exc
    except (IndexError, TypeError, ValueError) as exc:
        raise WorldStateError(f"cosmos-policy comparison summary is malformed: {exc}") from exc


def _robotics_compare_groot_row(summary: JSONDict) -> JSONDict:
    try:
        return {
            "flow_id": "gr00t-replay",
            "provider": str(summary["providers"][0]),
            "model": summary["model"],
            "source": "sanitized GR00T PolicyClient replay",
            "raw_shape": _groot_shape_result(summary),
            "raw_tensor_count": len(summary["raw_action_shapes"]),
            "embodiment_tag": summary["embodiment_tag"],
            "latency_ms": summary["latency_ms"],
            "translated_action_count": int(summary["translated_action_count"]),
            "events": len(summary.get("event_phases", [])),
            "artifact": "artifacts/gr00t-replay.json",
        }
    except KeyError as exc:
        raise WorldStateError(
            f"gr00t-replay comparison summary missing required key {exc!s}."
        ) from exc
    except (IndexError, TypeError, ValueError) as exc:
        raise WorldStateError(f"gr00t-replay comparison summary is malformed: {exc}") from exc


def _harness_artifact_payload(summary: JSONDict, name: str) -> JSONDict:
    artifacts = summary.get("harness_artifacts")
    if not isinstance(artifacts, dict):
        raise WorldStateError(f"{name} source flow did not expose harness artifacts.")
    descriptor = artifacts.get(name)
    if not isinstance(descriptor, dict) or "payload" not in descriptor:
        raise WorldStateError(f"{name} source flow did not expose an artifact payload.")
    payload = descriptor["payload"]
    if not isinstance(payload, dict):
        raise WorldStateError(f"{name} source flow artifact payload must be a JSON object.")
    return payload


_RUNNERS: dict[str, FlowRunner] = {
    "leworldmodel": _run_leworldmodel_demo,
    "lerobot": _run_lerobot_demo,
    "cosmos-policy": _run_cosmos_policy_demo,
    "gr00t-replay": _run_gr00t_replay_demo,
    "robotics-compare": _run_robotics_compare_demo,
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
    if flow_id == "gr00t-replay":
        return (
            HarnessStep(
                "Load saved PolicyClient replay",
                "Use a sanitized GR00T N1.7 response shape from the live GPU smoke.",
                "Checkout-safe replay loaded; no GPU or network call is required.",
                f"task={summary['task_description']}",
            ),
            HarnessStep(
                "Check provider boundary",
                "Instantiate GrootPolicyClientProvider with an injected replay client.",
                "Provider health is configured for PolicyClient.get_action.",
                f"model={summary['model']}",
            ),
            HarnessStep(
                "Call GR00T adapter",
                "Route the replay through the same policy provider event path.",
                f"{summary['policy_select_calls']} get_action call handled.",
                f"embodiment={summary['embodiment_tag']}",
            ),
            HarnessStep(
                "Validate raw tensors",
                "Check named eef, gripper, and joint tensors before translation.",
                _groot_shape_result(summary),
                "raw=eef_9d,gripper_position,joint_position",
            ),
            HarnessStep(
                "Translate actions",
                "Map GR00T end-effector rows into executable WorldForge Action objects.",
                f"{summary['translated_action_count']} move_to actions produced.",
                f"latency_ms={float(summary['latency_ms']):.1f}",
            ),
            HarnessStep(
                "Preserve replay artifact",
                "Write the inspector state, provider events, and sanitized replay artifact.",
                "artifact=artifacts/gr00t-replay.json",
                f"events={', '.join(summary['event_phases'])}",
            ),
        )
    if flow_id == "robotics-compare":
        rows_by_flow = {str(row["flow_id"]): row for row in summary["rows"]}
        return (
            HarnessStep(
                "Run LeRobot policy path",
                "Execute the checkout-safe LeRobot policy-plus-score flow.",
                (
                    f"{rows_by_flow['lerobot']['candidate_count']} candidate chunks, "
                    f"selected #{rows_by_flow['lerobot']['selected_candidate_index']}."
                ),
                f"translated_actions={rows_by_flow['lerobot']['translated_action_count']}",
            ),
            HarnessStep(
                "Replay Cosmos-Policy /act",
                "Route the sanitized ALOHA replay through CosmosPolicyProvider.",
                f"raw action shape {rows_by_flow['cosmos-policy']['raw_shape']}.",
                f"translated_actions={rows_by_flow['cosmos-policy']['translated_action_count']}",
            ),
            HarnessStep(
                "Replay GR00T PolicyClient",
                "Route the sanitized DROID replay through GrootPolicyClientProvider.",
                str(rows_by_flow["gr00t-replay"]["raw_shape"]),
                f"translated_actions={rows_by_flow['gr00t-replay']['translated_action_count']}",
            ),
            HarnessStep(
                "Normalize policy contracts",
                (
                    "Compare provider outputs by shape, selected candidate, and translated "
                    "action count."
                ),
                f"{summary['comparison_count']} policy surfaces normalized.",
                f"total_translated_actions={summary['total_translated_actions']}",
            ),
            HarnessStep(
                "Inspect provider events",
                "Record a comparable event for each policy surface.",
                _event_result(summary),
                f"events={len(summary['event_phases'])}",
            ),
            HarnessStep(
                "Preserve comparison artifact",
                "Write a sanitized comparison plus replay artifacts for offline inspection.",
                "artifact=artifacts/robotics-policy-comparison.json",
                "gpu_required=false",
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
    if flow_id == "gr00t-replay":
        return (
            HarnessMetric("Flow", "policy", "GR00T PolicyClient contract replay"),
            HarnessMetric(
                "Raw tensors",
                str(len(summary["raw_action_shapes"])),
                _groot_shape_result(summary),
            ),
            HarnessMetric(
                "Translated",
                str(summary["translated_action_count"]),
                "WorldForge Action objects",
            ),
            HarnessMetric(
                "Latency",
                _format_ms(summary["latency_ms"]),
                "live-smoke reference latency",
            ),
            HarnessMetric(
                "Events",
                str(len(summary["event_phases"])),
                ", ".join(summary["event_phases"]),
            ),
            HarnessMetric("Artifact", "replay", "artifacts/gr00t-replay.json"),
        )
    if flow_id == "robotics-compare":
        rows_by_flow = {str(row["flow_id"]): row for row in summary["rows"]}
        return (
            HarnessMetric("Flow", "policy comparison", "three robotics policy surfaces"),
            HarnessMetric(
                "LeRobot",
                f"{rows_by_flow['lerobot']['candidate_count']} candidates",
                f"selected #{rows_by_flow['lerobot']['selected_candidate_index']}",
            ),
            HarnessMetric(
                "Cosmos",
                str(rows_by_flow["cosmos-policy"]["raw_shape"]),
                f"value={_format_optional_float(rows_by_flow['cosmos-policy']['value_prediction'])}",
            ),
            HarnessMetric(
                "GR00T",
                str(rows_by_flow["gr00t-replay"]["raw_tensor_count"]),
                "named action tensors",
            ),
            HarnessMetric(
                "Translated",
                str(summary["total_translated_actions"]),
                "WorldForge Action objects",
            ),
            HarnessMetric(
                "Artifacts",
                "3",
                "comparison plus replay artifacts",
            ),
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
    if flow_id == "gr00t-replay":
        return (
            "flow: gr00t-replay",
            f"provider: {', '.join(summary['providers'])}",
            f"model: {summary['model']}",
            f"task: {summary['task_description']}",
            f"embodiment_tag: {summary['embodiment_tag']}",
            f"health: {summary['health']['healthy']}",
            f"raw_action_shapes: {summary['raw_action_shapes']}",
            f"translated_actions: {summary['translated_action_count']}",
            f"latency_ms: {float(summary['latency_ms']):.1f}",
            f"result_digest: {summary['result_digest']}",
            "saved_replay_artifact: artifacts/gr00t-replay.json",
            f"events: {', '.join(summary['event_phases'])}",
        )
    if flow_id == "robotics-compare":
        rows_by_flow = {str(row["flow_id"]): row for row in summary["rows"]}
        return (
            "flow: robotics-compare",
            f"providers: {', '.join(summary['providers'])}",
            f"flow_ids: {', '.join(summary['flow_ids'])}",
            "gpu_required: false",
            (
                "lerobot: "
                f"candidates={rows_by_flow['lerobot']['candidate_count']} "
                f"selected=#{rows_by_flow['lerobot']['selected_candidate_index']} "
                f"translated_actions={rows_by_flow['lerobot']['translated_action_count']}"
            ),
            (
                "cosmos-policy: "
                f"raw_shape={rows_by_flow['cosmos-policy']['raw_shape']} "
                f"translated_actions={rows_by_flow['cosmos-policy']['translated_action_count']} "
                "value_prediction="
                f"{_format_optional_float(rows_by_flow['cosmos-policy']['value_prediction'])}"
            ),
            (
                "gr00t-replay: "
                f"raw_tensors={rows_by_flow['gr00t-replay']['raw_tensor_count']} "
                f"translated_actions={rows_by_flow['gr00t-replay']['translated_action_count']} "
                f"latency_ms={_format_ms(rows_by_flow['gr00t-replay']['latency_ms'])}"
            ),
            f"total_translated_actions: {summary['total_translated_actions']}",
            "comparison_artifact: artifacts/robotics-policy-comparison.json",
            "replay_artifacts: artifacts/cosmos-policy-replay.json, artifacts/gr00t-replay.json",
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


def _groot_shape_result(summary: JSONDict) -> str:
    shapes = summary["raw_action_shapes"]
    return ", ".join(
        f"{name}={' x '.join(str(item) for item in shape)}"
        for name, shape in sorted(shapes.items())
    )


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
