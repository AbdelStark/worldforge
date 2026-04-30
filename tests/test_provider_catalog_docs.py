from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from worldforge.providers.catalog import (
    PROVIDER_CATALOG,
    provider_docs_index,
    render_provider_catalog_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_INDEX = ROOT / "docs" / "src" / "providers" / "README.md"
README = ROOT / "README.md"
SCRIPT = ROOT / "scripts" / "generate_provider_docs.py"
README_DOCS_LINK_PREFIX = "https://abdelstark.github.io/worldforge/providers/"
START_MARKER = "<!-- provider-catalog:start -->"
END_MARKER = "<!-- provider-catalog:end -->"
README_START_MARKER = "<!-- provider-catalog-readme:start -->"
README_END_MARKER = "<!-- provider-catalog-readme:end -->"


def _provider_catalog_block() -> str:
    content = PROVIDER_INDEX.read_text(encoding="utf-8")
    start = content.index(START_MARKER) + len(START_MARKER)
    end = content.index(END_MARKER, start)
    return content[start:end].strip()


def _readme_catalog_block() -> str:
    content = README.read_text(encoding="utf-8")
    start = content.index(README_START_MARKER) + len(README_START_MARKER)
    end = content.index(README_END_MARKER, start)
    return content[start:end].strip()


def test_provider_catalog_docs_are_generated_from_catalog() -> None:
    assert _provider_catalog_block() == render_provider_catalog_markdown()
    assert _readme_catalog_block() == render_provider_catalog_markdown(
        docs_link_prefix=README_DOCS_LINK_PREFIX
    )


def test_generate_provider_docs_check_passes() -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_provider_catalog_docs_pages_exist_for_linked_entries() -> None:
    provider_docs_dir = ROOT / "docs" / "src" / "providers"
    for entry in PROVIDER_CATALOG:
        if entry.docs_page is not None:
            assert (provider_docs_dir / entry.docs_page).exists()
        assert entry.runtime_ownership


def test_provider_docs_index_points_to_existing_docs() -> None:
    for entry in provider_docs_index():
        assert (ROOT / entry["docs_path"]).exists()
        assert entry["implementation_status"] in {
            "scaffold",
            "experimental",
            "beta",
            "stable",
        }
        assert entry["capabilities"]
        assert entry["registration"]
