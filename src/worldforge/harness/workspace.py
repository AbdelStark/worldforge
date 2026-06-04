"""Run workspace layout helpers for harness and CLI flows."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from worldforge.artifact_io import write_json_artifact
from worldforge.config_profiles import validate_config_profile_provenance
from worldforge.models import JSONDict, WorldForgeError, require_json_dict, require_non_empty_text

RUN_WORKSPACE_SCHEMA_VERSION = 1
RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{8}$")


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    """Filesystem locations for one preserved WorldForge run."""

    run_id: str
    path: Path

    @property
    def inputs_dir(self) -> Path:
        return self.path / "inputs"

    @property
    def results_dir(self) -> Path:
        return self.path / "results"

    @property
    def reports_dir(self) -> Path:
        return self.path / "reports"

    @property
    def artifacts_dir(self) -> Path:
        return self.path / "artifacts"

    @property
    def logs_dir(self) -> Path:
        return self.path / "logs"

    @property
    def manifest_path(self) -> Path:
        return self.path / "run_manifest.json"

    def write_json(self, relative_path: str, payload: object) -> Path:
        """Write a stable JSON artifact below this run workspace."""

        target = self._resolve_child(relative_path)
        return write_json_artifact(target, payload)

    def write_text(self, relative_path: str, text: str) -> Path:
        """Write a text artifact below this run workspace."""

        target = self._resolve_child(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text if text.endswith("\n") else f"{text}\n", encoding="utf-8")
        return target

    def _resolve_child(self, relative_path: str) -> Path:
        target = self.path / relative_path
        resolved = target.resolve()
        root = self.path.resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"run artifact path escapes workspace: {relative_path}")
        return target


def create_run_id(now: datetime | None = None) -> str:
    """Return a sortable, file-safe run id."""

    timestamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"


def validate_run_id(run_id: str) -> str:
    """Validate and return a run id."""

    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must match YYYYMMDDTHHMMSSZ-xxxxxxxx with a lowercase hex suffix")
    return run_id


def workspace_root_for_state_dir(state_dir: Path) -> Path:
    """Return the workspace root associated with a world state directory."""

    if state_dir.name == "worlds" and state_dir.parent.name == ".worldforge":
        return state_dir.parent
    return state_dir


def runs_dir(workspace_dir: Path) -> Path:
    """Return the canonical runs directory for a WorldForge workspace."""

    return workspace_dir / "runs"


def create_run_workspace(
    workspace_dir: Path,
    *,
    kind: str,
    command: str,
    provider: str | None = None,
    operation: str | None = None,
    run_id: str | None = None,
    input_summary: JSONDict | None = None,
) -> RunWorkspace:
    """Create a `.worldforge/runs/<run-id>/` workspace and initial manifest."""

    resolved_run_id = validate_run_id(run_id) if run_id is not None else create_run_id()
    workspace = RunWorkspace(
        run_id=resolved_run_id,
        path=runs_dir(workspace_dir).resolve() / resolved_run_id,
    )
    for directory in (
        workspace.inputs_dir,
        workspace.results_dir,
        workspace.reports_dir,
        workspace.artifacts_dir,
        workspace.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=False)
    write_run_manifest(
        workspace,
        kind=kind,
        command=command,
        provider=provider,
        operation=operation,
        status="running",
        input_summary=input_summary or {},
    )
    return workspace


def write_run_manifest(
    workspace: RunWorkspace,
    *,
    kind: str,
    command: str,
    status: str,
    provider: str | None = None,
    operation: str | None = None,
    input_summary: JSONDict | None = None,
    result_summary: JSONDict | None = None,
    artifact_paths: dict[str, str] | None = None,
    config_profile: JSONDict | None = None,
    event_count: int = 0,
) -> Path:
    """Write the sanitized manifest for a preserved run."""

    payload = build_run_manifest_payload(
        workspace,
        kind=kind,
        command=command,
        provider=provider,
        operation=operation,
        status=status,
        input_summary=input_summary,
        result_summary=result_summary,
        artifact_paths=artifact_paths,
        config_profile=config_profile,
        event_count=event_count,
    )
    return write_json_artifact(workspace.manifest_path, payload)


def build_run_manifest_payload(
    workspace: RunWorkspace,
    *,
    kind: str,
    command: str,
    status: str,
    provider: str | None = None,
    operation: str | None = None,
    input_summary: JSONDict | None = None,
    result_summary: JSONDict | None = None,
    artifact_paths: dict[str, str] | None = None,
    config_profile: JSONDict | None = None,
    event_count: int = 0,
) -> JSONDict:
    """Build and validate the sanitized manifest for a preserved run."""

    validated_kind = require_non_empty_text(kind, name="run manifest kind")
    validated_status = require_non_empty_text(status, name="run manifest status")
    if not isinstance(command, str):
        raise WorldForgeError("run manifest command must be a string.")
    validated_event_count = _validate_event_count(event_count)
    validated_artifact_paths = _validate_artifact_paths(workspace, artifact_paths or {})
    payload: JSONDict = {
        "schema_version": RUN_WORKSPACE_SCHEMA_VERSION,
        "run_id": workspace.run_id,
        "created_at": _created_at_from_run_id(workspace.run_id),
        "kind": validated_kind,
        "command": command,
        "status": validated_status,
        "provider": _optional_manifest_text(provider, name="run manifest provider"),
        "operation": _optional_manifest_text(operation, name="run manifest operation"),
        "input_summary": require_json_dict(input_summary or {}, name="run manifest input_summary"),
        "result_summary": require_json_dict(
            result_summary or {},
            name="run manifest result_summary",
        ),
        "artifact_paths": validated_artifact_paths,
        "event_count": validated_event_count,
        "layout": {
            "inputs": "inputs/",
            "results": "results/",
            "reports": "reports/",
            "artifacts": "artifacts/",
            "logs": "logs/",
        },
    }
    if config_profile is not None:
        payload["config_profile"] = validate_config_profile_provenance(config_profile)
    return payload


def _optional_manifest_text(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorldForgeError(f"{name} must be a string when provided.")
    return value


def _validate_event_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldForgeError("run manifest event_count must be an integer.")
    if value < 0:
        raise WorldForgeError("run manifest event_count must be greater than or equal to 0.")
    return value


def _validate_artifact_paths(workspace: RunWorkspace, artifact_paths: dict[str, str]) -> JSONDict:
    del workspace
    if not isinstance(artifact_paths, dict):
        raise WorldForgeError("run manifest artifact_paths must be a JSON object.")
    validated: JSONDict = {}
    for raw_name, raw_path in artifact_paths.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise WorldForgeError("run manifest artifact path names must be non-empty strings.")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise WorldForgeError(
                f"run manifest artifact path for '{raw_name}' must be a non-empty string."
            )
        validated[raw_name] = raw_path
    return validated


def list_run_workspaces(workspace_dir: Path) -> tuple[JSONDict, ...]:
    """Return run manifests sorted newest first."""

    root = runs_dir(workspace_dir)
    if not root.exists():
        return ()
    runs: list[JSONDict] = []
    for manifest_path in root.glob("*/run_manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = require_json_dict(payload, name=f"Run manifest {manifest_path}")
        except (OSError, json.JSONDecodeError, WorldForgeError):
            continue
        payload["path"] = str(manifest_path.parent)
        runs.append(payload)
    return tuple(sorted(runs, key=lambda item: str(item.get("run_id", "")), reverse=True))


def cleanup_run_workspaces(
    workspace_dir: Path,
    *,
    keep: int,
    dry_run: bool = False,
) -> tuple[Path, ...]:
    """Remove old run workspaces while keeping the newest `keep` runs."""

    if keep < 0:
        raise ValueError("keep must be greater than or equal to 0")
    manifests = list_run_workspaces(workspace_dir)
    stale_paths = tuple(Path(str(item["path"])) for item in manifests[keep:])
    if dry_run:
        return stale_paths
    for path in stale_paths:
        shutil.rmtree(path)
    return stale_paths


def _created_at_from_run_id(run_id: str) -> str:
    timestamp = run_id.split("-", 1)[0]
    parsed = datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return parsed.isoformat().replace("+00:00", "Z")
