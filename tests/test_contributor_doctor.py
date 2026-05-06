from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "contributor_doctor.py"
SPEC = importlib.util.spec_from_file_location("contributor_doctor", SCRIPT)
assert SPEC is not None
contributor_doctor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["contributor_doctor"] = contributor_doctor
SPEC.loader.exec_module(contributor_doctor)


def _which_with(names: set[str]):
    return lambda name: f"/fake/{name}" if name in names else None


def _runner_with(returncodes: dict[tuple[str, ...], int]):
    def runner(command: Sequence[str]):
        key = tuple(command)
        return contributor_doctor.CommandResult(
            returncode=returncodes.get(key, 0),
            stdout="uv 0.9.18\n" if key == ("uv", "--version") else "",
        )

    return runner


def _missing_import(_: str) -> None:
    return None


def test_contributor_doctor_ready_state_with_optional_runtime_skips() -> None:
    payload = contributor_doctor.run_contributor_doctor(
        which=_which_with({"uv", "gh"}),
        runner=_runner_with(
            {
                ("uv", "--version"): 0,
                ("uv", "run", "python", "-c", "import mkdocs"): 0,
                ("gh", "auth", "status"): 0,
            }
        ),
        import_checker=_missing_import,
        root=ROOT,
    )

    assert payload["overall_status"] == "ready"
    assert payload["summary"]["required_failures"] == 0
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["uv"]["status"] == "ready"
    assert checks["GitHub CLI auth"]["status"] == "ready"
    assert checks["LeRobot runtime"]["status"] == "skipped"
    assert "does not install dependencies" in payload["claim_boundary"]


def test_contributor_doctor_missing_uv_blocks_required_setup() -> None:
    payload = contributor_doctor.run_contributor_doctor(
        which=_which_with({"gh"}),
        runner=_runner_with({("gh", "auth", "status"): 0}),
        import_checker=_missing_import,
        root=ROOT,
    )

    checks = {check["name"]: check for check in payload["checks"]}
    assert payload["overall_status"] == "needs_attention"
    assert checks["uv"]["status"] == "missing"
    assert checks["Docs tooling"]["status"] == "missing"
    assert checks["Docs tooling"]["details"]["blocked_by"] == "uv"


def test_contributor_doctor_missing_gh_auth_is_warning_not_failure() -> None:
    payload = contributor_doctor.run_contributor_doctor(
        which=_which_with({"uv", "gh"}),
        runner=_runner_with(
            {
                ("uv", "--version"): 0,
                ("uv", "run", "python", "-c", "import mkdocs"): 0,
                ("gh", "auth", "status"): 1,
            }
        ),
        import_checker=_missing_import,
        root=ROOT,
    )

    checks = {check["name"]: check for check in payload["checks"]}
    assert payload["overall_status"] == "ready"
    assert checks["GitHub CLI auth"]["status"] == "warning"
    assert checks["GitHub CLI auth"]["required"] is False


def test_contributor_doctor_markdown_is_public_issue_safe() -> None:
    payload = contributor_doctor.run_contributor_doctor(
        which=_which_with({"uv"}),
        runner=_runner_with(
            {
                ("uv", "--version"): 0,
                ("uv", "run", "python", "-c", "import mkdocs"): 0,
            }
        ),
        import_checker=_missing_import,
        root=ROOT,
    )

    markdown = contributor_doctor.render_contributor_doctor_markdown(payload)

    assert markdown.startswith("# WorldForge Contributor Doctor")
    assert "| Check | Required | Status | Summary | First triage step |" in markdown
    assert "/fake" not in markdown
