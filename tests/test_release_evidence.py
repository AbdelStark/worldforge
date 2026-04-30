from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("generate_release_evidence", SCRIPT)
assert SPEC is not None
generate_release_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_release_evidence"] = generate_release_evidence
SPEC.loader.exec_module(generate_release_evidence)
ManifestEvidence = generate_release_evidence.ManifestEvidence
main = generate_release_evidence.main
render_release_evidence = generate_release_evidence.render_release_evidence


def test_release_evidence_renders_without_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for name in (
        "COSMOS_BASE_URL",
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

    assert (
        "| `runway` | not configured | missing `RUNWAYML_API_SECRET`, `RUNWAY_API_SECRET` |"
        in report
    )
    assert "uv run python scripts/generate_provider_docs.py --check" in report
    assert "uv run --extra harness pytest --cov=src/worldforge" in report
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
    assert "run_manifest.json" in report
    assert "`generate`" in report
    assert "`video`=" in report
    assert "video.mp4" in report


def test_release_evidence_main_writes_default_shape(tmp_path: Path) -> None:
    output = tmp_path / "release-evidence.md"

    assert main(["--output", str(output), "--known-limitation", "Release candidate only."]) == 0

    report = output.read_text(encoding="utf-8")
    assert report.startswith("# WorldForge Release Evidence")
    assert "Release candidate only." in report
