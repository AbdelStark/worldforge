"""Runtime asset manifest helpers for optional smoke evidence."""

from __future__ import annotations

from pathlib import Path

from worldforge.providers.runtime_manifest import RuntimeAssetManifest

LEWORLDMODEL_ASSET_SOURCE = "huggingface:quentinll/lewm-pusht"
LEROBOT_POLICY_SOURCE = "host-selected LeRobot policy checkpoint"


def leworldmodel_checkpoint_asset(
    *,
    policy: str,
    checkpoint: Path,
    cache_root: Path,
    source: str = LEWORLDMODEL_ASSET_SOURCE,
    revision: str | None = None,
    exists: bool | None = None,
    rebuild_command: str | None = None,
) -> RuntimeAssetManifest:
    """Describe the host-owned LeWorldModel object checkpoint for evidence."""

    resolved_rebuild = rebuild_command or (
        "worldforge-build-leworldmodel-checkpoint "
        f"--policy {policy} --stablewm-home <cache-root> --revision <pinned-sha>"
    )
    return RuntimeAssetManifest(
        asset_id=f"leworldmodel:checkpoint:{policy}",
        provider="leworldmodel",
        asset_kind="checkpoint",
        path=checkpoint,
        cache_root=cache_root,
        source=source,
        revision=revision,
        local_only=True,
        exists=checkpoint.exists() if exists is None else exists,
        rebuild_command=resolved_rebuild,
    )


def lerobot_policy_asset(
    *,
    policy_path: str,
    cache_root: str | Path | None = None,
    exists: bool | None = None,
) -> RuntimeAssetManifest:
    """Describe the host-owned LeRobot policy checkpoint or repo reference."""

    return RuntimeAssetManifest(
        asset_id="lerobot:policy-checkpoint",
        provider="lerobot",
        asset_kind="policy_checkpoint",
        path=policy_path,
        cache_root=cache_root,
        source=LEROBOT_POLICY_SOURCE,
        local_only=True,
        exists=exists,
        rebuild_command=(
            "scripts/smoke_lerobot_policy.py --policy-path <repo-or-checkpoint> --device cpu"
        ),
    )


__all__ = [
    "LEROBOT_POLICY_SOURCE",
    "LEWORLDMODEL_ASSET_SOURCE",
    "lerobot_policy_asset",
    "leworldmodel_checkpoint_asset",
]
