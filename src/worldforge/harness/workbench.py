"""Provider development workbench checks."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from worldforge.models import JSONDict, ProviderEvent, WorldForgeError
from worldforge.providers import BaseProvider, ProviderError
from worldforge.providers.catalog import DOC_CAPABILITY_ORDER, PROVIDER_CATALOG
from worldforge.testing import (
    assert_embed_conformance,
    assert_generate_conformance,
    assert_predict_conformance,
    assert_provider_events_conform,
    assert_reason_conformance,
    assert_transfer_conformance,
)

AUTHORING_DOC = "docs/src/provider-authoring-guide.md"
CATALOG_CHECK_COMMAND = "uv run python scripts/generate_provider_docs.py --check"
FIXTURE_DOC = "tests/fixtures/providers/<provider>_*.json"

_CONFORMANCE_HELPERS: dict[str, str] = {
    "predict": "assert_predict_conformance",
    "generate": "assert_generate_conformance",
    "transfer": "assert_transfer_conformance",
    "reason": "assert_reason_conformance",
    "embed": "assert_embed_conformance",
    "score": "assert_score_conformance",
    "policy": "assert_policy_conformance",
}


def provider_workbench_report(
    provider_name: str,
    *,
    live: bool = False,
    fixtures_dir: Path | None = None,
    docs_root: Path | None = None,
) -> JSONDict:
    """Return an issue-ready provider workbench report.

    Default execution is checkout-safe: only deterministic local providers are
    invoked. Optional runtimes and credentialed providers are inspected but not
    called unless ``live=True`` is explicit.
    """

    events: list[ProviderEvent] = []
    provider = _create_catalog_provider(provider_name, events.append)
    profile = provider.profile()
    docs_base = docs_root or Path.cwd()
    started = perf_counter()

    required_tests = _required_tests(provider)
    health_report = _health_report(provider)
    invocation = _run_safe_conformance(provider, live=live)
    fixture_report = _fixture_report(provider.name, fixtures_dir=fixtures_dir)
    docs_report = _docs_report(provider, docs_root=docs_base)
    event_report = _event_report(events, provider=provider.name)

    checks = [
        _status_check(
            "profile",
            "passed",
            f"{provider.name} advertises {', '.join(required_tests) or 'no'} capability tests.",
        ),
        health_report,
        invocation,
        fixture_report,
        docs_report,
        event_report,
    ]
    status = (
        "passed" if all(check["status"] in {"passed", "skipped"} for check in checks) else "failed"
    )
    return {
        "provider": provider.name,
        "status": status,
        "live": live,
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        "profile": profile.to_dict(),
        "required_tests": required_tests,
        "checks": checks,
        "docs": {
            "authoring_guide": AUTHORING_DOC,
            "catalog_check": CATALOG_CHECK_COMMAND,
            "fixture_pattern": FIXTURE_DOC,
        },
        "issue_summary": _issue_summary(provider.name, checks),
    }


def provider_workbench_markdown(report: JSONDict) -> str:
    """Render a provider workbench report as pasteable Markdown."""

    lines = [
        f"# Provider Workbench: `{report['provider']}`",
        "",
        f"- status: `{report['status']}`",
        f"- live calls: `{str(report['live']).lower()}`",
        f"- duration_ms: `{report['duration_ms']}`",
        "",
        "## Required Capability Tests",
        "",
    ]
    required_tests = report["required_tests"]
    if isinstance(required_tests, list) and required_tests:
        lines.extend(f"- `{test}`" for test in required_tests)
    else:
        lines.append("- none advertised")
    lines.extend(["", "## Checks", ""])
    lines.extend(
        f"- `{check['status']}` `{check['name']}`: {check['detail']}" for check in report["checks"]
    )
    docs = report["docs"]
    lines.extend(
        [
            "",
            "## Author Links",
            "",
            f"- authoring guide: `{docs['authoring_guide']}`",
            f"- generated catalog check: `{docs['catalog_check']}`",
            f"- fixture pattern: `{docs['fixture_pattern']}`",
            "",
            "## Issue Summary",
            "",
            str(report["issue_summary"]),
        ]
    )
    return "\n".join(lines)


def _create_catalog_provider(
    provider_name: str,
    event_handler: Callable[[ProviderEvent], None],
) -> BaseProvider:
    for entry in PROVIDER_CATALOG:
        if entry.name == provider_name:
            return entry.create(event_handler=event_handler)
    valid = ", ".join(entry.name for entry in PROVIDER_CATALOG)
    raise ProviderError(f"Provider '{provider_name}' is unknown. Valid providers: {valid}.")


def _required_tests(provider: BaseProvider) -> list[str]:
    profile = provider.profile()
    return [
        _CONFORMANCE_HELPERS[capability]
        for capability in DOC_CAPABILITY_ORDER
        if profile.capabilities.supports(capability) and capability in _CONFORMANCE_HELPERS
    ]


def _run_safe_conformance(provider: BaseProvider, *, live: bool) -> JSONDict:
    profile = provider.profile()
    can_invoke = live or (profile.is_local and profile.deterministic and provider.configured())
    if not can_invoke:
        return _status_check(
            "conformance",
            "skipped",
            "live provider calls were not selected; rerun with --live on a prepared host.",
        )

    generated = None
    exercised: list[str] = []
    try:
        if profile.capabilities.predict:
            assert_predict_conformance(provider)
            exercised.append("predict")
        if profile.capabilities.reason:
            assert_reason_conformance(provider)
            exercised.append("reason")
        if profile.capabilities.embed:
            assert_embed_conformance(provider)
            exercised.append("embed")
        if profile.capabilities.generate:
            generated = assert_generate_conformance(provider)
            exercised.append("generate")
        if profile.capabilities.transfer:
            assert_transfer_conformance(provider, clip=generated)
            exercised.append("transfer")
    except (AssertionError, ProviderError, WorldForgeError) as exc:
        return _status_check("conformance", "failed", str(exc))

    return _status_check(
        "conformance",
        "passed",
        f"exercised {', '.join(exercised) if exercised else 'metadata-only'} safely.",
    )


def _health_report(provider: BaseProvider) -> JSONDict:
    health = provider.health()
    configured = provider.configured()
    if health.healthy and not configured:
        return _status_check(
            "health",
            "failed",
            "provider reports healthy while configured() is false.",
        )
    state = "healthy" if health.healthy else "unhealthy"
    config = "configured" if configured else "unconfigured"
    return {
        **_status_check("health", "passed", f"{state}; {config}; {health.details}"),
        "health": health.to_dict(),
        "configured": configured,
    }


def _fixture_report(provider: str, *, fixtures_dir: Path | None) -> JSONDict:
    resolved_dir = fixtures_dir or Path("tests/fixtures/providers")
    if not resolved_dir.exists():
        return _status_check("fixtures", "skipped", f"{resolved_dir} does not exist.")

    fixture_paths = sorted(resolved_dir.glob(f"{provider}_*.json"))
    if not fixture_paths:
        return _status_check(
            "fixtures",
            "skipped",
            f"no fixture playback files matched {resolved_dir}/{provider}_*.json.",
        )

    try:
        for path in fixture_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise WorldForgeError(f"{path} must contain a JSON object.")
    except (OSError, json.JSONDecodeError, WorldForgeError) as exc:
        return _status_check("fixtures", "failed", str(exc))

    return {
        **_status_check(
            "fixtures",
            "passed",
            f"validated {len(fixture_paths)} provider fixture JSON file(s).",
        ),
        "paths": [str(path) for path in fixture_paths],
    }


def _docs_report(provider: BaseProvider, *, docs_root: Path) -> JSONDict:
    profile = provider.profile()
    docs_paths = [
        docs_root / f"docs/src/providers/{provider.name}.md",
        docs_root / "docs/src/providers/README.md",
    ]
    docs_path = next((path for path in docs_paths if path.exists()), None)
    if docs_path is None:
        return _status_check(
            "docs",
            "failed",
            "provider docs page is missing; update docs/src/providers/ and generated catalog.",
        )

    text = docs_path.read_text(encoding="utf-8").lower()
    missing_terms = [
        term
        for term in (profile.implementation_status, *profile.supported_tasks)
        if term and term.lower() not in text
    ]
    if missing_terms:
        return _status_check(
            "docs",
            "failed",
            f"{docs_path} does not mention profile metadata: {', '.join(missing_terms)}.",
        )

    return _status_check(
        "docs",
        "passed",
        f"{docs_path} covers profile metadata; run `{CATALOG_CHECK_COMMAND}` before PR.",
    )


def _event_report(events: list[ProviderEvent], *, provider: str) -> JSONDict:
    try:
        assert_provider_events_conform(events, provider=provider)
    except AssertionError as exc:
        return _status_check("events", "failed", str(exc))
    return _status_check("events", "passed", f"{len(events)} provider event(s) are issue-safe.")


def _status_check(name: str, status: str, detail: str) -> JSONDict:
    return {"name": name, "status": status, "detail": detail}


def _issue_summary(provider: str, checks: list[JSONDict]) -> str:
    failures = [check for check in checks if check["status"] == "failed"]
    if not failures:
        return f"`{provider}` workbench passed with no failing checks."
    rendered = "; ".join(f"{check['name']}: {check['detail']}" for check in failures)
    return f"`{provider}` workbench failures: {rendered}"
