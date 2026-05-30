"""Run-workspace command execution for the WorldForge CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from worldforge.cli_support import _print_json
from worldforge.models import WorldForgeError, require_json_dict

if TYPE_CHECKING:
    from worldforge.runs_prune import RunsRetentionPolicy


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


def _write_rendered_output(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        rendered if rendered.endswith("\n") else rendered + "\n",
        encoding="utf-8",
    )


def _print_rendered_output(rendered: str) -> None:
    print(rendered, end="" if rendered.endswith("\n") else "\n")


def _cmd_runs_list(args: argparse.Namespace) -> int:
    from worldforge.harness.workspace import list_run_workspaces

    runs = list_run_workspaces(args.workspace_dir)
    if args.format == "markdown":
        _print_run_list_markdown(runs)
    else:
        _print_json(runs)
    return 0


def _cmd_runs_compare(args: argparse.Namespace) -> int:
    from worldforge.harness.report_compare import (
        compare_preserved_run_reports,
        comparison_artifact,
    )

    payload = compare_preserved_run_reports(args.paths, mode=args.mode)
    rendered = comparison_artifact(payload, output_format=args.format)
    if args.output is not None:
        _write_rendered_output(args.output, rendered)
        return 0
    print(rendered)
    return 0


def _cmd_runs_bundle(args: argparse.Namespace) -> int:
    from worldforge.evidence_bundle import generate_issue_bundle

    output_dir = args.output or args.workspace_dir / "issue-bundles" / args.run_id
    result = generate_issue_bundle(
        workspace_dir=args.workspace_dir,
        run_id=args.run_id,
        output_dir=output_dir,
        overwrite=args.overwrite,
    )
    if args.format == "json":
        _print_json(
            {
                "run_id": args.run_id,
                "output_dir": str(result.output_dir),
                "manifest_path": str(result.manifest_path),
                "summary_path": str(result.summary_path),
                "issue_template_path": str(result.issue_template_path),
                "safe_to_attach": result.manifest["safe_to_attach"],
                "included_count": result.manifest["included_count"],
                "excluded_count": result.manifest["excluded_count"],
                "first_triage_step": result.manifest["first_triage_step"],
            }
        )
    elif args.format == "html":
        issue_html_path = result.output_dir / "issue.html"
        if not issue_html_path.is_file():
            raise WorldForgeError("Issue bundle did not produce issue.html.")
        print(issue_html_path.read_text(encoding="utf-8"))
    else:
        if result.issue_template_path is None:
            raise WorldForgeError("Issue bundle did not produce issue.md.")
        print(result.issue_template_path.read_text(encoding="utf-8"))
    return 0


def _render_runs_index(args: argparse.Namespace) -> str:
    from worldforge.harness.run_history import RunHistoryFilter
    from worldforge.harness.run_index import build_run_index

    filters = RunHistoryFilter.from_strings(
        provider=args.provider,
        capability=args.capability,
        status=args.status,
        created_from=args.created_from,
        created_to=args.created_to,
        artifact_type=args.artifact_type,
    )
    index = build_run_index(args.workspace_dir, filters=filters)
    if args.format == "json":
        return index.to_json()
    if args.format == "csv":
        return index.to_csv()
    return index.to_markdown()


def _cmd_runs_index(args: argparse.Namespace) -> int:
    rendered = _render_runs_index(args)
    if args.output is not None:
        _write_rendered_output(args.output, rendered)
        return 0
    _print_rendered_output(rendered)
    return 0


def _runs_retention_profile(path: Path) -> RunsRetentionPolicy | None:
    from worldforge.runs_prune import parse_runs_retention

    try:
        profile_payload = require_json_dict(
            json.loads(path.expanduser().read_text(encoding="utf-8")),
            name=f"retention profile {path}",
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise WorldForgeError(f"Failed to read retention profile {path}: {exc}") from exc
    retention = profile_payload.get("runs_retention")
    if isinstance(retention, dict):
        return parse_runs_retention(retention)
    return None


def _runs_retention_policy_from_args(args: argparse.Namespace) -> RunsRetentionPolicy:
    from worldforge.runs_prune import RunsRetentionPolicy

    max_age_days = args.max_age_days
    keep_latest = args.keep_latest
    families = tuple(args.family or ())
    if args.retention_profile is not None:
        policy_from_profile = _runs_retention_profile(args.retention_profile)
        if policy_from_profile is not None:
            if max_age_days is None:
                max_age_days = policy_from_profile.max_age_days
            if keep_latest is None:
                keep_latest = policy_from_profile.keep_latest
            if not families and policy_from_profile.families:
                families = policy_from_profile.families
    return RunsRetentionPolicy(
        max_age_days=30 if max_age_days is None else max_age_days,
        keep_latest=10 if keep_latest is None else keep_latest,
        families=families,
    )


def _cmd_runs_prune(args: argparse.Namespace) -> int:
    from worldforge.runs_prune import apply_prune, plan_prune

    report = plan_prune(args.workspace_dir, policy=_runs_retention_policy_from_args(args))
    if args.apply:
        report = apply_prune(report)
    rendered = report.to_markdown() if args.format == "markdown" else report.to_json()
    _print_rendered_output(rendered)
    return 0


def _cmd_runs_cleanup(args: argparse.Namespace) -> int:
    from worldforge.harness.workspace import cleanup_run_workspaces

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


def _cmd_runs(args: argparse.Namespace) -> int:
    runs_dispatch: dict[str, Callable[[argparse.Namespace], int]] = {
        "list": _cmd_runs_list,
        "compare": _cmd_runs_compare,
        "bundle": _cmd_runs_bundle,
        "index": _cmd_runs_index,
        "prune": _cmd_runs_prune,
        "cleanup": _cmd_runs_cleanup,
    }
    handler = runs_dispatch.get(args.runs_command)
    if handler is None:
        return 2
    return handler(args)
