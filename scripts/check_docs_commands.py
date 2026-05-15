"""Check documented WorldForge commands for CLI and entry-point drift."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge.cli import _build_parser  # noqa: E402

DEFAULT_DOCS = (
    "README.md",
    "docs/src/cli.md",
    "docs/src/examples.md",
    "docs/src/operations.md",
    "docs/src/playbooks.md",
    "docs/src/task-starters.md",
    "AGENTS.md",
)
IGNORED_EXECUTABLES = {"uv", "uvx", "pytest", "bash", "curl", "jq", "python", "python3", "rm"}
WORLD_FORGE_COMMAND = re.compile(
    r"(?<![A-Za-z0-9_./-])(worldforge(?:-[A-Za-z0-9_-]+)?)(?!/)([^\n`|]*)"
)
SCRIPT_COMMAND = re.compile(r"(?<![A-Za-z0-9_./-])(scripts/[A-Za-z0-9_.-]+)([^\n`|]*)")


@dataclass(frozen=True, slots=True)
class DocumentedCommand:
    executable: str
    args: tuple[str, ...]
    source: str
    line: int
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "executable": self.executable,
            "args": list(self.args),
            "source": self.source,
            "line": self.line,
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class DocsCommandCheck:
    documented: tuple[DocumentedCommand, ...]
    missing_entry_points: tuple[str, ...]
    stale_commands: tuple[str, ...]
    undocumented_worldforge_subcommands: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.missing_entry_points
            or self.stale_commands
            or self.undocumented_worldforge_subcommands
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "documented_count": len(self.documented),
            "missing_entry_points": list(self.missing_entry_points),
            "stale_commands": list(self.stale_commands),
            "undocumented_worldforge_subcommands": list(self.undocumented_worldforge_subcommands),
            "documented": [command.to_dict() for command in self.documented],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--doc",
        action="append",
        default=[],
        help="Documentation file to scan. Can be repeated. Defaults to public command docs.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format for the drift report.",
    )
    args = parser.parse_args(argv)
    docs = tuple(args.doc or DEFAULT_DOCS)
    report = check_docs_commands(ROOT, docs=docs)
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report.passed else 1


def check_docs_commands(
    root: Path = ROOT,
    *,
    docs: tuple[str, ...] = DEFAULT_DOCS,
) -> DocsCommandCheck:
    """Check docs for stale command references and undocumented public entry points."""

    project_scripts = _project_scripts(root)
    script_paths = _script_paths(root)
    worldforge_subcommands = _worldforge_subcommands()
    documented = tuple(
        command for doc in docs for command in _documented_commands(root / doc, root=root)
    )
    documented_executables = {command.executable for command in documented}
    documented_worldforge_subcommands = {
        command.args[0]
        for command in documented
        if command.executable == "worldforge" and command.args
    }
    stale = tuple(
        sorted(
            _stale_message(command, project_scripts, script_paths, worldforge_subcommands)
            for command in documented
            if _stale_message(command, project_scripts, script_paths, worldforge_subcommands)
        )
    )
    missing_entry_points = tuple(
        sorted(
            name
            for name in project_scripts
            if name.startswith("worldforge") and name not in documented_executables
        )
    )
    undocumented_worldforge_subcommands = tuple(
        sorted(worldforge_subcommands - documented_worldforge_subcommands)
    )
    return DocsCommandCheck(
        documented=documented,
        missing_entry_points=missing_entry_points,
        stale_commands=stale,
        undocumented_worldforge_subcommands=undocumented_worldforge_subcommands,
    )


def render_markdown(report: DocsCommandCheck) -> str:
    lines = [
        "# Docs Command Drift Check",
        "",
        f"- Status: `{'passed' if report.passed else 'failed'}`",
        f"- Documented commands scanned: {len(report.documented)}",
        "",
        "## Missing Entry Points",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report.missing_entry_points)
    if not report.missing_entry_points:
        lines.append("- none")
    lines.extend(["", "## Undocumented `worldforge` Subcommands", ""])
    lines.extend(f"- `worldforge {item}`" for item in report.undocumented_worldforge_subcommands)
    if not report.undocumented_worldforge_subcommands:
        lines.append("- none")
    lines.extend(["", "## Stale Commands", ""])
    lines.extend(f"- {item}" for item in report.stale_commands)
    if not report.stale_commands:
        lines.append("- none")
    return "\n".join(lines)


def _project_scripts(root: Path) -> set[str]:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = payload.get("project", {}).get("scripts", {})
    return {str(name) for name in scripts}


def _script_paths(root: Path) -> set[str]:
    scripts_dir = root / "scripts"
    if not scripts_dir.exists():
        return set()
    return {
        str(path.relative_to(root))
        for path in scripts_dir.iterdir()
        if path.is_file() and not path.name.startswith(".")
    }


def _worldforge_subcommands() -> set[str]:
    parser = _build_parser()
    subcommands: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subcommands.update(action.choices)
            break
    subcommands.discard("providers")
    return subcommands


def _documented_commands(path: Path, *, root: Path) -> tuple[DocumentedCommand, ...]:
    if not path.exists():
        return ()
    commands: list[DocumentedCommand] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        commands.extend(
            _commands_from_matches(
                WORLD_FORGE_COMMAND.finditer(line),
                path=path,
                root=root,
                line_number=line_number,
            )
        )
        commands.extend(
            _commands_from_matches(
                SCRIPT_COMMAND.finditer(line),
                path=path,
                root=root,
                line_number=line_number,
            )
        )
    return tuple(commands)


def _commands_from_matches(
    matches: Any,
    *,
    path: Path,
    root: Path,
    line_number: int,
) -> list[DocumentedCommand]:
    commands: list[DocumentedCommand] = []
    for match in matches:
        executable = match.group(1)
        args = tuple(_split_command_args(match.group(2)))
        commands.append(
            DocumentedCommand(
                executable=executable,
                args=args,
                source=str(path.relative_to(root)),
                line=line_number,
                raw=(executable + match.group(2)).strip(),
            )
        )
    return commands


def _split_command_args(value: str) -> list[str]:
    tokens = []
    for token in value.strip().split():
        cleaned = token.strip("`'\",;:()[]")
        if not cleaned or cleaned.startswith(("-", "<")):
            break
        if cleaned in {"|", "&&", "\\"}:
            break
        tokens.append(cleaned)
    return tokens


def _stale_message(
    command: DocumentedCommand,
    project_scripts: set[str],
    script_paths: set[str],
    worldforge_subcommands: set[str],
) -> str:
    if _is_python_reference(command):
        return ""
    if command.executable in project_scripts:
        if command.executable == "worldforge" and command.args:
            subcommand = command.args[0]
            if subcommand not in worldforge_subcommands and subcommand != "providers":
                return (
                    f"{command.source}:{command.line} references unknown `worldforge {subcommand}`"
                )
        return ""
    if command.executable in script_paths:
        return ""
    if command.executable in IGNORED_EXECUTABLES:
        return ""
    if command.executable.startswith("worldforge-"):
        return ""
    return f"{command.source}:{command.line} references unknown `{command.executable}`"


def _is_python_reference(command: DocumentedCommand) -> bool:
    first_arg = command.args[0] if command.args else ""
    return bool(
        command.executable == "worldforge"
        and (
            first_arg.startswith((".", "_"))
            or first_arg == "import"
            or command.raw.startswith(("worldforge.", "worldforge_"))
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
