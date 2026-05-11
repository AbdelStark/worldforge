"""Deterministic evaluation suites for WorldForge providers.

The evaluation package bundles five built-in suites — ``generation``, ``physics``,
``planning``, ``reasoning``, and ``transfer`` — that exercise a provider's typed surfaces
through fixed scenarios and capture results as :class:`EvaluationReport` payloads. Construct
suites via :meth:`EvaluationSuite.from_builtin` (the primary entry point) or assemble custom
:class:`EvaluationScenario` sequences with callable :class:`EvaluationContext` evaluators.

The suites are **adapter-contract checks, not physical-fidelity benchmarks**. A passing score
asserts the provider returns well-formed payloads under the documented inputs; it is not
evidence of physical realism, media quality, or task success on real hardware. The
``EvalReport``/``EvalResult``/``EvalScenario``/``EvalSuite`` aliases are kept for backwards
compatibility and resolve to the same classes.
"""

from .suites import (
    EvalReport,
    EvalResult,
    EvalScenario,
    EvalSuite,
    EvaluationContext,
    EvaluationFailureCase,
    EvaluationFailureGallery,
    EvaluationReport,
    EvaluationResult,
    EvaluationScenario,
    EvaluationScenarioOutcome,
    EvaluationSuite,
    GenerationEval,
    GenerationEvaluationSuite,
    PhysicsEval,
    PhysicsEvaluationSuite,
    PlanningEval,
    PlanningEvaluationSuite,
    ProviderSummary,
    ReasoningEval,
    ReasoningEvaluationSuite,
    TransferEval,
    TransferEvaluationSuite,
)

__all__ = [
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
