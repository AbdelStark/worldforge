"""Provider routing and fallback policies.

Typed orchestration for trying a preferred provider first and falling back to a
prioritized list of alternates when calls fail. The policy validates capability
compatibility before each attempt, preserves errors and event provenance across
attempts, and returns the full attempt history to the caller. Failures are
never silently masked: the chain stops at the first success and every prior or
trailing skipped/failed step is recorded in the :class:`RoutingResult`.

Routing is appropriate for:

- Optional providers that may be unconfigured on a given host (mock fallback
  when a remote credential is missing).
- Transient remote failures where retrying with a different adapter is
  preferable to surfacing the error.
- Developer loops that want a deterministic preferred-provider order across
  hosts with different credentials.

Routing is not appropriate for:

- Correctness-sensitive contracts where downstream pipelines depend on a
  specific provider's semantics; fallback masks the divergence.
- Billing-sensitive operations where re-trying multiplies cost. Configure a
  single provider and let the call surface its error.
- Robotics control loops where determinism of the chosen provider matters
  more than fault tolerance; pick one provider and fail loudly.

The :func:`route_capability` function is deterministic: providers are tried
in the order ``(preferred, *fallbacks)`` and the chain stops at the first
success.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from worldforge.models import (
    CAPABILITY_NAMES,
    JSONDict,
    WorldForgeError,
    _redact_observable_text,
)

if TYPE_CHECKING:
    from worldforge.framework import WorldForge

ROUTING_ATTEMPT_STATUSES: tuple[str, ...] = (
    "succeeded",
    "failed",
    "skipped-not-registered",
    "skipped-incompatible",
)


@dataclass(slots=True, frozen=True)
class _RouteStep[T]:
    attempt: RoutingAttempt
    succeeded: bool = False
    value: T | None = None


@dataclass(slots=True, frozen=True)
class ProviderRoutingPolicy:
    """Typed routing policy for a single capability call.

    Fields are validated at construction. An unknown capability, blank
    preferred name, blank fallback name, or duplicate provider in the chain
    raises :class:`WorldForgeError`.
    """

    capability: str
    preferred: str
    fallbacks: tuple[str, ...] = ()
    require_capability: bool = True
    operation: str = "routing"

    def __post_init__(self) -> None:
        _require_routing_policy_capability(self.capability)
        preferred = _normalize_policy_preferred(self.preferred)
        fallbacks = _normalize_policy_fallbacks(self.fallbacks, preferred=preferred)
        _require_policy_capability_flag(self.require_capability)
        operation = _normalize_policy_operation(self.operation)
        object.__setattr__(self, "preferred", preferred)
        object.__setattr__(self, "fallbacks", fallbacks)
        object.__setattr__(self, "operation", operation)

    def chain(self) -> tuple[str, ...]:
        """Return the ordered provider chain, preferred first."""

        return (self.preferred, *self.fallbacks)

    def to_dict(self) -> JSONDict:
        return {
            "capability": self.capability,
            "preferred": self.preferred,
            "fallbacks": list(self.fallbacks),
            "require_capability": self.require_capability,
            "operation": self.operation,
        }


def _require_routing_policy_capability(capability: object) -> str:
    if not isinstance(capability, str) or capability not in CAPABILITY_NAMES:
        known = ", ".join(CAPABILITY_NAMES)
        raise WorldForgeError(f"ProviderRoutingPolicy capability must be one of: {known}.")
    return capability


def _normalize_policy_preferred(preferred: object) -> str:
    if not isinstance(preferred, str) or not preferred.strip():
        raise WorldForgeError("ProviderRoutingPolicy preferred must be a non-empty string.")
    return preferred.strip()


def _normalize_policy_fallbacks(fallbacks: object, *, preferred: str) -> tuple[str, ...]:
    if not isinstance(fallbacks, tuple | list):
        raise WorldForgeError(
            "ProviderRoutingPolicy fallbacks must be a sequence of provider names."
        )
    cleaned = tuple(_normalize_policy_fallback(entry) for entry in fallbacks)
    _reject_duplicate_policy_providers((preferred, *cleaned))
    return cleaned


def _normalize_policy_fallback(fallback: object) -> str:
    if not isinstance(fallback, str) or not fallback.strip():
        raise WorldForgeError("ProviderRoutingPolicy fallbacks must be non-empty strings.")
    return fallback.strip()


def _reject_duplicate_policy_providers(chain: tuple[str, ...]) -> None:
    seen: set[str] = set()
    for provider in chain:
        if provider in seen:
            raise WorldForgeError(
                f"ProviderRoutingPolicy provider '{provider}' duplicated in chain."
            )
        seen.add(provider)


def _require_policy_capability_flag(require_capability: object) -> bool:
    if not isinstance(require_capability, bool):
        raise WorldForgeError("ProviderRoutingPolicy require_capability must be a bool.")
    return require_capability


def _normalize_policy_operation(operation: object) -> str:
    if not isinstance(operation, str) or not operation.strip():
        raise WorldForgeError("ProviderRoutingPolicy operation must be a non-empty string.")
    return operation.strip()


@dataclass(slots=True, frozen=True)
class RoutingAttempt:
    """One step in a routing chain.

    ``status`` is one of :data:`ROUTING_ATTEMPT_STATUSES`. ``reason`` carries a
    human-readable note for skipped steps. ``error_type`` and ``error_message``
    capture the exception class name and a redacted ``str(exc)`` from a failed
    call. Adapters should still raise sanitized provider errors, but routing
    attempts are artifact-facing records and therefore redact defensively too.
    """

    provider: str
    capability: str
    status: str
    reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("RoutingAttempt provider must be a non-empty string.")
        object.__setattr__(self, "provider", self.provider.strip())
        if not isinstance(self.capability, str) or self.capability not in CAPABILITY_NAMES:
            known = ", ".join(CAPABILITY_NAMES)
            raise WorldForgeError(f"RoutingAttempt capability must be one of: {known}.")
        if self.status not in ROUTING_ATTEMPT_STATUSES:
            options = ", ".join(ROUTING_ATTEMPT_STATUSES)
            raise WorldForgeError(f"RoutingAttempt status must be one of: {options}.")
        object.__setattr__(
            self,
            "reason",
            _sanitize_optional_attempt_text(self.reason, field="reason"),
        )
        object.__setattr__(
            self,
            "error_type",
            _sanitize_optional_attempt_text(self.error_type, field="error_type"),
        )
        object.__setattr__(
            self,
            "error_message",
            _sanitize_optional_attempt_text(self.error_message, field="error_message"),
        )

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "capability": self.capability,
            "status": self.status,
            "reason": self.reason,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


def _require_routing_result_capability(capability: object) -> str:
    if not isinstance(capability, str) or capability not in CAPABILITY_NAMES:
        known = ", ".join(CAPABILITY_NAMES)
        raise WorldForgeError(f"RoutingResult capability must be one of: {known}.")
    return capability


def _normalize_routing_chosen(chosen: object) -> str | None:
    if chosen is None:
        return None
    if not isinstance(chosen, str) or not chosen.strip():
        raise WorldForgeError("RoutingResult chosen must be None or a non-empty provider name.")
    return chosen.strip()


def _require_routing_succeeded(value: object) -> bool:
    if not isinstance(value, bool):
        raise WorldForgeError("RoutingResult succeeded must be a bool.")
    return value


def _routing_attempts_for_result(
    attempts: object,
    *,
    capability: str,
) -> tuple[RoutingAttempt, ...]:
    if not isinstance(attempts, tuple) or any(
        not isinstance(item, RoutingAttempt) for item in attempts
    ):
        raise WorldForgeError("RoutingResult attempts must be a tuple of RoutingAttempt.")
    if any(attempt.capability != capability for attempt in attempts):
        raise WorldForgeError("RoutingResult attempt capabilities must match result capability.")
    return attempts


def _succeeded_routing_attempts(attempts: tuple[RoutingAttempt, ...]) -> tuple[RoutingAttempt, ...]:
    return tuple(attempt for attempt in attempts if attempt.status == "succeeded")


def _validate_successful_routing_result(
    *,
    chosen: str | None,
    value: object,
    attempts: tuple[RoutingAttempt, ...],
    succeeded_attempts: tuple[RoutingAttempt, ...],
) -> None:
    if chosen is None:
        raise WorldForgeError("RoutingResult succeeded results require a chosen provider.")
    if value is None:
        raise WorldForgeError("RoutingResult succeeded results require a value.")
    if len(succeeded_attempts) != 1:
        raise WorldForgeError(
            "RoutingResult succeeded results must include exactly one succeeded attempt."
        )
    succeeded_attempt = succeeded_attempts[0]
    if succeeded_attempt.provider != chosen:
        raise WorldForgeError("RoutingResult chosen provider must match the succeeded attempt.")
    if attempts[-1] != succeeded_attempt:
        raise WorldForgeError("RoutingResult succeeded attempt must be the final routing attempt.")


def _validate_failed_routing_result(
    *,
    chosen: str | None,
    value: object,
    succeeded_attempts: tuple[RoutingAttempt, ...],
) -> None:
    if chosen is not None:
        raise WorldForgeError("RoutingResult failed results must not choose a provider.")
    if value is not None:
        raise WorldForgeError("RoutingResult failed results must not carry a value.")
    if succeeded_attempts:
        raise WorldForgeError("RoutingResult failed results must not include succeeded attempts.")


@dataclass(slots=True, frozen=True)
class RoutingResult[T]:
    """Outcome of a :func:`route_capability` call.

    ``value`` is the result returned by the chosen provider, or ``None`` when
    every attempt failed or was skipped. ``attempts`` records every chain step
    in the order it was tried, including skipped pre-call checks. ``chosen`` is
    the provider whose call returned a value, or ``None`` if the chain
    exhausted without success.
    """

    capability: str
    chosen: str | None
    succeeded: bool
    attempts: tuple[RoutingAttempt, ...]
    value: T | None = None

    def __post_init__(self) -> None:
        capability = _require_routing_result_capability(self.capability)
        chosen = _normalize_routing_chosen(self.chosen)
        object.__setattr__(self, "chosen", chosen)
        succeeded = _require_routing_succeeded(self.succeeded)
        attempts = _routing_attempts_for_result(self.attempts, capability=capability)
        succeeded_attempts = _succeeded_routing_attempts(attempts)
        if succeeded:
            _validate_successful_routing_result(
                chosen=chosen,
                value=self.value,
                attempts=attempts,
                succeeded_attempts=succeeded_attempts,
            )
            return
        _validate_failed_routing_result(
            chosen=chosen,
            value=self.value,
            succeeded_attempts=succeeded_attempts,
        )

    def to_dict(self) -> JSONDict:
        return {
            "capability": self.capability,
            "chosen": self.chosen,
            "succeeded": self.succeeded,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }

    def failed_attempts(self) -> tuple[RoutingAttempt, ...]:
        """Return only attempts whose status is ``failed`` (provider raised)."""

        return tuple(attempt for attempt in self.attempts if attempt.status == "failed")

    def skipped_attempts(self) -> tuple[RoutingAttempt, ...]:
        """Return only attempts skipped before the provider was invoked."""

        return tuple(attempt for attempt in self.attempts if attempt.status.startswith("skipped-"))


def route_capability[T](
    policy: ProviderRoutingPolicy,
    forge: WorldForge,
    *,
    invoke: Callable[[str], T],
) -> RoutingResult[T]:
    """Try preferred + fallbacks in order, returning the first success.

    For each provider in :meth:`ProviderRoutingPolicy.chain`:

    1. If the provider is not registered on ``forge``, record
       ``skipped-not-registered`` and continue.
    2. If ``policy.require_capability`` is set and the provider does not
       advertise ``policy.capability``, record ``skipped-incompatible`` and
       continue.
    3. Otherwise call ``invoke(name)``. On return record ``succeeded`` and
       short-circuit; on any exception record ``failed`` (with
       ``type(exc).__name__`` and redacted ``str(exc)``) and continue.

    Returns a :class:`RoutingResult` with the chosen provider, the value, and
    the full attempt history. ``succeeded=False`` when no provider satisfied
    the call.

    The routing layer does not emit its own :class:`worldforge.ProviderEvent`
    objects; the events emitted by ``forge``'s observable capability wrapper
    when each ``invoke`` runs are preserved unchanged. The ``attempts`` tuple
    is the chain-level companion to those per-call events.
    """

    if not isinstance(policy, ProviderRoutingPolicy):
        raise WorldForgeError("route_capability() policy must be a ProviderRoutingPolicy.")
    if not callable(invoke):
        raise WorldForgeError("route_capability() invoke must be callable.")

    attempts: list[RoutingAttempt] = []
    registered = set(forge.providers())

    for name in policy.chain():
        step = _route_provider_step(
            policy=policy,
            forge=forge,
            provider=name,
            registered=registered,
            invoke=invoke,
        )
        attempts.append(step.attempt)
        if step.succeeded:
            return _successful_route_result(
                policy=policy, provider=name, attempts=attempts, step=step
            )

    return _failed_route_result(policy=policy, attempts=attempts)


def _route_provider_step[T](
    *,
    policy: ProviderRoutingPolicy,
    forge: WorldForge,
    provider: str,
    registered: set[str],
    invoke: Callable[[str], T],
) -> _RouteStep[T]:
    if provider not in registered:
        return _RouteStep(_not_registered_attempt(policy, provider))
    if not _provider_supports_policy_capability(policy, forge, provider):
        return _RouteStep(_incompatible_capability_attempt(policy, provider))
    try:
        value = invoke(provider)
    except Exception as exc:
        return _RouteStep(_failed_provider_attempt(policy, provider, exc))
    return _RouteStep(_succeeded_provider_attempt(policy, provider), succeeded=True, value=value)


def _provider_supports_policy_capability(
    policy: ProviderRoutingPolicy,
    forge: WorldForge,
    provider: str,
) -> bool:
    if not policy.require_capability:
        return True
    info = forge.provider_info(provider)
    return bool(info.capabilities.supports(policy.capability))


def _not_registered_attempt(policy: ProviderRoutingPolicy, provider: str) -> RoutingAttempt:
    return RoutingAttempt(
        provider=provider,
        capability=policy.capability,
        status="skipped-not-registered",
        reason=f"provider '{provider}' is not registered",
    )


def _incompatible_capability_attempt(
    policy: ProviderRoutingPolicy, provider: str
) -> RoutingAttempt:
    return RoutingAttempt(
        provider=provider,
        capability=policy.capability,
        status="skipped-incompatible",
        reason=f"provider '{provider}' does not advertise capability '{policy.capability}'",
    )


def _failed_provider_attempt(
    policy: ProviderRoutingPolicy,
    provider: str,
    exc: Exception,
) -> RoutingAttempt:
    return RoutingAttempt(
        provider=provider,
        capability=policy.capability,
        status="failed",
        error_type=type(exc).__name__,
        error_message=str(exc),
    )


def _succeeded_provider_attempt(policy: ProviderRoutingPolicy, provider: str) -> RoutingAttempt:
    return RoutingAttempt(
        provider=provider,
        capability=policy.capability,
        status="succeeded",
    )


def _successful_route_result[T](
    *,
    policy: ProviderRoutingPolicy,
    provider: str,
    attempts: list[RoutingAttempt],
    step: _RouteStep[T],
) -> RoutingResult[T]:
    return RoutingResult(
        capability=policy.capability,
        chosen=provider,
        succeeded=True,
        attempts=tuple(attempts),
        value=step.value,
    )


def _failed_route_result(
    *,
    policy: ProviderRoutingPolicy,
    attempts: list[RoutingAttempt],
) -> RoutingResult[object]:
    return RoutingResult(
        capability=policy.capability,
        chosen=None,
        succeeded=False,
        attempts=tuple(attempts),
        value=None,
    )


def _sanitize_optional_attempt_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorldForgeError(f"RoutingAttempt {field} must be a string when provided.")
    sanitized = _redact_observable_text(value.strip())
    return sanitized or None
