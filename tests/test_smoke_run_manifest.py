from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worldforge.models import WorldForgeError
from worldforge.smoke.run_manifest import (
    build_run_manifest,
    digest_file,
    digest_json_value,
    env_summary,
    validate_run_manifest,
    write_run_manifest,
)


def test_build_run_manifest_records_value_free_runtime_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_fixture = tmp_path / "policy-info.json"
    input_fixture.write_text(json.dumps({"observation": {"x": 1}}), encoding="utf-8")
    monkeypatch.setenv("RUNWAYML_API_SECRET", "real-secret-value")

    manifest = build_run_manifest(
        run_id="run-123",
        provider_profile="runway",
        capability="generate",
        status="passed",
        env_vars=("RUNWAYML_API_SECRET", "RUNWAY_BASE_URL"),
        command_argv=("worldforge-smoke", "--provider", "runway"),
        event_count=2,
        input_fixture=input_fixture,
        result={"task_id": "task-1", "status": "succeeded"},
        artifact_paths={"downloaded_video": tmp_path / "video.mp4"},
    ).to_dict()

    assert manifest["schema_version"] == 1
    assert manifest["runtime_manifest_id"] == "runway:schema-1"
    assert manifest["input_fixture_digest"] == digest_file(input_fixture)
    assert manifest["result_digest"] == digest_json_value(
        {"task_id": "task-1", "status": "succeeded"}
    )
    assert manifest["event_count"] == 2
    assert manifest["artifact_paths"] == {"downloaded_video": str(tmp_path / "video.mp4")}
    assert manifest["env_summary"] == [
        {
            "name": "RUNWAYML_API_SECRET",
            "present": True,
            "source": "env:RUNWAYML_API_SECRET",
            "secret": True,
        },
        {
            "name": "RUNWAY_BASE_URL",
            "present": False,
            "source": "unset",
            "secret": False,
        },
    ]
    assert "real-secret-value" not in json.dumps(manifest)


def test_write_run_manifest_validates_before_writing(tmp_path: Path) -> None:
    path = tmp_path / "run_manifest.json"
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="cosmos",
        capability="generate",
        status="skipped",
        env_vars=("COSMOS_BASE_URL",),
        command_argv=("smoke",),
    )

    assert write_run_manifest(path, manifest) == path
    assert json.loads(path.read_text(encoding="utf-8"))["provider_profile"] == "cosmos"


def test_run_manifest_preserves_safe_input_summary() -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("lewm-real",),
        input_summary={
            "bridge": "pusht",
            "score_shapes": {"action_candidates": [1, 3, 4, 10]},
        },
    ).to_dict()

    assert manifest["input_summary"] == {
        "bridge": "pusht",
        "score_shapes": {"action_candidates": [1, 3, 4, 10]},
    }


def test_run_manifest_rejects_secret_like_values_and_signed_urls(tmp_path: Path) -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="runway",
        capability="generate",
        status="passed",
        env_vars=("RUNWAYML_API_SECRET",),
        command_argv=("smoke",),
    ).to_dict()

    with pytest.raises(WorldForgeError, match="secret-like metadata"):
        validate_run_manifest({**manifest, "api_token": "sk-test-token"})

    sanitized = build_run_manifest(
        run_id="run-1",
        provider_profile="runway",
        capability="generate",
        status="passed",
        env_vars=("RUNWAYML_API_SECRET",),
        command_argv=("smoke",),
        artifact_paths={"video": "https://example.test/video.mp4?X-Amz-Signature=secret"},
    ).to_dict()
    assert sanitized["artifact_paths"] == {"video": "https://example.test/video.mp4"}

    with pytest.raises(WorldForgeError, match=r"secret-like metadata|unsafe URL"):
        validate_run_manifest(
            {
                **manifest,
                "artifact_paths": {
                    "video": "https://example.test/video.mp4?X-Amz-Signature=secret"
                },
            }
        )


def test_env_summary_rejects_blank_names() -> None:
    with pytest.raises(WorldForgeError, match="env var names"):
        env_summary((" ",))


def test_build_run_manifest_defaults_to_process_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["smoke", "--flag"])

    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="unknown-local",
        capability="policy",
        status="skipped",
        env_vars=(),
    ).to_dict()

    assert manifest["command_argv"] == ["smoke", "--flag"]
    assert manifest["runtime_manifest_id"] is None
