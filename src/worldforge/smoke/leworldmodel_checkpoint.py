"""Build a LeWorldModel object checkpoint from Hugging Face assets.

Run with the same upstream runtime used by the real smoke:

    uv run --python 3.13 --with "<git stable-worldmodel>" --with "datasets>=2.21"
      --with huggingface_hub --with hydra-core --with omegaconf --with transformers
      --with "opencv-python" --with "imageio" worldforge-build-leworldmodel-checkpoint

The command downloads ``config.json`` from the model repo, validates that every
Hydra target is one of the known official PushT LeWM constructors, downloads
``weights.pt``, instantiates the LeWM module, loads the weights, and saves the
object checkpoint where ``stable_worldmodel.policy.AutoCostModel`` expects it.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from worldforge.models import WorldStateError
from worldforge.smoke.leworldmodel import DEFAULT_STABLEWM_HOME, _checkpoint_path

DEFAULT_REPO_ID = "quentinll/lewm-pusht"
LEWORLDMODEL_HF_DEFAULT_REVISION = "22b330c28c27ead4bfd1888615af1340e3fe9052"
LEWORLDMODEL_OFFICIAL_REPO_URL = "https://github.com/lucas-maes/le-wm"
LEWORLDMODEL_RUNTIME_API = "stable_worldmodel.policy.AutoCostModel"
LEWORLDMODEL_HF_CONFIG_TARGET = "stable_worldmodel.wm.lewm.LeWM"
LEWORLDMODEL_HF_BACKBONE_TARGET = "stable_pretraining.backbone.utils.vit_hf"
# Hydra instantiates nested `_target_` values recursively, so this list must stay exact and narrow.
LEWORLDMODEL_HF_ALLOWED_CONFIG_TARGETS = frozenset(
    {
        LEWORLDMODEL_HF_CONFIG_TARGET,
        LEWORLDMODEL_HF_BACKBONE_TARGET,
        "stable_worldmodel.wm.lewm.module.Embedder",
        "stable_worldmodel.wm.lewm.module.MLP",
        "stable_worldmodel.wm.lewm.module.Predictor",
        "torch.nn.BatchNorm1d",
    }
)


def _vit_hf_backbone(
    size: str = "tiny",
    patch_size: int = 14,
    image_size: int = 224,
    pretrained: bool = False,
    use_mask_token: bool = True,
    **kwargs: Any,
) -> object:
    """Build the ViT backbone referenced by the official PushT LeWM config."""

    from transformers import ViTConfig, ViTModel

    if kwargs:
        unsupported = ", ".join(sorted(kwargs))
        raise ValueError(f"Unsupported LeWM PushT ViT parameters: {unsupported}.")
    if pretrained is not False:
        raise ValueError("LeWM PushT ViT checkpoint builder requires pretrained=False.")
    if size != "tiny" or patch_size != 14 or image_size != 224:
        raise ValueError(
            "LeWM PushT ViT checkpoint builder only supports "
            "size='tiny', patch_size=14, image_size=224."
        )

    size_config = {"hidden_size": 192, "num_hidden_layers": 12, "num_attention_heads": 3}
    config_params = {
        **size_config,
        "intermediate_size": size_config["hidden_size"] * 4,
        "image_size": image_size,
        "patch_size": patch_size,
    }
    model = ViTModel(
        ViTConfig(**config_params),
        add_pooling_layer=False,
        use_mask_token=use_mask_token,
    )
    model.config.interpolate_pos_encoding = True
    return model


def _install_stable_pretraining_backbone_shim() -> None:
    """Expose the single stable-pretraining backbone target used by LeWM configs."""

    stable_pretraining = sys.modules.get("stable_pretraining") or ModuleType("stable_pretraining")
    backbone = sys.modules.get("stable_pretraining.backbone") or ModuleType(
        "stable_pretraining.backbone"
    )
    utils = sys.modules.get("stable_pretraining.backbone.utils") or ModuleType(
        "stable_pretraining.backbone.utils"
    )
    stable_pretraining.__path__ = []  # type: ignore[attr-defined]
    backbone.__path__ = []  # type: ignore[attr-defined]
    utils.vit_hf = _vit_hf_backbone  # type: ignore[attr-defined]
    stable_pretraining.backbone = backbone  # type: ignore[attr-defined]
    backbone.utils = utils  # type: ignore[attr-defined]
    sys.modules["stable_pretraining"] = stable_pretraining
    sys.modules["stable_pretraining.backbone"] = backbone
    sys.modules["stable_pretraining.backbone.utils"] = utils


def _repo_cache_dir(repo_id: str) -> Path:
    safe_repo = repo_id.replace("/", "__")
    return Path("~/.cache/worldforge/leworldmodel").expanduser() / safe_repo


def _load_optional_build_dependencies():
    try:
        # Required by current stable_worldmodel top-level visual-wrapper imports.
        importlib.import_module("cv2")
        importlib.import_module("imageio")
        importlib.import_module("stable_worldmodel")  # probe upstream runtime import envelope
        importlib.import_module("transformers")
        try:
            importlib.import_module("stable_pretraining")  # use upstream package when present
        except ImportError:
            _install_stable_pretraining_backbone_shim()
        import torch
        from huggingface_hub import hf_hub_download
        from hydra.utils import instantiate
        from omegaconf import OmegaConf
    except ImportError as exc:  # pragma: no cover - exercised by host smoke usage
        missing = exc.name or ""
        if missing == "matplotlib":
            raise SystemExit(
                "Building a LeWorldModel object checkpoint requires matplotlib in current "
                "upstream LeWorldModel runtime environments. Add `--with matplotlib` to the "
                "uv run invocation (see docs/src/operations.md)."
            ) from exc
        if missing == "cv2":
            raise SystemExit(
                "Building a LeWorldModel object checkpoint requires opencv-python because the "
                "current upstream stable_worldmodel package imports cv2 at module load time. "
                'Add `--with "opencv-python"` to the uv run invocation.'
            ) from exc
        if missing == "imageio":
            raise SystemExit(
                "Building a LeWorldModel object checkpoint requires imageio because the current "
                "upstream stable_worldmodel package imports imageio at module load time. "
                "Add `--with imageio` to the uv run invocation."
            ) from exc
        if missing == "transformers":
            raise SystemExit(
                "Building a LeWorldModel object checkpoint requires transformers because the "
                "official LeWM PushT config constructs its ViT encoder through a Hugging Face "
                "ViTModel. Add `--with transformers` to the uv run invocation."
            ) from exc
        raise SystemExit(
            "Building a LeWorldModel object checkpoint requires torch, huggingface_hub, "
            "hydra-core, omegaconf, transformers, opencv-python, imageio, and the upstream "
            "stable-worldmodel LeWM modules. Run the command with the dependency flags "
            "documented in docs/src/operations.md."
        ) from exc
    return torch, hf_hub_download, instantiate, OmegaConf


def _incompatible_keys(load_result: object) -> tuple[list[str], list[str]]:
    if load_result is None:
        return [], []
    if hasattr(load_result, "missing_keys") and hasattr(load_result, "unexpected_keys"):
        return list(load_result.missing_keys), list(load_result.unexpected_keys)
    missing, unexpected = load_result
    return list(missing), list(unexpected)


def _load_weights(torch: object, weights_path: Path, *, allow_unsafe_pickle: bool) -> object:
    if allow_unsafe_pickle:
        return torch.load(weights_path, map_location="cpu")
    try:
        return torch.load(weights_path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise SystemExit(
            "Safe LeWorldModel weight loading requires a torch version that supports "
            "`torch.load(..., weights_only=True)`. Upgrade torch or rerun with "
            "`--allow-unsafe-pickle` only when the weights file is trusted."
        ) from exc


def _config_target(config: object) -> str:
    if not isinstance(config, Mapping):
        raise WorldStateError("LeWorldModel config.json must contain a JSON object.")
    target = config.get("_target_")
    if not isinstance(target, str) or not target.strip():
        raise WorldStateError("LeWorldModel config.json must contain a non-empty _target_ field.")
    return target.strip()


def _ensure_leworldmodel_target(target: str) -> None:
    if target != LEWORLDMODEL_HF_CONFIG_TARGET:
        raise WorldStateError(
            "LeWorldModel config.json root _target_ must be "
            f"{LEWORLDMODEL_HF_CONFIG_TARGET!r}; got {target!r}."
        )


def _config_to_container(omega_conf: object, config: object) -> object:
    to_container = getattr(omega_conf, "to_container", None)
    if callable(to_container):
        return to_container(config, resolve=False)
    return config


def _target_path(path: str) -> str:
    return f"{path}._target_" if path != "$" else "$._target_"


def _child_path(path: str, key: object) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    key_text = str(key)
    return key_text if path == "$" else f"{path}.{key_text}"


def _ensure_allowed_hydra_target(target: object, path: str) -> str:
    target_path = _target_path(path)
    if not isinstance(target, str) or not target.strip():
        raise WorldStateError(f"LeWorldModel config {target_path} must be a non-empty string.")
    normalized = target.strip()
    if "${" in normalized:
        raise WorldStateError(f"LeWorldModel config {target_path} must not use interpolation.")
    if normalized not in LEWORLDMODEL_HF_ALLOWED_CONFIG_TARGETS:
        allowed = ", ".join(sorted(LEWORLDMODEL_HF_ALLOWED_CONFIG_TARGETS))
        raise WorldStateError(
            "LeWorldModel config contains disallowed Hydra _target_ "
            f"at {target_path}: {normalized!r}. Allowed targets: {allowed}."
        )
    return normalized


def _walk_hydra_targets(node: object, path: str = "$") -> None:
    if isinstance(node, Mapping):
        if "_target_" in node:
            _ensure_allowed_hydra_target(node["_target_"], path)
        for key, value in node.items():
            _walk_hydra_targets(value, _child_path(path, key))
        return
    if isinstance(node, Sequence) and not isinstance(node, str | bytes | bytearray):
        for index, value in enumerate(node):
            _walk_hydra_targets(value, _child_path(path, index))


def _walk_safe_config_values(node: object, path: str = "$") -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if not isinstance(key, str) or not key:
                raise WorldStateError(f"LeWorldModel config {path} contains an invalid key.")
            _walk_safe_config_values(value, _child_path(path, key))
        return
    if isinstance(node, Sequence) and not isinstance(node, str | bytes | bytearray):
        for index, value in enumerate(node):
            _walk_safe_config_values(value, _child_path(path, index))
        return
    if isinstance(node, str):
        if "${" in node:
            raise WorldStateError(f"LeWorldModel config {path} must not use interpolation.")
        return
    if isinstance(node, bool) or node is None or isinstance(node, int):
        return
    if isinstance(node, float) and math.isfinite(node):
        return
    raise WorldStateError(
        f"LeWorldModel config {path} must contain only JSON-native finite values."
    )


def _require_mapping_field(config: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise WorldStateError(f"LeWorldModel config field {key!r} must be a JSON object.")
    return value


def _require_exact_mapping(
    mapping: Mapping[str, object],
    *,
    path: str,
    expected: Mapping[str, object],
) -> None:
    extra = sorted(set(mapping) - set(expected))
    missing = sorted(set(expected) - set(mapping))
    if extra or missing:
        raise WorldStateError(
            f"LeWorldModel config {path} does not match the audited PushT shape: "
            f"missing={missing}, extra={extra}."
        )
    for key, expected_value in expected.items():
        if mapping.get(key) != expected_value:
            raise WorldStateError(
                f"LeWorldModel config {path}.{key} must be {expected_value!r}; "
                f"got {mapping.get(key)!r}."
            )


def _validate_known_pusht_parameters(config: Mapping[str, object]) -> None:
    encoder = _require_mapping_field(config, "encoder")
    _require_exact_mapping(
        encoder,
        path="$.encoder",
        expected={
            "_target_": LEWORLDMODEL_HF_BACKBONE_TARGET,
            "size": "tiny",
            "patch_size": 14,
            "image_size": 224,
            "pretrained": False,
            "use_mask_token": False,
        },
    )


def _validate_leworldmodel_config(
    omega_conf: object, config: object
) -> tuple[str, Mapping[str, object]]:
    plain_config = _config_to_container(omega_conf, config)
    target = _config_target(plain_config)
    _walk_hydra_targets(plain_config)
    _walk_safe_config_values(plain_config)
    _ensure_leworldmodel_target(target)
    _validate_known_pusht_parameters(plain_config)
    return target, plain_config


def _resolve_hf_revision(revision: str | None) -> str:
    resolved = (revision or LEWORLDMODEL_HF_DEFAULT_REVISION).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise WorldStateError(
            "LeWorldModel Hugging Face revision must be a pinned 40-character "
            f"commit SHA; got {revision!r}."
        )
    return resolved


def _checkpoint_provenance() -> dict[str, object]:
    return {
        "model_family": "LeWorldModel (LeWM)",
        "official_code": LEWORLDMODEL_OFFICIAL_REPO_URL,
        "runtime_api": LEWORLDMODEL_RUNTIME_API,
    }


def build_checkpoint(
    *,
    repo_id: str,
    policy: str,
    stablewm_home: Path,
    cache_dir: Path | None = None,
    revision: str | None = None,
    allow_unsafe_pickle: bool = False,
    force: bool = False,
) -> dict[str, object]:
    """Build and persist an object checkpoint from a Hugging Face LeWM repo."""

    output_path = _checkpoint_path(stablewm_home.expanduser(), policy)
    if output_path.exists() and not force:
        return {
            "created": False,
            "output": str(output_path),
            "policy": policy,
            "repo_id": repo_id,
            "reason": "checkpoint already exists",
            **_checkpoint_provenance(),
        }

    resolved_revision = _resolve_hf_revision(revision)
    torch, hf_hub_download, instantiate, omega_conf = _load_optional_build_dependencies()
    asset_dir = (cache_dir or _repo_cache_dir(repo_id)).expanduser()
    config_path = Path(
        hf_hub_download(
            repo_id=repo_id,
            filename="config.json",
            local_dir=str(asset_dir),
            revision=resolved_revision,
        )
    )

    config = omega_conf.load(config_path)
    target, safe_config = _validate_leworldmodel_config(omega_conf, config)
    weights_path = Path(
        hf_hub_download(
            repo_id=repo_id,
            filename="weights.pt",
            local_dir=str(asset_dir),
            revision=resolved_revision,
        )
    )
    model = instantiate(safe_config)
    weights = _load_weights(torch, weights_path, allow_unsafe_pickle=allow_unsafe_pickle)
    incompatible = model.load_state_dict(weights, strict=False)
    missing, unexpected = _incompatible_keys(incompatible)
    if missing or unexpected:
        raise SystemExit(
            "LeWorldModel weights did not match the instantiated model: "
            f"missing={missing[:10]}, unexpected={unexpected[:10]}"
        )

    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model, output_path)
    summary: dict[str, object] = {
        "created": True,
        "config": str(config_path),
        "output": str(output_path),
        "policy": policy,
        "repo_id": repo_id,
        "revision": resolved_revision,
        "weights": str(weights_path),
        "config_target": target,
        **_checkpoint_provenance(),
    }
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument(
        "--revision",
        default=os.environ.get("LEWORLDMODEL_REVISION") or LEWORLDMODEL_HF_DEFAULT_REVISION,
        help=(
            "Pinned Hugging Face commit SHA for config.json and weights.pt. Defaults to the "
            f"audited PushT LeWM revision {LEWORLDMODEL_HF_DEFAULT_REVISION}."
        ),
    )
    parser.add_argument("--policy", default=os.environ.get("LEWORLDMODEL_POLICY", "pusht/lewm"))
    parser.add_argument(
        "--stablewm-home",
        type=Path,
        default=Path(os.environ.get("STABLEWM_HOME", DEFAULT_STABLEWM_HOME)).expanduser(),
    )
    parser.add_argument(
        "--asset-cache-dir",
        type=Path,
        default=None,
        help=(
            "Directory for downloaded Hugging Face config/weights. Defaults to ~/.cache/worldforge."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild and overwrite the object checkpoint when it already exists.",
    )
    parser.add_argument(
        "--allow-unsafe-pickle",
        action="store_true",
        help=(
            "Allow legacy torch.load pickle deserialization for trusted weights only. "
            "By default, weights are loaded with weights_only=True."
        ),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        summary = build_checkpoint(
            repo_id=args.repo_id,
            policy=args.policy,
            stablewm_home=args.stablewm_home,
            cache_dir=args.asset_cache_dir.expanduser() if args.asset_cache_dir else None,
            revision=args.revision,
            allow_unsafe_pickle=args.allow_unsafe_pickle,
            force=args.force,
        )
    except WorldStateError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
