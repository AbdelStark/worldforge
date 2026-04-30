"""Stdlib batch evaluation host for WorldForge eval and benchmark jobs."""

from __future__ import annotations

import argparse
import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any

from worldforge import WorldForge, WorldForgeError
from worldforge.benchmark import (
    ProviderBenchmarkHarness,
    load_benchmark_budgets,
    load_benchmark_inputs,
)
from worldforge.evaluation import EvaluationSuite
from worldforge.harness.flows import (
    preserve_benchmark_run_workspace,
    preserve_eval_run_workspace,
)

JSON = dict[str, Any]
DEFAULT_WORKSPACE = Path(".worldforge/batch-eval")
DEFAULT_STATE_DIR = Path(".worldforge/batch-eval/worlds")


def run_eval_job(
    *,
    suite: str,
    providers: list[str],
    workspace_dir: Path,
    state_dir: Path,
) -> JSON:
    """Run a deterministic evaluation job and preserve its artifacts."""

    forge = WorldForge(state_dir=state_dir)
    report = EvaluationSuite.from_builtin(suite).run_report(providers, forge=forge)
    command = _command_string(
        [
            "eval",
            "--suite",
            suite,
            *_repeat_args("--provider", providers),
            "--workspace",
            str(workspace_dir),
        ]
    )
    workspace = preserve_eval_run_workspace(
        workspace_dir,
        suite_id=suite,
        providers=providers,
        artifacts=report.artifacts(),
        report=report,
        command=command,
    )
    manifest = _manifest_payload(workspace.manifest_path)
    return {
        "kind": "eval",
        "status": "passed",
        "exit_code": 0,
        "run_id": workspace.run_id,
        "run_workspace": str(workspace.path),
        "run_manifest": str(workspace.manifest_path),
        "report_paths": manifest["artifact_paths"],
        "summary": manifest["result_summary"],
    }


def run_benchmark_job(
    *,
    providers: list[str],
    operations: list[str] | None,
    iterations: int,
    concurrency: int,
    workspace_dir: Path,
    state_dir: Path,
    input_file: Path | None = None,
    budget_file: Path | None = None,
) -> JSON:
    """Run a benchmark job, preserve artifacts, and return a budget-aware summary."""

    forge = WorldForge(state_dir=state_dir)
    inputs = None
    input_metadata = None
    if input_file is not None:
        input_metadata, input_payload = _load_json_file(input_file, label="benchmark input file")
        inputs = load_benchmark_inputs(input_payload, base_path=input_file.expanduser().parent)

    report = ProviderBenchmarkHarness(forge=forge).run(
        providers,
        operations=operations,
        iterations=iterations,
        concurrency=concurrency,
        inputs=inputs,
    )
    if input_metadata is not None:
        report.run_metadata["input_file"] = input_metadata

    gate_report = None
    budget_metadata = None
    if budget_file is not None:
        budget_metadata, budget_payload = _load_json_file(
            budget_file,
            label="benchmark budget file",
        )
        report.run_metadata["budget_file"] = budget_metadata
        gate_report = report.evaluate_budgets(load_benchmark_budgets(budget_payload))

    command = _command_string(
        [
            "benchmark",
            *_repeat_args("--provider", providers),
            *_repeat_args("--operation", operations or []),
            "--iterations",
            str(iterations),
            "--concurrency",
            str(concurrency),
            "--workspace",
            str(workspace_dir),
        ]
    )
    workspace = preserve_benchmark_run_workspace(
        workspace_dir,
        providers=providers,
        operations=operations,
        artifacts=report.artifacts(),
        report=report,
        command=command,
        budget_passed=None if gate_report is None else gate_report.passed,
    )
    attached_inputs = _copy_input_artifacts(
        workspace.path,
        input_file=input_file,
        budget_file=budget_file,
    )
    if attached_inputs:
        _patch_manifest_artifacts(workspace.manifest_path, attached_inputs)
    manifest = _manifest_payload(workspace.manifest_path)
    budget_passed = None if gate_report is None else gate_report.passed
    status = "passed" if budget_passed is not False else "failed"
    return {
        "kind": "benchmark",
        "status": status,
        "exit_code": 0 if status == "passed" else 1,
        "run_id": workspace.run_id,
        "run_workspace": str(workspace.path),
        "run_manifest": str(workspace.manifest_path),
        "report_paths": manifest["artifact_paths"],
        "summary": manifest["result_summary"],
        "budget": None if gate_report is None else gate_report.to_dict(),
        "input_file": input_metadata,
        "budget_file": budget_metadata,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the batch host CLI parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Run WorldForge evaluation and benchmark jobs with preserved run-workspace artifacts."
        )
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="Workspace root that will receive runs/<run-id>/ artifacts.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="WorldForge state directory for temporary job worlds.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser("eval", help="Run a built-in evaluation suite.")
    eval_parser.add_argument(
        "--suite",
        choices=EvaluationSuite.builtin_names(),
        default="planning",
        help="Built-in evaluation suite.",
    )
    eval_parser.add_argument(
        "--provider",
        dest="providers",
        action="append",
        default=None,
        help="Provider name. Can be repeated.",
    )

    benchmark_parser = subparsers.add_parser("benchmark", help="Run provider benchmarks.")
    benchmark_parser.add_argument(
        "--provider",
        dest="providers",
        action="append",
        default=None,
        help="Provider name. Can be repeated.",
    )
    benchmark_parser.add_argument(
        "--operation",
        dest="operations",
        action="append",
        default=None,
        choices=ProviderBenchmarkHarness.benchmarkable_operations,
        help="Operation to benchmark. Can be repeated.",
    )
    benchmark_parser.add_argument("--iterations", type=int, default=2)
    benchmark_parser.add_argument("--concurrency", type=int, default=1)
    benchmark_parser.add_argument(
        "--input-file",
        type=Path,
        help="Optional deterministic benchmark input JSON file.",
    )
    benchmark_parser.add_argument(
        "--budget-file",
        type=Path,
        help="Optional benchmark budget JSON file. Failing gates exit non-zero.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the batch evaluation host CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "eval":
            result = run_eval_job(
                suite=args.suite,
                providers=args.providers or ["mock"],
                workspace_dir=args.workspace,
                state_dir=args.state_dir,
            )
        else:
            result = run_benchmark_job(
                providers=args.providers or ["mock"],
                operations=args.operations,
                iterations=args.iterations,
                concurrency=args.concurrency,
                workspace_dir=args.workspace,
                state_dir=args.state_dir,
                input_file=args.input_file,
                budget_file=args.budget_file,
            )
    except WorldForgeError as exc:
        print(json.dumps({"error": {"type": "validation_error", "message": str(exc)}}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(result["exit_code"])


def _repeat_args(flag: str, values: list[str]) -> list[str]:
    args: list[str] = []
    for value in values:
        args.extend([flag, value])
    return args


def _command_string(args: list[str]) -> str:
    return "python examples/hosts/batch-eval/app.py " + " ".join(args)


def _load_json_file(path: Path, *, label: str) -> tuple[JSON, object]:
    resolved = path.expanduser()
    try:
        text = resolved.read_text(encoding="utf-8")
        payload = json.loads(text)
    except OSError as exc:
        raise WorldForgeError(f"Failed to read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{label} must contain valid JSON: {exc}") from exc
    metadata = (
        payload.get("metadata")
        if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict)
        else {}
    )
    return (
        {
            "path": str(resolved.resolve()),
            "sha256": sha256(text.encode("utf-8")).hexdigest(),
            "metadata": metadata,
        },
        payload,
    )


def _copy_input_artifacts(
    run_workspace: Path,
    *,
    input_file: Path | None,
    budget_file: Path | None,
) -> dict[str, str]:
    copied: dict[str, str] = {}
    inputs_dir = run_workspace / "inputs"
    if input_file is not None:
        target = inputs_dir / "benchmark-inputs.json"
        shutil.copy2(input_file.expanduser(), target)
        copied["input_file"] = "inputs/benchmark-inputs.json"
    if budget_file is not None:
        target = inputs_dir / "benchmark-budget.json"
        shutil.copy2(budget_file.expanduser(), target)
        copied["budget_file"] = "inputs/benchmark-budget.json"
    return copied


def _patch_manifest_artifacts(manifest_path: Path, artifact_paths: dict[str, str]) -> None:
    manifest = _manifest_payload(manifest_path)
    paths = manifest.get("artifact_paths")
    if not isinstance(paths, dict):
        paths = {}
    paths.update(artifact_paths)
    manifest["artifact_paths"] = paths
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _manifest_payload(manifest_path: Path) -> JSON:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorldForgeError(f"run manifest at {manifest_path} must contain a JSON object.")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
