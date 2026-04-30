from __future__ import annotations

import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class _ImageSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = dict(attrs)
        source = values.get("src")
        if source:
            self.sources.append(source)


def _resolved_site_path(page: Path, source: str) -> Path | None:
    parsed = urlparse(source)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("data:"):
        return None
    if parsed.path.startswith("/worldforge/"):
        return SITE / unquote(parsed.path.removeprefix("/worldforge/"))
    if parsed.path.startswith("/"):
        return None
    return (page.parent / unquote(parsed.path)).resolve()


def test_built_docs_image_sources_resolve_to_site_files() -> None:
    pytest.importorskip("mkdocs")
    subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    missing: list[str] = []
    for page in SITE.rglob("*.html"):
        parser = _ImageSourceParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for source in parser.sources:
            resolved = _resolved_site_path(page, source)
            if resolved is None:
                continue
            if not resolved.is_relative_to(SITE):
                missing.append(f"{page.relative_to(SITE)} -> {source} escapes site/")
            elif not resolved.exists():
                missing.append(f"{page.relative_to(SITE)} -> {source}")

    assert missing == []


def test_health_readiness_runbook_documents_required_operational_signals() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")

    for status in ("ready", "provider_unconfigured", "provider_unhealthy"):
        assert status in operations
        assert status in playbooks

    required_header = (
        "| State | Symptom | Likely cause | First command | Expected signal | Escalation point |"
    )
    assert required_header in playbooks
    for incident in (
        "process live",
        "provider unconfigured",
        "provider unhealthy",
        "upstream degraded",
        "workflow failing",
    ):
        assert incident in playbooks

    assert "WorldForge does not own upstream SLA" in playbooks
    assert "Alert routing, paging policy" in playbooks
