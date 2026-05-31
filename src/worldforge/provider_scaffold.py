"""Generate a WorldForge provider scaffold."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from worldforge.provider_scaffold_models import (
    CAPABILITIES,
    DEFAULT_TAXONOMY,
    IMPLEMENTATION_STATUSES,
    ProviderNames,
    ScaffoldOptions,
    normalize_provider_name,
)
from worldforge.provider_scaffold_models import (
    dedupe_capabilities as _dedupe_capabilities,
)
from worldforge.provider_scaffold_rendering import scaffold_files


def write_scaffold(options: ScaffoldOptions) -> list[Path]:
    files = scaffold_files(options)
    existing = [path for path in files if path.exists()]
    if existing and not options.force:
        joined = "\n".join(f"- {path}" for path in existing)
        raise FileExistsError(f"refusing to overwrite existing scaffold files:\n{joined}")

    written: list[Path] = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def parse_args(argv: list[str]) -> ScaffoldOptions:
    parser = argparse.ArgumentParser(
        description="Generate a safe WorldForge provider scaffold.",
    )
    parser.add_argument("name", help="Provider display name, e.g. 'Acme WM'.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to write into. Defaults to the current directory.",
    )
    parser.add_argument(
        "--taxonomy",
        default=DEFAULT_TAXONOMY,
        help="Taxonomy category from docs/src/world-model-taxonomy.md.",
    )
    parser.add_argument(
        "--planned-capability",
        action="append",
        choices=CAPABILITIES,
        required=True,
        help="Capability stub to write. Repeat for multiple planned capabilities.",
    )
    parser.add_argument(
        "--implementation-status",
        choices=IMPLEMENTATION_STATUSES,
        required=True,
        help="Explicit provider maturity claim for the generated scaffold.",
    )
    parser.add_argument(
        "--env-var",
        help="Optional environment variable required by the provider.",
    )
    locality = parser.add_mutually_exclusive_group()
    locality.add_argument("--local", action="store_true", help="Scaffold a local provider.")
    locality.add_argument("--remote", action="store_true", help="Scaffold a remote provider.")
    parser.add_argument("--force", action="store_true", help="Overwrite generated scaffold files.")

    args = parser.parse_args(argv)
    names = normalize_provider_name(args.name)
    planned_capabilities = _dedupe_capabilities(args.planned_capability or [])
    if not planned_capabilities:
        parser.error("at least one --planned-capability is required")
    env_var = args.env_var.strip() if args.env_var else None
    if env_var == "":
        parser.error("--env-var must not be empty")
    is_local = not args.remote
    if args.remote and env_var is None:
        env_var = f"{names.snake.upper()}_API_KEY"

    return ScaffoldOptions(
        root=args.root.expanduser().resolve(),
        names=names,
        taxonomy=args.taxonomy.strip() or DEFAULT_TAXONOMY,
        planned_capabilities=planned_capabilities,
        implementation_status=args.implementation_status,
        is_local=is_local,
        env_var=env_var,
        force=bool(args.force),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_args(sys.argv[1:] if argv is None else argv)
        written = write_scaffold(options)
    except (FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Generated provider scaffold for {options.names.display}:")
    for path in written:
        print(f"- {path.relative_to(options.root)}")
    print("\nNext steps:")
    print("- implement the TODO methods before advertising capabilities")
    print("- replace placeholder fixtures and the .json.stub runtime manifest before promotion")
    print("- add the provider to src/worldforge/providers/__init__.py when it is ready")
    print("- register it in src/worldforge/providers/catalog.py only after the adapter is tested")
    print("- link the docs stub from docs/src/providers/README.md")
    print("\nNext validation commands:")
    print(f"- uv run pytest tests/test_{options.names.snake}_provider.py")
    print("- uv run python scripts/generate_provider_docs.py --check")
    print("- uv run pytest tests/test_provider_catalog_docs.py")
    print("- uv run mkdocs build --strict")
    print("\nWorkbench command after adding a catalog or direct target:")
    print(f"- uv run worldforge provider workbench {options.names.slug} --format markdown")
    return 0


__all__ = [
    "CAPABILITIES",
    "DEFAULT_TAXONOMY",
    "IMPLEMENTATION_STATUSES",
    "ProviderNames",
    "ScaffoldOptions",
    "main",
    "normalize_provider_name",
    "parse_args",
    "scaffold_files",
    "write_scaffold",
]


if __name__ == "__main__":
    raise SystemExit(main())
