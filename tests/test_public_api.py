from __future__ import annotations

import worldforge
import worldforge.observability as observability
import worldforge.provider_models as provider_models
import worldforge.rerun as rerun
import worldforge.scene_models as scene_models
import worldforge.structured_goals as structured_goals
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
        "embed",
        "plan",
        "score",
        "policy",
    )
    assert worldforge.Cost is not None
    assert worldforge.LatentMPCController is not None
    assert worldforge.PlannerConfig is not None
    assert worldforge.ScoreCandidateBatch is not None
    assert worldforge.Policy is not None
    assert worldforge.Predictor is not None
    assert worldforge.RunnableModel is not None
    assert worldforge.LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION == 1
    assert "skipped_missing_runtime" in worldforge.LIVE_SMOKE_EVIDENCE_STATUSES
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
    assert worldforge.WorldForge is not None
    assert worldforge.WorldForgeError is not None
    assert worldforge.WorldStateError is not None
    assert worldforge.SceneObjectPatch is not None
    assert worldforge.render_live_smoke_registry_table is not None
    assert worldforge.validate_live_smoke_registry is not None
    assert worldforge.load_benchmark_budgets is not None
    assert worldforge.load_benchmark_inputs is not None
    assert EvaluationSuite is not None
    assert worldforge.PlanningEvaluationSuite is not None
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


def test_provider_models_compatibility_facade_reexports_leaf_contracts() -> None:
    assert provider_models.ProviderCapabilities is worldforge.ProviderCapabilities
    assert provider_models.ProviderEvent is worldforge.ProviderEvent
    assert provider_models.ProviderRequestPolicy is worldforge.ProviderRequestPolicy
    assert provider_models.ProviderLifecycleStatus is worldforge.ProviderLifecycleStatus
    assert provider_models._redact_observable_text("api_key=secret") == "api_key=[redacted]"


def test_structured_goal_exports_use_goal_module_with_scene_compatibility() -> None:
    assert worldforge.StructuredGoal is structured_goals.StructuredGoal
    assert scene_models.StructuredGoal is structured_goals.StructuredGoal


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
