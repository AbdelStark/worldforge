"""Checkout-safe non-robotics flow runners for preserved showcase evidence."""

from __future__ import annotations

from pathlib import Path

from worldforge.benchmark import ProviderBenchmarkHarness
from worldforge.framework import WorldForge
from worldforge.models import JSONDict


def run_diagnostics_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
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


def run_workbench_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
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
