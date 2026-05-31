"""Deterministic evaluation suites for WorldForge providers.

The evaluation package bundles built-in ``physics`` and ``planning`` suites that exercise a
provider's typed surfaces through fixed scenarios and capture results as
:class:`EvaluationReport` payloads. Construct
suites via :meth:`EvaluationSuite.from_builtin` (the primary entry point) or assemble custom
:class:`EvaluationScenario` sequences with callable :class:`EvaluationContext` evaluators.

The suites are **adapter-contract checks, not physical-fidelity benchmarks**. A passing score
asserts the provider returns well-formed payloads under the documented inputs; it is not
evidence of physical realism, media quality, or task success on real hardware. The
``EvalReport``/``EvalResult``/``EvalScenario``/``EvalSuite`` aliases are kept for backwards
compatibility and resolve to the same classes.
"""

from worldforge.dataset_manifests import (
    DatasetManifest,
    DatasetManifestEntry,
    load_dataset_manifest,
    parse_dataset_manifest,
)
from worldforge.evaluation.failure_gallery import (
    EvaluationFailureCase,
    EvaluationFailureGallery,
)
from worldforge.evaluation.report import EvaluationReport
from worldforge.evaluation.results import (
    EvaluationContext,
    EvaluationResult,
    EvaluationScenario,
    EvaluationScenarioOutcome,
    ProviderSummary,
)

from .suites import (
    EvalReport,
    EvalResult,
    EvalScenario,
    EvalSuite,
    EvaluationSuite,
    PhysicsEval,
    PhysicsEvaluationSuite,
    PlanningEval,
    PlanningEvaluationSuite,
)

__all__ = [
    "DatasetManifest",
    "DatasetManifestEntry",
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
    "PhysicsEval",
    "PhysicsEvaluationSuite",
    "PlanningEval",
    "PlanningEvaluationSuite",
    "ProviderSummary",
    "load_dataset_manifest",
    "parse_dataset_manifest",
]
