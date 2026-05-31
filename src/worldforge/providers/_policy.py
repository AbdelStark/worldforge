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
    if _is_json_scalar(value):
        return value
    if isinstance(value, int | float):
        return _json_number(value, name=name)
    if isinstance(value, dict):
        return _json_object(value, name=name)
    if _is_json_sequence(value):
        return _json_array(value, name=name)
    raise ProviderError(f"{name} must be JSON-compatible.")


def _is_json_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | bool)


def _json_number(value: int | float, *, name: str) -> int | float:
    if not math.isfinite(float(value)):
        raise ProviderError(f"{name} must contain only finite numbers.")
    return value


def _json_object(value: dict[object, object], *, name: str) -> JSONDict:
    normalized: JSONDict = {}
    for key, child in value.items():
        normalized[_json_object_key(key, name=name)] = json_compatible(
            child,
            name=f"{name}.{key}",
        )
    return normalized


def _json_object_key(key: object, *, name: str) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ProviderError(f"{name} keys must be non-empty strings.")
    return key.strip()


def _is_json_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)


def _json_array(value: Sequence[object], *, name: str) -> list[object]:
    return [json_compatible(child, name=f"{name}[{index}]") for index, child in enumerate(value)]


def json_object(value: object, *, name: str) -> JSONDict:
    """Return a JSON object after normalizing provider-native containers."""

    normalized = json_compatible(value, name=name)
    if not isinstance(normalized, dict):
        raise ProviderError(f"{name} must be a JSON object.")
    return normalized


def policy_info_object(info: object, *, provider_label: str) -> JSONDict:
    if not isinstance(info, dict):
        raise ProviderError(f"{provider_label} policy info must be a JSON object.")
    return info


def policy_observation(
    info: JSONDict,
    *,
    provider_label: str,
    require_non_empty: bool = False,
    required_any_keys: tuple[str, ...] = (),
    validate_keys: bool = False,
) -> JSONDict:
    observation = info.get("observation")
    if not isinstance(observation, dict) or (require_non_empty and not observation):
        qualifier = "non-empty " if require_non_empty else ""
        raise ProviderError(
            f"{provider_label} policy info.observation must be a {qualifier}JSON object."
        )
    if validate_keys:
        _validate_policy_observation_keys(observation, provider_label=provider_label)
    if required_any_keys and not any(key in observation for key in required_any_keys):
        options = _format_required_key_options(required_any_keys)
        raise ProviderError(
            f"{provider_label} policy observation must include at least one of {options}."
        )
    return dict(observation)


def _format_required_key_options(required_any_keys: tuple[str, ...]) -> str:
    if len(required_any_keys) == 1:
        return required_any_keys[0]
    return f"{', '.join(required_any_keys[:-1])}, or {required_any_keys[-1]}"


def _validate_policy_observation_keys(
    observation: dict[object, object],
    *,
    provider_label: str,
) -> None:
    for key in observation:
        if not isinstance(key, str) or not key.strip():
            raise ProviderError(
                f"{provider_label} policy observation keys must be non-empty strings."
            )


def policy_options(info: JSONDict, *, provider_label: str) -> JSONDict | None:
    options = info.get("options")
    if options is not None and not isinstance(options, dict):
        raise ProviderError(
            f"{provider_label} policy info.options must be a JSON object when provided."
        )
    return dict(options) if isinstance(options, dict) else None


def policy_mode(
    info: JSONDict,
    *,
    provider_label: str,
    default: str,
    choices: tuple[str, ...],
) -> str:
    mode = info.get("mode", default)
    if isinstance(mode, str):
        normalized = mode.strip()
        if normalized in choices:
            return normalized
    formatted = " or ".join(f"'{choice}'" for choice in choices)
    raise ProviderError(f"{provider_label} policy info.mode must be {formatted}.")


def policy_action_horizon(
    info: JSONDict,
    *,
    provider_label: str,
    value_name: str,
    allow_string: bool = False,
) -> int | None:
    value = info.get("action_horizon")
    if value is None:
        return None
    if allow_string and isinstance(value, str):
        value = _policy_action_horizon_from_string(value, value_name=value_name)
        if value is None:
            return None
    elif isinstance(value, bool) or not isinstance(value, int):
        subject = value_name if allow_string else f"{provider_label} info.action_horizon"
        raise ProviderError(f"{subject} must be an integer greater than 0.")
    if value <= 0:
        raise ProviderError(f"{value_name} must be an integer greater than 0.")
    return value


def _policy_action_horizon_from_string(value: str, *, value_name: str) -> int | None:
    if not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        raise ProviderError(f"{value_name} must be an integer greater than 0.") from None


def policy_embodiment_tag(info: JSONDict, *, provider_label: str) -> str | None:
    embodiment_tag = info.get("embodiment_tag")
    if embodiment_tag is None:
        return None
    if not isinstance(embodiment_tag, str) or not embodiment_tag.strip():
        raise ProviderError(
            f"{provider_label} policy info.embodiment_tag must be a non-empty string when provided."
        )
    return embodiment_tag.strip()


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
