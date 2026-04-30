"""Generate a checkout-safe WorldForge release evidence report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge.smoke.run_manifest import validate_run_manifest  # noqa: E402

DEFAULT_OUTPUT = ROOT / ".worldforge" / "release-evidence" / "release-evidence.md"
DEFAULT_RUNS_DIR = ROOT / ".worldforge" / "runs"
DEFAULT_REPORTS_DIR = ROOT / ".worldforge" / "reports"
DEFAULT_DIST_DIR = ROOT / "dist"

VALIDATION_COMMANDS = (
    ("Lockfile", "uv lock --check"),
    ("Lint", "uv run ruff check src tests examples scripts"),
    ("Format", "uv run ruff format --check src tests examples scripts"),
    ("Provider catalog drift", "uv run python scripts/generate_provider_docs.py --check"),
    ("Docs", "uv run mkdocs build --strict"),
    ("Tests", "uv run pytest"),
    (
        "Coverage",
        "uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing "
        "--cov-fail-under=90",
    ),
    ("Package contract", "bash scripts/test_package.sh"),
    ("Build", "uv build --out-dir dist --clear --no-build-logs"),
    (
        "Dependency audit",
        "uv export --all-groups --no-emit-project --no-hashes -o requirements-ci.txt && "
        "uvx --from pip-audit pip-audit -r requirements-ci.txt",
    ),
)

LIVE_PROVIDER_ENV = {
    "cosmos": ("COSMOS_BASE_URL",),
    "runway": ("RUNWAYML_API_SECRET", "RUNWAY_API_SECRET"),
    "leworldmodel": ("LEWORLDMODEL_POLICY", "LEWM_POLICY"),
    "gr00t": ("GROOT_POLICY_HOST",),
    "lerobot": ("LEROBOT_POLICY_PATH", "LEROBOT_POLICY"),
}


@dataclass(frozen=True, slots=True)
class ManifestEvidence:
    path: Path
    payload: dict[str, Any]

    @property
    def provider(self) -> str:
        return str(self.payload["provider_profile"])

    @property
    def status(self) -> str:
        return str(self.payload["status"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Markdown report path. Defaults to .worldforge/release-evidence/release-evidence.md.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        action="append",
        default=[],
        help="Optional live-smoke run_manifest.json to include. Can be repeated.",
    )
    parser.add_argument(
        "--benchmark-artifact",
        type=Path,
        action="append",
        default=[],
        help="Optional benchmark or evaluation artifact to link. Can be repeated.",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        action="append",
        default=[],
        help="Optional preserved release artifact to link. Can be repeated.",
    )
    parser.add_argument(
        "--known-limitation",
        action="append",
        default=[],
        help="Known release limitation to include. Can be repeated.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.expanduser().resolve()
    manifests = _collect_manifests(args.run_manifest)
    benchmark_artifacts = _dedupe_paths(
        [*args.benchmark_artifact, *_glob_existing(DEFAULT_REPORTS_DIR, "*.json")]
    )
    artifacts = _dedupe_paths([*args.artifact, *_glob_existing(DEFAULT_DIST_DIR, "*")])
    report = render_release_evidence(
        output=output,
        manifests=manifests,
        benchmark_artifacts=benchmark_artifacts,
        artifacts=artifacts,
        known_limitations=tuple(args.known_limitation),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"wrote {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    return 0


def render_release_evidence(
    *,
    output: Path,
    manifests: tuple[ManifestEvidence, ...],
    benchmark_artifacts: tuple[Path, ...],
    artifacts: tuple[Path, ...],
    known_limitations: tuple[str, ...] = (),
) -> str:
    commit = _git_output("rev-parse", "--short", "HEAD") or "unknown"
    branch = _git_output("branch", "--show-current") or "unknown"
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    lines = [
        "# WorldForge Release Evidence",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Git branch: `{branch}`",
        f"- Git commit: `{commit}`",
        "",
        "## Validation Gates",
        "",
        "| Gate | Command | Evidence status |",
        "| --- | --- | --- |",
    ]
    for name, command in VALIDATION_COMMANDS:
        lines.append(f"| {name} | `{command}` | not run by evidence generator |")

    lines.extend(
        [
            "",
            "## Live Provider Evidence",
            "",
            "| Provider | Status | Evidence |",
            "| --- | --- | --- |",
        ]
    )
    lines.extend(
        _render_provider_row(provider, manifests, output) for provider in sorted(LIVE_PROVIDER_ENV)
    )

    extra_providers = sorted(
        {manifest.provider for manifest in manifests if manifest.provider not in LIVE_PROVIDER_ENV}
    )
    lines.extend(_render_provider_row(provider, manifests, output) for provider in extra_providers)

    lines.extend(
        [
            "",
            "## Benchmark And Evaluation Artifacts",
            "",
        ]
    )
    lines.extend(
        _artifact_lines(benchmark_artifacts, output, empty="- No benchmark artifacts linked.")
    )

    lines.extend(
        [
            "",
            "## Preserved Release Artifacts",
            "",
        ]
    )
    lines.extend(_artifact_lines(artifacts, output, empty="- No release artifacts linked."))

    lines.extend(
        [
            "",
            "## Known Limitations",
            "",
        ]
    )
    if known_limitations:
        lines.extend(f"- {item}" for item in known_limitations)
    else:
        lines.append(
            "- Live-provider evidence is optional and absent providers are reported explicitly."
        )

    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "This report records release validation evidence and links to preserved artifacts. "
            "Checkout-safe gates do not prove live provider availability, model quality, physical "
            "fidelity, or robot safety unless a matching live-smoke manifest is linked above.",
            "",
        ]
    )
    return "\n".join(lines)


def _collect_manifests(paths: list[Path]) -> tuple[ManifestEvidence, ...]:
    candidates = [*paths, *_glob_existing(DEFAULT_RUNS_DIR, "*/run_manifest.json")]
    evidence: list[ManifestEvidence] = []
    for path in _dedupe_paths(candidates):
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence.append(
            ManifestEvidence(path=path.resolve(), payload=validate_run_manifest(payload))
        )
    return tuple(evidence)


def _render_provider_row(
    provider: str, manifests: tuple[ManifestEvidence, ...], output: Path
) -> str:
    matching = [manifest for manifest in manifests if manifest.provider == provider]
    if matching:
        status = _combined_manifest_status(matching)
        links = ", ".join(_manifest_summary(manifest, output) for manifest in matching)
        return f"| `{provider}` | {status} | {links} |"

    env_vars = LIVE_PROVIDER_ENV.get(provider, ())
    configured = any(os.environ.get(name, "").strip() for name in env_vars)
    status = "skipped" if configured else "not configured"
    env_summary = ", ".join(f"`{name}`" for name in env_vars) or "no known env gate"
    reason = "configured but no run manifest linked" if configured else f"missing {env_summary}"
    return f"| `{provider}` | {status} | {reason} |"


def _combined_manifest_status(manifests: list[ManifestEvidence]) -> str:
    statuses = {manifest.status for manifest in manifests}
    if "failed" in statuses:
        return "failed"
    if "passed" in statuses:
        return "passed"
    return "skipped"


def _manifest_summary(manifest: ManifestEvidence, output: Path) -> str:
    payload = manifest.payload
    bits = [
        _markdown_link(manifest.path, output),
        f"`{payload['status']}`",
        f"`{payload['capability']}`",
    ]
    artifact_paths = payload.get("artifact_paths", {})
    if isinstance(artifact_paths, dict) and artifact_paths:
        bits.append(
            "artifacts: "
            + ", ".join(f"`{name}`={value}" for name, value in sorted(artifact_paths.items()))
        )
    return " ".join(bits)


def _artifact_lines(paths: tuple[Path, ...], output: Path, *, empty: str) -> list[str]:
    if not paths:
        return [empty]
    return [f"- {_markdown_link(path, output)}" for path in paths]


def _markdown_link(path: Path, output: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        display = resolved.relative_to(ROOT)
    except ValueError:
        display = resolved
    link = os.path.relpath(resolved, start=output.parent).replace(os.sep, "/")
    return f"[`{display}`]({link})"


def _glob_existing(directory: Path, pattern: str) -> tuple[Path, ...]:
    if not directory.exists():
        return ()
    return tuple(sorted(path for path in directory.glob(pattern) if path.is_file()))


def _dedupe_paths(paths: list[Path]) -> tuple[Path, ...]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return tuple(deduped)


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ("git", *args),
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
