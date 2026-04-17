from __future__ import annotations

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
            "--planned-capability",
            "score",
            "--planned-capability",
            "generate",
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
    docs_path = tmp_path / "docs" / "src" / "providers" / "acme-wm.md"

    assert "Generated provider scaffold for Acme WM" in result.stdout
    assert provider_path.exists()
    assert test_path.exists()
    assert success_fixture.exists()
    assert error_fixture.exists()
    assert docs_path.exists()

    provider_source = provider_path.read_text(encoding="utf-8")
    assert "class AcmeWMProvider(BaseProvider)" in provider_source
    assert "capabilities=ProviderCapabilities()" in provider_source
    assert "planned_capabilities = ('score', 'generate')" in provider_source
    assert 'ACME_WM_ENV_VAR = "ACME_WM_API_KEY"' in provider_source

    test_source = test_path.read_text(encoding="utf-8")
    assert "score_actions_is_not_implemented_yet" in test_source
    assert "generate_is_not_implemented_yet" in test_source

    docs_source = docs_path.read_text(encoding="utf-8")
    assert "Taxonomy category: JEPA latent predictive world model" in docs_source
    assert "`score` implemented, advertised, and tested" in docs_source

    py_compile.compile(str(provider_path), doraise=True)
    py_compile.compile(str(test_path), doraise=True)


def test_scaffold_provider_script_refuses_to_overwrite_files(tmp_path: Path) -> None:
    command = [
        sys.executable,
        str(SCRIPT),
        "Acme WM",
        "--root",
        str(tmp_path),
        "--planned-capability",
        "score",
    ]

    subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, capture_output=True, text=True)

    assert second.returncode == 2
    assert "refusing to overwrite existing scaffold files" in second.stderr
