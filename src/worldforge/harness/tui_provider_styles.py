"""Textual-free CSS constants for provider, eval, and benchmark screens."""

from __future__ import annotations

REGISTER_PROVIDER_MODAL_DEFAULT_CSS = """
    RegisterProviderModal {
        align: center middle;
    }

    RegisterProviderModal > #register-provider-card {
        width: 64;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    RegisterProviderModal .field-label {
        color: $text-muted;
        height: 1;
    }

    RegisterProviderModal Input {
        margin-bottom: 1;
    }

    RegisterProviderModal #register-provider-actions {
        height: auto;
        align: right middle;
        padding-top: 1;
    }

    RegisterProviderModal Button {
        margin-left: 1;
    }
    """

PROVIDERS_SCREEN_DEFAULT_CSS = """
    ProvidersScreen {
        background: $background;
        color: $foreground;
    }

    #providers-root {
        height: 1fr;
        padding: 1 2;
    }

    #providers-body {
        height: 1fr;
    }

    #providers-table-wrap {
        width: 2fr;
        margin-right: 1;
        border: round $panel;
        background: $surface;
    }

    #providers-table {
        height: 1fr;
        background: $surface;
    }

    #providers-empty {
        padding: 1 2;
        color: $text-muted;
    }

    #providers-empty.hidden {
        display: none;
    }

    #providers-detail {
        width: 1fr;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #providers-log {
        height: 10;
        margin-top: 1;
        border: round $panel;
        background: $surface;
    }

    #providers-actions {
        height: 3;
        margin-top: 1;
        align: right middle;
    }

    #providers-actions Button {
        margin-left: 1;
    }
    """

EVAL_SCREEN_DEFAULT_CSS = """
    EvalScreen {
        background: $background;
        color: $foreground;
    }

    #eval-root {
        height: 1fr;
        padding: 1 2;
    }

    #eval-form {
        width: 34;
        margin-right: 1;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #eval-output {
        width: 1fr;
    }

    #eval-log {
        height: 10;
        border: round $panel;
        background: $surface;
    }

    #eval-verdict {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
    }

    EvalScreen Select, EvalScreen Button {
        margin-bottom: 1;
    }
    """

BENCHMARK_SCREEN_DEFAULT_CSS = """
    BenchmarkScreen {
        background: $background;
        color: $foreground;
    }

    #benchmark-root {
        height: 1fr;
        padding: 1 2;
    }

    #benchmark-form {
        width: 34;
        margin-right: 1;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #benchmark-output {
        width: 1fr;
    }

    #benchmark-log {
        height: 10;
        border: round $panel;
        background: $surface;
    }

    #benchmark-stats {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
    }

    BenchmarkScreen Select, BenchmarkScreen Input, BenchmarkScreen Button {
        margin-bottom: 1;
    }
    """
