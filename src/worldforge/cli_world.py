"""World command execution for the WorldForge CLI."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable
from pathlib import Path

from worldforge import (
    Action,
    BBox,
    Position,
    SceneObject,
    SceneObjectPatch,
    WorldForge,
    WorldForgeError,
)
from worldforge.cli_support import _print_json


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


def _cmd_world_preflight(args: argparse.Namespace) -> int:
    from worldforge.persistence_preflight import (
        preflight_local_state,
        render_state_preflight_markdown,
    )

    report = preflight_local_state(
        state_dir=args.state_dir,
        workspace_dir=args.workspace_dir,
        world_ids=tuple(args.world_ids or ()),
        retention_keep=args.retention_keep,
    )
    if args.format == "markdown":
        print(render_state_preflight_markdown(report))
    else:
        _print_json(report)
    return 1 if report["status"] == "failed" else 0


def _cmd_world_migration_preview(args: argparse.Namespace) -> int:
    from worldforge.world_migration_preview import (
        preview_world_migration_from_path,
        preview_world_migration_from_world_id,
        render_world_migration_preview_markdown,
    )

    if args.source_path:
        report = preview_world_migration_from_path(Path(args.source))
    else:
        report = preview_world_migration_from_world_id(args.source, state_dir=args.state_dir)
    if args.format == "markdown":
        print(render_world_migration_preview_markdown(report), end="")
    else:
        _print_json(report)
    return 0 if report["can_apply_safely"] else 1


def _cmd_world_preflight_or_migration(args: argparse.Namespace) -> int:
    if args.world_command == "preflight":
        return _cmd_world_preflight(args)
    return _cmd_world_migration_preview(args)


def _cmd_world_diff(args: argparse.Namespace, forge: WorldForge) -> int:
    from worldforge.world_diff import diff_worlds, diff_worlds_from_paths

    if args.source_path or args.target_path:
        if not (args.source_path and args.target_path):
            raise WorldForgeError(
                "world diff requires --source-path and --target-path together "
                "when comparing exported JSON files."
            )
        diff = diff_worlds_from_paths(args.source, args.target)
    else:
        source_world = forge.load_world(args.source)
        target_world = forge.load_world(args.target)
        diff = diff_worlds(
            source_world.to_dict(),
            target_world.to_dict(),
            source_label=args.source,
            target_label=args.target,
        )
    if args.format == "markdown":
        print(diff.to_markdown(), end="")
    else:
        print(diff.to_json(), end="")
    return 0


def _cmd_world(args: argparse.Namespace, forge: WorldForge) -> int | None:
    world_dispatch: dict[str, Callable[[argparse.Namespace, WorldForge], int]] = {
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
        "diff": _cmd_world_diff,
    }
    handler = world_dispatch.get(args.world_command)
    if handler is None:
        return None
    return handler(args, forge)
