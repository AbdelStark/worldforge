"""Provider lifecycle hook orchestration."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from worldforge.models import (
    JSONDict,
    ProviderLifecycleResult,
    ProviderLifecycleStatus,
)

_LIFECYCLE_STATUS_PRECEDENCE = ("teardown-failed", "failed", "skipped", "ready")
_LIFECYCLE_ISSUE_STATUSES = frozenset({"teardown-failed", "failed", "skipped"})
_LIFECYCLE_TEARDOWN_HOOK = "teardown"


def provider_lifecycle_result(
    *,
    provider: str,
    hook: str,
    status: str,
    started: float | None = None,
    ready: bool | None = None,
    details: str = "",
    skip_reason: str = "",
    evidence: JSONDict | None = None,
) -> ProviderLifecycleResult:
    if ready is None:
        ready = status in {"no-op", "ready"}
    latency_ms = 0.0 if started is None else max(0.1, (perf_counter() - started) * 1000)
    return ProviderLifecycleResult(
        provider=provider,
        hook=hook,
        status=status,
        ready=ready,
        latency_ms=latency_ms,
        details=details,
        skip_reason=skip_reason,
        evidence=dict(evidence or {}),
    )


def build_provider_lifecycle_status(
    *,
    provider: str,
    preflight: Callable[[], ProviderLifecycleResult],
    warmup: Callable[[], ProviderLifecycleResult] | None = None,
    teardown: Callable[[], ProviderLifecycleResult] | None = None,
) -> ProviderLifecycleStatus:
    """Run optional lifecycle hooks and return a typed diagnostics status."""

    preflight_result = _invoke_lifecycle_hook(
        provider=provider,
        hook="preflight",
        callback=preflight,
    )
    warmup_result = None
    if warmup is not None and preflight_result.ready:
        warmup_result = _invoke_lifecycle_hook(
            provider=provider,
            hook="warmup",
            callback=warmup,
        )
    teardown_result = None
    if teardown is not None:
        teardown_result = _invoke_lifecycle_hook(
            provider=provider,
            hook="teardown",
            callback=teardown,
        )
    return _aggregate_lifecycle_status(
        provider,
        preflight=preflight_result,
        warmup=warmup_result,
        teardown=teardown_result,
    )


def _invoke_lifecycle_hook(
    *,
    provider: str,
    hook: str,
    callback: Callable[[], ProviderLifecycleResult],
) -> ProviderLifecycleResult:
    try:
        result = callback()
    except Exception as exc:
        return _lifecycle_failure_result(
            provider=provider,
            hook=hook,
            details=f"{hook} hook failed: {exc}",
        )
    return _normalize_lifecycle_hook_result(provider=provider, hook=hook, result=result)


def _lifecycle_failure_status(hook: str) -> str:
    if hook == _LIFECYCLE_TEARDOWN_HOOK:
        return "teardown-failed"
    return "failed"


def _lifecycle_failure_result(
    *,
    provider: str,
    hook: str,
    details: str,
    skip_reason: str = "",
    evidence: JSONDict | None = None,
) -> ProviderLifecycleResult:
    return provider_lifecycle_result(
        provider=provider,
        hook=hook,
        status=_lifecycle_failure_status(hook),
        ready=False,
        details=details,
        skip_reason=skip_reason,
        evidence=evidence,
    )


def _normalize_lifecycle_hook_result(
    *,
    provider: str,
    hook: str,
    result: object,
) -> ProviderLifecycleResult:
    if not isinstance(result, ProviderLifecycleResult):
        return _lifecycle_failure_result(
            provider=provider,
            hook=hook,
            details=(
                f"{hook} hook returned {type(result).__name__}; expected ProviderLifecycleResult."
            ),
        )
    if result.provider != provider or result.hook != hook:
        return _lifecycle_failure_result(
            provider=provider,
            hook=hook,
            details=(
                f"{hook} hook returned result for provider '{result.provider}' "
                f"and hook '{result.hook}'."
            ),
        )
    return _normalize_teardown_lifecycle_result(provider=provider, hook=hook, result=result)


def _normalize_teardown_lifecycle_result(
    *,
    provider: str,
    hook: str,
    result: ProviderLifecycleResult,
) -> ProviderLifecycleResult:
    if hook == _LIFECYCLE_TEARDOWN_HOOK and result.status == "failed":
        return _lifecycle_failure_result(
            provider=provider,
            hook=hook,
            details=result.details,
            skip_reason=result.skip_reason,
            evidence=result.evidence,
        )
    return result


def _aggregate_lifecycle_status(
    provider: str,
    *,
    preflight: ProviderLifecycleResult,
    warmup: ProviderLifecycleResult | None = None,
    teardown: ProviderLifecycleResult | None = None,
) -> ProviderLifecycleStatus:
    results = _lifecycle_results(preflight=preflight, warmup=warmup, teardown=teardown)
    status = _lifecycle_status_value(results)
    issue_result = _lifecycle_issue_result(results, status=status)
    detail_result = _lifecycle_detail_result(
        results,
        status=status,
        issue_result=issue_result,
        fallback=preflight,
    )
    return ProviderLifecycleStatus(
        provider=provider,
        status=status,
        ready=status in {"no-op", "ready"},
        preflight=preflight,
        warmup=warmup,
        teardown=teardown,
        details=detail_result.details,
        skip_reason=_lifecycle_skip_reason(issue_result),
        evidence=_lifecycle_evidence(results),
    )


def _lifecycle_results(
    *,
    preflight: ProviderLifecycleResult,
    warmup: ProviderLifecycleResult | None,
    teardown: ProviderLifecycleResult | None,
) -> tuple[ProviderLifecycleResult, ...]:
    return tuple(result for result in (preflight, warmup, teardown) if result is not None)


def _lifecycle_status_value(results: tuple[ProviderLifecycleResult, ...]) -> str:
    for status in _LIFECYCLE_STATUS_PRECEDENCE:
        if any(result.status == status for result in results):
            return status
    return "no-op"


def _lifecycle_issue_result(
    results: tuple[ProviderLifecycleResult, ...],
    *,
    status: str,
) -> ProviderLifecycleResult | None:
    if status not in _LIFECYCLE_ISSUE_STATUSES:
        return None
    return next((result for result in results if result.status == status), None)


def _lifecycle_detail_result(
    results: tuple[ProviderLifecycleResult, ...],
    *,
    status: str,
    issue_result: ProviderLifecycleResult | None,
    fallback: ProviderLifecycleResult,
) -> ProviderLifecycleResult:
    if issue_result is not None:
        return issue_result
    return next(
        (result for result in results if result.details or result.status == status),
        fallback,
    )


def _lifecycle_skip_reason(result: ProviderLifecycleResult | None) -> str:
    if result is None or result.status != "skipped":
        return ""
    return result.skip_reason


def _lifecycle_evidence(results: tuple[ProviderLifecycleResult, ...]) -> JSONDict:
    return {result.hook: dict(result.evidence) for result in results if result.evidence}


__all__ = ["build_provider_lifecycle_status", "provider_lifecycle_result"]
