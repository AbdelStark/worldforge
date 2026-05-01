from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from worldforge.models import ProviderEvent, WorldStateError
from worldforge.smoke import leworldmodel, leworldmodel_checkpoint


def _load_script() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_leworldmodel.py"
    spec = importlib.util.spec_from_file_location("smoke_leworldmodel", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_script_defaults_to_upstream_stablewm_home(monkeypatch) -> None:
    monkeypatch.delenv("STABLEWM_HOME", raising=False)
    script = _load_script()

    args = script._parser().parse_args([])

    assert args.stablewm_home == Path("~/.stable-wm").expanduser()


def test_smoke_script_honors_stablewm_home_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STABLEWM_HOME", str(tmp_path))
    script = _load_script()

    args = script._parser().parse_args([])

    assert args.stablewm_home == tmp_path


def test_checkpoint_path_uses_policy_object_checkpoint_name(tmp_path: Path) -> None:
    assert (
        leworldmodel._checkpoint_path(tmp_path, "pusht/lewm") == tmp_path / "pusht/lewm_object.ckpt"
    )


def test_require_object_checkpoint_reuses_existing_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "pusht/lewm_object.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("existing")

    result = leworldmodel._require_object_checkpoint(
        policy="pusht/lewm",
        cache_dir=tmp_path,
    )

    assert result == checkpoint
    assert checkpoint.read_text() == "existing"


def test_require_object_checkpoint_explains_missing_checkpoint(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="LeWorldModel object checkpoint not found"):
        leworldmodel._require_object_checkpoint(policy="pusht/lewm", cache_dir=tmp_path)


def test_build_checkpoint_reuses_existing_checkpoint_without_optional_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "pusht/lewm_object.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("existing")
    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: pytest.fail("optional dependencies should not load when checkpoint exists"),
    )

    summary = leworldmodel_checkpoint.build_checkpoint(
        repo_id="quentinll/lewm-pusht",
        policy="pusht/lewm",
        stablewm_home=tmp_path,
    )

    assert summary == {
        "created": False,
        "model_family": "LeWorldModel (LeWM)",
        "official_code": "https://github.com/lucas-maes/le-wm",
        "output": str(checkpoint),
        "policy": "pusht/lewm",
        "repo_id": "quentinll/lewm-pusht",
        "reason": "checkpoint already exists",
        "runtime_api": "stable_worldmodel.policy.AutoCostModel",
    }
    assert checkpoint.read_text() == "existing"


def test_checkpoint_builder_reports_missing_optional_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: (_ for _ in ()).throw(SystemExit("missing optional runtime")),
    )

    with pytest.raises(SystemExit, match="missing optional runtime"):
        leworldmodel_checkpoint.build_checkpoint(
            repo_id="quentinll/lewm-pusht",
            policy="pusht/lewm",
            stablewm_home=tmp_path,
        )


def test_checkpoint_builder_installs_stable_pretraining_backbone_shim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfig:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.interpolate_pos_encoding = False

    class FakeViTModel:
        def __init__(
            self,
            config: FakeConfig,
            *,
            add_pooling_layer: bool,
            use_mask_token: bool,
        ) -> None:
            self.config = config
            self.add_pooling_layer = add_pooling_layer
            self.use_mask_token = use_mask_token

    transformers = ModuleType("transformers")
    transformers.ViTConfig = FakeConfig
    transformers.ViTModel = FakeViTModel
    for name in (
        "stable_pretraining",
        "stable_pretraining.backbone",
        "stable_pretraining.backbone.utils",
    ):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "transformers", transformers)

    leworldmodel_checkpoint._install_stable_pretraining_backbone_shim()

    utils = importlib.import_module("stable_pretraining.backbone.utils")
    model = utils.vit_hf(size="tiny", patch_size=14, image_size=224, use_mask_token=False)
    assert model.config.kwargs["hidden_size"] == 192
    assert model.config.kwargs["num_attention_heads"] == 3
    assert model.config.kwargs["patch_size"] == 14
    assert model.config.interpolate_pos_encoding is True
    assert model.add_pooling_layer is False
    assert model.use_mask_token is False
    with pytest.raises(ValueError, match="pretrained=False"):
        utils.vit_hf(pretrained=True)
    with pytest.raises(ValueError, match="Unsupported LeWM PushT ViT parameters"):
        utils.vit_hf(hidden_size=999)


def test_build_checkpoint_saves_object_checkpoint_with_injected_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeParameter:
        def __init__(self) -> None:
            self.requires_grad = True

        def requires_grad_(self, value: bool) -> None:
            self.requires_grad = value

    class FakeModel:
        def __init__(self) -> None:
            self.evaluated = False
            self.parameter = FakeParameter()

        def load_state_dict(self, weights: object, *, strict: bool) -> object:
            assert weights == {"weights": True}
            assert strict is False
            return SimpleNamespace(missing_keys=(), unexpected_keys=())

        def eval(self) -> None:
            self.evaluated = True

        def parameters(self) -> list[FakeParameter]:
            return [self.parameter]

    class FakeTorch:
        def __init__(self) -> None:
            self.saved_model: FakeModel | None = None

        def load(
            self,
            path: Path,
            *,
            map_location: str,
            weights_only: bool = False,
        ) -> dict[str, bool]:
            assert path.name == "weights.pt"
            assert map_location == "cpu"
            assert weights_only is True
            return {"weights": True}

        def save(self, model: FakeModel, path: Path) -> None:
            self.saved_model = model
            path.write_text("saved")

    class FakeOmegaConf:
        @staticmethod
        def load(path: Path) -> dict[str, object]:
            assert path.name == "config.json"
            return {
                "_target_": "stable_worldmodel.wm.lewm.LeWM",
                "encoder": {
                    "_target_": "stable_pretraining.backbone.utils.vit_hf",
                    "size": "tiny",
                    "patch_size": 14,
                    "image_size": 224,
                    "pretrained": False,
                    "use_mask_token": False,
                },
                "predictor": {
                    "_target_": "stable_worldmodel.wm.lewm.module.Predictor",
                    "num_frames": 3,
                    "input_dim": 192,
                    "hidden_dim": 192,
                    "output_dim": 192,
                    "depth": 6,
                    "heads": 16,
                    "mlp_dim": 2048,
                    "dim_head": 64,
                    "dropout": 0.1,
                    "emb_dropout": 0.0,
                },
                "action_encoder": {
                    "_target_": "stable_worldmodel.wm.lewm.module.Embedder",
                    "input_dim": 10,
                    "emb_dim": 192,
                },
                "projector": {
                    "_target_": "stable_worldmodel.wm.lewm.module.MLP",
                    "input_dim": 192,
                    "output_dim": 192,
                    "hidden_dim": 2048,
                    "norm_fn": {
                        "_target_": "torch.nn.BatchNorm1d",
                        "_partial_": True,
                    },
                },
            }

    model = FakeModel()
    torch = FakeTorch()

    revision = "22b330c28c27ead4bfd1888615af1340e3fe9052"

    def hf_hub_download(
        *,
        repo_id: str,
        filename: str,
        local_dir: str,
        revision: str | None,
    ) -> str:
        assert repo_id == "quentinll/lewm-pusht"
        assert revision == "22b330c28c27ead4bfd1888615af1340e3fe9052"
        path = Path(local_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(filename)
        return str(path)

    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: (
            torch,
            hf_hub_download,
            lambda config: (
                model
                if isinstance(config, dict)
                else pytest.fail("instantiate should receive sanitized config dict")
            ),
            FakeOmegaConf,
        ),
    )

    summary = leworldmodel_checkpoint.build_checkpoint(
        repo_id="quentinll/lewm-pusht",
        policy="pusht/lewm",
        stablewm_home=tmp_path / "stablewm",
        cache_dir=tmp_path / "assets",
        revision=revision,
    )

    assert summary == {
        "config": str(tmp_path / "assets/config.json"),
        "config_target": "stable_worldmodel.wm.lewm.LeWM",
        "created": True,
        "model_family": "LeWorldModel (LeWM)",
        "official_code": "https://github.com/lucas-maes/le-wm",
        "output": str(tmp_path / "stablewm/pusht/lewm_object.ckpt"),
        "policy": "pusht/lewm",
        "repo_id": "quentinll/lewm-pusht",
        "revision": revision,
        "runtime_api": "stable_worldmodel.policy.AutoCostModel",
        "weights": str(tmp_path / "assets/weights.pt"),
    }
    assert torch.saved_model is model
    assert model.evaluated is True
    assert model.parameter.requires_grad is False
    assert (tmp_path / "stablewm/pusht/lewm_object.ckpt").read_text() == "saved"


def test_build_checkpoint_rejects_nested_disallowed_config_target_before_instantiate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeOmegaConf:
        @staticmethod
        def load(path: Path) -> dict[str, object]:
            return {
                "_target_": "stable_worldmodel.wm.lewm.LeWM",
                "encoder": {
                    "_target_": "stable_pretraining.backbone.utils.vit_hf",
                    "size": "tiny",
                },
                "callbacks": [
                    {
                        "_target_": "os.system",
                        "command": "touch /tmp/worldforge-should-not-execute",
                    }
                ],
            }

    downloaded: list[str] = []

    class NoWeightsTorch:
        @staticmethod
        def load(path: Path, *, map_location: str, weights_only: bool = False) -> object:
            pytest.fail("weights should not load for rejected config")

    def hf_hub_download(
        *,
        repo_id: str,
        filename: str,
        local_dir: str,
        revision: str | None,
    ) -> str:
        downloaded.append(filename)
        path = Path(local_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(filename)
        return str(path)

    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: (
            NoWeightsTorch,
            hf_hub_download,
            lambda _config: pytest.fail("unsafe config must not be instantiated"),
            FakeOmegaConf,
        ),
    )

    with pytest.raises(WorldStateError, match="disallowed Hydra _target_"):
        leworldmodel_checkpoint.build_checkpoint(
            repo_id="quentinll/lewm-pusht",
            policy="pusht/lewm",
            stablewm_home=tmp_path / "stablewm",
            cache_dir=tmp_path / "assets",
        )

    assert downloaded == ["config.json"]


def test_build_checkpoint_rejects_interpolated_config_target_before_instantiate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeOmegaConf:
        @staticmethod
        def load(path: Path) -> dict[str, object]:
            return {
                "_target_": "stable_worldmodel.wm.lewm.LeWM",
                "encoder": {
                    "_target_": "${encoder_target}",
                    "encoder_target": "os.system",
                },
            }

    def hf_hub_download(
        *,
        repo_id: str,
        filename: str,
        local_dir: str,
        revision: str | None,
    ) -> str:
        path = Path(local_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(filename)
        return str(path)

    class NoWeightsTorch:
        @staticmethod
        def load(path: Path, *, map_location: str, weights_only: bool = False) -> object:
            pytest.fail("weights should not load for rejected config")

    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: (
            NoWeightsTorch,
            hf_hub_download,
            lambda _config: pytest.fail("unsafe config must not be instantiated"),
            FakeOmegaConf,
        ),
    )

    with pytest.raises(WorldStateError, match="must not use interpolation"):
        leworldmodel_checkpoint.build_checkpoint(
            repo_id="quentinll/lewm-pusht",
            policy="pusht/lewm",
            stablewm_home=tmp_path / "stablewm",
            cache_dir=tmp_path / "assets",
        )


def test_leworldmodel_config_validation_uses_unresolved_omegaconf_container() -> None:
    class FakeOmegaConf:
        @staticmethod
        def to_container(config: object, *, resolve: bool) -> dict[str, object]:
            assert resolve is False
            return {
                "_target_": "stable_worldmodel.wm.lewm.LeWM",
                "encoder": {
                    "_target_": "stable_pretraining.backbone.utils.vit_hf",
                    "size": "tiny",
                    "patch_size": 14,
                    "image_size": 224,
                    "pretrained": False,
                    "use_mask_token": False,
                },
            }

    assert (
        leworldmodel_checkpoint._validate_leworldmodel_config(FakeOmegaConf, object())[0]
        == "stable_worldmodel.wm.lewm.LeWM"
    )


def test_leworldmodel_config_validation_rejects_non_target_interpolation() -> None:
    config = {
        "_target_": "stable_worldmodel.wm.lewm.LeWM",
        "encoder": {
            "_target_": "stable_pretraining.backbone.utils.vit_hf",
            "size": "tiny",
            "patch_size": 14,
            "image_size": 224,
            "pretrained": False,
            "use_mask_token": "${mask_token}",
        },
    }

    with pytest.raises(WorldStateError, match="must not use interpolation"):
        leworldmodel_checkpoint._validate_leworldmodel_config(object(), config)


def test_leworldmodel_config_validation_rejects_unsafe_vit_parameters() -> None:
    config = {
        "_target_": "stable_worldmodel.wm.lewm.LeWM",
        "encoder": {
            "_target_": "stable_pretraining.backbone.utils.vit_hf",
            "size": "tiny",
            "patch_size": 14,
            "image_size": 224,
            "pretrained": True,
            "use_mask_token": False,
        },
    }

    with pytest.raises(WorldStateError, match="pretrained"):
        leworldmodel_checkpoint._validate_leworldmodel_config(object(), config)


def test_build_checkpoint_requires_pinned_commit_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: pytest.fail("invalid revision should fail before optional dependency loading"),
    )

    with pytest.raises(WorldStateError, match="40-character commit SHA"):
        leworldmodel_checkpoint.build_checkpoint(
            repo_id="quentinll/lewm-pusht",
            policy="pusht/lewm",
            stablewm_home=tmp_path / "stablewm",
            cache_dir=tmp_path / "assets",
            revision="main",
        )


def test_build_checkpoint_rejects_incompatible_weights(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeModel:
        def load_state_dict(self, weights: object, *, strict: bool) -> object:
            return SimpleNamespace(missing_keys=("encoder.weight",), unexpected_keys=())

    class FakeTorch:
        @staticmethod
        def load(
            path: Path,
            *,
            map_location: str,
            weights_only: bool = False,
        ) -> dict[str, bool]:
            assert weights_only is True
            return {"weights": True}

    class FakeOmegaConf:
        @staticmethod
        def load(path: Path) -> dict[str, object]:
            return {
                "_target_": "stable_worldmodel.wm.lewm.LeWM",
                "encoder": {
                    "_target_": "stable_pretraining.backbone.utils.vit_hf",
                    "size": "tiny",
                    "patch_size": 14,
                    "image_size": 224,
                    "pretrained": False,
                    "use_mask_token": False,
                },
            }

    def hf_hub_download(
        *,
        repo_id: str,
        filename: str,
        local_dir: str,
        revision: str | None,
    ) -> str:
        assert revision == "22b330c28c27ead4bfd1888615af1340e3fe9052"
        path = Path(local_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(filename)
        return str(path)

    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: (FakeTorch, hf_hub_download, lambda config: FakeModel(), FakeOmegaConf),
    )

    with pytest.raises(SystemExit, match="weights did not match"):
        leworldmodel_checkpoint.build_checkpoint(
            repo_id="quentinll/lewm-pusht",
            policy="pusht/lewm",
            stablewm_home=tmp_path / "stablewm",
            cache_dir=tmp_path / "assets",
        )


def test_build_checkpoint_rejects_non_leworldmodel_config_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeOmegaConf:
        @staticmethod
        def load(path: Path) -> dict[str, str]:
            return {"_target_": "stable_worldmodel.wm.lewm_malicious.Run"}

    def hf_hub_download(
        *,
        repo_id: str,
        filename: str,
        local_dir: str,
        revision: str | None,
    ) -> str:
        path = Path(local_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(filename)
        return str(path)

    monkeypatch.setattr(
        leworldmodel_checkpoint,
        "_load_optional_build_dependencies",
        lambda: (object(), hf_hub_download, lambda _config: object(), FakeOmegaConf),
    )

    with pytest.raises(WorldStateError, match="disallowed Hydra _target_"):
        leworldmodel_checkpoint.build_checkpoint(
            repo_id="quentinll/lewm-pusht",
            policy="pusht/lewm",
            stablewm_home=tmp_path / "stablewm",
            cache_dir=tmp_path / "assets",
        )


def test_checkpoint_weight_loader_rejects_legacy_unsafe_torch_load(tmp_path: Path) -> None:
    class LegacyTorch:
        @staticmethod
        def load(path: Path, *, map_location: str) -> dict[str, bool]:
            return {"weights": True}

    with pytest.raises(SystemExit, match="weights_only=True"):
        leworldmodel_checkpoint._load_weights(
            LegacyTorch,
            tmp_path / "weights.pt",
            allow_unsafe_pickle=False,
        )


def test_checkpoint_weight_loader_allows_explicit_unsafe_pickle(tmp_path: Path) -> None:
    class LegacyTorch:
        @staticmethod
        def load(path: Path, *, map_location: str) -> dict[str, bool]:
            assert path == tmp_path / "weights.pt"
            assert map_location == "cpu"
            return {"weights": True}

    assert leworldmodel_checkpoint._load_weights(
        LegacyTorch,
        tmp_path / "weights.pt",
        allow_unsafe_pickle=True,
    ) == {"weights": True}


def test_incompatible_keys_supports_torch_return_object() -> None:
    keys = SimpleNamespace(missing_keys=("encoder.weight",), unexpected_keys=("head.bias",))

    assert leworldmodel_checkpoint._incompatible_keys(keys) == (
        ["encoder.weight"],
        ["head.bias"],
    )
    assert leworldmodel_checkpoint._incompatible_keys((["missing"], ["unexpected"])) == (
        ["missing"],
        ["unexpected"],
    )
    assert leworldmodel_checkpoint._incompatible_keys(None) == ([], [])


def test_checkpoint_builder_main_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, object] = {}

    def fake_build_checkpoint(**kwargs: object) -> dict[str, object]:
        calls.update(kwargs)
        return {"created": False, "output": "checkpoint"}

    monkeypatch.setattr(leworldmodel_checkpoint, "build_checkpoint", fake_build_checkpoint)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge-build-leworldmodel-checkpoint",
            "--repo-id",
            "repo/id",
            "--revision",
            "abc123",
            "--policy",
            "task/lewm",
            "--stablewm-home",
            str(tmp_path / "stablewm"),
            "--asset-cache-dir",
            str(tmp_path / "assets"),
            "--allow-unsafe-pickle",
            "--force",
        ],
    )

    assert leworldmodel_checkpoint.main() == 0

    assert calls == {
        "allow_unsafe_pickle": True,
        "cache_dir": tmp_path / "assets",
        "force": True,
        "policy": "task/lewm",
        "repo_id": "repo/id",
        "revision": "abc123",
        "stablewm_home": tmp_path / "stablewm",
    }
    assert json.loads(capsys.readouterr().out) == {"created": False, "output": "checkpoint"}


def test_build_inputs_uses_expected_tensor_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    torch = ModuleType("torch")
    torch.rand = lambda *shape: {"shape": shape}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)

    info, action_candidates = leworldmodel._build_inputs(
        batch=2,
        samples=3,
        history=4,
        horizon=5,
        action_dim=6,
        image_size=7,
    )

    assert info["pixels"] == {"shape": (2, 1, 4, 3, 7, 7)}
    assert info["goal"] == {"shape": (2, 1, 4, 3, 7, 7)}
    assert info["action"] == {"shape": (2, 1, 4, 6)}
    assert action_candidates == {"shape": (2, 3, 5, 6)}


def test_build_inputs_rejects_non_rollout_horizon() -> None:
    with pytest.raises(SystemExit, match="horizon must be greater than history"):
        leworldmodel._build_inputs(
            batch=1,
            samples=1,
            history=4,
            horizon=4,
            action_dim=2,
            image_size=8,
        )


def test_infer_cache_dir_from_checkpoint() -> None:
    checkpoint = Path("/tmp/stable-wm/pusht/lewm_object.ckpt")
    assert leworldmodel._infer_cache_dir_from_checkpoint(checkpoint, "pusht/lewm") == Path(
        "/tmp/stable-wm"
    )


def test_smoke_main_prints_provider_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeProvider:
        def __init__(
            self,
            *,
            policy: str,
            cache_dir: str,
            device: str,
            event_handler: object | None = None,
        ) -> None:
            self.policy = policy
            self.cache_dir = cache_dir
            self.device = device
            assert event_handler is not None

        def score_actions(self, *, info: object, action_candidates: object) -> SimpleNamespace:
            assert info == {"pixels": "pixels", "goal": "goal", "action": "action"}
            assert action_candidates == ["actions"]
            return SimpleNamespace(to_dict=lambda: {"best_index": 0, "scores": [0.1]})

        def health(self) -> SimpleNamespace:
            return SimpleNamespace(to_dict=lambda: {"healthy": True, "name": "leworldmodel"})

    monkeypatch.setattr(
        leworldmodel,
        "_require_object_checkpoint",
        lambda **_kwargs: tmp_path / "pusht/lewm_object.ckpt",
    )
    monkeypatch.setattr(
        leworldmodel,
        "_build_inputs",
        lambda **_kwargs: ({"pixels": "pixels", "goal": "goal", "action": "action"}, ["actions"]),
    )
    monkeypatch.setattr(leworldmodel, "LeWorldModelProvider", FakeProvider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge-smoke-leworldmodel",
            "--cache-dir",
            str(tmp_path),
            "--device",
            "cpu",
            "--json-only",
        ],
    )

    assert leworldmodel.main() == 0

    output = json.loads(capsys.readouterr().out)
    assert output["checkpoint"] == str(tmp_path / "pusht/lewm_object.ckpt")
    assert output["health"] == {"healthy": True, "name": "leworldmodel"}
    assert output["result"] == {"best_index": 0, "scores": [0.1]}
    assert output["score_payload_summary"]["candidate_count"] == 1
    assert output["score_payload_summary"]["score_direction"] == "lower_is_better"
    assert output["inputs"]["seed"] == 7
    assert output["inputs"]["total_tensor_elements"] == 0
    assert output["metrics"]["score_latency_ms"] >= 0.0
    assert output["provider_events"] == []


def test_smoke_main_prints_visual_pipeline_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkpoint = tmp_path / "pusht" / "lewm_object.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("checkpoint", encoding="utf-8")
    json_output = tmp_path / "lewm-real-summary.json"

    class FakeProvider:
        def __init__(
            self,
            *,
            policy: str,
            cache_dir: str,
            device: str,
            event_handler: object | None = None,
        ) -> None:
            assert policy == "pusht/lewm"
            assert cache_dir == str(tmp_path)
            assert device == "cpu"
            self.event_handler = event_handler

        def score_actions(self, *, info: object, action_candidates: object) -> SimpleNamespace:
            assert info == {
                "pixels": {"shape": (1, 1, 3, 3, 224, 224)},
                "goal": {"shape": (1, 1, 3, 3, 224, 224)},
                "action": {"shape": (1, 1, 3, 10)},
            }
            assert action_candidates == ["actions"]
            assert self.event_handler is not None
            self.event_handler(
                ProviderEvent(
                    provider="leworldmodel",
                    operation="score",
                    phase="success",
                    duration_ms=12.5,
                    metadata={"best_index": 1, "candidate_count": 2, "policy": "pusht/lewm"},
                )
            )
            return SimpleNamespace(
                to_dict=lambda: {
                    "best_index": 1,
                    "best_score": 0.1,
                    "lower_is_better": True,
                    "metadata": {"score_type": "cost"},
                    "scores": [0.3, 0.1],
                }
            )

        def health(self) -> SimpleNamespace:
            return SimpleNamespace(
                to_dict=lambda: {
                    "details": "configured for policy pusht/lewm",
                    "healthy": True,
                    "latency_ms": 0.1,
                    "name": "leworldmodel",
                }
            )

    monkeypatch.setattr(
        leworldmodel,
        "_build_inputs",
        lambda **_kwargs: (
            {
                "pixels": {"shape": (1, 1, 3, 3, 224, 224)},
                "goal": {"shape": (1, 1, 3, 3, 224, 224)},
                "action": {"shape": (1, 1, 3, 10)},
            },
            ["actions"],
        ),
    )
    monkeypatch.setattr(leworldmodel, "LeWorldModelProvider", FakeProvider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-real",
            "--checkpoint",
            str(checkpoint),
            "--device",
            "cpu",
            "--json-output",
            str(json_output),
            "--color",
            "always",
        ],
    )

    assert leworldmodel.main() == 0

    output = capsys.readouterr().out
    assert "WorldForge LeWorldModel real checkpoint inference" in output
    assert "\033[" in output
    assert "Mode: real upstream checkpoint inference" in output
    assert "What this demonstrates" in output
    assert "Pipeline" in output
    assert "[1/6] Resolve checkpoint and runtime settings" in output
    assert "[3/6] Preflight optional runtime dependencies" in output
    assert "[5/6] Run score_actions through the real checkpoint" in output
    assert "Candidate cost landscape" in output
    assert "Inference metrics" in output
    assert "Provider event log" in output
    assert "Artifacts" in output
    assert "#1" in output
    assert "BEST" in output
    assert "Use --json-only" in output
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["inputs"]["seed"] == 7
    assert payload["inputs"]["total_tensor_elements"] == 903198
    assert payload["score_payload_summary"]["candidate_count"] == 2
    assert payload["score_payload_summary"]["best_index"] == 1
    assert payload["metrics"]["gap_to_runner_up"] == pytest.approx(0.2)
    assert payload["provider_events"][0]["phase"] == "success"


def test_smoke_main_reports_missing_runtime_before_tensor_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkpoint = tmp_path / "pusht" / "lewm_object.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("checkpoint", encoding="utf-8")

    class FakeProvider:
        def __init__(
            self,
            *,
            policy: str,
            cache_dir: str,
            device: str,
            event_handler: object | None = None,
        ) -> None:
            assert policy == "pusht/lewm"
            assert cache_dir == str(tmp_path)
            assert device == "cpu"
            assert event_handler is not None

        def health(self) -> SimpleNamespace:
            return SimpleNamespace(
                to_dict=lambda: {
                    "details": "missing optional dependency torch",
                    "healthy": False,
                    "latency_ms": 0.1,
                    "name": "leworldmodel",
                }
            )

    def fail_build_inputs(**_kwargs: object) -> tuple[object, object]:
        raise AssertionError("_build_inputs should not run before dependency preflight")

    monkeypatch.setattr(leworldmodel, "_build_inputs", fail_build_inputs)
    monkeypatch.setattr(leworldmodel, "LeWorldModelProvider", FakeProvider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-real",
            "--checkpoint",
            str(checkpoint),
            "--device",
            "cpu",
        ],
    )

    assert leworldmodel.main() == 1

    message = capsys.readouterr().out
    assert "LeWorldModel runtime preflight failed: missing optional dependency torch" in message
    assert "scripts/lewm-real --checkpoint" in message
    assert 'uv run --python 3.13 --with "stable-worldmodel @ git+' in message
    assert "stable-worldmodel[train]" not in message
    assert '--with "opencv-python"' in message
    assert '--with "imageio"' in message
