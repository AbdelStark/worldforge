from __future__ import annotations

import json
from pathlib import Path

import httpx

from worldforge.smoke import cosmos


def test_cosmos_smoke_writes_artifact_summary_and_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("COSMOS_BASE_URL", "http://cosmos.test")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/health/ready":
            return httpx.Response(200, json={"status": "ready"})
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(
                200,
                json={"b64_video": "Y29zbW9zLXZpZGVv", "seed": 4},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    class StubCosmosProvider(cosmos.CosmosProvider):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cosmos, "CosmosProvider", StubCosmosProvider)
    output_path = tmp_path / "artifacts" / "cosmos.mp4"
    summary_path = tmp_path / "summary.json"
    manifest_path = tmp_path / "run_manifest.json"

    assert (
        cosmos.main(
            [
                "--output",
                str(output_path),
                "--summary-json",
                str(summary_path),
                "--run-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )

    assert output_path.read_bytes() == b"cosmos-video"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["byte_count"] == len(b"cosmos-video")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider_profile"] == "cosmos"
    assert manifest["capability"] == "generate"
    assert manifest["status"] == "passed"
    assert manifest["event_count"] == 2
    assert manifest["env_summary"][0] == {
        "name": "COSMOS_BASE_URL",
        "present": True,
        "source": "env:COSMOS_BASE_URL",
        "secret": False,
    }
