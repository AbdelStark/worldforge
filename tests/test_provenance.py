from __future__ import annotations

import json
import math

import pytest

from worldforge import (
    BenchmarkInputs,
    BenchmarkReport,
    BenchmarkResult,
    EvaluationReport,
    EvaluationResult,
    EvaluationSuite,
    ProviderBenchmarkHarness,
    WorldForge,
    WorldForgeError,
)
from worldforge.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    ProvenanceEnvelope,
    digest_payload,
)


def _stub_evaluation_envelope(**overrides) -> ProvenanceEnvelope:
    base = {
        "kind": "evaluation",
        "suite_id": "physics",
        "suite_version": "evaluation:1",
        "providers": ("mock",),
        "capabilities": ("predict",),
        "claim_boundary": "deterministic adapter contract checks",
        "metric_semantics": "typed contract pass rates",
    }
    base.update(overrides)
    return ProvenanceEnvelope(**base)


def test_provenance_envelope_validates_required_fields() -> None:
    envelope = _stub_evaluation_envelope()
    payload = envelope.to_dict()
    assert payload["schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert payload["kind"] == "evaluation"
    assert payload["suite_id"] == "physics"
    assert payload["providers"] == ["mock"]
    assert payload["worldforge_version"]


def test_provenance_envelope_rejects_invalid_inputs() -> None:
    with pytest.raises(WorldForgeError, match="kind must be one of"):
        _stub_evaluation_envelope(kind="other")
    with pytest.raises(WorldForgeError, match="suite_id"):
        _stub_evaluation_envelope(suite_id="")
    with pytest.raises(WorldForgeError, match="providers"):
        _stub_evaluation_envelope(providers=("",))
    with pytest.raises(WorldForgeError, match="event_count"):
        _stub_evaluation_envelope(event_count=-1)
    with pytest.raises(WorldForgeError, match="schema_version"):
        _stub_evaluation_envelope(schema_version=999)
    with pytest.raises(WorldForgeError, match="input_digest"):
        _stub_evaluation_envelope(input_digest="not-a-digest")
    with pytest.raises(WorldForgeError, match="budget_file"):
        _stub_evaluation_envelope(budget_file={"path": "x"})  # missing sha256


def test_provenance_envelope_with_overrides_replaces_fields() -> None:
    envelope = _stub_evaluation_envelope()
    swapped = envelope.with_overrides(command=("worldforge", "eval", "--suite", "physics"))
    assert swapped.command == ("worldforge", "eval", "--suite", "physics")
    assert swapped.suite_id == envelope.suite_id


def test_provenance_envelope_round_trips_through_from_dict() -> None:
    envelope = _stub_evaluation_envelope(
        command=("worldforge", "eval", "--suite", "physics"),
        input_digest=digest_payload({"suite": "physics"}),
        result_digest=digest_payload([{"score": 0.9}]),
        runtime_manifests={"leworldmodel": "leworldmodel:schema-1"},
        notes="release evidence",
    )
    rebuilt = ProvenanceEnvelope.from_dict(envelope.to_dict())
    assert rebuilt.to_dict() == envelope.to_dict()


def test_digest_payload_is_deterministic_and_rejects_non_finite() -> None:
    assert digest_payload({"a": 1, "b": 2}) == digest_payload({"b": 2, "a": 1})
    with pytest.raises(WorldForgeError):
        digest_payload({"value": math.nan})


def test_evaluation_report_includes_envelope_in_artifacts(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    report = EvaluationSuite.from_builtin("physics").run_report(["mock"], forge=forge)

    assert isinstance(report.provenance, ProvenanceEnvelope)
    assert report.provenance.kind == "evaluation"
    assert report.provenance.suite_id == "physics"
    assert report.provenance.providers == ("mock",)
    assert report.provenance.capabilities == ("predict",)
    assert report.provenance.input_digest is not None
    assert report.provenance.result_digest is not None

    payload = json.loads(report.to_json())
    assert payload["provenance"]["suite_id"] == "physics"
    assert payload["provenance"]["schema_version"] == PROVENANCE_SCHEMA_VERSION

    markdown = report.to_markdown()
    assert "## Provenance" in markdown
    assert "WorldForge version" in markdown
    assert "Suite version: evaluation:1" in markdown


def test_evaluation_report_rejects_provenance_kind_mismatch() -> None:
    benchmark_envelope = ProvenanceEnvelope(
        kind="benchmark",
        suite_id="physics",
        suite_version="benchmark:1",
        providers=("mock",),
        capabilities=("predict",),
        claim_boundary="adapter-path latency",
        metric_semantics="successful-sample latency",
    )
    with pytest.raises(WorldForgeError, match="kind='evaluation'"):
        EvaluationReport(
            "physics",
            "Physics Evaluation Suite",
            [],
            provenance=benchmark_envelope,
        )


def test_evaluation_report_requires_results_to_share_suite_metadata() -> None:
    foreign_result = EvaluationResult(
        suite_id="planning",
        suite="Planning",
        scenario="object-relocation",
        provider="mock",
        score=0.9,
        passed=True,
    )
    with pytest.raises(WorldForgeError, match="suite_id"):
        EvaluationReport("physics", "Physics", [foreign_result])


def test_benchmark_report_includes_envelope_in_artifacts(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    harness = ProviderBenchmarkHarness(forge=forge)
    report = harness.run("mock", operations=["predict"], iterations=2)

    assert isinstance(report.provenance, ProvenanceEnvelope)
    assert report.provenance.kind == "benchmark"
    assert report.provenance.providers == ("mock",)
    assert report.provenance.capabilities == ("predict",)
    assert report.provenance.input_digest == digest_payload(BenchmarkInputs().to_dict())
    assert report.provenance.result_digest is not None
    assert report.provenance.event_count >= 1

    payload = json.loads(report.to_json())
    assert payload["provenance"]["kind"] == "benchmark"
    assert "## Provenance" in report.to_markdown()


def test_benchmark_report_rejects_provenance_kind_mismatch() -> None:
    eval_envelope = ProvenanceEnvelope(
        kind="evaluation",
        suite_id="benchmark",
        suite_version="benchmark:1",
        providers=("mock",),
        capabilities=("predict",),
        claim_boundary="adapter-path latency",
        metric_semantics="successful-sample latency",
    )
    with pytest.raises(WorldForgeError, match="kind='benchmark'"):
        BenchmarkReport(results=[], provenance=eval_envelope)


def test_benchmark_csv_renderer_remains_stable_with_envelope(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    report = ProviderBenchmarkHarness(forge=forge).run(
        "mock",
        operations=["predict"],
        iterations=1,
    )
    assert report.to_csv().startswith("provider,operation,iterations")


def test_evaluation_csv_renderer_remains_stable_with_envelope(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    report = EvaluationSuite.from_builtin("physics").run_report(["mock"], forge=forge)
    assert report.to_csv().startswith("suite_id,suite,provider,scenario,score,passed,metrics_json")


def test_benchmark_report_validates_results_type() -> None:
    with pytest.raises(WorldForgeError, match="BenchmarkReport results"):
        BenchmarkReport(results=[object()])  # type: ignore[list-item]


def test_benchmark_result_to_dict_round_trips_into_report() -> None:
    sample = BenchmarkResult(
        provider="mock",
        operation="predict",
        iterations=1,
        concurrency=1,
        success_count=1,
        error_count=0,
        retry_count=0,
        total_time_ms=1.0,
        average_latency_ms=1.0,
        min_latency_ms=1.0,
        max_latency_ms=1.0,
        p50_latency_ms=1.0,
        p95_latency_ms=1.0,
        throughput_per_second=1.0,
        operation_metrics={"events": []},
        errors=[],
    )
    BenchmarkReport(results=[sample])  # type: ignore[arg-type]
