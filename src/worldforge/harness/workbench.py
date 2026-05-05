"""Provider development workbench checks."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from worldforge.models import JSONDict, ProviderEvent, WorldForgeError
from worldforge.providers import BaseProvider, ProviderError
from worldforge.providers.catalog import DOC_CAPABILITY_ORDER, PROVIDER_CATALOG
from worldforge.providers.runtime_manifest import load_runtime_manifest
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
PROVIDER_INDEX_DOC = "docs/src/providers/README.md"
PROVIDER_COHORT_DOC = "docs/src/provider-cohort-selection.md"
LIVE_SMOKE_EVIDENCE_DOC = "docs/src/live-smoke-evidence.json"

_CONFORMANCE_HELPERS: dict[str, str] = {
    "predict": "assert_predict_conformance",
    "generate": "assert_generate_conformance",
    "transfer": "assert_transfer_conformance",
    "reason": "assert_reason_conformance",
    "embed": "assert_embed_conformance",
    "score": "assert_score_conformance",
    "policy": "assert_policy_conformance",
}

_PROMOTION_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "experimental": (
        "selection_record",
        "docs_page",
        "catalog_or_candidate_index",
        "runtime_manifest",
        "fixture_coverage",
        "conformance_helpers",
        "redaction_checks",
    ),
    "beta": (
        "runtime_manifest",
        "fixture_coverage",
        "conformance_helpers",
        "redaction_checks",
        "prepared_host_smoke_record",
    ),
    "stable": (
        "runtime_manifest",
        "fixture_coverage",
        "conformance_helpers",
        "redaction_checks",
        "prepared_host_smoke_artifact",
        "release_evidence",
    ),
}

_STATUS_ORDER = ("scaffold", "experimental", "beta", "stable")


@dataclass(frozen=True, slots=True)
class _WorkbenchTarget:
    provider: BaseProvider
    source: str
    catalog_registered: bool
    docs_page: str


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
    target = _create_workbench_target(provider_name, events.append)
    provider = target.provider
    profile = provider.profile()
    docs_base = docs_root or Path.cwd()
    started = perf_counter()

    required_tests = _required_tests(provider)
    planned_capabilities = _planned_capabilities(provider)
    health_report = _health_report(provider)
    invocation = _run_safe_conformance(provider, live=live)
    fixture_report = _fixture_report(provider.name, fixtures_dir=fixtures_dir)
    runtime_manifest_report = _runtime_manifest_report(provider.name)
    docs_report = _docs_report(provider, docs_root=docs_base, target=target)
    catalog_report = _catalog_report(provider.name, docs_root=docs_base, target=target)
    event_report = _event_report(events, provider=provider.name)
    checks = [
        _status_check(
            "profile",
            "passed",
            (
                f"{provider.name} advertises {', '.join(required_tests) or 'no'} capability "
                f"tests; planned capabilities: {', '.join(planned_capabilities) or 'none'}."
            ),
        ),
        health_report,
        invocation,
        fixture_report,
        runtime_manifest_report,
        docs_report,
        catalog_report,
        event_report,
    ]
    promotion_report = _promotion_report(
        provider,
        checks=checks,
        docs_root=docs_base,
        target=target,
        required_tests=required_tests,
        planned_capabilities=planned_capabilities,
    )
    checks.append(
        _status_check(
            "promotion_evidence",
            "passed",
            _promotion_detail(promotion_report),
        )
    )

    status = (
        "passed" if all(check["status"] in {"passed", "skipped"} for check in checks) else "failed"
    )
    return {
        "provider": provider.name,
        "target_source": target.source,
        "catalog_registered": target.catalog_registered,
        "status": status,
        "live": live,
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        "profile": profile.to_dict(),
        "required_tests": required_tests,
        "planned_capabilities": planned_capabilities,
        "promotion": promotion_report,
        "checks": checks,
        "safe_artifacts": _safe_artifacts(provider.name, checks=checks, target=target),
        "validation_commands": _validation_commands(provider.name, docs_root=docs_base),
        "docs": {
            "authoring_guide": AUTHORING_DOC,
            "catalog_check": CATALOG_CHECK_COMMAND,
            "fixture_pattern": FIXTURE_DOC,
            "provider_index": PROVIDER_INDEX_DOC,
            "selection_record": PROVIDER_COHORT_DOC,
        },
        "issue_summary": _issue_summary(provider.name, checks),
    }


def provider_workbench_markdown(report: JSONDict) -> str:
    """Render a provider workbench report as pasteable Markdown."""

    lines = [
        f"# Provider Workbench: `{report['provider']}`",
        "",
        f"- status: `{report['status']}`",
        f"- target source: `{report['target_source']}`",
        f"- catalog registered: `{str(report['catalog_registered']).lower()}`",
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
    planned_capabilities = report.get("planned_capabilities", [])
    lines.extend(["", "## Planned Capability Surface", ""])
    if isinstance(planned_capabilities, list) and planned_capabilities:
        lines.extend(f"- `{capability}`" for capability in planned_capabilities)
    else:
        lines.append("- none declared")
    lines.extend(["", "## Checks", ""])
    lines.extend(
        f"- `{check['status']}` `{check['name']}`: {check['detail']}" for check in report["checks"]
    )
    promotion = report["promotion"]
    lines.extend(
        [
            "",
            "## Promotion Evidence",
            "",
            f"- current status: `{promotion['current_status']}`",
        ]
    )
    missing_by_status = promotion["missing_evidence_by_status"]
    if isinstance(missing_by_status, dict) and missing_by_status:
        lines.extend(
            f"- missing for `{status}`: {', '.join(f'`{item}`' for item in missing) or 'none'}"
            for status, missing in missing_by_status.items()
        )
    else:
        lines.append("- no promotion gaps for the current status")
    lines.extend(["", "## Safe Artifacts", ""])
    safe_artifacts = report.get("safe_artifacts", [])
    if isinstance(safe_artifacts, list) and safe_artifacts:
        lines.extend(
            f"- `{artifact['path']}`: {artifact['note']}"
            for artifact in safe_artifacts
            if isinstance(artifact, dict)
        )
    else:
        lines.append("- no local artifacts were referenced")
    lines.extend(["", "## Validation Commands", ""])
    validation_commands = report.get("validation_commands", [])
    if isinstance(validation_commands, list):
        lines.extend(f"- `{command}`" for command in validation_commands)
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


def _create_workbench_target(
    provider_name: str,
    event_handler: Callable[[ProviderEvent], None],
) -> _WorkbenchTarget:
    for entry in PROVIDER_CATALOG:
        if entry.name == provider_name:
            return _WorkbenchTarget(
                provider=entry.create(event_handler=event_handler),
                source="provider_catalog",
                catalog_registered=True,
                docs_page=entry.docs_page or "README.md",
            )
    if provider_name == "jepa-wms":
        from worldforge.providers.jepa_wms import JEPAWMSProvider

        return _WorkbenchTarget(
            provider=JEPAWMSProvider(event_handler=event_handler),
            source="direct_construction_candidate",
            catalog_registered=False,
            docs_page="jepa-wms.md",
        )
    valid = ", ".join(entry.name for entry in PROVIDER_CATALOG)
    raise ProviderError(
        f"Provider '{provider_name}' is unknown. Valid providers: {valid}, jepa-wms."
    )


def _required_tests(provider: BaseProvider) -> list[str]:
    profile = provider.profile()
    return [
        _CONFORMANCE_HELPERS[capability]
        for capability in DOC_CAPABILITY_ORDER
        if profile.capabilities.supports(capability) and capability in _CONFORMANCE_HELPERS
    ]


def _planned_capabilities(provider: BaseProvider) -> list[str]:
    planned = getattr(provider, "planned_capabilities", ())
    return [
        capability
        for capability in DOC_CAPABILITY_ORDER
        if isinstance(planned, tuple | list) and capability in planned
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

    patterns = _fixture_patterns(provider)
    fixture_paths = sorted({path for pattern in patterns for path in resolved_dir.glob(pattern)})
    if not fixture_paths:
        rendered_patterns = ", ".join(str(resolved_dir / pattern) for pattern in patterns)
        return _status_check(
            "fixtures",
            "skipped",
            f"no fixture playback files matched {rendered_patterns}.",
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
        "patterns": [str(resolved_dir / pattern) for pattern in patterns],
    }


def _fixture_patterns(provider: str) -> tuple[str, ...]:
    prefixes = [provider]
    module_prefix = provider.replace("-", "_")
    if module_prefix not in prefixes:
        prefixes.append(module_prefix)
    return tuple(f"{prefix}_*.json" for prefix in prefixes)


def _runtime_manifest_report(provider: str) -> JSONDict:
    try:
        manifest = load_runtime_manifest(provider)
    except WorldForgeError as exc:
        return _status_check("runtime_manifest", "skipped", str(exc))
    return {
        **_status_check(
            "runtime_manifest",
            "passed",
            (
                f"{provider}:schema-{manifest.schema_version}; capabilities "
                f"{', '.join(manifest.capabilities)}; minimum smoke "
                f"`{manifest.minimum_smoke_command}`."
            ),
        ),
        "manifest_id": f"{provider}:schema-{manifest.schema_version}",
        "path": f"src/worldforge/providers/runtime_manifests/{provider}.json",
        "minimum_smoke_command": manifest.minimum_smoke_command,
        "expected_success_signal": manifest.expected_success_signal,
    }


def _docs_report(provider: BaseProvider, *, docs_root: Path, target: _WorkbenchTarget) -> JSONDict:
    profile = provider.profile()
    docs_paths = [
        docs_root / f"docs/src/providers/{target.docs_page}",
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


def _catalog_report(provider: str, *, docs_root: Path, target: _WorkbenchTarget) -> JSONDict:
    index_path = docs_root / PROVIDER_INDEX_DOC
    try:
        text = index_path.read_text(encoding="utf-8").lower()
    except OSError as exc:
        return _status_check("catalog", "failed", f"failed to read {index_path}: {exc}")
    needle = f"`{provider}`"
    if needle not in text:
        return _status_check(
            "catalog",
            "failed",
            f"{PROVIDER_INDEX_DOC} does not mention `{provider}`.",
        )
    target_kind = (
        "catalog provider" if target.catalog_registered else "direct-construction candidate"
    )
    return _status_check(
        "catalog",
        "passed",
        f"{PROVIDER_INDEX_DOC} indexes `{provider}` as a {target_kind}.",
    )


def _event_report(events: list[ProviderEvent], *, provider: str) -> JSONDict:
    try:
        assert_provider_events_conform(events, provider=provider)
    except AssertionError as exc:
        return _status_check("events", "failed", str(exc))
    return _status_check("events", "passed", f"{len(events)} provider event(s) are issue-safe.")


def _promotion_report(
    provider: BaseProvider,
    *,
    checks: list[JSONDict],
    docs_root: Path,
    target: _WorkbenchTarget,
    required_tests: list[str],
    planned_capabilities: list[str],
) -> JSONDict:
    profile = provider.profile()
    current_status = profile.implementation_status
    present = _present_evidence(
        provider.name,
        checks=checks,
        docs_root=docs_root,
        target=target,
        required_tests=required_tests,
        planned_capabilities=planned_capabilities,
    )
    missing_by_status: dict[str, list[str]] = {}
    for status in _future_statuses(current_status):
        required = set(_PROMOTION_REQUIREMENTS[status])
        missing_by_status[status] = sorted(required.difference(present))
    next_status = next(iter(missing_by_status), None)
    return {
        "current_status": current_status,
        "next_status": next_status,
        "present_evidence": sorted(present),
        "missing_evidence_by_status": missing_by_status,
        "required_evidence_by_status": {
            status: list(requirements)
            for status, requirements in _PROMOTION_REQUIREMENTS.items()
            if status in missing_by_status
        },
    }


def _present_evidence(
    provider: str,
    *,
    checks: list[JSONDict],
    docs_root: Path,
    target: _WorkbenchTarget,
    required_tests: list[str],
    planned_capabilities: list[str],
) -> set[str]:
    checks_by_name = {str(check["name"]): check for check in checks}
    present: set[str] = set()
    if _doc_mentions(docs_root / PROVIDER_COHORT_DOC, provider):
        present.add("selection_record")
    if checks_by_name.get("docs", {}).get("status") == "passed":
        present.add("docs_page")
    if checks_by_name.get("catalog", {}).get("status") == "passed":
        present.add("catalog_or_candidate_index")
    if checks_by_name.get("runtime_manifest", {}).get("status") == "passed":
        present.add("runtime_manifest")
    if checks_by_name.get("fixtures", {}).get("status") == "passed":
        present.add("fixture_coverage")
    if required_tests or planned_capabilities:
        present.add("conformance_helpers")
    if checks_by_name.get("events", {}).get("status") == "passed":
        present.add("redaction_checks")
    if _live_smoke_entry(docs_root / LIVE_SMOKE_EVIDENCE_DOC, provider) is not None:
        present.add("prepared_host_smoke_record")
    live_entry = _live_smoke_entry(docs_root / LIVE_SMOKE_EVIDENCE_DOC, provider)
    if isinstance(live_entry, dict) and live_entry.get("artifact_path"):
        present.add("prepared_host_smoke_artifact")
    if target.catalog_registered and _doc_mentions(
        docs_root / "docs/src/claim-evidence-map.md",
        provider,
    ):
        present.add("release_evidence")
    return present


def _future_statuses(current_status: str) -> tuple[str, ...]:
    if current_status not in _STATUS_ORDER:
        return tuple(_PROMOTION_REQUIREMENTS)
    index = _STATUS_ORDER.index(current_status)
    return tuple(
        status for status in _STATUS_ORDER[index + 1 :] if status in _PROMOTION_REQUIREMENTS
    )


def _promotion_detail(promotion: JSONDict) -> str:
    next_status = promotion.get("next_status")
    if not next_status:
        return f"{promotion['current_status']} has no higher promotion status in this workbench."
    missing_by_status = promotion.get("missing_evidence_by_status", {})
    missing = []
    if isinstance(missing_by_status, dict):
        missing = list(missing_by_status.get(next_status, []))
    if not missing:
        return f"{promotion['current_status']} has evidence needed for {next_status}."
    return (
        f"{promotion['current_status']} missing for {next_status}: "
        f"{', '.join(str(item) for item in missing)}."
    )


def _safe_artifacts(
    provider: str,
    *,
    checks: list[JSONDict],
    target: _WorkbenchTarget,
) -> list[JSONDict]:
    artifacts = [
        _artifact(AUTHORING_DOC, "provider authoring guide"),
        _artifact(PROVIDER_INDEX_DOC, "generated provider index"),
        _artifact(f"docs/src/providers/{target.docs_page}", "provider documentation page"),
        _artifact(PROVIDER_COHORT_DOC, "provider selection record"),
        _artifact(FIXTURE_DOC.replace("<provider>", provider), "provider fixture pattern"),
    ]
    runtime = next((check for check in checks if check["name"] == "runtime_manifest"), None)
    if isinstance(runtime, dict) and isinstance(runtime.get("path"), str):
        artifacts.append(_artifact(runtime["path"], "runtime manifest"))
    return artifacts


def _artifact(path: str, note: str) -> JSONDict:
    return {"path": path, "note": note, "safe_to_attach": True}


def _validation_commands(provider: str, *, docs_root: Path) -> list[str]:
    commands = [
        "uv run pytest tests/test_provider_workbench.py tests/test_provider_catalog_docs.py",
        CATALOG_CHECK_COMMAND,
        "uv run mkdocs build --strict",
    ]
    test_path = docs_root / f"tests/test_{provider.replace('-', '_')}_provider.py"
    if test_path.exists():
        commands.insert(0, f"uv run pytest {test_path.relative_to(docs_root)}")
    return commands


def _doc_mentions(path: Path, provider: str) -> bool:
    try:
        return provider.lower() in path.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _live_smoke_entry(path: Path, provider: str) -> JSONDict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return None
    for entry in payload["entries"]:
        if isinstance(entry, dict) and entry.get("provider") == provider:
            return dict(entry)
    return None


def _status_check(name: str, status: str, detail: str) -> JSONDict:
    return {"name": name, "status": status, "detail": detail}


def _issue_summary(provider: str, checks: list[JSONDict]) -> str:
    failures = [check for check in checks if check["status"] == "failed"]
    if not failures:
        return f"`{provider}` workbench passed with no failing checks."
    rendered = "; ".join(f"{check['name']}: {check['detail']}" for check in failures)
    return f"`{provider}` workbench failures: {rendered}"
