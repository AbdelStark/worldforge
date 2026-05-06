"""Checkout-safe operator failure drills for WorldForge runbooks."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from worldforge import WorldForge
from worldforge.benchmark import ProviderBenchmarkHarness, load_benchmark_budgets
from worldforge.evidence_bundle import generate_issue_bundle
from worldforge.harness.workspace import RunWorkspace, create_run_workspace, write_run_manifest
from worldforge.models import JSONDict, ProviderEvent, WorldForgeError, WorldStateError, dump_json
from worldforge.providers import ProviderError
from worldforge.providers.runtime_manifest import load_runtime_manifest
from worldforge.providers.runway import RunwayTaskCreationResponse

DRILL_WORKSPACE_DEFAULT = Path(".worldforge/drills")
DRILL_IDS = (
    "missing-credentials",
    "missing-optional-dependency",
    "malformed-provider-output",
    "budget-violation",
    "corrupted-world-state",
    "expired-artifact",
    "unsafe-event-metadata",
)


@dataclass(frozen=True, slots=True)
class OperatorDrillSpec:
    """Metadata for a checkout-safe operator failure drill."""

    id: str
    title: str
    failure_mode: str
    expected_failure: str
    recovery_command: str
    description: str
    checkout_safe: bool = True
    prepared_host: bool = False

    def to_dict(self) -> JSONDict:
        return {
            "id": self.id,
            "title": self.title,
            "failure_mode": self.failure_mode,
            "expected_failure": self.expected_failure,
            "recovery_command": self.recovery_command,
            "description": self.description,
            "checkout_safe": self.checkout_safe,
            "prepared_host": self.prepared_host,
            "command": f"uv run worldforge drills run {self.id} --workspace-dir .worldforge/drills",
        }


@dataclass(frozen=True, slots=True)
class _DrillOutcome:
    failure_signal: str
    details: JSONDict
    artifacts: dict[str, str]
    event_count: int = 0


_SPECS: dict[str, OperatorDrillSpec] = {
    "missing-credentials": OperatorDrillSpec(
        id="missing-credentials",
        title="Missing provider credentials",
        failure_mode="missing_credentials",
        expected_failure="runtime manifest reports required provider credentials absent",
        recovery_command=(
            "load the required provider env var, then run "
            "`uv run worldforge provider health runway`"
        ),
        description=(
            "Uses the Runway runtime manifest with an empty environment so operators can rehearse "
            "a credential-missing path without touching local shell secrets."
        ),
    ),
    "missing-optional-dependency": OperatorDrillSpec(
        id="missing-optional-dependency",
        title="Missing optional dependency",
        failure_mode="missing_optional_dependency",
        expected_failure="optional runtime import is absent",
        recovery_command=(
            "install the provider optional runtime on a prepared host, then rerun its smoke command"
        ),
        description=(
            "Checks for a deliberately absent module name and records the same shape of failure an "
            "optional provider would surface when host-owned runtime packages are missing."
        ),
    ),
    "malformed-provider-output": OperatorDrillSpec(
        id="malformed-provider-output",
        title="Malformed provider output",
        failure_mode="malformed_provider_output",
        expected_failure="Runway task creation parser rejects a missing task id",
        recovery_command=(
            "capture the sanitized payload fixture, then fix the parser or upstream contract"
        ),
        description=(
            "Feeds a fixture-shaped malformed response through the real Runway parser so parser "
            "failure triage is repeatable without a live provider call."
        ),
    ),
    "budget-violation": OperatorDrillSpec(
        id="budget-violation",
        title="Benchmark budget violation",
        failure_mode="budget_violation",
        expected_failure="benchmark budget gate reports at least one violation",
        recovery_command=(
            "inspect the run bundle, then rerun "
            "`uv run worldforge benchmark --provider mock --operation predict --iterations 1`"
        ),
        description=(
            "Runs a one-iteration mock benchmark against an intentionally impossible latency "
            "budget so operators can rehearse budget-gate failure handling."
        ),
    ),
    "corrupted-world-state": OperatorDrillSpec(
        id="corrupted-world-state",
        title="Corrupted local world state",
        failure_mode="corrupted_world_state",
        expected_failure="local JSON world load raises WorldStateError",
        recovery_command=(
            "export diagnostics, quarantine the bad file, then recreate or import a valid world"
        ),
        description=(
            "Writes a malformed world JSON file inside the drill workspace and attempts to load it "
            "through the normal WorldForge persistence path."
        ),
    ),
    "expired-artifact": OperatorDrillSpec(
        id="expired-artifact",
        title="Expired remote artifact",
        failure_mode="expired_artifact",
        expected_failure="artifact expiry timestamp is already in the past",
        recovery_command=(
            "rerun the provider workflow to refresh the artifact, then export a new issue bundle"
        ),
        description=(
            "Records a sanitized expired artifact descriptor so operators can rehearse refresh and "
            "evidence-export handling without downloading remote media."
        ),
    ),
    "unsafe-event-metadata": OperatorDrillSpec(
        id="unsafe-event-metadata",
        title="Unsafe provider-event metadata",
        failure_mode="unsafe_event_metadata",
        expected_failure=(
            "non-JSON-native metadata is rejected and secret-shaped fields are redacted"
        ),
        recovery_command=(
            "remove object or tuple metadata, keep JSON-native fields only, then rerun the "
            "event-producing workflow"
        ),
        description=(
            "Exercises ProviderEvent validation and redaction with fixture metadata so event logs "
            "fail closed before unsafe values reach sinks."
        ),
    ),
}

_RUNNERS: dict[str, Callable[[RunWorkspace], _DrillOutcome]] = {}


def list_operator_drills() -> tuple[JSONDict, ...]:
    """Return drill metadata in stable display order."""

    return tuple(_SPECS[drill_id].to_dict() for drill_id in DRILL_IDS)


def get_operator_drill(drill_id: str) -> OperatorDrillSpec:
    """Return one drill spec or raise a clear error."""

    try:
        return _SPECS[drill_id]
    except KeyError as exc:
        raise WorldForgeError(f"Unknown operator drill: {drill_id}") from exc


def run_operator_drill(
    drill_id: str,
    *,
    workspace_dir: Path = DRILL_WORKSPACE_DEFAULT,
    bundle: bool = False,
) -> JSONDict:
    """Run one deterministic operator drill and preserve the observed failure."""

    spec = get_operator_drill(drill_id)
    workspace = create_run_workspace(
        workspace_dir,
        kind="operator_drill",
        command=f"uv run worldforge drills run {drill_id} --workspace-dir <workspace-dir>",
        provider="fixture",
        operation=spec.failure_mode,
        input_summary={
            "drill_id": drill_id,
            "checkout_safe": spec.checkout_safe,
            "prepared_host": spec.prepared_host,
        },
    )
    outcome = _RUNNERS[drill_id](workspace)
    result_summary: JSONDict = {
        "drill_id": drill_id,
        "drill_passed": True,
        "expected_failure_observed": True,
        "expected_failure": spec.expected_failure,
        "expected_signal": spec.expected_failure,
        "observed_failure": outcome.failure_signal,
        "failure_signal": outcome.failure_signal,
        "recovery_command": spec.recovery_command,
    }
    drill_payload: JSONDict = {
        "schema_version": 1,
        "status": "passed",
        "run_id": workspace.run_id,
        "drill": spec.to_dict(),
        "expected_failure_observed": True,
        "failure_signal": outcome.failure_signal,
        "recovery_command": spec.recovery_command,
        "details": outcome.details,
        "run_workspace": f"<workspace-dir>/runs/{workspace.run_id}",
        "run_manifest": f"<workspace-dir>/runs/{workspace.run_id}/run_manifest.json",
    }
    dump_json(drill_payload)
    outcome_artifacts = dict(outcome.artifacts)
    outcome_artifacts["drill_json"] = "results/drill.json"
    outcome_artifacts["drill_markdown"] = "reports/drill.md"
    workspace.write_json("results/drill.json", drill_payload)
    workspace.write_text("reports/drill.md", _render_drill_markdown(drill_payload))
    write_run_manifest(
        workspace,
        kind="operator_drill",
        command=f"uv run worldforge drills run {drill_id} --workspace-dir <workspace-dir>",
        provider="fixture",
        operation=spec.failure_mode,
        status="failed",
        input_summary={
            "drill_id": drill_id,
            "checkout_safe": spec.checkout_safe,
            "prepared_host": spec.prepared_host,
        },
        result_summary=result_summary,
        artifact_paths=outcome_artifacts,
        event_count=outcome.event_count,
    )
    result: JSONDict = {
        **drill_payload,
        "artifact_paths": outcome_artifacts,
        "run_workspace": str(workspace.path),
        "run_manifest": str(workspace.manifest_path),
    }
    if bundle:
        bundle_result = generate_issue_bundle(
            workspace_dir=workspace_dir,
            run_id=workspace.run_id,
            output_dir=workspace_dir / "issue-bundles" / workspace.run_id,
            overwrite=True,
        )
        result["issue_bundle"] = {
            "output_dir": str(bundle_result.output_dir),
            "manifest_path": str(bundle_result.manifest_path),
            "summary_path": str(bundle_result.summary_path),
            "issue_template_path": (
                str(bundle_result.issue_template_path)
                if bundle_result.issue_template_path is not None
                else None
            ),
            "safe_to_attach": bundle_result.manifest["safe_to_attach"],
        }
    dump_json(result)
    return result


def run_all_operator_drills(
    *,
    workspace_dir: Path = DRILL_WORKSPACE_DEFAULT,
    bundle: bool = False,
) -> JSONDict:
    """Run every checkout-safe operator drill."""

    runs = [
        run_operator_drill(drill_id, workspace_dir=workspace_dir, bundle=bundle)
        for drill_id in DRILL_IDS
    ]
    return {
        "status": "passed",
        "run_count": len(runs),
        "runs": runs,
    }


def render_operator_drills_markdown(drills: tuple[JSONDict, ...]) -> str:
    """Render drill metadata as Markdown."""

    lines = [
        "# Operator Failure Drills",
        "",
        "| Drill | Failure mode | Checkout-safe | Expected failure | Recovery command |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| `{id}` | {mode} | {safe} | {expected} | {recovery} |".format(
                id=drill["id"],
                mode=drill["failure_mode"],
                safe=str(drill["checkout_safe"]).lower(),
                expected=drill["expected_failure"],
                recovery=drill["recovery_command"],
            )
        )
        for drill in drills
    )
    return "\n".join(lines)


def render_operator_drill_result_markdown(result: JSONDict) -> str:
    """Render one drill result or an aggregate run result as Markdown."""

    if "runs" in result:
        lines = ["# Operator Drill Run", "", f"Status: `{result['status']}`", ""]
        lines.extend(f"- `{run['drill']['id']}`: {run['failure_signal']}" for run in result["runs"])
        return "\n".join(lines)
    return _render_drill_markdown(result)


def _render_drill_markdown(payload: JSONDict) -> str:
    drill = payload["drill"]
    return "\n".join(
        [
            f"# Operator Drill: {drill['title']}",
            "",
            f"- Drill id: `{drill['id']}`",
            f"- Failure mode: `{drill['failure_mode']}`",
            f"- Status: `{payload['status']}`",
            f"- Expected failure observed: `{str(payload['expected_failure_observed']).lower()}`",
            f"- Failure signal: {payload['failure_signal']}",
            f"- Recovery command: `{payload['recovery_command']}`",
            f"- Run manifest: `{payload['run_manifest']}`",
            "",
        ]
    )


def _missing_credentials(workspace: RunWorkspace) -> _DrillOutcome:
    manifest = load_runtime_manifest("runway")
    summary = manifest.config_summary(environ={}).to_dict()
    if summary["configured"]:
        raise WorldForgeError("missing credentials drill expected configured=false.")
    workspace.write_json("results/config-summary.json", summary)
    return _DrillOutcome(
        failure_signal="Provider config summary configured=false for RUNWAYML_API_SECRET",
        details={"provider": "runway", "config_summary": summary},
        artifacts={"config_summary": "results/config-summary.json"},
    )


def _missing_optional_dependency(workspace: RunWorkspace) -> _DrillOutcome:
    dependency = "worldforge_operator_drill_missing_dependency"
    spec = importlib.util.find_spec(dependency)
    if spec is not None:
        raise WorldForgeError(f"missing optional dependency drill unexpectedly found {dependency}.")
    details = {
        "provider": "fixture-optional-runtime",
        "dependency": dependency,
        "importable": False,
        "prepared_host": False,
    }
    workspace.write_json("results/dependency-check.json", details)
    return _DrillOutcome(
        failure_signal=f"missing optional dependency {dependency}",
        details=details,
        artifacts={"dependency_check": "results/dependency-check.json"},
    )


def _malformed_provider_output(workspace: RunWorkspace) -> _DrillOutcome:
    fixture = {"status": "SUCCEEDED", "output": []}
    workspace.write_json("inputs/malformed-runway-task.json", fixture)
    try:
        RunwayTaskCreationResponse.from_payload(
            fixture,
            provider_name="runway-drill",
            operation_name="task create",
        )
    except ProviderError as exc:
        details = {
            "provider": "runway-drill",
            "parser": "RunwayTaskCreationResponse",
            "error": str(exc),
        }
        workspace.write_json("results/parser-error.json", details)
        return _DrillOutcome(
            failure_signal=str(exc),
            details=details,
            artifacts={
                "fixture": "inputs/malformed-runway-task.json",
                "parser_error": "results/parser-error.json",
            },
        )
    raise WorldForgeError("malformed provider output drill expected ProviderError.")


def _budget_violation(workspace: RunWorkspace) -> _DrillOutcome:
    forge = WorldForge(state_dir=workspace.inputs_dir / "worlds")
    report = ProviderBenchmarkHarness(forge=forge).run(
        ["mock"],
        operations=["predict"],
        iterations=1,
        concurrency=1,
    )
    budget_payload = {
        "budgets": [
            {
                "provider": "mock",
                "operation": "predict",
                "max_average_latency_ms": 0.0,
                "max_error_count": 0,
                "max_retry_count": 0,
                "min_success_rate": 1.0,
            }
        ]
    }
    gate = report.evaluate_budgets(load_benchmark_budgets(budget_payload))
    if gate.passed:
        raise WorldForgeError("budget violation drill expected a failed budget gate.")
    workspace.write_json("inputs/budget.json", budget_payload)
    workspace.write_text("reports/benchmark.json", report.to_json())
    workspace.write_text("reports/benchmark.md", report.to_markdown())
    workspace.write_text("reports/benchmark.csv", report.to_csv())
    workspace.write_json("results/budget-gate.json", gate.to_dict())
    return _DrillOutcome(
        failure_signal=f"benchmark budget violation count={len(gate.violations)}",
        details={
            "budget_passed": gate.passed,
            "violation_count": len(gate.violations),
            "violations": [violation.to_dict() for violation in gate.violations],
        },
        artifacts={
            "budget": "inputs/budget.json",
            "benchmark_json": "reports/benchmark.json",
            "benchmark_markdown": "reports/benchmark.md",
            "benchmark_csv": "reports/benchmark.csv",
            "budget_gate": "results/budget-gate.json",
        },
    )


def _corrupted_world_state(workspace: RunWorkspace) -> _DrillOutcome:
    state_dir = workspace.inputs_dir / "worlds"
    state_dir.mkdir(parents=True, exist_ok=True)
    corrupt_path = state_dir / "corrupted.json"
    corrupt_path.write_text('{"id": "corrupted", "state": ', encoding="utf-8")
    try:
        WorldForge(state_dir=state_dir).load_world("corrupted")
    except WorldStateError as exc:
        error = _relative_workspace_text(workspace, str(exc))
        details = {
            "world_id": "corrupted",
            "state_file": "inputs/worlds/corrupted.json",
            "error": error,
        }
        workspace.write_json("results/world-state-error.json", details)
        return _DrillOutcome(
            failure_signal=error,
            details=details,
            artifacts={
                "corrupted_world": "inputs/worlds/corrupted.json",
                "world_state_error": "results/world-state-error.json",
            },
        )
    raise WorldForgeError("corrupted world state drill expected WorldStateError.")


def _expired_artifact(workspace: RunWorkspace) -> _DrillOutcome:
    expires_at = "2000-01-01T00:00:00Z"
    parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    expired = parsed < datetime.now(UTC)
    if not expired:
        raise WorldForgeError("expired artifact drill expected a past expiry timestamp.")
    descriptor = {
        "artifact_id": "drill-expired-artifact",
        "artifact_url": "https://artifacts.example.invalid/worldforge/drill-output.json",
        "expires_at": expires_at,
        "expired": True,
        "safe_to_attach": False,
    }
    workspace.write_json("artifacts/expired-artifact.json", descriptor)
    return _DrillOutcome(
        failure_signal=f"artifact expired at {expires_at}",
        details=descriptor,
        artifacts={"expired_artifact": "artifacts/expired-artifact.json"},
    )


def _unsafe_event_metadata(workspace: RunWorkspace) -> _DrillOutcome:
    try:
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="failure",
            metadata={"shape": (1, 2, 3)},
        )
    except WorldForgeError as exc:
        rejection = str(exc)
    else:
        raise WorldForgeError("unsafe event metadata drill expected WorldForgeError.")

    redacted_event = ProviderEvent(
        provider="runway",
        operation="artifact download",
        phase="failure",
        target="https://downloads.example.invalid/generated.mp4?token=drill-secret",
        message="download failed with Authorization=drill-secret",
        metadata={
            "api_token": "drill-secret",
            "safe_note": "metadata redaction drill",
        },
    ).to_dict()
    serialized = json.dumps(redacted_event, sort_keys=True)
    if "drill-secret" in serialized:
        raise WorldForgeError("unsafe event metadata drill leaked a secret-shaped value.")
    workspace.write_text("logs/provider-events.jsonl", json.dumps(redacted_event, sort_keys=True))
    details = {
        "rejection": rejection,
        "redacted_event": redacted_event,
        "secret_leaked": False,
    }
    workspace.write_json("results/event-redaction.json", details)
    return _DrillOutcome(
        failure_signal=rejection,
        details=details,
        artifacts={
            "provider_events": "logs/provider-events.jsonl",
            "event_redaction": "results/event-redaction.json",
        },
        event_count=1,
    )


_RUNNERS.update(
    {
        "missing-credentials": _missing_credentials,
        "missing-optional-dependency": _missing_optional_dependency,
        "malformed-provider-output": _malformed_provider_output,
        "budget-violation": _budget_violation,
        "corrupted-world-state": _corrupted_world_state,
        "expired-artifact": _expired_artifact,
        "unsafe-event-metadata": _unsafe_event_metadata,
    }
)


def _relative_workspace_text(workspace: RunWorkspace, value: str) -> str:
    return value.replace(str(workspace.path), "<run-workspace>")


__all__ = [
    "DRILL_IDS",
    "DRILL_WORKSPACE_DEFAULT",
    "OperatorDrillSpec",
    "get_operator_drill",
    "list_operator_drills",
    "render_operator_drill_result_markdown",
    "render_operator_drills_markdown",
    "run_all_operator_drills",
    "run_operator_drill",
]
