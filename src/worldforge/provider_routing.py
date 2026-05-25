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
        if not isinstance(self.capability, str) or self.capability not in CAPABILITY_NAMES:
            known = ", ".join(CAPABILITY_NAMES)
            raise WorldForgeError(f"ProviderRoutingPolicy capability must be one of: {known}.")
        if not isinstance(self.preferred, str) or not self.preferred.strip():
            raise WorldForgeError("ProviderRoutingPolicy preferred must be a non-empty string.")
        object.__setattr__(self, "preferred", self.preferred.strip())
        if not isinstance(self.fallbacks, tuple | list):
            raise WorldForgeError(
                "ProviderRoutingPolicy fallbacks must be a sequence of provider names."
            )
        cleaned: list[str] = []
        for entry in self.fallbacks:
            if not isinstance(entry, str) or not entry.strip():
                raise WorldForgeError("ProviderRoutingPolicy fallbacks must be non-empty strings.")
            cleaned.append(entry.strip())
        seen: set[str] = {self.preferred}
        for entry in cleaned:
            if entry in seen:
                raise WorldForgeError(
                    f"ProviderRoutingPolicy provider '{entry}' duplicated in chain."
                )
            seen.add(entry)
        object.__setattr__(self, "fallbacks", tuple(cleaned))
        if not isinstance(self.require_capability, bool):
            raise WorldForgeError("ProviderRoutingPolicy require_capability must be a bool.")
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise WorldForgeError("ProviderRoutingPolicy operation must be a non-empty string.")
        object.__setattr__(self, "operation", self.operation.strip())

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
        if not isinstance(self.capability, str) or self.capability not in CAPABILITY_NAMES:
            known = ", ".join(CAPABILITY_NAMES)
            raise WorldForgeError(f"RoutingResult capability must be one of: {known}.")
        if self.chosen is not None and (
            not isinstance(self.chosen, str) or not self.chosen.strip()
        ):
            raise WorldForgeError("RoutingResult chosen must be None or a non-empty provider name.")
        object.__setattr__(self, "chosen", self.chosen.strip() if self.chosen else None)
        if not isinstance(self.succeeded, bool):
            raise WorldForgeError("RoutingResult succeeded must be a bool.")
        if not isinstance(self.attempts, tuple) or any(
            not isinstance(item, RoutingAttempt) for item in self.attempts
        ):
            raise WorldForgeError("RoutingResult attempts must be a tuple of RoutingAttempt.")
        if any(attempt.capability != self.capability for attempt in self.attempts):
            raise WorldForgeError(
                "RoutingResult attempt capabilities must match result capability."
            )
        succeeded_attempts = tuple(
            attempt for attempt in self.attempts if attempt.status == "succeeded"
        )
        if self.succeeded:
            if self.chosen is None:
                raise WorldForgeError("RoutingResult succeeded results require a chosen provider.")
            if self.value is None:
                raise WorldForgeError("RoutingResult succeeded results require a value.")
            if len(succeeded_attempts) != 1:
                raise WorldForgeError(
                    "RoutingResult succeeded results must include exactly one succeeded attempt."
                )
            succeeded_attempt = succeeded_attempts[0]
            if succeeded_attempt.provider != self.chosen:
                raise WorldForgeError(
                    "RoutingResult chosen provider must match the succeeded attempt."
                )
            if self.attempts[-1] != succeeded_attempt:
                raise WorldForgeError(
                    "RoutingResult succeeded attempt must be the final routing attempt."
                )
            return
        if self.chosen is not None:
            raise WorldForgeError("RoutingResult failed results must not choose a provider.")
        if self.value is not None:
            raise WorldForgeError("RoutingResult failed results must not carry a value.")
        if succeeded_attempts:
            raise WorldForgeError(
                "RoutingResult failed results must not include succeeded attempts."
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
        if name not in registered:
            attempts.append(
                RoutingAttempt(
                    provider=name,
                    capability=policy.capability,
                    status="skipped-not-registered",
                    reason=f"provider '{name}' is not registered",
                )
            )
            continue
        if policy.require_capability:
            info = forge.provider_info(name)
            if not info.capabilities.supports(policy.capability):
                attempts.append(
                    RoutingAttempt(
                        provider=name,
                        capability=policy.capability,
                        status="skipped-incompatible",
                        reason=(
                            f"provider '{name}' does not advertise capability '{policy.capability}'"
                        ),
                    )
                )
                continue
        try:
            value = invoke(name)
        except Exception as exc:
            attempts.append(
                RoutingAttempt(
                    provider=name,
                    capability=policy.capability,
                    status="failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            continue
        attempts.append(
            RoutingAttempt(
                provider=name,
                capability=policy.capability,
                status="succeeded",
            )
        )
        return RoutingResult(
            capability=policy.capability,
            chosen=name,
            succeeded=True,
            attempts=tuple(attempts),
            value=value,
        )

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
