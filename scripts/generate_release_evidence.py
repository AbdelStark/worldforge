"""Generate a checkout-safe WorldForge release evidence report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge.live_smoke_evidence import (  # noqa: E402
    render_live_smoke_registry_table,
    validate_live_smoke_registry,
)
from worldforge.smoke.run_manifest import validate_run_manifest  # noqa: E402

DEFAULT_OUTPUT = ROOT / ".worldforge" / "release-evidence" / "release-evidence.md"
DEFAULT_LIVE_SMOKE_REGISTRY = ROOT / "docs" / "src" / "live-smoke-evidence.json"
DEFAULT_RUNS_DIR = ROOT / ".worldforge" / "runs"
DEFAULT_REPORTS_DIR = ROOT / ".worldforge" / "reports"
DEFAULT_DIST_DIR = ROOT / "dist"
DEFAULT_EVIDENCE_BUNDLES_DIR = ROOT / ".worldforge" / "evidence-bundles"

MAX_CAPTURE_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class ReleaseGate:
    """Checkout-safe validation gate included in release-readiness evidence."""

    name: str
    command: str
    triage_step: str


@dataclass(frozen=True, slots=True)
class ReleaseGateResult:
    """Result for one release-readiness validation gate."""

    name: str
    command: str
    status: str
    triage_step: str
    exit_code: int | None = None
    duration_ms: float | None = None
    started_at: str | None = None
    finished_at: str | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "triage_step": self.triage_step,
        }


CHECKOUT_SAFE_GATES = (
    ReleaseGate(
        "Lockfile",
        "uv lock --check",
        "Refresh dependency metadata intentionally, then rerun `uv lock --check`.",
    ),
    ReleaseGate(
        "Lint",
        "uv run ruff check src tests examples scripts",
        "Run Ruff locally, fix the named file and rule, then rerun the lint gate.",
    ),
    ReleaseGate(
        "Format",
        "uv run ruff format --check src tests examples scripts",
        "Run `uv run ruff format src tests examples scripts` and inspect the diff.",
    ),
    ReleaseGate(
        "Provider catalog drift",
        "uv run python scripts/generate_provider_docs.py --check",
        "Run the provider docs generator without `--check`, inspect generated docs, then rerun.",
    ),
    ReleaseGate(
        "Docs command drift",
        "uv run python scripts/check_docs_commands.py",
        "Fix stale command references or document the missing public entry point, then rerun.",
    ),
    ReleaseGate(
        "Core performance budgets",
        "uv run python scripts/check_core_performance.py",
        "Inspect the JSON report row, confirm the measured path, and fix regressions before "
        "changing budgets.",
    ),
    ReleaseGate(
        "Docs",
        "uv run mkdocs build --strict",
        "Fix the reported page, link, or navigation warning before release.",
    ),
    ReleaseGate(
        "Tests",
        "uv run pytest",
        "Reproduce the failing test directly and add or repair the focused regression.",
    ),
    ReleaseGate(
        "Coverage",
        "uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing "
        "--cov-fail-under=90",
        "Add focused tests for uncovered behavior instead of weakening the coverage gate.",
    ),
    ReleaseGate(
        "Package contract",
        "bash scripts/test_package.sh",
        "Inspect the isolated package-contract output for missing files, scripts, or metadata.",
    ),
    ReleaseGate(
        "Build",
        "uv build --out-dir dist --clear --no-build-logs",
        "Fix build backend or package metadata errors, then rebuild into a clean dist directory.",
    ),
    ReleaseGate(
        "Dependency audit",
        (
            'tmp_req="$(mktemp requirements-audit.XXXXXX)" && '
            'uv export --frozen --all-groups --no-emit-project --no-hashes -o "$tmp_req" '
            ">/dev/null && "
            'uvx --from pip-audit pip-audit -r "$tmp_req" --no-deps --disable-pip '
            '--progress-spinner off; status=$?; rm -f "$tmp_req"; exit $status'
        ),
        "Inspect the advisory, update or document the dependency decision, then rerun the audit.",
    ),
)
VALIDATION_COMMANDS = tuple((gate.name, gate.command) for gate in CHECKOUT_SAFE_GATES)

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
        "--json-output",
        help=(
            "JSON report path. Defaults to the Markdown output path with a .json suffix. "
            "Use '-' to print JSON to stdout after writing Markdown."
        ),
    )
    parser.add_argument(
        "--run-gates",
        action="store_true",
        help="Execute checkout-safe release gates before rendering evidence.",
    )
    parser.add_argument(
        "--gate",
        choices=tuple(gate.name for gate in CHECKOUT_SAFE_GATES),
        action="append",
        default=[],
        help="Limit --run-gates to one named gate. Can be repeated.",
    )
    parser.add_argument(
        "--skip-gate",
        choices=tuple(gate.name for gate in CHECKOUT_SAFE_GATES),
        action="append",
        default=[],
        help="Mark one release gate skipped with an explicit reason. Can be repeated.",
    )
    parser.add_argument(
        "--skip-reason",
        default="operator skipped this gate for the current evidence run",
        help="Reason recorded for gates named by --skip-gate.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        action="append",
        default=[],
        help="Optional live-smoke run_manifest.json to include. Can be repeated.",
    )
    parser.add_argument(
        "--live-smoke-registry",
        type=Path,
        default=DEFAULT_LIVE_SMOKE_REGISTRY,
        help=(
            "Publishable live-smoke evidence registry JSON. Defaults to "
            "docs/src/live-smoke-evidence.json."
        ),
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
    json_output = _json_output_path(output, args.json_output)
    selected_gates = _selected_gates(tuple(args.gate or ()))
    gate_results = release_gate_results(
        selected_gates,
        run=args.run_gates,
        skip_gates=tuple(args.skip_gate or ()),
        skip_reason=args.skip_reason,
    )
    manifests = _collect_manifests(args.run_manifest)
    live_smoke_registry = _load_live_smoke_registry(args.live_smoke_registry)
    benchmark_artifacts = _dedupe_paths(
        [*args.benchmark_artifact, *_glob_existing(DEFAULT_REPORTS_DIR, "*.json")]
    )
    artifacts = _dedupe_paths(
        [
            *args.artifact,
            *_glob_existing(DEFAULT_DIST_DIR, "*"),
            *_glob_existing(DEFAULT_EVIDENCE_BUNDLES_DIR, "*/evidence_manifest.json"),
        ]
    )
    report = render_release_evidence(
        output=output,
        manifests=manifests,
        live_smoke_registry=live_smoke_registry,
        benchmark_artifacts=benchmark_artifacts,
        artifacts=artifacts,
        known_limitations=tuple(args.known_limitation),
        gate_results=gate_results,
    )
    payload = release_evidence_payload(
        manifests=manifests,
        live_smoke_registry=live_smoke_registry,
        benchmark_artifacts=benchmark_artifacts,
        artifacts=artifacts,
        known_limitations=tuple(args.known_limitation),
        gate_results=gate_results,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"wrote {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    if json_output == "-":
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif json_output is not None:
        json_path = Path(json_output).expanduser().resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        display = json_path.relative_to(ROOT) if json_path.is_relative_to(ROOT) else json_path
        print(f"wrote {display}")
    failed = [result for result in gate_results if result.status == "failed"]
    return 1 if failed else 0


def release_gate_results(
    gates: tuple[ReleaseGate, ...] = CHECKOUT_SAFE_GATES,
    *,
    run: bool,
    skip_gates: tuple[str, ...] = (),
    skip_reason: str = "",
    runner: Any = subprocess.run,
) -> tuple[ReleaseGateResult, ...]:
    """Return release-readiness gate results, optionally executing commands."""

    skip_gate_names = set(skip_gates)
    results: list[ReleaseGateResult] = []
    for gate in gates:
        if gate.name in skip_gate_names:
            results.append(
                ReleaseGateResult(
                    name=gate.name,
                    command=gate.command,
                    status="skipped",
                    triage_step=skip_reason or gate.triage_step,
                )
            )
            continue
        if not run:
            results.append(
                ReleaseGateResult(
                    name=gate.name,
                    command=gate.command,
                    status="skipped",
                    triage_step="Run with `--run-gates` to execute this checkout-safe gate.",
                )
            )
            continue

        started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        start = monotonic()
        completed = runner(
            gate.command,
            shell=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        finished_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        duration_ms = round((monotonic() - start) * 1000, 3)
        return_code = int(completed.returncode)
        results.append(
            ReleaseGateResult(
                name=gate.name,
                command=gate.command,
                status="passed" if return_code == 0 else "failed",
                exit_code=return_code,
                duration_ms=duration_ms,
                started_at=started_at,
                finished_at=finished_at,
                stdout_tail=_capture_tail(completed.stdout),
                stderr_tail=_capture_tail(completed.stderr),
                triage_step=gate.triage_step,
            )
        )
    unknown_skips = skip_gate_names - {gate.name for gate in gates}
    if unknown_skips:
        unknown = ", ".join(sorted(unknown_skips))
        raise SystemExit(f"Unknown --skip-gate value for selected gates: {unknown}")
    return tuple(results)


def release_evidence_payload(
    *,
    manifests: tuple[ManifestEvidence, ...],
    benchmark_artifacts: tuple[Path, ...],
    artifacts: tuple[Path, ...],
    gate_results: tuple[ReleaseGateResult, ...],
    live_smoke_registry: dict[str, Any] | None = None,
    known_limitations: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return a JSON-native release-readiness evidence payload."""

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "git": {
            "branch": _git_output("branch", "--show-current") or "unknown",
            "commit": _git_output("rev-parse", "--short", "HEAD") or "unknown",
        },
        "validation_gates": [result.to_dict() for result in gate_results],
        "validation_summary": _gate_summary(gate_results),
        "live_provider_evidence": [
            _provider_evidence(provider, manifests) for provider in sorted(LIVE_PROVIDER_ENV)
        ],
        "extra_live_provider_evidence": [
            _provider_evidence(provider, manifests)
            for provider in sorted(
                {
                    manifest.provider
                    for manifest in manifests
                    if manifest.provider not in LIVE_PROVIDER_ENV
                }
            )
        ],
        "live_smoke_registry": live_smoke_registry,
        "benchmark_artifacts": [_path_record(path) for path in benchmark_artifacts],
        "release_artifacts": [_path_record(path) for path in artifacts],
        "known_limitations": list(known_limitations),
        "claim_boundary": (
            "Checkout-safe gates do not prove live provider availability, model quality, "
            "physical fidelity, or robot safety unless a matching live-smoke manifest is linked."
        ),
    }
    return 0


def render_release_evidence(
    *,
    output: Path,
    manifests: tuple[ManifestEvidence, ...],
    benchmark_artifacts: tuple[Path, ...],
    artifacts: tuple[Path, ...],
    live_smoke_registry: dict[str, Any] | None = None,
    known_limitations: tuple[str, ...] = (),
    gate_results: tuple[ReleaseGateResult, ...] | None = None,
) -> str:
    commit = _git_output("rev-parse", "--short", "HEAD") or "unknown"
    branch = _git_output("branch", "--show-current") or "unknown"
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    resolved_gate_results = gate_results or release_gate_results(run=False)
    lines = [
        "# WorldForge Release Evidence",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Git branch: `{branch}`",
        f"- Git commit: `{commit}`",
        f"- Validation status: `{_overall_gate_status(resolved_gate_results)}`",
        "",
        "## Validation Gates",
        "",
        "| Gate | Command | Status | Exit | First triage step |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for result in resolved_gate_results:
        exit_code = "-" if result.exit_code is None else str(result.exit_code)
        lines.append(
            f"| {result.name} | `{result.command}` | {result.status} | "
            f"{exit_code} | {result.triage_step} |"
        )

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
            "## Live Smoke Evidence Registry",
            "",
        ]
    )
    if live_smoke_registry is None:
        lines.append("- No live-smoke evidence registry linked.")
    else:
        lines.extend(render_live_smoke_registry_table(live_smoke_registry))

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


def _json_output_path(markdown_output: Path, raw_json_output: Path | str | None) -> Path | str:
    if raw_json_output == "-":
        return "-"
    if raw_json_output is not None:
        return Path(raw_json_output)
    return markdown_output.with_suffix(".json")


def _selected_gates(names: tuple[str, ...]) -> tuple[ReleaseGate, ...]:
    if not names:
        return CHECKOUT_SAFE_GATES
    selected_names = set(names)
    return tuple(gate for gate in CHECKOUT_SAFE_GATES if gate.name in selected_names)


def _capture_tail(value: str | None) -> str:
    if not value:
        return ""
    stripped = value.strip()
    if len(stripped) <= MAX_CAPTURE_CHARS:
        return stripped
    return stripped[-MAX_CAPTURE_CHARS:]


def _gate_summary(results: tuple[ReleaseGateResult, ...]) -> dict[str, int]:
    summary = {"passed": 0, "failed": 0, "skipped": 0, "host-owned": 0}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return summary


def _overall_gate_status(results: tuple[ReleaseGateResult, ...]) -> str:
    summary = _gate_summary(results)
    if summary["failed"]:
        return "failed"
    if summary["passed"] and not summary["skipped"]:
        return "passed"
    return "skipped"


def _provider_evidence(provider: str, manifests: tuple[ManifestEvidence, ...]) -> dict[str, Any]:
    matching = [manifest for manifest in manifests if manifest.provider == provider]
    if matching:
        return {
            "provider": provider,
            "status": _combined_manifest_status(matching),
            "manifests": [
                {
                    "path": _display_path(manifest.path),
                    "status": manifest.status,
                    "capability": manifest.payload["capability"],
                    "artifact_paths": manifest.payload.get("artifact_paths", {}),
                }
                for manifest in matching
            ],
            "reason": "",
        }
    env_vars = LIVE_PROVIDER_ENV.get(provider, ())
    configured = any(os.environ.get(name, "").strip() for name in env_vars)
    env_summary = ", ".join(env_vars) or "no known env gate"
    return {
        "provider": provider,
        "status": "host-owned",
        "manifests": [],
        "reason": (
            "configured but no run manifest linked"
            if configured
            else f"missing host-owned configuration: {env_summary}"
        ),
    }


def _path_record(path: Path) -> dict[str, str | int | None]:
    resolved = path.expanduser().resolve()
    digest = None
    size = None
    if resolved.is_file():
        data = resolved.read_bytes()
        digest = "sha256:" + sha256(data).hexdigest()
        size = len(data)
    return {
        "path": _display_path(resolved),
        "sha256": digest,
        "size_bytes": size,
    }


def _load_live_smoke_registry(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    registry_path = path.expanduser()
    if not registry_path.exists():
        return None
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    return validate_live_smoke_registry(payload)


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
    env_summary = ", ".join(f"`{name}`" for name in env_vars) or "no known env gate"
    reason = (
        "configured but no run manifest linked"
        if configured
        else f"missing host-owned configuration: {env_summary}"
    )
    status = "host-owned"
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
    display = _display_path(resolved)
    link = os.path.relpath(resolved, start=output.parent).replace(os.sep, "/")
    return f"[`{display}`]({link})"


def _display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


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
