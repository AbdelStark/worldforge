"""Execute selected checkout-safe Python snippets and parse selected JSON snippets."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DOCS = (
    "docs/src/api/python.md",
    "docs/src/scenarios.md",
    "docs/src/provider-routing.md",
    "docs/src/external-providers.md",
    "docs/src/benchmarking.md",
    "docs/src/artifact-integrity.md",
    "docs/src/world-diff.md",
    "docs/src/html-reports.md",
)

MARKER_PATTERN = re.compile(r"^<!--\s*worldforge-snippet:\s*([a-z-]+)\s*-->\s*$")
FENCE_PATTERN = re.compile(r"^```([A-Za-z0-9_-]*)\s*$")
SKIP_ACTIONS = {"skip-host-owned", "skip-credentialed", "skip-illustrative"}
EXECUTABLE_ACTIONS = {"execute", "parse"}
VALID_ACTIONS = EXECUTABLE_ACTIONS | SKIP_ACTIONS
MAX_CAPTURE_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class SnippetMarker:
    action: str
    path: str
    line: int
    heading: str


@dataclass(frozen=True, slots=True)
class SnippetBlock:
    path: str
    line: int
    heading: str
    language: str
    action: str
    code: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--doc",
        action="append",
        default=[],
        help="Markdown file to scan. Can be repeated. Defaults to selected public docs.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format for the snippet report.",
    )
    args = parser.parse_args(argv)

    docs = tuple(args.doc or DEFAULT_DOCS)
    payload = check_docs_snippets(docs=docs)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_docs_snippet_markdown(payload))
    return 0 if payload["passed"] else 1


def check_docs_snippets(
    *,
    docs: tuple[str, ...] = DEFAULT_DOCS,
    root: Path = ROOT,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    blocks: list[SnippetBlock] = []
    failures: list[dict[str, Any]] = []
    for doc in docs:
        path = root / doc
        parsed = parse_snippet_blocks(path, root=root)
        blocks.extend(parsed["blocks"])
        failures.extend(parsed["failures"])

    results = [run_snippet_block(block, root=root, runner=runner) for block in blocks]
    failures.extend(result for result in results if result["status"] == "failed")
    return {
        "schema_version": 1,
        "passed": not failures,
        "checked_docs": list(docs),
        "snippet_count": len(results),
        "summary": _summary(results),
        "results": results,
        "failures": failures,
        "claim_boundary": (
            "This gate executes only snippets marked with `worldforge-snippet: execute` and "
            "parses only snippets marked with `worldforge-snippet: parse`. Shell snippets, "
            "credentialed examples, optional-runtime examples, and illustrative fragments stay "
            "skipped with explicit markers."
        ),
    }


def parse_snippet_blocks(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    relative = _display_path(path, root)
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[SnippetBlock] = []
    failures: list[dict[str, Any]] = []
    heading = "(top)"
    pending: SnippetMarker | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("#"):
            heading = line.lstrip("#").strip() or heading
        marker_match = MARKER_PATTERN.match(line)
        if marker_match:
            action = marker_match.group(1)
            if action not in VALID_ACTIONS:
                failures.append(
                    _failure(
                        path=relative,
                        line=index + 1,
                        heading=heading,
                        language="",
                        reason=f"unknown snippet marker action: {action}",
                    )
                )
                pending = None
            else:
                pending = SnippetMarker(
                    action=action,
                    path=relative,
                    line=index + 1,
                    heading=heading,
                )
            index += 1
            continue
        fence_match = FENCE_PATTERN.match(line)
        if fence_match and pending is not None:
            language = fence_match.group(1).strip()
            code_lines: list[str] = []
            fence_line = index + 1
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index >= len(lines):
                failures.append(
                    _failure(
                        path=relative,
                        line=fence_line,
                        heading=pending.heading,
                        language=language,
                        reason="snippet fence is not closed",
                    )
                )
                pending = None
                break
            blocks.append(
                SnippetBlock(
                    path=relative,
                    line=fence_line,
                    heading=pending.heading,
                    language=language,
                    action=pending.action,
                    code="\n".join(code_lines).rstrip() + "\n",
                )
            )
            pending = None
        index += 1
    if pending is not None:
        failures.append(
            _failure(
                path=relative,
                line=pending.line,
                heading=pending.heading,
                language="",
                reason="snippet marker is not followed by a fenced code block",
            )
        )
    return {"blocks": blocks, "failures": failures}


def run_snippet_block(
    block: SnippetBlock,
    *,
    root: Path = ROOT,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    base = _result_base(block)
    if block.action in SKIP_ACTIONS:
        return {
            **base,
            "status": "skipped",
            "reason": block.action.removeprefix("skip-"),
        }
    if block.action == "execute":
        if block.language != "python":
            return {**base, "status": "failed", "reason": "execute snippets must be python"}
        return _execute_python(block, root=root, runner=runner)
    if block.action == "parse":
        if block.language != "json":
            return {**base, "status": "failed", "reason": "parse snippets must be json"}
        return _parse_json(block, root=root)
    return {**base, "status": "failed", "reason": f"unsupported action: {block.action}"}


def render_docs_snippet_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Docs Snippet Gate",
        "",
        f"- Status: `{'passed' if payload['passed'] else 'failed'}`",
        f"- Snippets: `{payload['snippet_count']}`",
        f"- Executed: `{payload['summary'].get('passed', 0)}`",
        f"- Skipped: `{payload['summary'].get('skipped', 0)}`",
        "",
        payload["claim_boundary"],
        "",
        "| File | Heading | Line | Language | Action | Status | Reason |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            f"| `{result['path']}` | {result['heading']} | {result['line']} | "
            f"`{result['language']}` | `{result['action']}` | `{result['status']}` | "
            f"{result.get('reason', '') or 'ok'} |"
        )
        for result in payload["results"]
    )
    return "\n".join(lines) + "\n"


def _execute_python(block: SnippetBlock, *, root: Path, runner: Any) -> dict[str, Any]:
    base = _result_base(block)
    with tempfile.TemporaryDirectory(prefix="worldforge-snippet-") as temp_dir:
        workspace = Path(temp_dir)
        snippet_path = workspace / "snippet.py"
        snippet_path.write_text(block.code, encoding="utf-8")
        command = [
            sys.executable,
            "-I",
            "-c",
            _python_probe_source(),
            str(root),
            str(snippet_path),
            str(workspace),
            f"{block.path}:{block.line}",
        ]
        completed = runner(command, cwd=root, capture_output=True, text=True, timeout=10)
    if completed.returncode != 0:
        return {
            **base,
            "status": "failed",
            "reason": "python snippet failed",
            "stdout": _tail(completed.stdout),
            "stderr": _tail(completed.stderr),
        }
    return {**base, "status": "passed", "reason": "executed in temp workspace"}


def _parse_json(block: SnippetBlock, *, root: Path) -> dict[str, Any]:
    base = _result_base(block)
    try:
        payload = json.loads(block.code)
        schema_note = _validate_known_json_schema(block, payload, root=root)
    except Exception as exc:
        return {**base, "status": "failed", "reason": f"json snippet failed: {exc}"}
    return {**base, "status": "passed", "reason": schema_note}


def _validate_known_json_schema(block: SnippetBlock, payload: object, *, root: Path) -> str:
    if block.path.endswith("scenarios.md") and isinstance(payload, dict) and "actions" in payload:
        from worldforge.scenarios import parse_scenario

        parse_scenario(payload)
        return "parsed as Scenario"
    if block.path.endswith("benchmarking.md"):
        from worldforge.benchmark import load_benchmark_budgets, load_benchmark_inputs

        if isinstance(payload, dict) and "budgets" in payload:
            load_benchmark_budgets(payload)
            return "parsed as BenchmarkBudget list"
        with tempfile.TemporaryDirectory(prefix="worldforge-snippet-benchmark-") as temp_dir:
            seed_clip = Path(temp_dir) / "seed-transfer.bin"
            seed_clip.write_bytes(b"snippet-transfer-fixture")
            load_benchmark_inputs(payload, base_path=temp_dir)
        return "parsed as BenchmarkInputs"
    return "parsed as JSON"


def _python_probe_source() -> str:
    return r"""
import os
import runpy
import sys
from pathlib import Path

root, snippet_path, workspace, source = sys.argv[1:5]
sys.path.insert(0, str(Path(root) / "src"))
os.environ["WORLDFORGE_SNIPPET_WORKSPACE"] = workspace
os.chdir(workspace)
runpy.run_path(snippet_path, run_name="__main__")
"""


def _result_base(block: SnippetBlock) -> dict[str, Any]:
    return {
        "path": block.path,
        "line": block.line,
        "heading": block.heading,
        "language": block.language,
        "action": block.action,
    }


def _failure(
    *,
    path: str,
    line: int,
    heading: str,
    language: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "path": path,
        "line": line,
        "heading": heading,
        "language": language,
        "action": "parse",
        "status": "failed",
        "reason": reason,
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for result in results:
        status = str(result["status"])
        summary[status] = summary.get(status, 0) + 1
    return summary


def _display_path(path: Path, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _tail(value: str) -> str:
    return value[-MAX_CAPTURE_CHARS:]


if __name__ == "__main__":
    raise SystemExit(main())
