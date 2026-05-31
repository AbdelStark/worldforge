from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _rendering_module():
    pytest.importorskip("rich")
    import worldforge.harness.robotics_tui_rendering as module

    return module


def _render_text(renderable: object) -> str:
    rich_console = pytest.importorskip("rich.console")
    console = rich_console.Console(record=True, width=150, color_system=None)
    console.print(renderable)
    return console.export_text(styles=False)


def _summary(tmp_path: Path) -> dict[str, object]:
    return {
        "checkpoint_display": "LeWorldModel object checkpoint",
        "checkpoint": "/safe/checkpoint.ckpt",
        "inputs": {
            "policy_path": "lerobot/diffusion_pusht",
            "approx_float32_mb": 1.25,
            "total_tensor_elements": 32768,
        },
        "score_result": {
            "best_index": 2,
            "best_score": 0.125,
            "scores": [0.7, 0.4, 0.125],
        },
        "visualization": {
            "candidate_targets": [
                {"index": 0, "x": 0.75, "y": 0.75, "z": 0.0},
                {"index": 1, "x": 0.625, "y": 0.625, "z": 0.0},
                {"index": 2, "x": 0.375, "y": 0.375, "z": 0.0},
            ],
        },
        "execution": {"final_block_position": {"x": 0.375, "y": 0.375, "z": 0.0}},
        "metrics": {"plan_latency_ms": 23.0, "total_latency_ms": 42.0},
        "provider_events": [
            {
                "provider": "lerobot",
                "operation": "policy",
                "phase": "success",
                "duration_ms": 12.5,
            },
            {
                "provider": "leworldmodel",
                "operation": "score",
                "phase": "success",
                "duration_ms": 17.25,
            },
        ],
        "rerun": {
            "save_path": str(tmp_path / "real-run.rrd"),
            "recording_size_bytes": 128,
            "recording_written": True,
        },
        "tensorboard": {
            "log_dir": str(tmp_path / "tensorboard"),
            "events_written": True,
            "run_name": "robotics-showcase",
        },
    }


def test_robotics_tui_rendering_imports_without_textual() -> None:
    rendering = _rendering_module()
    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(rendering)
        from worldforge.harness.robotics_view import RoboticsHelpSectionSpec

        assert len(reloaded.ROBOTICS_ARM_FRAMES) == 4
        assert reloaded.robotics_latency_bar(1.0, 2.0).strip()
        plain = reloaded.robotics_help_section_renderable(RoboticsHelpSectionSpec("plain"))
        styled = reloaded.robotics_help_section_renderable(
            RoboticsHelpSectionSpec("styled", style_token="success")
        )
        assert plain == "plain"
        assert styled.plain == "styled"
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(rendering)


def test_robotics_view_help_spec_imports_without_textual() -> None:
    import worldforge.harness.robotics_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        spec = reloaded.ROBOTICS_TABLETOP_HELP_SCREEN_SPEC
        assert spec.card_id == "robotics-help-card"
        assert spec.title_id == "robotics-help-title"
        assert spec.title == "Reading the tabletop replay"
        assert len(spec.sections) == 4
        assert spec.sections[1] == reloaded.RoboticsHelpSectionSpec(
            reloaded.ROBOTICS_TABLETOP_DIAGRAM,
            style_token="success",
        )
        assert all(section.classes == "robotics-help-section" for section in spec.sections)
        assert spec.sections[-1].text.startswith("Boundary:")
        assert [
            (binding.key, binding.action, binding.description, binding.show)
            for binding in reloaded.ROBOTICS_TABLETOP_HELP_BINDING_SPECS
        ] == [
            ("escape", "dismiss", "Close", True),
            ("q", "dismiss", "Close", False),
        ]
        app_spec = reloaded.ROBOTICS_SHOWCASE_APP_SPEC
        assert app_spec.title == "WorldForge Robotics Showcase"
        assert app_spec.body_id == "robotics-body"
        assert app_spec.body_selector == "#robotics-body"
        assert app_spec.default_stage_delay_s == reloaded.ROBOTICS_SHOWCASE_DEFAULT_STAGE_DELAY_S
        assert app_spec.arm_frame_interval_s == reloaded.ROBOTICS_ARM_FRAME_INTERVAL_S
        assert app_spec.default_stage_delay_s == 0.35
        assert app_spec.arm_frame_interval_s == 0.32
        assert reloaded.ROBOTICS_SHOWCASE_BODY_SELECTOR == "#robotics-body"
        assert [binding.action for binding in app_spec.bindings] == [
            "show_tabletop_help",
            "open_rerun",
            "open_tensorboard",
            "quit",
            "toggle_theme",
        ]
        assert [stage.stage_id for stage in app_spec.stages] == [
            "hero",
            "pipeline",
            "guide",
            "rerun",
            "tensorboard",
            "metrics",
            "arm",
            "candidates",
            "tabletop",
            "events",
        ]
        assert app_spec.stages[3].required_artifact == "rerun"
        assert app_spec.stages[4].required_artifact == "tensorboard"
        assert reloaded.robotics_showcase_stage_enabled(
            app_spec.stages[3],
            has_rerun_recording=True,
            has_tensorboard_logs=False,
        )
        assert not reloaded.robotics_showcase_stage_enabled(
            app_spec.stages[3],
            has_rerun_recording=False,
            has_tensorboard_logs=True,
        )
        assert reloaded.robotics_showcase_stage_enabled(
            app_spec.stages[4],
            has_rerun_recording=False,
            has_tensorboard_logs=True,
        )
        assert reloaded.robotics_showcase_stage_enabled(
            app_spec.stages[0],
            has_rerun_recording=False,
            has_tensorboard_logs=False,
        )
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_robotics_tui_renderers_preserve_report_contract(tmp_path: Path) -> None:
    rendering = _rendering_module()
    summary = _summary(tmp_path)

    rendered = "\n".join(
        _render_text(panel)
        for panel in (
            rendering.robotics_hero_panel(summary, summary_path=tmp_path / "summary.json"),
            rendering.robotics_pipeline_panel(),
            rendering.robotics_report_guide_panel(),
            rendering.robotics_metrics_panel(summary),
            rendering.robotics_candidate_panel(summary),
            rendering.robotics_tabletop_panel(summary),
            rendering.robotics_event_panel(summary),
            rendering.robotics_rerun_panel(summary),
            rendering.robotics_tensorboard_panel(summary),
            rendering.robotics_arm_panel(
                summary,
                frame_lines=rendering.ROBOTICS_ARM_FRAMES[0],
                target_line=rendering.robotics_arm_target_line(summary),
            ),
            rendering.robotics_progress_panel("Preparing replay"),
        )
    )

    assert "REAL ROBOTICS POLICY + WORLD MODEL" in rendered
    assert "Pipeline Flow" in rendered
    assert "Runtime + Tensor Contract" in rendered
    assert "Candidate Ranking" in rendered
    assert "SELECTED" in rendered
    assert "Tabletop Replay" in rendered
    assert "Provider Event Log" in rendered
    assert "Rerun Recording" in rendered
    assert "TensorBoard Logs" in rendered
    assert "selected candidate #2" in rendered
    assert "Preparing replay" in rendered


def test_robotics_tui_renderers_handle_missing_optional_artifacts() -> None:
    rendering = _rendering_module()
    summary: dict[str, object] = {}

    assert "not enabled" in _render_text(rendering.robotics_rerun_panel(summary))
    assert "not enabled" in _render_text(rendering.robotics_tensorboard_panel(summary))
    assert "mock final unavailable" in _render_text(
        rendering.robotics_arm_panel(
            summary,
            frame_lines=rendering.ROBOTICS_ARM_FRAMES[0],
            target_line=rendering.robotics_arm_target_line(summary),
        )
    )
