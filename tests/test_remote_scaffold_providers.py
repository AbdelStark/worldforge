from __future__ import annotations

import json

import pytest

from worldforge.providers import GenieProvider, ProviderError
from worldforge.testing import assert_provider_contract


def test_genie_provider_remains_fail_closed_without_runtime_contract(monkeypatch) -> None:
    monkeypatch.delenv("GENIE_API_KEY", raising=False)
    monkeypatch.delenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", raising=False)

    provider = GenieProvider()
    profile = provider.profile()

    assert profile.implementation_status == "scaffold"
    assert profile.capabilities.enabled_names() == []
    assert profile.artifact_types == []
    assert provider.configured() is False
    assert provider.health().healthy is False
    assert "GENIE_API_KEY" in provider.health().details

    report = assert_provider_contract(provider)
    assert report.configured is False
    assert report.exercised_operations == []


def test_configured_genie_scaffold_does_not_enable_generate(monkeypatch) -> None:
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-secret")
    monkeypatch.delenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", raising=False)

    provider = GenieProvider()
    summary = provider.config_summary().to_dict()

    assert provider.configured() is True
    assert provider.health().healthy is True
    assert provider.profile().capabilities.enabled_names() == []
    assert "genie-test-secret" not in json.dumps(summary)

    report = assert_provider_contract(provider)
    assert report.configured is True
    assert report.exercised_operations == []

    with pytest.raises(ProviderError, match="scaffold"):
        provider.generate("make an interactive world", duration_seconds=2.0)


def test_genie_scaffold_surrogate_requires_explicit_test_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-secret")
    monkeypatch.setenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", "1")

    clip = GenieProvider().generate("local plumbing test only", duration_seconds=1.0)

    assert clip.metadata["mode"] == "stub-remote-adapter"
    assert clip.metadata["credential_env"] == "GENIE_API_KEY"
