"""CLI for WorldForge provider and evaluation workflows."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from worldforge import (
    Action,
    BBox,
    GenerationOptions,
    Position,
    SceneObject,
    SceneObjectPatch,
    VideoClip,
    WorldForge,
    WorldForgeError,
)
from worldforge.benchmark import (
    ProviderBenchmarkHarness,
    load_benchmark_budgets,
    load_benchmark_inputs,
)
from worldforge.evaluation import EvaluationSuite
from worldforge.models import CAPABILITY_NAMES
from worldforge.providers import ProviderError
from worldforge.providers.catalog import provider_docs_index

CLI_DESCRIPTION = (
    "CLI for WorldForge provider diagnostics, prediction, generation, evaluation, "
    "benchmarking, and runnable demos."
)

CLI_EPILOG = """Common commands:
  worldforge examples
  worldforge doctor
  worldforge world create lab --provider mock
  worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0
  worldforge world predict <world-id> --object-id <object-id> --x 0.4 --y 0.5 --z 0
  worldforge world list
  worldforge world objects <world-id>
  worldforge world history <world-id>
  worldforge world delete <world-id>
  worldforge provider list
  worldforge provider docs
  worldforge provider info mock
  worldforge harness --list
  worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
  worldforge eval --suite planning --provider mock --format json
  worldforge benchmark --provider mock --iterations 5 --format json
  worldforge runs list
"""

EXAMPLE_COMMANDS: tuple[dict[str, str], ...] = (
    {
        "task": "Prediction and evaluation",
        "name": "basic-prediction",
        "surface": "predict, planning, evaluation",
        "requires": "base WorldForge package",
        "command": "uv run python examples/basic_prediction.py",
        "description": (
            "Create a mock world, run a deterministic prediction, plan an object move, and "
            "print a physics evaluation report."
        ),
    },
    {
        "task": "Provider comparison",
        "name": "cross-provider-compare",
        "surface": "provider registry, comparison",
        "requires": "base WorldForge package",
        "command": "uv run python examples/cross_provider_compare.py",
        "description": (
            "Register a second deterministic provider and compare prediction outputs across "
            "provider surfaces."
        ),
    },
    {
        "task": "Score planning",
        "name": "leworldmodel-score-planning",
        "surface": "score provider, planning, persistence",
        "requires": "base WorldForge package; injected deterministic score runtime",
        "command": "uv run worldforge-demo-leworldmodel",
        "description": (
            "Run the packaged LeWorldModel provider-surface demo without downloading "
            "upstream checkpoints."
        ),
    },
    {
        "task": "Policy plus score planning",
        "name": "lerobot-policy-score-planning",
        "surface": "policy provider, score provider, planning, persistence",
        "requires": "base WorldForge package; injected deterministic policy runtime",
        "command": "uv run worldforge-demo-lerobot",
        "description": (
            "Run the packaged LeRobot policy-plus-score planning demo without installing "
            "LeRobot or torch."
        ),
    },
    {
        "task": "Visual harness",
        "name": "theworldharness",
        "surface": "E2E flows, provider diagnostics, benchmark comparison",
        "requires": "Textual through the harness extra",
        "command": "uv run --extra harness worldforge-harness",
        "description": (
            "Open the optional Textual harness for running packaged E2E demos, diagnostics, "
            "and benchmark comparisons as visible provider workflows."
        ),
    },
    {
        "task": "Optional runtime smoke",
        "name": "leworldmodel-real-checkpoint-smoke",
        "surface": "optional runtime smoke",
        "requires": "host-owned stable-worldmodel, torch, datasets, and LeWM checkpoint assets",
        "command": (
            "scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu"
        ),
        "description": (
            "Exercise the real LeWorldModel checkpoint path from a host environment that owns "
            "the optional runtime and assets; prints visual pipeline, tensor, latency, event, "
            "and candidate-cost output."
        ),
    },
    {
        "task": "Real robotics showcase",
        "name": "lerobot-leworldmodel-real-robotics",
        "surface": "policy provider, score provider, planning, mock execution",
        "requires": (
            "host-owned LeRobot, stable-worldmodel, torch, datasets, policy checkpoint, "
            "LeWM checkpoint, and PushT simulation dependencies"
        ),
        "command": "scripts/robotics-showcase",
        "description": (
            "Compose real LeRobot policy inference with real LeWorldModel checkpoint scoring "
            "through a packaged PushT bridge and WorldForge policy-plus-score planning; opens "
            "a staged Textual visual report by default."
        ),
    },
)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def _world_summary(world) -> dict[str, object]:
    return {
        "id": world.id,
        "name": world.name,
        "provider": world.provider,
        "description": world.description,
        "step": world.step,
        "object_count": world.object_count,
        "history_length": world.history_length,
    }


def _object_summary(obj: SceneObject) -> dict[str, object]:
    return {
        "id": obj.id,
        "name": obj.name,
        "position": obj.position.to_dict(),
        "bbox": obj.bbox.to_dict(),
        "is_graspable": obj.is_graspable,
        "metadata": dict(obj.metadata),
    }


def _position_from_args(args: argparse.Namespace) -> Position:
    return Position(args.x, args.y, args.z)


def _optional_position_from_args(args: argparse.Namespace) -> Position | None:
    coordinates = (args.x, args.y, args.z)
    if all(value is None for value in coordinates):
        return None
    if any(value is None for value in coordinates):
        raise WorldForgeError("Position updates require --x, --y, and --z together.")
    return Position(args.x, args.y, args.z)


def _bbox_around(position: Position, size: float) -> BBox:
    if not math.isfinite(size) or size <= 0.0:
        raise WorldForgeError("--size must be a finite number greater than 0.")
    half = size / 2.0
    return BBox(
        Position(position.x - half, position.y - half, position.z - half),
        Position(position.x + half, position.y + half, position.z + half),
    )


def _parse_json_object(value: str, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{label} must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorldForgeError(f"{label} must decode to a JSON object.")
    return payload


def _parse_bool(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise WorldForgeError("Boolean values must be 'true' or 'false'.")


def _provider_args(providers: list[str]) -> list[str]:
    args: list[str] = []
    for provider in providers:
        args.extend(["--provider", provider])
    return args


def _operation_args(operations: list[str]) -> list[str]:
    args: list[str] = []
    for operation in operations:
        args.extend(["--operation", operation])
    return args


def _command_string(args: list[str]) -> str:
    return "worldforge " + " ".join(args)


def _world_history_payload(world) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for entry in world.history():
        action = json.loads(entry.action_json) if entry.action_json is not None else None
        entries.append(
            {
                "step": entry.step,
                "summary": entry.summary,
                "action": action,
                "object_count": len(entry.state.get("scene", {}).get("objects", {})),
            }
        )
    return entries


def _print_world_list_markdown(worlds: list[dict[str, object]]) -> None:
    print("# WorldForge Worlds")
    print()
    print("| id | name | provider | step | objects | history |")
    print("| --- | --- | --- | ---: | ---: | ---: |")
    for world in worlds:
        print(
            "| "
            f"`{world['id']}` | "
            f"{world['name']} | "
            f"`{world['provider']}` | "
            f"{world['step']} | "
            f"{world['object_count']} | "
            f"{world['history_length']} |"
        )


def _print_world_summary_markdown(world) -> None:
    print(f"# World {world.id}")
    print()
    print(f"- name: {world.name}")
    print(f"- provider: {world.provider}")
    print(f"- step: {world.step}")
    print(f"- objects: {world.object_count}")
    print(f"- history: {world.history_length}")
    if world.description:
        print(f"- description: {world.description}")


def _print_world_objects_markdown(world, objects: list[dict[str, object]]) -> None:
    print(f"# World Objects: {world.id}")
    print()
    print("| id | name | x | y | z | graspable |")
    print("| --- | --- | ---: | ---: | ---: | --- |")
    for obj in objects:
        position = obj["position"]
        if not isinstance(position, dict):
            raise WorldForgeError("World object position must be a JSON object.")
        print(
            "| "
            f"`{obj['id']}` | "
            f"{obj['name']} | "
            f"{float(position['x']):.3f} | "
            f"{float(position['y']):.3f} | "
            f"{float(position['z']):.3f} | "
            f"{obj['is_graspable']} |"
        )


def _print_world_prediction_markdown(payload: dict[str, object]) -> None:
    print(f"# World Prediction: {payload['world_id']}")
    print()
    print(f"- provider: {payload['provider']}")
    print(f"- saved: {payload['saved']}")
    print(f"- physics_score: {float(payload['physics_score']):.4f}")
    print(f"- confidence: {float(payload['confidence']):.4f}")
    print(f"- step: {payload['world']['step']}")
    print(f"- objects: {payload['world']['object_count']}")


def _print_world_delete_markdown(payload: dict[str, object]) -> None:
    print(f"# Deleted World: {payload['world_id']}")
    print()
    print(f"- state_dir: {payload['state_dir']}")
    print("- deleted: true")


def _print_world_history_markdown(world, entries: list[dict[str, object]]) -> None:
    print(f"# World History: {world.id}")
    print()
    print("| step | summary | action | objects |")
    print("| ---: | --- | --- | ---: |")
    for entry in entries:
        action = entry["action"]
        action_label = ""
        if isinstance(action, dict):
            action_label = str(action.get("type", ""))
        print(
            f"| {entry['step']} | {entry['summary']} | {action_label} | {entry['object_count']} |"
        )


def _print_examples_markdown() -> None:
    print("# WorldForge Examples")
    current_task = ""
    for example in EXAMPLE_COMMANDS:
        if example["task"] != current_task:
            current_task = example["task"]
            print()
            print(f"## {current_task}")
            print()
            print("| Example | Surface | Requirements | Command |")
            print("| --- | --- | --- | --- |")
        print(
            "| "
            f"`{example['name']}` | "
            f"{example['surface']} | "
            f"{example['requires']} | "
            f"`{example['command']}` |"
        )


def _print_run_list_markdown(runs: tuple[dict[str, object], ...]) -> None:
    print("# WorldForge Runs")
    print()
    print("| run_id | kind | status | provider | operation | path |")
    print("| --- | --- | --- | --- | --- | --- |")
    for run in runs:
        print(
            "| "
            f"`{run.get('run_id', '')}` | "
            f"{run.get('kind', '')} | "
            f"{run.get('status', '')} | "
            f"{run.get('provider', '')} | "
            f"{run.get('operation', '')} | "
            f"`{run.get('path', '')}` |"
        )


def _print_run_cleanup_markdown(paths: tuple[Path, ...], *, dry_run: bool) -> None:
    title = "WorldForge Run Cleanup Preview" if dry_run else "WorldForge Run Cleanup"
    print(f"# {title}")
    print()
    print(f"- removed_count: {0 if dry_run else len(paths)}")
    print(f"- selected_count: {len(paths)}")
    for path in paths:
        print(f"- `{path}`")


def _provider_docs_entries(name: str | None = None) -> tuple[dict[str, str], ...]:
    entries = provider_docs_index()
    if name is None:
        return entries
    return tuple(entry for entry in entries if entry["name"] == name)


def _print_provider_docs_markdown(entries: tuple[dict[str, str], ...]) -> None:
    print("# WorldForge Provider Docs")
    print()
    print("| Provider | Capability surface | Registration | Docs |")
    print("| --- | --- | --- | --- |")
    for entry in entries:
        print(
            "| "
            f"`{entry['name']}` | "
            f"{entry['capabilities']} | "
            f"{entry['registration']} | "
            f"`{entry['docs_path']}` |"
        )


def _add_generation_arguments(parser: argparse.ArgumentParser, *, include_fps: bool = True) -> None:
    parser.add_argument("--image", help="Input image path, URL, or provider-native reference.")
    parser.add_argument("--video", help="Input video path, URL, or provider-native reference.")
    parser.add_argument("--model", help="Provider model identifier.")
    parser.add_argument("--ratio", help="Provider aspect-ratio option.")
    parser.add_argument("--size", help="Provider resolution or size option.")
    if include_fps:
        parser.add_argument("--fps", type=float, help="Requested frames per second.")
    parser.add_argument("--seed", type=int, help="Provider seed when supported.")
    parser.add_argument("--negative-prompt", help="Negative prompt when supported.")
    parser.add_argument(
        "--reference-image",
        action="append",
        default=[],
        help="Reference image path, URL, or data URI. Can be repeated.",
    )


def _build_generation_options(args: argparse.Namespace) -> GenerationOptions:
    return GenerationOptions(
        image=getattr(args, "image", None),
        video=getattr(args, "video", None),
        model=getattr(args, "model", None),
        ratio=getattr(args, "ratio", None),
        size=getattr(args, "size", None),
        fps=getattr(args, "fps", None),
        seed=getattr(args, "seed", None),
        negative_prompt=getattr(args, "negative_prompt", None),
        reference_images=list(getattr(args, "reference_image", [])),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldforge",
        description=CLI_DESCRIPTION,
        epilog=CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    examples = subparsers.add_parser(
        "examples",
        help="List runnable examples grouped by task.",
    )
    examples.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for the examples index.",
    )

    providers = subparsers.add_parser("providers", help="List registered providers.")
    providers.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )

    provider = subparsers.add_parser("provider", help="Inspect provider profiles and health.")
    provider_subparsers = provider.add_subparsers(dest="provider_command", required=True)

    provider_list = provider_subparsers.add_parser("list", help="List provider profiles.")
    provider_list.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    provider_list.add_argument(
        "--registered-only",
        action="store_true",
        help="Show only providers registered for this process.",
    )
    provider_list.add_argument(
        "--capability",
        choices=CAPABILITY_NAMES,
        help="Filter providers by capability name.",
    )

    provider_info = provider_subparsers.add_parser("info", help="Show provider details.")
    provider_info.add_argument("name", help="Provider name.")
    provider_info.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )

    provider_health = provider_subparsers.add_parser("health", help="Show provider health.")
    provider_health.add_argument("name", nargs="?", help="Optional provider name.")
    provider_health.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    provider_health.add_argument(
        "--registered-only",
        action="store_true",
        help="Show only providers registered for this process.",
    )
    provider_health.add_argument(
        "--capability",
        choices=CAPABILITY_NAMES,
        help="Filter providers by capability name.",
    )

    provider_docs = provider_subparsers.add_parser(
        "docs",
        help="List provider documentation paths.",
    )
    provider_docs.add_argument("name", nargs="?", help="Optional provider name.")
    provider_docs.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for provider docs metadata.",
    )

    world = subparsers.add_parser("world", help="Manage persisted local JSON worlds.")
    world_subparsers = world.add_subparsers(
        dest="world_command",
        required=True,
        metavar="command",
    )

    world_list = world_subparsers.add_parser("list", help="List persisted worlds.")
    world_list.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_list.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for persisted world summaries.",
    )

    world_create = world_subparsers.add_parser("create", help="Create and save a world.")
    world_create.add_argument("name", help="World name.")
    world_create.add_argument("--provider", default="mock", help="Provider name.")
    world_create.add_argument(
        "--prompt",
        help="Optional prompt used to seed the world with deterministic checkout-safe objects.",
    )
    world_create.add_argument("--description", default="", help="Optional world description.")
    world_create.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_create.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the saved world summary.",
    )

    world_show = world_subparsers.add_parser("show", help="Show a persisted world.")
    world_show.add_argument("world_id", help="World identifier.")
    world_show.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_show.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the world.",
    )

    world_history = world_subparsers.add_parser("history", help="Show persisted world history.")
    world_history.add_argument("world_id", help="World identifier.")
    world_history.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_history.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for history entries.",
    )

    world_objects = world_subparsers.add_parser("objects", help="List objects in a world.")
    world_objects.add_argument("world_id", help="World identifier.")
    world_objects.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_objects.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for scene objects.",
    )

    world_add_object = world_subparsers.add_parser(
        "add-object",
        help="Add an object to a persisted world.",
    )
    world_add_object.add_argument("world_id", help="World identifier.")
    world_add_object.add_argument("name", help="Object name.")
    world_add_object.add_argument("--x", type=float, required=True, help="Object x coordinate.")
    world_add_object.add_argument("--y", type=float, required=True, help="Object y coordinate.")
    world_add_object.add_argument("--z", type=float, required=True, help="Object z coordinate.")
    world_add_object.add_argument(
        "--size",
        type=float,
        default=0.1,
        help="Centered bounding-box edge length.",
    )
    world_add_object.add_argument("--object-id", help="Optional object identifier.")
    world_add_object.add_argument(
        "--graspable",
        action="store_true",
        help="Mark the object as graspable.",
    )
    world_add_object.add_argument(
        "--metadata",
        help="Optional JSON object stored on the scene object.",
    )
    world_add_object.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_add_object.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the updated world summary.",
    )

    world_update_object = world_subparsers.add_parser(
        "update-object",
        help="Patch an object in a persisted world.",
    )
    world_update_object.add_argument("world_id", help="World identifier.")
    world_update_object.add_argument("object_id", help="Scene object identifier.")
    world_update_object.add_argument("--name", help="Replacement object name.")
    world_update_object.add_argument("--x", type=float, help="Replacement x coordinate.")
    world_update_object.add_argument("--y", type=float, help="Replacement y coordinate.")
    world_update_object.add_argument("--z", type=float, help="Replacement z coordinate.")
    world_update_object.add_argument(
        "--graspable",
        choices=("true", "false"),
        help="Replacement graspable flag.",
    )
    world_update_object.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_update_object.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the updated object.",
    )

    world_remove_object = world_subparsers.add_parser(
        "remove-object",
        help="Remove an object from a persisted world.",
    )
    world_remove_object.add_argument("world_id", help="World identifier.")
    world_remove_object.add_argument("object_id", help="Scene object identifier.")
    world_remove_object.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_remove_object.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the removed object.",
    )

    world_delete = world_subparsers.add_parser("delete", help="Delete a persisted world.")
    world_delete.add_argument("world_id", help="World identifier.")
    world_delete.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_delete.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the deletion result.",
    )

    world_predict = world_subparsers.add_parser(
        "predict",
        help="Predict and save the next state for a persisted world.",
    )
    world_predict.add_argument("world_id", help="World identifier.")
    world_predict.add_argument(
        "--provider",
        help="Provider name. Defaults to the world's provider.",
    )
    world_predict.add_argument("--x", type=float, required=True, help="Target x coordinate.")
    world_predict.add_argument("--y", type=float, required=True, help="Target y coordinate.")
    world_predict.add_argument("--z", type=float, required=True, help="Target z coordinate.")
    world_predict.add_argument("--speed", type=float, default=1.0, help="Action speed.")
    world_predict.add_argument("--object-id", help="Optional object id to move.")
    world_predict.add_argument("--steps", type=int, default=1, help="Prediction horizon in steps.")
    world_predict.add_argument(
        "--dry-run",
        action="store_true",
        help="Run prediction without saving the updated world.",
    )
    world_predict.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_predict.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the prediction result.",
    )

    world_export = world_subparsers.add_parser("export", help="Export a persisted world as JSON.")
    world_export.add_argument("world_id", help="World identifier.")
    world_export.add_argument("--output", help="Optional output path for exported JSON.")
    world_export.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )

    world_import = world_subparsers.add_parser(
        "import", help="Import and save exported world JSON."
    )
    world_import.add_argument("input", help="Path to exported world JSON.")
    world_import.add_argument("--new-id", action="store_true", help="Assign a fresh world id.")
    world_import.add_argument("--name", help="Optional replacement world name.")
    world_import.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_import.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the imported world summary.",
    )

    world_fork = world_subparsers.add_parser("fork", help="Fork a world from a history entry.")
    world_fork.add_argument("world_id", help="Source world identifier.")
    world_fork.add_argument(
        "--history-index",
        type=int,
        default=0,
        help="History entry index to fork from.",
    )
    world_fork.add_argument("--name", help="Optional forked world name.")
    world_fork.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    world_fork.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the forked world summary.",
    )

    runs = subparsers.add_parser("runs", help="List and clean preserved run workspaces.")
    runs_subparsers = runs.add_subparsers(dest="runs_command", required=True, metavar="command")
    runs_list = runs_subparsers.add_parser("list", help="List preserved run manifests.")
    runs_list.add_argument(
        "--workspace-dir",
        type=Path,
        default=Path(".worldforge"),
        help="WorldForge workspace directory containing runs/.",
    )
    runs_list.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for run summaries.",
    )
    runs_compare = runs_subparsers.add_parser(
        "compare",
        help="Compare preserved eval or benchmark run reports.",
    )
    runs_compare.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Run workspace directories, run_manifest.json files, or report JSON files.",
    )
    runs_compare.add_argument(
        "--format",
        choices=("json", "markdown", "csv"),
        default="markdown",
        help="Output format for the comparison summary.",
    )
    runs_compare.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the comparison artifact instead of stdout.",
    )
    runs_cleanup = runs_subparsers.add_parser("cleanup", help="Remove old preserved runs.")
    runs_cleanup.add_argument(
        "--workspace-dir",
        type=Path,
        default=Path(".worldforge"),
        help="WorldForge workspace directory containing runs/.",
    )
    runs_cleanup.add_argument(
        "--keep",
        type=int,
        default=10,
        help="Number of newest runs to keep.",
    )
    runs_cleanup.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selected run directories without deleting them.",
    )
    runs_cleanup.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for cleanup results.",
    )

    doctor = subparsers.add_parser("doctor", help="Inspect the local WorldForge environment.")
    doctor.add_argument("--state-dir", default=".worldforge/worlds", help="World state directory.")
    doctor.add_argument(
        "--registered-only",
        action="store_true",
        help="Show only providers registered for this process.",
    )
    doctor.add_argument(
        "--capability",
        choices=CAPABILITY_NAMES,
        help="Filter providers by capability name.",
    )

    generate = subparsers.add_parser("generate", help="Generate a clip with a provider.")
    generate.add_argument("prompt", help="Generation prompt.")
    generate.add_argument("--provider", default="mock", help="Provider name.")
    generate.add_argument("--duration", type=float, default=5.0, help="Clip duration in seconds.")
    generate.add_argument("--output", help="Optional path for the generated clip bytes.")
    generate.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
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
    transfer.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    _add_generation_arguments(transfer, include_fps=False)

    predict = subparsers.add_parser("predict", help="Run a deterministic prediction.")
    predict.add_argument("world_name", help="World name to create or load.")
    predict.add_argument("--provider", default="mock", help="Provider name.")
    predict.add_argument("--x", type=float, required=True, help="Target x coordinate.")
    predict.add_argument("--y", type=float, required=True, help="Target y coordinate.")
    predict.add_argument("--z", type=float, required=True, help="Target z coordinate.")
    predict.add_argument("--steps", type=int, default=1, help="Prediction horizon in steps.")
    predict.add_argument("--state-dir", default=".worldforge/worlds", help="World state directory.")

    evaluate = subparsers.add_parser("eval", help="Run a built-in evaluation suite.")
    evaluate.add_argument(
        "--suite",
        default="physics",
        choices=EvaluationSuite.builtin_names(),
        help="Built-in evaluation suite.",
    )
    evaluate.add_argument(
        "--provider",
        dest="providers",
        action="append",
        default=None,
        help="Provider name to evaluate. Can be repeated.",
    )
    evaluate.add_argument(
        "--format",
        choices=("markdown", "json", "csv"),
        default="markdown",
        help="Evaluation report format.",
    )
    evaluate.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    evaluate.add_argument(
        "--run-workspace",
        type=Path,
        help="Preserve sanitized eval artifacts under RUN_WORKSPACE/runs/<run-id>/.",
    )

    benchmark = subparsers.add_parser(
        "benchmark",
        help="Run provider latency and retry benchmarks.",
    )
    benchmark.add_argument(
        "--provider",
        dest="providers",
        action="append",
        default=None,
        help="Provider name to benchmark. Can be repeated.",
    )
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
    benchmark.add_argument(
        "--format",
        choices=("markdown", "json", "csv"),
        default="markdown",
        help="Benchmark report format.",
    )
    benchmark.add_argument(
        "--input-file",
        type=Path,
        help="Optional JSON file with deterministic benchmark inputs.",
    )
    benchmark.add_argument(
        "--budget-file",
        type=Path,
        help=("Optional JSON budget file. Failing gates exit non-zero after printing the report."),
    )
    benchmark.add_argument(
        "--state-dir", default=".worldforge/worlds", help="World state directory."
    )
    benchmark.add_argument(
        "--run-workspace",
        type=Path,
        help="Preserve sanitized benchmark artifacts under RUN_WORKSPACE/runs/<run-id>/.",
    )

    harness = subparsers.add_parser("harness", help="Launch TheWorldHarness TUI.")
    harness.add_argument(
        "--flow",
        choices=("leworldmodel", "lerobot", "diagnostics"),
        default="leworldmodel",
        help="Harness flow to open.",
    )
    harness.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for persisted demo worlds. Defaults to a temporary directory.",
    )
    harness.add_argument(
        "--list",
        action="store_true",
        help="List available harness flows without launching the TUI.",
    )
    harness.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for --list.",
    )
    harness.add_argument("--no-animation", action="store_true", help="Disable step reveal delays.")

    return parser


def _cmd_examples(args: argparse.Namespace) -> int:
    if args.format == "json":
        _print_json(EXAMPLE_COMMANDS)
    else:
        _print_examples_markdown()
    return 0


def _cmd_provider_docs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    entries = _provider_docs_entries(args.name)
    if not entries:
        parser.exit(2, f"Unknown provider: {args.name}\n")
    if args.format == "json":
        _print_json(entries)
    else:
        _print_provider_docs_markdown(entries)
    return 0


def _cmd_harness(args: argparse.Namespace) -> int:
    from worldforge.harness.cli import run_from_args

    return run_from_args(
        flow_id=args.flow,
        state_dir=args.state_dir,
        list_only=args.list,
        output_format=args.format,
        animate=not args.no_animation,
    )


def _cmd_runs(args: argparse.Namespace) -> int:
    from worldforge.harness.workspace import cleanup_run_workspaces, list_run_workspaces

    if args.runs_command == "list":
        runs = list_run_workspaces(args.workspace_dir)
        if args.format == "markdown":
            _print_run_list_markdown(runs)
        else:
            _print_json(runs)
        return 0

    if args.runs_command == "compare":
        from worldforge.harness.report_compare import (
            compare_preserved_run_reports,
            comparison_artifact,
        )

        payload = compare_preserved_run_reports(args.paths)
        rendered = comparison_artifact(payload, output_format=args.format)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                rendered + ("\n" if not rendered.endswith("\n") else ""),
                encoding="utf-8",
            )
            return 0
        print(rendered)
        return 0

    if args.runs_command == "cleanup":
        removed = cleanup_run_workspaces(
            args.workspace_dir,
            keep=args.keep,
            dry_run=args.dry_run,
        )
        if args.format == "markdown":
            _print_run_cleanup_markdown(removed, dry_run=args.dry_run)
        else:
            _print_json(
                {
                    "dry_run": args.dry_run,
                    "selected_count": len(removed),
                    "removed_count": 0 if args.dry_run else len(removed),
                    "paths": [str(path) for path in removed],
                }
            )
        return 0

    return 2


def _cmd_providers(args: argparse.Namespace, forge: WorldForge) -> int:
    _print_json([info.to_dict() for info in forge.list_providers()])
    return 0


def _cmd_provider_list(args: argparse.Namespace, forge: WorldForge) -> int:
    report = forge.doctor(
        capability=args.capability,
        registered_only=args.registered_only,
    )
    _print_json([provider.to_dict() for provider in report.providers])
    return 0


def _cmd_provider_info(args: argparse.Namespace, forge: WorldForge) -> int:
    name = args.name
    payload = {
        "registered": name in forge.providers(),
        "profile": forge.provider_profile(name).to_dict(),
        "health": forge.provider_health(name).to_dict(),
        "config_summary": forge.provider_config_summary(name).to_dict(),
    }
    if name in forge.providers():
        payload["info"] = forge.provider_info(name).to_dict()
    _print_json(payload)
    return 0


def _cmd_provider_health(args: argparse.Namespace, forge: WorldForge) -> int:
    if args.name:
        _print_json(forge.provider_health(args.name).to_dict())
        return 0
    report = forge.doctor(
        capability=args.capability,
        registered_only=args.registered_only,
    )
    _print_json(
        [
            {
                **provider.health.to_dict(),
                "registered": provider.registered,
            }
            for provider in report.providers
        ]
    )
    return 0


def _cmd_provider(args: argparse.Namespace, forge: WorldForge) -> int | None:
    provider_dispatch = {
        "list": _cmd_provider_list,
        "info": _cmd_provider_info,
        "health": _cmd_provider_health,
    }
    handler = provider_dispatch.get(args.provider_command)
    if handler is None:
        return None
    return handler(args, forge)


def _cmd_world_list(args: argparse.Namespace, forge: WorldForge) -> int:
    worlds = [_world_summary(forge.load_world(world_id)) for world_id in forge.list_worlds()]
    if args.format == "markdown":
        _print_world_list_markdown(worlds)
    else:
        _print_json(worlds)
    return 0


def _cmd_world_create(args: argparse.Namespace, forge: WorldForge) -> int:
    if args.prompt:
        world = forge.create_world_from_prompt(args.prompt, provider=args.provider, name=args.name)
        if args.description:
            world.description = args.description
    else:
        world = forge.create_world(args.name, provider=args.provider, description=args.description)
    forge.save_world(world)
    if args.format == "markdown":
        _print_world_summary_markdown(world)
    else:
        _print_json(_world_summary(world))
    return 0


def _cmd_world_show(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.load_world(args.world_id)
    if args.format == "markdown":
        _print_world_summary_markdown(world)
    else:
        _print_json(world.to_dict())
    return 0


def _cmd_world_history(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.load_world(args.world_id)
    entries = _world_history_payload(world)
    if args.format == "markdown":
        _print_world_history_markdown(world, entries)
    else:
        _print_json({"world_id": world.id, "history": entries})
    return 0


def _cmd_world_objects(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.load_world(args.world_id)
    objects = [_object_summary(obj) for obj in world.objects()]
    if args.format == "markdown":
        _print_world_objects_markdown(world, objects)
    else:
        _print_json({"world_id": world.id, "objects": objects})
    return 0


def _cmd_world_add_object(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.load_world(args.world_id)
    position = _position_from_args(args)
    metadata = _parse_json_object(args.metadata, label="--metadata") if args.metadata else {}
    object_kwargs = {"id": args.object_id} if args.object_id else {}
    obj = SceneObject(
        args.name,
        position,
        _bbox_around(position, args.size),
        is_graspable=args.graspable,
        metadata=metadata,
        **object_kwargs,
    )
    added = world.add_object(obj)
    forge.save_world(world)
    payload = {
        "world": _world_summary(world),
        "object": _object_summary(added),
    }
    if args.format == "markdown":
        _print_world_summary_markdown(world)
        print()
        _print_world_objects_markdown(world, [_object_summary(added)])
    else:
        _print_json(payload)
    return 0


def _cmd_world_update_object(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.load_world(args.world_id)
    patch = SceneObjectPatch()
    has_update = False
    if args.name is not None:
        patch.set_name(args.name)
        has_update = True
    position = _optional_position_from_args(args)
    if position is not None:
        patch.set_position(position)
        has_update = True
    if args.graspable is not None:
        patch.set_graspable(_parse_bool(args.graspable))
        has_update = True
    if not has_update:
        raise WorldForgeError(
            "update-object requires at least one of --name, --x/--y/--z, or --graspable."
        )
    updated = world.update_object_patch(args.object_id, patch)
    forge.save_world(world)
    payload = {
        "world": _world_summary(world),
        "object": _object_summary(updated),
    }
    if args.format == "markdown":
        _print_world_objects_markdown(world, [_object_summary(updated)])
    else:
        _print_json(payload)
    return 0


def _cmd_world_remove_object(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.load_world(args.world_id)
    removed = world.remove_object_by_id(args.object_id)
    if removed is None:
        raise WorldForgeError(f"Object '{args.object_id}' is not present in world '{world.id}'.")
    forge.save_world(world)
    payload = {
        "world": _world_summary(world),
        "removed_object": _object_summary(removed),
    }
    if args.format == "markdown":
        _print_world_summary_markdown(world)
        print()
        _print_world_objects_markdown(world, [_object_summary(removed)])
    else:
        _print_json(payload)
    return 0


def _cmd_world_delete(args: argparse.Namespace, forge: WorldForge) -> int:
    deleted_id = forge.delete_world(args.world_id)
    payload = {
        "world_id": deleted_id,
        "deleted": True,
        "state_dir": str(forge.state_dir),
    }
    if args.format == "markdown":
        _print_world_delete_markdown(payload)
    else:
        _print_json(payload)
    return 0


def _cmd_world_predict(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.load_world(args.world_id)
    action = Action.move_to(
        args.x,
        args.y,
        args.z,
        speed=args.speed,
        object_id=args.object_id,
    )
    prediction = world.predict(action, steps=args.steps, provider=args.provider)
    if not args.dry_run:
        forge.save_world(world)
    payload = {
        "world_id": world.id,
        "saved": not args.dry_run,
        "provider": prediction.provider,
        "physics_score": prediction.physics_score,
        "confidence": prediction.confidence,
        "metadata": prediction.metadata,
        "world": _world_summary(world),
        "world_state": prediction.world_state,
    }
    if args.format == "markdown":
        _print_world_prediction_markdown(payload)
    else:
        _print_json(payload)
    return 0


def _cmd_world_export(args: argparse.Namespace, forge: WorldForge) -> int:
    payload = forge.export_world(args.world_id)
    if args.output:
        target = Path(args.output).expanduser().resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{payload}\n", encoding="utf-8")
        except OSError as exc:
            raise WorldForgeError(f"Failed to write exported world to {target}: {exc}") from exc
        _print_json({"world_id": args.world_id, "output_path": str(target)})
    else:
        _print_json(json.loads(payload))
    return 0


def _cmd_world_import(args: argparse.Namespace, forge: WorldForge) -> int:
    source = Path(args.input).expanduser().resolve()
    try:
        payload = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorldForgeError(f"Failed to read imported world from {source}: {exc}") from exc
    world = forge.import_world(payload, new_id=args.new_id, name=args.name)
    forge.save_world(world)
    if args.format == "markdown":
        _print_world_summary_markdown(world)
    else:
        summary = _world_summary(world)
        summary["source_path"] = str(source)
        _print_json(summary)
    return 0


def _cmd_world_fork(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.fork_world(
        args.world_id,
        history_index=args.history_index,
        name=args.name,
    )
    forge.save_world(world)
    if args.format == "markdown":
        _print_world_summary_markdown(world)
    else:
        summary = _world_summary(world)
        summary["source_world_id"] = args.world_id
        summary["history_index"] = args.history_index
        _print_json(summary)
    return 0


def _cmd_world(args: argparse.Namespace, forge: WorldForge) -> int | None:
    world_dispatch = {
        "list": _cmd_world_list,
        "create": _cmd_world_create,
        "show": _cmd_world_show,
        "history": _cmd_world_history,
        "objects": _cmd_world_objects,
        "add-object": _cmd_world_add_object,
        "update-object": _cmd_world_update_object,
        "remove-object": _cmd_world_remove_object,
        "delete": _cmd_world_delete,
        "predict": _cmd_world_predict,
        "export": _cmd_world_export,
        "import": _cmd_world_import,
        "fork": _cmd_world_fork,
    }
    handler = world_dispatch.get(args.world_command)
    if handler is None:
        return None
    return handler(args, forge)


def _cmd_doctor(args: argparse.Namespace, forge: WorldForge) -> int:
    _print_json(
        forge.doctor(
            capability=args.capability,
            registered_only=args.registered_only,
        ).to_dict()
    )
    return 0


def _cmd_generate(args: argparse.Namespace, forge: WorldForge) -> int:
    options = _build_generation_options(args)
    clip = forge.generate(
        args.prompt,
        args.provider,
        duration_seconds=args.duration,
        options=options,
    )
    payload = clip.to_dict()
    if args.output:
        payload["output_path"] = str(clip.save(Path(args.output)))
    _print_json(payload)
    return 0


def _cmd_transfer(args: argparse.Namespace, forge: WorldForge) -> int:
    options = _build_generation_options(args)
    input_clip = VideoClip.from_file(
        args.input,
        fps=args.fps,
        resolution=(args.width, args.height),
        duration_seconds=args.duration,
    )
    clip = forge.transfer(
        input_clip,
        args.provider,
        width=args.width,
        height=args.height,
        fps=args.fps,
        prompt=args.prompt,
        options=options,
    )
    payload = clip.to_dict()
    if args.output:
        payload["output_path"] = str(clip.save(Path(args.output)))
    _print_json(payload)
    return 0


def _cmd_predict(args: argparse.Namespace, forge: WorldForge) -> int:
    world = forge.create_world(args.world_name, args.provider)
    prediction = world.predict(Action.move_to(args.x, args.y, args.z), steps=args.steps)
    _print_json(
        {
            "provider": prediction.provider,
            "physics_score": prediction.physics_score,
            "confidence": prediction.confidence,
            "world_state": prediction.world_state,
        }
    )
    return 0


def _cmd_eval(args: argparse.Namespace, forge: WorldForge) -> int:
    suite = EvaluationSuite.from_builtin(args.suite)
    providers = args.providers or ["mock"]
    report = suite.run_report(providers, forge=forge)
    artifacts = report.artifacts()
    if args.run_workspace is not None:
        from worldforge.harness.flows import preserve_eval_run_workspace

        preserve_eval_run_workspace(
            args.run_workspace,
            suite_id=args.suite,
            providers=providers,
            artifacts=artifacts,
            report=report,
            command=_command_string(["eval", "--suite", args.suite, *_provider_args(providers)]),
        )
    if args.format == "json":
        print(artifacts["json"])
    elif args.format == "csv":
        print(artifacts["csv"])
    else:
        print(artifacts["markdown"])
    return 0


def _cmd_benchmark(args: argparse.Namespace, forge: WorldForge) -> int:
    harness = ProviderBenchmarkHarness(forge=forge)
    providers = args.providers or ["mock"]
    benchmark_inputs = None
    input_file_metadata = None
    if args.input_file:
        input_path = args.input_file.expanduser()
        try:
            input_text = input_path.read_text(encoding="utf-8")
            input_payload = json.loads(input_text)
        except OSError as exc:
            raise WorldForgeError(
                f"Failed to read benchmark input file {args.input_file}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise WorldForgeError(f"Benchmark input file must contain valid JSON: {exc}") from exc
        benchmark_inputs = load_benchmark_inputs(
            input_payload,
            base_path=input_path.parent,
        )
        input_metadata = (
            input_payload.get("metadata")
            if isinstance(input_payload, dict) and isinstance(input_payload.get("metadata"), dict)
            else {}
        )
        input_file_metadata = {
            "path": str(input_path.resolve()),
            "sha256": sha256(input_text.encode("utf-8")).hexdigest(),
            "metadata": input_metadata,
        }
    report = harness.run(
        providers,
        operations=args.operations,
        iterations=args.iterations,
        concurrency=args.concurrency,
        inputs=benchmark_inputs,
    )
    if input_file_metadata is not None:
        report.run_metadata["input_file"] = input_file_metadata
    gate_report = None
    if args.budget_file:
        budget_path = args.budget_file.expanduser()
        try:
            budget_text = budget_path.read_text(encoding="utf-8")
            budget_payload = json.loads(budget_text)
        except OSError as exc:
            raise WorldForgeError(
                f"Failed to read benchmark budget file {args.budget_file}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise WorldForgeError(f"Benchmark budget file must contain valid JSON: {exc}") from exc
        budget_metadata = (
            budget_payload.get("metadata")
            if isinstance(budget_payload, dict) and isinstance(budget_payload.get("metadata"), dict)
            else {}
        )
        report.run_metadata["budget_file"] = {
            "path": str(budget_path.resolve()),
            "sha256": sha256(budget_text.encode("utf-8")).hexdigest(),
            "metadata": budget_metadata,
        }
        gate_report = report.evaluate_budgets(load_benchmark_budgets(budget_payload))

    if args.run_workspace is not None:
        from worldforge.harness.flows import preserve_benchmark_run_workspace

        preserve_benchmark_run_workspace(
            args.run_workspace,
            providers=providers,
            operations=args.operations,
            artifacts=report.artifacts(),
            report=report,
            command=_command_string(
                [
                    "benchmark",
                    *_provider_args(providers),
                    *_operation_args(args.operations or []),
                    "--iterations",
                    str(args.iterations),
                    "--concurrency",
                    str(args.concurrency),
                ]
            ),
            budget_passed=None if gate_report is None else gate_report.passed,
        )

    if args.format == "json":
        if gate_report is None:
            print(report.to_json())
        else:
            print(
                json.dumps(
                    {
                        "benchmark": report.to_dict(),
                        "gate": gate_report.to_dict(),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
    elif args.format == "csv":
        print(gate_report.to_csv() if gate_report is not None else report.to_csv())
    else:
        if gate_report is None:
            print(report.to_markdown())
        else:
            print(report.to_markdown())
            print()
            print(gate_report.to_markdown())
    return 0 if gate_report is None or gate_report.passed else 1


_ForgeHandler = Callable[[argparse.Namespace, WorldForge], "int | None"]

_FORGE_COMMANDS: dict[str, _ForgeHandler] = {
    "providers": _cmd_providers,
    "provider": _cmd_provider,
    "world": _cmd_world,
    "doctor": _cmd_doctor,
    "generate": _cmd_generate,
    "transfer": _cmd_transfer,
    "predict": _cmd_predict,
    "eval": _cmd_eval,
    "benchmark": _cmd_benchmark,
}


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "examples":
        return _cmd_examples(args)

    if args.command == "provider" and args.provider_command == "docs":
        return _cmd_provider_docs(args, parser)

    if args.command == "harness":
        return _cmd_harness(args)

    if args.command == "runs":
        try:
            return _cmd_runs(args)
        except (WorldForgeError, ValueError) as exc:
            parser.exit(2, f"{exc}\n")

    forge = WorldForge(state_dir=args.state_dir)

    handler = _FORGE_COMMANDS.get(args.command)
    if handler is not None:
        try:
            result = handler(args, forge)
        except (ProviderError, WorldForgeError, ValueError) as exc:
            parser.exit(2, f"{exc}\n")
        if result is not None:
            return result

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
