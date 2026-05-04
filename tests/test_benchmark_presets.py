"""Tests for the benchmark preset registry and CLI integration."""

from __future__ import annotations

import json

import pytest

from worldforge import WorldForgeError
from worldforge.benchmark_presets import (
    PRESET_CATEGORIES,
    BenchmarkPreset,
    get_preset,
    list_preset_names,
    list_presets,
    load_preset_budgets,
    load_preset_inputs,
    preset_budget_payload,
    preset_inputs_payload,
)


def test_preset_catalogue_covers_required_categories() -> None:
    categories = {preset.category for preset in list_presets()}
    assert {"checkout-safe", "remote-media", "prepared-host", "release"} <= categories
    assert categories <= set(PRESET_CATEGORIES)
    names = list_preset_names()
    assert names == tuple(preset.name for preset in list_presets())
    assert len(names) == len(set(names))


@pytest.mark.parametrize("name", list_preset_names())
def test_preset_inputs_and_budgets_load(name: str) -> None:
    preset = get_preset(name)
    inputs = load_preset_inputs(preset)
    assert inputs is not None
    if preset.budget_file is None:
        assert load_preset_budgets(preset) == []
    else:
        budgets = load_preset_budgets(preset)
        assert budgets


def test_get_preset_rejects_unknown_name() -> None:
    with pytest.raises(WorldForgeError, match="Unknown benchmark preset"):
        get_preset("does-not-exist")


def test_checkout_safe_presets_never_skip(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_SECRET", raising=False)
    monkeypatch.delenv("LEWORLDMODEL_POLICY", raising=False)
    monkeypatch.delenv("LEWM_POLICY", raising=False)
    monkeypatch.delenv("LEROBOT_POLICY_PATH", raising=False)
    monkeypatch.delenv("LEROBOT_POLICY", raising=False)
    monkeypatch.delenv("GROOT_POLICY_HOST", raising=False)
    for preset in list_presets():
        if preset.category in ("checkout-safe", "release"):
            assert preset.skip_reason() is None


def test_remote_media_preset_skips_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_SECRET", raising=False)
    preset = get_preset("remote-media-dryrun")
    reason = preset.skip_reason()
    assert reason is not None
    assert "cosmos" in reason
    assert "runway" in reason


def test_remote_media_preset_runs_when_env_present(monkeypatch) -> None:
    monkeypatch.setenv("COSMOS_BASE_URL", "https://cosmos.example/api")
    preset = get_preset("remote-media-dryrun")
    assert preset.skip_reason() is None
    configured = preset.configured_providers()
    assert "cosmos" in configured


def test_prepared_host_preset_skips_when_env_missing(monkeypatch) -> None:
    for env_var in (
        "LEWORLDMODEL_POLICY",
        "LEWM_POLICY",
        "LEROBOT_POLICY_PATH",
        "LEROBOT_POLICY",
        "GROOT_POLICY_HOST",
    ):
        monkeypatch.delenv(env_var, raising=False)
    preset = get_preset("prepared-host")
    reason = preset.skip_reason()
    assert reason is not None
    assert "leworldmodel" in reason
    assert "lerobot" in reason
    assert "gr00t" in reason


def test_preset_payloads_round_trip() -> None:
    for preset in list_presets():
        envelope = preset.to_dict()
        assert envelope["name"] == preset.name
        assert envelope["category"] == preset.category
        if preset.inputs_file is not None:
            payload = preset_inputs_payload(preset)
            assert payload is not None
            assert "inputs" in payload
        if preset.budget_file is not None:
            budget = preset_budget_payload(preset)
            assert budget is not None
            assert "budgets" in budget


def test_invalid_preset_construction_is_rejected() -> None:
    with pytest.raises(WorldForgeError, match="non-empty string"):
        BenchmarkPreset(
            name="",
            title="",
            summary="",
            category="checkout-safe",
            providers=("mock",),
            operations=("predict",),
            iterations=1,
            concurrency=1,
            inputs_file=None,
            budget_file=None,
            failure_tolerance="fail-on-violation",
        )
    with pytest.raises(WorldForgeError, match="category"):
        BenchmarkPreset(
            name="bogus",
            title="bogus",
            summary="bogus",
            category="not-a-category",
            providers=("mock",),
            operations=("predict",),
            iterations=1,
            concurrency=1,
            inputs_file=None,
            budget_file=None,
            failure_tolerance="fail-on-violation",
        )
    with pytest.raises(WorldForgeError, match="failure_tolerance"):
        BenchmarkPreset(
            name="bogus",
            title="bogus",
            summary="bogus",
            category="checkout-safe",
            providers=("mock",),
            operations=("predict",),
            iterations=1,
            concurrency=1,
            inputs_file=None,
            budget_file=None,
            failure_tolerance="other",
        )


def test_cli_lists_presets_in_json(monkeypatch, capsys) -> None:
    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(["benchmark", "--list-presets", "--format", "json"])
    forge = WorldForge(state_dir=None)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    names = {entry["name"] for entry in payload["presets"]}
    assert {"mock-smoke", "parser-overhead", "release-evidence"} <= names


def test_cli_runs_mock_smoke_preset(monkeypatch, capsys, tmp_path) -> None:
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(
        ["benchmark", "--preset", "mock-smoke", "--format", "json", "--state-dir", str(tmp_path)]
    )
    forge = WorldForge(state_dir=tmp_path)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["preset"] == "mock-smoke"
    assert payload["benchmark"]["run_metadata"]["preset"]["name"] == "mock-smoke"
    assert payload["gate"]["passed"] is True


def test_cli_skips_remote_media_dryrun_when_env_missing(monkeypatch, capsys) -> None:
    for env_var in ("COSMOS_BASE_URL", "RUNWAYML_API_SECRET", "RUNWAY_API_SECRET"):
        monkeypatch.delenv(env_var, raising=False)
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(["benchmark", "--preset", "remote-media-dryrun", "--format", "json"])
    forge = WorldForge(state_dir=None)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["status"] == "skipped"
    assert "cosmos" in payload["reason"]


def test_cli_lists_presets_in_markdown(monkeypatch, capsys) -> None:
    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(["benchmark", "--list-presets"])
    forge = WorldForge(state_dir=None)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Benchmark Presets" in out
    assert "## checkout-safe" in out
    assert "mock-smoke" in out


def test_cli_lists_presets_in_csv(monkeypatch, capsys) -> None:
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(["benchmark", "--list-presets", "--format", "csv"])
    forge = WorldForge(state_dir=None)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("name,category,providers,operations,iterations")
    assert "mock-smoke,checkout-safe" in out


def test_cli_runs_preset_in_markdown_with_workspace(tmp_path, capsys) -> None:
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    workspace_dir = tmp_path / "workspace"
    args = parser.parse_args(
        [
            "benchmark",
            "--preset",
            "mock-smoke",
            "--run-workspace",
            str(workspace_dir),
            "--state-dir",
            str(tmp_path / "worlds"),
        ]
    )
    forge = WorldForge(state_dir=tmp_path / "worlds")
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Benchmark Report" in out
    assert "# Benchmark Gate Report" in out
    runs_dir = workspace_dir / "runs"
    assert runs_dir.exists()


def test_cli_preset_csv_output(tmp_path, capsys) -> None:
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(
        ["benchmark", "--preset", "mock-smoke", "--format", "csv", "--state-dir", str(tmp_path)]
    )
    forge = WorldForge(state_dir=tmp_path)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("provider,operation,metric")  # gate CSV preferred when budgets present


def test_cli_skips_remote_media_dryrun_in_markdown(monkeypatch, capsys) -> None:
    for env_var in ("COSMOS_BASE_URL", "RUNWAYML_API_SECRET", "RUNWAY_API_SECRET"):
        monkeypatch.delenv(env_var, raising=False)
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(["benchmark", "--preset", "remote-media-dryrun"])
    forge = WorldForge(state_dir=None)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    assert "skipped" in out
    assert "cosmos" in out


def test_cli_show_preset_markdown(capsys) -> None:
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(["benchmark", "--show-preset", "release-evidence"])
    forge = WorldForge(state_dir=None)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Release evidence" in out
    assert "Category: release" in out
    assert "Skip reason:" in out


def test_cli_show_preset(monkeypatch, capsys) -> None:
    from worldforge.cli import _build_parser, _cmd_benchmark
    from worldforge.framework import WorldForge

    parser = _build_parser()
    args = parser.parse_args(["benchmark", "--show-preset", "release-evidence", "--format", "json"])
    forge = WorldForge(state_dir=None)
    rc = _cmd_benchmark(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["preset"]["name"] == "release-evidence"
    assert payload["budget_payload"]["budgets"]
