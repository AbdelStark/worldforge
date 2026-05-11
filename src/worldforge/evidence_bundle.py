"""Checkout-safe evidence bundle export for preserved WorldForge runs."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from worldforge.harness.workspace import runs_dir
from worldforge.html_report import render_evidence_bundle_html, render_issue_bundle_html
from worldforge.models import JSONDict, WorldForgeError, dump_json
from worldforge.testing.capability_fixtures import CAPABILITY_FIXTURE_NAMES

EVIDENCE_BUNDLE_SCHEMA_VERSION = 1
MAX_SAFE_ARTIFACT_BYTES = 1_000_000

_ROOT = Path(__file__).resolve().parents[2]
_SAFE_SUFFIXES = {".json", ".jsonl", ".md", ".csv", ".txt", ".html"}
_SECRET_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\s+[a-z0-9._~-]+|password|secret|signature|token=|"
    r"x-amz-signature|runwayml_api_secret|nvidia_api_key)",
    re.IGNORECASE,
)
_HOST_PATH_PATTERN = re.compile(r"(/Users/|/private/|/var/folders/|file://|[A-Za-z]:\\)")


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

    workspace = workspace_dir.expanduser().resolve()
    output = output_dir.expanduser().resolve()
    run_paths = _select_run_paths(workspace, run_ids)
    if not run_paths:
        raise WorldForgeError("No run workspaces found for evidence bundle generation.")
    if output.exists():
        if not overwrite and any(output.iterdir()):
            raise WorldForgeError(f"Evidence bundle output directory is not empty: {output}")
        if overwrite:
            shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    context = _BundleContext(output=output)
    runs: list[JSONDict] = []
    copied_refs: set[Path] = set()
    for run_path in run_paths:
        manifest = _load_run_manifest(run_path)
        run_id = str(manifest.get("run_id") or run_path.name)
        run_record = {
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
        runs.append(run_record)
        _copy_run_workspace(
            context,
            run_path=run_path,
            run_id=run_id,
            copied_refs=copied_refs,
        )
        _copy_report_references(
            context,
            run_path=run_path,
            run_id=run_id,
            copied_refs=copied_refs,
        )
        _record_manifest_artifact_references(
            context,
            run_path=run_path,
            run_id=run_id,
            manifest=manifest,
        )

    fixture_digests = _fixture_digests() if include_fixture_digests else []
    manifest = {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_workspace": _display_path(workspace),
        "run_count": len(runs),
        "runs": sorted(runs, key=lambda item: str(item["run_id"])),
        "files": sorted(context.files, key=lambda item: str(item["path"])),
        "fixture_digests": fixture_digests,
        "included_count": sum(1 for item in context.files if item["included"]),
        "excluded_count": sum(1 for item in context.files if not item["included"]),
        "safe_to_attach": all(bool(item["safe_to_attach"]) for item in context.files),
    }
    dump_json(manifest)
    manifest_path = output / "evidence_manifest.json"
    summary_path = output / "summary.md"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(render_evidence_bundle_summary(manifest), encoding="utf-8")
    summary_html_path = output / "summary.html"
    summary_html_path.write_text(render_evidence_bundle_html(manifest), encoding="utf-8")
    return BundleResult(
        output_dir=output,
        manifest_path=manifest_path,
        summary_path=summary_path,
        manifest=manifest,
    )


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
    dump_json(manifest)
    issue_path = result.output_dir / "issue.md"
    result.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result.summary_path.write_text(render_evidence_bundle_summary(manifest), encoding="utf-8")
    issue_path.write_text(render_issue_bundle_template(manifest), encoding="utf-8")
    (result.output_dir / "summary.html").write_text(
        render_evidence_bundle_html(manifest), encoding="utf-8"
    )
    issue_html_path = result.output_dir / "issue.html"
    issue_html_path.write_text(render_issue_bundle_html(manifest), encoding="utf-8")
    return BundleResult(
        output_dir=result.output_dir,
        manifest_path=result.manifest_path,
        summary_path=result.summary_path,
        issue_template_path=issue_path,
        manifest=manifest,
    )


def render_evidence_bundle_summary(manifest: JSONDict) -> str:
    """Render a Markdown summary for an evidence bundle manifest."""

    lines = [
        "# WorldForge Evidence Bundle",
        "",
        f"- Schema version: `{manifest['schema_version']}`",
        f"- Generated at: `{manifest['generated_at']}`",
        f"- Source workspace: `{manifest['source_workspace']}`",
        f"- Runs: {manifest['run_count']}",
        f"- Included files: {manifest['included_count']}",
        f"- Excluded files: {manifest['excluded_count']}",
        f"- Safe to attach: `{str(manifest['safe_to_attach']).lower()}`",
        "",
        "## Runs",
        "",
        "| Run | Kind | Status | Provider | Operation | Command | Skip reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| {run_id} | {kind} | {status} | {provider} | {operation} | "
            "`{command}` | {skip_reason} |"
        ).format(
            run_id=run["run_id"],
            kind=run["kind"] or "-",
            status=run["status"] or "-",
            provider=run.get("provider") or "-",
            operation=run.get("operation") or "-",
            command=run.get("command") or "-",
            skip_reason=run.get("skip_reason") or "-",
        )
        for run in manifest["runs"]
    )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "| Path | Included | Safe to attach | SHA256 | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in manifest["files"]:
        digest = str(item.get("sha256") or "-")
        lines.append(
            "| `{path}` | {included} | {safe} | `{digest}` | {reason} |".format(
                path=item["path"],
                included=str(item["included"]).lower(),
                safe=str(item["safe_to_attach"]).lower(),
                digest=digest,
                reason=item.get("reason") or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Fixture Digests",
            "",
            "| Fixture | SHA256 |",
            "| --- | --- |",
        ]
    )
    lines.extend(
        f"| `{fixture['path']}` | `{fixture['sha256']}` |"
        for fixture in manifest["fixture_digests"]
    )
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "This bundle copies checkout-safe evidence from preserved WorldForge run workspaces. "
            "Excluded files are listed with reasons. The bundle does not upload artifacts, execute "
            "live providers, include raw secrets, or claim physical fidelity.",
            "",
        ]
    )
    return "\n".join(lines)


def render_issue_bundle_template(manifest: JSONDict) -> str:
    """Render a short GitHub issue body from an issue-run bundle manifest."""

    runs = manifest.get("runs", [])
    run = runs[0] if isinstance(runs, list) and runs else {}
    if not isinstance(run, dict):
        run = {}
    safe = bool(manifest.get("safe_to_attach"))
    validation_errors = run.get("validation_errors")
    lines = [
        f"## WorldForge Run Issue: `{run.get('run_id', '-')}`",
        "",
        "### Command",
        "",
        f"`{run.get('command') or '-'}`",
        "",
        "### Expected Signal",
        "",
        str(run.get("expected_signal") or "-"),
        "",
        "### Observed Failure",
        "",
        str(run.get("observed_failure") or "-"),
    ]
    if isinstance(validation_errors, list) and validation_errors:
        lines.extend(["", "Validation errors:"])
        lines.extend(f"- {error}" for error in validation_errors)
    lines.extend(
        [
            "",
            "### Artifacts",
            "",
            "- `evidence_manifest.json`",
            "- `summary.md`",
            "- `issue.md`",
            f"- included files: {manifest.get('included_count', 0)}",
            f"- excluded files: {manifest.get('excluded_count', 0)}",
            "",
            "### Safe-To-Attach Notes",
            "",
            f"- safe_to_attach: `{str(safe).lower()}`",
            (
                "- Attach the bundle contents from this directory."
                if safe
                else "- Review `evidence_manifest.json` before attaching; at least one file was "
                "excluded or marked local-only."
            ),
            "- Excluded files remain listed with reason, digest when available, and `local_only`.",
            "",
            "### First Triage Step",
            "",
            str(manifest.get("first_triage_step") or _first_triage_step(manifest)),
            "",
        ]
    )
    return "\n".join(lines)


@dataclass(slots=True)
class _BundleContext:
    output: Path
    files: list[JSONDict] | None = None

    def __post_init__(self) -> None:
        if self.files is None:
            self.files = []


def _select_run_paths(workspace_dir: Path, run_ids: tuple[str, ...]) -> list[Path]:
    root = runs_dir(workspace_dir)
    if run_ids:
        return [root / run_id for run_id in sorted(run_ids)]
    if not root.exists():
        return []
    return sorted(path.parent for path in root.glob("*/run_manifest.json"))


def _load_run_manifest(run_path: Path) -> JSONDict:
    manifest_path = run_path / "run_manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorldForgeError(f"Run manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Run manifest contains invalid JSON: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise WorldForgeError(f"Run manifest must be a JSON object: {manifest_path}")
    return payload


def _copy_run_workspace(
    context: _BundleContext,
    *,
    run_path: Path,
    run_id: str,
    copied_refs: set[Path],
) -> None:
    for source in sorted(path for path in run_path.rglob("*") if path.is_file()):
        resolved = source.resolve()
        if resolved in copied_refs:
            continue
        copied_refs.add(resolved)
        relative = source.relative_to(run_path)
        _copy_safe_file(
            context,
            source=source,
            destination=Path("runs") / run_id / relative,
            kind="run-artifact",
        )


def _copy_report_references(
    context: _BundleContext,
    *,
    run_path: Path,
    run_id: str,
    copied_refs: set[Path],
) -> None:
    for report_path in sorted((run_path / "reports").glob("*.json")):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        run_metadata = payload.get("run_metadata", {})
        if not isinstance(run_metadata, dict):
            continue
        for key, destination_root in (
            ("input_file", Path("inputs")),
            ("budget_file", Path("budgets")),
        ):
            summary = run_metadata.get(key)
            if not isinstance(summary, dict):
                continue
            resource_name = _benchmark_preset_resource_name(summary.get("path"))
            if resource_name is not None:
                _copy_package_resource(
                    context,
                    package="worldforge.benchmark_presets._data",
                    name=resource_name,
                    destination=destination_root
                    / "src/worldforge/benchmark_presets/_data"
                    / resource_name,
                    kind=key,
                )
                continue
            referenced = _resolve_report_reference(summary.get("path"))
            if referenced is None:
                _record_excluded(
                    context,
                    destination=destination_root / run_id / f"{key}.json",
                    source=str(summary.get("path", "")),
                    reason="referenced path is missing, absolute, or outside the repository",
                    kind=key,
                    local_only=True,
                )
                continue
            resolved = referenced.resolve()
            if resolved in copied_refs:
                continue
            copied_refs.add(resolved)
            _copy_safe_file(
                context,
                source=referenced,
                destination=destination_root / _repo_relative(referenced),
                kind=key,
            )
        provenance = payload.get("provenance", {})
        if not isinstance(provenance, dict):
            continue
        dataset_manifests = provenance.get("dataset_manifests", [])
        if not isinstance(dataset_manifests, list):
            continue
        for reference in dataset_manifests:
            if not isinstance(reference, dict):
                continue
            referenced = _resolve_report_reference(reference.get("path"))
            if referenced is None:
                continue
            resolved = referenced.resolve()
            if resolved in copied_refs:
                continue
            copied_refs.add(resolved)
            _copy_safe_file(
                context,
                source=referenced,
                destination=Path("dataset-manifests") / _repo_relative(referenced),
                kind="dataset-manifest",
            )


def _record_manifest_artifact_references(
    context: _BundleContext,
    *,
    run_path: Path,
    run_id: str,
    manifest: JSONDict,
) -> None:
    artifact_paths = manifest.get("artifact_paths", {})
    if not isinstance(artifact_paths, dict):
        return
    for label, raw_path in sorted(artifact_paths.items()):
        if not isinstance(raw_path, str) or not raw_path.strip():
            _record_excluded(
                context,
                destination=Path("runs") / run_id / f"artifacts/{label}",
                source=str(raw_path),
                reason="artifact reference is not a non-empty relative path",
                kind="artifact-reference",
                local_only=True,
            )
            continue
        candidate = Path(raw_path)
        if candidate.is_absolute():
            _record_excluded(
                context,
                destination=Path("runs") / run_id / f"artifacts/{label}",
                source=raw_path,
                reason="absolute artifact path is local-only",
                kind="artifact-reference",
                local_only=True,
            )
            continue
        resolved = (run_path / candidate).resolve()
        if not _is_relative_to(resolved, run_path.resolve()):
            _record_excluded(
                context,
                destination=Path("runs") / run_id / f"artifacts/{label}",
                source=raw_path,
                reason="artifact path escapes the run workspace",
                kind="artifact-reference",
                local_only=True,
            )


def _resolve_report_reference(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = Path(value)
    if raw.is_absolute():
        resolved = raw.resolve()
        if _is_relative_to(resolved, _ROOT.resolve()):
            return resolved
        return None
    candidates = [
        _ROOT / raw,
        _ROOT / "src" / "worldforge" / raw,
        _ROOT / "src" / "worldforge" / raw.parent / raw.name,
    ]
    if value.startswith("benchmark_presets/_data/"):
        candidates.insert(0, _ROOT / "src" / "worldforge" / value)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _benchmark_preset_resource_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    prefix = "benchmark_presets/_data/"
    if not value.startswith(prefix):
        return None
    name = value.removeprefix(prefix)
    if "/" in name or not name.endswith(".json"):
        return None
    return name


def _copy_safe_file(
    context: _BundleContext,
    *,
    source: Path,
    destination: Path,
    kind: str,
) -> None:
    digest = _sha256_file(source)
    size = source.stat().st_size
    reason = _unsafe_reason(source, size)
    if reason is not None:
        _record_file(
            context,
            destination=destination,
            source=source,
            kind=kind,
            included=False,
            safe_to_attach=False,
            local_only="host-local path" in reason,
            reason=reason,
            sha256=digest,
            size=size,
        )
        return
    target = context.output / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    _record_file(
        context,
        destination=destination,
        source=source,
        kind=kind,
        included=True,
        safe_to_attach=True,
        local_only=False,
        reason=None,
        sha256=digest,
        size=size,
    )


def _copy_package_resource(
    context: _BundleContext,
    *,
    package: str,
    name: str,
    destination: Path,
    kind: str,
) -> None:
    resource = resources.files(package).joinpath(name)
    if not resource.is_file():
        _record_excluded(
            context,
            destination=destination,
            source=f"{package}/{name}",
            reason="package resource not found",
            kind=kind,
            local_only=False,
        )
        return
    data = resource.read_bytes()
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    size = len(data)
    reason = _unsafe_bytes_reason(suffix=Path(name).suffix, size=size, data=data)
    if reason is not None:
        _record_file(
            context,
            destination=destination,
            source=Path(f"{package}/{name}"),
            kind=kind,
            included=False,
            safe_to_attach=False,
            local_only="host-local path" in reason,
            reason=reason,
            sha256=digest,
            size=size,
        )
        return
    target = context.output / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    _record_file(
        context,
        destination=destination,
        source=Path(f"{package}/{name}"),
        kind=kind,
        included=True,
        safe_to_attach=True,
        local_only=False,
        reason=None,
        sha256=digest,
        size=size,
    )


def _unsafe_reason(path: Path, size: int) -> str | None:
    return _unsafe_bytes_reason(
        suffix=path.suffix,
        size=size,
        data=path.read_bytes(),
    )


def _unsafe_bytes_reason(*, suffix: str, size: int, data: bytes) -> str | None:
    if suffix.lower() not in _SAFE_SUFFIXES:
        return f"unsupported artifact suffix '{suffix or '<none>'}'"
    if size > MAX_SAFE_ARTIFACT_BYTES:
        return f"file exceeds {MAX_SAFE_ARTIFACT_BYTES} byte safe attachment limit"
    text = data.decode("utf-8", errors="replace")
    if _SECRET_PATTERN.search(text):
        return "secret-like material detected"
    if _HOST_PATH_PATTERN.search(text):
        return "host-local path detected"
    parsed = _json_or_none(text)
    if parsed is not None and _contains_unsafe_url(parsed):
        return "signed or credentialed URL detected"
    return None


def _contains_unsafe_url(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_unsafe_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unsafe_url(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(
        re.search(
            r"https?://[^\\s\"']+[?&](token|signature|sig|key|api_key)=",
            value,
            re.I,
        )
    )


def _json_or_none(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _record_excluded(
    context: _BundleContext,
    *,
    destination: Path,
    source: str,
    reason: str,
    kind: str,
    local_only: bool,
) -> None:
    context.files.append(
        {
            "path": destination.as_posix(),
            "source": _safe_source_display(source),
            "kind": kind,
            "included": False,
            "safe_to_attach": False,
            "local_only": local_only,
            "reason": reason,
            "sha256": None,
            "size_bytes": None,
        }
    )


def _record_file(
    context: _BundleContext,
    *,
    destination: Path,
    source: Path,
    kind: str,
    included: bool,
    safe_to_attach: bool,
    local_only: bool,
    reason: str | None,
    sha256: str,
    size: int,
) -> None:
    context.files.append(
        {
            "path": destination.as_posix(),
            "source": _display_path(source),
            "kind": kind,
            "included": included,
            "safe_to_attach": safe_to_attach,
            "local_only": local_only,
            "reason": reason,
            "sha256": sha256,
            "size_bytes": size,
        }
    )


def _fixture_digests() -> list[JSONDict]:
    fixtures: list[JSONDict] = []
    fixtures.extend(
        _resource_digest(
            package=f"worldforge.testing.fixtures.{capability}",
            name=entry.name,
            display_path=f"src/worldforge/testing/fixtures/{capability}/{entry.name}",
        )
        for capability in CAPABILITY_FIXTURE_NAMES
        for entry in sorted(
            resources.files(f"worldforge.testing.fixtures.{capability}").iterdir(),
            key=lambda item: item.name,
        )
        if entry.name.endswith(".json") and entry.is_file()
    )
    fixtures.extend(
        _resource_digest(
            package="worldforge.benchmark_presets._data",
            name=entry.name,
            display_path=f"src/worldforge/benchmark_presets/_data/{entry.name}",
        )
        for entry in sorted(
            resources.files("worldforge.benchmark_presets._data").iterdir(),
            key=lambda item: item.name,
        )
        if entry.name.endswith(".json") and entry.is_file()
    )
    return sorted(fixtures, key=lambda item: str(item["path"]))


def _resource_digest(*, package: str, name: str, display_path: str) -> JSONDict:
    data = resources.files(package).joinpath(name).read_bytes()
    return {
        "path": display_path,
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "size_bytes": len(data),
    }


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
    status = str(manifest.get("status", "") or "unknown")
    result_summary = manifest.get("result_summary", {})
    if isinstance(result_summary, dict):
        for key in (
            "observed_failure",
            "failure_reason",
            "error",
            "error_message",
            "message",
            "skip_reason",
            "reason",
        ):
            value = result_summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        validation_errors = _validation_errors(manifest)
        if validation_errors:
            return "; ".join(validation_errors)
    if status == "passed":
        return "No failure recorded; bundle captures a successful preserved run."
    if status == "skipped":
        return _skip_reason(manifest) or "Run was skipped without a structured reason."
    if status == "cancelled":
        return "Run was cancelled before completion."
    if status == "failed":
        return "Run failed without a structured failure reason."
    return f"Run status is {status}."


def _validation_errors(manifest: JSONDict) -> list[str]:
    result_summary = manifest.get("result_summary", {})
    if not isinstance(result_summary, dict):
        return []
    raw_errors = result_summary.get("validation_errors") or result_summary.get("validation_error")
    if isinstance(raw_errors, str) and raw_errors.strip():
        return [raw_errors.strip()]
    if isinstance(raw_errors, list):
        return [str(error).strip() for error in raw_errors if str(error).strip()]
    return []


def _first_triage_step(manifest: JSONDict) -> str:
    if not bool(manifest.get("safe_to_attach")):
        return (
            "Open evidence_manifest.json, inspect excluded files and local_only entries, and "
            "remove or replace unsafe artifacts before attaching the bundle."
        )
    return (
        "Open summary.md, then inspect the copied run_manifest.json and report artifacts for the "
        "preserved run."
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _repo_relative(path: Path) -> Path:
    resolved = path.resolve()
    try:
        return resolved.relative_to(_ROOT.resolve())
    except ValueError:
        return Path(path.name)


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_ROOT.resolve()).as_posix()
    except ValueError:
        return f"<host-local:{path.name}>"


def _safe_source_display(source: str) -> str:
    if Path(source).is_absolute() or _HOST_PATH_PATTERN.search(source):
        return f"<host-local:{Path(source).name or 'path'}>"
    return source


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "BundleResult",
    "generate_evidence_bundle",
    "generate_issue_bundle",
    "render_evidence_bundle_summary",
    "render_issue_bundle_template",
]
