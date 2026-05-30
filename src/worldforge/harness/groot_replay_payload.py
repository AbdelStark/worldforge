"""Deterministic raw-action payloads for the checkout-safe GR00T replay."""

from __future__ import annotations

import math

from worldforge.models import JSONDict

_GROOT_REPLAY_EEF_PREFIX_ROWS = (
    (
        0.45209485,
        -0.04993579,
        0.35151827,
        0.99991280,
        -0.00503587,
        -0.01220623,
        0.00520440,
        0.99989104,
        0.01381495,
    ),
    (
        0.45370448,
        -0.05460007,
        0.35082236,
        0.99975926,
        -0.00603632,
        -0.02109618,
        0.00664691,
        0.99955750,
        0.02899381,
    ),
    (
        0.45319659,
        -0.04851697,
        0.35273436,
        0.99879819,
        -0.01500455,
        -0.04665894,
        0.01667653,
        0.99922508,
        0.03565361,
    ),
    (
        0.45103294,
        -0.05216613,
        0.35121581,
        0.99818760,
        -0.01888346,
        -0.05713980,
        0.02149428,
        0.99873638,
        0.04542767,
    ),
    (
        0.45371175,
        -0.04883665,
        0.35304552,
        0.99673748,
        -0.02772977,
        -0.07579842,
        0.03198496,
        0.99794549,
        0.05551316,
    ),
    (
        0.45116049,
        -0.04859919,
        0.35463876,
        0.99458879,
        -0.04060974,
        -0.09562392,
        0.04728588,
        0.99652177,
        0.06861795,
    ),
    (
        0.45225149,
        -0.04907730,
        0.35640752,
        0.99183750,
        -0.05253663,
        -0.11618217,
        0.06253119,
        0.99449146,
        0.08412262,
    ),
    (
        0.45332921,
        -0.04459824,
        0.35799032,
        0.98470002,
        -0.05842229,
        -0.16417292,
        0.07588259,
        0.99186796,
        0.10217515,
    ),
)
_GROOT_REPLAY_GRIPPER_PREFIX_ROWS = (
    (0.00195312,),
    (0.0,),
    (0.00390625,),
    (0.0,),
    (0.00195312,),
    (0.0,),
    (0.0,),
    (0.00585938,),
)
_GROOT_REPLAY_JOINT_PREFIX_ROWS = (
    (-0.19574580, -0.40341792, -0.10423726, -2.19564652, -0.21871637, 2.10479379, 0.39902940),
    (-0.19844921, -0.40122452, -0.09466118, -2.19360781, -0.24168095, 2.11665559, 0.39399421),
    (-0.21554480, -0.41246665, -0.09100682, -2.19702625, -0.24528827, 2.11675787, 0.38742143),
    (-0.19939159, -0.40944505, -0.09160183, -2.19366264, -0.26949242, 2.11434579, 0.37265414),
    (-0.19068547, -0.40942037, -0.09546585, -2.19406295, -0.27474448, 2.12093925, 0.37172550),
    (-0.18911973, -0.41755563, -0.09746341, -2.19225788, -0.29558879, 2.12040114, 0.35820645),
    (-0.19144866, -0.41764820, -0.09365430, -2.18930912, -0.30929935, 2.13109922, 0.33803242),
    (-0.17990023, -0.43038398, -0.09860370, -2.18720603, -0.32697150, 2.13032913, 0.33624285),
)


def groot_replay_raw_actions(*, action_horizon: int) -> JSONDict:
    """Build the deterministic raw-action tensor fixture for the GR00T replay."""
    if action_horizon <= 0:
        raise ValueError("GR00T replay action_horizon must be positive.")
    return {
        "eef_9d": [[_groot_eef_row(index) for index in range(action_horizon)]],
        "gripper_position": [[_groot_gripper_row(index) for index in range(action_horizon)]],
        "joint_position": [[_groot_joint_row(index) for index in range(action_horizon)]],
    }


def _groot_eef_row(index: int) -> list[float]:
    if index < len(_GROOT_REPLAY_EEF_PREFIX_ROWS):
        return list(_GROOT_REPLAY_EEF_PREFIX_ROWS[index])
    return [
        round(0.454 - index * 0.00034 + math.sin(index) * 0.0011, 8),
        round(-0.052 + index * 0.00052 + math.cos(index) * 0.0010, 8),
        round(0.351 + index * 0.00318 + math.sin(index / 2) * 0.0012, 8),
        round(0.985 - index * 0.00135, 8),
        round(-0.058 - index * 0.00195, 8),
        round(-0.164 - index * 0.00485, 8),
        round(0.076 + index * 0.0023, 8),
        round(0.992 - index * 0.0012, 8),
        round(0.102 + index * 0.0042, 8),
    ]


def _groot_gripper_row(index: int) -> list[float]:
    if index < len(_GROOT_REPLAY_GRIPPER_PREFIX_ROWS):
        return list(_GROOT_REPLAY_GRIPPER_PREFIX_ROWS[index])
    return [round(0.00195312 * (index % 4), 8)]


def _groot_joint_row(index: int) -> list[float]:
    if index < len(_GROOT_REPLAY_JOINT_PREFIX_ROWS):
        return list(_GROOT_REPLAY_JOINT_PREFIX_ROWS[index])
    return [
        round(-0.180 - index * 0.0023, 8),
        round(-0.430 - index * 0.0021, 8),
        round(-0.099 + index * 0.00035, 8),
        round(-2.187 + index * 0.00095, 8),
        round(-0.327 - index * 0.0052, 8),
        round(2.130 + index * 0.0011, 8),
        round(0.336 - index * 0.0033, 8),
    ]


__all__ = ["groot_replay_raw_actions"]
