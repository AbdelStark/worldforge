"""Stdlib reference service host for embedding WorldForge."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from worldforge import Action, BBox, Position, SceneObject, WorldForge, WorldForgeError
from worldforge.models import DoctorReport, ProviderHealth
from worldforge.observability import JsonLoggerSink
from worldforge.providers import ProviderError

JSON = dict[str, Any]
BodyReader = Callable[[], JSON]
DEFAULT_PROVIDER = os.environ.get("WORLDFORGE_SERVICE_PROVIDER", "mock")
DEFAULT_STATE_DIR = os.environ.get("WORLDFORGE_SERVICE_STATE_DIR", ".worldforge/service-worlds")
DEFAULT_HOST = os.environ.get("WORLDFORGE_SERVICE_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("WORLDFORGE_SERVICE_PORT", "8080"))


@dataclass(slots=True, frozen=True)
class ServiceConfig:
    """Runtime settings owned by the embedding service host."""

    provider: str = DEFAULT_PROVIDER
    state_dir: Path = Path(DEFAULT_STATE_DIR)


GetRoute = Callable[[WorldForge, ServiceConfig, str], JSON]
PostRoute = Callable[[WorldForge, ServiceConfig, str, JSON], JSON]


class WorldForgeServiceHandler(BaseHTTPRequestHandler):
    """HTTP boundary for the stdlib reference service host."""

    server_version = "WorldForgeServiceHost/0.1"
    config: ClassVar[ServiceConfig] = ServiceConfig()

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def log_message(self, format: str, *args: object) -> None:
        logging.getLogger("worldforge.service_host").info(format, *args)

    def _dispatch(self, method: str) -> None:
        request_id = self.headers.get("x-request-id") or uuid4().hex
        forge = _build_forge(self.config, request_id)
        try:
            payload = _route_request(
                method,
                self.path,
                forge,
                self.config,
                request_id,
                self._read_json_body,
            )
            self._send_json(payload, request_id=request_id)
        except (WorldForgeError, ProviderError) as exc:
            self._send_json(
                public_error_payload(
                    exc,
                    request_id=request_id,
                    status=HTTPStatus.BAD_REQUEST,
                ),
                request_id=request_id,
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:  # pragma: no cover - defensive service boundary
            logging.getLogger("worldforge.service_host").exception("request failed")
            self._send_json(
                public_error_payload(
                    exc,
                    request_id=request_id,
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                ),
                request_id=request_id,
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _read_json_body(self) -> JSON:
        length_header = self.headers.get("content-length", "0")
        try:
            length = int(length_header)
        except ValueError as exc:
            raise WorldForgeError("content-length must be an integer") from exc
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorldForgeError("request body must be a JSON object") from exc
        if not isinstance(payload, dict):
            raise WorldForgeError("request body must be a JSON object")
        return payload

    def _send_json(
        self,
        payload: JSON,
        *,
        request_id: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.send_header("x-request-id", request_id)
        self.end_headers()
        self.wfile.write(body)


def readiness_snapshot(forge: WorldForge, provider: str) -> JSON:
    """Map WorldForge diagnostics to a host-facing readiness payload."""

    doctor = forge.doctor(registered_only=True)
    configured = provider in forge.providers()
    health = forge.provider_health(provider) if configured else None
    provider_healthy = bool(health and health.healthy)
    readiness = _readiness_state(
        provider_configured=configured,
        provider_healthy=provider_healthy,
    )
    checks: JSON = {
        "framework_alive": True,
        "provider": provider,
        "provider_configured": configured,
        "provider_healthy": provider_healthy,
    }
    if health is not None:
        checks["provider_health"] = health.to_dict()
    else:
        checks["provider_health"] = {
            "name": provider,
            "healthy": False,
            "latency_ms": 0.0,
            "details": "provider is not registered in this host process",
        }
    return {
        "status": readiness,
        "checks": checks,
        "traffic": "accept" if readiness == "ready" else "drain",
        "doctor": _doctor_summary(doctor),
    }


def provider_list_payload(forge: WorldForge) -> JSON:
    """Return provider diagnostics suitable for a service readiness page."""

    report = forge.doctor(registered_only=True)
    return {
        "providers": [provider.to_dict() for provider in report.providers],
        "summary": _doctor_summary(report),
    }


def prediction_payload(
    forge: WorldForge,
    payload: JSON,
    *,
    provider: str,
    request_id: str,
) -> JSON:
    """Run one deterministic, non-mutating prediction workflow for service smoke checks."""

    world_id = str(payload.get("world_id", "service-smoke"))
    world = forge.create_world(world_id, provider=provider)
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )
    target = payload.get("target")
    if isinstance(target, dict):
        x = target.get("x", 0.2)
        y = target.get("y", 0.5)
        z = target.get("z", 0.0)
    else:
        x, y, z = 0.2, 0.5, 0.0
    prediction = world.predict(Action.move_to(x, y, z), steps=1, provider=provider)
    return {
        "request_id": request_id,
        "provider": prediction.provider,
        "confidence": prediction.confidence,
        "physics_score": prediction.physics_score,
        "world": {
            "id": world.id,
            "object_count": world.object_count,
            "step": world.step,
        },
    }


def public_error_payload(exc: Exception, *, request_id: str, status: int) -> JSON:
    """Convert internal exceptions to a typed public error without leaking internals."""

    if isinstance(exc, ProviderError):
        error_type = "provider_error"
    elif isinstance(exc, WorldForgeError):
        error_type = "validation_error"
    else:
        error_type = "internal_error"
    message = str(exc) if error_type != "internal_error" else "request failed"
    message = ProviderHealth(
        name="service-error",
        healthy=False,
        latency_ms=0.0,
        details=message,
    ).details
    return {
        "error": {
            "type": error_type,
            "message": message,
            "status": status,
            "request_id": request_id,
        }
    }


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    config: ServiceConfig | None = None,
) -> ThreadingHTTPServer:
    """Create the reference HTTP server without starting its serve loop."""

    resolved = config or ServiceConfig()
    handler = _handler_factory(resolved)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def run(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    config: ServiceConfig | None = None,
) -> None:
    """Run the reference service until interrupted."""

    server = create_server(host, port, config=config)
    with server:
        print(f"WorldForge service host listening on http://{host}:{server.server_port}")
        server.serve_forever()


def _doctor_summary(report: DoctorReport) -> JSON:
    return {
        "provider_count": report.provider_count,
        "registered_provider_count": report.registered_provider_count,
        "healthy_provider_count": report.healthy_provider_count,
        "issue_count": len(report.issues),
        "issues": list(report.issues),
    }


def _readiness_state(*, provider_configured: bool, provider_healthy: bool) -> str:
    if not provider_configured:
        return "provider_unconfigured"
    if not provider_healthy:
        return "provider_unhealthy"
    return "ready"


def _build_forge(config: ServiceConfig, request_id: str) -> WorldForge:
    return WorldForge(
        state_dir=config.state_dir,
        event_handler=JsonLoggerSink(extra_fields={"request_id": request_id, "host": "service"}),
    )


def _route_request(
    method: str,
    path: str,
    forge: WorldForge,
    config: ServiceConfig,
    request_id: str,
    read_json_body: BodyReader,
) -> JSON:
    if method == "GET":
        return _route_get(path, forge, config, request_id)
    if method == "POST":
        return _route_post(path, forge, config, request_id, read_json_body)
    raise WorldForgeError(f"Unknown route: {method} {path}")


def _route_get(path: str, forge: WorldForge, config: ServiceConfig, request_id: str) -> JSON:
    handler = _GET_ROUTES.get(path)
    if handler is None:
        raise WorldForgeError(f"Unknown route: GET {path}")
    return handler(forge, config, request_id)


def _route_post(
    path: str,
    forge: WorldForge,
    config: ServiceConfig,
    request_id: str,
    read_json_body: BodyReader,
) -> JSON:
    handler = _POST_ROUTES.get(path)
    if handler is None:
        raise WorldForgeError(f"Unknown route: POST {path}")
    return handler(forge, config, request_id, read_json_body())


def _healthz_payload(_forge: WorldForge, _config: ServiceConfig, request_id: str) -> JSON:
    return {"status": "live", "request_id": request_id}


def _readyz_payload(forge: WorldForge, config: ServiceConfig, request_id: str) -> JSON:
    return {"request_id": request_id, **readiness_snapshot(forge, config.provider)}


def _providers_payload(forge: WorldForge, _config: ServiceConfig, request_id: str) -> JSON:
    return {"request_id": request_id, **provider_list_payload(forge)}


def _mock_predict_workflow_payload(
    forge: WorldForge,
    config: ServiceConfig,
    request_id: str,
    body: JSON,
) -> JSON:
    provider = str(body.get("provider") or config.provider)
    return prediction_payload(forge, body, provider=provider, request_id=request_id)


def _predict_workflow_payload(
    forge: WorldForge,
    config: ServiceConfig,
    request_id: str,
    body: JSON,
) -> JSON:
    provider = str(body.get("provider") or config.provider)
    return prediction_payload(forge, body, provider=provider, request_id=request_id)


_GET_ROUTES: dict[str, GetRoute] = {
    "/healthz": _healthz_payload,
    "/readyz": _readyz_payload,
    "/providers": _providers_payload,
}

_POST_ROUTES: dict[str, PostRoute] = {
    "/workflows/mock-predict": _mock_predict_workflow_payload,
    "/workflows/predict": _predict_workflow_payload,
}


def _handler_factory(config: ServiceConfig) -> type[BaseHTTPRequestHandler]:
    return type(
        "ConfiguredWorldForgeServiceHandler",
        (WorldForgeServiceHandler,),
        {"__module__": __name__, "config": config},
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--state-dir", type=Path, default=Path(DEFAULT_STATE_DIR))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run(
        host=args.host,
        port=args.port,
        config=ServiceConfig(provider=args.provider, state_dir=args.state_dir),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
