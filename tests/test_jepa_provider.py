from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from worldforge import Action, WorldForge
from worldforge.providers import JepaProvider, ProviderError
from worldforge.testing import assert_provider_contract, assert_score_conformance

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "providers"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class FakeHubScoringModel:
    def __init__(self, response: object) -> None:
        self.response = response
        self.device: str | None = None
        self.eval_called = False
        self.calls: list[dict[str, Any]] = []

    def to(self, device: str) -> FakeHubScoringModel:
        self.device = device
        return self

    def eval(self) -> FakeHubScoringModel:
        self.eval_called = True
        return self

    def score_actions(
        self,
        *,
        model_path: str,
        info: dict[str, Any],
        action_candidates: object,
    ) -> object:
        self.calls.append(
            {
                "model_path": model_path,
                "info": info,
                "action_candidates": action_candidates,
            }
        )
        return self.response


def test_jepa_profile_is_real_score_only_adapter(monkeypatch) -> None:
    monkeypatch.delenv("JEPA_MODEL_NAME", raising=False)
    monkeypatch.delenv("JEPA_MODEL_PATH", raising=False)

    provider = JepaProvider()
    profile = provider.profile()

    assert profile.implementation_status == "experimental"
    assert profile.capabilities.enabled_names() == ["score"]
    assert profile.required_env_vars == ["JEPA_MODEL_NAME"]
    assert provider.configured() is False
    assert provider.health().healthy is False
    assert "JEPA_MODEL_NAME" in provider.health().details


def test_jepa_legacy_scaffold_env_is_metadata_not_runtime(monkeypatch) -> None:
    monkeypatch.delenv("JEPA_MODEL_NAME", raising=False)
    monkeypatch.setenv("JEPA_MODEL_PATH", "/tmp/old-scaffold-path")

    provider = JepaProvider()
    summary = provider.config_summary().to_dict()

    assert provider.configured() is False
    assert provider.health().healthy is False
    assert "legacy scaffold metadata" in provider.health().details
    assert summary["fields"][0]["name"] == "JEPA_MODEL_NAME"
    assert summary["fields"][0]["present"] is False
    assert summary["fields"][1]["name"] == "JEPA_MODEL_PATH"
    assert summary["fields"][1]["present"] is True
    assert "old-scaffold-path" not in json.dumps(summary)


def test_jepa_scores_through_upstream_torch_hub_contract(tmp_path) -> None:
    payload = _fixture("jepa_wms_success.json")
    model = FakeHubScoringModel(payload["runtime_response"])
    loader_calls: list[dict[str, Any]] = []

    def load_from_hub(hub_repo: str, model_name: str, **kwargs: object) -> object:
        loader_calls.append(
            {
                "hub_repo": hub_repo,
                "model_name": model_name,
                "kwargs": kwargs,
            }
        )
        return model, object()

    provider = JepaProvider(
        model_name="jepa_wm_pusht",
        device="cpu",
        hub_loader=load_from_hub,
        torch_module=object(),
    )
    result = provider.score_actions(
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )

    assert result.provider == "jepa"
    assert result.best_index == 1
    assert result.metadata["model_name"] == "jepa_wm_pusht"
    assert result.metadata["hub_repo"] == "facebookresearch/jepa-wms"
    assert loader_calls == [
        {
            "hub_repo": "facebookresearch/jepa-wms",
            "model_name": "jepa_wm_pusht",
            "kwargs": {"pretrained": True, "device": "cpu"},
        }
    ]
    assert model.calls[-1]["model_path"] == "jepa_wm_pusht"
    assert model.device == "cpu"
    assert model.eval_called is True

    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)
    world = forge.create_world_from_prompt("tabletop Push-T scene", provider="mock")
    candidate_plans = [
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.4, 0.5, 0.0)],
        [Action.move_to(0.7, 0.5, 0.0)],
    ]
    plan = world.plan(
        goal="choose the lowest JEPA latent cost",
        provider="jepa",
        planner="jepa-mpc",
        candidate_actions=candidate_plans,
        score_info=payload["info"],
        score_action_candidates=payload["action_candidates"],
        execution_provider="mock",
    )

    assert plan.provider == "jepa"
    assert plan.actions == candidate_plans[1]
    assert plan.metadata["planning_mode"] == "score"


def test_jepa_contract_helpers_cover_configured_score_provider() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JepaProvider(
        model_name="jepa_wm_pusht",
        hub_loader=lambda *_args, **_kwargs: FakeHubScoringModel(payload["runtime_response"]),
        torch_module=object(),
    )

    assert provider.configured() is True
    assert_score_conformance(
        provider,
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )
    report = assert_provider_contract(
        provider,
        score_info=payload["info"],
        score_action_candidates=payload["action_candidates"],
    )
    assert report.exercised_operations == ["score"]


def test_jepa_rejects_unsupported_scaffold_surrogate_call() -> None:
    provider = JepaProvider(model_name="jepa_wm_pusht")

    with pytest.raises(ProviderError, match="does not implement embed"):
        provider.embed(text="cube")
