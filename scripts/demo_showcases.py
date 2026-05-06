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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge import Action, BBox, Position, SceneObject, WorldForge  # noqa: E402
from worldforge.demos import lerobot_e2e  # noqa: E402
from worldforge.evidence_bundle import generate_issue_bundle  # noqa: E402
from worldforge.harness.workspace import create_run_workspace, write_run_manifest  # noqa: E402
from worldforge.models import JSONDict, ProviderEvent, dump_json  # noqa: E402
from worldforge.operator_drills import run_operator_drill  # noqa: E402
from worldforge.persistence_preflight import preflight_local_state  # noqa: E402

DEFAULT_WORKSPACE = Path(".worldforge/demo-showcases")


@dataclass(frozen=True, slots=True)
class DemoWorkflow:
    id: str
    title: str
    issue: int
    runner: Callable[[Path], JSONDict]


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
)


if __name__ == "__main__":
    raise SystemExit(main())
