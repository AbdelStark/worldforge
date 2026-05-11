from __future__ import annotations

import argparse
import configparser
import tarfile
import zipfile
from collections.abc import Iterable
from email.parser import Parser
from pathlib import Path

PACKAGE_NAME = "worldforge-ai"

WHEEL_REQUIRED_FILES = (
    "worldforge/__init__.py",
    "worldforge/py.typed",
    "worldforge/rerun.py",
    "worldforge/capabilities/__init__.py",
    "worldforge/providers/observable.py",
    "worldforge/demos/rerun_showcase.py",
    "worldforge/smoke/robotics_showcase.py",
)

WHEEL_FORBIDDEN_PREFIXES = (
    "AGENTS.md",
    "docs/",
    "examples/",
    "scripts/",
    "tests/",
)

SDIST_REQUIRED_SUFFIXES = (
    ".env.example",
    "AGENTS.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "MAINTAINERS.md",
    "README.md",
    "SECURITY.md",
    "SUPPORT.md",
    "mkdocs.yml",
    "pyproject.toml",
    "docs/src/api/python.md",
    "docs/src/architecture.md",
    "docs/src/artifact-integrity.md",
    "docs/src/demo-showcases.md",
    "docs/src/docs-map.md",
    "docs/src/provider-authoring-guide.md",
    "docs/src/quality.md",
    "docs/src/robotics-showcase-deep-dive.md",
    "docs/src/use-case-cookbook.md",
    "scripts/demo_showcases.py",
    "scripts/generate_dependency_audit_evidence.py",
    "scripts/generate_quality_dashboard.py",
    "scripts/generate_release_notes.py",
    "scripts/check_wrapper_portability.py",
    "scripts/contributor_doctor.py",
    "scripts/check_distribution.py",
    "scripts/test_package.sh",
    "src/worldforge/py.typed",
    "src/worldforge/capabilities/__init__.py",
    "src/worldforge/providers/observable.py",
    "tests/test_capability_dual_routing.py",
    "tests/test_capability_protocols.py",
)

REQUIRED_CONSOLE_SCRIPTS = (
    "worldforge",
    "worldforge-harness",
    "worldforge-demo-leworldmodel",
    "worldforge-demo-lerobot",
    "worldforge-demo-rerun",
    "worldforge-build-leworldmodel-checkpoint",
    "worldforge-smoke-leworldmodel",
    "worldforge-smoke-lerobot-leworldmodel",
    "worldforge-robotics-showcase",
    "lewm-real",
    "lewm-lerobot-real",
)

REQUIRED_METADATA = {
    "Name": PACKAGE_NAME,
    "Requires-Python": "<3.14,>=3.13",
    "License-Expression": "MIT",
}


def _single_artifact(dist_dir: Path, pattern: str) -> Path:
    matches = sorted(dist_dir.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {pattern} in {dist_dir}, found {len(matches)}")
    return matches[0]


def _wheel_names(wheel_path: Path) -> list[str]:
    with zipfile.ZipFile(wheel_path) as archive:
        return archive.namelist()


def _sdist_names(sdist_path: Path) -> list[str]:
    with tarfile.open(sdist_path) as archive:
        return archive.getnames()


def _require_exact(names: Iterable[str], required: Iterable[str], artifact: Path) -> None:
    present = set(names)
    missing = [entry for entry in required if entry not in present]
    if missing:
        formatted = "\n  - ".join(missing)
        raise SystemExit(f"{artifact.name} is missing required entries:\n  - {formatted}")


def _require_suffixes(
    names: Iterable[str], required_suffixes: Iterable[str], artifact: Path
) -> None:
    present = tuple(names)
    missing = [
        suffix for suffix in required_suffixes if not any(name.endswith(suffix) for name in present)
    ]
    if missing:
        formatted = "\n  - ".join(missing)
        raise SystemExit(f"{artifact.name} is missing required entries:\n  - {formatted}")


def _reject_generated_python_cache(names: Iterable[str], artifact: Path) -> None:
    offenders = [
        name for name in names if "__pycache__/" in name or name.endswith((".pyc", ".pyo", ".pyd"))
    ]
    if offenders:
        formatted = "\n  - ".join(sorted(offenders)[:20])
        raise SystemExit(f"{artifact.name} contains generated Python cache files:\n  - {formatted}")


def _reject_wheel_source_only_payloads(names: Iterable[str], artifact: Path) -> None:
    offenders = [
        name
        for name in names
        if any(name == prefix or name.startswith(prefix) for prefix in WHEEL_FORBIDDEN_PREFIXES)
    ]
    if offenders:
        formatted = "\n  - ".join(sorted(offenders)[:20])
        raise SystemExit(f"{artifact.name} contains source-only payloads:\n  - {formatted}")


def _read_wheel_text(wheel_path: Path, suffix: str) -> str:
    names = _wheel_names(wheel_path)
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one wheel entry ending with {suffix!r} in {wheel_path.name}, "
            f"found {len(matches)}"
        )
    with zipfile.ZipFile(wheel_path) as archive:
        return archive.read(matches[0]).decode("utf-8")


def _check_wheel_metadata(wheel_path: Path) -> None:
    metadata = Parser().parsestr(_read_wheel_text(wheel_path, ".dist-info/METADATA"))
    for field, expected in REQUIRED_METADATA.items():
        actual = metadata.get(field)
        if actual != expected:
            raise SystemExit(
                f"{wheel_path.name} metadata field {field!r} is {actual!r}; expected {expected!r}"
            )
    extras = set(metadata.get_all("Provides-Extra", []))
    for extra in ("harness", "rerun"):
        if extra not in extras:
            raise SystemExit(f"{wheel_path.name} metadata is missing the {extra} extra")


def _check_console_scripts(wheel_path: Path) -> None:
    parser = configparser.ConfigParser()
    parser.read_string(_read_wheel_text(wheel_path, ".dist-info/entry_points.txt"))
    if not parser.has_section("console_scripts"):
        raise SystemExit(f"{wheel_path.name} is missing console_scripts entry points")
    console_scripts = parser["console_scripts"]
    missing = [script for script in REQUIRED_CONSOLE_SCRIPTS if script not in console_scripts]
    if missing:
        formatted = "\n  - ".join(missing)
        raise SystemExit(f"{wheel_path.name} is missing console scripts:\n  - {formatted}")


def check_distribution(dist_dir: Path) -> None:
    if not dist_dir.is_dir():
        raise SystemExit(f"distribution directory does not exist: {dist_dir}")

    wheel_path = _single_artifact(dist_dir, "*.whl")
    sdist_path = _single_artifact(dist_dir, "*.tar.gz")

    wheel_entries = _wheel_names(wheel_path)
    sdist_entries = _sdist_names(sdist_path)

    _require_exact(wheel_entries, WHEEL_REQUIRED_FILES, wheel_path)
    _reject_generated_python_cache(wheel_entries, wheel_path)
    _reject_wheel_source_only_payloads(wheel_entries, wheel_path)
    _check_wheel_metadata(wheel_path)
    _check_console_scripts(wheel_path)

    _require_suffixes(sdist_entries, SDIST_REQUIRED_SUFFIXES, sdist_path)
    _reject_generated_python_cache(sdist_entries, sdist_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate WorldForge wheel and sdist contents.")
    parser.add_argument("dist_dir", type=Path, help="Directory containing one wheel and one sdist.")
    args = parser.parse_args()
    check_distribution(args.dist_dir)


if __name__ == "__main__":
    main()
