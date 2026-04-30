from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from worldforge.smoke import pusht_showcase_inputs, robotics_showcase


class FakeTensor:
    def __init__(self, data: object) -> None:
        self.data = data

    @property
    def shape(self) -> tuple[int, ...]:
        return self._shape(self.data)

    @staticmethod
    def _shape(value: object) -> tuple[int, ...]:
        if isinstance(value, list):
            if not value:
                return (0,)
            return (len(value), *FakeTensor._shape(value[0]))
        return ()

    def tolist(self) -> object:
        return self.data

    def detach(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def reshape(self, shape: int) -> FakeTensor:
        if shape != -1:
            raise AssertionError("test fake only implements reshape(-1)")
        flattened: list[float] = []

        def visit(value: object) -> None:
            if isinstance(value, list):
                for child in value:
                    visit(child)
                return
            flattened.append(float(value))  # type: ignore[arg-type]

        visit(self.data)
        return FakeTensor(flattened)

    def numel(self) -> int:
        total = 1
        for part in self.shape:
            total *= part
        return total

    def clamp(self, minimum: float, maximum: float) -> FakeTensor:
        return FakeTensor(self._map(lambda value: max(minimum, min(maximum, value))))

    def repeat_interleave(self, repeats: int, dim: int) -> FakeTensor:
        def repeat_axis(value: object, axis: int) -> object:
            if axis == 0:
                if isinstance(value, list):
                    repeated: list[object] = []
                    for child in value:
                        repeated.extend(copy.deepcopy(child) for _ in range(repeats))
                    return repeated
                return [copy.deepcopy(value) for _ in range(repeats)]
            if not isinstance(value, list):
                raise AssertionError("repeat_interleave axis exceeds tensor rank")
            return [repeat_axis(child, axis - 1) for child in value]

        return FakeTensor(repeat_axis(self.data, dim))

    def unsqueeze(self, dim: int) -> FakeTensor:
        def insert_axis(value: object, axis: int) -> object:
            if axis == 0:
                return [value]
            if not isinstance(value, list):
                raise AssertionError("unsqueeze axis exceeds tensor rank")
            return [insert_axis(child, axis - 1) for child in value]

        return FakeTensor(insert_axis(self.data, dim))

    def repeat(self, *repeats: int) -> FakeTensor:
        def repeat_axes(value: object, axes: tuple[int, ...]) -> object:
            if not axes:
                return value
            if not isinstance(value, list):
                return value
            repeated_children = [repeat_axes(child, axes[1:]) for child in value]
            out: list[object] = []
            for _ in range(axes[0]):
                out.extend(copy.deepcopy(repeated_children))
            return out

        return FakeTensor(repeat_axes(self.data, tuple(repeats)))

    def to(self, _dtype: object) -> FakeTensor:
        return self

    def _map(self, fn: object) -> object:
        def visit(value: object) -> object:
            if isinstance(value, list):
                return [visit(child) for child in value]
            return fn(float(value))  # type: ignore[operator,arg-type]

        return visit(self.data)

    def __iter__(self):
        if not isinstance(self.data, list):
            raise TypeError("scalar fake tensor is not iterable")
        for child in self.data:
            yield FakeTensor(child)

    def __getitem__(self, item: object) -> FakeTensor:
        if not isinstance(self.data, list):
            raise TypeError("scalar fake tensor is not subscriptable")
        return FakeTensor(self.data[item])  # type: ignore[index]

    def __mul__(self, scale: float) -> FakeTensor:
        return FakeTensor(self._map(lambda value: value * scale))

    def __neg__(self) -> FakeTensor:
        return FakeTensor(self._map(lambda value: -value))

    def __float__(self) -> float:
        if isinstance(self.data, list):
            raise TypeError("non-scalar fake tensor cannot be converted to float")
        return float(self.data)  # type: ignore[arg-type]


class FakeTorch:
    float32 = "float32"

    @staticmethod
    def as_tensor(value: object, dtype: object | None = None) -> FakeTensor:
        return FakeTensor(value)

    @staticmethod
    def stack(values: list[FakeTensor], dim: int = 0) -> FakeTensor:
        assert dim == 0
        return FakeTensor([value.tolist() for value in values])


def _showcase_summary() -> dict[str, Any]:
    return {
        "mode": "real_lerobot_policy_plus_real_leworldmodel_score",
        "checkpoint_display": "~/.stable-wm/pusht/lewm_object.ckpt",
        "health": {
            "lerobot": {"healthy": True},
            "leworldmodel": {"healthy": True},
        },
        "inputs": {
            "policy_path": "lerobot/diffusion_pusht",
            "approx_float32_mb": 3.446,
            "total_tensor_elements": 903318,
        },
        "score_result": {
            "best_index": 2,
            "best_score": 9.331253051757812,
            "scores": [17.086671829223633, 12.75649642944336, 9.331253051757812],
        },
        "execution": {
            "actions_applied": 1,
            "final_step": 1,
            "final_block_position": {"x": 0.375, "y": 0.375, "z": 0.0},
        },
        "provider_events": [
            {
                "provider": "lerobot",
                "operation": "policy",
                "phase": "success",
                "duration_ms": 5211.61,
            },
            {
                "provider": "leworldmodel",
                "operation": "score",
                "phase": "success",
                "duration_ms": 67.77,
            },
        ],
        "visualization": {
            "selected_candidate": 2,
            "candidate_targets": [
                {"index": 0, "x": 0.75, "y": 0.75, "z": 0.0},
                {"index": 1, "x": 0.625, "y": 0.625, "z": 0.0},
                {"index": 2, "x": 0.375, "y": 0.375, "z": 0.0},
            ],
        },
        "metrics": {
            "plan_latency_ms": 5279.53,
            "total_latency_ms": 9597.51,
        },
    }


def test_robotics_showcase_forwards_packaged_pusht_defaults(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_low_level_main(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(robotics_showcase.lerobot_leworldmodel, "main", fake_low_level_main)

    assert (
        robotics_showcase.main(
            [
                "--checkpoint",
                str(tmp_path / "pusht/lewm_object.ckpt"),
                "--device",
                "cpu",
                "--no-color",
                "--no-json-output",
            ]
        )
        == 0
    )

    forwarded = captured["argv"]
    assert forwarded[:2] == ["--policy-path", "lerobot/diffusion_pusht"]
    assert "--observation-module" in forwarded
    assert (
        forwarded[forwarded.index("--observation-module") + 1]
        == "worldforge.smoke.pusht_showcase_inputs:build_observation"
    )
    assert (
        forwarded[forwarded.index("--score-info-module") + 1]
        == "worldforge.smoke.pusht_showcase_inputs:build_score_info"
    )
    assert (
        forwarded[forwarded.index("--translator") + 1]
        == "worldforge.smoke.pusht_showcase_inputs:translate_candidates"
    )
    assert (
        forwarded[forwarded.index("--candidate-builder") + 1]
        == "worldforge.smoke.pusht_showcase_inputs:build_action_candidates"
    )
    assert forwarded[forwarded.index("--expected-action-dim") + 1] == "10"
    assert forwarded[forwarded.index("--expected-horizon") + 1] == "4"
    assert "--json-output" not in forwarded


def test_packaged_pusht_bridge_builds_candidates_without_optional_import_at_module_load(
    monkeypatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", FakeTorch)

    candidates = pusht_showcase_inputs.build_action_candidates([0.8, -2.0], {}, {})

    assert candidates.shape == (1, 3, 4, 10)
    assert candidates.tolist()[0][0][0] == [0.8, 0.8, 0.8, 0.8, 0.8, -1.0, -1.0, -1.0, -1.0, -1.0]

    plans = pusht_showcase_inputs.translate_candidates(
        [0.8, -2.0],
        {"score_bridge": {"object_id": "block-1"}},
        {},
    )
    assert len(plans) == 3
    assert plans[0][0].parameters["object_id"] == "block-1"
    assert plans[0][0].parameters["target"] == {"x": 0.7, "y": 0.25, "z": 0.0}


def test_robotics_showcase_uses_tmp_json_output_by_default(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_low_level_main(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(robotics_showcase.lerobot_leworldmodel, "main", fake_low_level_main)

    assert robotics_showcase.main(["--checkpoint", "/tmp/pusht/lewm_object.ckpt"]) == 0

    forwarded = captured["argv"]
    assert forwarded[forwarded.index("--json-output") + 1] == str(
        robotics_showcase.DEFAULT_JSON_OUTPUT
    )
    assert forwarded[forwarded.index("--run-manifest") + 1] == str(
        robotics_showcase.DEFAULT_JSON_OUTPUT.with_name("run_manifest.json")
    )


def test_robotics_showcase_auto_downloads_missing_checkpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    build_calls: dict[str, Any] = {}

    def fake_build_checkpoint(**kwargs: Any) -> dict[str, Any]:
        build_calls.update(kwargs)
        target = kwargs["stablewm_home"] / f"{kwargs['policy']}_object.ckpt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"stub")
        return {"created": True, "output": str(target)}

    def fake_low_level_main(argv: list[str]) -> int:
        return 0

    monkeypatch.setattr(
        robotics_showcase.leworldmodel_checkpoint, "build_checkpoint", fake_build_checkpoint
    )
    monkeypatch.setattr(robotics_showcase.lerobot_leworldmodel, "main", fake_low_level_main)

    assert (
        robotics_showcase.main(
            [
                "--stablewm-home",
                str(tmp_path),
                "--lewm-revision",
                "abc123",
                "--allow-unsafe-pickle",
                "--no-json-output",
                "--no-tui",
            ]
        )
        == 0
    )

    assert build_calls["policy"] == "pusht/lewm"
    assert build_calls["stablewm_home"] == tmp_path
    assert build_calls["repo_id"] == robotics_showcase.leworldmodel_checkpoint.DEFAULT_REPO_ID
    assert build_calls["revision"] == "abc123"
    assert build_calls["allow_unsafe_pickle"] is True


def test_robotics_showcase_health_only_does_not_auto_download_missing_checkpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    build_called = False
    captured: dict[str, Any] = {}

    def fake_build_checkpoint(**_: Any) -> dict[str, Any]:
        nonlocal build_called
        build_called = True
        return {"created": False}

    def fake_low_level_main(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        robotics_showcase.leworldmodel_checkpoint, "build_checkpoint", fake_build_checkpoint
    )
    monkeypatch.setattr(robotics_showcase.lerobot_leworldmodel, "main", fake_low_level_main)

    assert (
        robotics_showcase.main(
            [
                "--stablewm-home",
                str(tmp_path),
                "--health-only",
                "--no-json-output",
                "--no-tui",
            ]
        )
        == 0
    )

    assert build_called is False
    assert "--health-only" in captured["argv"]


def test_robotics_showcase_skips_download_when_checkpoint_present(
    monkeypatch,
    tmp_path: Path,
) -> None:
    build_called = False

    def fake_build_checkpoint(**_: Any) -> dict[str, Any]:
        nonlocal build_called
        build_called = True
        return {"created": False}

    def fake_low_level_main(argv: list[str]) -> int:
        return 0

    target = tmp_path / "pusht/lewm_object.ckpt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"stub")

    monkeypatch.setattr(
        robotics_showcase.leworldmodel_checkpoint, "build_checkpoint", fake_build_checkpoint
    )
    monkeypatch.setattr(robotics_showcase.lerobot_leworldmodel, "main", fake_low_level_main)

    assert (
        robotics_showcase.main(
            [
                "--stablewm-home",
                str(tmp_path),
                "--no-json-output",
                "--no-tui",
            ]
        )
        == 0
    )
    assert build_called is False


def test_robotics_showcase_skips_download_when_explicit_checkpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    build_called = False

    def fake_build_checkpoint(**_: Any) -> dict[str, Any]:
        nonlocal build_called
        build_called = True
        return {"created": False}

    def fake_low_level_main(argv: list[str]) -> int:
        return 0

    monkeypatch.setattr(
        robotics_showcase.leworldmodel_checkpoint, "build_checkpoint", fake_build_checkpoint
    )
    monkeypatch.setattr(robotics_showcase.lerobot_leworldmodel, "main", fake_low_level_main)

    assert (
        robotics_showcase.main(
            [
                "--checkpoint",
                str(tmp_path / "custom/path.ckpt"),
                "--no-json-output",
                "--no-tui",
            ]
        )
        == 0
    )
    assert build_called is False


def test_robotics_showcase_tui_mode_captures_json_and_launches_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_low_level_main(argv: list[str]) -> int:
        captured["argv"] = argv
        print(json.dumps(_showcase_summary()))
        return 0

    def fake_launch(
        summary: dict[str, Any],
        *,
        summary_path: Path | None,
        stage_delay: float,
        animate_arm: bool,
    ) -> int:
        captured["summary"] = summary
        captured["summary_path"] = summary_path
        captured["stage_delay"] = stage_delay
        captured["animate_arm"] = animate_arm
        return 0

    monkeypatch.setattr(robotics_showcase.lerobot_leworldmodel, "main", fake_low_level_main)
    monkeypatch.setattr(robotics_showcase, "_launch_tui", fake_launch)

    json_path = tmp_path / "summary.json"
    assert (
        robotics_showcase.main(
            [
                "--checkpoint",
                "/tmp/pusht/lewm_object.ckpt",
                "--json-output",
                str(json_path),
                "--tui-stage-delay",
                "0.2",
                "--tui",
            ]
        )
        == 0
    )

    assert "--json-only" in captured["argv"]
    assert captured["summary"]["score_result"]["best_index"] == 2
    assert captured["summary_path"] == json_path
    assert captured["stage_delay"] == 0.2
    assert captured["animate_arm"] is True
