"""Flow definitions and runners for TheWorldHarness."""

from __future__ import annotations

import json
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
from worldforge.models import JSONDict

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
    "diagnostics": _run_diagnostics_demo,
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
        raise ValueError(f"unknown harness flow '{flow_id}'. Valid flows: {valid}.")

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
    summary = _RUNNERS[flow_id](state_dir=resolved_state_dir, emit=False)
    run = HarnessRun(
        flow=flow,
        state_dir=resolved_state_dir,
        summary=summary,
        steps=_steps_for(flow_id, summary),
        metrics=_metrics_for(flow_id, summary),
        transcript=_transcript_for(flow_id, summary),
        workspace_path=workspace.path,
    )
    _write_flow_workspace(workspace, run)
    return run


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
) -> RunWorkspace:
    """Preserve an evaluation report in the shared run workspace layout."""

    workspace = create_run_workspace(
        workspace_dir,
        kind="eval",
        command=command,
        provider=", ".join(providers),
        operation=suite_id,
        input_summary={"suite_id": suite_id, "providers": list(providers)},
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
        input_summary={"suite_id": suite_id, "providers": list(providers)},
        result_summary=result_summary,
        artifact_paths=paths,
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
    )
    return report.artifacts()


def _benchmark_artifacts_from_payload(payload: JSONDict) -> dict[str, str]:
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
    event_count = 0
    event_phases = run.summary.get("event_phases")
    if isinstance(event_phases, list):
        event_count = len(event_phases)
        workspace.write_text(
            "logs/provider-events.jsonl",
            "\n".join(
                json.dumps(
                    {
                        "event_type": "provider_event_summary",
                        "provider": run.flow.provider,
                        "operation": run.flow.id,
                        "phase": str(phase),
                    },
                    sort_keys=True,
                )
                for phase in event_phases
            ),
        )
    artifact_paths = {
        "summary": str(summary_path.relative_to(workspace.path)),
        "steps": str(steps_path.relative_to(workspace.path)),
        "metrics": str(metrics_path.relative_to(workspace.path)),
        "transcript": str(transcript_path.relative_to(workspace.path)),
    }
    write_run_manifest(
        workspace,
        kind="flow",
        command=run.flow.command,
        provider=run.flow.provider,
        operation=run.flow.id,
        status="completed",
        input_summary={"flow_id": run.flow.id, "state_dir": str(run.state_dir)},
        result_summary={
            "step_count": len(run.steps),
            "metric_count": len(run.metrics),
            "summary_keys": sorted(run.summary),
        },
        artifact_paths=artifact_paths,
        event_count=event_count,
    )


def _write_report_artifacts(workspace: RunWorkspace, artifacts: dict[str, str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for name, content in artifacts.items():
        suffix = "md" if name == "markdown" else name
        path = workspace.write_text(f"reports/report.{suffix}", content)
        paths[name] = str(path.relative_to(workspace.path))
    return paths


def _steps_for(flow_id: str, summary: JSONDict) -> tuple[HarnessStep, ...]:
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
    raise ValueError(f"unknown harness flow '{flow_id}'")


def _metrics_for(flow_id: str, summary: JSONDict) -> tuple[HarnessMetric, ...]:
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


def _position(summary: JSONDict) -> str:
    final = summary["final_cube_position"]
    return f"({final['x']:.2f}, {final['y']:.2f}, {final['z']:.2f})"


def _format_ms(value: object) -> str:
    return f"{float(value):.2f} ms"
