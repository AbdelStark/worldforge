"""Reusable provider contract helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from worldforge.models import (
    Action,
    ActionScoreResult,
    BBox,
    EmbeddingResult,
    JSONDict,
    Position,
    ProviderHealth,
    ProviderProfile,
    ReasoningResult,
    SceneObject,
    VideoClip,
)
from worldforge.providers import BaseProvider, PredictionPayload, ProviderError

T = TypeVar("T")


def sample_contract_action() -> Action:
    """Return a deterministic action for provider contract checks."""

    return Action.move_to(0.25, 0.5, 0.0, speed=1.0)


def sample_contract_world_state() -> JSONDict:
    """Return a minimal world-state payload for provider contract checks."""

    cube = SceneObject(
        "contract-cube",
        Position(0.0, 0.5, 0.0),
        BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        is_graspable=True,
    )
    return {
        "schema_version": 1,
        "id": "world_contract",
        "name": "contract-world",
        "provider": "contract",
        "description": "World state used for provider contract checks.",
        "step": 0,
        "scene": {"objects": {cube.id: cube.to_dict()}},
        "metadata": {"name": "contract-world"},
    }


@dataclass(slots=True)
class ProviderContractReport:
    """Summary of executed provider contract checks."""

    provider: str
    configured: bool
    profile: ProviderProfile
    health: ProviderHealth
    exercised_operations: list[str] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "profile": self.profile.to_dict(),
            "health": self.health.to_dict(),
            "exercised_operations": list(self.exercised_operations),
        }


def _expect_provider_error(operation_name: str, call: Callable[[], T]) -> None:
    try:
        call()
    except ProviderError:
        return
    msg = f"Provider contract expected '{operation_name}' to raise ProviderError when unavailable."
    raise AssertionError(msg)


def _validate_prediction(provider: str, payload: PredictionPayload) -> None:
    assert isinstance(payload.state, dict)
    assert isinstance(payload.metadata, dict)
    assert isinstance(payload.frames, list)
    assert all(isinstance(frame, bytes) for frame in payload.frames)
    assert isinstance(payload.confidence, float)
    assert 0.0 <= payload.confidence <= 1.0
    assert isinstance(payload.physics_score, float)
    assert 0.0 <= payload.physics_score <= 1.0
    assert payload.latency_ms >= 0.0
    assert "scene" in payload.state
    assert payload.metadata.get("provider") == provider


def _validate_reasoning(provider: str, result: ReasoningResult) -> None:
    assert result.provider == provider
    assert isinstance(result.answer, str)
    assert result.answer
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.evidence, list)


def _validate_embedding(provider: str, result: EmbeddingResult) -> None:
    assert result.provider == provider
    assert isinstance(result.model, str)
    assert result.model
    assert isinstance(result.vector, list)
    assert len(result.vector) >= 1
    assert all(isinstance(value, float) for value in result.vector)


def _validate_clip(clip: VideoClip) -> None:
    assert isinstance(clip.frames, list)
    assert all(isinstance(frame, bytes) for frame in clip.frames)
    assert clip.fps > 0.0
    assert clip.resolution[0] > 0
    assert clip.resolution[1] > 0
    assert clip.duration_seconds >= 0.0
    assert isinstance(clip.metadata, dict)


def _validate_action_scores(provider: str, result: ActionScoreResult) -> None:
    assert result.provider == provider
    assert isinstance(result.scores, list)
    assert result.scores
    assert all(isinstance(score, float) for score in result.scores)
    assert isinstance(result.best_index, int)
    assert 0 <= result.best_index < len(result.scores)
    assert result.best_score == result.scores[result.best_index]
    assert isinstance(result.lower_is_better, bool)
    assert isinstance(result.metadata, dict)


def assert_provider_contract(
    provider: BaseProvider,
    *,
    world_state: JSONDict | None = None,
    action: Action | None = None,
    score_info: JSONDict | None = None,
    score_action_candidates: object | None = None,
) -> ProviderContractReport:
    """Assert that a provider obeys the WorldForge adapter contract.

    This helper is intended for provider package tests. It validates metadata,
    health reporting, and either successful execution or clear credential errors
    for every declared capability.
    """

    profile = provider.profile()
    info = provider.info()
    health = provider.health()
    configured = provider.configured()

    assert profile.name == provider.name
    assert info.name == provider.name
    assert info.description == profile.description
    assert info.is_local == profile.is_local
    assert sorted(info.capabilities.enabled_names()) == sorted(profile.supported_tasks)
    assert health.name == provider.name
    if health.healthy:
        assert configured
    if not configured and profile.requires_credentials:
        assert health.healthy is False
    if profile.capabilities.plan:
        assert profile.capabilities.predict

    sample_state = world_state or sample_contract_world_state()
    sample_action = action or sample_contract_action()
    report = ProviderContractReport(
        provider=provider.name,
        configured=configured,
        profile=profile,
        health=health,
    )
    can_invoke = configured

    if profile.capabilities.predict:
        if can_invoke:
            prediction = provider.predict(sample_state, sample_action, 2)
            _validate_prediction(provider.name, prediction)
            report.exercised_operations.append("predict")
        else:
            _expect_provider_error(
                "predict",
                lambda: provider.predict(sample_state, sample_action, 2),
            )

    if profile.capabilities.reason:
        if can_invoke:
            reasoning = provider.reason(
                "How many objects are in the scene?", world_state=sample_state
            )
            _validate_reasoning(provider.name, reasoning)
            report.exercised_operations.append("reason")
        else:
            _expect_provider_error(
                "reason",
                lambda: provider.reason(
                    "How many objects are in the scene?",
                    world_state=sample_state,
                ),
            )

    if profile.capabilities.embed:
        if can_invoke:
            embedding = provider.embed(text="contract vector")
            _validate_embedding(provider.name, embedding)
            report.exercised_operations.append("embed")
        else:
            _expect_provider_error("embed", lambda: provider.embed(text="contract vector"))

    generated_clip: VideoClip | None = None
    if profile.capabilities.generate:
        if can_invoke:
            generated_clip = provider.generate("contract prompt", duration_seconds=1.0)
            _validate_clip(generated_clip)
            report.exercised_operations.append("generate")
        else:
            _expect_provider_error(
                "generate",
                lambda: provider.generate("contract prompt", duration_seconds=1.0),
            )

    if profile.capabilities.transfer:
        transfer_input = generated_clip or VideoClip(
            frames=[b"contract-frame"],
            fps=8.0,
            resolution=(64, 64),
            duration_seconds=0.125,
            metadata={"provider": provider.name},
        )
        if can_invoke:
            transferred = provider.transfer(transfer_input, width=48, height=48, fps=12.0)
            _validate_clip(transferred)
            report.exercised_operations.append("transfer")
        else:
            _expect_provider_error(
                "transfer",
                lambda: provider.transfer(transfer_input, width=48, height=48, fps=12.0),
            )

    if profile.capabilities.score:
        if can_invoke:
            if score_info is None or score_action_candidates is None:
                raise AssertionError(
                    "Provider contract requires score_info and score_action_candidates for "
                    "configured score providers."
                )
            scores = provider.score_actions(
                info=score_info,
                action_candidates=score_action_candidates,
            )
            _validate_action_scores(provider.name, scores)
            report.exercised_operations.append("score")
        else:
            _expect_provider_error(
                "score",
                lambda: provider.score_actions(
                    info=score_info or {},
                    action_candidates=[]
                    if score_action_candidates is None
                    else score_action_candidates,
                ),
            )

    return report
