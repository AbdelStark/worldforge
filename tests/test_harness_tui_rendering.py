from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from worldforge.harness.models import HarnessFlow, HarnessMetric, HarnessRun, HarnessStep
from worldforge.harness.run_history_models import RunHistoryRecord
from worldforge.models import ProviderEvent


def _rendering_module():
    pytest.importorskip("rich")
    import worldforge.harness.tui_rendering as module

    return module


def _render_text(renderable: object) -> str:
    rich_console = pytest.importorskip("rich.console")
    console = rich_console.Console(record=True, width=120, color_system=None)
    console.print(renderable)
    return console.export_text(styles=False)


def _flow() -> HarnessFlow:
    return HarnessFlow(
        id="demo",
        title="Demo Flow",
        short_title="Demo",
        focus="contract",
        provider="mock",
        capability="predict",
        command="worldforge demo",
        accent="cyan",
        summary="A deterministic flow.",
    )


def _colors():
    rendering = _rendering_module()
    return rendering.TuiRenderColors(
        foreground="white",
        accent="cyan",
        success="green",
        warning="yellow",
        error="red",
        muted="bright_black",
        panel="blue",
    )


def test_tui_rendering_imports_without_textual() -> None:
    rendering = _rendering_module()
    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(rendering)
        assert reloaded.TuiRenderColors(
            foreground="",
            accent="",
            success="",
            warning="",
            error="",
            muted="",
            panel="",
        )
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(rendering)


def test_tui_log_view_imports_without_textual() -> None:
    import worldforge.harness.tui_log_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        spec = reloaded.RichLogSpec("events")
        assert spec.widget_id == "events"
        assert spec.selector == "#events"
        assert spec.max_lines == reloaded.DEFAULT_RICH_LOG_MAX_LINES
        with pytest.raises(ValueError, match="max_lines"):
            reloaded.RichLogSpec("bad", max_lines=0)
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_report_view_imports_without_textual() -> None:
    import worldforge.harness.tui_report_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        spec = reloaded.ReportCompletionSpec(
            kind="eval",
            export_widget_id="eval-export",
            status_widget_id="eval-verdict",
        )
        run_control = reloaded.ReportRunControlSpec(
            worker_group="eval",
            worker_name="eval.run",
            notify_title="Eval",
            cancel_message="Cancelled eval run.",
            mismatch_title="Capability mismatch",
        )
        assert spec.kind == "eval"
        assert spec.export_selector == "#eval-export"
        assert spec.status_selector == "#eval-verdict"
        assert spec.saved_message("report.md") == "Report saved: report.md"
        assert reloaded.report_saved_message("report.md") == "Report saved: report.md"
        assert run_control.worker_group == "eval"
        assert run_control.worker_name == "eval.run"
        assert run_control.notify_title == "Eval"
        assert run_control.cancel_message == "Cancelled eval run."
        assert run_control.mismatch_title == "Capability mismatch"
        assert run_control.mismatch_log_style == "bold red"
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_provider_event_helpers_import_without_textual() -> None:
    pytest.importorskip("rich")
    import worldforge.harness.tui_provider_events as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        event = ProviderEvent(
            provider="mock",
            operation="predict",
            phase="retry",
            attempt=2,
            max_attempts=3,
            duration_ms=12.5,
        )
        rendered = reloaded.format_provider_event(event, timestamp="12:00:00")
        assert "12:00:00" in rendered.plain
        assert "mock.predict" in rendered.plain
        assert reloaded.provider_event_summary(event) == {
            "phase": "retry",
            "latency_ms": 12.5,
            "retries": 1,
        }
        failure = reloaded.provider_event_failure("mock", "predict", RuntimeError("failed"))
        assert failure.phase == "failure"
        assert failure.message == "failed"
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_benchmark_view_imports_without_textual() -> None:
    import worldforge.harness.tui_benchmark_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        view = reloaded.benchmark_sample_progress(
            {
                "provider": "mock",
                "operation": "predict",
                "iteration": 2,
                "latency_ms": 20.0,
            },
            (10.0,),
            total=5,
        )
        assert view.samples == (10.0, 20.0)
        assert view.progress_count == 2
        assert view.log_line == "mock.predict #2 20.00 ms"
        request = reloaded.benchmark_request_from_form(
            provider_value="mock",
            operation_value="predict",
            iterations_value="",
        )
        assert request.request is not None
        assert request.request.iterations == reloaded.DEFAULT_BENCHMARK_ITERATIONS
        assert reloaded.BENCHMARK_RUN_BUTTON_ID == "benchmark-run"
        assert reloaded.BENCHMARK_SCREEN_SPEC.provider.widget_id == "benchmark-provider"
        assert reloaded.BENCHMARK_SCREEN_SPEC.operation.default == "predict"
        assert reloaded.BENCHMARK_SCREEN_SPEC.iterations.default == str(
            reloaded.DEFAULT_BENCHMARK_ITERATIONS
        )
        assert reloaded.BENCHMARK_SCREEN_SPEC.stats.empty_message == (
            "No benchmark run yet — press r to execute."
        )
        assert reloaded.BENCHMARK_SCREEN_SPEC.log.widget_id == "benchmark-log"
        assert reloaded.BENCHMARK_SCREEN_SPEC.log.max_lines == 5000
        assert reloaded.BENCHMARK_SCREEN_SPEC.completion.kind == "benchmark"
        assert reloaded.BENCHMARK_SCREEN_SPEC.completion.export_selector == "#benchmark-export"
        assert reloaded.BENCHMARK_SCREEN_SPEC.completion.status_selector == "#benchmark-stats"
        assert reloaded.BENCHMARK_SCREEN_SPEC.run_control.worker_group == "benchmark"
        assert reloaded.BENCHMARK_SCREEN_SPEC.run_control.worker_name == "benchmark.run"
        assert reloaded.BENCHMARK_SCREEN_SPEC.run_control.notify_title == "Benchmark"
        assert reloaded.BENCHMARK_SCREEN_SPEC.run_control.cancel_message == (
            "Cancelled benchmark run."
        )
        assert reloaded.BENCHMARK_SCREEN_SPEC.run_control.mismatch_title == "Benchmark"
        assert reloaded.BENCHMARK_LOG_SELECTOR == "#benchmark-log"
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.BENCHMARK_BINDING_SPECS
        ] == [
            ("r", "run_benchmark", "Run", True),
            ("escape", "cancel_or_back", "Cancel/Back", True),
        ]
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_benchmark_view_formats_progress_stats() -> None:
    import worldforge.harness.tui_benchmark_view as module

    view = module.benchmark_sample_progress(
        {
            "provider": "mock",
            "operation": "generate",
            "iteration": 5,
            "latency_ms": 50.0,
        },
        (10.0, 20.0, 30.0, 40.0),
        total=5,
    )

    assert view.samples == (10.0, 20.0, 30.0, 40.0, 50.0)
    assert view.latency_ms == 50.0
    assert view.progress_count == 5
    assert view.log_line == "mock.generate #5 50.00 ms"
    assert view.stats_line == "Samples: 5/5  median=30.00 ms  p95=40.00 ms"


def test_tui_benchmark_view_validates_run_form() -> None:
    import worldforge.harness.tui_benchmark_view as module

    accepted = module.benchmark_request_from_form(
        provider_value="mock",
        operation_value="predict",
        iterations_value="7",
    )
    defaulted = module.benchmark_request_from_form(
        provider_value="mock",
        operation_value="embed",
        iterations_value="",
    )
    rejected = module.benchmark_request_from_form(
        provider_value="mock",
        operation_value="predict",
        iterations_value="nope",
    )
    ignored = module.benchmark_request_from_form(
        provider_value=object(),
        operation_value="predict",
        iterations_value="3",
    )

    assert accepted.request is not None
    assert accepted.request.provider == "mock"
    assert accepted.request.operation == "predict"
    assert accepted.request.iterations == 7
    assert defaulted.request is not None
    assert defaulted.request.iterations == module.DEFAULT_BENCHMARK_ITERATIONS
    assert rejected.request is None
    assert rejected.error == "Iterations must be an integer."
    assert ignored.request is None
    assert ignored.error is None


def test_tui_eval_view_imports_without_textual() -> None:
    import worldforge.harness.tui_eval_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        request = reloaded.eval_request_from_form(
            suite_value="planning",
            provider_value="mock",
        )
        assert request is not None
        assert request.suite_id == "planning"
        assert request.provider == "mock"
        assert reloaded.eval_running_log_line("planning", "mock") == "running planning x mock"
        assert reloaded.report_saved_message("report.md") == "Report saved: report.md"
        assert reloaded.EVAL_RUN_BUTTON_ID == "eval-run"
        assert reloaded.EVAL_SCREEN_SPEC.suite.widget_id == "eval-suite"
        assert reloaded.EVAL_SCREEN_SPEC.suite.default == "planning"
        assert reloaded.EVAL_SCREEN_SPEC.provider.label == "Provider"
        assert reloaded.EVAL_SCREEN_SPEC.verdict.empty_message == (
            "No suite run yet — press r to execute."
        )
        assert reloaded.EVAL_SCREEN_SPEC.log.widget_id == "eval-log"
        assert reloaded.EVAL_SCREEN_SPEC.log.max_lines == 5000
        assert reloaded.EVAL_SCREEN_SPEC.completion.kind == "eval"
        assert reloaded.EVAL_SCREEN_SPEC.completion.export_selector == "#eval-export"
        assert reloaded.EVAL_SCREEN_SPEC.completion.status_selector == "#eval-verdict"
        assert reloaded.EVAL_SCREEN_SPEC.run_control.worker_group == "eval"
        assert reloaded.EVAL_SCREEN_SPEC.run_control.worker_name == "eval.run"
        assert reloaded.EVAL_SCREEN_SPEC.run_control.notify_title == "Eval"
        assert reloaded.EVAL_SCREEN_SPEC.run_control.cancel_message == "Cancelled eval run."
        assert reloaded.EVAL_SCREEN_SPEC.run_control.mismatch_title == "Capability mismatch"
        assert reloaded.EVAL_LOG_SELECTOR == "#eval-log"
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.EVAL_BINDING_SPECS
        ] == [
            ("r", "run_eval", "Run", True),
            ("escape", "cancel_or_back", "Cancel/Back", True),
        ]
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_eval_view_ignores_incomplete_select_values() -> None:
    import worldforge.harness.tui_eval_view as module

    assert module.eval_request_from_form(suite_value=object(), provider_value="mock") is None
    assert module.eval_request_from_form(suite_value="planning", provider_value=object()) is None


def test_tui_app_view_imports_without_textual() -> None:
    import worldforge.harness.tui_app_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        titles = [spec.title for spec in reloaded.SYSTEM_COMMAND_SPECS]
        assert "Jump: Worlds" in titles
        assert "New world" in titles
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.APP_BINDING_SPECS
        ] == [
            ("?", "show_help", "Help", True),
            ("q", "quit", "Quit", True),
            ("ctrl+t", "toggle_theme", "Theme", False),
            ("g,h", "switch_screen('home')", "Jump: Home", False),
            ("g,r", "switch_screen('run-inspector')", "Jump: Run Inspector", False),
            ("g,w", "switch_screen('worlds')", "Jump: Worlds", False),
            ("g,p", "switch_screen('providers')", "Jump: Providers", False),
            ("g,e", "switch_screen('eval')", "Jump: Eval", False),
            ("g,b", "switch_screen('benchmark')", "Jump: Benchmark", False),
            ("g,u", "switch_screen('runs')", "Jump: Runs", False),
        ]
        assert reloaded.APP_SCREEN_NAMES == (
            "home",
            "run-inspector",
            "worlds",
            "providers",
            "eval",
            "benchmark",
            "runs",
        )
        assert [
            (
                spec.name,
                spec.system_title,
                spec.system_help,
                spec.binding_key,
                spec.binding_description,
            )
            for spec in reloaded.APP_SCREEN_ROUTE_SPECS
        ] == [
            ("home", "Jump: Home", "Open the Home screen", "g,h", "Jump: Home"),
            (
                "run-inspector",
                "Jump: Run Inspector",
                "Open the Run Inspector screen",
                "g,r",
                "Jump: Run Inspector",
            ),
            ("worlds", "Jump: Worlds", "Open the Worlds screen", "g,w", "Jump: Worlds"),
            (
                "providers",
                "Jump: Providers",
                "Open the Providers screen",
                "g,p",
                "Jump: Providers",
            ),
            ("eval", "Run eval suite", "Open the Eval screen", "g,e", "Jump: Eval"),
            (
                "benchmark",
                "Run benchmark",
                "Open the Benchmark screen",
                "g,b",
                "Jump: Benchmark",
            ),
            ("runs", "Jump: Runs", "Open preserved run history", "g,u", "Jump: Runs"),
        ]
        assert reloaded.app_screen_name("providers") == "providers"
        assert reloaded.app_screen_name("missing") is None
        assert reloaded.initial_screen_name("providers") == "providers"
        assert reloaded.initial_screen_name("missing") == "home"
        assert reloaded.flow_system_command_title("Demo") == "Run flow: Demo"
        assert reloaded.flow_system_command_help("Demo") == (
            "Switch the Run Inspector to Demo and run it"
        )
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_app_view_builds_dynamic_palette_specs(tmp_path: Path) -> None:
    import worldforge.harness.tui_app_view as module

    report = tmp_path / "eval-planning.md"
    workspace = tmp_path / "runs" / "run-001"
    record = SimpleNamespace(run_id="run-001", path=workspace)

    specs = module.palette_item_specs(
        world_ids=("lab",),
        providers=("mock",),
        report_paths=(report,),
        run_records=(record,),
    )

    assert [(spec.title, spec.help_text, spec.kind, spec.value) for spec in specs] == [
        ("World: lab", "Open the Worlds screen", "world", "lab"),
        ("Provider: mock", "Open the Providers screen", "provider", "mock"),
        ("Run: eval-planning.md", "Open the preserved report", "report", report),
        (
            "Run workspace: run-001",
            "Open the preserved run workspace",
            "run-workspace",
            workspace,
        ),
    ]


def test_tui_app_view_decides_run_inspector_refresh() -> None:
    import worldforge.harness.tui_app_view as module

    assert module.screen_needs_run_inspector_refresh(
        "run-inspector",
        is_run_inspector=True,
        can_run_flows=False,
    )
    assert not module.screen_needs_run_inspector_refresh(
        "run-inspector",
        is_run_inspector=True,
        can_run_flows=True,
    )
    assert not module.screen_needs_run_inspector_refresh(
        "worlds",
        is_run_inspector=True,
        can_run_flows=False,
    )
    assert not module.screen_needs_run_inspector_refresh(
        "run-inspector",
        is_run_inspector=False,
        can_run_flows=False,
    )


def test_harness_theme_policy_imports_without_textual() -> None:
    import worldforge.harness.theme as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        assert reloaded.THEME_ORDER == (
            "worldforge-dark",
            "worldforge-light",
            "worldforge-high-contrast",
        )
        assert [(spec.name, spec.dark) for spec in reloaded.THEME_SPECS] == [
            ("worldforge-dark", True),
            ("worldforge-light", False),
            ("worldforge-high-contrast", True),
        ]
        assert all("foreground" in spec.palette for spec in reloaded.THEME_SPECS)
        assert reloaded.next_theme_name("worldforge-dark") == "worldforge-light"
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_harness_theme_policy_cycles_and_falls_back() -> None:
    import worldforge.harness.theme as module

    assert module.next_theme_name("worldforge-dark") == "worldforge-light"
    assert module.next_theme_name("worldforge-light") == "worldforge-high-contrast"
    assert module.next_theme_name("worldforge-high-contrast") == "worldforge-dark"
    assert module.next_theme_name("unknown-theme") == "worldforge-light"


def test_tui_chrome_view_imports_without_textual() -> None:
    import worldforge.harness.tui_chrome_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        flow = _flow()
        fallback_flow = HarnessFlow(
            id="diagnostics",
            title="Diagnostics",
            short_title="Diagnostics",
            focus="provider diagnostics",
            provider="WorldForge",
            capability="",
            command="worldforge harness --flow diagnostics",
            accent="blue",
            summary="Inspect provider state.",
        )
        run = HarnessRun(
            flow=flow,
            state_dir=Path(".worldforge"),
            summary={},
            steps=(),
            metrics=(),
            transcript=(),
            kind="eval",
        )

        assert reloaded.CHROME_CONTAINER_ID == "chrome"
        assert reloaded.BREADCRUMB_ID == "breadcrumb"
        assert reloaded.BREADCRUMB_SELECTOR == "#breadcrumb"
        assert reloaded.PROVIDER_PILL_ID == "provider-pill"
        assert reloaded.PROVIDER_PILL_SELECTOR == "#provider-pill"
        assert reloaded.screen_chrome(
            "providers",
            provider_label=reloaded.provider_capability_label("mock", "predict"),
        ) == reloaded.ScreenChrome(("worldforge", "providers"), "mock · predict")
        assert reloaded.flow_provider_label(flow) == "mock · predict"
        assert reloaded.flow_provider_label(fallback_flow) == "WorldForge · diagnostics"
        assert reloaded.run_inspector_fixed_chrome(run) == reloaded.ScreenChrome(
            ("worldforge", "run-inspector", "Demo"),
            "predict",
        )
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_help_view_collects_unique_rows_without_textual() -> None:
    import worldforge.harness.tui_help_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        screen_binding = SimpleNamespace(
            key="?",
            description="Help",
            action="show_help",
        )
        duplicate = SimpleNamespace(
            key="?",
            description="Duplicate help",
            action="show_help",
        )
        hidden_binding = SimpleNamespace(
            key="g,w",
            description=None,
            action="switch_screen('worlds')",
        )
        app_binding = SimpleNamespace(
            key="q",
            description="Quit",
            action="quit",
        )
        app = SimpleNamespace(
            _bindings=SimpleNamespace(
                key_to_bindings={
                    "q": [app_binding],
                    "?": [duplicate],
                }
            )
        )
        source = SimpleNamespace(
            app=app,
            _bindings=SimpleNamespace(
                key_to_bindings={
                    "?": [screen_binding],
                    "g,w": [hidden_binding],
                }
            ),
        )

        assert reloaded.HELP_MODAL_SPEC.card_id == "help-card"
        assert reloaded.HELP_MODAL_SPEC.title.widget_id == "help-title"
        assert reloaded.HELP_MODAL_SPEC.table.widget_id == "help-table"
        assert reloaded.HELP_MODAL_SPEC.table.columns == ("Key", "Description", "Action")
        assert reloaded.HELP_TABLE_SELECTOR == "#help-table"
        assert reloaded.HELP_MODAL_SPEC.footnote.widget_id == "help-footnote"
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.HELP_BINDING_SPECS
        ] == [
            ("escape", "dismiss", "Close", True),
            ("q", "dismiss", "Close", False),
        ]
        assert reloaded.PLACEHOLDER_MODAL_SPEC.card_id == "placeholder-card"
        assert reloaded.PLACEHOLDER_MODAL_SPEC.title_id == "placeholder-title"
        assert reloaded.PLACEHOLDER_MODAL_SPEC.body_id == "placeholder-body"
        assert reloaded.PLACEHOLDER_MODAL_SPEC.footnote.widget_id == "placeholder-footnote"
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.PLACEHOLDER_BINDING_SPECS
        ] == [
            ("escape", "dismiss", "Close", True),
            ("q", "dismiss", "Close", False),
            ("enter", "dismiss", "Close", False),
        ]
        assert reloaded.placeholder_title("M2") == "Coming in milestone M2"
        assert reloaded.help_binding_rows(source) == (
            reloaded.HelpBindingRow("?", "Help", "show_help"),
            reloaded.HelpBindingRow("g,w", "", "switch_screen('worlds')"),
            reloaded.HelpBindingRow("q", "Quit", "quit"),
        )
        assert reloaded.help_binding_rows(SimpleNamespace()) == ()
        assert reloaded.help_binding_rows(None) == ()
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_run_history_view_filter_contract_imports_without_textual(tmp_path: Path) -> None:
    import worldforge.harness.run_history_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        result = reloaded.run_history_filter_from_form(
            reloaded.RunHistoryFilterForm(
                provider=" mock ",
                capability=" predict ",
                status="completed",
                created_from="2026-05-28",
                artifact_type=" json ",
            )
        )
        invalid = reloaded.run_history_filter_from_form(
            reloaded.RunHistoryFilterForm(created_from="not-a-date")
        )
        record = RunHistoryRecord(
            run_id="run-1",
            kind="flow",
            status="completed",
            provider="mock",
            operation="predict",
            capability="predict",
            capabilities=("predict",),
            created_at="2026-05-28T00:00:00Z",
            created_date=None,
            command="worldforge harness --flow diagnostics",
            rerun_command="worldforge harness --open run-1",
            failure_summary="",
            safe_artifact_types=("json",),
            artifact_count=1,
            event_count=2,
            path=tmp_path / "run-1",
            display_path=".worldforge/runs/run-1",
            issue_bundle_command="worldforge harness bundle run-1",
            issue_bundle_path=".worldforge/runs/run-1/issue-bundle",
            comparison_command=None,
            recovery_command=None,
        )

        assert reloaded.RUN_STATUS_FILTER_OPTIONS[0] == ("any status", "")
        assert reloaded.RUN_HISTORY_SCREEN_SPEC.root_id == "runs-root"
        assert reloaded.RUN_HISTORY_SCREEN_SPEC.table_columns == (
            "run",
            "status",
            "provider",
            "capability",
            "artifacts",
        )
        assert reloaded.RUN_HISTORY_SCREEN_SPEC.empty.empty_message == (
            "No preserved runs match the active filters."
        )
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.RUN_HISTORY_BINDING_SPECS
        ] == [
            ("enter", "open_selected", "Open", True),
            ("f", "focus_provider_filter", "Filter", True),
            ("escape", "clear_filters", "Clear", True),
        ]
        assert reloaded.RUN_HISTORY_TABLE_SELECTOR == "#runs-table"
        assert reloaded.RUN_HISTORY_DETAIL_SELECTOR == "#runs-detail"
        assert reloaded.RUN_STATUS_FILTER_ID == "runs-status-filter"
        assert reloaded.RUN_PROVIDER_FILTER_ID == "runs-provider-filter"
        assert "#runs-provider-filter" in reloaded.RUN_FILTER_INPUT_SELECTORS
        assert result.error is None
        assert result.filters.provider == "mock"
        assert result.filters.capability == "predict"
        assert result.filters.status == "completed"
        assert str(result.filters.created_from) == "2026-05-28"
        assert result.filters.artifact_type == "json"
        assert invalid.error == "run history date must use YYYY-MM-DD: not-a-date"
        assert invalid.filters.provider is None
        assert reloaded.selected_run_record({"run-1": record}, "run-1") is record
        assert reloaded.selected_run_record({"run-1": record}, None) is None
        assert reloaded.selected_run_provider_label(record) == "mock"
        assert reloaded.selected_run_provider_label(None) == ""
        assert reloaded.first_visible_run_id(["run-1"]) == "run-1"
        assert reloaded.first_visible_run_id(()) is None
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_home_view_imports_without_textual() -> None:
    import worldforge.harness.tui_home_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        assert reloaded.home_recent_text(world_ids=(), report_paths=(), run_records=()) == (
            "No recent worlds or runs — press [b]n[/] to create a world or [b]e[/] to run an eval."
        )
        assert [
            (spec.target, spec.title, spec.binding, spec.widget_id)
            for spec in reloaded.HOME_JUMP_SPECS
        ] == [
            ("worlds", "Create a world", "n", "jump-create-world"),
            ("providers", "Run a provider", "p", "jump-run-provider"),
            ("eval", "Run an eval", "e", "jump-run-eval"),
            ("runs", "Review runs", "u", "jump-review-runs"),
        ]
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.HOME_JUMP_CARD_BINDING_SPECS
        ] == [("enter", "activate", "Activate", False)]
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.HOME_SCREEN_BINDING_SPECS
        ] == [
            ("n", "jump('worlds')", "Create a world", True),
            ("p", "jump('providers')", "Run a provider", True),
            ("e", "jump('eval')", "Run an eval", True),
            ("u", "jump('runs')", "Review runs", True),
        ]
        assert reloaded.HOME_SCREEN_SPEC.root_id == "home-root"
        assert reloaded.HOME_SCREEN_SPEC.intro.widget_id == "home-intro"
        assert "visual integration reference" in reloaded.HOME_SCREEN_SPEC.intro.text
        assert reloaded.HOME_SCREEN_SPEC.cards_id == "home-cards"
        assert reloaded.HOME_SCREEN_SPEC.recent.widget_id == "home-recent"
        assert reloaded.HOME_RECENT_SELECTOR == "#home-recent"
        assert reloaded.HOME_INITIAL_FOCUS_WIDGET_ID == "jump-create-world"
        assert reloaded.home_jump_target_screen("providers") == "providers"
        assert reloaded.home_jump_target_screen("missing") is None
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_run_inspector_view_contract_imports_without_textual() -> None:
    import worldforge.harness.tui_run_inspector_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        flow = _flow()
        second = HarnessFlow(
            id="score-lab",
            title="Score Lab",
            short_title="Score",
            focus="score planning",
            provider="score-provider",
            capability="score",
            command="worldforge score",
            accent="yellow",
            summary="Score candidates.",
        )
        flows = (flow, second)
        flow_map = {item.id: item for item in flows}

        assert reloaded.RUN_INSPECTOR_DEFAULT_FLOW_ID == "leworldmodel"
        assert reloaded.RUN_INSPECTOR_DEFAULT_STEP_DELAY_SECONDS == 0.18
        assert reloaded.RUN_INSPECTOR_RUN_BUTTON_LABEL == "Run selected flow"
        assert reloaded.RUN_INSPECTOR_SCREEN_SPEC.root_id == "root"
        assert reloaded.RUN_INSPECTOR_SCREEN_SPEC.run.widget_id == "run-button"
        assert reloaded.RUN_INSPECTOR_SCREEN_SPEC.run.variant == "warning"
        assert reloaded.RUN_INSPECTOR_FLOW_SELECT_ID == "flow-select"
        assert reloaded.RUN_INSPECTOR_TIMELINE_ID == "timeline"
        assert reloaded.RUN_INSPECTOR_INSPECTOR_ID == "inspector"
        assert reloaded.RUN_INSPECTOR_TRANSCRIPT_ID == "transcript"
        assert reloaded.RUN_INSPECTOR_EXPORT_PREVIEW_ID == "export-preview"
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.RUN_INSPECTOR_BINDING_SPECS
        ] == [("r", "run_selected", "Run", True)]
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.run_inspector_flow_bindings(flows)
        ] == [
            ("1", "select_flow('demo')", "Demo", True),
            ("2", "select_flow('score-lab')", "Score", True),
        ]
        assert reloaded.run_inspector_flow_options(flows) == (
            ("Demo Flow", "demo"),
            ("Score Lab", "score-lab"),
        )
        assert reloaded.run_inspector_flow_card_id(flow) == "flow-card-demo"
        assert reloaded.resolve_run_inspector_flow_id("score-lab", flow_map) == "score-lab"
        assert reloaded.resolve_run_inspector_flow_id("missing", flow_map) == "demo"
        assert reloaded.RUN_INSPECTOR_READY_STEPS[0].title == "Ready"
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_home_view_sorts_recent_worlds_and_formats_summary(tmp_path: Path) -> None:
    import worldforge.harness.tui_home_view as module

    older = tmp_path / "older.json"
    newer = tmp_path / "newer.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")
    os.utime(older, (1.0, 1.0))
    os.utime(newer, (2.0, 2.0))

    world_ids = module.recent_world_ids(
        ("missing", "older", "newer"),
        state_dir=tmp_path,
        limit=2,
    )
    summary = module.home_recent_text(
        world_ids=world_ids,
        report_paths=(tmp_path / "eval-report.md",),
        run_records=(SimpleNamespace(run_id="run-001"),),
    )

    assert world_ids == ["newer", "older"]
    assert summary == "\n".join(
        [
            "Recent",
            "Worlds: newer, older",
            "Reports: eval-report.md",
            "Runs: run-001",
        ]
    )


def test_tui_provider_view_imports_without_textual() -> None:
    import worldforge.harness.tui_provider_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        assert (
            reloaded.provider_capability_cell(
                True,
                implementation_status="ready",
            )
            == "●"
        )
        assert (
            reloaded.provider_capability_cell(
                True,
                implementation_status="scaffold",
            )
            == "○"
        )
        assert (
            reloaded.provider_capability_cell(
                False,
                implementation_status="ready",
            )
            == ""
        )
        assert reloaded.provider_registration_from_form(" mock-alt ").provider_name == "mock-alt"
        assert reloaded.REGISTER_PROVIDER_MODAL_SPEC.name.widget_id == "register-provider-name"
        assert reloaded.REGISTER_PROVIDER_MODAL_SPEC.submit.label == "Register"
        assert reloaded.REGISTER_PROVIDER_MODAL_SPEC.note == (
            "Registers a MockProvider variant. Live optional runtimes remain host-owned."
        )
        assert reloaded.PROVIDER_SCREEN_SPEC.root_id == "providers-root"
        assert reloaded.PROVIDER_SCREEN_SPEC.table.columns[:4] == (
            "provider",
            "status",
            "credentials",
            "runtime",
        )
        assert reloaded.PROVIDER_SCREEN_SPEC.empty.message == (
            "No providers registered — set env vars or run with provider mock."
        )
        assert reloaded.PROVIDER_TABLE_SELECTOR == "#providers-table"
        assert reloaded.PROVIDER_DETAIL_SELECTOR == "#providers-detail"
        assert reloaded.PROVIDER_LOG_SELECTOR == "#providers-log"
        assert reloaded.PROVIDER_SCREEN_SPEC.log.max_lines == 5000
        assert reloaded.PROVIDER_FIELD_LABEL_CLASS == "field-label"
        assert [
            (spec.widget_id, spec.label, spec.variant, spec.action)
            for spec in reloaded.PROVIDER_ACTION_SPECS
        ] == [
            ("provider-run", "Run predict", "primary", "run"),
            ("provider-cancel", "Cancel", "warning", "cancel"),
            ("provider-register", "Register", "default", "register"),
        ]
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.PROVIDER_BINDING_SPECS
        ] == [
            ("enter", "select_provider", "Use", True),
            ("p", "run_predict", "Predict", True),
            ("r", "register_provider", "Register", True),
            ("escape", "cancel_or_back", "Cancel/Back", True),
        ]
        assert [
            (spec.key, spec.action, spec.description, spec.show)
            for spec in reloaded.REGISTER_PROVIDER_BINDING_SPECS
        ] == [("escape", "cancel", "Cancel", True)]
        assert reloaded.PROVIDER_RUN_BUTTON_ID == "provider-run"
        assert reloaded.PROVIDER_CANCEL_BUTTON_ID == "provider-cancel"
        assert reloaded.PROVIDER_REGISTER_BUTTON_ID == "provider-register"
        assert (
            reloaded.provider_predict_target(
                current_provider="missing",
                current_row_provider="mock",
                provider_names=("mock",),
            )
            == "mock"
        )
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_tui_provider_view_formats_provider_table_rows() -> None:
    import worldforge.harness.tui_provider_view as module
    from worldforge.harness.connectors import ProviderConnectorSummary

    configured = ProviderConnectorSummary(
        name="mock",
        status="configured",
        registered=True,
        health="healthy",
        capabilities=("predict", "generate"),
        implementation_status="ready",
        required_env_vars=(),
        missing_env_vars=(),
        optional_dependencies=(),
        smoke_command="uv run worldforge provider info mock",
        triage_steps=(),
    )
    scaffold = ProviderConnectorSummary(
        name="jepa",
        status="scaffold",
        registered=False,
        health="credential-gated scaffold",
        capabilities=("score",),
        implementation_status="scaffold",
        required_env_vars=("JEPA_API_KEY",),
        missing_env_vars=("JEPA_API_KEY",),
        optional_dependencies=(),
        smoke_command="uv run worldforge provider info jepa",
        triage_steps=(),
    )
    missing_dependency = ProviderConnectorSummary(
        name="leworldmodel",
        status="missing_dependency",
        registered=True,
        health="missing optional dependency stable_worldmodel",
        capabilities=("score",),
        implementation_status="experimental",
        required_env_vars=(),
        missing_env_vars=(),
        optional_dependencies=("stable-worldmodel",),
        smoke_command="uv run worldforge-smoke-leworldmodel",
        triage_steps=(),
    )

    assert module.provider_table_row(configured, capability_names=("predict", "score")) == (
        "mock",
        "configured",
        "ok",
        "ok",
        "●",
        "",
    )
    assert module.provider_table_row(scaffold, capability_names=("predict", "score")) == (
        "jepa",
        "scaffold",
        "n/a",
        "scaffold",
        "",
        "○",
    )
    assert module.provider_table_row(
        missing_dependency,
        capability_names=("predict", "score"),
    ) == (
        "leworldmodel",
        "missing_dependency",
        "ok",
        "deps",
        "",
        "●",
    )


def test_tui_provider_view_validates_registration_name() -> None:
    import worldforge.harness.tui_provider_view as module

    accepted = module.provider_registration_from_form("  mock-alt  ")
    rejected = module.provider_registration_from_form("   ")

    assert accepted.provider_name == "mock-alt"
    assert accepted.error is None
    assert rejected.provider_name is None
    assert rejected.error == "Provider id must be non-empty."


def test_tui_provider_view_selects_predict_and_cancel_targets() -> None:
    import worldforge.harness.tui_provider_view as module

    assert (
        module.provider_predict_target(
            current_provider="mock-alt",
            current_row_provider="mock",
            provider_names=("mock", "mock-alt"),
        )
        == "mock-alt"
    )
    assert (
        module.provider_predict_target(
            current_provider="missing",
            current_row_provider="mock",
            provider_names=("mock",),
        )
        == "mock"
    )
    assert (
        module.provider_predict_target(
            current_provider=object(),
            current_row_provider=None,
            provider_names=(),
        )
        == "mock"
    )
    assert (
        module.provider_cancel_target(
            current_provider="mock-alt",
            current_row_provider="mock",
        )
        == "mock-alt"
    )
    assert (
        module.provider_cancel_target(
            current_provider=object(),
            current_row_provider="mock",
        )
        == "mock"
    )


def test_tui_provider_view_success_summary_shape() -> None:
    import worldforge.harness.tui_provider_view as module

    assert module.provider_success_summary(12.5) == {
        "phase": "success",
        "latency_ms": 12.5,
        "retries": 0,
    }


def test_timeline_and_flow_card_render_expected_labels() -> None:
    rendering = _rendering_module()
    colors = _colors()
    flow = _flow()
    step = HarnessStep("Validate", "Run local gate.", "passed", "report.json")

    timeline = rendering.timeline_panel(
        flow,
        (step,),
        active_index=0,
        complete_count=1,
        colors=colors,
    )
    card = rendering.flow_card_panel(flow, selected=True, colors=colors)

    assert "Demo Flow / execution trace" in _render_text(timeline)
    assert "Demo" in _render_text(card)


def test_run_inspector_and_export_preview_render_contract_details() -> None:
    rendering = _rendering_module()
    colors = _colors()
    run = HarnessRun(
        flow=_flow(),
        state_dir=Path(".worldforge"),
        summary={},
        steps=(),
        metrics=(HarnessMetric("latency", "12 ms", "p50"),),
        transcript=("started", "finished"),
        provider_events=(
            {
                "phase": "retry",
                "provider": "mock",
                "operation": "predict",
                "attempt": 2,
                "duration_ms": 12.5,
            },
        ),
        validation_errors=("missing artifact",),
    )

    inspector = rendering.run_inspector_panel(run, colors=colors)
    transcript = rendering.run_transcript_panel(run, colors=colors)
    export = rendering.export_preview_panel(
        {"markdown": "short report"},
        report_format="markdown",
        colors=colors,
    )
    long_report = "x" * rendering.EXPORT_PREVIEW_MAX_CHARS + "TAIL"
    truncated_export = rendering.export_preview_panel(
        {"markdown": long_report},
        report_format="markdown",
        colors=colors,
    )

    assert "Provider events" in _render_text(inspector)
    assert "missing artifact" in _render_text(inspector)
    assert "finished" in _render_text(transcript)
    assert "short report" in _render_text(export)
    truncated_text = _render_text(truncated_export)
    assert rendering.EXPORT_PREVIEW_TRUNCATED_MESSAGE in truncated_text
    assert "TAIL" not in truncated_text
