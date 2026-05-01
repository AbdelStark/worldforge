from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from worldforge.smoke import cosmos_policy


def _policy_info() -> dict[str, object]:
    return {
        "observation": {
            "primary_image": [[[[0, 0, 0]]]],
            "left_wrist_image": [[[[1, 1, 1]]]],
            "right_wrist_image": [[[[2, 2, 2]]]],
            "proprio": [0.0 for _ in range(14)],
        },
        "task_description": "move the cube",
        "action_horizon": 1,
    }


def test_cosmos_policy_smoke_writes_sanitized_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("COSMOS_POLICY_API_TOKEN", "cosmos-policy-secret")
    policy_path = tmp_path / "policy_info.json"
    policy_path.write_text(json.dumps(_policy_info()), encoding="utf-8")
    translator_path = tmp_path / "translator.py"
    translator_path.write_text(
        "from worldforge import Action\n"
        "def translate_actions(raw_actions, info, provider_info):\n"
        "    return [Action.move_to(0.1, 0.2, 0.3)]\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "runs" / "cosmos-policy-live" / "run_manifest.json"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/act"
        assert request.headers["authorization"] == "Bearer cosmos-policy-secret"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["task_description"] == "move the cube"
        return httpx.Response(
            200,
            json={
                "actions": [[0.1 for _ in range(14)]],
                "value_prediction": 0.75,
            },
        )

    class StubCosmosPolicyProvider(cosmos_policy.CosmosPolicyProvider):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cosmos_policy, "CosmosPolicyProvider", StubCosmosPolicyProvider)

    assert (
        cosmos_policy.main(
            [
                "--base-url",
                "http://cosmos-policy.test",
                "--policy-info-json",
                str(policy_path),
                "--translator",
                f"{translator_path}:translate_actions",
                "--run-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exported = json.dumps(manifest, sort_keys=True)
    assert manifest["provider_profile"] == "cosmos-policy"
    assert manifest["capability"] == "policy"
    assert manifest["status"] == "passed"
    assert manifest["event_count"] == 1
    assert "cosmos-policy-secret" not in exported


def test_cosmos_policy_smoke_health_only_skips_policy_request(tmp_path: Path) -> None:
    manifest_path = tmp_path / "runs" / "cosmos-policy-health" / "run_manifest.json"

    assert (
        cosmos_policy.main(
            [
                "--base-url",
                "http://cosmos-policy.test",
                "--health-only",
                "--run-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider_profile"] == "cosmos-policy"
    assert manifest["status"] == "skipped"
    assert manifest["event_count"] == 0


def test_cosmos_policy_smoke_requires_explicit_base_url(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_POLICY_BASE_URL", raising=False)

    with pytest.raises(SystemExit, match="COSMOS_POLICY_BASE_URL"):
        cosmos_policy.main(["--health-only"])


def test_cosmos_policy_smoke_rejects_invalid_timeout_env(monkeypatch) -> None:
    monkeypatch.setenv("COSMOS_POLICY_TIMEOUT_SECONDS", "not-a-number")

    with pytest.raises(SystemExit, match="COSMOS_POLICY_TIMEOUT_SECONDS"):
        cosmos_policy.main(["--base-url", "http://cosmos-policy.test", "--health-only"])
