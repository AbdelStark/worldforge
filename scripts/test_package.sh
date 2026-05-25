#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/worldforge-package.XXXXXX")"
VENV_DIR="$TMP_DIR/.venv"

cleanup() {
    rm -rf "$TMP_DIR"
}

trap cleanup EXIT

cd "$ROOT_DIR"
uv build --out-dir "$TMP_DIR/dist" --clear --no-build-logs
uv run python "$ROOT_DIR/scripts/check_distribution.py" "$TMP_DIR/dist"
uv venv "$VENV_DIR"

wheel_paths=("$TMP_DIR"/dist/*.whl)
if [ "${#wheel_paths[@]}" -ne 1 ]; then
    printf 'expected exactly one built wheel in %s/dist, found %s\n' "$TMP_DIR" "${#wheel_paths[@]}" >&2
    exit 1
fi

uv pip install --python "$VENV_DIR/bin/python" "${wheel_paths[0]}" pytest

"$VENV_DIR/bin/python" - <<'PY'
import worldforge
import worldforge.evaluation
import worldforge.providers

assert worldforge.__version__
assert worldforge.WorldForge is not None
PY

"$VENV_DIR/bin/python" -m pytest "$ROOT_DIR/tests" -q
