"""Tests for the M0 capability-protocol scaffolding."""

from __future__ import annotations

from pathlib import Path

import pytest

from worldforge import (
    Cost,
    Embedder,
    Generator,
    Planner,
    Policy,
    Predictor,
    Reasoner,
    RunnableModel,
    Transferer,
    WorldForge,
    WorldForgeError,
)
from worldforge.capabilities import CAPABILITY_FIELD_NAMES, CAPABILITY_PROTOCOLS
from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    GenerationOptions,
    JSONDict,
    ProviderEvent,
    VideoClip,
)
from worldforge.providers.base import ProviderError, ProviderProfileSpec
from worldforge.providers.mock import MockProvider
from worldforge.providers.observable import _ObservableCapability

# --- Fixtures: minimal capability impls ---------------------------------------------------------


class _PureCost:
    name = "pure_cost"
    profile = ProviderProfileSpec(description="pure cost")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        return ActionScoreResult(
            provider=self.name,
            scores=[0.5],
            best_index=0,
            metadata={"info": dict(info)},
        )


class _PurePolicy:
    name = "pure_policy"
    profile = None

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        return ActionPolicyResult(
            provider=self.name,
            actions=[Action(kind="noop", parameters={})],
            metadata={"info": dict(info)},
        )


class _PureGenerator:
    name = "pure_gen"
    profile = None

    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        return VideoClip(
            provider=self.name,
            prompt=prompt,
            duration_seconds=duration_seconds,
            width=64,
            height=64,
            fps=4.0,
            frames=[b"\x00\x01"],
            metadata={"src": "pure-gen"},
        )


class _MultiCapability:
    """Implements both Cost and Policy structurally."""

    name = "multi"
    profile = None

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        return ActionScoreResult(provider=self.name, scores=[1.0], best_index=0)

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        return ActionPolicyResult(
            provider=self.name,
            actions=[Action(kind="noop", parameters={})],
        )


class _NoCapability:
    name = "nope"
    profile = None


# --- Tests --------------------------------------------------------------------------------------


def test_capability_protocols_are_runtime_checkable():
    assert isinstance(_PureCost(), Cost)
    assert isinstance(_PurePolicy(), Policy)
    assert isinstance(_PureGenerator(), Generator)
    assert not isinstance(_PureCost(), Policy)
    assert not isinstance(_PurePolicy(), Cost)
    assert not isinstance(_NoCapability(), Cost)


def test_capability_protocol_names_match_field_names():
    assert set(CAPABILITY_PROTOCOLS) == set(CAPABILITY_FIELD_NAMES)
    assert CAPABILITY_PROTOCOLS["cost"] is Cost
    assert CAPABILITY_PROTOCOLS["policy"] is Policy
    assert CAPABILITY_PROTOCOLS["generator"] is Generator
    assert CAPABILITY_PROTOCOLS["predictor"] is Predictor
    assert CAPABILITY_PROTOCOLS["reasoner"] is Reasoner
    assert CAPABILITY_PROTOCOLS["embedder"] is Embedder
    assert CAPABILITY_PROTOCOLS["transferer"] is Transferer
    assert CAPABILITY_PROTOCOLS["planner"] is Planner


def test_runnable_model_capability_fields_iterates_only_set_fields():
    bundle = RunnableModel(name="bundle", cost=_PureCost(), policy=_PurePolicy())
    fields = dict(bundle.capability_fields())
    assert set(fields) == {"cost", "policy"}
    assert fields["cost"].name == "pure_cost"
    assert fields["policy"].name == "pure_policy"


def test_runnable_model_capability_fields_yields_in_canonical_order():
    bundle = RunnableModel(
        name="bundle",
        generator=_PureGenerator(),
        cost=_PureCost(),
        policy=_PurePolicy(),
    )
    ordered = [field for field, _ in bundle.capability_fields()]
    # Canonical order: policy, cost, generator, predictor, reasoner, embedder, transferer, planner.
    assert ordered == ["policy", "cost", "generator"]


def test_observable_capability_emits_success_event(tmp_path: Path):
    events: list[ProviderEvent] = []
    wrapped = _ObservableCapability(_PureCost(), kind="cost", event_handler=events.append)
    result = wrapped.call(info={"k": 1}, action_candidates=[[Action(kind="noop", parameters={})]])
    assert isinstance(result, ActionScoreResult)
    assert len(events) == 1
    event = events[0]
    assert event.provider == "pure_cost"
    assert event.operation == "score"
    assert event.phase == "success"
    assert event.duration_ms is not None
    assert event.duration_ms >= 0


def test_observable_capability_emits_failure_event_on_exception():
    class _Boom:
        name = "boom"
        profile = None

        def score_actions(self, *, info, action_candidates):
            raise RuntimeError("boom")

    events: list[ProviderEvent] = []
    wrapped = _ObservableCapability(_Boom(), kind="cost", event_handler=events.append)
    with pytest.raises(ProviderError, match="Provider 'boom' score failed: boom"):
        wrapped.call(info={}, action_candidates=[])
    assert len(events) == 1
    assert events[0].phase == "failure"
    assert "Provider 'boom' score failed: boom" in events[0].message


def test_observable_capability_rejects_invalid_return_contract():
    class _BadCost:
        name = "bad_cost"
        profile = None

        def score_actions(self, *, info, action_candidates):
            return {"scores": [1.0]}

    events: list[ProviderEvent] = []
    wrapped = _ObservableCapability(_BadCost(), kind="cost", event_handler=events.append)

    with pytest.raises(ProviderError, match="expected ActionScoreResult"):
        wrapped.call(info={}, action_candidates=[])

    assert len(events) == 1
    assert events[0].phase == "failure"
    assert "expected ActionScoreResult" in events[0].message


def test_observable_capability_synthesizes_diagnostics_surfaces():
    wrapped = _ObservableCapability(_PureCost(), kind="cost")
    info = wrapped.info()
    assert info.name == "pure_cost"
    assert info.capabilities.score is True
    assert info.capabilities.policy is False
    profile = wrapped.profile()
    assert profile.description == "pure cost"
    health = wrapped.health()
    assert health.healthy is True


def test_observable_capability_rejects_unknown_kind():
    with pytest.raises(WorldForgeError):
        _ObservableCapability(_PureCost(), kind="bogus")


def test_observable_capability_rejects_missing_method():
    with pytest.raises(WorldForgeError):
        _ObservableCapability(_PureCost(), kind="policy")


def _isolated_forge(tmp_path: Path) -> WorldForge:
    return WorldForge(state_dir=str(tmp_path / "state"))


def test_register_dispatches_by_protocol_membership(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register(_MultiCapability())
    assert "multi" in forge._capability_registries["cost"]
    assert "multi" in forge._capability_registries["policy"]
    # Other registries untouched.
    assert "multi" not in forge._capability_registries["generator"]


def test_register_base_provider_uses_legacy_provider_registry(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register(MockProvider(name="legacy-mock"))
    assert "legacy-mock" in forge.providers()
    assert all("legacy-mock" not in registry for registry in forge._capability_registries.values())


def test_register_unpacks_runnable_model(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    bundle = RunnableModel(
        name="bundle",
        cost=_PureCost(),
        policy=_PurePolicy(),
        generator=_PureGenerator(),
    )
    forge.register(bundle)
    assert "pure_cost" in forge._capability_registries["cost"]
    assert "pure_policy" in forge._capability_registries["policy"]
    assert "pure_gen" in forge._capability_registries["generator"]


def test_register_typed_shortcut_validates_protocol(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_PureCost())
    with pytest.raises(WorldForgeError):
        forge.register_cost(_PurePolicy())  # type: ignore[arg-type]


def test_register_rejects_non_capability_objects(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    with pytest.raises(WorldForgeError):
        forge.register(_NoCapability())


def test_register_rejects_duplicate_name_in_same_capability(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_PureCost())
    with pytest.raises(WorldForgeError):
        forge.register_cost(_PureCost())


def test_register_allows_same_name_in_different_capabilities(tmp_path: Path):
    forge = _isolated_forge(tmp_path)

    class _SameNameCost:
        name = "shared"
        profile = None

        def score_actions(self, *, info, action_candidates):
            return ActionScoreResult(provider="shared", scores=[0.0], best_index=0)

    class _SameNamePolicy:
        name = "shared"
        profile = None

        def select_actions(self, *, info):
            return ActionPolicyResult(
                provider="shared",
                actions=[Action(kind="noop", parameters={})],
            )

    forge.register_cost(_SameNameCost())
    forge.register_policy(_SameNamePolicy())
    assert "shared" in forge._capability_registries["cost"]
    assert "shared" in forge._capability_registries["policy"]


def test_register_propagates_event_handler(tmp_path: Path):
    events: list[ProviderEvent] = []
    forge = WorldForge(state_dir=str(tmp_path / "state"), event_handler=events.append)
    forge.register_cost(_PureCost())
    wrapped = forge._capability_registries["cost"]["pure_cost"]
    wrapped.call(info={}, action_candidates=[])
    assert len(events) == 1
    assert events[0].operation == "score"


def test_register_rejects_nameless_impl(tmp_path: Path):
    forge = _isolated_forge(tmp_path)

    class _NamelessCost:
        name = ""
        profile = None

        def score_actions(self, *, info, action_candidates):
            return ActionScoreResult(provider="x", scores=[0.0], best_index=0)

    with pytest.raises(WorldForgeError):
        forge.register_cost(_NamelessCost())
