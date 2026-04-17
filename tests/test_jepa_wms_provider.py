from __future__ import annotations

import pytest

from worldforge.providers.base import ProviderError
from worldforge.providers.jepa_wms import JEPAWMSProvider


def test_jepa_wms_profile_starts_as_safe_scaffold() -> None:
    provider = JEPAWMSProvider()
    profile = provider.profile()

    assert profile.name == "jepa-wms"
    assert profile.implementation_status == "scaffold"
    assert profile.supported_tasks == []
    assert provider.planned_capabilities == ("score",)
    assert provider.taxonomy_category == "JEPA latent predictive world model"


def test_jepa_wms_health_reports_missing_configuration(monkeypatch) -> None:
    monkeypatch.delenv("JEPA_WMS_MODEL_PATH", raising=False)

    health = JEPAWMSProvider().health()

    assert health.healthy is False
    assert "JEPA_WMS_MODEL_PATH" in health.details


def test_jepa_wms_health_stays_unhealthy_until_implemented(monkeypatch) -> None:
    monkeypatch.setenv("JEPA_WMS_MODEL_PATH", "/tmp/jepa-wms-checkpoint")

    health = JEPAWMSProvider().health()

    assert health.healthy is False
    assert "no runtime adapter implemented" in health.details


def test_jepa_wms_score_actions_is_not_implemented_yet() -> None:
    provider = JEPAWMSProvider()

    with pytest.raises(ProviderError, match="not implemented"):
        provider.score_actions(info={}, action_candidates=[])
