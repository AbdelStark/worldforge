"""Compatibility exports for WorldForge evaluation suites."""

from __future__ import annotations

from worldforge.evaluation.builtin_suites import (
    GenerationEvaluationSuite,
    PhysicsEvaluationSuite,
    PlanningEvaluationSuite,
    ReasoningEvaluationSuite,
    TransferEvaluationSuite,
)
from worldforge.evaluation.failure_gallery import (
    EVALUATION_FAILURE_GALLERY_SCHEMA_VERSION,
    EvaluationFailureCase,
    EvaluationFailureGallery,
)
from worldforge.evaluation.report import EvaluationReport
from worldforge.evaluation.results import (
    EVALUATION_CLAIM_BOUNDARY,
    EVALUATION_METRIC_SEMANTICS,
    EvaluationContext,
    EvaluationResult,
    EvaluationScenario,
    EvaluationScenarioOutcome,
    ProviderSummary,
)
from worldforge.evaluation.suite_base import EvaluationSuite

EvalScenario = EvaluationScenario
EvalResult = EvaluationResult
EvalReport = EvaluationReport
EvalSuite = EvaluationSuite
GenerationEval = GenerationEvaluationSuite
PhysicsEval = PhysicsEvaluationSuite
PlanningEval = PlanningEvaluationSuite
ReasoningEval = ReasoningEvaluationSuite
TransferEval = TransferEvaluationSuite

__all__ = [
    "EVALUATION_CLAIM_BOUNDARY",
    "EVALUATION_FAILURE_GALLERY_SCHEMA_VERSION",
    "EVALUATION_METRIC_SEMANTICS",
    "EvalReport",
    "EvalResult",
    "EvalScenario",
    "EvalSuite",
    "EvaluationContext",
    "EvaluationFailureCase",
    "EvaluationFailureGallery",
    "EvaluationReport",
    "EvaluationResult",
    "EvaluationScenario",
    "EvaluationScenarioOutcome",
    "EvaluationSuite",
    "GenerationEval",
    "GenerationEvaluationSuite",
    "PhysicsEval",
    "PhysicsEvaluationSuite",
    "PlanningEval",
    "PlanningEvaluationSuite",
    "ProviderSummary",
    "ReasoningEval",
    "ReasoningEvaluationSuite",
    "TransferEval",
    "TransferEvaluationSuite",
]
