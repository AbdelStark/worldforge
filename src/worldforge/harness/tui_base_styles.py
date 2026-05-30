"""Shared Textual-free CSS constants for TheWorldHarness shell screens."""

from __future__ import annotations

BREADCRUMB_DEFAULT_CSS = """
    Breadcrumb {
        height: 1;
        padding: 0 2;
        background: $boost;
        color: $foreground;
    }
    """

PROVIDER_STATUS_PILL_DEFAULT_CSS = """
    ProviderStatusPill {
        height: 1;
        padding: 0 2;
        background: $boost;
        color: $foreground;
        text-style: bold;
    }
    """

JUMP_CARD_DEFAULT_CSS = """
    JumpCard {
        height: 7;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
        color: $foreground;
    }
    JumpCard:focus, JumpCard:focus-within {
        border: round $accent;
        background: $boost;
    }
    """

HOME_SCREEN_DEFAULT_CSS = """
    HomeScreen {
        background: $background;
        color: $foreground;
    }

    #home-root {
        padding: 1 2;
        height: 1fr;
    }

    #home-intro {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
    }

    #home-cards {
        height: auto;
    }

    #home-recent {
        height: auto;
        margin-top: 1;
        padding: 1 2;
        border: round $panel;
        background: $surface;
        color: $text-muted;
    }
    """

RUNS_SCREEN_DEFAULT_CSS = """
    RunsScreen {
        background: $background;
        color: $foreground;
    }

    #runs-root {
        padding: 1 2;
        height: 1fr;
    }

    #runs-filter-row {
        height: auto;
        margin-bottom: 1;
    }

    #runs-filter-row Input, #runs-filter-row Select {
        width: 1fr;
        margin-right: 1;
    }

    #runs-body {
        height: 1fr;
    }

    #runs-table-wrap {
        width: 2fr;
        margin-right: 1;
    }

    #runs-table {
        height: 1fr;
    }

    #runs-empty {
        height: 1fr;
        align: center middle;
        color: $text-muted;
    }

    #runs-empty.hidden {
        display: none;
    }

    #runs-table.hidden {
        display: none;
    }

    #runs-detail {
        width: 1fr;
        padding: 1 2;
        border: round $panel;
        background: $surface;
        color: $foreground;
    }
    """

RUN_INSPECTOR_SCREEN_DEFAULT_CSS = """
    RunInspectorScreen {
        background: $background;
        color: $foreground;
    }

    #root {
        height: 1fr;
        padding: 1 2;
    }

    #hero {
        height: 10;
        margin-bottom: 1;
    }

    #body {
        height: 1fr;
    }

    #rail {
        width: 30;
        margin-right: 1;
    }

    #timeline {
        width: 1fr;
        margin-right: 1;
    }

    #inspector-column {
        width: 42;
    }

    FlowCard {
        height: 6;
        margin-bottom: 1;
    }

    Select {
        margin-bottom: 1;
    }

    Button {
        margin-bottom: 1;
    }

    #transcript {
        height: 14;
        margin-top: 1;
    }
    """

HELP_SCREEN_DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > #help-card {
        width: 70%;
        max-width: 90;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    HelpScreen #help-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $accent;
    }

    HelpScreen DataTable {
        height: auto;
        max-height: 30;
        background: $surface;
    }

    HelpScreen #help-footnote {
        height: auto;
        padding: 1 0 0 0;
        color: $text-muted;
    }
    """

PLACEHOLDER_SCREEN_DEFAULT_CSS = """
    PlaceholderScreen {
        align: center middle;
    }

    PlaceholderScreen > #placeholder-card {
        width: 60%;
        max-width: 80;
        height: auto;
        padding: 1 2;
        border: round $warning;
        background: $surface;
    }

    PlaceholderScreen #placeholder-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $warning;
    }

    PlaceholderScreen #placeholder-body {
        height: auto;
        color: $foreground;
    }

    PlaceholderScreen #placeholder-footnote {
        height: auto;
        padding: 1 0 0 0;
        color: $text-muted;
    }
    """

CONFIRM_DELETE_SCREEN_DEFAULT_CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }

    ConfirmDeleteScreen > #confirm-card {
        width: 60%;
        max-width: 72;
        height: auto;
        padding: 1 2;
        border: round $error;
        background: $surface;
    }

    ConfirmDeleteScreen #confirm-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $error;
    }

    ConfirmDeleteScreen #confirm-prompt {
        height: auto;
        color: $foreground;
    }

    ConfirmDeleteScreen #confirm-actions {
        height: auto;
        padding-top: 1;
        align: right middle;
    }

    ConfirmDeleteScreen Button {
        margin-left: 1;
    }
    """

THE_WORLD_HARNESS_APP_CSS = """
    Header {
        background: $surface;
        color: $foreground;
    }

    Footer {
        background: $surface;
        color: $foreground;
    }

    #chrome {
        height: 1;
        background: $boost;
    }

    #breadcrumb {
        width: 1fr;
    }

    #provider-pill {
        width: auto;
    }
    """
