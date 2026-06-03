"""Persisted world command parser construction."""

from __future__ import annotations

from worldforge.cli_args.common import (
    Subparsers,
    _add_format_argument,
    _add_state_dir_argument,
    _add_xyz_arguments,
)


def _add_world_commands(subparsers: Subparsers) -> None:
    world = subparsers.add_parser("world", help="Manage persisted local JSON worlds.")
    world_subparsers = world.add_subparsers(
        dest="world_command",
        required=True,
        metavar="command",
    )
    _add_world_read_commands(world_subparsers)
    _add_world_create_command(world_subparsers)
    _add_world_object_commands(world_subparsers)
    _add_world_delete_command(world_subparsers)
    _add_world_predict_command(world_subparsers)
    _add_world_io_commands(world_subparsers)


def _add_world_read_commands(subparsers: Subparsers) -> None:
    world_list = subparsers.add_parser("list", help="List persisted worlds.")
    _add_state_dir_argument(world_list)
    _add_format_argument(
        world_list,
        choices=("json", "markdown"),
        help_text="Output format for persisted world summaries.",
    )

    world_show = subparsers.add_parser("show", help="Show a persisted world.")
    world_show.add_argument("world_id", help="World identifier.")
    _add_state_dir_argument(world_show)
    _add_format_argument(
        world_show, choices=("json", "markdown"), help_text="Output format for the world."
    )

    world_history = subparsers.add_parser("history", help="Show persisted world history.")
    world_history.add_argument("world_id", help="World identifier.")
    _add_state_dir_argument(world_history)
    _add_format_argument(
        world_history, choices=("json", "markdown"), help_text="Output format for history entries."
    )

    world_objects = subparsers.add_parser("objects", help="List objects in a world.")
    world_objects.add_argument("world_id", help="World identifier.")
    _add_state_dir_argument(world_objects)
    _add_format_argument(
        world_objects, choices=("json", "markdown"), help_text="Output format for scene objects."
    )


def _add_world_create_command(subparsers: Subparsers) -> None:
    world_create = subparsers.add_parser("create", help="Create and save a world.")
    world_create.add_argument("name", help="World name.")
    world_create.add_argument("--provider", default="mock", help="Provider name.")
    world_create.add_argument(
        "--prompt",
        help="Optional prompt used to seed the world with deterministic checkout-safe objects.",
    )
    world_create.add_argument("--description", default="", help="Optional world description.")
    _add_state_dir_argument(world_create)
    _add_format_argument(
        world_create,
        choices=("json", "markdown"),
        help_text="Output format for the saved world summary.",
    )


def _add_world_object_commands(subparsers: Subparsers) -> None:
    _add_world_add_object_command(subparsers)
    _add_world_update_object_command(subparsers)
    _add_world_remove_object_command(subparsers)


def _add_world_add_object_command(subparsers: Subparsers) -> None:
    world_add_object = subparsers.add_parser(
        "add-object",
        help="Add an object to a persisted world.",
    )
    world_add_object.add_argument("world_id", help="World identifier.")
    world_add_object.add_argument("name", help="Object name.")
    _add_xyz_arguments(world_add_object, required=True, label="Object")
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
    _add_state_dir_argument(world_add_object)
    _add_format_argument(
        world_add_object,
        choices=("json", "markdown"),
        help_text="Output format for the updated world summary.",
    )


def _add_world_update_object_command(subparsers: Subparsers) -> None:
    world_update_object = subparsers.add_parser(
        "update-object",
        help="Patch an object in a persisted world.",
    )
    world_update_object.add_argument("world_id", help="World identifier.")
    world_update_object.add_argument("object_id", help="Scene object identifier.")
    world_update_object.add_argument("--name", help="Replacement object name.")
    _add_xyz_arguments(world_update_object, required=False, label="Replacement")
    world_update_object.add_argument(
        "--graspable",
        choices=("true", "false"),
        help="Replacement graspable flag.",
    )
    _add_state_dir_argument(world_update_object)
    _add_format_argument(
        world_update_object,
        choices=("json", "markdown"),
        help_text="Output format for the updated object.",
    )


def _add_world_remove_object_command(subparsers: Subparsers) -> None:
    world_remove_object = subparsers.add_parser(
        "remove-object",
        help="Remove an object from a persisted world.",
    )
    world_remove_object.add_argument("world_id", help="World identifier.")
    world_remove_object.add_argument("object_id", help="Scene object identifier.")
    _add_state_dir_argument(world_remove_object)
    _add_format_argument(
        world_remove_object,
        choices=("json", "markdown"),
        help_text="Output format for the removed object.",
    )


def _add_world_delete_command(subparsers: Subparsers) -> None:
    world_delete = subparsers.add_parser("delete", help="Delete a persisted world.")
    world_delete.add_argument("world_id", help="World identifier.")
    _add_state_dir_argument(world_delete)
    _add_format_argument(
        world_delete,
        choices=("json", "markdown"),
        help_text="Output format for the deletion result.",
    )


def _add_world_predict_command(subparsers: Subparsers) -> None:
    world_predict = subparsers.add_parser(
        "predict",
        help="Predict and save the next state for a persisted world.",
    )
    world_predict.add_argument("world_id", help="World identifier.")
    world_predict.add_argument(
        "--provider", help="Provider name. Defaults to the world's provider."
    )
    _add_xyz_arguments(world_predict, required=True, label="Target")
    world_predict.add_argument("--speed", type=float, default=1.0, help="Action speed.")
    world_predict.add_argument("--object-id", help="Optional object id to move.")
    world_predict.add_argument("--steps", type=int, default=1, help="Prediction horizon in steps.")
    world_predict.add_argument(
        "--dry-run",
        action="store_true",
        help="Run prediction without saving the updated world.",
    )
    _add_state_dir_argument(world_predict)
    _add_format_argument(
        world_predict,
        choices=("json", "markdown"),
        help_text="Output format for the prediction result.",
    )


def _add_world_io_commands(subparsers: Subparsers) -> None:
    _add_world_export_command(subparsers)
    _add_world_import_command(subparsers)
    _add_world_fork_command(subparsers)


def _add_world_export_command(subparsers: Subparsers) -> None:
    world_export = subparsers.add_parser("export", help="Export a persisted world as JSON.")
    world_export.add_argument("world_id", help="World identifier.")
    world_export.add_argument("--output", help="Optional output path for exported JSON.")
    _add_state_dir_argument(world_export)


def _add_world_import_command(subparsers: Subparsers) -> None:
    world_import = subparsers.add_parser(
        "import",
        help="Import and save exported world JSON.",
    )
    world_import.add_argument("input", help="Path to exported world JSON.")
    world_import.add_argument("--new-id", action="store_true", help="Assign a fresh world id.")
    world_import.add_argument("--name", help="Optional replacement world name.")
    _add_state_dir_argument(world_import)
    _add_format_argument(
        world_import,
        choices=("json", "markdown"),
        help_text="Output format for the imported world summary.",
    )


def _add_world_fork_command(subparsers: Subparsers) -> None:
    world_fork = subparsers.add_parser("fork", help="Fork a world from a history entry.")
    world_fork.add_argument("world_id", help="Source world identifier.")
    world_fork.add_argument(
        "--history-index",
        type=int,
        default=0,
        help="History entry index to fork from.",
    )
    world_fork.add_argument("--name", help="Optional forked world name.")
    _add_state_dir_argument(world_fork)
    _add_format_argument(
        world_fork,
        choices=("json", "markdown"),
        help_text="Output format for the forked world summary.",
    )
