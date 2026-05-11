from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess

from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest
from worldforge.testing import DeterministicClock, stable_snapshot

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("generate_release_evidence", SCRIPT)
assert SPEC is not None
generate_release_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_release_evidence"] = generate_release_evidence
SPEC.loader.exec_module(generate_release_evidence)
ManifestEvidence = generate_release_evidence.ManifestEvidence
ReleaseGate = generate_release_evidence.ReleaseGate
main = generate_release_evidence.main
render_release_evidence = generate_release_evidence.render_release_evidence
release_gate_results = generate_release_evidence.release_gate_results


def test_release_evidence_renders_without_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for name in (
        "COSMOS_BASE_URL",
        "COSMOS_POLICY_BASE_URL",
        "RUNWAYML_API_SECRET",
        "RUNWAY_API_SECRET",
        "LEWORLDMODEL_POLICY",
        "LEWM_POLICY",
        "GROOT_POLICY_HOST",
        "LEROBOT_POLICY_PATH",
        "LEROBOT_POLICY",
    ):
        monkeypatch.delenv(name, raising=False)

    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(json.dumps({"results": []}), encoding="utf-8")

    report = render_release_evidence(
        output=tmp_path / "release-evidence.md",
        manifests=(),
        benchmark_artifacts=(benchmark,),
        artifacts=(),
        known_limitations=("No prepared-host smokes were run for this branch.",),
    )

    assert "| `runway` | host-owned |" in report
    assert "missing host-owned configuration: `RUNWAYML_API_SECRET`, `RUNWAY_API_SECRET`" in report
    assert "| `cosmos-policy` | host-owned |" in report
    assert "missing host-owned configuration: `COSMOS_POLICY_BASE_URL`" in report
    assert "uv run python scripts/generate_provider_docs.py --check" in report
    assert "uv run python scripts/check_docs_snippets.py" in report
    assert "uv run python scripts/check_optional_import_boundaries.py" in report
    assert "uv run --extra harness pytest --cov=src/worldforge" in report
    assert "Run with `--run-gates` to execute this checkout-safe gate." in report
    assert "[`" in report
    assert "benchmark.json" in report
    assert "No prepared-host smokes were run for this branch." in report


def test_release_evidence_links_live_manifest_and_artifact(tmp_path: Path) -> None:
    output = tmp_path / "bundle" / "release-evidence.md"
    manifest_path = tmp_path / "runs" / "runway-smoke" / "run_manifest.json"
    video_path = tmp_path / "runs" / "runway-smoke" / "video.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"fake-video")
    manifest = build_run_manifest(
        run_id="runway-smoke",
        provider_profile="runway",
        capability="generate",
        status="passed",
        env_vars=("RUNWAYML_API_SECRET",),
        command_argv=("worldforge-smoke-runway",),
        event_count=3,
        artifact_paths={"video": video_path},
        created_at="2026-01-01T00:00:00+00:00",
    )
    write_run_manifest(manifest_path, manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    report = render_release_evidence(
        output=output,
        manifests=(ManifestEvidence(path=manifest_path, payload=payload),),
        benchmark_artifacts=(),
        artifacts=(video_path,),
    )

    assert "| `runway` | passed |" in report
    assert payload["created_at"] == "2026-01-01T00:00:00+00:00"
    assert "run_manifest.json" in report
    assert "`generate`" in report
    assert "`video`=" in report
    assert "video.mp4" in report


def test_release_evidence_main_writes_default_shape(tmp_path: Path) -> None:
    output = tmp_path / "release-evidence.md"

    assert main(["--output", str(output), "--known-limitation", "Release candidate only."]) == 0

    report = output.read_text(encoding="utf-8")
    payload = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert report.startswith("# WorldForge Release Evidence")
    assert "Release candidate only." in report
    assert payload["schema_version"] == 1
    assert payload["validation_summary"]["skipped"] >= 1
    assert payload["live_provider_evidence"][0]["status"] == "host-owned"


def test_release_evidence_gate_runner_records_pass_fail_and_skip() -> None:
    gates = (
        ReleaseGate("Pass", "pass-command", "inspect pass"),
        ReleaseGate("Fail", "fail-command", "inspect fail"),
        ReleaseGate("Skip", "skip-command", "inspect skip"),
    )

    def runner(command: str, **kwargs) -> CompletedProcess[str]:
        assert kwargs["shell"] is True
        if command == "fail-command":
            return CompletedProcess(command, 7, stdout="ok", stderr="broken\n" * 2000)
        return CompletedProcess(command, 0, stdout="passed", stderr="")

    results = release_gate_results(
        gates,
        run=True,
        skip_gates=("Skip",),
        skip_reason="host skipped intentionally",
        runner=runner,
    )

    assert [result.status for result in results] == ["passed", "failed", "skipped"]
    assert results[0].exit_code == 0
    assert results[1].exit_code == 7
    assert len(results[1].stderr_tail) <= generate_release_evidence.MAX_CAPTURE_CHARS
    assert results[2].triage_step == "host skipped intentionally"


def test_release_evidence_gate_runner_accepts_deterministic_clock() -> None:
    gate = ReleaseGate("Docs", "uv run mkdocs build --strict", "fix docs")
    clock = DeterministicClock(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        wall_step=timedelta(seconds=1),
        monotonic_start=100.0,
        monotonic_step=0.25,
    )

    results = release_gate_results(
        (gate,),
        run=True,
        runner=lambda command, **_kwargs: CompletedProcess(command, 0, stdout="ok", stderr=""),
        now_utc=clock.now,
        monotonic_clock=clock.monotonic,
    )

    assert results[0].started_at == "2026-01-01T00:00:00+00:00"
    assert results[0].finished_at == "2026-01-01T00:00:01+00:00"
    assert results[0].duration_ms == 250.0


def test_release_evidence_json_payload_contains_gate_and_host_owned_statuses() -> None:
    gate_results = release_gate_results(
        (ReleaseGate("Docs", "uv run mkdocs build --strict", "fix docs"),),
        run=False,
    )

    payload = generate_release_evidence.release_evidence_payload(
        manifests=(),
        benchmark_artifacts=(),
        artifacts=(),
        gate_results=gate_results,
        known_limitations=("No live smokes.",),
    )

    assert payload["validation_gates"][0]["status"] == "skipped"
    assert payload["validation_gates"][0]["triage_step"].startswith("Run with")
    assert payload["validation_summary"] == {
        "passed": 0,
        "failed": 0,
        "skipped": 1,
        "host-owned": 0,
    }
    assert {item["status"] for item in payload["live_provider_evidence"]} == {"host-owned"}
    assert payload["known_limitations"] == ["No live smokes."]


def test_release_evidence_payload_uses_explicit_clock_for_snapshot(tmp_path: Path) -> None:
    gate_results = release_gate_results(
        (ReleaseGate("Docs", "uv run mkdocs build --strict", "fix docs"),),
        run=False,
    )
    payload = generate_release_evidence.release_evidence_payload(
        manifests=(),
        benchmark_artifacts=(tmp_path / "benchmark.json",),
        artifacts=(),
        gate_results=gate_results,
        known_limitations=("No live smokes.",),
        now_utc=DeterministicClock(start=datetime(2026, 1, 1, tzinfo=UTC)).now,
    )
    snapshot = stable_snapshot(
        payload,
        path_roots={tmp_path: "<tmp>"},
        field_replacements={"commit": "<commit>"},
    )

    assert snapshot["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert snapshot["benchmark_artifacts"][0]["path"] == "<tmp>/benchmark.json"
    assert snapshot["git"]["commit"] == "<commit>"


def test_release_evidence_main_discovers_evidence_bundle_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundles_dir = tmp_path / "evidence-bundles"
    bundle_manifest = bundles_dir / "mock" / "evidence_manifest.json"
    bundle_manifest.parent.mkdir(parents=True)
    bundle_manifest.write_text(
        json.dumps({"schema_version": 1, "safe_to_attach": True}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(generate_release_evidence, "DEFAULT_EVIDENCE_BUNDLES_DIR", bundles_dir)
    monkeypatch.setattr(generate_release_evidence, "DEFAULT_DIST_DIR", tmp_path / "dist")
    output = tmp_path / "release-evidence.md"

    assert main(["--output", str(output)]) == 0

    report = output.read_text(encoding="utf-8")
    assert "evidence_manifest.json" in report


def test_release_evidence_main_discovers_dependency_audit_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dependency_audit_dir = tmp_path / "dependency-audit"
    dependency_audit_json = dependency_audit_dir / "dependency-audit.json"
    dependency_audit_json.parent.mkdir(parents=True)
    dependency_audit_json.write_text(
        json.dumps({"schema_version": 1, "status": "passed"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        generate_release_evidence,
        "DEFAULT_DEPENDENCY_AUDIT_DIR",
        dependency_audit_dir,
    )
    monkeypatch.setattr(
        generate_release_evidence,
        "DEFAULT_EVIDENCE_BUNDLES_DIR",
        tmp_path / "evidence-bundles",
    )
    monkeypatch.setattr(generate_release_evidence, "DEFAULT_DIST_DIR", tmp_path / "dist")
    output = tmp_path / "release-evidence.md"

    assert main(["--output", str(output)]) == 0

    report = output.read_text(encoding="utf-8")
    payload = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert "dependency-audit.json" in report
    assert any(
        artifact["path"].endswith("dependency-audit.json")
        for artifact in payload["release_artifacts"]
    )
