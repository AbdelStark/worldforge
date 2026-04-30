"""Checkout-safe LeWorldModel task bridge registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .pusht_showcase_inputs import (
    DEFAULT_ACTION_DIM,
    DEFAULT_HISTORY,
    DEFAULT_HORIZON,
)


@dataclass(frozen=True, slots=True)
class LeWorldModelTaskBridge:
    """Static metadata for a host-owned LeWorldModel task bridge."""

    name: str
    task: str
    observation_module: str
    score_info_module: str
    translator: str
    candidate_builder: str
    expected_action_dim: int
    expected_horizon: int
    shape_summary: dict[str, Any]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "task": self.task,
            "observation_module": self.observation_module,
            "score_info_module": self.score_info_module,
            "translator": self.translator,
            "candidate_builder": self.candidate_builder,
            "expected_action_dim": self.expected_action_dim,
            "expected_horizon": self.expected_horizon,
            "shape_summary": dict(self.shape_summary),
            "description": self.description,
        }


PUSHT_BRIDGE = LeWorldModelTaskBridge(
    name="pusht",
    task="PushT tabletop manipulation",
    observation_module="worldforge.smoke.pusht_showcase_inputs:build_observation",
    score_info_module="worldforge.smoke.pusht_showcase_inputs:build_score_info",
    translator="worldforge.smoke.pusht_showcase_inputs:translate_candidates_contract",
    candidate_builder="worldforge.smoke.pusht_showcase_inputs:build_action_candidates",
    expected_action_dim=DEFAULT_ACTION_DIM,
    expected_horizon=DEFAULT_HORIZON,
    shape_summary={
        "policy_observation": {
            "observation.image": [1, 3, 96, 96],
            "observation.state": [1, 2],
        },
        "score_info": {
            "pixels": [1, 1, DEFAULT_HISTORY, 3, 224, 224],
            "goal": [1, 1, DEFAULT_HISTORY, 3, 224, 224],
            "action": [1, 1, DEFAULT_HISTORY, DEFAULT_ACTION_DIM],
        },
        "action_candidates": [1, 3, DEFAULT_HORIZON, DEFAULT_ACTION_DIM],
        "raw_policy_action": [2],
    },
    description=(
        "Packaged PushT bridge for the LeRobot diffusion PushT policy and the "
        "LeWorldModel PushT object checkpoint. Hosts own the environment reset, "
        "image preprocessing, and the 2D policy action to 10D score tensor mapping."
    ),
)

BRIDGES = {PUSHT_BRIDGE.name: PUSHT_BRIDGE}


def bridge_names() -> tuple[str, ...]:
    """Return registered task bridge names."""

    return tuple(sorted(BRIDGES))


def get_bridge(name: str) -> LeWorldModelTaskBridge:
    """Return a registered bridge or raise a user-facing ValueError."""

    try:
        return BRIDGES[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown LeWorldModel task bridge '{name}'. Available bridges: "
            f"{', '.join(bridge_names())}."
        ) from exc
