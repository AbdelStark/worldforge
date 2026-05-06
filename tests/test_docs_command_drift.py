from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_docs_commands.py"
SPEC = importlib.util.spec_from_file_location("check_docs_commands", SCRIPT)
assert SPEC is not None
check_docs_commands = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["check_docs_commands"] = check_docs_commands
SPEC.loader.exec_module(check_docs_commands)


def test_docs_command_checker_passes_current_public_docs(capsys) -> None:
    assert check_docs_commands.main(["--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["passed"] is True
    assert payload["missing_entry_points"] == []
    assert payload["stale_commands"] == []
    assert payload["undocumented_worldforge_subcommands"] == []
    assert payload["documented_count"] > 20


def test_docs_command_checker_reports_stale_and_missing_commands(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "known-smoke").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "example"

[project.scripts]
worldforge = "worldforge.cli:main"
worldforge-demo-known = "worldforge.demo:main"
worldforge-demo-missing = "worldforge.missing:main"
""".lstrip(),
        encoding="utf-8",
    )
    doc = tmp_path / "README.md"
    doc.write_text(
        """
```bash
uv run worldforge doctor
uv run worldforge missing-subcommand
uv run worldforge-demo-known
scripts/known-smoke
scripts/missing-smoke
```
""".lstrip(),
        encoding="utf-8",
    )

    report = check_docs_commands.check_docs_commands(tmp_path, docs=("README.md",))

    assert report.passed is False
    assert report.missing_entry_points == ("worldforge-demo-missing",)
    assert any("worldforge missing-subcommand" in item for item in report.stale_commands)
    assert any("scripts/missing-smoke" in item for item in report.stale_commands)
