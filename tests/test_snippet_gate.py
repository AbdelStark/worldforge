from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_docs_snippets.py"
SPEC = importlib.util.spec_from_file_location("check_docs_snippets", SCRIPT)
assert SPEC is not None
check_docs_snippets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["check_docs_snippets"] = check_docs_snippets
SPEC.loader.exec_module(check_docs_snippets)


def test_docs_snippet_gate_passes_selected_public_docs() -> None:
    payload = check_docs_snippets.check_docs_snippets()

    assert payload["passed"] is True
    assert payload["snippet_count"] >= 6
    assert payload["summary"]["passed"] >= 4
    assert payload["summary"]["skipped"] >= 1
    assert not payload["failures"]
    assert "docs/src/api/python.md" in payload["checked_docs"]
    assert "docs/src/scenarios.md" in payload["checked_docs"]


def test_docs_snippet_gate_reports_python_failure_with_heading(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "broken.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "# Broken",
                "",
                "## Example",
                "",
                "<!-- worldforge-snippet: execute -->",
                "```python",
                "raise RuntimeError('broken snippet')",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = check_docs_snippets.check_docs_snippets(
        docs=("docs/broken.md",),
        root=tmp_path,
    )

    assert payload["passed"] is False
    assert payload["failures"][0]["path"] == "docs/broken.md"
    assert payload["failures"][0]["heading"] == "Example"
    assert payload["failures"][0]["language"] == "python"
    assert payload["failures"][0]["reason"] == "python snippet failed"
    assert "broken snippet" in payload["failures"][0]["stderr"]


def test_docs_snippet_gate_rejects_bad_json(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "bad-json.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "# JSON",
                "",
                "<!-- worldforge-snippet: parse -->",
                "```json",
                "{not-json}",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = check_docs_snippets.check_docs_snippets(
        docs=("docs/bad-json.md",),
        root=tmp_path,
    )

    assert payload["passed"] is False
    assert payload["failures"][0]["reason"].startswith("json snippet failed:")


def test_docs_snippet_gate_preserves_skip_reasons(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "skips.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "# Skips",
                "",
                "<!-- worldforge-snippet: skip-host-owned -->",
                "```python",
                "import torch",
                "```",
                "",
                "<!-- worldforge-snippet: skip-credentialed -->",
                "```json",
                '{"endpoint": "https://provider.example"}',
                "```",
                "",
                "<!-- worldforge-snippet: skip-illustrative -->",
                "```python",
                "...",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = check_docs_snippets.check_docs_snippets(
        docs=("docs/skips.md",),
        root=tmp_path,
    )

    assert payload["passed"] is True
    assert [result["reason"] for result in payload["results"]] == [
        "host-owned",
        "credentialed",
        "illustrative",
    ]


def test_docs_snippet_gate_cli_outputs_json(capsys) -> None:
    assert check_docs_snippets.main(["--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["passed"] is True


def test_docs_snippet_gate_uses_supplied_runner_for_python(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "runner.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "\n".join(
            [
                "# Runner",
                "",
                "<!-- worldforge-snippet: execute -->",
                "```python",
                "print('ok')",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    seen: list[list[str]] = []

    def runner(command: list[str], **kwargs) -> CompletedProcess[str]:
        seen.append(command)
        assert kwargs["cwd"] == tmp_path
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    payload = check_docs_snippets.check_docs_snippets(
        docs=("docs/runner.md",),
        root=tmp_path,
        runner=runner,
    )

    assert payload["passed"] is True
    assert seen
