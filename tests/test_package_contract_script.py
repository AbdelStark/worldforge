from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "test_package.sh"


def test_package_contract_script_installs_the_built_wheel_generically() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'wheel_paths=("$TMP_DIR"/dist/*.whl)' in script
    assert '"$TMP_DIR"/dist/worldforge-*.whl' not in script


def test_package_contract_script_checks_distribution_contents() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'uv build --out-dir "$TMP_DIR/dist" --clear --no-build-logs' in script
    assert 'scripts/check_distribution.py" "$TMP_DIR/dist"' in script
