from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from worldforge import GenerationOptions, ProviderEvent, ProviderRequestPolicy
from worldforge.providers import RunwayProvider
from worldforge.providers import runway as runway_module
from worldforge.providers import runway_responses as runway_response_module
from worldforge.providers.base import ProviderError
from worldforge.providers.runway import RunwayOrganizationResponse, RunwayTaskStatusResponse
from worldforge.providers.runway_requests import build_runway_generation_request

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name: str) -> dict[str, object]:
    return json.loads((ROOT / "tests" / "fixtures" / "providers" / name).read_text())


def test_runway_provider_facade_reexports_response_parsers() -> None:
    facade = runway_module
    response_module = runway_response_module

    assert facade.RunwayOrganizationResponse is response_module.RunwayOrganizationResponse
    assert facade.RunwayTaskCreationResponse is response_module.RunwayTaskCreationResponse
    assert facade.RunwayTaskStatusResponse is response_module.RunwayTaskStatusResponse


def test_runway_generation_request_builder_normalizes_body() -> None:
    request = build_runway_generation_request(
        prompt="a studio product turntable",
        duration_seconds=4.6,
        ratio="640:480",
        options=GenerationOptions(
            model="gen4_turbo",
            fps=12.0,
            seed=7,
            extras={"watermark": False},
        ),
        default_model="gen4.5",
    )

    assert request.body == {
        "model": "gen4_turbo",
        "promptText": "a studio product turntable",
        "ratio": "640:480",
        "duration": 5,
        "seed": 7,
        "watermark": False,
    }
    assert request.duration == 5
    assert request.fps == 12.0
    assert request.resolution == (640, 480)
    assert request.mode == "text_to_video"


def test_runway_organization_response_normalizes_optional_fields() -> None:
    response = RunwayOrganizationResponse.from_payload(
        {"id": " org_test ", "name": " Test Org "},
        provider_name="runway",
    )

    assert response.organization_id == "org_test"
    assert response.name == "Test Org"
    assert response.details() == "Test Org"


def test_runway_task_status_response_normalizes_optional_fields() -> None:
    status = RunwayTaskStatusResponse.from_payload(
        {"status": " succeeded ", "output": [" https://downloads.example.com/out.mp4 "]},
        provider_name="runway",
        expected_task_id="task_generate",
    )

    assert status.task_id == "task_generate"
    assert status.status == "SUCCEEDED"
    assert status.outputs == ("https://downloads.example.com/out.mp4",)


def test_runway_task_status_response_rejects_task_id_mismatch() -> None:
    with pytest.raises(ProviderError, match="does not match requested task"):
        RunwayTaskStatusResponse.from_payload(
            {"id": "other_task", "status": "SUCCEEDED", "output": []},
            provider_name="runway",
            expected_task_id="task_generate",
        )


@pytest.mark.parametrize(
    ("fixture_name", "match"),
    [
        ("runway_task_failed.json", "failed with status FAILED: moderation rejected prompt"),
        ("runway_task_empty_output.json", "completed without outputs"),
        ("runway_task_partial_output.json", "invalid entries"),
    ],
)
def test_runway_provider_rejects_malformed_or_failed_task_outputs(
    monkeypatch: pytest.MonkeyPatch,
    fixture_name: str,
    match: str,
) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json=_fixture("runway_create_success.json"))
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(200, json=_fixture(fixture_name))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    with pytest.raises(ProviderError, match=match):
        provider.generate("a rainy alley at night", duration_seconds=4.0)


def test_runway_provider_download_retry_exhaustion_keeps_signed_url_out_of_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    events: list[ProviderEvent] = []
    attempts = {"download": 0}

    def handler(request: httpx.Request) -> httpx.Response:
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
                        "?X-Amz-Signature=download-secret&token=download-token"
                    ],
                },
            )
        if request.method == "GET" and request.url.host == "downloads.example.com":
            attempts["download"] += 1
            return httpx.Response(503, text="retry exhausted")
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        request_policy=ProviderRequestPolicy.remote_defaults(
            request_timeout_seconds=30.0,
            read_retry_attempts=2,
            read_backoff_seconds=0.0,
        ),
        event_handler=events.append,
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    with pytest.raises(ProviderError, match="artifact download failed with status 503"):
        provider.generate(
            "a rainy alley at night",
            duration_seconds=4.0,
            options=GenerationOptions(fps=24.0),
        )

    assert attempts["download"] == 2
    download_events = [event for event in events if event.operation == "artifact download"]
    assert [(event.phase, event.status_code) for event in download_events] == [
        ("retry", 503),
        ("failure", 503),
    ]
    assert [event.target for event in download_events] == [
        "https://downloads.example.com/generated.mp4",
        "https://downloads.example.com/generated.mp4",
    ]
    exported = json.dumps([event.to_dict() for event in events])
    assert "download-secret" not in exported
    assert "X-Amz-Signature" not in exported
