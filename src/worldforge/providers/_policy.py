"""Private helpers shared by embodied policy provider adapters."""

from __future__ import annotations

import math
from collections.abc import Sequence
from contextlib import nullcontext
from typing import Any

from worldforge.models import Action, JSONDict

from .base import ProviderError


def no_grad_context(torch: Any) -> Any:
    """Return ``torch.no_grad()`` when available, otherwise a null context."""

    no_grad = getattr(torch, "no_grad", None)
    return no_grad() if callable(no_grad) else nullcontext()


def prepare_model(model: Any, *, device: str | None) -> Any:
    """Move to device, set eval mode, and disable gradients when the model supports it."""

    if device is not None and hasattr(model, "to"):
        model = model.to(device)
    if hasattr(model, "eval"):
        model = model.eval()
    if hasattr(model, "requires_grad_"):
        model.requires_grad_(False)
    return model


def json_compatible(value: object, *, name: str) -> object:
    """Return a JSON-compatible copy of provider-native output."""

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return json_compatible(tolist(), name=name)
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int | float):
        number = float(value)
        if not math.isfinite(number):
            raise ProviderError(f"{name} must contain only finite numbers.")
        return value
    if isinstance(value, dict):
        normalized: JSONDict = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ProviderError(f"{name} keys must be non-empty strings.")
            normalized[key.strip()] = json_compatible(child, name=f"{name}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [
            json_compatible(child, name=f"{name}[{index}]") for index, child in enumerate(value)
        ]
    raise ProviderError(f"{name} must be JSON-compatible.")


def json_object(value: object, *, name: str) -> JSONDict:
    """Return a JSON object after normalizing provider-native containers."""

    normalized = json_compatible(value, name=name)
    if not isinstance(normalized, dict):
        raise ProviderError(f"{name} must be a JSON object.")
    return normalized


def normalize_policy_action_candidates(
    value: Sequence[Action] | Sequence[Sequence[Action]],
    *,
    provider_label: str,
) -> list[list[Action]]:
    """Normalize a translator result to candidate action plans."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or not value:
        raise ProviderError(
            f"{provider_label} action translator must return a non-empty action sequence."
        )
    if all(isinstance(item, Action) for item in value):
        return [list(value)]  # type: ignore[list-item]

    candidates: list[list[Action]] = []
    for index, candidate in enumerate(value):
        if (
            not isinstance(candidate, Sequence)
            or isinstance(candidate, str | bytes)
            or not candidate
        ):
            raise ProviderError(
                f"{provider_label} action translator candidate {index} must be a non-empty "
                "action sequence."
            )
        actions = list(candidate)
        if not all(isinstance(action, Action) for action in actions):
            raise ProviderError(
                f"{provider_label} action translator candidate {index} must contain only "
                "Action instances."
            )
        candidates.append(actions)
    return candidates
