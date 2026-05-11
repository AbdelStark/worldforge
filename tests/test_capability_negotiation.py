"""Tests for the capability negotiation report (WF-FEAT-010)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from worldforge import (
    CAPABILITY_NEGOTIATION_SCHEMA_VERSION,
    CapabilityNegotiationReport,
    CapabilityProviderStatus,
    ProviderCapabilities,
    WorkflowNegotiation,
    WorkflowSpec,
    WorldForge,
    WorldForgeError,
    get_workflow,
    list_workflow_names,
    list_workflows,
    negotiate_capabilities,
)
from worldforge.capability_negotiation import negotiate
from worldforge.providers import BaseProvider, ProviderProfileSpec

ROOT = Path(__file__).resolve().parents[1]
DEMO_SHOWCASES = ROOT / "scripts" / "demo_showcases.py"

REMOTE_ENV_VARS = (
    "COSMOS_BASE_URL",
    "RUNWAYML_API_SECRET",
    "RUNWAY_API_SECRET",
    "LEWORLDMODEL_POLICY",
    "LEWM_POLICY",
    "LEROBOT_POLICY_PATH",
    "LEROBOT_POLICY",
    "GROOT_POLICY_HOST",
)


def _clear_remote_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in REMOTE_ENV_VARS:
        monkeypatch.delenv(env, raising=False)


def test_known_workflows_are_listed_in_display_order() -> None:
    names = list_workflow_names()
    workflows = list_workflows()
    assert names == tuple(spec.name for spec in workflows)
    assert "generate-only" in names
    assert "policy-plus-score" in names
    assert "evaluation-physics" in names


def test_workflow_spec_validates_required_capabilities() -> None:
    with pytest.raises(WorldForgeError, match="non-empty string"):
        WorkflowSpec(
            name="",
            title="x",
            description="x",
            required_capabilities=("predict",),
        )
    with pytest.raises(WorldForgeError, match="at least one required capability"):
        WorkflowSpec(
            name="bogus",
            title="bogus",
            description="bogus",
            required_capabilities=(),
        )
    with pytest.raises(WorldForgeError, match="unknown capabilities"):
        WorkflowSpec(
            name="bogus",
            title="bogus",
            description="bogus",
            required_capabilities=("not-a-capability",),
        )


def test_get_workflow_rejects_unknown_name() -> None:
    with pytest.raises(WorldForgeError, match="Unknown workflow"):
        get_workflow("does-not-exist")


def test_predict_only_workflow_is_ready_with_mock_alone(monkeypatch, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["predict-only"], forge=forge)
    assert isinstance(report, CapabilityNegotiationReport)
    assert report.schema_version == CAPABILITY_NEGOTIATION_SCHEMA_VERSION
    assert len(report.workflows) == 1
    negotiation = report.workflows[0]
    assert negotiation.ready is True
    assert "mock" in negotiation.summary()
    assert all(req.ready for req in negotiation.requirements)


def test_score_only_workflow_blocked_when_runtime_missing(monkeypatch, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["score-only"], forge=forge)
    negotiation = report.workflows[0]
    assert negotiation.ready is False
    requirement = negotiation.requirements[0]
    assert requirement.capability == "score"
    assert any(
        status.readiness == "missing-config" and status.name == "leworldmodel"
        for status in requirement.candidates
    )
    assert negotiation.recommended_actions
    assert any("leworldmodel" in action for action in negotiation.recommended_actions)


def test_policy_plus_score_workflow_lists_both_provider_pools(monkeypatch, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["policy-plus-score"], forge=forge)
    negotiation = report.workflows[0]
    assert negotiation.ready is False
    capabilities = {req.capability for req in negotiation.requirements}
    assert capabilities == {"policy", "score"}
    policy_req = next(req for req in negotiation.requirements if req.capability == "policy")
    score_req = next(req for req in negotiation.requirements if req.capability == "score")
    policy_names = {status.name for status in policy_req.candidates}
    score_names = {status.name for status in score_req.candidates}
    assert {"gr00t", "lerobot"} <= policy_names
    assert "leworldmodel" in score_names
    assert any("policy" in action for action in negotiation.recommended_actions)
    assert any("score" in action for action in negotiation.recommended_actions)


def test_workflow_becomes_ready_once_runtime_env_is_set(monkeypatch, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    monkeypatch.setenv("COSMOS_BASE_URL", "https://cosmos.example/api")
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["generate-only"], forge=forge)
    negotiation = report.workflows[0]
    # generate-only is satisfied by mock alone; the test still confirms cosmos is no longer
    # blocked on missing-config now that COSMOS_BASE_URL is set.
    assert negotiation.ready is True
    requirement = negotiation.requirements[0]
    cosmos = next((status for status in requirement.candidates if status.name == "cosmos"), None)
    assert cosmos is not None
    assert cosmos.readiness != "missing-config"


def test_unsupported_capability_for_unconfigured_provider_classifies_correctly(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["generate-only"], forge=forge)
    negotiation = report.workflows[0]
    requirement = negotiation.requirements[0]
    cosmos = next(status for status in requirement.candidates if status.name == "cosmos")
    assert cosmos.capability_compatible is True
    assert cosmos.readiness == "missing-config"
    assert "COSMOS_BASE_URL" in (cosmos.reason or "")


def test_negotiate_default_covers_every_workflow(monkeypatch, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(forge=forge)
    assert len(report.workflows) == len(list_workflow_names())
    payload = report.to_dict()
    assert payload["schema_version"] == CAPABILITY_NEGOTIATION_SCHEMA_VERSION
    assert payload["workflow_count"] == len(report.workflows)


def test_report_renders_markdown(monkeypatch, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["policy-plus-score"], forge=forge)
    markdown = report.to_markdown()
    assert "# Capability Negotiation Report" in markdown
    assert "Policy + score workflow" in markdown
    assert "Required capabilities: policy, score" in markdown
    assert "BLOCKED" in markdown
    assert "Recommended actions" in markdown


def test_capability_negotiation_preflight_demo_preserves_blockers(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location(
        "worldforge_capability_negotiation_preflight_demo_test",
        DEMO_SHOWCASES,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    results = module.run_workflows(
        "capability-negotiation-preflight",
        workspace_dir=tmp_path,
        overwrite=True,
    )
    summary_path = Path(results[0]["artifact_paths"]["summary_json"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report = summary["report"]

    assert {"ready", "missing-config", "missing-dependency", "not-registered"} <= set(
        report["readiness_values"]
    )
    assert report["unsupported_example"]["readiness"] == "unsupported"
    assert "policy-plus-score" in report["workflow_shapes"]
    assert report["recommended_actions"]


def test_workflow_negotiation_to_dict_round_trip(tmp_path, monkeypatch) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["generate-only"], forge=forge)
    payload = report.workflows[0].to_dict()
    assert payload["workflow"]["name"] == "generate-only"
    assert payload["ready"] is True
    assert payload["requirements"][0]["candidates"]


def test_negotiate_capabilities_alias_matches(tmp_path, monkeypatch) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    via_alias = negotiate_capabilities(["predict-only"], forge=forge)
    via_module = negotiate(["predict-only"], forge=forge)
    assert via_alias.to_dict() == via_module.to_dict()


def test_unsupported_capability_classified_when_provider_does_not_advertise() -> None:
    """A provider without the capability is classified ``unsupported``."""

    class _StubBareProvider(BaseProvider):
        def __init__(self, *, name: str = "bare-policy") -> None:
            super().__init__(
                name=name,
                capabilities=ProviderCapabilities(predict=True),
                profile=ProviderProfileSpec(
                    description="Stub provider with predict only.",
                    is_local=True,
                    deterministic=True,
                    requires_credentials=False,
                ),
            )

    from worldforge.capability_negotiation import _classify_provider

    provider = _StubBareProvider()

    class _Forge:
        def providers(self):
            return [provider.name]

        def _require_provider(self, name):
            assert name == provider.name
            return provider

    status = _classify_provider(
        name=provider.name,
        capability="policy",
        capabilities=provider.profile().capabilities,
        registered=True,
        forge=_Forge(),  # type: ignore[arg-type]
        environ={},
    )
    assert status.readiness == "unsupported"
    assert status.capability_compatible is False


def test_cli_negotiate_lists_workflows(monkeypatch, capsys) -> None:
    _clear_remote_env(monkeypatch)
    from worldforge.cli import _build_parser, _cmd_negotiate
    from worldforge.framework import WorldForge as _WorldForge

    parser = _build_parser()
    args = parser.parse_args(["negotiate", "--list", "--format", "json"])
    forge = _WorldForge(state_dir=None)
    rc = _cmd_negotiate(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    names = {entry["name"] for entry in payload["workflows"]}
    assert "policy-plus-score" in names


def test_cli_negotiate_runs_workflow_in_json(monkeypatch, capsys, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    from worldforge.cli import _build_parser, _cmd_negotiate
    from worldforge.framework import WorldForge as _WorldForge

    parser = _build_parser()
    args = parser.parse_args(
        ["negotiate", "--workflow", "predict-only", "--format", "json"],
    )
    forge = _WorldForge(state_dir=tmp_path)
    rc = _cmd_negotiate(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["workflows"][0]["workflow"]["name"] == "predict-only"
    assert payload["workflows"][0]["ready"] is True


def test_cli_negotiate_exits_nonzero_when_blocked(monkeypatch, capsys, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    from worldforge.cli import _build_parser, _cmd_negotiate
    from worldforge.framework import WorldForge as _WorldForge

    parser = _build_parser()
    args = parser.parse_args(["negotiate", "--workflow", "policy-plus-score"])
    forge = _WorldForge(state_dir=tmp_path)
    rc = _cmd_negotiate(args, forge)
    out = capsys.readouterr().out
    assert rc == 1
    assert "BLOCKED" in out
    assert "Recommended actions" in out


def test_cli_negotiate_lists_workflows_in_markdown(monkeypatch, capsys) -> None:
    _clear_remote_env(monkeypatch)
    from worldforge.cli import _build_parser, _cmd_negotiate
    from worldforge.framework import WorldForge as _WorldForge

    parser = _build_parser()
    args = parser.parse_args(["negotiate", "--list"])
    forge = _WorldForge(state_dir=None)
    rc = _cmd_negotiate(args, forge)
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Known Workflows" in out
    assert "policy-plus-score" in out


def test_provider_status_to_dict_shape() -> None:
    status = CapabilityProviderStatus(
        name="x",
        capability="score",
        registered=False,
        capability_compatible=True,
        configured=False,
        healthy=False,
        readiness="missing-config",
        reason="missing FOO",
    )
    payload = status.to_dict()
    assert payload["name"] == "x"
    assert payload["capability"] == "score"
    assert payload["readiness"] == "missing-config"


def test_top_level_module_exports_negotiation_symbols() -> None:
    import worldforge

    assert worldforge.WorkflowSpec is WorkflowSpec
    assert worldforge.WorkflowNegotiation is WorkflowNegotiation
    assert worldforge.CapabilityNegotiationReport is CapabilityNegotiationReport
    assert worldforge.CapabilityProviderStatus is CapabilityProviderStatus
    assert worldforge.negotiate_capabilities is negotiate_capabilities
