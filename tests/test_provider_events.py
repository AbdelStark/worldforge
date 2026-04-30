from __future__ import annotations

from worldforge import Action, ProviderEvent, VideoClip, WorldForge
from worldforge.providers import GenieProvider, MockProvider


def test_worldforge_event_handler_propagates_to_builtin_and_manual_providers(tmp_path) -> None:
    events: list[ProviderEvent] = []
    forge = WorldForge(
        state_dir=tmp_path,
        auto_register_remote=False,
        event_handler=events.append,
    )
    world = forge.create_world_from_prompt("empty room", provider="mock")

    world.predict(Action.move_to(0.2, 0.5, 0.0), steps=2)
    forge.generate("orbiting cube", "mock", duration_seconds=1.0)

    manual_provider = MockProvider(name="manual")
    forge.register_provider(manual_provider)
    forge.reason("manual", "where is the cube?", world=world)

    assert manual_provider.event_handler is not None
    assert [(event.provider, event.operation, event.phase) for event in events] == [
        ("mock", "predict", "success"),
        ("mock", "generate", "success"),
        ("manual", "reason", "success"),
    ]
    assert events[0].metadata["steps"] == 2


def test_stub_remote_provider_forwards_mock_events(monkeypatch) -> None:
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.setenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", "1")
    events: list[ProviderEvent] = []
    provider = GenieProvider(event_handler=events.append)

    payload = provider.predict(
        {
            "id": "world-test",
            "name": "test",
            "provider": "genie",
            "step": 0,
            "scene": {"objects": {}},
            "metadata": {},
        },
        Action.spawn_object("cube"),
        1,
    )

    assert payload.metadata["mode"] == "stub-remote-adapter"
    assert [(event.provider, event.operation, event.phase) for event in events] == [
        ("genie", "predict", "success")
    ]


def test_scaffold_surrogate_opt_in_exercises_non_predict_operations(monkeypatch) -> None:
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.setenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", "true")
    provider = GenieProvider()

    generated = provider.generate("cube replay", 1.0)
    transferred = provider.transfer(
        VideoClip(
            frames=[b"seed"],
            fps=8.0,
            resolution=(160, 90),
            duration_seconds=1.0,
        ),
        width=320,
        height=180,
        fps=12.0,
    )
    reasoning = provider.reason("how many objects?", world_state={"scene": {"objects": {}}})
    embedding = provider.embed(text="cube")

    assert generated.metadata["mode"] == "stub-remote-adapter"
    assert transferred.metadata["credential_env"] == "GENIE_API_KEY"
    assert "GENIE_API_KEY" in reasoning.evidence[-1]
    assert embedding.provider == "genie"
