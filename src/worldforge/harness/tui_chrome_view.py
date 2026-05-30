"""Textual-free chrome state for TheWorldHarness screens."""

from __future__ import annotations

from dataclasses import dataclass

from worldforge.harness.models import HarnessFlow, HarnessRun
from worldforge.harness.theme import FLOW_CAPABILITY_FALLBACKS


@dataclass(frozen=True, slots=True)
class ChromeWidgetSpec:
    widget_id: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class ChromeLayoutSpec:
    container_id: str
    breadcrumb: ChromeWidgetSpec
    provider_pill: ChromeWidgetSpec


CHROME_LAYOUT_SPEC = ChromeLayoutSpec(
    container_id="chrome",
    breadcrumb=ChromeWidgetSpec("breadcrumb"),
    provider_pill=ChromeWidgetSpec("provider-pill"),
)
CHROME_CONTAINER_ID = CHROME_LAYOUT_SPEC.container_id
BREADCRUMB_ID = CHROME_LAYOUT_SPEC.breadcrumb.widget_id
BREADCRUMB_SELECTOR = CHROME_LAYOUT_SPEC.breadcrumb.selector
PROVIDER_PILL_ID = CHROME_LAYOUT_SPEC.provider_pill.widget_id
PROVIDER_PILL_SELECTOR = CHROME_LAYOUT_SPEC.provider_pill.selector


@dataclass(frozen=True, slots=True)
class ScreenChrome:
    path: tuple[str, ...]
    provider_label: str = ""


def screen_chrome(*path_parts: str, provider_label: str = "") -> ScreenChrome:
    return ScreenChrome(("worldforge", *path_parts), provider_label)


def provider_capability_label(provider: str, capability: str) -> str:
    return f"{provider} · {capability}" if capability else provider


def flow_provider_label(flow: HarnessFlow) -> str:
    capability = flow.capability or FLOW_CAPABILITY_FALLBACKS.get(flow.id, "")
    return provider_capability_label(flow.provider, capability)


def run_inspector_flow_chrome(flow: HarnessFlow, provider_label: str) -> ScreenChrome:
    return screen_chrome("run-inspector", flow.short_title, provider_label=provider_label)


def run_inspector_fixed_chrome(run: HarnessRun) -> ScreenChrome:
    return screen_chrome(
        "run-inspector",
        run.flow.short_title,
        provider_label=run.flow.capability,
    )
