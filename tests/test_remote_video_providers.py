from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from worldforge import GenerationOptions, ProviderEvent, ProviderRequestPolicy, VideoClip
from worldforge.models import JSONDict, WorldForgeError
from worldforge.providers import CosmosProvider, ProviderError, RunwayProvider
from worldforge.providers import http_utils as http_utils_module
from worldforge.providers import runway as runway_module
from worldforge.providers.http_utils import request_bytes_with_policy, validate_remote_url
from worldforge.testing import assert_provider_contract

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "providers"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_cosmos_provider_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/health/ready":
            return httpx.Response(200, json=_fixture("cosmos_health_ready.json"))
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(200, json=_fixture("cosmos_generate_success.json"))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(handler),
    )

    report = assert_provider_contract(provider)

    assert report.configured is True
    assert report.exercised_operations == ["generate"]
    assert set(provider.profile().capabilities.enabled_names()) == {"generate"}


def test_cosmos_provider_contract_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)

    report = assert_provider_contract(CosmosProvider())

    assert report.configured is False
    assert report.exercised_operations == []


def test_runway_provider_contract(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    generated_bytes = b"runway-generated"
    transferred_bytes = b"runway-transferred"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/organization":
            return httpx.Response(200, json={"id": "org_test"})
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json={"id": "task_generate"})
        if request.method == "POST" and request.url.path == "/v1/video_to_video":
            return httpx.Response(200, json={"id": "task_transfer"})
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(
                200,
                json={
                    "id": "task_generate",
                    "createdAt": "2026-04-07T00:00:00Z",
                    "status": "SUCCEEDED",
                    "output": ["https://downloads.example.com/generated.mp4"],
                },
            )
        if request.method == "GET" and request.url.path == "/v1/tasks/task_transfer":
            return httpx.Response(
                200,
                json={
                    "id": "task_transfer",
                    "createdAt": "2026-04-07T00:00:00Z",
                    "status": "SUCCEEDED",
                    "output": ["https://downloads.example.com/transferred.mp4"],
                },
            )
        if request.method == "GET" and request.url.host == "downloads.example.com":
            if request.url.path.endswith("generated.mp4"):
                return httpx.Response(200, content=generated_bytes)
            if request.url.path.endswith("transferred.mp4"):
                return httpx.Response(200, content=transferred_bytes)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    report = assert_provider_contract(provider)

    assert report.configured is True
    assert set(report.exercised_operations) == {"generate", "transfer"}
    assert set(provider.profile().capabilities.enabled_names()) == {"generate", "transfer"}


def test_runway_provider_contract_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_SECRET", raising=False)

    report = assert_provider_contract(RunwayProvider())

    assert report.configured is False
    assert report.exercised_operations == []


def test_cosmos_provider_health_and_generate() -> None:
    video_bytes = b"cosmos-video"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/health/ready":
            return httpx.Response(200, json=_fixture("cosmos_health_ready.json"))

        if request.method == "POST" and request.url.path == "/v1/infer":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["prompt"] == "drive through the city"
            assert payload["image"] == "https://example.com/seed.png"
            assert payload["video_params"]["width"] == 1280
            assert payload["video_params"]["height"] == 720
            assert payload["video_params"]["frames_count"] == 48
            return httpx.Response(
                200,
                json=_fixture("cosmos_generate_success.json"),
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(handler),
    )

    health = provider.health()
    assert health.healthy is True

    clip = provider.generate(
        "drive through the city",
        duration_seconds=2.0,
        options=GenerationOptions(
            image="https://example.com/seed.png",
            fps=24.0,
            seed=7,
        ),
    )
    assert clip.blob() == video_bytes
    assert clip.metadata["mode"] == "image2world"
    assert clip.metadata["content_type"] == "video/mp4"
    assert clip.metadata["upsampled_prompt"] == "drive through the city, cinematic detail"


def test_cosmos_provider_reports_malformed_health_fixture() -> None:
    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_fixture("cosmos_health_malformed.json"))
        ),
    )

    health = provider.health()

    assert health.healthy is False
    assert "healthcheck response field 'status'" in health.details


def test_runway_provider_health_generate_and_transfer(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    generated_bytes = b"runway-generated"
    transferred_bytes = b"runway-transferred"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/organization":
            return httpx.Response(200, json={"id": "org_test"})

        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["model"] == "gen4.5"
            assert payload["promptText"] == "a rainy alley at night"
            assert payload["duration"] == 4
            return httpx.Response(200, json={"id": "task_generate"})

        if request.method == "POST" and request.url.path == "/v1/video_to_video":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["model"] == "gen4_aleph"
            assert payload["promptText"] == "make it look cinematic"
            assert payload["videoUri"].startswith("data:video/mp4;base64,")
            assert payload["references"] == [{"uri": "https://example.com/style.png"}]
            return httpx.Response(200, json={"id": "task_transfer"})

        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(
                200,
                json={
                    "id": "task_generate",
                    "createdAt": "2026-04-07T00:00:00Z",
                    "status": "SUCCEEDED",
                    "output": ["https://downloads.example.com/generated.mp4"],
                },
            )

        if request.method == "GET" and request.url.path == "/v1/tasks/task_transfer":
            return httpx.Response(
                200,
                json={
                    "id": "task_transfer",
                    "createdAt": "2026-04-07T00:00:00Z",
                    "status": "SUCCEEDED",
                    "output": ["https://downloads.example.com/transferred.mp4"],
                },
            )

        if request.method == "GET" and request.url.host == "downloads.example.com":
            if request.url.path.endswith("generated.mp4"):
                return httpx.Response(200, content=generated_bytes)
            if request.url.path.endswith("transferred.mp4"):
                return httpx.Response(200, content=transferred_bytes)

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    assert provider.health().healthy is True

    generated = provider.generate(
        "a rainy alley at night",
        duration_seconds=4.0,
        options=GenerationOptions(fps=24.0),
    )
    assert generated.blob() == generated_bytes
    assert generated.metadata["mode"] == "text_to_video"

    transferred = provider.transfer(
        generated,
        width=1280,
        height=720,
        fps=24.0,
        prompt="make it look cinematic",
        options=GenerationOptions(reference_images=["https://example.com/style.png"]),
    )
    assert transferred.blob() == transferred_bytes
    assert transferred.metadata["mode"] == "video_to_video"


def test_cosmos_provider_rejects_invalid_asset_paths_and_payloads(tmp_path) -> None:
    missing_image = tmp_path / "missing.png"

    provider = CosmosProvider(base_url="http://cosmos.test")

    with pytest.raises(ProviderError, match="does not exist"):
        provider.generate(
            "drive through the city",
            duration_seconds=2.0,
            options=GenerationOptions(image=str(missing_image)),
        )

    def invalid_payload_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(200, json={"b64_video": "not-base64!"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(invalid_payload_handler),
    )

    with pytest.raises(ProviderError, match="invalid base64 video payload"):
        provider.generate("drive through the city", duration_seconds=2.0)


def test_cosmos_provider_rejects_malformed_response_fixtures() -> None:
    def missing_video_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(200, json=_fixture("cosmos_generate_missing_video.json"))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(missing_video_handler),
    )
    with pytest.raises(ProviderError, match="field 'b64_video'"):
        provider.generate("drive through the city", duration_seconds=2.0)

    def bad_seed_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(200, json=_fixture("cosmos_generate_bad_seed.json"))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(bad_seed_handler),
    )
    with pytest.raises(ProviderError, match="field 'seed'"):
        provider.generate("drive through the city", duration_seconds=2.0)

    def failed_task_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(200, json=_fixture("cosmos_generate_failed_task.json"))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(failed_task_handler),
    )
    with pytest.raises(ProviderError, match="generation task failed: model rejected prompt"):
        provider.generate("drive through the city", duration_seconds=2.0)

    def unsupported_artifact_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(200, json=_fixture("cosmos_generate_unsupported_artifact.json"))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(unsupported_artifact_handler),
    )
    with pytest.raises(ProviderError, match="returned artifact references"):
        provider.generate("drive through the city", duration_seconds=2.0)

    provider = CosmosProvider(base_url="http://cosmos.test")
    with pytest.raises(ProviderError, match="multiples of 8"):
        provider.generate(
            "drive through the city",
            duration_seconds=2.0,
            options=GenerationOptions(size="641x360"),
        )


def test_cosmos_provider_retries_transient_health_failure() -> None:
    attempts = {"health": 0}
    events: list[ProviderEvent] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/health/ready":
            attempts["health"] += 1
            if attempts["health"] == 1:
                return httpx.Response(503, text="warming up")
            return httpx.Response(200, json={"status": "ready"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        request_policy=ProviderRequestPolicy.remote_defaults(
            request_timeout_seconds=30.0,
            read_retry_attempts=2,
            read_backoff_seconds=0.0,
        ),
        event_handler=events.append,
        transport=httpx.MockTransport(handler),
    )

    health = provider.health()
    assert health.healthy is True
    assert attempts["health"] == 2
    assert [(event.operation, event.phase) for event in events] == [
        ("healthcheck", "retry"),
        ("healthcheck", "success"),
    ]


def test_cosmos_provider_events_cover_auth_failures_and_timeouts() -> None:
    auth_events: list[ProviderEvent] = []

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        event_handler=auth_events.append,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                text='{"message":"bad token","api_key":"secret-token"}',
            )
        ),
    )

    with pytest.raises(ProviderError, match="generation request failed with status 401"):
        provider.generate("drive through the city", duration_seconds=2.0)

    assert [(event.operation, event.phase, event.status_code) for event in auth_events] == [
        ("generation request", "failure", 401)
    ]
    assert "secret-token" not in json.dumps([event.to_dict() for event in auth_events])

    timeout_events: list[ProviderEvent] = []

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("cosmos timed out", request=request)

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        event_handler=timeout_events.append,
        transport=httpx.MockTransport(timeout_handler),
    )

    with pytest.raises(ProviderError, match="failed after 1 attempt"):
        provider.generate("drive through the city", duration_seconds=2.0)

    assert [(event.operation, event.phase) for event in timeout_events] == [
        ("generation request", "failure")
    ]
    assert timeout_events[0].method == "POST"
    assert timeout_events[0].target == "/v1/infer"


def test_runway_provider_rejects_invalid_runtime_inputs(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    provider = RunwayProvider(
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    with pytest.raises(WorldForgeError, match="duration_seconds"):
        provider.generate("a rainy alley at night", duration_seconds=0.0)

    with pytest.raises(WorldForgeError, match="width"):
        provider.transfer(
            clip=_sample_clip(),
            width=0,
            height=720,
            fps=24.0,
        )

    with pytest.raises(WorldForgeError, match="fps"):
        provider.transfer(
            clip=_sample_clip(),
            width=1280,
            height=720,
            fps=0.0,
        )


def test_runway_provider_retries_polling_and_download_reads(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    attempts = {"poll": 0, "download": 0}
    generated_bytes = b"retry-generated"
    events: list[ProviderEvent] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json={"id": "task_generate"})

        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            attempts["poll"] += 1
            if attempts["poll"] == 1:
                return httpx.Response(503, text="retry poll")
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
            if attempts["download"] == 1:
                return httpx.Response(503, text="retry download")
            return httpx.Response(200, content=generated_bytes)

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

    generated = provider.generate(
        "a rainy alley at night",
        duration_seconds=4.0,
        options=GenerationOptions(fps=24.0),
    )
    assert generated.blob() == generated_bytes
    assert generated.metadata["artifact_url"] == "https://downloads.example.com/generated.mp4"
    assert "output_url" not in generated.metadata
    assert attempts["poll"] == 2
    assert attempts["download"] == 2
    assert [(event.operation, event.phase) for event in events] == [
        ("generation request", "success"),
        ("task poll", "retry"),
        ("task poll", "success"),
        ("artifact download", "retry"),
        ("artifact download", "success"),
    ]
    download_targets = [event.target for event in events if event.operation == "artifact download"]
    assert download_targets == [
        "https://downloads.example.com/generated.mp4",
        "https://downloads.example.com/generated.mp4",
    ]
    assert "download-secret" not in json.dumps([event.to_dict() for event in events])
    assert "download-secret" not in json.dumps(generated.metadata)


def test_runway_provider_sanitizes_signed_artifact_metadata(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAY_API_SECRET", "legacy-runway-test-key")
    generated_bytes = b"signed-url-generated"

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
                        "?X-Amz-Signature=download-secret#fragment"
                    ],
                },
            )
        if request.method == "GET" and request.url.host == "downloads.example.com":
            return httpx.Response(200, content=generated_bytes)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    generated = provider.generate("a rainy alley at night", duration_seconds=4.0)

    assert generated.blob() == generated_bytes
    assert generated.metadata["artifact_url"] == "https://downloads.example.com/generated.mp4"
    exported = json.dumps(generated.to_dict())
    assert "download-secret" not in exported
    assert "X-Amz-Signature" not in exported


def test_runway_provider_does_not_retry_generation_post(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    attempts = {"post": 0}
    events: list[ProviderEvent] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            attempts["post"] += 1
            return httpx.Response(503, text='{"api_key":"post-secret","message":"busy"}')
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        request_policy=ProviderRequestPolicy.remote_defaults(
            request_timeout_seconds=30.0,
            read_retry_attempts=3,
            read_backoff_seconds=0.0,
        ),
        event_handler=events.append,
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    with pytest.raises(ProviderError, match="generation request failed with status 503"):
        provider.generate(
            "a rainy alley at night",
            duration_seconds=4.0,
            options=GenerationOptions(fps=24.0),
        )
    assert attempts["post"] == 1
    assert [(event.operation, event.phase, event.status_code) for event in events] == [
        ("generation request", "failure", 503)
    ]
    assert "post-secret" not in json.dumps([event.to_dict() for event in events])


def test_runway_provider_rejects_malformed_response_fixtures(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    provider = RunwayProvider(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_fixture("runway_org_malformed.json"))
        ),
        poll_interval_seconds=0.0,
        max_polls=1,
    )
    health = provider.health()
    assert health.healthy is False
    assert "must include 'id' or 'name'" in health.details

    def missing_task_id_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json=_fixture("runway_create_missing_id.json"))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(missing_task_id_handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )
    with pytest.raises(ProviderError, match="field 'id'"):
        provider.generate("a rainy alley at night", duration_seconds=4.0)


@pytest.mark.parametrize(
    ("fixture_name", "expected_error"),
    [
        ("runway_task_empty_output.json", "completed without outputs"),
        ("runway_task_partial_output.json", "contains invalid entries"),
        ("runway_task_failed.json", "moderation rejected prompt"),
    ],
)
def test_runway_provider_rejects_bad_task_fixtures(
    monkeypatch,
    fixture_name: str,
    expected_error: str,
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
    with pytest.raises(ProviderError, match=expected_error):
        provider.generate("a rainy alley at night", duration_seconds=4.0)


def test_runway_provider_rejects_expired_artifacts_and_bad_content_types(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    def expired_artifact_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json=_fixture("runway_create_success.json"))
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(200, json=_fixture("runway_task_success.json"))
        if request.method == "GET" and request.url.host == "downloads.example.com":
            return httpx.Response(403, text="artifact expired")
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(expired_artifact_handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )
    with pytest.raises(ProviderError, match="expired or unavailable"):
        provider.generate("a rainy alley at night", duration_seconds=4.0)

    def bad_content_type_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json=_fixture("runway_create_success.json"))
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(200, json=_fixture("runway_task_success.json"))
        if request.method == "GET" and request.url.host == "downloads.example.com":
            return httpx.Response(
                200,
                content=b"<html>not a video</html>",
                headers={"content-type": "text/html"},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(bad_content_type_handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )
    with pytest.raises(ProviderError, match="unsupported content type"):
        provider.generate("a rainy alley at night", duration_seconds=4.0)


@pytest.mark.parametrize(
    "artifact_url",
    [
        "http://127.0.0.1:8777/generated.mp4",
        "http://localhost:8777/generated.mp4",
        "http://169.254.169.254/latest/meta-data",
        "ftp://downloads.example.com/generated.mp4",
        "https://user:pass@downloads.example.com/generated.mp4",
    ],
)
def test_runway_provider_rejects_unsafe_artifact_urls(monkeypatch, artifact_url: str) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json=_fixture("runway_create_success.json"))
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(
                200,
                json={
                    "id": "task_generate",
                    "status": "SUCCEEDED",
                    "output": [artifact_url],
                },
            )
        raise AssertionError(f"Unexpected request after artifact validation: {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
    )

    with pytest.raises(ProviderError, match="artifact URL"):
        provider.generate("a rainy alley at night", duration_seconds=4.0)


def test_runway_provider_allows_local_artifact_urls_only_when_explicit(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    artifact_url = "http://127.0.0.1:8777/generated.mp4"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json=_fixture("runway_create_success.json"))
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(
                200,
                json={
                    "id": "task_generate",
                    "status": "SUCCEEDED",
                    "output": [artifact_url],
                },
            )
        if request.method == "GET" and request.url.host == "127.0.0.1":
            return httpx.Response(200, content=b"local-artifact")
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
        allow_local_artifact_urls=True,
    )

    generated = provider.generate("a rainy alley at night", duration_seconds=4.0)

    assert generated.blob() == b"local-artifact"


def test_runway_provider_rejects_artifacts_over_size_limit(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json=_fixture("runway_create_success.json"))
        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            return httpx.Response(
                200,
                json={
                    "id": "task_generate",
                    "status": "SUCCEEDED",
                    "output": ["https://downloads.example.com/generated.mp4"],
                },
            )
        if request.method == "GET" and request.url.host == "downloads.example.com":
            return httpx.Response(
                200,
                content=b"too-large",
                headers={"content-length": "9", "content-type": "video/mp4"},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = RunwayProvider(
        transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.0,
        max_polls=1,
        max_artifact_bytes=8,
    )

    with pytest.raises(ProviderError, match="download size limit"):
        provider.generate("a rainy alley at night", duration_seconds=4.0)


@pytest.mark.parametrize(
    ("resolve_artifact_dns", "expected_resolve_dns"),
    (
        (None, False),
        (True, True),
        (False, False),
    ),
)
def test_runway_provider_artifact_dns_policy_with_custom_transport(
    monkeypatch,
    resolve_artifact_dns: bool | None,
    expected_resolve_dns: bool,
) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    artifact_url = "https://downloads.example.com/generated.mp4"
    resolve_dns_values: list[bool] = []

    class CustomTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path == "/v1/image_to_video":
                return httpx.Response(200, json=_fixture("runway_create_success.json"))
            if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
                return httpx.Response(
                    200,
                    json={
                        "id": "task_generate",
                        "status": "SUCCEEDED",
                        "output": [artifact_url],
                    },
                )
            if request.method == "GET" and request.url.host == "downloads.example.com":
                return httpx.Response(
                    200,
                    content=b"artifact",
                    headers={"content-type": "video/mp4"},
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    def capture_validate_remote_url(
        url: str,
        *,
        provider_name: str,
        url_name: str,
        allow_local_network: bool = False,
        resolve_dns: bool = True,
        dns_resolution_timeout_seconds: float = 2.0,
    ) -> str:
        del provider_name, url_name, allow_local_network, dns_resolution_timeout_seconds
        resolve_dns_values.append(resolve_dns)
        return url

    monkeypatch.setattr(runway_module, "validate_remote_url", capture_validate_remote_url)
    kwargs = {}
    if resolve_artifact_dns is not None:
        kwargs["resolve_artifact_dns"] = resolve_artifact_dns

    provider = RunwayProvider(
        transport=CustomTransport(),
        poll_interval_seconds=0.0,
        max_polls=1,
        **kwargs,
    )

    generated = provider.generate("a rainy alley at night", duration_seconds=4.0)

    assert generated.blob() == b"artifact"
    assert resolve_dns_values == [expected_resolve_dns]


def test_runway_config_summary_reports_effective_artifact_dns_policy(monkeypatch) -> None:
    monkeypatch.delenv("RUNWAYML_RESOLVE_ARTIFACT_DNS", raising=False)
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    def artifact_dns_detail(provider: RunwayProvider) -> str:
        summary: JSONDict = provider.config_summary().to_dict()
        field = next(
            item for item in summary["fields"] if item["name"] == "RUNWAYML_RESOLVE_ARTIFACT_DNS"
        )
        return str(field["detail"])

    assert artifact_dns_detail(RunwayProvider()) == "auto; effective resolve_dns=true"
    assert (
        artifact_dns_detail(
            RunwayProvider(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
        )
        == "auto; effective resolve_dns=false"
    )
    assert (
        artifact_dns_detail(RunwayProvider(resolve_artifact_dns=False))
        == "effective resolve_dns=false"
    )


def test_request_bytes_with_policy_caps_streamed_body_without_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(b"abcdef"))

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderError, match="download size limit"),
    ):
        request_bytes_with_policy(
            client,
            method="GET",
            url="https://downloads.example.com/generated.mp4",
            provider_name="runway",
            operation_name="artifact download",
            policy=ProviderRequestPolicy.remote_defaults(
                request_timeout_seconds=30.0,
                read_retry_attempts=1,
            ).download,
            max_bytes=5,
        )


def test_request_bytes_with_policy_closes_retry_stream_before_backoff(monkeypatch) -> None:
    events: list[str] = []
    attempts = 0

    class ObservedRetryStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"retry later"

        def close(self) -> None:
            events.append("closed")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, stream=ObservedRetryStream())
        return httpx.Response(200, content=b"ok")

    def record_sleep(delay: float) -> None:
        del delay
        events.append("sleep")

    monkeypatch.setattr(http_utils_module, "sleep", record_sleep)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data = request_bytes_with_policy(
            client,
            method="GET",
            url="https://downloads.example.com/generated.mp4",
            provider_name="runway",
            operation_name="artifact download",
            policy=ProviderRequestPolicy.remote_defaults(
                request_timeout_seconds=30.0,
                read_retry_attempts=2,
            ).download,
        )

    assert data == b"ok"
    assert attempts == 2
    assert events == ["closed", "sleep"]


def test_validate_remote_url_allows_public_https_without_dns_resolution() -> None:
    assert (
        validate_remote_url(
            "https://downloads.example.com/generated.mp4?signature=temporary",
            provider_name="runway",
            url_name="artifact URL",
            resolve_dns=False,
        )
        == "https://downloads.example.com/generated.mp4?signature=temporary"
    )


def test_validate_remote_url_wraps_dns_worker_failures(monkeypatch) -> None:
    def fail_resolution(*_args: object, **_kwargs: object) -> list[str]:
        raise RuntimeError("resolver worker failed")

    monkeypatch.setattr(http_utils_module, "_getaddrinfo_with_timeout", fail_resolution)

    with pytest.raises(ProviderError, match="host resolution failed"):
        validate_remote_url(
            "https://downloads.example.com/generated.mp4",
            provider_name="runway",
            url_name="artifact URL",
        )


def test_getaddrinfo_uses_bounded_result_queue_timeout(monkeypatch) -> None:
    class CompletedProcess:
        exitcode = 0

        def start(self) -> None:
            pass

        def join(self, _timeout: float | None = None) -> None:
            pass

        def is_alive(self) -> bool:
            return False

        def terminate(self) -> None:
            raise AssertionError("completed process should not be terminated")

    class ResultQueue:
        timeout_seen: float | None = None

        def get(self, *, timeout: float) -> tuple[str, list[str]]:
            self.timeout_seen = timeout
            return ("ok", ["93.184.216.34"])

        def close(self) -> None:
            pass

        def join_thread(self) -> None:
            pass

    class CompletedContext:
        def __init__(self) -> None:
            self.queue = ResultQueue()

        def Queue(self, *args: object, **kwargs: object) -> ResultQueue:
            del args, kwargs
            return self.queue

        def Process(self, *args: object, **kwargs: object) -> CompletedProcess:
            del args, kwargs
            return CompletedProcess()

    context = CompletedContext()

    def fake_get_context(_method: str) -> CompletedContext:
        return context

    monkeypatch.setattr(http_utils_module.multiprocessing, "get_context", fake_get_context)

    assert http_utils_module._getaddrinfo_with_timeout(
        "downloads.example.com",
        443,
        timeout_seconds=2.0,
    ) == ["93.184.216.34"]
    assert context.queue.timeout_seen is not None
    assert context.queue.timeout_seen >= 1.0


def test_runway_provider_rejects_provider_specific_limits(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")

    provider = RunwayProvider(
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        poll_interval_seconds=0.0,
        max_polls=1,
    )
    with pytest.raises(ProviderError, match="Invalid Runway ratio"):
        provider.generate(
            "a rainy alley at night",
            duration_seconds=4.0,
            options=GenerationOptions(ratio="not-a-ratio"),
        )

    with pytest.raises(WorldForgeError, match="Runway max_polls"):
        RunwayProvider(max_polls=0)


def _sample_clip() -> VideoClip:
    return VideoClip(
        frames=[b"video"],
        fps=24.0,
        resolution=(1280, 720),
        duration_seconds=1.0,
        metadata={"content_type": "video/mp4"},
    )
