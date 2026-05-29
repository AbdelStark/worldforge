"""Run checkout-safe performance budgets for core WorldForge paths."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge import WorldForge  # noqa: E402
from worldforge.benchmark import load_benchmark_inputs  # noqa: E402
from worldforge.evaluation import EvaluationSuite  # noqa: E402
from worldforge.evidence_bundle import generate_evidence_bundle  # noqa: E402
from worldforge.harness.workspace import create_run_workspace, write_run_manifest  # noqa: E402

DEFAULT_BUDGETS_MS = {
    "world_persistence": 250.0,
    "benchmark_fixture_loading": 100.0,
    "provider_catalog_diagnostics": 250.0,
    "evidence_bundle_creation": 500.0,
    "report_rendering": 250.0,
}


@dataclass(frozen=True, slots=True)
class CorePerformanceResult:
    name: str
    duration_ms: float
    budget_ms: float | None
    passed: bool
    artifact_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "budget_ms": self.budget_ms,
            "passed": self.passed,
            "artifact_path": self.artifact_path,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-file", type=Path, help="JSON file mapping operation to max ms.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        help="Preserve run artifacts under this workspace instead of a temporary directory.",
    )
    args = parser.parse_args(argv)
    budgets = _load_budgets(args.budget_file) if args.budget_file else DEFAULT_BUDGETS_MS
    payload = run_core_performance_budgets(budgets=budgets, workspace_dir=args.workspace_dir)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if payload["passed"] else 1


def run_core_performance_budgets(
    *,
    budgets: dict[str, float] | None = None,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    """Measure checkout-safe core paths against optional millisecond budgets."""

    resolved_budgets = budgets or DEFAULT_BUDGETS_MS
    if workspace_dir is None:
        with tempfile.TemporaryDirectory(prefix="worldforge-core-perf-") as tmp:
            return _run(Path(tmp), budgets=resolved_budgets, preserve=False)
    workspace = workspace_dir.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return _run(workspace, budgets=resolved_budgets, preserve=True)


def _run(workspace: Path, *, budgets: dict[str, float], preserve: bool) -> dict[str, Any]:
    results = [
        _measure("world_persistence", budgets, lambda: _world_persistence(workspace)),
        _measure("benchmark_fixture_loading", budgets, _benchmark_fixture_loading),
        _measure("provider_catalog_diagnostics", budgets, lambda: _provider_catalog(workspace)),
        _measure("evidence_bundle_creation", budgets, lambda: _evidence_bundle(workspace)),
        _measure("report_rendering", budgets, lambda: _report_rendering(workspace)),
    ]
    payload = {
        "schema_version": 1,
        "passed": all(result.passed for result in results),
        "preserved_workspace": str(workspace) if preserve else None,
        "results": [result.to_dict() for result in results],
        "claim_boundary": (
            "These checkout-safe budgets detect local regressions only. They are not a public "
            "leaderboard, cross-machine performance claim, or optional-runtime benchmark."
        ),
    }
    if preserve:
        (workspace / "core-performance.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def _measure(
    name: str,
    budgets: dict[str, float],
    operation: Callable[[], str | None],
) -> CorePerformanceResult:
    started = perf_counter()
    artifact_path = operation()
    duration_ms = round((perf_counter() - started) * 1000, 3)
    budget = budgets.get(name)
    return CorePerformanceResult(
        name=name,
        duration_ms=duration_ms,
        budget_ms=budget,
        passed=budget is None or duration_ms <= budget,
        artifact_path=artifact_path,
    )


def _world_persistence(workspace: Path) -> str | None:
    forge = WorldForge(state_dir=workspace / "worlds", auto_register_remote=False)
    world = forge.create_world_from_prompt("A table with one cube", provider="mock", name="perf")
    forge.save_world(world)
    reloaded = forge.load_world(world.id)
    if reloaded.id != world.id:
        raise RuntimeError("world persistence reload mismatch")
    return str((workspace / "worlds" / f"{world.id}.json").resolve())


def _benchmark_fixture_loading() -> str | None:
    input_file = ROOT / "examples/benchmark-inputs.json"
    inputs = load_benchmark_inputs(
        json.loads(input_file.read_text(encoding="utf-8")),
        base_path=input_file.parent,
    )
    if inputs.embedding_text == "":
        raise RuntimeError("benchmark fixture did not load")
    return "examples/benchmark-inputs.json"


def _provider_catalog(workspace: Path) -> str | None:
    forge = WorldForge(state_dir=workspace / "doctor-worlds", auto_register_remote=False)
    report = forge.doctor(registered_only=True)
    if report.provider_count < 1:
        raise RuntimeError("doctor returned no providers")
    path = workspace / "doctor-report.json"
    path.write_text(report.to_json(), encoding="utf-8")
    return str(path)


def _evidence_bundle(workspace: Path) -> str | None:
    run_workspace = create_run_workspace(
        workspace,
        kind="benchmark",
        command="worldforge benchmark --provider mock",
        provider="mock",
        operation="benchmark",
        input_summary={"provider": "mock"},
    )
    run_workspace.write_json("reports/report.json", {"schema_version": 1, "status": "passed"})
    write_run_manifest(
        run_workspace,
        kind="benchmark",
        command="worldforge benchmark --provider mock",
        provider="mock",
        operation="benchmark",
        status="passed",
        input_summary={"provider": "mock"},
        result_summary={"status": "passed"},
    )
    result = generate_evidence_bundle(
        workspace_dir=workspace,
        output_dir=workspace / "evidence-bundle",
        overwrite=True,
        include_fixture_digests=False,
    )
    return str(result.manifest_path)


def _report_rendering(workspace: Path) -> str | None:
    forge = WorldForge(state_dir=workspace / "report-worlds", auto_register_remote=False)
    report = EvaluationSuite.from_builtin("planning").run_report(["mock"], forge=forge)
    markdown = report.to_markdown()
    if "# Evaluation Report" not in markdown:
        raise RuntimeError("evaluation report renderer returned unexpected Markdown")
    path = workspace / "report.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def _load_budgets(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("core performance budget file must be a JSON object")
    budgets: dict[str, float] = {}
    for key, value in payload.items():
        if (
            not isinstance(key, str)
            or isinstance(value, bool)
            or not isinstance(value, int | float)
            or value < 0
        ):
            raise SystemExit("core performance budgets must map operation names to non-negative ms")
        budgets[key] = float(value)
    return budgets


if __name__ == "__main__":
    raise SystemExit(main())
