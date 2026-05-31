from __future__ import annotations

import json
import math
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
    monkeypatch.setenv("LEWORLDMODEL_POLICY", "real-secret-value")

    manifest = build_run_manifest(
        run_id="run-123",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY", "LEWORLDMODEL_DEVICE"),
        command_argv=("worldforge-smoke", "--provider", "leworldmodel"),
        event_count=2,
        input_fixture=input_fixture,
        result={"task_id": "task-1", "status": "succeeded"},
        artifact_paths={"score_result": tmp_path / "score.json"},
        artifact_root=tmp_path,
    ).to_dict()

    assert manifest["schema_version"] == 1
    assert manifest["runtime_manifest_id"] == "leworldmodel:schema-1"
    assert manifest["input_digest"] == digest_file(input_fixture)
    assert manifest["input_fixture_digest"] == digest_file(input_fixture)
    assert manifest["result_digest"] == digest_json_value(
        {"task_id": "task-1", "status": "succeeded"}
    )
    assert manifest["event_count"] == 2
    assert manifest["artifact_paths"] == {"score_result": "score.json"}
    assert manifest["env_summary"] == [
        {
            "name": "LEWORLDMODEL_POLICY",
            "present": True,
            "source": "env:LEWORLDMODEL_POLICY",
            "secret": False,
        },
        {
            "name": "LEWORLDMODEL_DEVICE",
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
        provider_profile="leworldmodel",
        capability="score",
        status="skipped",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
    )

    assert write_run_manifest(path, manifest) == path
    assert json.loads(path.read_text(encoding="utf-8"))["provider_profile"] == "leworldmodel"


def test_write_run_manifest_rejects_non_finite_payload_before_touching_disk(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "run_manifest.json"
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="skipped",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
    ).to_dict()

    with pytest.raises(WorldForgeError, match="finite number"):
        write_run_manifest(path, {**manifest, "input_summary": {"score": math.nan}})

    assert not path.exists()
    assert not path.parent.exists()


def test_validate_run_manifest_rejects_unknown_status() -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
    ).to_dict()

    with pytest.raises(WorldForgeError, match="status must be passed"):
        validate_run_manifest({**manifest, "status": "success"})


def test_run_manifest_preserves_safe_input_summary() -> None:
    input_summary = {
        "bridge": "pusht",
        "score_shapes": {"action_candidates": [1, 3, 4, 10]},
    }
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("lewm-real",),
        input_summary=input_summary,
    ).to_dict()

    assert manifest["input_summary"] == input_summary
    assert manifest["input_digest"] == digest_json_value(input_summary)


def test_run_manifest_rejects_secret_like_values_and_signed_urls(tmp_path: Path) -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
    ).to_dict()

    with pytest.raises(WorldForgeError, match="secret-like metadata"):
        validate_run_manifest({**manifest, "api_token": "sk-test-token"})

    sanitized = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
        artifact_paths={"video": "https://example.test/video.mp4?X-Amz-Signature=secret"},
    ).to_dict()
    assert sanitized["artifact_paths"] == {"video": "https://example.test/video.mp4"}

    with pytest.raises(WorldForgeError, match=r"secret-like metadata|unsafe URL|normalized"):
        validate_run_manifest(
            {
                **manifest,
                "artifact_paths": {
                    "video": "https://example.test/video.mp4?X-Amz-Signature=secret"
                },
            }
        )


def test_run_manifest_rejects_nested_secret_like_values() -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
    ).to_dict()

    with pytest.raises(WorldForgeError, match="secret-like metadata"):
        validate_run_manifest(
            {
                **manifest,
                "input_summary": {
                    "triage": ["Bearer abc123"],
                },
            }
        )


def test_run_manifest_rejects_host_local_artifact_paths(tmp_path: Path) -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
    ).to_dict()

    with pytest.raises(WorldForgeError, match="absolute host paths"):
        validate_run_manifest({**manifest, "artifact_paths": {"video": str(tmp_path / "v.mp4")}})

    with pytest.raises(WorldForgeError, match="outside the run directory"):
        build_run_manifest(
            run_id="run-1",
            provider_profile="leworldmodel",
            capability="score",
            status="passed",
            env_vars=("LEWORLDMODEL_POLICY",),
            command_argv=("smoke",),
            artifact_paths={"video": tmp_path.parent / "v.mp4"},
            artifact_root=tmp_path,
        )


def test_validate_run_manifest_rejects_malformed_collection_fields() -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        provider_profile="leworldmodel",
        capability="score",
        status="passed",
        env_vars=("LEWORLDMODEL_POLICY",),
        command_argv=("smoke",),
    ).to_dict()

    cases = (
        ("command_argv", [], "command_argv must be a non-empty string list"),
        ("env_summary", {}, "env_summary must be a list"),
        ("artifact_paths", [], "artifact_paths must be an object"),
        ("runtime_assets", {}, "runtime_assets must be a list"),
        ("input_summary", [], "input_summary must be an object"),
    )

    for field_name, value, message in cases:
        with pytest.raises(WorldForgeError, match=message):
            validate_run_manifest({**manifest, field_name: value})


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
