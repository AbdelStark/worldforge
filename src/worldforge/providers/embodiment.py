"""Embodiment action translator contracts for policy providers."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from worldforge.models import Action, JSONDict

from ._policy import json_object, normalize_policy_action_candidates
from .base import ProviderError

ActionTranslatorCallable = Callable[
    [object, JSONDict, JSONDict],
    Sequence[Action] | Sequence[Sequence[Action]],
]


def _materialize(value: object) -> object:
    current = value
    for method_name in ("detach", "cpu"):
        method = getattr(current, method_name, None)
        if callable(method):
            current = method()
    tolist = getattr(current, "tolist", None)
    if callable(tolist):
        return tolist()
    if isinstance(current, tuple):
        return [_materialize(item) for item in current]
    return current


def _numeric_leaf(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProviderError(f"{name} must contain only numeric action values.")
    number = float(value)
    if not math.isfinite(number):
        raise ProviderError(f"{name} must contain only finite action values.")
    return number


def _nested_shape(value: object, *, name: str) -> tuple[int, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if not value:
            raise ProviderError(f"{name} must not contain empty action dimensions.")
        child_shapes = [_nested_shape(child, name=name) for child in value]
        first = child_shapes[0]
        if any(shape != first for shape in child_shapes):
            raise ProviderError(f"{name} must be rectangular.")
        return (len(value), *first)
    _numeric_leaf(value, name=name)
    return ()


def _action_shape(value: object, *, name: str) -> tuple[int, ...]:
    shape = getattr(value, "shape", None)
    if shape is not None:
        try:
            return tuple(int(part) for part in tuple(shape))
        except (TypeError, ValueError):
            pass
    materialized = _materialize(value)
    return _nested_shape(materialized, name=name)


@dataclass(frozen=True)
class EmbodimentTranslatorContract:
    """Validation metadata for a host-owned action translator.

    The contract is intentionally about the boundary, not robot execution. It
    proves the raw policy output belongs to the expected embodiment and has the
    expected tensor shape before a host translator converts it to WorldForge
    ``Action`` objects.
    """

    embodiment_tag: str
    action_dim: int | None = None
    action_horizon: int | None = None
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        tag = self.embodiment_tag.strip()
        if not tag:
            raise ProviderError("embodiment_tag must be a non-empty string.")
        object.__setattr__(self, "embodiment_tag", tag)
        for field_name in ("action_dim", "action_horizon"):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or value <= 0):
                raise ProviderError(f"{field_name} must be an integer greater than 0.")
        normalized_metadata = json_object(self.metadata, name="translator metadata")
        object.__setattr__(self, "metadata", normalized_metadata)

    def validate_raw_actions(
        self,
        raw_actions: object,
        info: JSONDict,
        provider_info: JSONDict,
        *,
        name: str = "raw policy actions",
    ) -> tuple[int, ...]:
        """Validate the embodiment tag and raw action tensor shape."""

        raw_tag = info.get("embodiment_tag") or provider_info.get("embodiment_tag")
        if raw_tag is not None and str(raw_tag).strip() != self.embodiment_tag:
            raise ProviderError(
                f"Embodiment translator for '{self.embodiment_tag}' cannot translate "
                f"actions tagged '{str(raw_tag).strip()}'."
            )
        shape = _action_shape(raw_actions, name=name)
        if self.action_dim is not None and (not shape or shape[-1] != self.action_dim):
            actual = shape[-1] if shape else "scalar"
            raise ProviderError(
                f"Embodiment translator expected action_dim={self.action_dim}, got {actual}."
            )
        if self.action_horizon is not None and (len(shape) < 2 or shape[-2] != self.action_horizon):
            actual = shape[-2] if len(shape) >= 2 else "scalar"
            raise ProviderError(
                "Embodiment translator expected "
                f"action_horizon={self.action_horizon}, got {actual}."
            )
        return shape

    def validate_candidates(self, candidates: Sequence[Sequence[Action]]) -> None:
        if self.action_horizon is None:
            return
        for index, actions in enumerate(candidates):
            if len(actions) != self.action_horizon:
                raise ProviderError(
                    f"Embodiment translator candidate {index} returned {len(actions)} "
                    f"WorldForge action(s), expected {self.action_horizon}."
                )

    def preview_summary(self, *, raw_shape: tuple[int, ...] | None = None) -> JSONDict:
        return {
            "embodiment_tag": self.embodiment_tag,
            "action_dim": self.action_dim,
            "action_horizon": self.action_horizon,
            "raw_action_shape": list(raw_shape) if raw_shape is not None else None,
            "metadata": dict(self.metadata),
        }


class EmbodimentActionTranslator:
    """Callable wrapper that enforces an ``EmbodimentTranslatorContract``."""

    def __init__(
        self,
        contract: EmbodimentTranslatorContract,
        translate: ActionTranslatorCallable,
    ) -> None:
        if not callable(translate):
            raise ProviderError("translate must be callable.")
        self.contract = contract
        self._translate = translate
        self.last_raw_shape: tuple[int, ...] | None = None

    def __call__(
        self,
        raw_actions: object,
        info: JSONDict,
        provider_info: JSONDict,
    ) -> list[list[Action]]:
        raw_shape = self.contract.validate_raw_actions(raw_actions, info, provider_info)
        translated = self._translate(raw_actions, info, provider_info)
        candidates = normalize_policy_action_candidates(
            translated,
            provider_label=f"{self.contract.embodiment_tag} embodiment",
        )
        self.contract.validate_candidates(candidates)
        self.last_raw_shape = raw_shape
        return candidates

    def contract_summary(self) -> JSONDict:
        return self.contract.preview_summary(raw_shape=self.last_raw_shape)
