"""Diagnose checkout prerequisites for WorldForge contributors."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class ContributorCheck:
    name: str
    status: str
    required: bool
    summary: str
    triage_step: str
    details: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "summary": self.summary,
            "triage_step": self.triage_step,
            "details": self.details,
        }


Which = Callable[[str], str | None]
Runner = Callable[[Sequence[str]], CommandResult]
ImportChecker = Callable[[str], object | None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. Markdown is safe to paste into public issues.",
    )
    args = parser.parse_args(argv)

    payload = run_contributor_doctor()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_contributor_doctor_markdown(payload))
    return 0 if payload["overall_status"] == "ready" else 1


def run_contributor_doctor(
    *,
    which: Which = shutil.which,
    runner: Runner | None = None,
    import_checker: ImportChecker = importlib.util.find_spec,
    root: Path = ROOT,
) -> dict[str, object]:
    """Return a JSON-native contributor setup diagnosis.

    The report intentionally avoids absolute paths, environment values, usernames, tokens, and
    command output that may contain host-specific details.
    """

    command_runner = runner or _default_runner
    uv_available = which("uv") is not None
    checks = [
        _python_check(),
        _source_tree_check(root),
        _uv_check(which=which, runner=command_runner),
        _docs_tooling_check(uv_available=uv_available, runner=command_runner),
        _github_cli_check(which=which, runner=command_runner),
        *[
            _optional_runtime_check(import_checker, module=module, label=label)
            for module, label in (
                ("stable_worldmodel", "LeWorldModel runtime"),
                ("lerobot", "LeRobot runtime"),
                ("gr00t", "GR00T runtime"),
                ("rerun", "Rerun SDK"),
            )
        ],
    ]
    required_failures = [
        check for check in checks if check.required and check.status not in {"ready"}
    ]
    return {
        "schema_version": 1,
        "overall_status": "ready" if not required_failures else "needs_attention",
        "claim_boundary": (
            "This contributor doctor checks checkout prerequisites only. It does not install "
            "dependencies, validate secrets, download checkpoints, or prove optional runtime "
            "readiness."
        ),
        "checks": [check.to_dict() for check in checks],
        "summary": {
            "ready": sum(1 for check in checks if check.status == "ready"),
            "missing": sum(1 for check in checks if check.status == "missing"),
            "warning": sum(1 for check in checks if check.status == "warning"),
            "skipped": sum(1 for check in checks if check.status == "skipped"),
            "required_failures": len(required_failures),
        },
    }


def render_contributor_doctor_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# WorldForge Contributor Doctor",
        "",
        f"Overall status: `{payload['overall_status']}`",
        "",
        str(payload["claim_boundary"]),
        "",
        "| Check | Required | Status | Summary | First triage step |",
        "| --- | --- | --- | --- | --- |",
    ]
    for raw_check in payload["checks"]:
        check = raw_check if isinstance(raw_check, dict) else {}
        lines.append(
            "| {name} | {required} | `{status}` | {summary} | {triage} |".format(
                name=check.get("name", ""),
                required="yes" if check.get("required") else "no",
                status=check.get("status", ""),
                summary=check.get("summary", ""),
                triage=check.get("triage_step", ""),
            )
        )
    return "\n".join(lines) + "\n"


def _default_runner(command: Sequence[str]) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(returncode=124, stdout=exc.stdout or "", stderr=exc.stderr or "")
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _python_check() -> ContributorCheck:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ready = (3, 13) <= sys.version_info[:2] < (3, 14)
    return ContributorCheck(
        name="Python version",
        status="ready" if ready else "missing",
        required=True,
        summary=f"Python {version}; WorldForge supports >=3.13,<3.14.",
        triage_step="Run commands through `uv run --python 3.13 ...`.",
        details={"version": version, "requires_python": ">=3.13,<3.14"},
    )


def _source_tree_check(root: Path) -> ContributorCheck:
    required_paths = ("pyproject.toml", "src/worldforge", "tests", "docs/src")
    missing = [relative for relative in required_paths if not (root / relative).exists()]
    return ContributorCheck(
        name="Checkout source tree",
        status="ready" if not missing else "missing",
        required=True,
        summary="Required source, test, and docs paths are present."
        if not missing
        else f"Missing checkout paths: {', '.join(missing)}.",
        triage_step="Run the doctor from the repository root after a complete checkout.",
        details={"missing_paths": missing},
    )


def _uv_check(*, which: Which, runner: Runner) -> ContributorCheck:
    if which("uv") is None:
        return ContributorCheck(
            name="uv",
            status="missing",
            required=True,
            summary="uv is not available on PATH.",
            triage_step="Install uv, then run `uv sync --group dev`.",
            details={"on_path": False},
        )
    result = runner(("uv", "--version"))
    ready = result.returncode == 0
    version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
    return ContributorCheck(
        name="uv",
        status="ready" if ready else "missing",
        required=True,
        summary=f"uv command responded: {version}." if ready else "uv is present but failed.",
        triage_step="Run `uv --version`, then reinstall uv if it fails.",
        details={"on_path": True, "command": "uv --version", "exit_code": result.returncode},
    )


def _docs_tooling_check(*, uv_available: bool, runner: Runner) -> ContributorCheck:
    if not uv_available:
        return ContributorCheck(
            name="Docs tooling",
            status="missing",
            required=True,
            summary="Docs tooling was not checked because uv is unavailable.",
            triage_step="Install uv, run `uv sync --group dev`, then rerun this doctor.",
            details={"blocked_by": "uv"},
        )
    result = runner(("uv", "run", "python", "-c", "import mkdocs"))
    ready = result.returncode == 0
    return ContributorCheck(
        name="Docs tooling",
        status="ready" if ready else "missing",
        required=True,
        summary="MkDocs import succeeded through the uv environment."
        if ready
        else "MkDocs import failed through the uv environment.",
        triage_step="Run `uv sync --group dev`, then `uv run mkdocs build --strict`.",
        details={"command": "uv run python -c 'import mkdocs'", "exit_code": result.returncode},
    )


def _github_cli_check(*, which: Which, runner: Runner) -> ContributorCheck:
    if which("gh") is None:
        return ContributorCheck(
            name="GitHub CLI auth",
            status="skipped",
            required=False,
            summary="gh is not available; local validation can still run.",
            triage_step="Install gh and run `gh auth status` before publishing PRs.",
            details={"gh_on_path": False},
        )
    result = runner(("gh", "auth", "status"))
    ready = result.returncode == 0
    return ContributorCheck(
        name="GitHub CLI auth",
        status="ready" if ready else "warning",
        required=False,
        summary="gh auth status succeeded."
        if ready
        else "gh is installed but authentication is not ready.",
        triage_step="Run `gh auth login` or use the GitHub web UI for PR publishing.",
        details={"gh_on_path": True, "command": "gh auth status", "exit_code": result.returncode},
    )


def _optional_runtime_check(
    import_checker: ImportChecker,
    *,
    module: str,
    label: str,
) -> ContributorCheck:
    try:
        available = import_checker(module) is not None
    except (ImportError, ValueError):
        available = False
    return ContributorCheck(
        name=label,
        status="ready" if available else "skipped",
        required=False,
        summary=f"Optional module `{module}` is importable."
        if available
        else f"Optional module `{module}` is not installed; this is expected in base checkout.",
        triage_step=(
            "Use the provider-specific prepared-host command only when running that optional "
            "runtime."
        ),
        details={"module": module, "host_owned": True},
    )


if __name__ == "__main__":
    raise SystemExit(main())
