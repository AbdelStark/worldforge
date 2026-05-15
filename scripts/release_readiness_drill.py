"""Generate checkout-safe release readiness drill evidence.

The drill renders fixture release-evidence artifacts for a clean pass and a
controlled failure without creating tags, building distributions, publishing
packages, signing artifacts, or running host-owned optional runtimes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC = ROOT / "src"
for path in (SCRIPT_DIR, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from generate_release_evidence import (  # noqa: E402
    ReleaseGateResult,
    release_evidence_payload,
    render_release_evidence,
)

DEFAULT_WORKSPACE = ROOT / ".worldforge" / "release-readiness-drill"
DRILL_MODES = ("clean-pass", "controlled-failure")


@dataclass(frozen=True, slots=True)
class DrillArtifact:
    mode: str
    status: str
    markdown_path: Path
    json_path: Path
    payload: dict[str, Any]

    def to_dict(self, *, root: Path) -> dict[str, Any]:
        first_failed = first_failed_gate(self.payload)
        return {
            "mode": self.mode,
            "status": self.status,
            "markdown_path": _display_path(self.markdown_path, root),
            "json_path": _display_path(self.json_path, root),
            "validation_summary": self.payload["validation_summary"],
            "host_owned_optional_skips": [
                row
                for row in self.payload["live_provider_evidence"]
                if row["status"] == "host-owned"
            ],
            "first_failed_gate": first_failed,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="Directory where drill evidence artifacts are written.",
    )
    parser.add_argument(
        "--mode",
        choices=(*DRILL_MODES, "all"),
        default="all",
        help="Drill fixture to render. Defaults to both clean-pass and controlled-failure.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Summary format printed to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_release_readiness_drill(args.workspace_dir, mode=args.mode)
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_drill_summary_markdown(result))
    return 0 if result["status"] == "passed" else 1


def run_release_readiness_drill(workspace_dir: Path, *, mode: str = "all") -> dict[str, Any]:
    if mode not in (*DRILL_MODES, "all"):
        raise ValueError(f"unknown release readiness drill mode: {mode}")
    workspace = workspace_dir.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    modes = DRILL_MODES if mode == "all" else (mode,)
    artifacts = tuple(_render_drill_mode(workspace, drill_mode) for drill_mode in modes)
    summary = {
        "schema_version": 1,
        "kind": "release_readiness_drill",
        "status": "passed",
        "safe_to_attach": True,
        "workspace_dir": _display_path(workspace, ROOT),
        "publishing_actions": {
            "creates_git_tag": False,
            "publishes_package": False,
            "creates_github_release": False,
            "signs_artifacts": False,
        },
        "claim_boundary": (
            "Drill evidence rehearses release gates and optional-runtime skip reporting only; "
            "maintainer release approval still requires the real release checklist and current "
            "gate outputs."
        ),
        "artifacts": [artifact.to_dict(root=ROOT) for artifact in artifacts],
    }
    summary_path = workspace / "release-readiness-drill.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = workspace / "release-readiness-drill.md"
    markdown_path.write_text(render_drill_summary_markdown(summary), encoding="utf-8")
    summary["summary_json"] = _display_path(summary_path, ROOT)
    summary["summary_markdown"] = _display_path(markdown_path, ROOT)
    return summary


def _render_drill_mode(workspace: Path, mode: str) -> DrillArtifact:
    mode_dir = workspace / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = mode_dir / "release-evidence.md"
    json_path = mode_dir / "release-evidence.json"
    gate_results = _fixture_gate_results(mode)
    limitations = (
        (
            "Release readiness drill fixture; no tag, publish, signing, or trusted publishing "
            "step ran."
        ),
        "Host-owned optional runtime smokes are represented as explicit skips unless linked "
        "by a real run manifest.",
    )
    now = _drill_timestamp
    report = render_release_evidence(
        output=markdown_path,
        manifests=(),
        benchmark_artifacts=(),
        artifacts=(),
        gate_results=gate_results,
        known_limitations=limitations,
        now_utc=now,
    )
    markdown_path.write_text(report, encoding="utf-8")
    payload = release_evidence_payload(
        manifests=(),
        benchmark_artifacts=(),
        artifacts=(),
        gate_results=gate_results,
        known_limitations=limitations,
        now_utc=now,
    )
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return DrillArtifact(
        mode=mode,
        status=_fixture_status(payload),
        markdown_path=markdown_path,
        json_path=json_path,
        payload=payload,
    )


def _fixture_gate_results(mode: str) -> tuple[ReleaseGateResult, ...]:
    if mode == "clean-pass":
        return (
            ReleaseGateResult(
                name="Docs command drift",
                command="uv run python scripts/check_docs_commands.py",
                status="passed",
                exit_code=0,
                duration_ms=125.0,
                started_at="2026-01-01T00:00:00+00:00",
                finished_at="2026-01-01T00:00:01+00:00",
                stdout_tail="Status: passed",
                triage_step="Fix stale command references, then rerun the docs command gate.",
            ),
            ReleaseGateResult(
                name="Package contract",
                command="bash scripts/test_package.sh",
                status="passed",
                exit_code=0,
                duration_ms=250.0,
                started_at="2026-01-01T00:00:01+00:00",
                finished_at="2026-01-01T00:00:02+00:00",
                stdout_tail="package contract passed",
                triage_step="Inspect package contract output for missing files or metadata.",
            ),
            ReleaseGateResult(
                name="Optional runtime live smokes",
                command="link prepared-host run_manifest.json files when available",
                status="skipped",
                exit_code=None,
                triage_step=(
                    "Run provider-specific live smokes on a prepared host and pass "
                    "`--run-manifest` to release evidence."
                ),
            ),
        )
    if mode == "controlled-failure":
        return (
            ReleaseGateResult(
                name="Docs command drift",
                command="uv run python scripts/check_docs_commands.py",
                status="passed",
                exit_code=0,
                duration_ms=125.0,
                started_at="2026-01-01T00:00:00+00:00",
                finished_at="2026-01-01T00:00:01+00:00",
                stdout_tail="Status: passed",
                triage_step="Fix stale command references, then rerun the docs command gate.",
            ),
            ReleaseGateResult(
                name="Package contract",
                command="bash scripts/test_package.sh",
                status="failed",
                exit_code=2,
                duration_ms=200.0,
                started_at="2026-01-01T00:00:01+00:00",
                finished_at="2026-01-01T00:00:02+00:00",
                stderr_tail="sdist is missing docs/src/demo-showcases.md",
                triage_step=(
                    "Inspect `scripts/check_distribution.py`, fix the package include contract, "
                    "then rerun `bash scripts/test_package.sh`."
                ),
            ),
            ReleaseGateResult(
                name="Dependency audit",
                command="uv run python scripts/generate_dependency_audit_evidence.py",
                status="skipped",
                exit_code=None,
                triage_step=(
                    "Run the dependency audit after the package-contract failure is fixed."
                ),
            ),
        )
    raise ValueError(f"unknown release readiness drill mode: {mode}")


def first_failed_gate(payload: dict[str, Any]) -> dict[str, Any] | None:
    for gate in payload.get("validation_gates", []):
        if gate.get("status") == "failed":
            return {
                "name": gate["name"],
                "command": gate["command"],
                "triage_step": gate["triage_step"],
                "exit_code": gate["exit_code"],
            }
    return None


def _fixture_status(payload: dict[str, Any]) -> str:
    return "failed" if first_failed_gate(payload) is not None else "passed"


def render_drill_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# WorldForge Release Readiness Drill",
        "",
        summary["claim_boundary"],
        "",
        "| Mode | Status | Evidence JSON | First failed gate | First triage command |",
        "| --- | --- | --- | --- | --- |",
    ]
    for artifact in summary["artifacts"]:
        first_failed = artifact["first_failed_gate"] or {}
        lines.append(
            "| {mode} | {status} | `{json_path}` | {gate} | {triage} |".format(
                mode=artifact["mode"],
                status=artifact["status"],
                json_path=artifact["json_path"],
                gate=first_failed.get("name", "-"),
                triage=first_failed.get("triage_step", "-"),
            )
        )
    lines.extend(
        [
            "",
            "## Publishing Boundary",
            "",
            "- Creates git tag: false",
            "- Publishes package: false",
            "- Creates GitHub release: false",
            "- Signs artifacts: false",
            "",
        ]
    )
    return "\n".join(lines)


def _drill_timestamp() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
