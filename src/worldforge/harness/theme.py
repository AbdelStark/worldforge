"""Color palette for TheWorldHarness themes.

This module defines the raw color tokens used by ``worldforge-dark`` and
``worldforge-light``. It is deliberately Textual-free so the harness extra
boundary stays intact (only ``tui.py`` is allowed to import Textual). The
``tui`` module reads these mappings to construct ``textual.theme.Theme``
instances at runtime.

Keys mirror the semantic tokens documented in roadmap section 2.1 plus the
``foreground`` / ``background`` fields the renderer requires to derive shades.
"""

from __future__ import annotations

from typing import Final

# Palette values were lifted from the original tui.py hex literals (greenish
# black / cream amber / sage green family) and balanced for both dark and
# light terminals. Each theme defines every token used at runtime; nothing is
# shared across themes by design.
WORLDFORGE_DARK_PALETTE: Final[dict[str, str]] = {
    "primary": "#8ec5a3",
    "secondary": "#6f9c84",
    "accent": "#d8c46a",
    "warning": "#d8c46a",
    "error": "#c8616b",
    "success": "#8ec5a3",
    "foreground": "#d3d6cf",
    "background": "#101512",
    "surface": "#171f1a",
    "panel": "#3b423e",
    "boost": "#1f2823",
    "muted": "#6f7770",
}

WORLDFORGE_LIGHT_PALETTE: Final[dict[str, str]] = {
    "primary": "#3a7a5a",
    "secondary": "#2e5d46",
    "accent": "#a8782a",
    "warning": "#a8782a",
    "error": "#9c2a36",
    "success": "#3a7a5a",
    "foreground": "#1f2624",
    "background": "#f4f1e6",
    "surface": "#ffffff",
    "panel": "#dcd8c8",
    "boost": "#e8e3d2",
    "muted": "#5b635c",
}

THEME_NAME_DARK: Final[str] = "worldforge-dark"
THEME_NAME_LIGHT: Final[str] = "worldforge-light"

# Per-flow capability label fallbacks. Source of truth lives on
# ``HarnessFlow.capability``; this map is only used as a defensive default if
# a future flow forgets to declare one.
FLOW_CAPABILITY_FALLBACKS: Final[dict[str, str]] = {
    "leworldmodel": "score",
    "lerobot": "policy",
    "diagnostics": "diagnostics",
}
