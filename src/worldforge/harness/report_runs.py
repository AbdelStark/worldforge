"""Evaluation and benchmark report helpers for preserved showcase runs."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from worldforge.artifact_io import write_json_artifact
from worldforge.benchmark import BenchmarkReport, BenchmarkResult, ProviderBenchmarkHarness
from worldforge.evaluation import EvaluationReport, EvaluationResult, EvaluationSuite
from worldforge.framework import WorldForge
from worldforge.harness.models import HarnessFlow, HarnessMetric, HarnessRun, HarnessStep
from worldforge.harness.workspace import RunWorkspace, create_run_workspace, write_run_manifest
from worldforge.models import JSONDict, WorldForgeError, require_json_dict
from worldforge.provenance import ProvenanceEnvelope


def eval_run_artifacts(
    forge: WorldForge,
    suite_id: str,
    providers: str | Sequence[str],
    *,
    world=None,
) -> tuple[dict[str, str], EvaluationReport]:
    """Run an evaluation suite and return canonical report artifacts.

    This helper is intentionally Textual-free. The TUI and tests both call it so
    the strings shown in showcase reports stay byte-identical to the CLI report
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
    payload = _report_json_payload(artifacts["json"], artifact_name="json")
    reports_dir = forge.state_dir / "reports"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    safe_kind = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in kind).strip("-")
    path = reports_dir / f"{safe_kind}-{timestamp}-{run_id}.json"
    write_json_artifact(path, payload)
    return path.resolve()


def eval_report_harness_run(
    suite_id: str,
    artifacts: dict[str, str],
    payload: JSONDict,
    *,
    path: Path,
    state_dir: Path,
) -> HarnessRun:
    """Build the live TUI ``HarnessRun`` for a just-completed evaluation report."""

    results = list(payload.get("results", []))
    summaries = list(payload.get("provider_summaries", []))
    passed = sum(1 for result in results if result.get("passed"))
    total = len(results)
    flow = HarnessFlow(
        id=f"eval-{suite_id}",
        title=f"Evaluation: {payload.get('suite', suite_id)}",
        short_title=f"Eval {suite_id}",
        focus="evaluation",
        provider=", ".join(str(summary.get("provider", "provider")) for summary in summaries)
        or "provider",
        capability="eval",
        command=f"worldforge eval --suite {suite_id}",
        accent="",
        summary=f"{passed}/{total} scenarios passed.",
    )
    return HarnessRun(
        flow=flow,
        state_dir=state_dir,
        summary=payload,
        steps=(
            HarnessStep("Run evaluation", "Execute built-in suite.", f"{passed}/{total} passed."),
        ),
        metrics=tuple(
            HarnessMetric(
                str(summary.get("provider", "provider")),
                f"{summary.get('passed_scenario_count', 0)}/{summary.get('scenario_count', 0)}",
                f"average_score={float(summary.get('average_score', 0.0)):.2f}",
            )
            for summary in summaries
        ),
        transcript=("kind: eval", f"suite: {suite_id}", f"report_path: {path}"),
        kind="eval",
        report_path=path,
        artifacts=artifacts,
    )


def benchmark_report_harness_run(
    artifacts: dict[str, str],
    payload: JSONDict,
    *,
    path: Path,
    state_dir: Path,
) -> HarnessRun:
    """Build the live TUI ``HarnessRun`` for a just-completed benchmark report."""

    results = list(payload.get("results", []))
    flow = HarnessFlow(
        id="benchmark",
        title="Benchmark Report",
        short_title="Benchmark",
        focus="latency / retry / throughput",
        provider=", ".join(sorted({str(result.get("provider", "provider")) for result in results}))
        or "provider",
        capability="benchmark",
        command="worldforge benchmark",
        accent="",
        summary=f"{len(results)} benchmark rows.",
    )
    return HarnessRun(
        flow=flow,
        state_dir=state_dir,
        summary=payload,
        steps=(
            HarnessStep("Run benchmark", "Execute provider operations.", f"{len(results)} rows."),
        ),
        metrics=tuple(
            HarnessMetric(
                f"{result.get('provider')}.{result.get('operation')}",
                f"{float(result.get('average_latency_ms') or 0.0):.2f} ms",
                f"ok={result.get('success_count')}/{result.get('iterations')}",
            )
            for result in results
        ),
        transcript=("kind: benchmark", f"report_path: {path}", f"rows: {len(results)}"),
        kind="benchmark",
        report_path=path,
        artifacts=artifacts,
    )


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


def _write_report_artifacts(workspace: RunWorkspace, artifacts: dict[str, str]) -> dict[str, str]:
    json_payloads = {
        name: _report_json_payload(content, artifact_name=name)
        for name, content in artifacts.items()
        if _is_json_report_artifact(name)
    }
    paths: dict[str, str] = {}
    for name, content in artifacts.items():
        relative_path = _report_artifact_relative_path(name)
        if name in json_payloads:
            path = workspace.write_json(relative_path, json_payloads[name])
        else:
            path = workspace.write_text(relative_path, content)
        paths[name] = str(path.relative_to(workspace.path))
    return paths


def _is_json_report_artifact(name: str) -> bool:
    return name == "json" or name.endswith(".json")


def _report_artifact_relative_path(name: str) -> str:
    suffix = "md" if name == "markdown" else name
    return f"reports/report.{suffix}"


def _report_json_payload(content: str, *, artifact_name: str) -> JSONDict:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(
            f"Report artifact {artifact_name!r} must contain valid JSON."
        ) from exc
    return require_json_dict(payload, name=f"Report artifact {artifact_name!r}")
