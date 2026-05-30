"""Textual-free CSS constants for TheWorldHarness world editor screens."""

from __future__ import annotations

NEW_WORLD_SCREEN_DEFAULT_CSS = """
    NewWorldScreen {
        align: center middle;
    }

    NewWorldScreen > #new-world-card {
        width: 70%;
        max-width: 84;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    NewWorldScreen #new-world-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $accent;
    }

    NewWorldScreen #new-world-error {
        height: auto;
        color: $error;
        padding: 1 0 0 0;
    }

    NewWorldScreen #new-world-error.hidden {
        display: none;
    }

    NewWorldScreen .field-label {
        color: $text-muted;
        height: 1;
    }

    NewWorldScreen Input, NewWorldScreen Select {
        margin-bottom: 1;
    }

    NewWorldScreen #new-world-actions {
        height: auto;
        padding-top: 1;
        align: right middle;
    }

    NewWorldScreen Button {
        margin-left: 1;
    }
    """

EDIT_OBJECT_SCREEN_DEFAULT_CSS = """
    EditObjectScreen {
        align: center middle;
    }

    EditObjectScreen > #edit-object-card {
        width: 60%;
        max-width: 72;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    EditObjectScreen #edit-object-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $accent;
    }

    EditObjectScreen .field-label {
        color: $text-muted;
        height: 1;
    }

    EditObjectScreen Input {
        margin-bottom: 1;
    }

    EditObjectScreen #edit-object-error {
        color: $error;
        height: auto;
    }

    EditObjectScreen #edit-object-error.hidden {
        display: none;
    }

    EditObjectScreen #edit-object-actions {
        height: auto;
        padding-top: 1;
        align: right middle;
    }

    EditObjectScreen Button {
        margin-left: 1;
    }
    """

WORLDS_SCREEN_DEFAULT_CSS = """
    WorldsScreen {
        background: $background;
        color: $foreground;
    }

    #worlds-root {
        height: 1fr;
        padding: 1 2;
    }

    #worlds-filter-row {
        height: 3;
        margin-bottom: 1;
    }

    #worlds-filter-label {
        width: auto;
        padding: 1 1 0 0;
        color: $text-muted;
    }

    #worlds-filter {
        width: 1fr;
    }

    #worlds-body {
        height: 1fr;
    }

    #worlds-table-wrap {
        width: 2fr;
        margin-right: 1;
        border: round $panel;
        background: $surface;
    }

    #worlds-detail {
        width: 1fr;
        padding: 1 2;
        border: round $panel;
        background: $surface;
        color: $foreground;
    }

    #worlds-detail.-focused {
        border: round $accent;
    }

    #worlds-empty {
        padding: 1 2;
        color: $text-muted;
    }

    #worlds-empty.hidden {
        display: none;
    }

    #worlds-table.hidden {
        display: none;
    }
    """

WORLD_EDIT_SCREEN_DEFAULT_CSS = """
    WorldEditScreen {
        background: $background;
        color: $foreground;
    }

    #edit-root {
        height: 1fr;
        padding: 1 2;
    }

    #edit-title {
        height: 1;
        text-style: bold;
        color: $accent;
    }

    #edit-body {
        height: 1fr;
    }

    #edit-form {
        width: 2fr;
        margin-right: 1;
        border: round $panel;
        background: $surface;
        padding: 1 2;
    }

    #edit-preview {
        width: 1fr;
        border: round $panel;
        background: $surface;
        padding: 1 2;
        color: $foreground;
    }

    #edit-preview.-staged {
        border: round $warning;
    }

    #edit-objects {
        height: 10;
        margin-top: 1;
        background: $surface;
    }

    #edit-objects-header {
        height: 1;
        color: $text-muted;
    }

    .field-label {
        height: 1;
        color: $text-muted;
    }

    Input, Select {
        margin-bottom: 1;
    }

    #edit-preview-caption {
        height: 1;
        color: $warning;
    }

    #edit-preview-caption.hidden {
        display: none;
    }
    """
