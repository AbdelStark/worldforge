"""Audit optional runtime import boundaries for checkout-safe WorldForge paths."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


@dataclass(frozen=True, slots=True)
class OptionalImportBoundary:
    name: str
    roots: tuple[str, ...]
    direct_import_allowed: tuple[str, ...]
    lazy_import_allowed: tuple[str, ...]
    triage_step: str


@dataclass(frozen=True, slots=True)
class BoundaryViolation:
    path: str
    line: int
    boundary: str
    imported: str
    kind: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "boundary": self.boundary,
            "imported": self.imported,
            "kind": self.kind,
            "message": self.message,
        }


DEFAULT_BOUNDARIES = (
    OptionalImportBoundary(
        name="Textual TUI",
        roots=("textual",),
        direct_import_allowed=("src/worldforge/harness/tui.py",),
        lazy_import_allowed=(),
        triage_step="Move Textual imports into src/worldforge/harness/tui.py.",
    ),
    OptionalImportBoundary(
        name="Rerun SDK",
        roots=("rerun",),
        direct_import_allowed=(),
        lazy_import_allowed=("src/worldforge/rerun.py",),
        triage_step="Load Rerun through worldforge.rerun and keep rerun-sdk optional.",
    ),
    OptionalImportBoundary(
        name="Torch",
        roots=("torch",),
        direct_import_allowed=(
            "src/worldforge/smoke/leworldmodel.py",
            "src/worldforge/smoke/leworldmodel_checkpoint.py",
            "src/worldforge/smoke/lerobot_leworldmodel.py",
            "src/worldforge/smoke/pusht_showcase_inputs.py",
        ),
        lazy_import_allowed=(
            "src/worldforge/providers/leworldmodel.py",
            "src/worldforge/providers/jepa_wms.py",
            "src/worldforge/providers/lerobot.py",
            "src/worldforge/smoke/jepa_wms.py",
        ),
        triage_step="Keep torch imports in prepared-host providers or optional smoke modules.",
    ),
    OptionalImportBoundary(
        name="LeWorldModel",
        roots=("stable_worldmodel", "stable_pretraining"),
        direct_import_allowed=("src/worldforge/smoke/pusht_showcase_inputs.py",),
        lazy_import_allowed=(
            "src/worldforge/providers/leworldmodel.py",
            "src/worldforge/smoke/leworldmodel_checkpoint.py",
        ),
        triage_step="Keep stable-worldmodel imports behind LeWorldModel optional runtime paths.",
    ),
    OptionalImportBoundary(
        name="LeRobot",
        roots=("lerobot",),
        direct_import_allowed=(),
        lazy_import_allowed=("src/worldforge/providers/lerobot.py",),
        triage_step="Keep LeRobot imports inside LeRobotPolicyProvider lazy loading.",
    ),
    OptionalImportBoundary(
        name="GR00T",
        roots=("gr00t",),
        direct_import_allowed=(),
        lazy_import_allowed=("src/worldforge/providers/gr00t.py",),
        triage_step="Keep GR00T client imports inside GrootPolicyClientProvider lazy loading.",
    ),
    OptionalImportBoundary(
        name="Cosmos-Policy server",
        roots=("cosmos_policy",),
        direct_import_allowed=(),
        lazy_import_allowed=(),
        triage_step="Do not import a Cosmos-Policy runtime package from WorldForge base paths.",
    ),
)

OPTIONAL_RUNTIME_ROOTS = tuple(
    sorted({root for boundary in DEFAULT_BOUNDARIES for root in boundary.roots})
)

IMPORT_TIME_MODULES = (
    "worldforge",
    "worldforge.cli",
    "worldforge.framework",
    "worldforge.providers",
    "worldforge.evaluation",
    "worldforge.benchmark",
    "worldforge.testing",
    "worldforge.rerun",
    "worldforge.harness.cli",
    "worldforge.harness.connectors",
    "worldforge.harness.flows",
    "worldforge.harness.models",
    "worldforge.harness.report_compare",
    "worldforge.harness.run_history",
    "worldforge.harness.run_index",
    "worldforge.harness.theme",
    "worldforge.harness.workbench",
    "worldforge.harness.workspace",
    "worldforge.harness.worlds_view",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format for the optional import boundary report.",
    )
    args = parser.parse_args(argv)

    payload = check_optional_import_boundaries()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_optional_import_boundary_markdown(payload))
    return 0 if payload["passed"] else 1


def check_optional_import_boundaries(
    *,
    root: Path = ROOT,
    boundaries: tuple[OptionalImportBoundary, ...] = DEFAULT_BOUNDARIES,
    import_time_modules: tuple[str, ...] = IMPORT_TIME_MODULES,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Return the static and import-time optional dependency boundary report."""

    static_result = check_static_import_boundaries(root=root, boundaries=boundaries)
    import_time_result = check_import_time_boundaries(
        root=root,
        optional_roots=tuple(sorted({root for item in boundaries for root in item.roots})),
        modules=import_time_modules,
        runner=runner,
    )
    return {
        "schema_version": 1,
        "passed": static_result["passed"] and import_time_result["passed"],
        "claim_boundary": (
            "This audit checks checkout-safe base imports and static Python imports. It does not "
            "install optional runtimes, import TUI modules, start provider servers, or validate "
            "prepared-host packages."
        ),
        "static": static_result,
        "import_time": import_time_result,
    }


def check_static_import_boundaries(
    *,
    root: Path = ROOT,
    boundaries: tuple[OptionalImportBoundary, ...] = DEFAULT_BOUNDARIES,
) -> dict[str, Any]:
    """Check Python source files for disallowed optional runtime imports."""

    violations: list[BoundaryViolation] = []
    src_root = root / "src" / "worldforge"
    for path in sorted(src_root.rglob("*.py")):
        violations.extend(_check_python_file(path, root=root, boundaries=boundaries))
    return {
        "passed": not violations,
        "checked_files": sum(1 for _ in src_root.rglob("*.py")),
        "violations": [violation.to_dict() for violation in violations],
    }


def check_import_time_boundaries(
    *,
    root: Path = ROOT,
    optional_roots: tuple[str, ...] = OPTIONAL_RUNTIME_ROOTS,
    modules: tuple[str, ...] = IMPORT_TIME_MODULES,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Import base modules in a clean process and report leaked optional modules."""

    command = [
        sys.executable,
        "-I",
        "-c",
        _import_time_probe_source(),
        str(root / "src"),
        json.dumps(list(optional_roots)),
        json.dumps(list(modules)),
    ]
    completed = runner(command, cwd=root, capture_output=True, text=True)
    if completed.returncode != 0:
        return {
            "passed": False,
            "modules": list(modules),
            "optional_roots": list(optional_roots),
            "loaded_optional_modules": [],
            "failures": [
                {
                    "message": "import-time probe failed",
                    "exit_code": int(completed.returncode),
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                }
            ],
        }
    payload = json.loads(completed.stdout)
    loaded = payload.get("loaded_optional_modules", [])
    failures = (
        [
            {
                "message": (
                    "checkout-safe imports loaded optional runtime modules: "
                    + ", ".join(str(item) for item in loaded)
                )
            }
        ]
        if loaded
        else []
    )
    return {
        "passed": not loaded,
        "modules": list(modules),
        "optional_roots": list(optional_roots),
        "loaded_optional_modules": loaded,
        "failures": failures,
    }


def render_optional_import_boundary_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Optional Import Boundary Audit",
        "",
        f"- Status: `{'passed' if payload['passed'] else 'failed'}`",
        f"- Static files checked: `{payload['static']['checked_files']}`",
        "",
        payload["claim_boundary"],
        "",
        "## Static Import Violations",
        "",
    ]
    violations = payload["static"]["violations"]
    if not violations:
        lines.append("- none")
    else:
        lines.extend(
            (
                "- "
                f"`{violation['path']}:{violation['line']}` imports "
                f"`{violation['imported']}` for {violation['boundary']} "
                f"via {violation['kind']}: {violation['message']}"
            )
            for violation in violations
        )
    lines.extend(["", "## Import-Time Leaks", ""])
    loaded = payload["import_time"]["loaded_optional_modules"]
    if loaded:
        lines.extend(f"- `{item}`" for item in loaded)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _check_python_file(
    path: Path,
    *,
    root: Path,
    boundaries: tuple[OptionalImportBoundary, ...],
) -> tuple[BoundaryViolation, ...]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    relative_path = path.relative_to(root).as_posix()
    violations: list[BoundaryViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                violations.extend(
                    _violations_for_import(
                        relative_path,
                        line=node.lineno,
                        imported=alias.name,
                        kind="direct import",
                        boundaries=boundaries,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                violations.extend(
                    _violations_for_import(
                        relative_path,
                        line=node.lineno,
                        imported=node.module,
                        kind="direct import",
                        boundaries=boundaries,
                    )
                )
        elif isinstance(node, ast.Call):
            imported = _lazy_import_name(node)
            if imported is None:
                continue
            violations.extend(
                _violations_for_import(
                    relative_path,
                    line=node.lineno,
                    imported=imported,
                    kind="lazy import",
                    boundaries=boundaries,
                )
            )
    return tuple(violations)


def _violations_for_import(
    path: str,
    *,
    line: int,
    imported: str,
    kind: str,
    boundaries: tuple[OptionalImportBoundary, ...],
) -> tuple[BoundaryViolation, ...]:
    root = imported.split(".", 1)[0]
    violations: list[BoundaryViolation] = []
    for boundary in boundaries:
        if root not in boundary.roots:
            continue
        allowed = boundary.lazy_import_allowed
        if kind != "lazy import":
            allowed = boundary.direct_import_allowed
        if path in allowed:
            continue
        violations.append(
            BoundaryViolation(
                path=path,
                line=line,
                boundary=boundary.name,
                imported=imported,
                kind=kind,
                message=boundary.triage_step,
            )
        )
    return tuple(violations)


def _lazy_import_name(node: ast.Call) -> str | None:
    if not node.args:
        return None
    if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        return None
    function = node.func
    if isinstance(function, ast.Name) and function.id == "import_module":
        return node.args[0].value
    if (
        isinstance(function, ast.Attribute)
        and function.attr in {"import_module", "find_spec"}
        and _attribute_root(function) == "importlib"
    ):
        return node.args[0].value
    return None


def _attribute_root(node: ast.Attribute) -> str | None:
    value: ast.expr = node
    while isinstance(value, ast.Attribute):
        value = value.value
    if isinstance(value, ast.Name):
        return value.id
    return None


def _import_time_probe_source() -> str:
    return r"""
import importlib
import json
import sys

src, roots_json, modules_json = sys.argv[1:4]
sys.path.insert(0, src)
optional_roots = tuple(json.loads(roots_json))
modules = tuple(json.loads(modules_json))
for module in modules:
    importlib.import_module(module)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == root or name.startswith(root + ".") for root in optional_roots)
)
print(json.dumps({"loaded_optional_modules": loaded}, sort_keys=True))
"""


if __name__ == "__main__":
    raise SystemExit(main())
