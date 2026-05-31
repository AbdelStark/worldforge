"""Robotics policy replay comparison flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from worldforge.harness.flow_artifacts import (
    COSMOS_POLICY_REPLAY_ARTIFACT,
    GROOT_REPLAY_ARTIFACT,
    ROBOTICS_COMPARE_REPLAY_ARTIFACTS,
    ROBOTICS_COMPARISON_ARTIFACT,
)
from worldforge.harness.flow_catalog import flow_index
from worldforge.harness.flow_rendering import (
    groot_shape_result as _groot_shape_result,
)
from worldforge.harness.flow_rendering import transcript_for as _transcript_for
from worldforge.models import (
    JSONDict,
    ProviderEvent,
    WorldForgeError,
    WorldStateError,
    _redact_observable_text,
)
from worldforge.providers.base import ProviderError

FlowRunner = Callable[..., JSONDict]


@dataclass(frozen=True)
class RoboticsCompareRunners:
    lerobot: FlowRunner
    cosmos_policy: FlowRunner
    groot_replay: FlowRunner


def run_robotics_compare_demo(
    *,
    state_dir: Path,
    emit: bool = False,
    runners: RoboticsCompareRunners,
) -> JSONDict:
    subflows = _robotics_compare_subflows(state_dir, runners)
    validation_errors = _robotics_compare_validation_errors(subflows)
    source_validation = _robotics_compare_source_validation()
    if validation_errors:
        return _robotics_compare_failure_summary(
            state_dir=state_dir,
            subflows=subflows,
            source_validation=source_validation,
            validation_errors=validation_errors,
            emit=emit,
        )

    try:
        rows = _robotics_compare_rows(subflows)
        provider_events = _robotics_compare_provider_events(subflows, rows=rows)
        comparison_payload = _robotics_compare_completed_payload(
            source_validation=source_validation,
            rows=rows,
        )
        harness_artifacts = _robotics_compare_artifacts(
            subflows,
            comparison_payload,
            require_replays=True,
        )
        comparison_payload["artifacts"] = _robotics_compare_replay_artifact_paths(harness_artifacts)
    except Exception as exc:
        return _robotics_compare_failure_summary(
            state_dir=state_dir,
            subflows=subflows,
            source_validation=source_validation,
            validation_errors=[_robotics_compare_exception_error("robotics-compare", exc)],
            emit=emit,
        )

    summary = _robotics_compare_success_summary(
        state_dir=state_dir,
        rows=rows,
        source_validation=source_validation,
        provider_events=provider_events,
        harness_artifacts=harness_artifacts,
    )
    if emit:
        print("\n".join(_transcript_for("robotics-compare", summary)))
    return summary


def _robotics_compare_subflows(
    state_dir: Path,
    runners: RoboticsCompareRunners,
) -> dict[str, JSONDict]:
    return {
        "lerobot": _run_robotics_compare_subflow(
            "lerobot",
            runners.lerobot,
            state_dir / "lerobot",
        ),
        "cosmos-policy": _run_robotics_compare_subflow(
            "cosmos-policy",
            runners.cosmos_policy,
            state_dir=state_dir / "cosmos-policy",
        ),
        "gr00t-replay": _run_robotics_compare_subflow(
            "gr00t-replay",
            runners.groot_replay,
            state_dir=state_dir / "gr00t-replay",
        ),
    }


def _robotics_compare_rows(subflows: dict[str, JSONDict]) -> list[JSONDict]:
    return [
        robotics_compare_lerobot_row(subflows["lerobot"]),
        robotics_compare_cosmos_row(subflows["cosmos-policy"]),
        robotics_compare_groot_row(subflows["gr00t-replay"]),
    ]


def _robotics_compare_completed_payload(
    *,
    source_validation: JSONDict,
    rows: list[JSONDict],
) -> JSONDict:
    return {
        "schema_version": 1,
        "flow_id": "robotics-compare",
        "status": "completed",
        "source_validation": source_validation,
        "rows": rows,
        "artifacts": {},
        "notes": [
            "WorldForge owns the common policy contract, validation, events, and replay surface.",
            "Robotics model runtimes remain host-owned and are not required for this replay.",
        ],
    }


def _robotics_compare_success_summary(
    *,
    state_dir: Path,
    rows: list[JSONDict],
    source_validation: JSONDict,
    provider_events: list[JSONDict],
    harness_artifacts: JSONDict,
) -> JSONDict:
    return {
        "demo_kind": "robotics_policy_replay_comparison",
        "state_dir": str(state_dir),
        "providers": [str(row["provider"]) for row in rows],
        "flow_ids": [str(row["flow_id"]) for row in rows],
        "comparison_count": len(rows),
        "rows": rows,
        "total_translated_actions": sum(int(row["translated_action_count"]) for row in rows),
        "gpu_required": False,
        "source_validation": source_validation,
        "event_phases": [str(event.get("phase", "unknown")) for event in provider_events],
        "provider_events": provider_events,
        "harness_artifacts": harness_artifacts,
    }


def _run_robotics_compare_subflow(
    flow_id: str,
    runner: FlowRunner,
    state_dir: Path,
) -> JSONDict:
    try:
        summary = runner(state_dir=state_dir, emit=False)
    except Exception as exc:
        return _robotics_compare_failed_subflow_summary(
            flow_id,
            state_dir,
            _robotics_compare_exception_error("", exc),
        )
    if not isinstance(summary, dict):
        return _robotics_compare_failed_subflow_summary(
            flow_id,
            state_dir,
            f"WorldStateError: {flow_id} subflow returned {type(summary).__name__}, "
            "expected JSON object",
        )
    return summary


def _robotics_compare_failed_subflow_summary(
    flow_id: str,
    state_dir: Path,
    message: str,
) -> JSONDict:
    safe_message = _redact_observable_text(message).strip()
    event = ProviderEvent(
        provider=flow_index()[flow_id].provider,
        operation=flow_id,
        phase="failure",
        message=safe_message,
        metadata={"stage": "robotics-compare-subflow"},
    )
    return {
        "demo_kind": "robotics_compare_subflow",
        "state_dir": str(state_dir),
        "status": "failed",
        "providers": [flow_id],
        "event_phases": [event.phase],
        "provider_events": [event.to_dict()],
        "validation_errors": [safe_message],
    }


def _robotics_compare_exception_error(prefix: str, exc: BaseException) -> str:
    detail = _redact_observable_text(str(exc)).strip()
    type_name = _robotics_compare_exception_type_name(exc)
    message = f"{type_name}: {detail}" if detail else type_name
    return f"{prefix}: {message}" if prefix else message


def _robotics_compare_exception_type_name(exc: BaseException) -> str:
    if isinstance(exc, ProviderError):
        return "ProviderError"
    if isinstance(exc, WorldStateError):
        return "WorldStateError"
    if isinstance(exc, WorldForgeError):
        return "WorldForgeError"
    return "ProviderError"


def _robotics_compare_failure_summary(
    *,
    state_dir: Path,
    subflows: dict[str, JSONDict],
    source_validation: JSONDict,
    validation_errors: list[str],
    emit: bool,
) -> JSONDict:
    validation_errors = [_redact_observable_text(error) for error in validation_errors]
    comparison_payload: JSONDict = {
        "schema_version": 1,
        "flow_id": "robotics-compare",
        "status": "failed",
        "source_validation": source_validation,
        "validation_errors": validation_errors,
        "artifacts": {},
        "notes": [
            "At least one subflow failed before comparison rows could be normalized.",
            "Available sanitized replay artifacts are still preserved for triage.",
        ],
    }
    provider_events = _robotics_compare_provider_events(
        subflows,
        validation_errors=validation_errors,
    )
    harness_artifacts = _robotics_compare_artifacts(
        subflows,
        comparison_payload,
        require_replays=False,
    )
    comparison_payload["artifacts"] = _robotics_compare_replay_artifact_paths(harness_artifacts)
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
        "harness_artifacts": harness_artifacts,
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
            errors.extend(_redact_observable_text(f"{flow_id}: {error}") for error in flow_errors)
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
        ROBOTICS_COMPARISON_ARTIFACT.name: ROBOTICS_COMPARISON_ARTIFACT.descriptor(
            comparison_payload
        ),
    }
    for flow_id, artifact in ROBOTICS_COMPARE_REPLAY_ARTIFACTS:
        try:
            payload = harness_artifact_payload(subflows[flow_id], artifact.name)
        except WorldStateError:
            if require_replays:
                raise
            continue
        artifacts[artifact.name] = artifact.descriptor(payload)
    return artifacts


def _robotics_compare_replay_artifact_paths(harness_artifacts: JSONDict) -> JSONDict:
    paths: JSONDict = {}
    for _flow_id, artifact in ROBOTICS_COMPARE_REPLAY_ARTIFACTS:
        descriptor = harness_artifacts.get(artifact.name)
        if not isinstance(descriptor, dict):
            continue
        path = descriptor.get("path")
        if isinstance(path, str):
            paths[artifact.name] = path
    return paths


def robotics_compare_lerobot_row(summary: JSONDict) -> JSONDict:
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


def robotics_compare_cosmos_row(summary: JSONDict) -> JSONDict:
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
            "artifact": COSMOS_POLICY_REPLAY_ARTIFACT.path,
        }
    except KeyError as exc:
        raise WorldStateError(
            f"cosmos-policy comparison summary missing required key {exc!s}."
        ) from exc
    except (IndexError, TypeError, ValueError) as exc:
        raise WorldStateError(f"cosmos-policy comparison summary is malformed: {exc}") from exc


def robotics_compare_groot_row(summary: JSONDict) -> JSONDict:
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
            "artifact": GROOT_REPLAY_ARTIFACT.path,
        }
    except KeyError as exc:
        raise WorldStateError(
            f"gr00t-replay comparison summary missing required key {exc!s}."
        ) from exc
    except (IndexError, TypeError, ValueError) as exc:
        raise WorldStateError(f"gr00t-replay comparison summary is malformed: {exc}") from exc


def harness_artifact_payload(summary: JSONDict, name: str) -> JSONDict:
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
