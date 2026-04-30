"""WorldForge: testable world-model workflows for physical-AI systems.

WorldForge is a Python integration layer that gives world-model providers, score models,
embodied policies, and media generators explicit capability contracts. Planning, evaluation,
benchmarks, diagnostics, local state, and CLI tooling are built on top of those contracts.

The package exposes the public surface used by adapters, CLI commands, evaluations, and
benchmarks. Public re-exports are loaded lazily so lightweight integrations, such as pytest
plugin discovery, do not import the full runtime stack before they need it.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Any

try:
    __version__ = version("worldforge-ai")
except PackageNotFoundError:  # pragma: no cover - fallback for editable local imports
    __version__ = "0.0.0"

_EXPORTS: dict[str, str] = {  # pragma: no cover - initialized before pytest-cov by plugins
    "BenchmarkBudget": "worldforge.benchmark",
    "BenchmarkGateReport": "worldforge.benchmark",
    "BenchmarkGateViolation": "worldforge.benchmark",
    "BenchmarkInputs": "worldforge.benchmark",
    "BenchmarkReport": "worldforge.benchmark",
    "BenchmarkResult": "worldforge.benchmark",
    "ProviderBenchmarkHarness": "worldforge.benchmark",
    "load_benchmark_budgets": "worldforge.benchmark",
    "load_benchmark_inputs": "worldforge.benchmark",
    "run_benchmark": "worldforge.benchmark",
    "Cost": "worldforge.capabilities",
    "Embedder": "worldforge.capabilities",
    "Generator": "worldforge.capabilities",
    "Planner": "worldforge.capabilities",
    "Policy": "worldforge.capabilities",
    "Predictor": "worldforge.capabilities",
    "Reasoner": "worldforge.capabilities",
    "RunnableModel": "worldforge.capabilities",
    "Transferer": "worldforge.capabilities",
    "EvalReport": "worldforge.evaluation",
    "EvalResult": "worldforge.evaluation",
    "EvalScenario": "worldforge.evaluation",
    "EvalSuite": "worldforge.evaluation",
    "EvaluationReport": "worldforge.evaluation",
    "EvaluationResult": "worldforge.evaluation",
    "EvaluationScenario": "worldforge.evaluation",
    "EvaluationSuite": "worldforge.evaluation",
    "GenerationEval": "worldforge.evaluation",
    "GenerationEvaluationSuite": "worldforge.evaluation",
    "PhysicsEval": "worldforge.evaluation",
    "PhysicsEvaluationSuite": "worldforge.evaluation",
    "PlanningEval": "worldforge.evaluation",
    "PlanningEvaluationSuite": "worldforge.evaluation",
    "ProviderSummary": "worldforge.evaluation",
    "ReasoningEval": "worldforge.evaluation",
    "ReasoningEvaluationSuite": "worldforge.evaluation",
    "TransferEval": "worldforge.evaluation",
    "TransferEvaluationSuite": "worldforge.evaluation",
    "Comparison": "worldforge.framework",
    "Plan": "worldforge.framework",
    "PlanExecution": "worldforge.framework",
    "Prediction": "worldforge.framework",
    "World": "worldforge.framework",
    "WorldForge": "worldforge.framework",
    "list_eval_suites": "worldforge.framework",
    "run_eval": "worldforge.framework",
    "ProviderBudgetExceededError": "worldforge.providers",
    "EmbodimentActionTranslator": "worldforge.providers",
    "EmbodimentTranslatorContract": "worldforge.providers",
    "CAPABILITY_NAMES": "worldforge.models",
    "Action": "worldforge.models",
    "ActionPolicyResult": "worldforge.models",
    "ActionScoreResult": "worldforge.models",
    "BBox": "worldforge.models",
    "DoctorReport": "worldforge.models",
    "EmbeddingResult": "worldforge.models",
    "GenerationOptions": "worldforge.models",
    "Pose": "worldforge.models",
    "Position": "worldforge.models",
    "ProviderCapabilities": "worldforge.models",
    "ProviderDoctorStatus": "worldforge.models",
    "ProviderEvent": "worldforge.models",
    "ProviderHealth": "worldforge.models",
    "ProviderInfo": "worldforge.models",
    "ProviderProfile": "worldforge.models",
    "ProviderRequestPolicy": "worldforge.models",
    "ReasoningResult": "worldforge.models",
    "RequestOperationPolicy": "worldforge.models",
    "RerunArtifactLogger": "worldforge.rerun",
    "RerunEventSink": "worldforge.rerun",
    "RerunRecordingConfig": "worldforge.rerun",
    "RerunSession": "worldforge.rerun",
    "RetryPolicy": "worldforge.models",
    "Rotation": "worldforge.models",
    "SceneObject": "worldforge.models",
    "SceneObjectPatch": "worldforge.models",
    "StructuredGoal": "worldforge.models",
    "VideoClip": "worldforge.models",
    "WorldForgeError": "worldforge.models",
    "WorldStateError": "worldforge.models",
    "create_rerun_event_handler": "worldforge.rerun",
}

__all__ = sorted((*_EXPORTS, "__version__"))


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORTS[name])
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:  # pragma: no cover - module dir support
    return sorted((*globals(), *_EXPORTS))
