"""Deterministic scene-reasoning evaluation suite."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from worldforge.evaluation.results import EvaluationResult, EvaluationScenario
from worldforge.evaluation.results import clamp_score as _clamp_score
from worldforge.evaluation.suite_base import EvaluationSuite
from worldforge.evaluation.suite_fixtures import seed_object
from worldforge.models import Position

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge


class ReasoningEvaluationSuite(EvaluationSuite):
    """Built-in suite for scene reasoning quality checks."""

    def __init__(self) -> None:
        super().__init__(
            "Reasoning Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "scene-count",
                    "Checks whether the provider reports the tracked object count.",
                    required_capabilities=("reason",),
                ),
                EvaluationScenario(
                    "scene-identity",
                    "Checks whether provider evidence references tracked object identifiers.",
                    required_capabilities=("reason",),
                ),
            ],
            suite_id="reasoning",
        )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        world = super()._build_world(provider, forge=forge)
        seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        return world

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_scene_count(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        expected_count = world.object_count
        reasoning = forge.reason(provider, "How many objects are tracked?", world=world)
        answer = reasoning.answer.lower()
        mentions_count = str(expected_count) in answer
        has_evidence = bool(reasoning.evidence)
        score = _clamp_score(
            (
                reasoning.confidence
                + (1.0 if mentions_count else 0.0)
                + (1.0 if has_evidence else 0.0)
            )
            / 3
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=mentions_count and has_evidence,
            metrics={
                "confidence": reasoning.confidence,
                "expected_count": expected_count,
                "evidence_count": len(reasoning.evidence),
                "mentions_count": mentions_count,
            },
        )

    def _evaluate_scene_identity(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        object_ids = sorted(obj.id for obj in world.objects())
        reasoning = forge.reason(provider, "Which object ids are tracked?", world=world)
        haystack = " ".join([reasoning.answer, *reasoning.evidence]).lower()
        matched_ids = [object_id for object_id in object_ids if object_id.lower() in haystack]
        coverage = len(matched_ids) / len(object_ids) if object_ids else 1.0
        score = _clamp_score((reasoning.confidence + coverage) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=coverage == 1.0,
            metrics={
                "confidence": reasoning.confidence,
                "tracked_object_count": len(object_ids),
                "matched_object_count": len(matched_ids),
                "coverage": coverage,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "scene-count": _evaluate_scene_count,
        "scene-identity": _evaluate_scene_identity,
    }


__all__ = ["ReasoningEvaluationSuite"]
