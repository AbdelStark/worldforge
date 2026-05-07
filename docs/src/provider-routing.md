# Provider Routing And Fallback

WorldForge ships a typed routing helper for trying a preferred provider first
and falling back to a prioritized list of alternates when calls fail. The
helper validates capability compatibility before each attempt, preserves the
underlying provider events emitted by the observable capability wrapper, and
returns the full attempt history to the caller. Failures are never silently
masked.

## When fallback is appropriate

- **Optional providers**: a host has the mock provider registered for offline
  development and a remote adapter (Cosmos, Runway) configured when its
  credentials are present. Routing prefers the remote and falls back to mock
  when the credentialed adapter is missing on a checkout.
- **Transient remote failures**: a remote provider returns a retryable status
  code its own retry policy could not absorb. Routing logs the failure and
  tries the next provider so a one-off network blip does not break a batch
  evaluation.
- **Cross-host portability**: the same workflow runs on machines with
  different provider mixes. A deterministic preferred + fallback chain keeps
  the call path predictable across hosts.

## When fallback is not appropriate

- **Correctness-sensitive contracts**: downstream pipelines that depend on
  the chosen provider's specific semantics (a particular world-model, a
  particular policy network). A silent fallback to a different provider
  changes the result without changing the caller. Pick one provider and let
  the call surface its error.
- **Billing-sensitive operations**: re-trying with another paid provider
  multiplies cost. Configure a single provider and surface its failure.
- **Robotics control loops**: deterministic provider selection matters more
  than fault tolerance. A fallback in a control loop hides which model
  produced an action; fail loudly so an operator can decide whether to
  re-engage.
- **Malformed provider output**: the routing helper does not mask
  contract-validation errors. Adapters that pass schema-invalid data to the
  observable capability wrapper raise ``ProviderError``; the chain records
  the failure as a normal failed attempt and tries the next provider, but
  the malformed output never reaches the caller.

## Public surface

`worldforge.provider_routing` (re-exported on the top-level package):

| Symbol | Purpose |
| --- | --- |
| `ProviderRoutingPolicy` | Frozen policy: capability + preferred + fallbacks + capability-check toggle + operation tag |
| `RoutingAttempt` | One step in the chain: provider, capability, status, optional reason / error type / sanitized message |
| `RoutingResult` | Outcome: chosen provider, success flag, full attempt history, returned value |
| `ROUTING_ATTEMPT_STATUSES` | Enumerated statuses: `succeeded`, `failed`, `skipped-not-registered`, `skipped-incompatible` |
| `route_capability(policy, forge, *, invoke)` | Try the chain, return the first success |

`route_capability` is deterministic. Providers are tried in the order
`(preferred, *fallbacks)` and the chain stops at the first success. Each
unregistered or capability-incompatible provider is recorded as a skipped
attempt **without** invoking the call; only registered, compatible providers
are passed to ``invoke``. Any exception raised by ``invoke`` is captured as a
`failed` attempt with the exception class name and ``str(exc)`` and the chain
continues.

## Example

```python
from worldforge import ProviderRoutingPolicy, WorldForge, route_capability

forge = WorldForge()
# Forge auto-registers `mock` everywhere and `runway` when RUNWAYML_API_SECRET
# is present in the host environment.

policy = ProviderRoutingPolicy(
    capability="generate",
    preferred="runway",
    fallbacks=("mock",),
    operation="orbit-clip-fallback",
)

result = route_capability(
    policy,
    forge,
    invoke=lambda name: forge.generate(
        "orbiting cube on a wood table",
        name,
        duration_seconds=2.0,
    ),
)

if not result.succeeded:
    raise RuntimeError(
        "no provider in chain satisfied generate(): "
        + ", ".join(
            f"{a.provider}={a.status}" for a in result.attempts
        )
    )

print(f"chosen={result.chosen} via_chain={[a.provider for a in result.attempts]}")
clip = result.value
```

When ``runway`` is not configured on the host, the attempt history records
`skipped-not-registered` for it and the chain proceeds to ``mock`` —
without invoking any remote call or charging the credentialed account.

## Events and provenance

`route_capability` does **not** emit its own `ProviderEvent` objects. The
events produced by the observable capability wrapper inside
`forge.generate(...)`, `forge.predict(...)`, etc. are preserved unchanged and
flow through whatever ``event_handler`` was attached to the forge. The
``RoutingResult.attempts`` tuple is the chain-level companion to those
per-call events.

Failed attempts in `attempts` carry:

- ``status="failed"``
- ``error_type``: the exception class name (e.g. ``"ProviderError"``,
  ``"ProviderBudgetExceededError"``)
- ``error_message``: ``str(exc)``. Adapters are responsible for keeping
  exception messages sanitized — the same contract that applies to
  `ProviderEvent` messages and metadata.

## Validation gates

Routing inputs are validated at construction:

- ``capability`` must be one of ``CAPABILITY_NAMES``
- ``preferred`` must be a non-empty provider name
- ``fallbacks`` must be a sequence of non-empty provider names
- the chain (``preferred + fallbacks``) cannot contain duplicates
- ``require_capability`` must be a ``bool``
- ``operation`` must be a non-empty string

Each violation raises ``WorldForgeError`` so misconfiguration surfaces at
policy construction, not in a dispatch path.
