#!/usr/bin/env python
"""Run a LeWorldModel provider smoke test with a real checkpoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from worldforge.providers import LeWorldModelProvider


def _checkpoint_path(cache_dir: Path, policy: str) -> Path:
    return cache_dir / f"{policy}_object.ckpt"


def _prepare_object_checkpoint(
    *,
    policy: str,
    hf_repo: str,
    stablewm_home: Path,
    cache_dir: Path,
) -> Path:
    object_path = _checkpoint_path(cache_dir, policy)
    if object_path.exists():
        return object_path

    try:
        import torch
        from stable_worldmodel.wm.utils import load_pretrained
    except ImportError as exc:  # pragma: no cover - exercised by host smoke usage
        raise SystemExit(
            "Preparing a LeWorldModel object checkpoint requires torch and the upstream "
            "stable_worldmodel.wm.utils.load_pretrained helper. Install the upstream "
            "stable-worldmodel[train,env] runtime before running this script."
        ) from exc

    model = load_pretrained(hf_repo, cache_dir=str(stablewm_home))
    object_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model, object_path)
    return object_path


def _build_inputs(
    *,
    batch: int,
    samples: int,
    history: int,
    horizon: int,
    action_dim: int,
    image_size: int,
):
    import torch

    if horizon <= history:
        raise SystemExit("horizon must be greater than history for LeWorldModel rollout.")
    info = {
        "pixels": torch.rand(batch, 1, history, 3, image_size, image_size),
        "goal": torch.rand(batch, 1, history, 3, image_size, image_size),
        "action": torch.rand(batch, 1, history, action_dim),
    }
    action_candidates = torch.rand(batch, samples, horizon, action_dim)
    return info, action_candidates


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default=os.environ.get("LEWORLDMODEL_POLICY", "pusht/lewm"))
    parser.add_argument("--hf-repo", default="quentinll/lewm-pusht")
    parser.add_argument(
        "--stablewm-home",
        type=Path,
        default=Path(os.environ.get("STABLEWM_HOME", "~/.stable_worldmodel")).expanduser(),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help=(
            "Checkpoint root passed to LeWorldModelProvider. Defaults to STABLEWM_HOME/checkpoints."
        ),
    )
    parser.add_argument("--device", default=os.environ.get("LEWORLDMODEL_DEVICE", "cpu"))
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--history", type=int, default=3)
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--action-dim", type=int, default=10)
    parser.add_argument("--image-size", type=int, default=224)
    return parser


def main() -> int:
    args = _parser().parse_args()
    cache_dir = args.cache_dir or (args.stablewm_home / "checkpoints")
    object_path = _prepare_object_checkpoint(
        policy=args.policy,
        hf_repo=args.hf_repo,
        stablewm_home=args.stablewm_home,
        cache_dir=cache_dir,
    )
    info, action_candidates = _build_inputs(
        batch=args.batch,
        samples=args.samples,
        history=args.history,
        horizon=args.horizon,
        action_dim=args.action_dim,
        image_size=args.image_size,
    )
    provider = LeWorldModelProvider(
        policy=args.policy,
        cache_dir=str(cache_dir),
        device=args.device,
    )
    result = provider.score_actions(info=info, action_candidates=action_candidates)
    print(
        json.dumps(
            {
                "checkpoint": str(object_path),
                "health": provider.health().to_dict(),
                "result": result.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
