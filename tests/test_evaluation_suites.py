from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from worldforge import DATASET_MANIFEST_SCHEMA_VERSION, WorldForge, WorldForgeError
from worldforge.dataset_manifests import load_dataset_manifest, parse_dataset_manifest
from worldforge.evaluation import (
    EvaluationContext,
    EvaluationScenario,
    EvaluationScenarioOutcome,
    EvaluationSuite,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET_MANIFEST = ROOT / "examples/dataset-manifests/mock-evaluation-fixtures.json"
CUSTOM_EVAL_EXAMPLE = ROOT / "examples/custom_evaluation_suite.py"
_DIGEST = "sha256:72b95ee161e971da5eb37a54b426dda56863819d81cd6e4b32f1111f8336c086"


def test_builtin_evaluation_suite_names_are_stable() -> None:
    assert EvaluationSuite.builtin_names() == [
        "generation",
        "physics",
        "planning",
        "reasoning",
        "transfer",
    ]


def test_builtin_evaluation_reports_export_failure_gallery_artifacts(tmp_path) -> None:
    report = EvaluationSuite.from_builtin("physics").run_report(
        ["mock"],
        forge=WorldForge(state_dir=tmp_path),
    )
    artifacts = report.artifacts()

    assert {"json", "markdown", "csv", "failure_gallery.json", "failure_gallery.md"} <= set(
        artifacts
    )
    assert json.loads(artifacts["failure_gallery.json"])["case_count"] == 0
    assert "No failed evaluation cases." in artifacts["failure_gallery.md"]


def test_dataset_manifest_validates_and_evaluation_report_cites_it(tmp_path) -> None:
    manifest = load_dataset_manifest(DATASET_MANIFEST, root=ROOT)
    assert manifest.schema_version == DATASET_MANIFEST_SCHEMA_VERSION
    assert manifest.entry_count == 2
    assert manifest.entries[0].kind == "local-fixture"
    assert manifest.entries[1].kind == "remote-reference"

    report = EvaluationSuite.from_builtin("physics").run_report(
        ["mock"],
        forge=WorldForge(state_dir=tmp_path),
        dataset_manifests=[DATASET_MANIFEST],
    )

    assert report.provenance is not None
    refs = report.provenance.dataset_manifests
    assert len(refs) == 1
    assert refs[0]["id"] == "mock-evaluation-fixtures"
    assert refs[0]["path"] == "examples/dataset-manifests/mock-evaluation-fixtures.json"
    assert refs[0]["entry_count"] == 2
    payload = report.to_dict()
    assert payload["provenance"]["dataset_manifests"][0]["id"] == "mock-evaluation-fixtures"
    assert "entries" not in payload["provenance"]["dataset_manifests"][0]
    assert "Dataset manifests: mock-evaluation-fixtures" in report.to_markdown()


def test_dataset_manifest_rejects_unsafe_or_under_specified_payloads() -> None:
    payload = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))

    missing_provenance = json.loads(json.dumps(payload))
    del missing_provenance["provenance"]["owner"]
    with pytest.raises(WorldForgeError, match=r"provenance\.owner"):
        parse_dataset_manifest(missing_provenance, root=ROOT)

    unsafe_path = json.loads(json.dumps(payload))
    unsafe_path["entries"][0]["path"] = "../private.json"
    with pytest.raises(WorldForgeError, match="traversal"):
        parse_dataset_manifest(unsafe_path, root=ROOT)

    bad_digest = json.loads(json.dumps(payload))
    bad_digest["entries"][0]["sha256"] = _DIGEST.replace("72", "73", 1)
    with pytest.raises(WorldForgeError, match="does not match local fixture"):
        parse_dataset_manifest(bad_digest, root=ROOT)


def test_dataset_manifest_validates_remote_reference_boundaries() -> None:
    payload = {
        "schema_version": DATASET_MANIFEST_SCHEMA_VERSION,
        "id": "remote-reference",
        "name": "Remote Reference",
        "description": "Manifest containing a stable remote reference.",
        "license": "Example license",
        "provenance": {
            "source": "Example registry",
            "version": "remote-reference:1",
            "owner": "WorldForge tests",
        },
        "privacy": {"classification": "public", "contains_personal_data": False},
        "safety": {
            "reviewed": True,
            "contains_sensitive_capability_data": False,
            "contains_robot_logs": False,
        },
        "host_acquisition_steps": ["Fetch outside the repository and verify the digest."],
        "entries": [
            {
                "id": "remote-entry",
                "kind": "remote-reference",
                "description": "Stable external reference.",
                "sha256": _DIGEST,
                "uri": "https://example.com/worldforge/dataset.json",
            },
            {
                "id": "host-entry",
                "kind": "host-asset",
                "description": "Host-owned prepared asset reference.",
                "sha256": _DIGEST,
                "asset_id": "host-prepared-fixture-v1",
            },
        ],
    }
    manifest = parse_dataset_manifest(payload, root=ROOT)
    assert manifest.entries[0].uri == "https://example.com/worldforge/dataset.json"
    assert manifest.entries[1].asset_id == "host-prepared-fixture-v1"

    payload["entries"][0]["uri"] = "https://example.com/worldforge/dataset.json?token=secret"
    with pytest.raises(WorldForgeError, match="query strings"):
        parse_dataset_manifest(payload, root=ROOT)


def test_custom_evaluation_suite_runs_with_provenance_and_artifacts(tmp_path) -> None:
    def evaluate_object_count(context: EvaluationContext) -> EvaluationScenarioOutcome:
        return context.outcome(
            score=1.0,
            passed=True,
            metrics={
                "object_count": context.world.object_count,
                "scenario_index": context.index,
            },
        )

    suite = EvaluationSuite.custom(
        suite_id="custom-object-count",
        name="Custom Object Count",
        suite_version="custom-object-count:1",
        claim_boundary=(
            "This custom suite is a deterministic checkout example, not a model-quality claim."
        ),
        scenarios=[
            EvaluationScenario.from_callable(
                name="empty-world-count",
                description="Checks that a checkout-created world is readable.",
                evaluator=evaluate_object_count,
            )
        ],
    )
    EvaluationSuite.register("custom-object-count", lambda: suite, replace=True)
    try:
        report = EvaluationSuite.from_registered("custom-object-count").run_report(
            ["mock"],
            forge=WorldForge(state_dir=tmp_path),
        )
    finally:
        EvaluationSuite.unregister("custom-object-count")

    assert report.results[0].passed is True
    assert report.results[0].metrics["object_count"] == 0
    assert report.provenance is not None
    assert report.provenance.suite_version == "custom-object-count:1"
    assert report.to_dict()["claim_boundary"].startswith("This custom suite")
    assert json.loads(report.artifacts()["failure_gallery.json"])["suite_version"] == (
        "custom-object-count:1"
    )
    assert "Custom Object Count" in report.artifacts()["markdown"]


def test_custom_evaluation_suite_failure_gallery_uses_custom_claim_boundary(tmp_path) -> None:
    def fail(context: EvaluationContext) -> dict[str, object]:
        return {
            "score": 0.25,
            "passed": False,
            "metrics": {
                "local_path": "/Users/example/private/run.json",
                "tensor_values": [[1, 2, 3], [4, 5, 6]],
                "scenario": context.scenario.name,
            },
        }

    suite = EvaluationSuite.custom(
        suite_id="custom-failure",
        name="Custom Failure Suite",
        suite_version="custom-failure:1",
        claim_boundary="Custom failure gallery is issue-triage evidence only.",
        scenarios=[
            EvaluationScenario.from_callable(
                name="failing-scenario",
                description="Produces one representative failure.",
                evaluator=fail,
            )
        ],
    )

    report = suite.run_report("mock", forge=WorldForge(state_dir=tmp_path))
    gallery = report.failure_gallery()
    payload = gallery.to_dict()

    assert payload["case_count"] == 1
    assert payload["claim_boundary"] == "Custom failure gallery is issue-triage evidence only."
    assert payload["cases"][0]["metrics_preview"]["local_path"] == "[host-local-path]"
    assert payload["cases"][0]["metrics_preview"]["tensor_values"]["type"] == "array"


def test_custom_evaluation_walkthrough_example_writes_report_artifacts(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location(
        "worldforge_custom_evaluation_suite_test",
        CUSTOM_EVAL_EXAMPLE,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    summary = module.run_walkthrough(
        output_dir=tmp_path / "artifacts",
        state_dir=tmp_path / "worlds",
    )

    assert summary["safe_to_attach"] is True
    assert summary["provenance_present"] is True
    assert summary["result_count"] == 2
    assert summary["failed_count"] == 1
    artifact_paths = summary["artifact_paths"]
    assert {"json", "markdown", "html", "failure_gallery.json", "failure_gallery.md"} <= set(
        artifact_paths
    )
    report_payload = json.loads(Path(artifact_paths["json"]).read_text(encoding="utf-8"))
    gallery_payload = json.loads(
        Path(artifact_paths["failure_gallery.json"]).read_text(encoding="utf-8")
    )
    assert report_payload["provenance"]["suite_id"] == "custom-empty-world"
    assert gallery_payload["case_count"] == 1
    assert "controlled-failure-gallery" in Path(artifact_paths["markdown"]).read_text(
        encoding="utf-8"
    )


def test_custom_evaluation_suite_rejects_invalid_metric_payload(tmp_path) -> None:
    def invalid_metrics(context: EvaluationContext) -> EvaluationScenarioOutcome:
        return context.outcome(
            score=1.0,
            passed=True,
            metrics={"bad": object()},
        )

    suite = EvaluationSuite.custom(
        suite_id="custom-invalid-metrics",
        name="Custom Invalid Metrics",
        suite_version="custom-invalid-metrics:1",
        claim_boundary="Invalid metric fixture.",
        scenarios=[
            EvaluationScenario.from_callable(
                name="invalid-metrics",
                description="Returns a non-JSON metric payload.",
                evaluator=invalid_metrics,
            )
        ],
    )

    with pytest.raises(WorldForgeError, match=r"EvaluationScenarioOutcome metrics\.bad"):
        suite.run_report("mock", forge=WorldForge(state_dir=tmp_path))
