"""CLI for WorldForge provider and evaluation workflows."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

from worldforge import (
    Action,
    GenerationOptions,
    VideoClip,
    WorldForge,
    WorldForgeError,
)
from worldforge.cli_benchmark import _cmd_benchmark
from worldforge.cli_parser import PROFILE_FORMAT_CHOICES as _PROFILE_FORMAT_CHOICES
from worldforge.cli_parser import build_parser as _build_cli_parser
from worldforge.cli_provider import (
    _cmd_provider,
    _cmd_provider_docs,
    _cmd_provider_workbench,
    _cmd_providers,
)
from worldforge.cli_runs import _cmd_runs
from worldforge.cli_scenario import _cmd_scenario
from worldforge.cli_support import (
    _command_string,
    _config_profile_provenance,
    _print_json,
    _profile_command_args,
    _provider_args,
)
from worldforge.cli_world import _cmd_world, _cmd_world_preflight_or_migration
from worldforge.config_profiles import ConfigProfile, load_config_profile
from worldforge.evaluation import EvaluationSuite
from worldforge.models import _redact_observable_text
from worldforge.providers import ProviderError

_HOST_LOCAL_PATH_PATTERN = re.compile(
    r"(?P<path>(?:/Users|/private|/var/folders|/tmp)/[^\s,;:)'\"]+)"
)
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
        "task": "Robot decision traces",
        "name": "so101-replay-trace",
        "surface": "score provider, decision trace, counterfactuals, mock replay",
        "requires": "base WorldForge package; deterministic SO-101-shaped replay fixture",
        "command": "uv run worldforge-demo-so101-replay-trace",
        "description": (
            "Score SO-101 pick-and-place candidate actions, select the best replay action, "
            "and emit a reusable robot decision trace without LeRobot, torch, DimOS, or hardware."
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
        "task": "Batch evaluation host",
        "name": "batch-eval-host",
        "surface": "evaluation, benchmarking, run workspaces, budget gates",
        "requires": "base WorldForge package; checkout examples directory",
        "command": "uv run python examples/hosts/batch-eval/app.py benchmark --provider mock",
        "description": (
            "Run mock provider eval or benchmark jobs as a production-shaped batch process with "
            "preserved run manifests, report exports, and non-zero budget-gate failures."
        ),
    },
    {
        "task": "Robotics operator host",
        "name": "robotics-operator-host",
        "surface": "offline policy+score review, dry-run approval, replay artifacts",
        "requires": "base WorldForge package; checkout examples directory",
        "command": (
            "uv run python examples/hosts/robotics-operator/app.py review --sample-translator"
        ),
        "description": (
            "Run a non-mutating robotics operator review that preserves selected action chunks, "
            "score rationale, provider events, dry-run approval, and replay artifacts."
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
    return _build_cli_parser()


def _cmd_examples(args: argparse.Namespace) -> int:
    if args.format == "json":
        _print_json(EXAMPLE_COMMANDS)
    else:
        _print_examples_markdown()
    return 0


def _cmd_harness(args: argparse.Namespace) -> int:
    from worldforge.harness.cli import run_from_args

    return run_from_args(
        flow_id=args.flow,
        state_dir=args.state_dir,
        list_only=args.list,
        connectors=args.connectors,
        runs=args.runs,
        workspace_dir=args.workspace_dir,
        provider=args.provider,
        capability=args.capability,
        status=args.status,
        created_from=args.created_from,
        created_to=args.created_to,
        artifact_type=args.artifact_type,
        output_format=args.format,
        animate=not args.no_animation,
    )


def _cmd_drills(args: argparse.Namespace) -> int:
    from worldforge.operator_drills import (
        list_operator_drills,
        render_operator_drill_result_markdown,
        render_operator_drills_markdown,
        run_all_operator_drills,
        run_operator_drill,
    )

    if args.drills_command == "list":
        drills = list_operator_drills()
        if args.format == "json":
            _print_json(drills)
        else:
            print(render_operator_drills_markdown(drills))
        return 0

    if args.drills_command == "run":
        if args.drill == "all":
            result = run_all_operator_drills(
                workspace_dir=args.workspace_dir,
                bundle=args.bundle,
            )
        else:
            result = run_operator_drill(
                args.drill,
                workspace_dir=args.workspace_dir,
                bundle=args.bundle,
            )
        if args.format == "markdown":
            print(render_operator_drill_result_markdown(result))
        else:
            _print_json(result)
        return 0 if result["status"] == "passed" else 1

    return 2


def _cmd_doctor(args: argparse.Namespace, forge: WorldForge) -> int:
    _print_json(
        forge.doctor(
            capability=args.capability,
            registered_only=args.registered_only,
        ).to_dict()
    )
    return 0


def _cmd_negotiate(args: argparse.Namespace, forge: WorldForge) -> int:
    from worldforge.capability_negotiation import (
        get_workflow,
        list_workflows,
    )
    from worldforge.capability_negotiation import (
        negotiate as run_negotiation,
    )

    if args.list_workflows:
        workflows = list_workflows()
        if args.format == "json":
            _print_json({"workflows": [workflow.to_dict() for workflow in workflows]})
        else:
            lines = ["# Known Workflows", ""]
            for workflow in workflows:
                lines.extend(
                    [
                        f"- **{workflow.name}** — {workflow.title}",
                        f"  required: {', '.join(workflow.required_capabilities)}",
                        f"  {workflow.description}",
                    ]
                )
            print("\n".join(lines))
        return 0

    workflows = (get_workflow(args.workflow),) if args.workflow else None
    report = run_negotiation(workflows=workflows, forge=forge)
    if args.format == "json":
        _print_json(report.to_dict())
    else:
        print(report.to_markdown())
    return 0 if all(negotiation.ready for negotiation in report.workflows) else 1


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


def _explicit_cli_options(argv: list[str]) -> set[str]:
    options: set[str] = set()
    for item in argv:
        if item == "--":
            break
        if item.startswith("--"):
            options.add(item.split("=", maxsplit=1)[0])
    return options


def _profile_command_key(args: argparse.Namespace) -> tuple[str, ...]:
    command = str(getattr(args, "command", ""))
    if command == "runs":
        return (command, str(getattr(args, "runs_command", "")))
    if command == "world":
        return (command, str(getattr(args, "world_command", "")))
    return (command,)


def _apply_cli_profile(args: argparse.Namespace, argv: list[str]) -> None:
    profile_path = getattr(args, "profile", None)
    if profile_path is None:
        args.config_profile = None
        return
    profile = load_config_profile(profile_path)
    explicit = _explicit_cli_options(argv)
    _apply_profile_providers(args, profile, explicit)
    _apply_profile_operations(args, profile, explicit)
    _apply_profile_format(args, profile, explicit)
    _apply_profile_run_workspace(args, profile, explicit)
    _apply_profile_state_dir(args, profile, explicit)
    args.config_profile = profile


def _profile_option_available(
    args: argparse.Namespace,
    *,
    attr: str,
    option: str,
    explicit: set[str],
) -> bool:
    return hasattr(args, attr) and option not in explicit


def _apply_profile_providers(
    args: argparse.Namespace,
    profile: ConfigProfile,
    explicit: set[str],
) -> None:
    if (
        _profile_option_available(args, attr="providers", option="--provider", explicit=explicit)
        and profile.providers
    ):
        args.providers = list(profile.providers)


def _apply_profile_operations(
    args: argparse.Namespace,
    profile: ConfigProfile,
    explicit: set[str],
) -> None:
    if getattr(args, "command", None) != "benchmark":
        return
    if (
        _profile_option_available(args, attr="operations", option="--operation", explicit=explicit)
        and profile.operations
    ):
        args.operations = list(profile.operations)


def _apply_profile_format(
    args: argparse.Namespace,
    profile: ConfigProfile,
    explicit: set[str],
) -> None:
    if not _profile_option_available(args, attr="format", option="--format", explicit=explicit):
        return
    if not profile.output_format:
        return
    _validate_profile_output_format(args, profile.output_format)
    args.format = profile.output_format


def _validate_profile_output_format(args: argparse.Namespace, output_format: str) -> None:
    allowed_formats = _PROFILE_FORMAT_CHOICES.get(_profile_command_key(args), set())
    if output_format not in allowed_formats:
        raise WorldForgeError(
            f"Configuration profile output_format '{output_format}' is not "
            f"supported by `{_cli_command_path(args)}`."
        )


def _apply_profile_run_workspace(
    args: argparse.Namespace,
    profile: ConfigProfile,
    explicit: set[str],
) -> None:
    if not _profile_option_available(
        args,
        attr="run_workspace",
        option="--run-workspace",
        explicit=explicit,
    ):
        return
    workspace = profile.run_workspace or profile.workspace_dir
    if workspace is not None:
        args.run_workspace = Path(workspace)


def _apply_profile_state_dir(
    args: argparse.Namespace,
    profile: ConfigProfile,
    explicit: set[str],
) -> None:
    if (
        _profile_option_available(args, attr="state_dir", option="--state-dir", explicit=explicit)
        and profile.state_dir
    ):
        args.state_dir = profile.state_dir


def _cmd_eval(args: argparse.Namespace, forge: WorldForge) -> int:
    suite = EvaluationSuite.from_builtin(args.suite)
    providers = args.providers or ["mock"]
    report = suite.run_report(
        providers,
        forge=forge,
        dataset_manifests=args.dataset_manifests,
    )
    eval_command = _command_string(
        ["eval", "--suite", args.suite, *_provider_args(providers), *_profile_command_args(args)]
    )
    for manifest_path in args.dataset_manifests or ():
        eval_command += f" --dataset-manifest {manifest_path}"
    if report.provenance is not None:
        report.provenance = report.provenance.with_overrides(
            command=tuple(eval_command.split()),
        )
    artifacts = report.artifacts()
    if args.run_workspace is not None:
        from worldforge.harness.flows import preserve_eval_run_workspace

        preserve_eval_run_workspace(
            args.run_workspace,
            suite_id=args.suite,
            providers=providers,
            artifacts=artifacts,
            report=report,
            command=eval_command,
            config_profile=_config_profile_provenance(args),
        )
    if args.format == "json":
        print(artifacts["json"])
    elif args.format == "csv":
        print(artifacts["csv"])
    elif args.format == "html":
        print(artifacts["html"])
    else:
        print(artifacts["markdown"])
    return 0


_ForgeHandler = Callable[[argparse.Namespace, WorldForge], "int | None"]

_FORGE_COMMANDS: dict[str, _ForgeHandler] = {
    "providers": _cmd_providers,
    "provider": _cmd_provider,
    "world": _cmd_world,
    "doctor": _cmd_doctor,
    "negotiate": _cmd_negotiate,
    "generate": _cmd_generate,
    "transfer": _cmd_transfer,
    "predict": _cmd_predict,
    "eval": _cmd_eval,
    "benchmark": _cmd_benchmark,
}


_ArgHandler = Callable[[argparse.Namespace], int]
_ParserArgHandler = Callable[[argparse.Namespace, argparse.ArgumentParser], int]
_SpecialCommandHandler = Callable[[argparse.ArgumentParser, argparse.Namespace], int]
_SpecialCommandKey = tuple[str | None, str | None]
_CLI_LOCAL_ERRORS = (WorldForgeError, ValueError)
_CLI_PROVIDER_ERRORS = (ProviderError, WorldForgeError, ValueError)
_WORLD_TRIAGE_STEPS = {
    "preflight": "run `uv run worldforge world preflight --workspace-dir .worldforge`.",
    "migration-preview": (
        "run `uv run worldforge world migration-preview <world-id> --state-dir "
        ".worldforge/worlds --format json`."
    ),
}
_WORLD_DEFAULT_TRIAGE_STEP = (
    "run `uv run worldforge world list --state-dir <state-dir>` and retry with a listed world id."
)
_PROVIDER_TRIAGE_STEP = (
    "run `uv run worldforge doctor` and `uv run worldforge provider health <provider>`."
)
_COMMAND_TRIAGE_STEPS_BEFORE_PROVIDER = {
    "scenario": "run `uv run worldforge scenario validate <scenario.json>` before `scenario run`.",
    "benchmark": (
        "validate benchmark input/budget JSON, then run `uv run worldforge benchmark --help`."
    ),
}
_COMMAND_TRIAGE_STEPS_AFTER_PROVIDER = {
    "runs": (
        "inspect the run manifest and rerun `uv run worldforge runs --help` for bundle "
        "or cleanup syntax."
    ),
    "drills": (
        "run `uv run worldforge drills list` and rerun the named drill with `--format json`."
    ),
}


def _exit_with_public_cli_error(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    exc: Exception,
) -> None:
    parser.exit(2, _format_public_cli_error(args, exc) + "\n")


def _run_arg_handler(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    handler: _ArgHandler,
    error_types: tuple[type[Exception], ...],
) -> int:
    try:
        return handler(args)
    except error_types as exc:
        _exit_with_public_cli_error(parser, args, exc)
    raise AssertionError("parser.exit returned unexpectedly")


def _plain_special_handler(handler: _ArgHandler) -> _SpecialCommandHandler:
    def run(_parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
        return handler(args)

    return run


def _parser_special_handler(handler: _ParserArgHandler) -> _SpecialCommandHandler:
    def run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
        return handler(args, parser)

    return run


def _checked_special_handler(
    handler: _ArgHandler,
    error_types: tuple[type[Exception], ...],
) -> _SpecialCommandHandler:
    def run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
        return _run_arg_handler(parser, args, handler, error_types)

    return run


_WORLD_PREFLIGHT_OR_MIGRATION_SPECIAL = _checked_special_handler(
    _cmd_world_preflight_or_migration,
    _CLI_LOCAL_ERRORS,
)


_SPECIAL_SUBCOMMAND_FIELDS = {
    "provider": "provider_command",
    "world": "world_command",
}
_SPECIAL_COMMAND_HANDLERS: dict[_SpecialCommandKey, _SpecialCommandHandler] = {
    ("examples", None): _plain_special_handler(_cmd_examples),
    ("provider", "docs"): _parser_special_handler(_cmd_provider_docs),
    ("provider", "workbench"): _checked_special_handler(
        _cmd_provider_workbench,
        _CLI_PROVIDER_ERRORS,
    ),
    ("harness", None): _plain_special_handler(_cmd_harness),
    ("runs", None): _checked_special_handler(_cmd_runs, _CLI_LOCAL_ERRORS),
    ("drills", None): _checked_special_handler(_cmd_drills, _CLI_LOCAL_ERRORS),
    ("scenario", None): _checked_special_handler(_cmd_scenario, _CLI_PROVIDER_ERRORS),
    ("world", "preflight"): _WORLD_PREFLIGHT_OR_MIGRATION_SPECIAL,
    ("world", "migration-preview"): _WORLD_PREFLIGHT_OR_MIGRATION_SPECIAL,
}


def _namespace_string(args: argparse.Namespace, field_name: str) -> str | None:
    value = getattr(args, field_name, None)
    return value if isinstance(value, str) else None


def _special_command_key(args: argparse.Namespace) -> _SpecialCommandKey:
    command = _namespace_string(args, "command")
    subcommand_field = _SPECIAL_SUBCOMMAND_FIELDS.get(command)
    if subcommand_field is None:
        return command, None
    return command, _namespace_string(args, subcommand_field)


def _dispatch_special_command(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> int | None:
    handler = _SPECIAL_COMMAND_HANDLERS.get(_special_command_key(args))
    if handler is None:
        return None
    return handler(parser, args)


def _dispatch_forge_command(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    forge: WorldForge,
) -> int | None:
    handler = _FORGE_COMMANDS.get(args.command)
    if handler is None:
        return None
    try:
        return handler(args, forge)
    except _CLI_PROVIDER_ERRORS as exc:
        _exit_with_public_cli_error(parser, args, exc)
    raise AssertionError("parser.exit returned unexpectedly")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        _apply_cli_profile(args, sys.argv[1:])
    except _CLI_LOCAL_ERRORS as exc:
        _exit_with_public_cli_error(parser, args, exc)

    result = _dispatch_special_command(parser, args)
    if result is not None:
        return result

    forge = WorldForge(state_dir=args.state_dir)
    result = _dispatch_forge_command(parser, args, forge)
    if result is not None:
        return result

    parser.error(f"Unknown command: {args.command}")
    return 2


def _format_public_cli_error(args: argparse.Namespace, exc: Exception) -> str:
    command_path = _cli_command_path(args)
    message = _safe_cli_error_text(str(exc))
    return (
        f"WorldForge CLI error [{command_path}]: {message}\n"
        f"First triage: {_first_triage_step(args, message)}"
    )


def _cli_command_path(args: argparse.Namespace) -> str:
    parts = [str(getattr(args, "command", "") or "unknown")]
    for field_name in (
        "provider_command",
        "world_command",
        "scenario_command",
        "runs_command",
        "drill_command",
    ):
        value = getattr(args, field_name, None)
        if isinstance(value, str) and value:
            parts.append(value)
    return " ".join(parts)


def _safe_cli_error_text(message: str) -> str:
    redacted = _redact_observable_text(message)
    return _HOST_LOCAL_PATH_PATTERN.sub("<host-local-path>", redacted)


def _first_triage_step(args: argparse.Namespace, message: str) -> str:
    command = getattr(args, "command", None)
    if command == "world":
        return _world_triage_step(args)
    triage_step = _COMMAND_TRIAGE_STEPS_BEFORE_PROVIDER.get(command)
    if triage_step is not None:
        return triage_step
    if _needs_provider_triage(command, message):
        return _PROVIDER_TRIAGE_STEP
    return _COMMAND_TRIAGE_STEPS_AFTER_PROVIDER.get(command, _default_triage_step(command))


def _world_triage_step(args: argparse.Namespace) -> str:
    return _WORLD_TRIAGE_STEPS.get(
        getattr(args, "world_command", None),
        _WORLD_DEFAULT_TRIAGE_STEP,
    )


def _needs_provider_triage(command: object, message: str) -> bool:
    return command == "provider" or "provider" in message.lower()


def _default_triage_step(command: object) -> str:
    return f"run `uv run worldforge {command or '<command>'} --help`."


if __name__ == "__main__":
    raise SystemExit(main())
