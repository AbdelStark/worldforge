from __future__ import annotations

import pytest

from worldforge import Action, BBox, Position, ProviderCapabilities, SceneObject, WorldForge
from worldforge.providers import (
    BaseProvider,
    CosmosPolicyProvider,
    CosmosProvider,
    GenieProvider,
    JepaProvider,
    LeWorldModelProvider,
    MockProvider,
    ProviderError,
    RunwayProvider,
)
from worldforge.providers.base import ProviderProfileSpec


def test_provider_submodule_exports_provider_classes() -> None:
    assert CosmosPolicyProvider is not None
    assert CosmosProvider is not None
    assert GenieProvider is not None
    assert JepaProvider is not None
    assert LeWorldModelProvider is not None
    assert MockProvider is not None
    assert RunwayProvider is not None


def test_provider_capabilities_are_closed_by_default_and_unsupported_predict_is_typed(
    tmp_path,
) -> None:
    provider = BaseProvider("empty")

    assert provider.capabilities == ProviderCapabilities()
    assert provider.capabilities.enabled_names() == []

    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)
    world = forge.create_world("capability-world", "empty")

    with pytest.raises(ProviderError, match="does not implement predict"):
        world.predict(Action.move_to(0.1, 0.5, 0.0))


def test_base_provider_requires_all_profile_environment_variables(monkeypatch) -> None:
    provider = BaseProvider(
        "remote-contract",
        profile=ProviderProfileSpec(required_env_vars=("FIRST_REQUIRED", "SECOND_REQUIRED")),
    )
    monkeypatch.delenv("FIRST_REQUIRED", raising=False)
    monkeypatch.delenv("SECOND_REQUIRED", raising=False)

    assert provider.configured() is False
    assert "FIRST_REQUIRED" in provider.health().details
    assert "SECOND_REQUIRED" in provider.health().details

    monkeypatch.setenv("FIRST_REQUIRED", "set")
    assert provider.configured() is False

    monkeypatch.setenv("SECOND_REQUIRED", "set")
    assert provider.configured() is True


def test_generation_transfer_reason_embedding_and_manual_registration(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    forge.register_provider(MockProvider(name="manual-mock"))
    assert "manual-mock" in forge.providers()

    descriptor = forge.provider_info("manual-mock")
    assert descriptor.name == "manual-mock"
    assert descriptor.capabilities.predict is True

    health = forge.provider_health("mock")
    assert health.name == "mock"
    assert health.healthy is True

    clip = forge.generate("A cube rolling across a table", "mock", duration_seconds=1.0)
    assert clip.frame_count >= 1

    transferred = forge.transfer(clip, "mock", width=320, height=180, fps=12.0)
    assert transferred.resolution == (320, 180)

    world = forge.create_world("manual-world", "manual-mock")
    world.add_object(
        SceneObject(
            "red_mug",
            Position(0.0, 0.8, 0.0),
            BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
        )
    )

    prediction = world.predict(Action.move_to(0.25, 0.8, 0.0), steps=2)
    assert prediction.provider == "manual-mock"

    reasoning = forge.reason("mock", "how many objects are here?", world=world)
    assert reasoning.answer
    assert reasoning.confidence >= 0.0
    assert len(reasoning.evidence) >= 1

    embedding = forge.embed("mock", text="a mug on a kitchen counter")
    assert embedding.provider == "mock"
    assert embedding.model == "mock-embedding-v1"
    assert embedding.shape == [32]
    assert len(embedding.vector) == 32
