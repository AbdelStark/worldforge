"""Tests for M1 dual-routing on WorldForge capability methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from worldforge import ProviderBenchmarkHarness, WorldForge, WorldForgeError
from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    EmbeddingResult,
    JSONDict,
    ProviderEvent,
)
from worldforge.providers.base import PredictionPayload, ProviderError, ProviderProfileSpec

# --- Fixture impls covering each protocol -------------------------------------------------------


class _FakeCost:
    name = "fake_cost"
    profile = ProviderProfileSpec(description="fake")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        return ActionScoreResult(provider=self.name, scores=[0.25], best_index=0)


class _FakeUtilityCost:
    name = "fake_utility_cost"
    profile = ProviderProfileSpec(description="fake utility")

    def __init__(self, *, scores: list[float] | None = None) -> None:
        self._scores = scores or [0.2, 0.9]

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        return ActionScoreResult(
            provider=self.name,
            scores=list(self._scores),
            best_index=1,
            lower_is_better=False,
        )


class _FakePolicy:
    name = "fake_policy"
    profile = None

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        return ActionPolicyResult(
            provider=self.name,
            actions=[Action(kind="noop", parameters={})],
        )


class _FakeCandidatePolicy:
    name = "fake_candidate_policy"
    profile = None

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        candidates = [
            [Action(kind="noop", parameters={"candidate": 0})],
            [Action(kind="noop", parameters={"candidate": 1})],
        ]
        return ActionPolicyResult(
            provider=self.name,
            actions=list(candidates[0]),
            action_candidates=candidates,
        )


class _FakePredictor:
    name = "fake_predictor"
    profile = ProviderProfileSpec(description="fake predictor")

    def predict(
        self,
        world_state: JSONDict,
        action: Action,
        steps: int,
    ) -> PredictionPayload:
        state = dict(world_state)
        state["step"] = int(state.get("step", 0)) + steps
        state.setdefault("metadata", {})["last_action"] = action.to_dict()
        return PredictionPayload(
            state=state,
            confidence=0.9,
            physics_score=0.8,
            frames=[b"frame"],
            metadata={"provider": self.name},
            latency_ms=0.1,
        )


class _FakeEmbedder:
    name = "fake_embedder"
    profile = None

    def embed(self, *, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            provider=self.name,
            model="fake",
            vector=[1.0, 0.0, 0.0],
        )


class _FakeHybrid:
    name = "fake_hybrid"
    profile = ProviderProfileSpec(description="fake hybrid")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        return ActionScoreResult(provider=self.name, scores=[0.5], best_index=0)

    def embed(self, *, text: str) -> EmbeddingResult:
        return EmbeddingResult(provider=self.name, model="fake", vector=[1.0, 0.0])


# --- Helpers ------------------------------------------------------------------------------------


def _isolated_forge(tmp_path: Path) -> WorldForge:
    return WorldForge(state_dir=str(tmp_path / "state"))


# --- Tests --------------------------------------------------------------------------------------


def test_score_actions_accepts_registered_name(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_FakeCost())
    result = forge.score_actions("fake_cost", info={}, action_candidates=[])
    assert result.provider == "fake_cost"


def test_score_actions_accepts_typed_kwarg(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_FakeCost())
    result = forge.score_actions(cost="fake_cost", info={}, action_candidates=[])
    assert result.provider == "fake_cost"


def test_score_actions_accepts_direct_instance(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    direct = _FakeCost()
    result = forge.score_actions(cost=direct, info={}, action_candidates=[])
    assert result.provider == "fake_cost"


def test_select_actions_accepts_both_forms(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_policy(_FakePolicy())
    via_name = forge.select_actions(policy="fake_policy", info={})
    via_instance = forge.select_actions(policy=_FakePolicy(), info={})
    assert via_name.provider == "fake_policy"
    assert via_instance.provider == "fake_policy"


def test_embed_accepts_both_forms(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_embedder(_FakeEmbedder())
    via_name = forge.embed(embedder="fake_embedder", text="abc")
    via_instance = forge.embed(embedder=_FakeEmbedder(), text="abc")
    assert via_name.vector == [1.0, 0.0, 0.0]
    assert via_instance.vector == [1.0, 0.0, 0.0]


def test_predict_accepts_both_forms(tmp_path: Path):
    """forge.predict() routes to a Predictor capability, new or legacy."""

    forge = _isolated_forge(tmp_path)
    forge.register_predictor(_FakePredictor())
    payload = forge.predict(
        world_state={"objects": []},
        action=Action(kind="noop", parameters={}),
        steps=2,
        predictor="fake_predictor",
    )
    direct_payload = forge.predict(
        world_state={"objects": []},
        action=Action(kind="noop", parameters={}),
        steps=2,
        predictor=_FakePredictor(),
    )
    assert payload.metadata["provider"] == "fake_predictor"
    assert payload.state["step"] == 2
    assert direct_payload.state["step"] == 2

    # Legacy: use mock provider via positional name
    payload_legacy = forge.predict(
        world_state={"objects": []},
        action=Action(kind="noop", parameters={}),
        steps=1,
        provider="mock",
    )
    assert payload_legacy.confidence >= 0.0


def test_world_predict_and_plan_use_registered_protocols(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_predictor(_FakePredictor())
    forge.register_policy(_FakePolicy())
    forge.register_cost(_FakeCost())

    world = forge.create_world("protocol-world", "fake_predictor")
    prediction = world.predict(Action(kind="noop", parameters={}), steps=2)
    assert prediction.provider == "fake_predictor"
    assert prediction.world_state["step"] == 2

    plan = world.plan(
        goal="hold position",
        policy_provider="fake_policy",
        policy_info={"mode": "test"},
        score_provider="fake_cost",
        score_info={"goal": "hold"},
    )
    assert plan.metadata["planning_mode"] == "policy+score"
    assert plan.metadata["policy_provider"] == "fake_policy"
    assert plan.metadata["score_provider"] == "fake_cost"


def test_score_planning_uses_direction_aware_success_probability(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_FakeUtilityCost())
    world = forge.create_world("utility-world", "mock")
    candidates = [
        [Action(kind="noop", parameters={"candidate": 0})],
        [Action(kind="noop", parameters={"candidate": 1})],
    ]

    plan = world.plan(
        goal="choose the highest utility action",
        provider="fake_utility_cost",
        candidate_actions=candidates,
        score_info={"objective": "maximize utility"},
    )

    assert plan.actions == candidates[1]
    assert plan.success_probability == 0.9
    assert plan.metadata["score_result"]["lower_is_better"] is False
    assert plan.metadata["success_probability_source"] == "bounded_best_utility_heuristic"
    trace_steps = plan.metadata["workflow_trace"]["steps"]
    assert [step["status"] for step in trace_steps] == ["success", "skipped", "success"]
    assert trace_steps[1]["error_summary"].startswith("Policy provider not requested")


def test_policy_planning_defaults_to_world_provider(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_policy(_FakePolicy())
    world = forge.create_world("policy-default-world", "fake_policy")

    plan = world.plan(goal="hold position", policy_info={"mode": "default-provider"})

    assert plan.provider == "fake_policy"
    assert plan.metadata["planning_mode"] == "policy"
    assert plan.metadata["policy_provider"] == "fake_policy"
    assert plan.actions == [Action(kind="noop", parameters={})]
    trace_steps = plan.metadata["workflow_trace"]["steps"]
    assert [step["status"] for step in trace_steps] == ["success", "success", "skipped"]
    assert trace_steps[2]["error_summary"].startswith("Score provider not requested")


def test_score_planning_uses_public_candidate_validation(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_FakeUtilityCost())
    world = forge.create_world("invalid-candidate-world", "mock")

    with pytest.raises(WorldForgeError, match=r"candidate_actions\[0\]"):
        world.plan(
            goal="reject empty candidate action plans",
            provider="fake_utility_cost",
            candidate_actions=[[]],
            score_info={"objective": "maximize utility"},
        )


def test_score_planning_does_not_invent_probability_for_unbounded_utility(
    tmp_path: Path,
):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_FakeUtilityCost(scores=[2.0, 10.0]))
    world = forge.create_world("utility-world", "mock")

    plan = world.plan(
        goal="choose the highest utility action",
        provider="fake_utility_cost",
        candidate_actions=[
            [Action(kind="noop", parameters={"candidate": 0})],
            [Action(kind="noop", parameters={"candidate": 1})],
        ],
        score_info={"objective": "maximize utility"},
    )

    assert plan.success_probability == 0.5
    assert plan.metadata["success_probability_source"] == "unbounded_best_utility_no_probability"


def test_policy_score_planning_uses_direction_aware_success_probability(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_policy(_FakeCandidatePolicy())
    forge.register_cost(_FakeUtilityCost())
    world = forge.create_world("utility-policy-world", "mock")

    plan = world.plan(
        goal="choose the best policy candidate",
        policy_provider="fake_candidate_policy",
        policy_info={"mode": "test"},
        score_provider="fake_utility_cost",
        score_info={"objective": "maximize utility"},
    )

    assert plan.metadata["planning_mode"] == "policy+score"
    assert plan.actions == [Action(kind="noop", parameters={"candidate": 1})]
    assert plan.success_probability == 0.9
    assert plan.metadata["success_probability_source"] == "bounded_best_utility_heuristic"


def test_policy_planning_rejects_host_supplied_candidates(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_policy(_FakePolicy())
    world = forge.create_world("policy-candidate-world", "mock")

    with pytest.raises(WorldForgeError, match="do not pass candidate_actions"):
        world.plan(
            goal="policy owns candidate generation",
            policy_provider="fake_policy",
            policy_info={"mode": "test"},
            candidate_actions=[Action(kind="noop", parameters={})],
        )


def test_capability_legacy_string_falls_back_to_provider_registry(tmp_path: Path):
    """A string that names only a legacy provider still resolves through the legacy path."""

    forge = _isolated_forge(tmp_path)
    # 'mock' is a legacy BaseProvider auto-registered via the catalog.
    result = forge.embed("mock", text="legacy path")
    assert result.provider == "mock"


def test_capability_unknown_name_raises(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    with pytest.raises(ProviderError):
        forge.score_actions("does_not_exist", info={}, action_candidates=[])


def test_capability_kind_mismatch_on_instance_raises(tmp_path: Path):
    """Passing a Cost instance where a Policy is expected must not silently succeed."""

    forge = _isolated_forge(tmp_path)
    with pytest.raises(WorldForgeError):
        forge.select_actions(policy=_FakeCost(), info={})  # type: ignore[arg-type]


def test_registered_protocols_are_visible_to_diagnostics_and_benchmark(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register_cost(_FakeCost())

    assert "fake_cost" in forge.providers()
    assert forge.provider_info("fake_cost").capabilities.score is True
    assert forge.provider_profile("fake_cost").description == "fake"
    assert forge.provider_health("fake_cost").healthy is True
    assert [health.name for health in forge.provider_healths(capability="score")] == ["fake_cost"]

    report = forge.doctor(capability="score", registered_only=True)
    assert [status.profile.name for status in report.providers] == ["fake_cost"]
    assert report.providers[0].registered is True

    benchmark = ProviderBenchmarkHarness(forge=forge).run("fake_cost", iterations=1)
    assert [(result.provider, result.operation) for result in benchmark.results] == [
        ("fake_cost", "score")
    ]
    assert benchmark.results[0].success_count == 1


def test_multi_protocol_registration_merges_provider_health(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    forge.register(_FakeHybrid())

    profile = forge.provider_profile("fake_hybrid")
    assert profile.capabilities.score is True
    assert profile.capabilities.embed is True

    health = forge.provider_health("fake_hybrid")
    assert health.name == "fake_hybrid"
    assert health.healthy is True
    assert health.details == "configured"

    report = forge.doctor(registered_only=True)
    statuses = {status.profile.name: status for status in report.providers}
    assert statuses["fake_hybrid"].health.details == "configured"
    assert statuses["fake_hybrid"].lifecycle.status == "no-op"
    assert len(statuses["fake_hybrid"].lifecycle.evidence["components"]) == 2


def test_event_handler_observes_new_registration(tmp_path: Path):
    events: list[ProviderEvent] = []
    forge = WorldForge(state_dir=str(tmp_path / "state"), event_handler=events.append)
    forge.register_cost(_FakeCost())
    initial = len(events)
    forge.score_actions(cost="fake_cost", info={}, action_candidates=[])
    new_events = events[initial:]
    score_events = [e for e in new_events if e.operation == "score"]
    assert any(e.phase == "success" and e.provider == "fake_cost" for e in score_events)


def test_register_then_dispatch_via_register_method(tmp_path: Path):
    """forge.register(impl) without a typed shortcut also makes it dispatch-resolvable."""

    forge = _isolated_forge(tmp_path)
    forge.register(_FakeCost())
    result = forge.score_actions(cost="fake_cost", info={}, action_candidates=[])
    assert result.provider == "fake_cost"


def test_no_target_raises(tmp_path: Path):
    forge = _isolated_forge(tmp_path)
    with pytest.raises(WorldForgeError):
        forge.score_actions(info={}, action_candidates=[])
