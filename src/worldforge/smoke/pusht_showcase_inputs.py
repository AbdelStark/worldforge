"""Packaged PushT inputs for the real LeRobot + LeWorldModel showcase.

These helpers are intentionally narrow: they build a PushT observation and
LeWorldModel score tensors from the upstream ``stable_worldmodel`` PushT
environment, then bridge the selected LeRobot action into checkpoint-native
LeWorldModel action candidates. The optional imports stay inside the functions
so WorldForge's base package remains lightweight.
"""

from __future__ import annotations

from typing import Any

DEFAULT_OBSERVATION_SEED = 7
DEFAULT_GOAL_SEED = 11
DEFAULT_IMAGE_SIZE = 224
DEFAULT_POLICY_IMAGE_SIZE = 96
DEFAULT_HISTORY = 3
DEFAULT_HORIZON = 4
DEFAULT_ACTION_DIM = 10
DEFAULT_ACTION_BLOCK = 5


def pusht_translator_contract() -> object:
    """Return the checkout-safe PushT translator contract without importing optional runtimes."""

    from worldforge.providers import EmbodimentTranslatorContract

    return EmbodimentTranslatorContract(
        embodiment_tag="pusht",
        action_dim=2,
        metadata={
            "task": "pusht",
            "raw_policy_space": "xy",
            "worldforge_action": "move_to",
            "score_action_dim": DEFAULT_ACTION_DIM,
        },
    )


def _materialize(value: object) -> object:
    current = value
    for method_name in ("detach", "cpu"):
        method = getattr(current, method_name, None)
        if callable(method):
            current = method()
    return current


def _real_pusht_frame(seed: int = DEFAULT_OBSERVATION_SEED) -> tuple[object, object, object]:
    try:
        import numpy as np
        import torch
        import torch.nn.functional as functional
        from stable_worldmodel.envs.pusht.env import PushT
    except ImportError as exc:
        raise RuntimeError(
            "PushT showcase inputs require stable_worldmodel, torch, numpy, and the "
            "PushT environment dependencies. Run scripts/robotics-showcase so uv installs "
            "the host-owned optional runtime set for this process."
        ) from exc

    env = PushT(render_mode="rgb_array", resolution=DEFAULT_IMAGE_SIZE)
    observation, _info = env.reset(seed=seed)
    frame = env.render()
    frame_tensor = torch.as_tensor(np.asarray(frame), dtype=torch.float32).permute(2, 0, 1) / 255.0
    policy_image = functional.interpolate(
        frame_tensor.unsqueeze(0),
        size=(DEFAULT_POLICY_IMAGE_SIZE, DEFAULT_POLICY_IMAGE_SIZE),
        mode="bilinear",
        align_corners=False,
    )
    state = torch.as_tensor(observation["proprio"][:2], dtype=torch.float32).unsqueeze(0)
    return frame_tensor, policy_image, state


def build_observation() -> dict[str, Any]:
    """Build a LeRobot PushT observation from the upstream PushT environment."""

    _frame, policy_image, state = _real_pusht_frame(seed=DEFAULT_OBSERVATION_SEED)
    return {
        "observation.image": policy_image,
        "observation.state": state,
    }


def build_score_info() -> dict[str, Any]:
    """Build LeWorldModel score tensors aligned to the packaged PushT showcase."""

    import torch

    current_frame, _policy_image, _state = _real_pusht_frame(seed=DEFAULT_OBSERVATION_SEED)
    goal_frame, _goal_policy_image, _goal_state = _real_pusht_frame(seed=DEFAULT_GOAL_SEED)
    return {
        "pixels": current_frame.repeat(DEFAULT_HISTORY, 1, 1, 1).unsqueeze(0).unsqueeze(0),
        "goal": goal_frame.repeat(DEFAULT_HISTORY, 1, 1, 1).unsqueeze(0).unsqueeze(0),
        "action": torch.zeros(1, 1, DEFAULT_HISTORY, DEFAULT_ACTION_DIM, dtype=torch.float32),
    }


def _raw_xy(raw_actions: object) -> object:
    import torch

    raw = _materialize(raw_actions)
    tensor = torch.as_tensor(raw, dtype=torch.float32).reshape(-1)
    if tensor.numel() < 2:
        raise ValueError("LeRobot PushT action must contain at least x and y.")
    return tensor[:2].clamp(-1.0, 1.0)


def _candidate_xy(raw_actions: object) -> object:
    import torch

    base = _raw_xy(raw_actions)
    return torch.stack(
        [
            base,
            base * 0.5,
            -base * 0.5,
        ],
        dim=0,
    )


def build_action_candidates(
    raw_actions: object,
    _info: dict[str, Any],
    _provider_info: dict[str, Any],
) -> object:
    """Bridge a PushT LeRobot action into LeWorldModel candidate tensors.

    LeWorldModel's PushT object checkpoint expects 10-dimensional blocked
    actions. The bridge repeats the two policy coordinates into the known
    PushT action-block structure instead of silently projecting arbitrary
    embodiments into a different action space.
    """

    import torch

    xy = _candidate_xy(raw_actions)
    blocked = xy.repeat_interleave(DEFAULT_ACTION_BLOCK, dim=1)
    return blocked.unsqueeze(0).unsqueeze(2).repeat(1, 1, DEFAULT_HORIZON, 1).to(torch.float32)


def translate_candidates(
    raw_actions: object,
    info: dict[str, Any],
    _provider_info: dict[str, Any],
) -> list[list[Any]]:
    """Translate PushT candidate ``x, y`` values into visual WorldForge moves."""

    from worldforge import Action

    object_id = "pusht-block"
    bridge = info.get("score_bridge")
    if isinstance(bridge, dict):
        object_id = str(bridge.get("object_id") or object_id)

    plans = []
    for xy in _candidate_xy(raw_actions):
        x = 0.5 + float(xy[0]) * 0.25
        y = 0.5 + float(xy[1]) * 0.25
        plans.append([Action.move_to(x, y, 0.0, object_id=object_id)])
    return plans


def translate_candidates_with_contract() -> object:
    """Return a PushT translator callable that validates embodiment and raw shape."""

    from worldforge.providers import EmbodimentActionTranslator

    return EmbodimentActionTranslator(pusht_translator_contract(), translate_candidates)


translate_candidates_contract = translate_candidates_with_contract()
