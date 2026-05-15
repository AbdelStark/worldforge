from __future__ import annotations

import re
from pathlib import Path

from worldforge.providers.catalog import (
    PROVIDER_CATALOG,
    provider_configuration_index,
    render_provider_configuration_index_markdown,
)
from worldforge.providers.runtime_manifest import load_runtime_manifests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_INDEX = ROOT / "docs" / "src" / "provider-configuration-index.md"
START_MARKER = "<!-- provider-config-index:start -->"
END_MARKER = "<!-- provider-config-index:end -->"


def _provider_config_block() -> str:
    content = CONFIG_INDEX.read_text(encoding="utf-8")
    start = content.index(START_MARKER) + len(START_MARKER)
    end = content.index(END_MARKER, start)
    return content[start:end].strip()


def _env_example_names() -> set[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]+)=", text, flags=re.MULTILINE))


def _smoke_command_anchor(command: str) -> str:
    for token in command.split():
        if token.startswith(("worldforge-smoke", "scripts/")):
            return token
    raise AssertionError(f"smoke command has no documented entry point anchor: {command}")


def test_provider_configuration_index_is_generated_from_catalog() -> None:
    assert _provider_config_block() == render_provider_configuration_index_markdown()


def test_provider_configuration_index_covers_catalog_profiles_and_evidence_levels() -> None:
    rows = {str(row["provider"]): row for row in provider_configuration_index()}
    catalog = {entry.name: entry.create().profile() for entry in PROVIDER_CATALOG}

    assert tuple(rows) == tuple(catalog)
    assert rows["mock"]["evidence_level"] == "fixture-tested"
    assert rows["genie"]["evidence_level"] == "scaffold"
    assert rows["genie"]["capabilities"] == "scaffold"
    assert rows["genie"]["smoke_command"] == ""

    for name, row in rows.items():
        profile = catalog[name]
        assert row["implementation_status"] == profile.implementation_status
        assert row["required_env_vars"] == tuple(profile.required_env_vars)
        assert Path(ROOT, str(row["docs_path"])).exists()
        if name not in {"mock", "genie"}:
            assert row["evidence_level"] == "prepared-host"
            assert row["smoke_command"]


def test_provider_configuration_index_env_vars_are_documented_in_env_example() -> None:
    env_names = _env_example_names()

    for row in provider_configuration_index():
        documented_env = set(row["required_env_vars"]) | set(row["optional_env_vars"])
        assert documented_env <= env_names, row["provider"]


def test_provider_configuration_index_matches_runtime_manifest_smoke_docs() -> None:
    rows = {str(row["provider"]): row for row in provider_configuration_index()}

    for manifest in load_runtime_manifests():
        if manifest.provider not in rows:
            continue
        row = rows[manifest.provider]
        docs_text = (ROOT / manifest.docs_path).read_text(encoding="utf-8")
        assert row["optional_env_vars"] == manifest.optional_env_vars
        assert row["optional_dependencies"] == manifest.optional_dependencies
        assert row["prepared_host_assets"] == manifest.host_owned_artifacts
        assert row["smoke_command"] == manifest.minimum_smoke_command
        assert _smoke_command_anchor(manifest.minimum_smoke_command) in docs_text
