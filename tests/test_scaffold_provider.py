from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
