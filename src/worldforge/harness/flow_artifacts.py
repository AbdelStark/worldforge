"""Shared harness flow artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass

from worldforge.models import JSONDict


@dataclass(frozen=True, slots=True)
class HarnessArtifactSpec:
    name: str
    path: str

    def descriptor(self, payload: object) -> JSONDict:
        return {
            "path": self.path,
            "payload": payload,
        }


COSMOS_POLICY_REPLAY_ARTIFACT = HarnessArtifactSpec(
    name="cosmos_policy_replay",
    path="artifacts/cosmos-policy-replay.json",
)
GROOT_REPLAY_ARTIFACT = HarnessArtifactSpec(
    name="gr00t_replay",
    path="artifacts/gr00t-replay.json",
)
ROBOTICS_COMPARISON_ARTIFACT = HarnessArtifactSpec(
    name="robotics_comparison",
    path="artifacts/robotics-policy-comparison.json",
)
ROBOTICS_COMPARE_REPLAY_ARTIFACTS: tuple[tuple[str, HarnessArtifactSpec], ...] = (
    ("cosmos-policy", COSMOS_POLICY_REPLAY_ARTIFACT),
    ("gr00t-replay", GROOT_REPLAY_ARTIFACT),
)
