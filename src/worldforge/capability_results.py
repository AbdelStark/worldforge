"""Capability result payload data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from worldforge._model_utils import (
    JSONDict,
    WorldForgeError,
    require_finite_number,
    require_json_dict,
    require_positive_int,
)
from worldforge.scene_models import Action


@dataclass(slots=True)
class EmbeddingResult:
    """Embedding output from a provider."""

    provider: str
    model: str
    vector: list[float]

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("EmbeddingResult provider must be a non-empty string.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise WorldForgeError("EmbeddingResult model must be a non-empty string.")
        if not isinstance(self.vector, list) or not self.vector:
            raise WorldForgeError("EmbeddingResult vector must be a non-empty list.")
        self.provider = self.provider.strip()
        self.model = self.model.strip()
        self.vector = [
            require_finite_number(value, name="EmbeddingResult vector value")
            for value in self.vector
        ]

    @property
    def shape(self) -> list[int]:
        return [len(self.vector)]


@dataclass(slots=True)
class ActionScoreResult:
    """Provider scores for a batch of candidate action sequences.

    Scores are provider-defined, but ``best_index`` must identify the candidate the
    provider recommends for downstream planning.
    """

    provider: str
    scores: list[float]
    best_index: int
    lower_is_better: bool = True
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.provider = _validated_score_provider(self.provider)
        self.scores = _validated_action_scores(self.scores)
        self.best_index = _validated_score_best_index(
            self.best_index,
            score_count=len(self.scores),
        )
        self.lower_is_better = _validated_score_direction(self.lower_is_better)
        _validate_score_best_index_direction(
            scores=self.scores,
            best_index=self.best_index,
            lower_is_better=self.lower_is_better,
        )
        self.metadata = _validated_score_metadata(self.metadata)

    @property
    def best_score(self) -> float:
        return self.scores[self.best_index]

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "scores": list(self.scores),
            "best_index": self.best_index,
            "best_score": self.best_score,
            "lower_is_better": self.lower_is_better,
            "metadata": dict(self.metadata),
        }


def _validated_score_provider(provider: object) -> str:
    if not isinstance(provider, str) or not provider.strip():
        raise WorldForgeError("ActionScoreResult provider must be a non-empty string.")
    return provider.strip()


def _validated_action_scores(scores: object) -> list[float]:
    if not isinstance(scores, list) or not scores:
        raise WorldForgeError("ActionScoreResult scores must be a non-empty list.")
    return [require_finite_number(score, name="ActionScoreResult score") for score in scores]


def _validated_score_best_index(best_index: object, *, score_count: int) -> int:
    if isinstance(best_index, bool) or not isinstance(best_index, int):
        raise WorldForgeError("ActionScoreResult best_index is out of range.")
    if best_index < 0 or best_index >= score_count:
        raise WorldForgeError("ActionScoreResult best_index is out of range.")
    return best_index


def _validated_score_direction(lower_is_better: object) -> bool:
    if not isinstance(lower_is_better, bool):
        raise WorldForgeError("ActionScoreResult lower_is_better must be a boolean.")
    return lower_is_better


def _validate_score_best_index_direction(
    *,
    scores: list[float],
    best_index: int,
    lower_is_better: bool,
) -> None:
    expected_best_score = min(scores) if lower_is_better else max(scores)
    if scores[best_index] == expected_best_score:
        return
    raise WorldForgeError("ActionScoreResult best_index must match lower_is_better direction.")


def _validated_score_metadata(metadata: object) -> JSONDict:
    if not isinstance(metadata, dict):
        raise WorldForgeError("ActionScoreResult metadata must be a JSON object.")
    return require_json_dict(metadata, name="ActionScoreResult metadata")


@dataclass(slots=True)
class ActionPolicyResult:
    """Provider-selected action chunk from an embodied policy.

    Policy providers choose or propose actions from observations. They do not imply future-state
    prediction or candidate scoring unless the provider exposes those capabilities separately.
    ``action_candidates`` stores one or more executable candidate plans when the policy can expose
    alternatives for downstream scoring.
    """

    provider: str
    actions: list[Action]
    raw_actions: JSONDict = field(default_factory=dict)
    action_horizon: int | None = None
    embodiment_tag: str | None = None
    metadata: JSONDict = field(default_factory=dict)
    action_candidates: list[list[Action]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.provider = self._normalized_provider()
        self.actions = self._normalized_actions()
        self.raw_actions = self._normalized_raw_actions()
        self.action_horizon = self._normalized_action_horizon()
        self.embodiment_tag = self._normalized_embodiment_tag()
        self.metadata = self._normalized_metadata()
        self.action_candidates = self._normalized_action_candidates()

    def _normalized_provider(self) -> str:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("ActionPolicyResult provider must be a non-empty string.")
        return self.provider.strip()

    def _normalized_actions(self) -> list[Action]:
        if not isinstance(self.actions, list) or not self.actions:
            raise WorldForgeError("ActionPolicyResult actions must be a non-empty list.")
        if not all(isinstance(action, Action) for action in self.actions):
            raise WorldForgeError("ActionPolicyResult actions must contain only Action instances.")
        return list(self.actions)

    def _normalized_raw_actions(self) -> JSONDict:
        if not isinstance(self.raw_actions, dict):
            raise WorldForgeError("ActionPolicyResult raw_actions must be a JSON object.")
        return require_json_dict(
            self.raw_actions,
            name="ActionPolicyResult raw_actions",
        )

    def _normalized_action_horizon(self) -> int | None:
        if self.action_horizon is None:
            return None
        return require_positive_int(
            self.action_horizon,
            name="ActionPolicyResult action_horizon",
        )

    def _normalized_embodiment_tag(self) -> str | None:
        if self.embodiment_tag is None:
            return None
        if not isinstance(self.embodiment_tag, str) or not self.embodiment_tag.strip():
            raise WorldForgeError(
                "ActionPolicyResult embodiment_tag must be a non-empty string when provided."
            )
        return self.embodiment_tag.strip()

    def _normalized_metadata(self) -> JSONDict:
        if not isinstance(self.metadata, dict):
            raise WorldForgeError("ActionPolicyResult metadata must be a JSON object.")
        return require_json_dict(
            self.metadata,
            name="ActionPolicyResult metadata",
        )

    def _normalized_action_candidates(self) -> list[list[Action]]:
        if not isinstance(self.action_candidates, list):
            raise WorldForgeError("ActionPolicyResult action_candidates must be a list.")
        if not self.action_candidates:
            return [list(self.actions)]
        return [
            self._normalized_action_candidate(candidate, index=index)
            for index, candidate in enumerate(self.action_candidates)
        ]

    @staticmethod
    def _normalized_action_candidate(candidate: object, *, index: int) -> list[Action]:
        if not isinstance(candidate, list) or not candidate:
            raise WorldForgeError(
                "ActionPolicyResult action_candidates must contain non-empty action lists."
            )
        if not all(isinstance(action, Action) for action in candidate):
            raise WorldForgeError(
                f"ActionPolicyResult action_candidates[{index}] must contain only Action instances."
            )
        return list(candidate)

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "actions": [action.to_dict() for action in self.actions],
            "raw_actions": dict(self.raw_actions),
            "action_horizon": self.action_horizon,
            "embodiment_tag": self.embodiment_tag,
            "metadata": dict(self.metadata),
            "action_candidates": [
                [action.to_dict() for action in candidate] for candidate in self.action_candidates
            ],
        }
