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
from worldforge.providers.leworldmodel import LeWorldModelProvider
from worldforge.providers.runtime_manifest import load_runtime_manifest

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


@dataclass(frozen=True, slots=True)
class _DrillRun:
    spec: OperatorDrillSpec
    workspace: RunWorkspace
    outcome: _DrillOutcome
    payload: JSONDict
    artifact_paths: dict[str, str]


_SPECS: dict[str, OperatorDrillSpec] = {
    "missing-credentials": OperatorDrillSpec(
        id="missing-credentials",
        title="Missing provider runtime configuration",
        failure_mode="missing_runtime_configuration",
        expected_failure="runtime manifest reports required score runtime configuration absent",
        recovery_command=(
            "set LEWORLDMODEL_POLICY or LEWM_POLICY, then run "
            "`uv run worldforge provider health leworldmodel`"
        ),
        description=(
            "Uses the LeWorldModel runtime manifest with an empty environment so operators can "
            "rehearse a score-runtime configuration gap without touching local shell state."
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
        title="Malformed score provider payload",
        failure_mode="malformed_provider_output",
        expected_failure="LeWorldModel score input parser rejects a malformed payload",
        recovery_command=(
            "capture the sanitized payload fixture, then fix the score adapter contract"
        ),
        description=(
            "Feeds a malformed score request through the real LeWorldModel boundary so parser "
            "failure triage is repeatable without a live optional runtime."
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
            "evidence-export handling without downloading remote artifacts."
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
    run = _execute_operator_drill(spec, workspace_dir=workspace_dir)
    result = _operator_drill_result(run)
    if bundle:
        result["issue_bundle"] = _operator_drill_issue_bundle(run, workspace_dir=workspace_dir)
    dump_json(result)
    return result


def _execute_operator_drill(
    spec: OperatorDrillSpec,
    *,
    workspace_dir: Path,
) -> _DrillRun:
    workspace = create_run_workspace(
        workspace_dir,
        kind="operator_drill",
        command=_operator_drill_command(spec.id),
        provider="fixture",
        operation=spec.failure_mode,
        input_summary=_operator_drill_input_summary(spec),
    )
    outcome = _RUNNERS[spec.id](workspace)
    payload = _operator_drill_payload(spec, workspace, outcome)
    artifact_paths = _operator_drill_artifact_paths(outcome)
    _write_operator_drill_artifacts(workspace, payload)
    _write_operator_drill_manifest(spec, workspace, outcome, artifact_paths)
    return _DrillRun(
        spec=spec,
        workspace=workspace,
        outcome=outcome,
        payload=payload,
        artifact_paths=artifact_paths,
    )


def _operator_drill_command(drill_id: str) -> str:
    return f"uv run worldforge drills run {drill_id} --workspace-dir <workspace-dir>"


def _operator_drill_input_summary(spec: OperatorDrillSpec) -> JSONDict:
    return {
        "drill_id": spec.id,
        "checkout_safe": spec.checkout_safe,
        "prepared_host": spec.prepared_host,
    }


def _operator_drill_result_summary(spec: OperatorDrillSpec, outcome: _DrillOutcome) -> JSONDict:
    return {
        "drill_id": spec.id,
        "drill_passed": True,
        "expected_failure_observed": True,
        "expected_failure": spec.expected_failure,
        "expected_signal": spec.expected_failure,
        "observed_failure": outcome.failure_signal,
        "failure_signal": outcome.failure_signal,
        "recovery_command": spec.recovery_command,
    }


def _operator_drill_payload(
    spec: OperatorDrillSpec,
    workspace: RunWorkspace,
    outcome: _DrillOutcome,
) -> JSONDict:
    return {
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


def _operator_drill_artifact_paths(outcome: _DrillOutcome) -> dict[str, str]:
    artifact_paths = dict(outcome.artifacts)
    artifact_paths["drill_json"] = "results/drill.json"
    artifact_paths["drill_markdown"] = "reports/drill.md"
    return artifact_paths


def _write_operator_drill_artifacts(workspace: RunWorkspace, payload: JSONDict) -> None:
    dump_json(payload)
    workspace.write_json("results/drill.json", payload)
    workspace.write_text("reports/drill.md", _render_drill_markdown(payload))


def _write_operator_drill_manifest(
    spec: OperatorDrillSpec,
    workspace: RunWorkspace,
    outcome: _DrillOutcome,
    artifact_paths: dict[str, str],
) -> None:
    write_run_manifest(
        workspace,
        kind="operator_drill",
        command=_operator_drill_command(spec.id),
        provider="fixture",
        operation=spec.failure_mode,
        status="failed",
        input_summary=_operator_drill_input_summary(spec),
        result_summary=_operator_drill_result_summary(spec, outcome),
        artifact_paths=artifact_paths,
        event_count=outcome.event_count,
    )


def _operator_drill_result(run: _DrillRun) -> JSONDict:
    return {
        **run.payload,
        "artifact_paths": run.artifact_paths,
        "run_workspace": str(run.workspace.path),
        "run_manifest": str(run.workspace.manifest_path),
    }


def _operator_drill_issue_bundle(run: _DrillRun, *, workspace_dir: Path) -> JSONDict:
    bundle_result = generate_issue_bundle(
        workspace_dir=workspace_dir,
        run_id=run.workspace.run_id,
        output_dir=workspace_dir / "issue-bundles" / run.workspace.run_id,
        overwrite=True,
    )
    return {
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
    manifest = load_runtime_manifest("leworldmodel")
    summary = manifest.config_summary(environ={}).to_dict()
    if summary["configured"]:
        raise WorldForgeError("missing credentials drill expected configured=false.")
    workspace.write_json("results/config-summary.json", summary)
    return _DrillOutcome(
        failure_signal=(
            "Provider config summary configured=false for LEWORLDMODEL_POLICY or LEWM_POLICY"
        ),
        details={"provider": "leworldmodel", "config_summary": summary},
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
    fixture = {"info": {}, "action_candidates": []}
    workspace.write_json("inputs/malformed-score-request.json", fixture)
    try:
        LeWorldModelProvider(
            policy="operator-drill",
            model_loader=lambda _policy, _cache_dir: object(),
            tensor_module=object(),
        ).score_actions(
            info=fixture["info"],
            action_candidates=fixture["action_candidates"],
        )
    except ProviderError as exc:
        details = {
            "provider": "leworldmodel",
            "parser": "LeWorldModelProvider.score_actions",
            "error": str(exc),
        }
        workspace.write_json("results/parser-error.json", details)
        return _DrillOutcome(
            failure_signal=str(exc),
            details=details,
            artifacts={
                "fixture": "inputs/malformed-score-request.json",
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
            provider="leworldmodel",
            operation="score",
            phase="failure",
            metadata={"shape": (1, 2, 3)},
        )
    except WorldForgeError as exc:
        rejection = str(exc)
    else:
        raise WorldForgeError("unsafe event metadata drill expected WorldForgeError.")

    redacted_event = ProviderEvent(
        provider="leworldmodel",
        operation="score",
        phase="failure",
        target="https://scores.example.invalid/score?token=drill-secret",
        message="score failed with Authorization=drill-secret",
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
