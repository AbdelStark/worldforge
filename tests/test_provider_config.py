from __future__ import annotations

import json

from worldforge.providers import (
    CosmosProvider,
    GrootPolicyClientProvider,
    LeRobotPolicyProvider,
    LeWorldModelProvider,
    RunwayProvider,
)
from worldforge.providers.catalog import create_known_providers
from worldforge.providers.runtime_manifest import load_runtime_manifest, load_runtime_manifests

SECRET_VALUES = (
    "cosmos-secret",
    "runway-secret",
    "gr00t-secret",
    "signed-query-secret",
    "password-secret",
)


def _assert_no_secret_values(payload: object) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    for secret in SECRET_VALUES:
        assert secret not in serialized


def test_provider_config_summaries_are_value_free_json(monkeypatch) -> None:
    monkeypatch.setenv("COSMOS_BASE_URL", "https://cosmos.example.test")
    monkeypatch.setenv("NVIDIA_API_KEY", "cosmos-secret")
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-secret")
    monkeypatch.setenv("GROOT_POLICY_HOST", "127.0.0.1")
    monkeypatch.setenv("GROOT_POLICY_API_TOKEN", "gr00t-secret")
    monkeypatch.setenv("LEROBOT_POLICY_PATH", "lerobot/checkpoint")
    monkeypatch.setenv("LEWORLDMODEL_POLICY", "pusht/lewm")

    summaries = [provider.config_summary().to_dict() for provider in create_known_providers()]

    assert {summary["provider"] for summary in summaries} == {
        "mock",
        "cosmos",
        "runway",
        "leworldmodel",
        "gr00t",
        "lerobot",
        "jepa",
        "genie",
    }
    for summary in summaries:
        assert set(summary) == {"provider", "configured", "fields"}
        for field in summary["fields"]:
            assert set(field) == {
                "name",
                "present",
                "source",
                "required",
                "secret",
                "valid",
                "detail",
                "aliases",
            }
            assert "value" not in field
    _assert_no_secret_values(summaries)


def test_provider_config_summary_reports_alias_source_without_value(monkeypatch) -> None:
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.setenv("RUNWAY_API_SECRET", "runway-secret")

    summary = RunwayProvider().config_summary().to_dict()

    api_field = summary["fields"][0]
    assert api_field["name"] == "RUNWAYML_API_SECRET"
    assert api_field["aliases"] == ["RUNWAY_API_SECRET"]
    assert api_field["present"] is True
    assert api_field["source"] == "env:RUNWAY_API_SECRET"
    assert api_field["secret"] is True
    _assert_no_secret_values(summary)


def test_direct_provider_config_summary_reports_source_not_value(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_SECRET", raising=False)
    monkeypatch.delenv("GROOT_POLICY_HOST", raising=False)
    monkeypatch.delenv("LEROBOT_POLICY_PATH", raising=False)
    monkeypatch.delenv("LEWORLDMODEL_POLICY", raising=False)

    summaries = [
        CosmosProvider(base_url="https://cosmos.example.test").config_summary().to_dict(),
        GrootPolicyClientProvider(host="127.0.0.1", api_token="gr00t-secret")
        .config_summary()
        .to_dict(),
        LeRobotPolicyProvider(policy_path="lerobot/checkpoint").config_summary().to_dict(),
        LeWorldModelProvider(policy="pusht/lewm").config_summary().to_dict(),
    ]

    for summary in summaries:
        assert summary["configured"] is True
        assert summary["fields"][0]["source"] == "direct"
    _assert_no_secret_values(summaries)


def test_runtime_manifest_config_summaries_cover_declared_env_without_values() -> None:
    env = {
        "RUNWAY_API_SECRET": "runway-secret",
        "RUNWAYML_BASE_URL": "https://api.example.test",
        "NVIDIA_API_KEY": "cosmos-secret",
    }

    runway_summary = load_runtime_manifest("runway").config_summary(environ=env).to_dict()

    assert runway_summary["configured"] is True
    assert runway_summary["fields"][0]["source"] == "env:RUNWAY_API_SECRET"
    assert runway_summary["fields"][0]["aliases"] == ["RUNWAY_API_SECRET"]
    assert runway_summary["fields"][0]["secret"] is True
    assert runway_summary["fields"][1]["name"] == "RUNWAYML_BASE_URL"
    for manifest in load_runtime_manifests():
        summary = manifest.config_summary(environ={}).to_dict()
        assert summary["provider"] == manifest.provider
        assert [field["name"] for field in summary["fields"]] == [
            manifest.required_env_vars[0],
            *manifest.optional_env_vars,
        ]
    _assert_no_secret_values(runway_summary)
