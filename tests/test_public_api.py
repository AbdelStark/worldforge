from __future__ import annotations

import worldforge
import worldforge.observability as observability
from worldforge.evaluation import EvaluationSuite
from worldforge.providers import MockProvider


def test_top_level_exports_and_subpackages_import() -> None:
    assert worldforge.__version__
    assert worldforge.ActionScoreResult is not None
    assert worldforge.BenchmarkInputs is not None
    assert worldforge.BenchmarkReport is not None
    assert worldforge.BenchmarkResult is not None
    assert worldforge.GenerationOptions is not None
    assert worldforge.GenerationEvaluationSuite is not None
    assert worldforge.ProviderEvent is not None
    assert worldforge.ProviderBenchmarkHarness is not None
    assert worldforge.ProviderRequestPolicy is not None
    assert worldforge.RequestOperationPolicy is not None
    assert worldforge.RetryPolicy is not None
    assert worldforge.StructuredGoal is not None
    assert worldforge.TransferEvaluationSuite is not None
    assert worldforge.WorldForge is not None
    assert worldforge.WorldForgeError is not None
    assert worldforge.WorldStateError is not None
    assert worldforge.SceneObjectPatch is not None
    assert EvaluationSuite is not None
    assert worldforge.PlanningEvaluationSuite is not None
    assert worldforge.ReasoningEvaluationSuite is not None
    assert MockProvider is not None
    assert observability.JsonLoggerSink is not None
    assert observability.InMemoryRecorderSink is not None
    assert observability.ProviderMetricsSink is not None
    assert observability.compose_event_handlers is not None
