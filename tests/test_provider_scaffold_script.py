from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scaffold_provider.py"


def test_scaffold_provider_script_generates_safe_adapter_files(tmp_path: Path) -> None:
    result = subprocess.run(
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
            "--planned-capability",
            "generate",
            "--planned-capability",
            "policy",
            "--remote",
            "--env-var",
            "ACME_WM_API_KEY",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    provider_path = tmp_path / "src" / "worldforge" / "providers" / "acme_wm.py"
    test_path = tmp_path / "tests" / "test_acme_wm_provider.py"
    success_fixture = tmp_path / "tests" / "fixtures" / "providers" / "acme_wm_success.json"
    error_fixture = tmp_path / "tests" / "fixtures" / "providers" / "acme_wm_error.json"
    runtime_manifest_stub = (
        tmp_path / "src" / "worldforge" / "providers" / "runtime_manifests" / "acme-wm.json.stub"
    )
    docs_path = tmp_path / "docs" / "src" / "providers" / "acme-wm.md"
    workbench_path = tmp_path / "docs" / "src" / "providers" / "acme-wm-workbench.md"

    assert "Generated provider scaffold for Acme WM" in result.stdout
    assert "Next validation commands:" in result.stdout
    assert "uv run worldforge provider workbench acme-wm --format markdown" in result.stdout
    assert provider_path.exists()
    assert test_path.exists()
    assert success_fixture.exists()
    assert error_fixture.exists()
    assert runtime_manifest_stub.exists()
    assert not runtime_manifest_stub.with_suffix("").exists()
    assert docs_path.exists()
    assert workbench_path.exists()

    provider_source = provider_path.read_text(encoding="utf-8")
    assert "class AcmeWMProvider(BaseProvider)" in provider_source
    assert "from .base import BaseProvider, ProviderError, ProviderProfileSpec" in provider_source
    assert "capabilities=ProviderCapabilities(predict=False)" in provider_source
    assert "profile=ProviderProfileSpec(" in provider_source
    assert "planned_capabilities = ('score', 'generate', 'policy')" in provider_source
    assert "scaffold_implementation_status = 'scaffold'" in provider_source
    assert "implementation_status='scaffold'" in provider_source
    assert 'ACME_WM_ENV_VAR = "ACME_WM_API_KEY"' in provider_source
    assert "healthy=False" in provider_source
    assert "no runtime adapter implemented" in provider_source

    test_source = test_path.read_text(encoding="utf-8")
    assert "capability_calls_fail_closed_until_promoted" in test_source
    assert "profile.capabilities.supports(capability) is False" in test_source
    assert "score_actions_is_not_implemented_yet" in test_source
    assert "generate_is_not_implemented_yet" in test_source
    assert "select_actions_is_not_implemented_yet" in test_source
    assert "profile.supported_tasks == []" in test_source

    fixture_payload = json.loads(success_fixture.read_text(encoding="utf-8"))
    assert fixture_payload["fixture_status"] == "placeholder"
    assert fixture_payload["usable_as_evidence"] is False
    assert fixture_payload["replace_before_promotion"] is True

    manifest_payload = json.loads(runtime_manifest_stub.read_text(encoding="utf-8"))
    assert manifest_payload["stub_status"] == "incomplete"
    assert manifest_payload["usable_as_evidence"] is False
    assert manifest_payload["implementation_status"] == "scaffold"
    assert manifest_payload["required_env_vars"] == ["ACME_WM_API_KEY"]
    assert "rename" in manifest_payload["_instructions"].lower()

    docs_source = docs_path.read_text(encoding="utf-8")
    assert "Taxonomy category: JEPA latent predictive world model" in docs_source
    assert "not executable until the promotion criteria pass" in docs_source
    assert "acme-wm.json.stub" in docs_source
    assert "`score` implemented, advertised, and tested" in docs_source
    assert "`policy` implemented, advertised, and tested" in docs_source

    workbench_source = workbench_path.read_text(encoding="utf-8")
    assert "Provider Workbench Checklist" in workbench_source
    assert "uv run pytest tests/test_acme_wm_provider.py" in workbench_source
    assert "uv run pytest tests/test_provider_runtime_manifests.py" in workbench_source

    py_compile.compile(str(provider_path), doraise=True)
    py_compile.compile(str(test_path), doraise=True)


def test_scaffold_provider_script_refuses_to_overwrite_files(tmp_path: Path) -> None:
    command = [
        sys.executable,
        str(SCRIPT),
        "Acme WM",
        "--root",
        str(tmp_path),
        "--implementation-status",
        "scaffold",
        "--planned-capability",
        "score",
    ]

    subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=False, capture_output=True, text=True)

    assert second.returncode == 2
    assert "refusing to overwrite existing scaffold files" in second.stderr
