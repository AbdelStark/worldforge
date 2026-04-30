from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from worldforge import WorldForge, WorldForgeError

ROOT = Path(__file__).resolve().parents[1]
SERVICE_APP = ROOT / "examples" / "hosts" / "service" / "app.py"


def _load_service_app():
    import importlib.util

    spec = importlib.util.spec_from_file_location("worldforge_service_host_example", SERVICE_APP)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def service_app():
    return _load_service_app()


def _request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={"content-type": "application/json", "x-request-id": "request-123"},
    )
    with urlopen(request, timeout=5) as response:
        return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))


def test_service_host_readiness_maps_provider_state(tmp_path, service_app) -> None:
    forge = WorldForge(state_dir=tmp_path)

    ready = service_app.readiness_snapshot(forge, "mock")
    assert ready["status"] == "ready"
    assert ready["checks"]["framework_alive"] is True
    assert ready["checks"]["provider_configured"] is True
    assert ready["checks"]["provider_healthy"] is True
    assert ready["doctor"]["registered_provider_count"] >= 1

    degraded = service_app.readiness_snapshot(forge, "missing-provider")
    assert degraded["status"] == "degraded"
    assert degraded["checks"]["provider_configured"] is False
    assert degraded["checks"]["provider_healthy"] is False


def test_service_host_endpoints_exercise_reference_workflows(tmp_path, service_app) -> None:
    server = service_app.create_server(
        "127.0.0.1",
        0,
        config=service_app.ServiceConfig(provider="mock", state_dir=tmp_path),
    )
    with server:
        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
        )
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        status, headers, health = _request_json(f"{base_url}/healthz")
        assert status == 200
        assert headers["x-request-id"] == "request-123"
        assert health == {"request_id": "request-123", "status": "live"}

        _status, _headers, ready = _request_json(f"{base_url}/readyz")
        assert ready["status"] == "ready"
        assert ready["checks"]["provider"] == "mock"

        _status, _headers, providers = _request_json(f"{base_url}/providers")
        assert "mock" in {provider["name"] for provider in providers["providers"]}

        _status, _headers, prediction = _request_json(
            f"{base_url}/workflows/mock-predict",
            method="POST",
            payload={},
        )
        assert prediction["provider"] == "mock"
        assert prediction["confidence"] > 0

        _status, _headers, generated = _request_json(
            f"{base_url}/workflows/generate",
            method="POST",
            payload={"provider": "mock", "prompt": "service smoke", "duration_seconds": 0.25},
        )
        assert generated["provider"] == "mock"
        assert generated["frame_count"] >= 1

        server.shutdown()
        thread.join(timeout=5)


def test_service_host_errors_are_public_and_redacted(service_app) -> None:
    payload = service_app.public_error_payload(
        WorldForgeError("token=super-secret-value failed"),
        request_id="request-123",
        status=400,
    )

    assert payload["error"]["type"] == "validation_error"
    assert payload["error"]["request_id"] == "request-123"
    assert "super-secret-value" not in payload["error"]["message"]


def test_service_host_unknown_route_returns_typed_error(tmp_path, service_app) -> None:
    server = service_app.create_server(
        "127.0.0.1",
        0,
        config=service_app.ServiceConfig(provider="mock", state_dir=tmp_path),
    )
    with server:
        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
        )
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        with pytest.raises(HTTPError) as exc_info:
            _request_json(f"{base_url}/missing")
        body = json.loads(exc_info.value.read().decode("utf-8"))
        assert exc_info.value.code == 400
        assert body["error"]["type"] == "validation_error"
        assert body["error"]["request_id"] == "request-123"

        server.shutdown()
        thread.join(timeout=5)
