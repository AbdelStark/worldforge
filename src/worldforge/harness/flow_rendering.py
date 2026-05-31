"""Render harness flow summaries into steps, metrics, transcripts, and events."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from pathlib import Path

from worldforge.harness.flow_artifacts import (
    COSMOS_POLICY_REPLAY_ARTIFACT,
    GROOT_REPLAY_ARTIFACT,
    ROBOTICS_COMPARISON_ARTIFACT,
)
from worldforge.harness.flow_events import provider_events_for as provider_events_for
from worldforge.harness.models import HarnessMetric, HarnessStep
from worldforge.models import JSONDict

StepBuilder = Callable[[JSONDict], tuple[HarnessStep, ...]]
MetricBuilder = Callable[[JSONDict], tuple[HarnessMetric, ...]]
TranscriptBuilder = Callable[[JSONDict], tuple[str, ...]]


def steps_for(flow_id: str, summary: JSONDict) -> tuple[HarnessStep, ...]:
    validation_errors = _validation_errors(summary)
    if validation_errors:
        return _failure_steps(summary, validation_errors)
    return _build_known_flow(flow_id, summary, _STEP_BUILDERS)


def metrics_for(flow_id: str, summary: JSONDict) -> tuple[HarnessMetric, ...]:
    validation_errors = _validation_errors(summary)
    if validation_errors:
        return _failure_metrics(summary, validation_errors)
    return _build_known_flow(flow_id, summary, _METRIC_BUILDERS)


def transcript_for(flow_id: str, summary: JSONDict) -> tuple[str, ...]:
    validation_errors = _validation_errors(summary)
    if validation_errors:
        return _failure_transcript(flow_id, summary, validation_errors)
    return _build_known_flow(flow_id, summary, _TRANSCRIPT_BUILDERS)


def _build_known_flow[BuildResult](
    flow_id: str,
    summary: JSONDict,
    builders: Mapping[str, Callable[[JSONDict], BuildResult]],
) -> BuildResult:
    try:
        builder = builders[flow_id]
    except KeyError as exc:
        raise ValueError(f"unknown harness flow '{flow_id}'") from exc
    return builder(summary)


def _validation_errors(summary: JSONDict) -> tuple[object, ...]:
    validation_errors = summary.get("validation_errors")
    if isinstance(validation_errors, list):
        return tuple(validation_errors)
    return ()


def groot_shape_result(summary: JSONDict) -> str:
    shapes = summary["raw_action_shapes"]
    return ", ".join(
        f"{name}={' x '.join(str(item) for item in shape)}"
        for name, shape in sorted(shapes.items())
    )


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


def _failure_steps(
    summary: JSONDict,
    validation_errors: tuple[object, ...],
) -> tuple[HarnessStep, ...]:
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


def _leworldmodel_steps(summary: JSONDict) -> tuple[HarnessStep, ...]:
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


def _lerobot_steps(summary: JSONDict) -> tuple[HarnessStep, ...]:
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
            "Execute selected WorldForge actions, save the final world, and reload it from disk.",
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


def _cosmos_policy_steps(summary: JSONDict) -> tuple[HarnessStep, ...]:
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
            f"artifact={COSMOS_POLICY_REPLAY_ARTIFACT.path}",
            f"events={', '.join(summary['event_phases'])}",
        ),
    )


def _gr00t_replay_steps(summary: JSONDict) -> tuple[HarnessStep, ...]:
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
            groot_shape_result(summary),
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
            f"artifact={GROOT_REPLAY_ARTIFACT.path}",
            f"events={', '.join(summary['event_phases'])}",
        ),
    )


def _robotics_compare_steps(summary: JSONDict) -> tuple[HarnessStep, ...]:
    rows_by_flow = _robotics_compare_rows_by_flow(summary)
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
            "Compare provider outputs by shape, selected candidate, and translated action count.",
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
            f"artifact={ROBOTICS_COMPARISON_ARTIFACT.path}",
            "gpu_required=false",
        ),
    )


def _diagnostics_steps(summary: JSONDict) -> tuple[HarnessStep, ...]:
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
            "Execute mock benchmark samples across predict and embed.",
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


def _workbench_steps(summary: JSONDict) -> tuple[HarnessStep, ...]:
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
            (f"jepa-wms stable gaps: {', '.join(candidate_missing.get('stable', [])) or 'none'}."),
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


_STEP_BUILDERS: dict[str, StepBuilder] = {
    "leworldmodel": _leworldmodel_steps,
    "lerobot": _lerobot_steps,
    "cosmos-policy": _cosmos_policy_steps,
    "gr00t-replay": _gr00t_replay_steps,
    "robotics-compare": _robotics_compare_steps,
    "diagnostics": _diagnostics_steps,
    "workbench": _workbench_steps,
}


def _failure_metrics(
    summary: JSONDict,
    validation_errors: tuple[object, ...],
) -> tuple[HarnessMetric, ...]:
    return (
        HarnessMetric("Status", "failed", "run manifest preserved for reproduction"),
        HarnessMetric("Events", str(len(summary.get("event_phases", []))), "failure"),
        HarnessMetric("Errors", str(len(validation_errors)), str(validation_errors[0])),
    )


def _diagnostics_metrics(summary: JSONDict) -> tuple[HarnessMetric, ...]:
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


def _workbench_metrics(summary: JSONDict) -> tuple[HarnessMetric, ...]:
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


def _cosmos_policy_metrics(summary: JSONDict) -> tuple[HarnessMetric, ...]:
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
        HarnessMetric("Artifact", "replay", COSMOS_POLICY_REPLAY_ARTIFACT.path),
    )


def _gr00t_replay_metrics(summary: JSONDict) -> tuple[HarnessMetric, ...]:
    return (
        HarnessMetric("Flow", "policy", "GR00T PolicyClient contract replay"),
        HarnessMetric(
            "Raw tensors",
            str(len(summary["raw_action_shapes"])),
            groot_shape_result(summary),
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
        HarnessMetric("Artifact", "replay", GROOT_REPLAY_ARTIFACT.path),
    )


def _robotics_compare_metrics(summary: JSONDict) -> tuple[HarnessMetric, ...]:
    rows_by_flow = _robotics_compare_rows_by_flow(summary)
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


def _planning_metrics(flow_label: str, summary: JSONDict) -> tuple[HarnessMetric, ...]:
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


def _leworldmodel_metrics(summary: JSONDict) -> tuple[HarnessMetric, ...]:
    return _planning_metrics("score", summary)


def _lerobot_metrics(summary: JSONDict) -> tuple[HarnessMetric, ...]:
    return _planning_metrics("policy+score", summary)


_METRIC_BUILDERS: dict[str, MetricBuilder] = {
    "leworldmodel": _leworldmodel_metrics,
    "lerobot": _lerobot_metrics,
    "cosmos-policy": _cosmos_policy_metrics,
    "gr00t-replay": _gr00t_replay_metrics,
    "robotics-compare": _robotics_compare_metrics,
    "diagnostics": _diagnostics_metrics,
    "workbench": _workbench_metrics,
}


def _failure_transcript(
    flow_id: str,
    summary: JSONDict,
    validation_errors: tuple[object, ...],
) -> tuple[str, ...]:
    return (
        f"flow: {flow_id}",
        "status: failed",
        f"state_dir: {summary.get('state_dir', '')}",
        f"validation_errors: {' | '.join(str(error) for error in validation_errors)}",
        f"events: {', '.join(str(phase) for phase in summary.get('event_phases', []))}",
    )


def _diagnostics_transcript(summary: JSONDict) -> tuple[str, ...]:
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


def _workbench_transcript(summary: JSONDict) -> tuple[str, ...]:
    candidate_missing = summary["missing_evidence_by_provider"]["jepa-wms"]
    return (
        "flow: workbench",
        f"providers: {', '.join(summary['providers'])}",
        f"passed: {summary['passed_count']}/{summary['report_count']}",
        f"jepa-wms_missing_stable: {', '.join(candidate_missing.get('stable', [])) or 'none'}",
        f"safe_artifacts: {summary['safe_artifact_count']}",
        f"validation_commands: {' | '.join(summary['validation_commands'])}",
    )


def _cosmos_policy_transcript(summary: JSONDict) -> tuple[str, ...]:
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
        f"saved_replay_artifact: {COSMOS_POLICY_REPLAY_ARTIFACT.path}",
        f"events: {', '.join(summary['event_phases'])}",
    )


def _gr00t_replay_transcript(summary: JSONDict) -> tuple[str, ...]:
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
        f"saved_replay_artifact: {GROOT_REPLAY_ARTIFACT.path}",
        f"events: {', '.join(summary['event_phases'])}",
    )


def _robotics_compare_transcript(summary: JSONDict) -> tuple[str, ...]:
    rows_by_flow = _robotics_compare_rows_by_flow(summary)
    return (
        "flow: robotics-compare",
        f"providers: {', '.join(summary['providers'])}",
        f"flow_ids: {', '.join(summary['flow_ids'])}",
        "gpu_required: false",
        _lerobot_comparison_line(rows_by_flow["lerobot"]),
        _cosmos_policy_comparison_line(rows_by_flow["cosmos-policy"]),
        _gr00t_comparison_line(rows_by_flow["gr00t-replay"]),
        f"total_translated_actions: {summary['total_translated_actions']}",
        f"comparison_artifact: {ROBOTICS_COMPARISON_ARTIFACT.path}",
        f"replay_artifacts: {COSMOS_POLICY_REPLAY_ARTIFACT.path}, {GROOT_REPLAY_ARTIFACT.path}",
        f"events: {', '.join(summary['event_phases'])}",
    )


def _robotics_compare_rows_by_flow(summary: JSONDict) -> dict[str, JSONDict]:
    return {str(row["flow_id"]): row for row in summary["rows"]}


def _lerobot_comparison_line(row: JSONDict) -> str:
    return (
        "lerobot: "
        f"candidates={row['candidate_count']} "
        f"selected=#{row['selected_candidate_index']} "
        f"translated_actions={row['translated_action_count']}"
    )


def _cosmos_policy_comparison_line(row: JSONDict) -> str:
    return (
        "cosmos-policy: "
        f"raw_shape={row['raw_shape']} "
        f"translated_actions={row['translated_action_count']} "
        f"value_prediction={_format_optional_float(row['value_prediction'])}"
    )


def _gr00t_comparison_line(row: JSONDict) -> str:
    return (
        "gr00t-replay: "
        f"raw_tensors={row['raw_tensor_count']} "
        f"translated_actions={row['translated_action_count']} "
        f"latency_ms={_format_ms(row['latency_ms'])}"
    )


def _planning_transcript(flow_id: str, summary: JSONDict) -> tuple[str, ...]:
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
    return tuple(lines)


def _leworldmodel_transcript(summary: JSONDict) -> tuple[str, ...]:
    return _planning_transcript("leworldmodel", summary)


def _lerobot_transcript(summary: JSONDict) -> tuple[str, ...]:
    return (
        *_planning_transcript("lerobot", summary),
        f"policy_candidate_count: {summary['policy_candidate_count']}",
        f"policy_select_calls: {summary['policy_select_calls']}",
        f"policy_reset_calls: {summary['policy_reset_calls']}",
    )


_TRANSCRIPT_BUILDERS: dict[str, TranscriptBuilder] = {
    "leworldmodel": _leworldmodel_transcript,
    "lerobot": _lerobot_transcript,
    "cosmos-policy": _cosmos_policy_transcript,
    "gr00t-replay": _gr00t_replay_transcript,
    "robotics-compare": _robotics_compare_transcript,
    "diagnostics": _diagnostics_transcript,
    "workbench": _workbench_transcript,
}


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


def _position(summary: JSONDict) -> str:
    final = summary["final_cube_position"]
    return f"({final['x']:.2f}, {final['y']:.2f}, {final['z']:.2f})"


def _format_ms(value: object) -> str:
    return f"{float(value):.2f} ms"
