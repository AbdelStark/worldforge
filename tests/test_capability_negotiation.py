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
from worldforge.models import ProviderHealth
from worldforge.providers import BaseProvider, ProviderProfileSpec

ROOT = Path(__file__).resolve().parents[1]
DEMO_SHOWCASES = ROOT / "scripts" / "demo_showcases.py"

REMOTE_ENV_VARS = (
    "COSMOS_POLICY_BASE_URL",
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
    assert "predict-only" in names
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


def test_score_workflow_becomes_ready_with_registered_score_provider(monkeypatch, tmp_path) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)

    class _ReadyScoreProvider(BaseProvider):
        def __init__(self) -> None:
            super().__init__(
                name="ready-score",
                capabilities=ProviderCapabilities(score=True),
                profile=ProviderProfileSpec(
                    description="Ready local score provider.",
                    is_local=True,
                    deterministic=True,
                    requires_credentials=False,
                ),
            )

        def health(self) -> ProviderHealth:
            return ProviderHealth(
                name=self.name,
                healthy=True,
                latency_ms=0.0,
                details="ready",
            )

    forge.register_provider(_ReadyScoreProvider())
    report = negotiate(["score-only"], forge=forge)
    negotiation = report.workflows[0]
    assert negotiation.ready is True
    requirement = negotiation.requirements[0]
    ready_score = next(status for status in requirement.candidates if status.name == "ready-score")
    assert ready_score.readiness == "ready"


def test_unconfigured_score_provider_classifies_missing_config(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    report = negotiate(["score-only"], forge=forge)
    negotiation = report.workflows[0]
    requirement = negotiation.requirements[0]
    leworldmodel = next(
        status for status in requirement.candidates if status.name == "leworldmodel"
    )
    assert leworldmodel.capability_compatible is True
    assert leworldmodel.readiness == "missing-config"
    assert "LEWORLDMODEL_POLICY" in (leworldmodel.reason or "")


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
    report = negotiate(["predict-only"], forge=forge)
    payload = report.workflows[0].to_dict()
    assert payload["workflow"]["name"] == "predict-only"
    assert payload["ready"] is True
    assert payload["requirements"][0]["candidates"]


def test_negotiate_capabilities_alias_matches(tmp_path, monkeypatch) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    via_alias = negotiate_capabilities(["predict-only"], forge=forge)
    via_module = negotiate(["predict-only"], forge=forge)
    assert via_alias.to_dict() == via_module.to_dict()


def test_negotiate_accepts_workflow_specs_and_names_in_order(tmp_path, monkeypatch) -> None:
    _clear_remote_env(monkeypatch)
    forge = WorldForge(state_dir=tmp_path)
    custom = WorkflowSpec(
        name="custom-predict",
        title="Custom predict workflow",
        description="Custom predict-only surface.",
        required_capabilities=("predict",),
    )

    report = negotiate([custom, "predict-only"], forge=forge)

    assert [negotiation.workflow.name for negotiation in report.workflows] == [
        "custom-predict",
        "predict-only",
    ]
    assert all(negotiation.ready for negotiation in report.workflows)


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


def test_registered_unhealthy_provider_classified_as_missing_dependency() -> None:
    class _UnhealthyScoreProvider(BaseProvider):
        def __init__(self) -> None:
            super().__init__(
                name="unhealthy-score",
                capabilities=ProviderCapabilities(score=True),
                profile=ProviderProfileSpec(
                    description="Stub score provider with unhealthy runtime.",
                    is_local=True,
                    deterministic=True,
                    requires_credentials=False,
                ),
            )

        def health(self) -> ProviderHealth:
            return ProviderHealth(
                name=self.name,
                healthy=False,
                latency_ms=0.0,
                details="missing optional scoring runtime",
            )

    from worldforge.capability_negotiation import _classify_provider

    provider = _UnhealthyScoreProvider()

    class _Forge:
        def _require_provider(self, name):
            assert name == provider.name
            return provider

    status = _classify_provider(
        name=provider.name,
        capability="score",
        capabilities=provider.profile().capabilities,
        registered=True,
        forge=_Forge(),  # type: ignore[arg-type]
        environ={},
    )

    assert status.readiness == "missing-dependency"
    assert status.configured is True
    assert status.healthy is False
    assert status.reason == "provider 'unhealthy-score' health check is unhealthy"


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
