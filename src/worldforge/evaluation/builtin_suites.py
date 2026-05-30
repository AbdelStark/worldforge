"""Stable facade for built-in deterministic evaluation suite implementations."""

from __future__ import annotations

from worldforge.evaluation.media_suites import GenerationEvaluationSuite, TransferEvaluationSuite
from worldforge.evaluation.physics_suite import PhysicsEvaluationSuite
from worldforge.evaluation.planning_suite import PlanningEvaluationSuite
from worldforge.evaluation.reasoning_suite import ReasoningEvaluationSuite
from worldforge.evaluation.suite_fixtures import (
    _SAMPLE_IMAGE_DATA_URI,
    _sample_transfer_clip,
    _seed_object,
)

__all__ = [
    "_SAMPLE_IMAGE_DATA_URI",
    "GenerationEvaluationSuite",
    "PhysicsEvaluationSuite",
    "PlanningEvaluationSuite",
    "ReasoningEvaluationSuite",
    "TransferEvaluationSuite",
    "_sample_transfer_clip",
    "_seed_object",
]
