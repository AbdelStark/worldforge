"""Workflow, evaluation, benchmark, and harness parser construction."""

from __future__ import annotations

import argparse
from pathlib import Path

from worldforge.benchmark import ProviderBenchmarkHarness
from worldforge.cli_args.common import (
    DEFAULT_WORKSPACE_DIR,
    Subparsers,
    _add_format_argument,
    _add_generation_arguments,
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


def _add_media_commands(subparsers: Subparsers) -> None:
    generate = subparsers.add_parser("generate", help="Generate a clip with a provider.")
    generate.add_argument("prompt", help="Generation prompt.")
    generate.add_argument("--provider", default="mock", help="Provider name.")
    generate.add_argument("--duration", type=float, default=5.0, help="Clip duration in seconds.")
    generate.add_argument("--output", help="Optional path for the generated clip bytes.")
    _add_state_dir_argument(generate)
    _add_generation_arguments(generate)

    transfer = subparsers.add_parser("transfer", help="Transform an input clip with a provider.")
    transfer.add_argument("input", help="Input clip path.")
    transfer.add_argument("--provider", default="mock", help="Provider name.")
    transfer.add_argument("--prompt", default="", help="Transfer prompt.")
    transfer.add_argument("--width", type=int, default=1280, help="Input clip width.")
    transfer.add_argument("--height", type=int, default=720, help="Input clip height.")
    transfer.add_argument("--fps", type=float, default=24.0, help="Input clip frames per second.")
    transfer.add_argument("--duration", type=float, default=5.0, help="Input clip duration.")
    transfer.add_argument("--output", help="Optional path for the transformed clip bytes.")
    _add_state_dir_argument(transfer)
    _add_generation_arguments(transfer, include_fps=False)


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


def _add_harness_command(subparsers: Subparsers) -> None:
    harness = subparsers.add_parser("harness", help="Launch TheWorldHarness TUI.")
    harness.add_argument(
        "--flow",
        choices=(
            "leworldmodel",
            "lerobot",
            "cosmos-policy",
            "gr00t",
            "diagnostics",
            "workbench",
            "eval",
            "benchmark",
            "runs",
        ),
        default="leworldmodel",
        help="Harness flow to open.",
    )
    harness.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for persisted demo worlds. Defaults to a temporary directory.",
    )
    _add_harness_mode_arguments(harness)
    _add_harness_run_filters(harness)
    harness.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for --list, --connectors, and --runs.",
    )
    harness.add_argument("--no-animation", action="store_true", help="Disable step reveal delays.")


def _add_harness_mode_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available harness flows without launching the TUI.",
    )
    parser.add_argument(
        "--connectors",
        action="store_true",
        help="List provider connector readiness without launching the TUI.",
    )
    parser.add_argument(
        "--runs",
        action="store_true",
        help="List preserved run history without launching the TUI.",
    )
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=DEFAULT_WORKSPACE_DIR,
        help="Workspace root for --runs. Defaults to .worldforge.",
    )


def _add_harness_run_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", help="Filter --runs output by provider substring.")
    parser.add_argument("--capability", help="Filter --runs output by capability.")
    parser.add_argument("--status", help="Filter --runs output by run status.")
    parser.add_argument("--created-from", help="Filter --runs output from YYYY-MM-DD.")
    parser.add_argument("--created-to", help="Filter --runs output through YYYY-MM-DD.")
    parser.add_argument("--artifact-type", help="Filter --runs output by safe artifact type.")
