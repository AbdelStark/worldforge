from __future__ import annotations

import worldforge
import worldforge.observability as observability
import worldforge.rerun as rerun
import worldforge.testing as testing_helpers
from worldforge.evaluation import EvaluationSuite
from worldforge.providers import GrootPolicyClientProvider, MockProvider


def test_top_level_exports_and_subpackages_import() -> None:
    assert worldforge.__version__
    assert worldforge.ActionPolicyResult is not None
    assert worldforge.ActionScoreResult is not None
    assert worldforge.BenchmarkBudget is not None
    assert worldforge.BenchmarkGateReport is not None
    assert worldforge.BenchmarkGateViolation is not None
    assert worldforge.BenchmarkInputs is not None
    assert worldforge.BenchmarkReport is not None
    assert worldforge.BenchmarkResult is not None
    assert worldforge.CAPABILITY_NAMES == (
        "predict",
        "generate",
        "reason",
        "embed",
        "plan",
        "transfer",
        "score",
        "policy",
    )
    assert worldforge.Cost is not None
    assert worldforge.Policy is not None
    assert worldforge.Generator is not None
    assert worldforge.Predictor is not None
    assert worldforge.RunnableModel is not None
    assert worldforge.GenerationOptions is not None
    assert worldforge.GenerationEvaluationSuite is not None
    assert worldforge.ProviderEvent is not None
    assert worldforge.ProviderBenchmarkHarness is not None
    assert worldforge.ProviderBudgetExceededError is not None
    assert worldforge.ProviderRequestPolicy is not None
    assert worldforge.RequestOperationPolicy is not None
    assert worldforge.RetryPolicy is not None
    assert worldforge.RerunArtifactLogger is not None
    assert worldforge.RerunEventSink is not None
    assert worldforge.RerunRecordingConfig is not None
    assert worldforge.RerunSession is not None
    assert worldforge.StructuredGoal is not None
    assert worldforge.TransferEvaluationSuite is not None
    assert worldforge.WorldForge is not None
    assert worldforge.WorldForgeError is not None
    assert worldforge.WorldStateError is not None
    assert worldforge.SceneObjectPatch is not None
    assert worldforge.load_benchmark_budgets is not None
    assert worldforge.load_benchmark_inputs is not None
    assert EvaluationSuite is not None
    assert worldforge.PlanningEvaluationSuite is not None
    assert worldforge.ReasoningEvaluationSuite is not None
    assert MockProvider is not None
    assert GrootPolicyClientProvider is not None
    assert observability.JsonLoggerSink is not None
    assert observability.InMemoryMetricsExporter is not None
    assert observability.InMemoryRecorderSink is not None
    assert observability.OpenTelemetryProviderEventSink is not None
    assert observability.ProviderMetricsExporterSink is not None
    assert observability.ProviderMetricsSink is not None
    assert observability.RunJsonLogSink is not None
    assert observability.compose_event_handlers is not None
    assert observability.provider_event_metric_labels is not None
    assert observability.provider_event_span_attributes is not None
    assert rerun.RerunArtifactLogger is not None
    assert rerun.create_rerun_event_handler is not None


def test_lazy_export_modules_have_expected_dir_and_attribute_errors() -> None:
    assert "WorldForge" in dir(worldforge)
    assert "ProviderContractReport" in dir(testing_helpers)
    assert testing_helpers.ProviderContractReport is not None

    missing = "missing_public_export"
    for module in (worldforge, testing_helpers):
        try:
            getattr(module, missing)
        except AttributeError as exc:
            assert missing in str(exc)
        else:  # pragma: no cover - assertion guard
            raise AssertionError(f"{module.__name__} unexpectedly exposes {missing}")
