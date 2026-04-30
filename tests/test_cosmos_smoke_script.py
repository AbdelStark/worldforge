from __future__ import annotations

import json
from pathlib import Path

import httpx

from worldforge.smoke import cosmos, runway


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


def test_runway_smoke_writes_sanitized_artifact_summary_and_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/organization":
            return httpx.Response(200, json={"id": "org_test"})
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json={"id": "task_generate"})
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(
                200,
                json={
                    "id": "task_generate",
                    "status": "SUCCEEDED",
                    "output": [
                        "https://downloads.example.com/generated.mp4"
                        "?X-Amz-Signature=download-secret"
                    ],
                },
            )
        if request.method == "GET" and request.url.host == "downloads.example.com":
            return httpx.Response(200, content=b"runway-video")
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    class StubRunwayProvider(runway.RunwayProvider):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            kwargs["poll_interval_seconds"] = 0.0
            kwargs["max_polls"] = 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(runway, "RunwayProvider", StubRunwayProvider)
    output_path = tmp_path / "artifacts" / "runway.mp4"
    summary_path = tmp_path / "summary.json"
    manifest_path = tmp_path / "run_manifest.json"

    assert (
        runway.main(
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

    assert output_path.read_bytes() == b"runway-video"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exported = json.dumps({"summary": summary, "manifest": manifest})
    assert summary["artifact_url"] == "https://downloads.example.com/generated.mp4"
    assert manifest["artifact_paths"]["runway_artifact_url"] == (
        "https://downloads.example.com/generated.mp4"
    )
    assert manifest["provider_profile"] == "runway"
    assert manifest["capability"] == "generate"
    assert manifest["status"] == "passed"
    assert manifest["event_count"] == 4
    assert "download-secret" not in exported
    assert "X-Amz-Signature" not in exported
