"""Checkout-safe evidence bundle export for preserved WorldForge runs."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from worldforge import evidence_bundle_files as _bundle_files
from worldforge import evidence_bundle_rendering as _bundle_rendering
from worldforge.artifact_io import write_json_artifact
from worldforge.models import JSONDict, WorldForgeError, dump_json

_first_triage_step = _bundle_rendering._first_triage_step
evidence_bundle_artifact = _bundle_rendering.evidence_bundle_artifact
issue_bundle_artifact = _bundle_rendering.issue_bundle_artifact
render_evidence_bundle_summary = _bundle_rendering.render_evidence_bundle_summary
render_issue_bundle_template = _bundle_rendering.render_issue_bundle_template

EVIDENCE_BUNDLE_SCHEMA_VERSION = 1
MAX_SAFE_ARTIFACT_BYTES = _bundle_files.MAX_SAFE_ARTIFACT_BYTES
_ROOT = _bundle_files._ROOT
_DATASET_MANIFEST_ARTIFACT_KIND = "dataset-manifest"

_OBSERVED_FAILURE_KEYS: tuple[str, ...] = (
    "observed_failure",
    "failure_reason",
    "error",
    "error_message",
    "message",
    "skip_reason",
    "reason",
)
_STATUS_OBSERVED_FAILURES: dict[str, str] = {
    "passed": "No failure recorded; bundle captures a successful preserved run.",
    "cancelled": "Run was cancelled before completion.",
    "failed": "Run failed without a structured failure reason.",
}


@dataclass(frozen=True, slots=True)
class BundleResult:
    """Paths and payload for a generated evidence bundle."""

    output_dir: Path
    manifest_path: Path
    summary_path: Path
    manifest: JSONDict
    issue_template_path: Path | None = None


def generate_evidence_bundle(
    *,
    workspace_dir: Path,
    output_dir: Path,
    run_ids: tuple[str, ...] = (),
    overwrite: bool = False,
    include_fixture_digests: bool = True,
    generated_at: str | None = None,
) -> BundleResult:
    """Generate a deterministic, safe-to-attach evidence bundle from preserved runs."""

    _sync_bundle_file_root()
    workspace, output = _resolved_bundle_paths(workspace_dir=workspace_dir, output_dir=output_dir)
    run_paths = _required_run_paths(workspace, run_ids)
    _prepare_bundle_output(output, overwrite=overwrite)
    context = _bundle_files._BundleContext(output=output)
    runs = _collect_run_evidence(context, run_paths)
    manifest = _build_evidence_bundle_manifest(
        context,
        workspace=workspace,
        runs=runs,
        include_fixture_digests=include_fixture_digests,
        generated_at=generated_at,
    )
    manifest_path, summary_path = _write_evidence_bundle_outputs(output, manifest)
    return BundleResult(
        output_dir=output,
        manifest_path=manifest_path,
        summary_path=summary_path,
        manifest=manifest,
    )


def _resolved_bundle_paths(*, workspace_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    return workspace_dir.expanduser().resolve(), output_dir.expanduser().resolve()


def _required_run_paths(workspace: Path, run_ids: tuple[str, ...]) -> list[Path]:
    run_paths = _bundle_files._select_run_paths(workspace, run_ids)
    if not run_paths:
        raise WorldForgeError("No run workspaces found for evidence bundle generation.")
    return run_paths


def _prepare_bundle_output(output: Path, *, overwrite: bool) -> None:
    if output.exists():
        if not overwrite and any(output.iterdir()):
            raise WorldForgeError(f"Evidence bundle output directory is not empty: {output}")
        if overwrite:
            shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)


def _collect_run_evidence(
    context: _bundle_files._BundleContext,
    run_paths: list[Path],
) -> list[JSONDict]:
    copied_refs: set[Path] = set()
    return [
        _copy_run_evidence(context, run_path=run_path, copied_refs=copied_refs)
        for run_path in run_paths
    ]


def _copy_run_evidence(
    context: _bundle_files._BundleContext,
    *,
    run_path: Path,
    copied_refs: set[Path],
) -> JSONDict:
    manifest = _bundle_files._load_run_manifest(run_path)
    run_id = str(manifest.get("run_id") or run_path.name)
    _bundle_files._copy_run_workspace(
        context, run_path=run_path, run_id=run_id, copied_refs=copied_refs
    )
    _bundle_files._copy_report_references(
        context, run_path=run_path, run_id=run_id, copied_refs=copied_refs
    )
    _bundle_files._record_manifest_artifact_references(
        context,
        run_path=run_path,
        run_id=run_id,
        manifest=manifest,
    )
    return _run_record(manifest=manifest, run_path=run_path, run_id=run_id)


def _run_record(*, manifest: JSONDict, run_path: Path, run_id: str) -> JSONDict:
    return {
        "run_id": run_id,
        "kind": str(manifest.get("kind", "")),
        "status": str(manifest.get("status", "")),
        "command": str(manifest.get("command", "")),
        "provider": manifest.get("provider"),
        "operation": manifest.get("operation"),
        "expected_signal": _expected_signal(manifest),
        "observed_failure": _observed_failure(manifest),
        "skip_reason": _skip_reason(manifest),
        "validation_errors": _validation_errors(manifest),
        "source_path": _display_path(run_path),
    }


def _build_evidence_bundle_manifest(
    context: _bundle_files._BundleContext,
    *,
    workspace: Path,
    runs: list[JSONDict],
    include_fixture_digests: bool,
    generated_at: str | None,
) -> JSONDict:
    files = context.files or []
    fixture_digests = _bundle_files._fixture_digests() if include_fixture_digests else []
    manifest = {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_workspace": _display_path(workspace),
        "run_count": len(runs),
        "runs": sorted(runs, key=lambda item: str(item["run_id"])),
        "files": sorted(files, key=lambda item: str(item["path"])),
        "fixture_digests": fixture_digests,
        "included_count": sum(1 for item in files if item["included"]),
        "excluded_count": sum(1 for item in files if not item["included"]),
        "safe_to_attach": all(bool(item["safe_to_attach"]) for item in files),
    }
    dump_json(manifest)
    return manifest


def _write_evidence_bundle_outputs(output: Path, manifest: JSONDict) -> tuple[Path, Path]:
    manifest_path = output / "evidence_manifest.json"
    summary_path = output / "summary.md"
    write_json_artifact(manifest_path, manifest)
    summary_path.write_text(
        evidence_bundle_artifact(manifest, "markdown").content, encoding="utf-8"
    )
    (output / "summary.html").write_text(
        evidence_bundle_artifact(manifest, "html").content, encoding="utf-8"
    )
    return manifest_path, summary_path


def generate_issue_bundle(
    *,
    workspace_dir: Path,
    run_id: str,
    output_dir: Path,
    overwrite: bool = False,
    generated_at: str | None = None,
) -> BundleResult:
    """Generate a small issue-ready bundle for one preserved run."""

    result = generate_evidence_bundle(
        workspace_dir=workspace_dir,
        output_dir=output_dir,
        run_ids=(run_id,),
        overwrite=overwrite,
        include_fixture_digests=False,
        generated_at=generated_at,
    )
    manifest = {
        **result.manifest,
        "bundle_kind": "issue-run",
        "issue_template": "issue.md",
        "first_triage_step": _first_triage_step(result.manifest),
    }
    issue_path = result.output_dir / "issue.md"
    write_json_artifact(result.manifest_path, manifest)
    result.summary_path.write_text(
        evidence_bundle_artifact(manifest, "markdown").content,
        encoding="utf-8",
    )
    issue_path.write_text(issue_bundle_artifact(manifest, "markdown").content, encoding="utf-8")
    (result.output_dir / "summary.html").write_text(
        evidence_bundle_artifact(manifest, "html").content,
        encoding="utf-8",
    )
    issue_html_path = result.output_dir / "issue.html"
    issue_html_path.write_text(issue_bundle_artifact(manifest, "html").content, encoding="utf-8")
    return BundleResult(
        output_dir=result.output_dir,
        manifest_path=result.manifest_path,
        summary_path=result.summary_path,
        issue_template_path=issue_path,
        manifest=manifest,
    )


def _register_builtin_report_renderers() -> None:
    _bundle_rendering.register_builtin_evidence_bundle_renderers(
        schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION
    )


_register_builtin_report_renderers()


def _skip_reason(manifest: JSONDict) -> str | None:
    for section_name in ("result_summary", "input_summary"):
        section = manifest.get(section_name)
        if isinstance(section, dict):
            reason = section.get("skip_reason") or section.get("reason")
            if isinstance(reason, str) and reason.strip():
                return reason.strip()
    if manifest.get("status") == "skipped":
        return "skipped without a structured reason"
    return None


def _expected_signal(manifest: JSONDict) -> str:
    result_summary = manifest.get("result_summary", {})
    if isinstance(result_summary, dict):
        expected = result_summary.get("expected_signal")
        if isinstance(expected, str) and expected.strip():
            return expected.strip()
    return "The preserved command completes and writes a non-failed run_manifest.json."


def _observed_failure(manifest: JSONDict) -> str:
    status = _manifest_status(manifest)
    result_summary = _result_summary(manifest)
    return (
        _result_summary_failure(result_summary)
        or _validation_failure(result_summary)
        or _status_observed_failure(status, manifest)
    )


def _manifest_status(manifest: JSONDict) -> str:
    return str(manifest.get("status", "") or "unknown")


def _result_summary(manifest: JSONDict) -> JSONDict:
    result_summary = manifest.get("result_summary", {})
    if isinstance(result_summary, dict):
        return result_summary
    return {}


def _result_summary_failure(result_summary: JSONDict) -> str | None:
    for key in _OBSERVED_FAILURE_KEYS:
        value = result_summary.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _validation_failure(result_summary: JSONDict) -> str | None:
    validation_errors = _validation_errors_from_summary(result_summary)
    if validation_errors:
        return "; ".join(validation_errors)
    return None


def _status_observed_failure(status: str, manifest: JSONDict) -> str:
    if status == "skipped":
        return _skip_reason(manifest) or "Run was skipped without a structured reason."
    return _STATUS_OBSERVED_FAILURES.get(status, f"Run status is {status}.")


def _validation_errors(manifest: JSONDict) -> list[str]:
    result_summary = _result_summary(manifest)
    return _validation_errors_from_summary(result_summary)


def _validation_errors_from_summary(result_summary: JSONDict) -> list[str]:
    raw_errors = result_summary.get("validation_errors") or result_summary.get("validation_error")
    if isinstance(raw_errors, str) and raw_errors.strip():
        return [raw_errors.strip()]
    if isinstance(raw_errors, list):
        return [str(error).strip() for error in raw_errors if str(error).strip()]
    return []


def _sync_bundle_file_root() -> None:
    _bundle_files._ROOT = _ROOT


def _resolve_report_reference(value: object) -> Path | None:
    _sync_bundle_file_root()
    return _bundle_files._resolve_report_reference(value)


def _repo_relative(path: Path) -> Path:
    _sync_bundle_file_root()
    return _bundle_files._repo_relative(path)


def _display_path(path: Path) -> str:
    _sync_bundle_file_root()
    return _bundle_files._display_path(path)


def _known_roots() -> tuple[Path, ...]:
    _sync_bundle_file_root()
    return _bundle_files._known_roots()


_BundleContext = _bundle_files._BundleContext
_copy_report_references = _bundle_files._copy_report_references
_copy_run_workspace = _bundle_files._copy_run_workspace
_fixture_digests = _bundle_files._fixture_digests
_load_run_manifest = _bundle_files._load_run_manifest
_record_manifest_artifact_references = _bundle_files._record_manifest_artifact_references
_select_run_paths = _bundle_files._select_run_paths

__all__ = [
    "EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "BundleResult",
    "generate_evidence_bundle",
    "generate_issue_bundle",
    "render_evidence_bundle_summary",
    "render_issue_bundle_template",
]
