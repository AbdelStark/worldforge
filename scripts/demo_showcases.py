"""Run checkout-safe WorldForge demo and use-case showcase workflows."""

from __future__ import annotations

import argparse
import importlib.util
import json
import py_compile
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge import (  # noqa: E402
    ENTRY_POINT_GROUP,
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    BBox,
    Position,
    ProviderCapabilities,
    ProviderHealth,
    SceneObject,
    WorldForge,
    action_candidates_to_score_payload,
    bounded_move_grid_candidates,
    discover_entry_point_providers,
)
from worldforge.capability_negotiation import negotiate  # noqa: E402
from worldforge.demos import lerobot_e2e  # noqa: E402
from worldforge.evidence_bundle import generate_issue_bundle  # noqa: E402
from worldforge.harness.workspace import create_run_workspace, write_run_manifest  # noqa: E402
from worldforge.models import JSONDict, ProviderEvent, dump_json  # noqa: E402
from worldforge.operator_drills import run_operator_drill  # noqa: E402
from worldforge.persistence_preflight import preflight_local_state  # noqa: E402
from worldforge.providers import BaseProvider, ProviderProfileSpec  # noqa: E402
from worldforge.providers.base import ProviderError  # noqa: E402
from worldforge.providers.catalog import PROVIDER_CATALOG  # noqa: E402
from worldforge.testing import (  # noqa: E402
    FixtureSnapshotEntry,
    FixtureSnapshotManifest,
    build_fixture_snapshot_manifest,
    validate_fixture_snapshot_manifest,
)

DEFAULT_WORKSPACE = Path(".worldforge/demo-showcases")


@dataclass(frozen=True, slots=True)
class DemoWorkflow:
    id: str
    title: str
    issue: int
    runner: Callable[[Path], JSONDict]


class _CandidateLabPolicy(BaseProvider):
    def __init__(
        self,
        candidate_plans: list[list[Action]],
        *,
        translator_available: bool = True,
    ) -> None:
        super().__init__(
            "candidate-lab-policy",
            capabilities=ProviderCapabilities(policy=True),
            profile=ProviderProfileSpec(
                description="Deterministic checkout-safe policy candidate lab provider.",
                implementation_status="demo",
                is_local=True,
                deterministic=True,
            ),
        )
        self._candidate_plans = candidate_plans
        self._translator_available = translator_available

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        if not self._translator_available:
            raise ProviderError("candidate lab action_translator is required.")
        raw_actions = {
            "policy_logits": [0.2, 0.6, 0.2],
            "raw_policy_action_preserved": True,
            "observation_keys": sorted(info),
        }
        return ActionPolicyResult(
            provider=self.name,
            actions=list(self._candidate_plans[0]),
            raw_actions=raw_actions,
            action_horizon=len(self._candidate_plans[0]),
            embodiment_tag="candidate-lab",
            metadata={
                "candidate_count": len(self._candidate_plans),
                "translator": "checkout-safe deterministic mapper",
            },
            action_candidates=[list(plan) for plan in self._candidate_plans],
        )


class _CandidateLabScore(BaseProvider):
    def __init__(self, scores: list[float]) -> None:
        super().__init__(
            "candidate-lab-score",
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(
                description="Deterministic checkout-safe candidate scorer.",
                implementation_status="demo",
                is_local=True,
                deterministic=True,
            ),
        )
        self._scores = scores

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        if not isinstance(action_candidates, list) or len(action_candidates) != len(self._scores):
            raise ProviderError("candidate lab scorer received mismatched action candidates.")
        return ActionScoreResult(
            provider=self.name,
            scores=list(self._scores),
            best_index=min(range(len(self._scores)), key=self._scores.__getitem__),
            metadata={
                "candidate_count": len(self._scores),
                "score_source": "deterministic checkout lab",
                "goal": str(info.get("goal", "")),
            },
        )


class _UnhealthyTransferProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            "demo-unhealthy-transfer",
            capabilities=ProviderCapabilities(transfer=True),
            profile=ProviderProfileSpec(
                description="Demo provider with configured runtime but unhealthy dependency.",
                implementation_status="demo",
                is_local=True,
                deterministic=True,
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            healthy=False,
            latency_ms=0.0,
            details="demo optional runtime dependency is unavailable",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List checkout-safe demo workflows.")
    list_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")

    run_parser = subparsers.add_parser("run", help="Run one workflow or all workflows.")
    run_parser.add_argument("workflow", choices=(*_workflow_ids(), "all"))
    run_parser.add_argument("--workspace-dir", type=Path, default=DEFAULT_WORKSPACE)
    run_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    run_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Remove the selected workflow output directory before running.",
    )

    args = parser.parse_args(argv)
    if args.command == "list":
        workflows = [workflow_summary(workflow) for workflow in WORKFLOWS]
        if args.format == "json":
            print(json.dumps({"workflows": workflows}, indent=2, sort_keys=True))
        else:
            print(render_workflow_list_markdown(workflows))
        return 0

    results = run_workflows(
        args.workflow,
        workspace_dir=args.workspace_dir,
        overwrite=args.overwrite,
    )
    run_status = (
        "passed"
        if all(result["status"] in {"passed", "skipped"} for result in results)
        else "failed"
    )
    payload: JSONDict = {
        "schema_version": 1,
        "status": run_status,
        "workspace_dir": str(args.workspace_dir),
        "results": results,
        "claim_boundary": (
            "These demo workflows are checkout-safe integration stories. They do not install "
            "optional runtimes, call paid providers, operate robots, or claim physical fidelity."
        ),
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_run_markdown(payload))
    return 0 if payload["status"] == "passed" else 1


def run_workflows(
    workflow: str,
    *,
    workspace_dir: Path,
    overwrite: bool = False,
) -> list[JSONDict]:
    selected = WORKFLOWS if workflow == "all" else (_workflow_by_id(workflow),)
    workspace_root = workspace_dir.expanduser().resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    results: list[JSONDict] = []
    for spec in selected:
        workflow_dir = workspace_root / spec.id
        if overwrite and workflow_dir.exists():
            shutil.rmtree(workflow_dir)
        workflow_dir.mkdir(parents=True, exist_ok=True)
        summary = spec.runner(workflow_dir)
        result = _preserve_workflow_result(spec, workflow_dir, summary)
        results.append(result)
    return results


def workflow_summary(workflow: DemoWorkflow) -> JSONDict:
    return {"id": workflow.id, "title": workflow.title, "issue": workflow.issue}


def render_workflow_list_markdown(workflows: list[JSONDict]) -> str:
    lines = [
        "# WorldForge Demo Showcase Workflows",
        "",
        "| Workflow | Issue | Title |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{workflow['id']}` | #{workflow['issue']} | {workflow['title']} |"
        for workflow in workflows
    )
    return "\n".join(lines) + "\n"


def render_run_markdown(payload: JSONDict) -> str:
    lines = [
        "# WorldForge Demo Showcase Run",
        "",
        f"Status: `{payload['status']}`",
        "",
        str(payload["claim_boundary"]),
        "",
        "| Workflow | Status | Safe to attach | Summary | First triage step |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| `{id}` | `{status}` | `{safe}` | {summary} | {triage} |".format(
                id=result["id"],
                status=result["status"],
                safe=str(result["safe_to_attach"]).lower(),
                summary=result["summary"],
                triage=result["first_triage_step"],
            )
        )
        for result in payload["results"]
    )
    return "\n".join(lines) + "\n"


def _preserve_workflow_result(
    spec: DemoWorkflow,
    workflow_dir: Path,
    summary: JSONDict,
) -> JSONDict:
    dump_json(summary)
    status = str(summary.get("status", "passed"))
    safe_to_attach = bool(summary.get("safe_to_attach", True))
    run_workspace = create_run_workspace(
        workflow_dir,
        kind="demo_showcase",
        command=f"uv run python scripts/demo_showcases.py run {spec.id}",
        provider=str(summary.get("provider", "fixture")),
        operation=spec.id,
        input_summary={"workflow": spec.id, "issue": spec.issue},
    )
    run_workspace.write_json("results/summary.json", summary)
    run_workspace.write_text("reports/summary.md", _summary_markdown(spec, summary))
    workflow_artifacts = _copy_artifact_paths(run_workspace, summary.get("artifact_paths", {}))
    write_run_manifest(
        run_workspace,
        kind="demo_showcase",
        command=f"uv run python scripts/demo_showcases.py run {spec.id}",
        provider=str(summary.get("provider", "fixture")),
        operation=spec.id,
        status=status,
        input_summary={"workflow": spec.id, "issue": spec.issue},
        result_summary={
            "summary": str(summary.get("summary", spec.title)),
            "safe_to_attach": safe_to_attach,
            "first_triage_step": str(summary.get("first_triage_step", "")),
        },
        artifact_paths={
            "summary_json": "results/summary.json",
            "summary_markdown": "reports/summary.md",
            **workflow_artifacts,
        },
    )
    result = {
        "id": spec.id,
        "issue": spec.issue,
        "title": spec.title,
        "status": status,
        "safe_to_attach": safe_to_attach,
        "summary": str(summary.get("summary", spec.title)),
        "first_triage_step": str(summary.get("first_triage_step", "")),
        "run_manifest": str(run_workspace.manifest_path),
        "run_workspace": str(run_workspace.path),
        "artifact_paths": {
            "summary_json": str(run_workspace.path / "results/summary.json"),
            "summary_markdown": str(run_workspace.path / "reports/summary.md"),
        },
    }
    dump_json(result)
    (workflow_dir / "workflow-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _summary_markdown(spec: DemoWorkflow, summary: JSONDict) -> str:
    lines = [
        f"# {spec.title}",
        "",
        f"- Issue: #{spec.issue}",
        f"- Status: `{summary.get('status', 'passed')}`",
        f"- Safe to attach: `{str(summary.get('safe_to_attach', True)).lower()}`",
        f"- First triage step: {summary.get('first_triage_step', '')}",
        "",
        "## Summary",
        "",
        str(summary.get("summary", spec.title)),
        "",
        "## Claim Boundary",
        "",
        str(summary.get("claim_boundary", "Checkout-safe demo evidence only.")),
        "",
    ]
    return "\n".join(lines)


def _first_run(workflow_dir: Path) -> JSONDict:
    state_dir = workflow_dir / "worlds"
    forge = WorldForge(state_dir=state_dir, auto_register_remote=False)
    world = forge.create_world("first-run-local-world", provider="mock")
    cube = SceneObject(
        "cube",
        Position(0.0, 0.5, 0.0),
        BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        id="cube-1",
    )
    world.add_object(cube)
    prediction = world.predict(Action.move_to(0.04, 0.5, 0.0), steps=1, provider="mock")
    forge.save_world(world)
    exported = workflow_dir / "exported-world.json"
    exported.write_text(
        json.dumps(world.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    preflight = preflight_local_state(state_dir=state_dir, workspace_dir=workflow_dir)
    (workflow_dir / "preflight.json").write_text(
        json.dumps(preflight, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "passed",
        "provider": "mock",
        "safe_to_attach": True,
        "summary": (
            "Created a mock world, mutated an object, predicted one step, exported JSON, "
            "and ran preflight."
        ),
        "world_id": world.id,
        "object_count": world.object_count,
        "history_length": world.history_length,
        "prediction": {
            "provider": prediction.provider,
            "confidence": prediction.confidence,
            "physics_score": prediction.physics_score,
            "latency_ms": prediction.latency_ms,
            "world_step": prediction.world_state["step"],
        },
        "preflight_status": preflight["status"],
        "artifact_paths": {
            "exported_world": str(exported),
            "preflight": str(workflow_dir / "preflight.json"),
        },
        "first_triage_step": "Run `uv run worldforge world preflight --state-dir <demo>/worlds`.",
        "claim_boundary": "Mock-provider workflow only; no physical-fidelity claim.",
    }


def _issue_bundle(workflow_dir: Path) -> JSONDict:
    workspace = create_run_workspace(
        workflow_dir,
        kind="provider_diagnostic",
        command="uv run worldforge provider health runway",
        provider="runway",
        operation="health",
        input_summary={"credentialed": False, "checkout_safe": True},
    )
    workspace.write_json(
        "reports/provider-health.json",
        {
            "provider": "runway",
            "status": "skipped",
            "reason": "required provider credential is not configured in checkout-safe demo",
            "safe_to_attach": True,
        },
    )
    workspace.write_text("logs/provider-events.jsonl", '{"provider":"runway","phase":"skipped"}')
    write_run_manifest(
        workspace,
        kind="provider_diagnostic",
        command="uv run worldforge provider health runway",
        provider="runway",
        operation="health",
        status="skipped",
        input_summary={"credentialed": False, "checkout_safe": True},
        result_summary={
            "expected_signal": "provider credentials missing",
            "skip_reason": "required provider credential is not configured",
            "safe_to_attach": True,
        },
        artifact_paths={
            "provider_health": "reports/provider-health.json",
            "provider_events": "logs/provider-events.jsonl",
        },
    )
    bundle = generate_issue_bundle(
        workspace_dir=workflow_dir,
        run_id=workspace.run_id,
        output_dir=workflow_dir / "issue-bundle",
        overwrite=True,
    )
    return {
        "status": "passed",
        "provider": "runway",
        "safe_to_attach": bool(bundle.manifest["safe_to_attach"]),
        "summary": (
            "Created a skipped provider diagnostic run and exported an issue-ready evidence bundle."
        ),
        "run_id": workspace.run_id,
        "bundle_manifest": str(bundle.manifest_path),
        "issue_template": str(bundle.issue_template_path),
        "artifact_tree": sorted(
            str(path.relative_to(workflow_dir)) for path in bundle.output_dir.rglob("*")
        ),
        "artifact_paths": {
            "bundle_manifest": str(bundle.manifest_path),
            "issue_template": str(bundle.issue_template_path),
        },
        "first_triage_step": (
            "Attach `issue-bundle/issue.md` and `issue-bundle/evidence_manifest.json`."
        ),
        "claim_boundary": (
            "Diagnostic fixture only; no raw provider credentials or live call output."
        ),
    }


def _robotics_replay(workflow_dir: Path) -> JSONDict:
    summary = lerobot_e2e.run_demo(state_dir=workflow_dir / "worlds", emit=False)
    replay_manifest = {
        "schema_version": 1,
        "mode": "checkout-safe robotics replay",
        "uses_optional_runtime": False,
        "selected_candidate_index": summary["selected_candidate_index"],
        "candidate_costs": summary["candidate_costs"],
        "event_phases": summary["event_phases"],
        "safe_to_attach": True,
        "prepared_host_follow_up": "scripts/robotics-showcase --health-only",
    }
    manifest_path = workflow_dir / "robotics-replay-manifest.json"
    manifest_path.write_text(
        json.dumps(replay_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "passed",
        "provider": "lerobot",
        "safe_to_attach": True,
        "summary": (
            "Rendered deterministic policy+score replay with selected action chunk and "
            "score rationale."
        ),
        "replay": replay_manifest,
        "artifact_paths": {"replay_manifest": str(manifest_path)},
        "first_triage_step": (
            "Run `uv run worldforge-demo-lerobot` before prepared-host robotics commands."
        ),
        "claim_boundary": (
            "Replay uses injected deterministic policy and score runtime; no robot control."
        ),
    }


def _remote_media_dry_run(workflow_dir: Path) -> JSONDict:
    events = [
        ProviderEvent(
            provider="cosmos",
            operation="generate",
            phase="success",
            method="POST",
            target="https://api.example.invalid/cosmos/tasks?signature=fake-secret",
            status_code=200,
            message="fixture success with signed URL https://assets.example/video.mp4?token=fake",
            metadata={
                "signed_url": "https://assets.example/video.mp4?token=fake",
                "retention_days": 7,
            },
        ).to_dict(),
        ProviderEvent(
            provider="runway",
            operation="transfer",
            phase="failed",
            method="GET",
            target="https://api.example.invalid/runway/tasks?api_key=fake",
            status_code=410,
            message="fixture artifact URL expired",
            metadata={"artifact_url": "https://assets.example/out.mp4?X-Amz-Signature=fake"},
        ).to_dict(),
    ]
    events_path = workflow_dir / "remote-media-events.json"
    events_path.write_text(json.dumps(events, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "passed",
        "provider": "cosmos+runway",
        "safe_to_attach": True,
        "summary": (
            "Exercised fixture-backed Cosmos success and Runway expired-artifact dry-run "
            "events with redaction."
        ),
        "provider_events": events,
        "redaction_verified": "fake-secret" not in json.dumps(events)
        and "token=fake" not in json.dumps(events),
        "artifact_paths": {"provider_events": str(events_path)},
        "first_triage_step": (
            "Use prepared-host smoke commands only after checking sanitized dry-run artifacts."
        ),
        "claim_boundary": (
            "Fixture-backed parser and artifact-retention story only; no paid API call."
        ),
    }


def _adapter_author(workflow_dir: Path) -> JSONDict:
    generated_root = workflow_dir / "generated-provider"
    command = [
        sys.executable,
        str(ROOT / "scripts/scaffold_provider.py"),
        "Demo WM",
        "--root",
        str(generated_root),
        "--taxonomy",
        "JEPA latent predictive world model",
        "--implementation-status",
        "scaffold",
        "--planned-capability",
        "score",
        "--remote",
        "--env-var",
        "DEMO_WM_API_KEY",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    provider_path = generated_root / "src/worldforge/providers/demo_wm.py"
    test_path = generated_root / "tests/test_demo_wm_provider.py"
    manifest_stub = generated_root / "src/worldforge/providers/runtime_manifests/demo-wm.json.stub"
    docs_path = generated_root / "docs/src/providers/demo-wm.md"
    workbench_path = generated_root / "docs/src/providers/demo-wm-workbench.md"
    for path in (provider_path, test_path):
        py_compile.compile(str(path), doraise=True)
    return {
        "status": "passed",
        "provider": "demo-wm",
        "safe_to_attach": True,
        "summary": "Generated a provider scaffold in demo output and reported promotion blockers.",
        "generated_files": sorted(
            str(path.relative_to(generated_root))
            for path in generated_root.rglob("*")
            if path.is_file()
        ),
        "stdout": completed.stdout,
        "scaffold_incomplete": True,
        "workbench_report": workbench_path.read_text(encoding="utf-8"),
        "artifact_paths": {
            "provider": str(provider_path),
            "test": str(test_path),
            "runtime_manifest_stub": str(manifest_stub),
            "docs_stub": str(docs_path),
            "workbench_report": str(workbench_path),
        },
        "first_triage_step": (
            "Replace placeholder fixtures and run the generated provider test before promotion."
        ),
        "claim_boundary": (
            "Generated scaffold is intentionally incomplete and not evidence of a real provider."
        ),
    }


def _batch_eval(workflow_dir: Path) -> JSONDict:
    app = _load_module(ROOT / "examples/hosts/batch-eval/app.py", "worldforge_batch_eval_demo")
    eval_result = app.run_eval_job(
        suite="planning",
        providers=["mock"],
        workspace_dir=workflow_dir / "batch-host",
        state_dir=workflow_dir / "worlds",
    )
    budget_file = workflow_dir / "impossible-budget.json"
    budget_file.write_text(
        json.dumps(
            {
                "budgets": [
                    {
                        "provider": "mock",
                        "operation": "predict",
                        "min_success_rate": 1.0,
                        "max_error_count": 0,
                        "max_average_latency_ms": 0.0,
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    benchmark_result = app.run_benchmark_job(
        providers=["mock"],
        operations=["predict"],
        iterations=1,
        concurrency=1,
        workspace_dir=workflow_dir / "batch-host",
        state_dir=workflow_dir / "worlds",
        budget_file=budget_file,
    )
    return {
        "status": "passed",
        "provider": "mock",
        "safe_to_attach": True,
        "summary": (
            "Ran batch host eval success and controlled benchmark budget failure with "
            "preserved manifests."
        ),
        "eval": eval_result,
        "benchmark": benchmark_result,
        "controlled_failure_exit_code": benchmark_result["exit_code"],
        "artifact_paths": {"budget_file": str(budget_file)},
        "first_triage_step": "Inspect the failed benchmark run manifest before changing budgets.",
        "claim_boundary": (
            "Batch host demo uses mock provider only; no scheduler or remote provider claim."
        ),
    }


def _service_host(workflow_dir: Path) -> JSONDict:
    app = _load_module(ROOT / "examples/hosts/service/app.py", "worldforge_service_host_demo")
    forge = WorldForge(state_dir=workflow_dir / "worlds", auto_register_remote=False)
    readiness = app.readiness_snapshot(forge, "mock")
    request = app.mock_prediction_payload(forge, request_id="demo-request")
    server = app.create_server(
        host="127.0.0.1",
        port=0,
        config=app.ServiceConfig(state_dir=workflow_dir / "worlds"),
    )
    server_address = f"http://127.0.0.1:{server.server_port}"
    server.server_close()
    return {
        "status": "passed",
        "provider": "mock",
        "safe_to_attach": True,
        "summary": (
            "Created the stdlib service host, checked readiness, handled one mock request, "
            "and closed it."
        ),
        "readiness": readiness,
        "request": request,
        "server_address": server_address,
        "shutdown": "server_close",
        "first_triage_step": (
            "Run `uv run python examples/hosts/service/app.py --help` and inspect `/readyz`."
        ),
        "claim_boundary": (
            "Stdlib host example only; auth, deployment, and uptime remain host-owned."
        ),
    }


def _rerun_gallery(workflow_dir: Path) -> JSONDict:
    layers = [
        {"name": "world_snapshots", "source": "mock world state"},
        {"name": "plans", "source": "mock plan artifact"},
        {"name": "benchmark_summary", "source": "mock benchmark report"},
        {"name": "robotics_replay", "source": "deterministic replay manifest"},
    ]
    manifest = {
        "schema_version": 1,
        "status": "skipped_missing_extra",
        "requires_extra": "rerun",
        "open_command": (
            "uv run --extra rerun rerun .worldforge/demo-showcases/rerun-gallery/gallery.rrd"
        ),
        "layers": layers,
        "safe_to_attach": True,
    }
    manifest_path = workflow_dir / "rerun-gallery-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "skipped",
        "provider": "mock",
        "safe_to_attach": True,
        "summary": (
            "Wrote a Rerun gallery manifest and clear missing-extra status without requiring a GUI."
        ),
        "manifest": manifest,
        "artifact_paths": {"gallery_manifest": str(manifest_path)},
        "first_triage_step": (
            "Install the `rerun` extra, then open the `.rrd` with the documented command."
        ),
        "claim_boundary": "Manifest-only checkout path; no remote viewer or live robot dependency.",
    }


def _failure_lab(workflow_dir: Path) -> JSONDict:
    lab_workspace = workflow_dir / "lab"
    drill_ids = ("missing-credentials", "corrupted-world-state", "unsafe-event-metadata")
    drills = [
        run_operator_drill(drill_id, workspace_dir=lab_workspace, bundle=True)
        for drill_id in drill_ids
    ]
    preflight = preflight_local_state(
        state_dir=lab_workspace / "worlds",
        workspace_dir=lab_workspace,
    )
    report = {
        "schema_version": 1,
        "drills": drills,
        "preflight": preflight,
        "expected_failures": [drill["failure_signal"] for drill in drills],
        "recovery_commands": [drill["recovery_command"] for drill in drills],
        "safe_to_attach": True,
    }
    report_path = workflow_dir / "failure-lab-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "passed",
        "provider": "fixture",
        "safe_to_attach": True,
        "summary": (
            "Ran failure drills and preflight under an isolated lab workspace with "
            "recovery commands."
        ),
        "report": report,
        "artifact_paths": {"lab_report": str(report_path)},
        "first_triage_step": (
            "Read the lab report recovery_commands before touching real `.worldforge` state."
        ),
        "claim_boundary": (
            "Lab mutates only its workspace; no real credentials or optional runtimes."
        ),
    }


def _cookbook(workflow_dir: Path) -> JSONDict:
    cookbook = ROOT / "docs/src/use-case-cookbook.md"
    recipe_count = cookbook.read_text(encoding="utf-8").count("### Recipe")
    return {
        "status": "passed",
        "provider": "docs",
        "safe_to_attach": True,
        "summary": f"Validated use-case cookbook with {recipe_count} task-oriented recipes.",
        "recipe_count": recipe_count,
        "artifact_paths": {"cookbook": str(cookbook)},
        "first_triage_step": (
            "Open the recipe matching the failed command and inspect its artifact row."
        ),
        "claim_boundary": (
            "Cookbook routes existing workflows; it does not add runtime integrations."
        ),
    }


def _external_provider_package(workflow_dir: Path) -> JSONDict:
    package_root = workflow_dir / "external-provider-package"
    source_root = package_root / "src"
    package_dir = source_root / "worldforge_demo_provider"
    tests_dir = package_root / "tests"
    package_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text('"""Checkout-safe WorldForge demo provider."""\n')
    pyproject_path = package_root / "pyproject.toml"
    pyproject_path.write_text(
        "\n".join(
            [
                "[project]",
                'name = "worldforge-demo-provider"',
                'version = "0.0.0"',
                'description = "Checkout-safe WorldForge external provider demo"',
                'requires-python = ">=3.13,<3.14"',
                'dependencies = ["worldforge"]',
                "",
                '[project.entry-points."worldforge.providers"]',
                'demo-external = "worldforge_demo_provider.provider:create_provider"',
                'needs-optional = "worldforge_demo_provider.needs_optional:create_provider"',
                'mock = "worldforge_demo_provider.provider:create_provider"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    provider_path = package_dir / "provider.py"
    provider_path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "from worldforge import Action, ProviderCapabilities",
                "from worldforge.providers import BaseProvider, PredictionPayload, "
                "ProviderProfileSpec",
                "",
                "",
                "class DemoExternalProvider(BaseProvider):",
                "    def __init__(self, *, event_handler=None) -> None:",
                "        super().__init__(",
                '            name="demo-external",',
                "            capabilities=ProviderCapabilities(predict=True),",
                "            profile=ProviderProfileSpec(",
                '                description="Checkout-safe external provider package demo.",',
                '                implementation_status="demo",',
                "                is_local=True,",
                "                deterministic=True,",
                "            ),",
                "            event_handler=event_handler,",
                "        )",
                "",
                "    def predict(",
                "        self, world_state: dict, action: Action, steps: int",
                "    ) -> PredictionPayload:",
                "        next_state = dict(world_state)",
                '        next_state["provider"] = self.name',
                '        next_state["step"] = int(next_state.get("step", 0)) + steps',
                "        return PredictionPayload(",
                "            world_state=next_state,",
                "            confidence=0.91,",
                "            physics_score=0.89,",
                "            latency_ms=0.5,",
                "        )",
                "",
                "",
                "def create_provider(*, event_handler=None) -> DemoExternalProvider:",
                "    return DemoExternalProvider(event_handler=event_handler)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    missing_path = package_dir / "needs_optional.py"
    missing_path.write_text(
        "\n".join(
            [
                "import worldforge_demo_missing_runtime",
                "",
                "",
                "def create_provider(*, event_handler=None):",
                "    return worldforge_demo_missing_runtime.create_provider(",
                "        event_handler=event_handler",
                "    )",
                "",
            ]
        ),
        encoding="utf-8",
    )
    generated_test = tests_dir / "test_demo_external_provider.py"
    generated_test.write_text(
        "\n".join(
            [
                "from worldforge_demo_provider.provider import create_provider",
                "",
                "",
                "def test_provider_factory_name_matches_entry_point():",
                '    assert create_provider().name == "demo-external"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    for path in (provider_path, missing_path, generated_test):
        py_compile.compile(str(path), doraise=True)

    entry_points = (
        EntryPoint(
            name="demo-external",
            value="worldforge_demo_provider.provider:create_provider",
            group=ENTRY_POINT_GROUP,
        ),
        EntryPoint(
            name="needs-optional",
            value="worldforge_demo_provider.needs_optional:create_provider",
            group=ENTRY_POINT_GROUP,
        ),
        EntryPoint(
            name="mock",
            value="worldforge_demo_provider.provider:create_provider",
            group=ENTRY_POINT_GROUP,
        ),
    )

    def entry_points_provider(group: str) -> tuple[EntryPoint, ...]:
        return entry_points if group == ENTRY_POINT_GROUP else ()

    sys.path.insert(0, str(source_root))
    try:
        discovery = discover_entry_point_providers(
            enabled=True,
            catalog=PROVIDER_CATALOG,
            entry_points_provider=entry_points_provider,
        )
        disabled = discover_entry_point_providers(
            enabled=False,
            catalog=PROVIDER_CATALOG,
            entry_points_provider=entry_points_provider,
        )
        provider = discovery.entries[0].create()
    finally:
        with suppress(ValueError):
            sys.path.remove(str(source_root))
        for module_name in tuple(sys.modules):
            if module_name.startswith("worldforge_demo_provider"):
                sys.modules.pop(module_name, None)

    report = {
        "schema_version": 1,
        "entry_point_group": ENTRY_POINT_GROUP,
        "package_root": str(package_root),
        "generated_files": sorted(
            str(path.relative_to(package_root))
            for path in package_root.rglob("*")
            if path.is_file()
        ),
        "discovery_enabled": discovery.to_dict(),
        "discovery_disabled": disabled.to_dict(),
        "provider": {
            "name": provider.name,
            "capabilities": provider.capabilities.to_dict(),
            "configured": provider.configured(),
            "description": provider.description,
        },
        "skip_reasons": {skip.name: skip.reason for skip in discovery.skipped},
        "safe_to_attach": True,
    }
    report_path = workflow_dir / "external-provider-discovery.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "status": "passed",
        "provider": "demo-external",
        "safe_to_attach": True,
        "summary": (
            "Generated a temp external provider package and proved entry-point discovery, "
            "disabled discovery, duplicate-name skips, and missing optional dependency skips."
        ),
        "report": report,
        "artifact_paths": {
            "discovery_report": str(report_path),
            "pyproject": str(pyproject_path),
            "provider": str(provider_path),
            "generated_test": str(generated_test),
        },
        "first_triage_step": (
            "Inspect `external-provider-discovery.json`, then run the generated provider package "
            "tests in the temp package before publishing."
        ),
        "claim_boundary": (
            "Checkout-safe package-shape demo only; no PyPI publishing, credentialed provider, "
            "or remote call."
        ),
    }


def _custom_evaluation_suite(workflow_dir: Path) -> JSONDict:
    example = _load_module(
        ROOT / "examples/custom_evaluation_suite.py",
        "worldforge_custom_evaluation_demo",
    )
    walkthrough = example.run_walkthrough(
        output_dir=workflow_dir / "custom-eval-artifacts",
        state_dir=workflow_dir / "worlds",
    )
    artifact_paths = dict(walkthrough["artifact_paths"])
    return {
        "status": "passed",
        "provider": "mock",
        "safe_to_attach": True,
        "summary": (
            "Ran a custom evaluation suite with provenance, deterministic metrics, one "
            "controlled failure, and JSON/Markdown/HTML/failure-gallery artifacts."
        ),
        "walkthrough": walkthrough,
        "artifact_paths": artifact_paths,
        "first_triage_step": (
            "Open `custom-eval-artifacts/markdown` first, then inspect "
            "`failure_gallery.md` for the controlled failed case."
        ),
        "claim_boundary": walkthrough["claim_boundary"],
    }


def _policy_score_candidate_lab(workflow_dir: Path) -> JSONDict:
    candidate_plans = bounded_move_grid_candidates(
        x_bounds=(0.1, 0.7),
        y_bounds=(0.5, 0.5),
        z_bounds=(0.0, 0.0),
        x_steps=3,
        y_steps=1,
        z_steps=1,
        object_id="cube-1",
    )
    score_payload = action_candidates_to_score_payload(candidate_plans)
    scores = [0.72, 0.18, 0.44]
    forge = WorldForge(state_dir=workflow_dir / "worlds", auto_register_remote=False)
    forge.register_provider(_CandidateLabPolicy(candidate_plans))
    forge.register_provider(_CandidateLabScore(scores))
    world = forge.create_world("candidate-lab-world", provider="mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
            id="cube-1",
        )
    )
    plan = world.plan(
        goal="choose the lowest-cost candidate",
        policy_provider="candidate-lab-policy",
        score_provider="candidate-lab-score",
        policy_info={"observation": "checkout-safe grid"},
        score_info={"goal": "move cube near center"},
        execution_provider="mock",
    )
    execution = world.execute_plan(plan)
    selected_index = int(plan.metadata["score_result"]["best_index"])

    invalid_bounds_error = ""
    try:
        bounded_move_grid_candidates(
            x_bounds=(1.0, 0.0),
            y_bounds=(0.5, 0.5),
            z_bounds=(0.0, 0.0),
            x_steps=3,
            y_steps=1,
            z_steps=1,
        )
    except Exception as exc:
        invalid_bounds_error = str(exc)

    translator_missing_error = ""
    try:
        _CandidateLabPolicy(candidate_plans, translator_available=False).select_actions(
            info={"observation": "checkout-safe grid"}
        )
    except ProviderError as exc:
        translator_missing_error = str(exc)

    candidate_table = [
        {
            "index": index,
            "score": scores[index],
            "selected": index == selected_index,
            "actions": [action.to_dict() for action in candidate],
        }
        for index, candidate in enumerate(candidate_plans)
    ]
    report = {
        "schema_version": 1,
        "safe_to_attach": True,
        "planning_mode": plan.metadata["planning_mode"],
        "policy_provider": plan.metadata["policy_provider"],
        "score_provider": plan.metadata["score_provider"],
        "candidate_count": len(candidate_plans),
        "score_payload": score_payload,
        "candidate_table": candidate_table,
        "selected_candidate_index": selected_index,
        "selected_action": plan.actions[0].to_dict(),
        "raw_policy_actions": plan.metadata["policy_result"]["raw_actions"],
        "score_metadata": plan.metadata["score_result"]["metadata"],
        "workflow_trace": plan.metadata["workflow_trace"],
        "execution_final_step": execution.final_world().step,
        "expected_failures": {
            "invalid_candidate_bounds": invalid_bounds_error,
            "missing_translator": translator_missing_error,
        },
        "claim_boundary": (
            "Checkout-safe deterministic candidate lab only; no robot controller, simulator, "
            "checkpoint download, or physical-performance claim."
        ),
    }
    report_path = workflow_dir / "policy-score-candidate-lab.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = workflow_dir / "policy-score-candidate-lab.md"
    markdown_lines = [
        "# Policy+Score Candidate Lab",
        "",
        f"- planning_mode: `{report['planning_mode']}`",
        f"- selected_candidate_index: `{selected_index}`",
        f"- candidate_count: `{len(candidate_plans)}`",
        "",
        "| index | score | selected | target_x |",
        "| ---: | ---: | --- | ---: |",
    ]
    markdown_lines.extend(
        "| {index} | {score:.2f} | {selected} | {target_x:.2f} |".format(
            index=row["index"],
            score=row["score"],
            selected="yes" if row["selected"] else "no",
            target_x=row["actions"][0]["parameters"]["target"]["x"],
        )
        for row in candidate_table
    )
    markdown_lines.extend(
        [
            "",
            "## Expected Failures",
            "",
            f"- invalid_candidate_bounds: {invalid_bounds_error}",
            f"- missing_translator: {translator_missing_error}",
            "",
            report["claim_boundary"],
        ]
    )
    markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    return {
        "status": "passed",
        "provider": "candidate-lab-policy+candidate-lab-score",
        "safe_to_attach": True,
        "summary": (
            "Generated deterministic action candidates, preserved raw policy actions, ranked "
            "them with a score provider, selected the lowest-cost action, and captured invalid "
            "bounds plus missing-translator failures."
        ),
        "report": report,
        "artifact_paths": {
            "lab_report": str(report_path),
            "lab_markdown": str(markdown_path),
        },
        "first_triage_step": (
            "Open `policy-score-candidate-lab.md` and verify the selected row matches "
            "`score_result.best_index`."
        ),
        "claim_boundary": report["claim_boundary"],
    }


def _fixture_drift_review(workflow_dir: Path) -> JSONDict:
    lab_root = workflow_dir / "fixture-drift-lab"
    provider_fixture = lab_root / "tests/fixtures/providers/demo_provider_payload.json"
    benchmark_fixture = lab_root / "examples/demo-benchmark-inputs.json"
    scenario_fixture = lab_root / "examples/scenarios/demo-scenario.json"
    for path, payload in (
        (
            provider_fixture,
            {"schema_version": 1, "provider": "mock", "status": "baseline"},
        ),
        (
            benchmark_fixture,
            {"schema_version": 1, "inputs": [{"provider": "mock", "operation": "predict"}]},
        ),
        (
            scenario_fixture,
            {
                "schema_version": 1,
                "id": "demo-scenario",
                "description": "Fixture drift walkthrough scenario.",
            },
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    baseline = build_fixture_snapshot_manifest(
        (provider_fixture, benchmark_fixture, scenario_fixture),
        root=lab_root,
    )
    baseline_report = validate_fixture_snapshot_manifest(baseline, root=lab_root)
    baseline_manifest_path = lab_root / "fixture-snapshots-baseline.json"
    baseline_manifest_path.write_text(
        json.dumps(baseline.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    missing_fixture = lab_root / "tests/fixtures/providers/missing_payload.json"
    provider_path = provider_fixture.relative_to(lab_root).as_posix()
    benchmark_path = benchmark_fixture.relative_to(lab_root).as_posix()
    scenario_path = scenario_fixture.relative_to(lab_root).as_posix()
    missing_entry = replace(
        next(entry for entry in baseline.entries if entry.path == provider_path),
        path=missing_fixture.relative_to(lab_root).as_posix(),
    )
    changed_payload = {"schema_version": 1, "inputs": [{"provider": "mock", "operation": "embed"}]}
    benchmark_fixture.write_text(
        json.dumps(changed_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    scenario_fixture.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "id": "demo-scenario",
                "description": "Fixture drift walkthrough schema change.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    unsafe_entry = FixtureSnapshotEntry(
        path="../private/provider-secret.json",
        sha256="sha256:" + "0" * 64,
        size_bytes=1,
        fixture_kind="provider-payload-fixture",
        fixture_schema_version=1,
    )
    review_manifest = FixtureSnapshotManifest(
        entries=(
            missing_entry,
            *baseline.entries[1:],
            unsafe_entry,
        )
    )
    review_report = validate_fixture_snapshot_manifest(review_manifest, root=lab_root)
    review_manifest_path = lab_root / "fixture-snapshots-review.json"
    review_json_path = workflow_dir / "fixture-drift-review.json"
    review_markdown_path = workflow_dir / "fixture-drift-review.md"
    review_manifest_path.write_text(
        json.dumps(review_manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_json_path.write_text(
        json.dumps(review_report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_markdown_path.write_text(review_report.to_markdown() + "\n", encoding="utf-8")

    intended_manifest = FixtureSnapshotManifest(
        entries=tuple(
            replace(entry, review_status="intended-update")
            if entry.path in {benchmark_path, scenario_path}
            else entry
            for entry in baseline.entries
        )
    )
    intended_report = validate_fixture_snapshot_manifest(
        intended_manifest,
        root=lab_root,
        allow_intended_updates=True,
    )
    refreshed = build_fixture_snapshot_manifest(
        (provider_fixture, benchmark_fixture, scenario_fixture),
        root=lab_root,
    )
    refreshed_manifest_path = lab_root / "fixture-snapshots-refreshed.json"
    intended_json_path = workflow_dir / "fixture-drift-intended-update.json"
    refreshed_manifest_path.write_text(
        json.dumps(refreshed.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    intended_json_path.write_text(
        json.dumps(intended_report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "safe_to_attach": True,
        "baseline_passed": baseline_report.passed,
        "review_passed": review_report.passed,
        "intended_update_passed": intended_report.passed,
        "review_summary": review_report.summary,
        "review_statuses": [issue.status for issue in review_report.issues],
        "managed_fixture_kinds": sorted({entry.fixture_kind for entry in baseline.entries}),
        "approved_update_path": [
            "Mark the reviewed manifest entry as review_status=intended-update.",
            "Run the snapshot manager with --allow-intended-updates for human review.",
            "After approving fixture and manifest diffs, refresh the manifest with --write.",
        ],
        "claim_boundary": (
            "Checkout-safe fixture drift walkthrough only; all mutations occur under the "
            "selected demo workspace."
        ),
    }
    summary_path = workflow_dir / "fixture-drift-summary.json"
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "passed",
        "provider": "fixture-snapshot-manager",
        "safe_to_attach": True,
        "summary": (
            "Created a controlled fixture drift review covering missing, changed, schema-change, "
            "unsafe-path, and intended-update paths under a temp workspace."
        ),
        "report": report,
        "artifact_paths": {
            "summary": str(summary_path),
            "baseline_manifest": str(baseline_manifest_path),
            "review_manifest": str(review_manifest_path),
            "review_json": str(review_json_path),
            "review_markdown": str(review_markdown_path),
            "intended_update_json": str(intended_json_path),
            "refreshed_manifest": str(refreshed_manifest_path),
        },
        "first_triage_step": (
            "Open `fixture-drift-review.md`, inspect every changed fixture diff, then approve "
            "intentional updates before rewriting the manifest."
        ),
        "claim_boundary": report["claim_boundary"],
    }


def _capability_negotiation_preflight(workflow_dir: Path) -> JSONDict:
    clear_env = {
        "COSMOS_BASE_URL": "",
        "RUNWAYML_API_SECRET": "",
        "RUNWAY_API_SECRET": "",
        "LEWORLDMODEL_POLICY": "",
        "LEWM_POLICY": "",
        "LEROBOT_POLICY_PATH": "",
        "LEROBOT_POLICY": "",
        "GROOT_POLICY_HOST": "",
    }
    forge = WorldForge(state_dir=workflow_dir / "worlds", auto_register_remote=False)
    forge.register_provider(_UnhealthyTransferProvider())
    main_report = negotiate(
        [
            "predict-only",
            "generate-only",
            "transfer-only",
            "score-only",
            "policy-plus-score",
            "evaluation-physics",
        ],
        forge=forge,
        environ=clear_env,
    )
    not_registered_forge = WorldForge(
        state_dir=workflow_dir / "not-registered-worlds",
        auto_register_remote=False,
    )
    not_registered_report = negotiate(
        ["generate-only"],
        forge=not_registered_forge,
        environ={"COSMOS_BASE_URL": "https://cosmos.example.invalid"},
    )
    reports_dir = workflow_dir / "capability-negotiation"
    reports_dir.mkdir(parents=True, exist_ok=True)
    main_json = reports_dir / "preflight-report.json"
    main_markdown = reports_dir / "preflight-report.md"
    not_registered_json = reports_dir / "not-registered-report.json"
    main_json.write_text(
        json.dumps(main_report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    main_markdown.write_text(main_report.to_markdown(), encoding="utf-8")
    not_registered_json.write_text(
        json.dumps(not_registered_report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    readiness_values = sorted(
        {
            status["readiness"]
            for workflow in main_report.to_dict()["workflows"]
            for requirement in workflow["requirements"]
            for status in requirement["candidates"]
        }
        | {
            status["readiness"]
            for workflow in not_registered_report.to_dict()["workflows"]
            for requirement in workflow["requirements"]
            for status in requirement["candidates"]
        }
    )
    unsupported_example = {
        "provider": "demo-unhealthy-transfer",
        "capability": "policy",
        "readiness": "unsupported",
        "reason": "provider 'demo-unhealthy-transfer' does not advertise capability 'policy'",
    }
    report = {
        "schema_version": 1,
        "safe_to_attach": True,
        "workflow_shapes": [
            "predict-only",
            "generate-only",
            "transfer-only",
            "score-only",
            "policy-plus-score",
            "evaluation-physics",
        ],
        "readiness_values": readiness_values,
        "unsupported_example": unsupported_example,
        "recommended_actions": [
            action
            for workflow in main_report.to_dict()["workflows"]
            for action in workflow["recommended_actions"]
        ],
        "claim_boundary": (
            "Checkout-safe preflight only; this report does not install dependencies, configure "
            "credentials, or execute fallback workflows."
        ),
    }
    summary_path = workflow_dir / "capability-negotiation-preflight.json"
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "passed",
        "provider": "capability-negotiation",
        "safe_to_attach": True,
        "summary": (
            "Preserved capability negotiation reports for ready, missing-config, "
            "missing-dependency, unsupported, and not-registered preflight cases."
        ),
        "report": report,
        "artifact_paths": {
            "summary": str(summary_path),
            "preflight_json": str(main_json),
            "preflight_markdown": str(main_markdown),
            "not_registered_json": str(not_registered_json),
        },
        "first_triage_step": (
            "Open `capability-negotiation/preflight-report.md` and follow the first "
            "recommended action for the blocked capability slot."
        ),
        "claim_boundary": report["claim_boundary"],
    }


def _copy_artifact_paths(run_workspace: Any, artifact_paths: object) -> dict[str, str]:
    if not isinstance(artifact_paths, dict):
        return {}
    preserved: dict[str, str] = {}
    for key, value in artifact_paths.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_file():
            continue
        safe_key = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in key
        ).strip("_")
        target_name = f"{safe_key or 'artifact'}{path.suffix}"
        relative_path = f"artifacts/{target_name}"
        shutil.copyfile(path, run_workspace.path / relative_path)
        preserved[key] = relative_path
    return preserved


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _workflow_ids() -> tuple[str, ...]:
    return tuple(workflow.id for workflow in WORKFLOWS)


def _workflow_by_id(workflow_id: str) -> DemoWorkflow:
    for workflow in WORKFLOWS:
        if workflow.id == workflow_id:
            return workflow
    raise KeyError(workflow_id)


WORKFLOWS = (
    DemoWorkflow("first-run", "First-run local world workflow", 189, _first_run),
    DemoWorkflow(
        "diagnostics-issue-bundle",
        "Provider diagnostics to issue bundle",
        190,
        _issue_bundle,
    ),
    DemoWorkflow("robotics-replay", "Guided robotics showcase replay", 191, _robotics_replay),
    DemoWorkflow(
        "remote-media-dry-run",
        "Remote media dry-run showcase",
        192,
        _remote_media_dry_run,
    ),
    DemoWorkflow("adapter-author", "Adapter author journey", 193, _adapter_author),
    DemoWorkflow("batch-eval", "Batch evaluation host walkthrough", 194, _batch_eval),
    DemoWorkflow("service-host", "Stdlib service host use case", 195, _service_host),
    DemoWorkflow("rerun-gallery", "Rerun visual gallery showcase", 196, _rerun_gallery),
    DemoWorkflow("failure-lab", "Failure recovery lab", 197, _failure_lab),
    DemoWorkflow("use-case-cookbook", "Use case cookbook", 198, _cookbook),
    DemoWorkflow(
        "external-provider-package",
        "External provider package demo",
        237,
        _external_provider_package,
    ),
    DemoWorkflow(
        "custom-evaluation-suite",
        "Custom evaluation suite walkthrough",
        238,
        _custom_evaluation_suite,
    ),
    DemoWorkflow(
        "policy-score-candidate-lab",
        "Policy+score candidate lab",
        239,
        _policy_score_candidate_lab,
    ),
    DemoWorkflow(
        "fixture-drift-review",
        "Fixture drift review walkthrough",
        240,
        _fixture_drift_review,
    ),
    DemoWorkflow(
        "capability-negotiation-preflight",
        "Capability negotiation preflight demo",
        241,
        _capability_negotiation_preflight,
    ),
)


if __name__ == "__main__":
    raise SystemExit(main())
