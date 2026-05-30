from __future__ import annotations

import json
import sys
from pathlib import Path

from worldforge.demos.external_provider_package import (
    discover_external_provider_package,
    external_provider_discovery_report,
    run_external_provider_package_workflow,
    write_external_provider_package,
)


def test_external_provider_package_generation_preserves_expected_files(tmp_path: Path) -> None:
    package = write_external_provider_package(tmp_path / "external-provider-package")

    assert package.pyproject_path.is_file()
    assert package.provider_path.is_file()
    assert package.missing_path.is_file()
    assert package.generated_test.is_file()
    assert package.generated_files() == [
        "pyproject.toml",
        "src/worldforge_demo_provider/__init__.py",
        "src/worldforge_demo_provider/needs_optional.py",
        "src/worldforge_demo_provider/provider.py",
        "tests/test_demo_external_provider.py",
    ]
    assert 'demo-external = "worldforge_demo_provider.provider:create_provider"' in (
        package.pyproject_path.read_text(encoding="utf-8")
    )


def test_external_provider_discovery_reports_skips_and_cleans_import_state(
    tmp_path: Path,
) -> None:
    package = write_external_provider_package(tmp_path / "external-provider-package")
    discovery, disabled, provider = discover_external_provider_package(package.source_root)
    report = external_provider_discovery_report(
        package=package,
        discovery=discovery,
        disabled=disabled,
        provider=provider,
    )

    assert provider.name == "demo-external"
    assert report["discovery_enabled"]["discovered"][0]["name"] == "demo-external"
    assert report["discovery_disabled"]["enabled"] is False
    assert report["provider"]["capabilities"]["predict"] is True
    assert "missing dependency" in report["skip_reasons"]["needs-optional"]
    assert "duplicate name" in report["skip_reasons"]["mock"]
    assert str(package.source_root) not in sys.path
    assert not any(name.startswith("worldforge_demo_provider") for name in sys.modules)


def test_external_provider_package_workflow_writes_attachable_report(tmp_path: Path) -> None:
    result = run_external_provider_package_workflow(tmp_path)
    artifact_paths = result["artifact_paths"]
    report_path = Path(str(artifact_paths["discovery_report"]))

    assert result["status"] == "passed"
    assert result["provider"] == "demo-external"
    assert result["safe_to_attach"] is True
    assert report_path.is_file()
    assert Path(str(artifact_paths["pyproject"])).is_file()
    assert Path(str(artifact_paths["provider"])).is_file()
    assert Path(str(artifact_paths["generated_test"])).is_file()
    assert json.loads(report_path.read_text(encoding="utf-8")) == result["report"]
