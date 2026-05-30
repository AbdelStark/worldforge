from __future__ import annotations

import pytest

from worldforge.providers.base import ProviderError
from worldforge.providers.embodiment import EmbodimentTranslatorContract


def test_embodiment_contract_uses_provider_info_tag_when_info_omits_tag() -> None:
    contract = EmbodimentTranslatorContract(embodiment_tag="aloha", action_dim=3)

    with pytest.raises(ProviderError, match="cannot translate actions tagged 'so100'"):
        contract.validate_raw_actions(
            [[0.1, 0.5, 0.0]],
            {},
            {"embodiment_tag": "so100"},
        )


def test_embodiment_contract_reports_scalar_shape_for_dim_and_horizon_mismatches() -> None:
    dim_contract = EmbodimentTranslatorContract(embodiment_tag="aloha", action_dim=3)

    with pytest.raises(ProviderError, match="action_dim=3, got scalar"):
        dim_contract.validate_raw_actions(0.1, {"embodiment_tag": "aloha"}, {})

    horizon_contract = EmbodimentTranslatorContract(embodiment_tag="aloha", action_horizon=2)

    with pytest.raises(ProviderError, match="action_horizon=2, got scalar"):
        horizon_contract.validate_raw_actions([0.1, 0.5, 0.0], {"embodiment_tag": "aloha"}, {})
