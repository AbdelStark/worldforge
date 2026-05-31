from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from worldforge.provider_scaffold import (
    DEFAULT_TAXONOMY,
    ScaffoldOptions,
    main,
    normalize_provider_name,
    parse_args,
    scaffold_files,
    write_scaffold,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scaffold_provider.py"


def _run_scaffold(tmp_path: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "Acme WM",
            "--root",
            str(tmp_path),
            "--taxonomy",
            "JEPA latent predictive world model",
            "--implementation-status",
            "scaffold",
            "--planned-capability",
            "score",
            *extra_args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_normalize_provider_name_derives_safe_identifiers() -> None:
    names = normalize_provider_name("ACME WM 2")

    assert names.display == "ACME WM 2"
    assert names.slug == "acme-wm-2"
    assert names.snake == "acme_wm_2"
    assert names.class_name == "ACMEWM2Provider"


@pytest.mark.parametrize("raw_name", ["", "123 world", "class"])
def test_normalize_provider_name_rejects_unsafe_identifiers(raw_name: str) -> None:
    with pytest.raises(ValueError):
        normalize_provider_name(raw_name)


def test_parse_args_defaults_remote_credentials_and_dedupes_capabilities(tmp_path: Path) -> None:
    options = parse_args(
        [
            "Acme WM",
            "--root",
            str(tmp_path),
            "--implementation-status",
            "scaffold",
            "--planned-capability",
            "score",
            "--planned-capability",
            "score",
            "--remote",
        ]
    )

    assert options.root == tmp_path.resolve()
    assert options.taxonomy == DEFAULT_TAXONOMY
    assert options.planned_capabilities == ("score",)
    assert options.is_local is False
    assert options.env_var == "ACME_WM_API_KEY"


def test_scaffold_files_builds_expected_contract_paths_without_writing(tmp_path: Path) -> None:
    names = normalize_provider_name("Acme WM")
    options = ScaffoldOptions(
        root=tmp_path,
        names=names,
        taxonomy="JEPA latent predictive world model",
        planned_capabilities=("score", "policy"),
        implementation_status="scaffold",
        is_local=False,
        env_var="ACME_WM_API_KEY",
        force=False,
    )

    files = scaffold_files(options)

    assert set(files) == {
        tmp_path / "src/worldforge/providers/acme_wm.py",
        tmp_path / "tests/test_acme_wm_provider.py",
        tmp_path / "tests/fixtures/providers/acme_wm_success.json",
        tmp_path / "tests/fixtures/providers/acme_wm_error.json",
        tmp_path / "src/worldforge/providers/runtime_manifests/acme-wm.json.stub",
        tmp_path / "docs/src/providers/acme-wm.md",
        tmp_path / "docs/src/providers/acme-wm-workbench.md",
    }
    assert (
        "planned_capabilities = ('score', 'policy')"
        in files[tmp_path / "src/worldforge/providers/acme_wm.py"]
    )
    assert (
        "`policy` implemented, advertised, and tested"
        in files[tmp_path / "docs/src/providers/acme-wm.md"]
    )
    assert not any(path.exists() for path in files)


def test_scaffold_rendering_reuses_shared_capability_templates() -> None:
    import worldforge.provider_scaffold_rendering as rendering
    import worldforge.provider_scaffold_templates as templates

    assert rendering._CAPABILITY_MODEL_IMPORTS is templates.CAPABILITY_MODEL_IMPORTS
    assert rendering._CAPABILITY_STUB_TEMPLATES is templates.CAPABILITY_STUB_TEMPLATES
    assert rendering._CAPABILITY_TEST_TEMPLATES is templates.CAPABILITY_TEST_TEMPLATES


def test_scaffold_files_supports_local_provider_without_required_env(tmp_path: Path) -> None:
    names = normalize_provider_name("Local WM")
    options = ScaffoldOptions(
        root=tmp_path,
        names=names,
        taxonomy="local test provider",
        planned_capabilities=("predict",),
        implementation_status="scaffold",
        is_local=True,
        env_var=None,
        force=False,
    )

    files = scaffold_files(options)
    provider_source = files[tmp_path / "src/worldforge/providers/local_wm.py"]
    docs_source = files[tmp_path / "docs/src/providers/local-wm.md"]
    generated_test_source = files[tmp_path / "tests/test_local_wm_provider.py"]

    assert "import os" not in provider_source
    assert "PredictionPayload" in provider_source
    assert "required_env_vars=()" in provider_source
    assert "return True" in provider_source
    assert "Required environment variable: none yet." in docs_source
    assert "health_reports_missing_configuration" not in generated_test_source


def test_scaffold_files_rejects_empty_capability_plan(tmp_path: Path) -> None:
    names = normalize_provider_name("Acme WM")
    options = ScaffoldOptions(
        root=tmp_path,
        names=names,
        taxonomy="JEPA latent predictive world model",
        planned_capabilities=(),
        implementation_status="scaffold",
        is_local=True,
        env_var=None,
        force=False,
    )

    with pytest.raises(ValueError, match="requires at least one planned capability"):
        scaffold_files(options)


def test_write_scaffold_refuses_overwrite_without_force(tmp_path: Path) -> None:
    options = parse_args(
        [
            "Acme WM",
            "--root",
            str(tmp_path),
            "--implementation-status",
            "scaffold",
            "--planned-capability",
            "score",
        ]
    )

    written = write_scaffold(options)

    assert tmp_path / "src/worldforge/providers/acme_wm.py" in written
    assert all(path.exists() for path in written)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_scaffold(options)


def test_main_prints_summary_and_returns_success(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "Acme WM",
            "--root",
            str(tmp_path),
            "--implementation-status",
            "scaffold",
            "--planned-capability",
            "score",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Generated provider scaffold for Acme WM" in captured.out
    assert "uv run pytest tests/test_acme_wm_provider.py" in captured.out
    assert captured.err == ""


def test_main_reports_validation_errors(capsys) -> None:
    result = main(
        [
            "123 world",
            "--implementation-status",
            "scaffold",
            "--planned-capability",
            "score",
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "provider name must start with a letter" in captured.err


def test_scaffold_provider_requires_explicit_implementation_status(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "Acme WM",
            "--root",
            str(tmp_path),
            "--planned-capability",
            "score",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--implementation-status" in result.stderr


def test_scaffold_provider_writes_full_contract_pack(tmp_path: Path) -> None:
    result = _run_scaffold(tmp_path, "--remote", "--env-var", "ACME_WM_API_KEY")

    provider_path = tmp_path / "src/worldforge/providers/acme_wm.py"
    test_path = tmp_path / "tests/test_acme_wm_provider.py"
    manifest_stub_path = tmp_path / "src/worldforge/providers/runtime_manifests/acme-wm.json.stub"
    docs_path = tmp_path / "docs/src/providers/acme-wm.md"
    workbench_path = tmp_path / "docs/src/providers/acme-wm-workbench.md"

    for path in (provider_path, test_path, manifest_stub_path, docs_path, workbench_path):
        assert path.exists(), path

    assert "uv run pytest tests/test_acme_wm_provider.py" in result.stdout
    assert "uv run mkdocs build --strict" in result.stdout
    assert "worldforge provider workbench acme-wm" in result.stdout

    provider_source = provider_path.read_text(encoding="utf-8")
    assert "planned_capabilities = ('score',)" in provider_source
    assert "implementation_status='scaffold'" in provider_source
    assert "profile=ProviderProfileSpec(" in provider_source
    assert "capabilities=ProviderCapabilities(predict=False)" in provider_source

    test_source = test_path.read_text(encoding="utf-8")
    assert "profile.capabilities.supports(capability) is False" in test_source
    assert "capability_calls_fail_closed_until_promoted" in test_source
    assert "ProviderError" in test_source

    docs_source = docs_path.read_text(encoding="utf-8")
    assert "not executable until the promotion criteria pass" in docs_source
    assert "acme-wm.json.stub" in docs_source
    assert "uv run worldforge provider workbench acme-wm --format markdown" in docs_source

    workbench_source = workbench_path.read_text(encoding="utf-8")
    assert "not evidence by\nitself" in workbench_source
    assert "Existing files are not overwritten unless `--force` is explicit" in workbench_source


def test_scaffold_provider_manifest_stub_cannot_be_loaded_as_evidence(tmp_path: Path) -> None:
    _run_scaffold(tmp_path)

    manifest_stub_path = tmp_path / "src/worldforge/providers/runtime_manifests/acme-wm.json.stub"
    manifest_path = tmp_path / "src/worldforge/providers/runtime_manifests/acme-wm.json"
    payload = json.loads(manifest_stub_path.read_text(encoding="utf-8"))

    assert manifest_stub_path.exists()
    assert not manifest_path.exists()
    assert payload["stub_status"] == "incomplete"
    assert payload["usable_as_evidence"] is False
    assert "TODO" in json.dumps(payload)
