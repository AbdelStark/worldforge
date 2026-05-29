from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from worldforge.providers import CosmosProvider
from worldforge.providers.base import ProviderError

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name: str) -> dict[str, object]:
    return json.loads((ROOT / "tests" / "fixtures" / "providers" / name).read_text())


@pytest.mark.parametrize(
    ("fixture_name", "match"),
    [
        ("cosmos_generate_failed_task.json", "generation task failed: model rejected prompt"),
        ("cosmos_generate_unsupported_artifact.json", "returned artifact references"),
        ("cosmos_generate_missing_video.json", "field 'b64_video'"),
    ],
)
def test_cosmos_provider_rejects_remote_media_artifact_contract_failures(
    fixture_name: str,
    match: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/infer":
            return httpx.Response(200, json=_fixture(fixture_name))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = CosmosProvider(
        base_url="http://cosmos.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError, match=match):
        provider.generate("drive through the city", duration_seconds=2.0)
