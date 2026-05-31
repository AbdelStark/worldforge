"""Workflow, evaluation, and benchmark parser construction."""

from __future__ import annotations

import argparse
from pathlib import Path

from worldforge.benchmark import ProviderBenchmarkHarness
from worldforge.cli_args.common import (
    Subparsers,
    _add_format_argument,
    _add_profile_argument,
    _add_provider_repeat_argument,
    _add_state_dir_argument,
    _add_xyz_arguments,
)
from worldforge.evaluation import EvaluationSuite


def _add_scenario_commands(subparsers: Subparsers) -> None:
    scenario = subparsers.add_parser(
        "scenario",
        help="Validate or run a JSON-native checkout-safe scenario file.",
    )
    scenario_subparsers = scenario.add_subparsers(
        dest="scenario_command",
        required=True,
        metavar="command",
    )
    _add_scenario_validate_command(scenario_subparsers)
    _add_scenario_run_command(scenario_subparsers)


def _add_scenario_validate_command(subparsers: Subparsers) -> None:
    scenario_validate = subparsers.add_parser(
        "validate",
        help="Load and validate a scenario JSON file without running it.",
    )
    scenario_validate.add_argument("path", type=Path, help="Scenario JSON file path.")
    _add_format_argument(
        scenario_validate,
        choices=("json", "markdown"),
        help_text="Output format for the validation report.",
    )


def _add_scenario_run_command(subparsers: Subparsers) -> None:
    scenario_run = subparsers.add_parser(
        "run",
        help="Validate and run a scenario file end-to-end with a checkout-safe provider.",
    )
    scenario_run.add_argument("path", type=Path, help="Scenario JSON file path.")
    _add_state_dir_argument(
        scenario_run,
        help_text="World state directory (the scenario world is created here).",
    )
    _add_format_argument(
        scenario_run,
        choices=("json", "markdown"),
        help_text="Output format for the scenario run result.",
    )
    scenario_run.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the rendered result instead of stdout.",
    )


def _add_negotiate_command(subparsers: Subparsers) -> None:
    negotiate = subparsers.add_parser(
        "negotiate",
        help="Report whether providers can satisfy a capability workflow before it runs.",
    )
    negotiate.add_argument(
        "--workflow",
        dest="workflow",
        default=None,
        help=(
            "Workflow name to negotiate. Repeat with --workflow each time, "
            "or omit to cover every workflow."
        ),
    )
    negotiate.add_argument(
        "--list",
        dest="list_workflows",
        action="store_true",
        help="List known workflows and exit.",
    )
    _add_format_argument(
        negotiate, choices=("markdown", "json"), default="markdown", help_text="Output format."
    )
    _add_state_dir_argument(negotiate)


def _add_predict_command(subparsers: Subparsers) -> None:
    predict = subparsers.add_parser("predict", help="Run a deterministic prediction.")
    predict.add_argument("world_name", help="World name to create or load.")
    predict.add_argument("--provider", default="mock", help="Provider name.")
    _add_xyz_arguments(predict, required=True, label="Target")
    predict.add_argument("--steps", type=int, default=1, help="Prediction horizon in steps.")
    _add_state_dir_argument(predict)


def _add_eval_command(subparsers: Subparsers) -> None:
    evaluate = subparsers.add_parser("eval", help="Run a built-in evaluation suite.")
    evaluate.add_argument(
        "--suite",
        default="physics",
        choices=EvaluationSuite.builtin_names(),
        help="Built-in evaluation suite.",
    )
    _add_provider_repeat_argument(evaluate, help_text="Provider name to evaluate. Can be repeated.")
    _add_profile_argument(evaluate)
    _add_format_argument(
        evaluate,
        choices=("markdown", "json", "csv", "html"),
        default="markdown",
        help_text="Evaluation report format.",
    )
    _add_state_dir_argument(evaluate)
    evaluate.add_argument(
        "--run-workspace",
        type=Path,
        help="Preserve sanitized eval artifacts under RUN_WORKSPACE/runs/<run-id>/.",
    )
    evaluate.add_argument(
        "--dataset-manifest",
        dest="dataset_manifests",
        action="append",
        type=Path,
        default=None,
        help="Dataset manifest JSON to cite in evaluation provenance. Can be repeated.",
    )


def _add_benchmark_command(subparsers: Subparsers) -> None:
    benchmark = subparsers.add_parser(
        "benchmark",
        help="Run provider latency and retry benchmarks.",
    )
    _add_provider_repeat_argument(
        benchmark, help_text="Provider name to benchmark. Can be repeated."
    )
    _add_profile_argument(benchmark)
    benchmark.add_argument(
        "--operation",
        dest="operations",
        action="append",
        default=None,
        choices=ProviderBenchmarkHarness.benchmarkable_operations,
        help="Operation to benchmark. Can be repeated.",
    )
    benchmark.add_argument("--iterations", type=int, default=5, help="Iterations per operation.")
    benchmark.add_argument("--concurrency", type=int, default=1, help="Concurrent workers.")
    _add_format_argument(
        benchmark,
        choices=("markdown", "json", "csv", "html"),
        default="markdown",
        help_text="Benchmark report format.",
    )
    _add_benchmark_artifact_arguments(benchmark)
    _add_benchmark_preset_arguments(benchmark)


def _add_benchmark_artifact_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input-file",
        type=Path,
        help="Optional JSON file with deterministic benchmark inputs.",
    )
    parser.add_argument(
        "--budget-file",
        type=Path,
        help="Optional JSON budget file. Failing gates exit non-zero after printing the report.",
    )
    _add_state_dir_argument(parser)
    parser.add_argument(
        "--run-workspace",
        type=Path,
        help="Preserve sanitized benchmark artifacts under RUN_WORKSPACE/runs/<run-id>/.",
    )


def _add_benchmark_preset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--preset",
        dest="preset",
        default=None,
        help=(
            "Run a named benchmark preset (overrides --provider, --operation, --iterations, "
            "--concurrency, --input-file, and --budget-file). Use --list-presets for the catalogue."
        ),
    )
    parser.add_argument(
        "--list-presets",
        dest="list_presets",
        action="store_true",
        help="List benchmark presets and exit.",
    )
    parser.add_argument(
        "--show-preset",
        dest="show_preset",
        default=None,
        help="Print one benchmark preset's details and exit.",
    )
