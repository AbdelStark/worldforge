# Capability protocols refactor

## Status
Draft · 2026-04-24

## Outcome (one sentence)
Replace the monolithic `BaseProvider` + capability-flag design with narrow public `Protocol` interfaces per capability (`Policy`, `Cost`, `Generator`, `Predictor`, `Reasoner`, `Embedder`, `Transferer`, `Planner`), an optional `RunnableModel` composite that groups them, and a registration surface that indexes each implementation into per-capability registries — so a user can implement one capability in a few lines, register it directly, and have the rest of the stack (planner, diagnostics, evaluation, benchmark, docs generation) treat it as first-class.

## Why this refactor
The current design in [src/worldforge/providers/base.py](../../src/worldforge/providers/base.py) forces every adapter to subclass one `BaseProvider` class that declares all eight capability methods as fail-closed stubs. `ProviderCapabilities` flags declare what the adapter implements. Two structural weaknesses follow:

1. **Flags can lie.** Nothing at instantiation or import time prevents a subclass from setting `capabilities=ProviderCapabilities(score=True)` without overriding `score_actions`, or vice versa. The only defense is the runtime contract test `worldforge.testing.assert_provider_contract()` ([src/worldforge/testing/providers.py:166](../../src/worldforge/testing/providers.py:166)), and only if someone runs it.
2. **Most adapters are single-capability.** `LeWorldModelProvider` implements `score` only; `LeRobotPolicyProvider` implements `policy` only; `CosmosProvider` implements `generate` only. They each inherit seven stub methods that will never be called and carry a flag set that encodes the same truth structurally would. Only `MockProvider` genuinely uses the multi-capability shape.

The cost of this weakness shows up every time someone wants to plug in a custom cost function or policy. The minimum ceremony today is ~20 lines of subclass + flag + profile wiring to expose one method. Third-party packages that want to ship a cost implementation have to depend on `worldforge.providers.BaseProvider` — they can't depend on a narrow `Cost` protocol because none is exported.

This refactor removes the flag/method-divergence failure mode by making structural implementation (satisfies the `Cost` protocol) the source of truth, and reduces the ceremony to "define a class with one method, register it."

## In scope
- Define public `Protocol` classes in a new module `worldforge.capabilities` for each of the eight capability surfaces: `Policy`, `Cost`, `Generator`, `Predictor`, `Reasoner`, `Embedder`, `Transferer`, `Planner`.
- Each protocol declares: `name: str`, `profile: ProviderProfileSpec` (optional, defaults to `None`), and exactly one capability method with its existing signature.
- Define an optional composite `RunnableModel` dataclass with one optional slot per capability. `RunnableModel` is pure sugar — the framework treats registration of a `RunnableModel` as "register each non-`None` field into the matching capability registry."
- Replace the single `WorldForge._providers` registry with per-capability registries: `_policies`, `_costs`, `_generators`, etc. Add `WorldForge.register(x)` with runtime dispatch: if `x` satisfies `Cost`, index it under its name in `_costs`; if it also satisfies `Policy`, also index it in `_policies`; etc.
- Add typed convenience shortcuts: `register_cost`, `register_policy`, `register_generator`, etc., each of which validates the argument satisfies the matching protocol and indexes only into that registry.
- Accept both string lookup and direct instances at call sites: `forge.score_actions(cost="leworldmodel", ...)` and `forge.score_actions(cost=my_cost_obj, ...)` both work. Same for `forge.select_actions(policy=...)`, `forge.plan(..., cost=..., policy=...)`.
- Framework wraps every registered implementation in an internal `_ObservableCapability` decorator that adds event emission (`ProviderEvent` phases retry/success/failure), latency timing, and health tracking. The user's `Cost` implementation stays pure — it returns an `ActionScoreResult` and nothing else. Observability is layered on at registration time.
- Rewrite every concrete adapter ([mock.py](../../src/worldforge/providers/mock.py), [leworldmodel.py](../../src/worldforge/providers/leworldmodel.py), [lerobot.py](../../src/worldforge/providers/lerobot.py), [gr00t.py](../../src/worldforge/providers/gr00t.py), [cosmos.py](../../src/worldforge/providers/cosmos.py), [runway.py](../../src/worldforge/providers/runway.py), [remote.py](../../src/worldforge/providers/remote.py), [jepa_wms.py](../../src/worldforge/providers/jepa_wms.py)) against the new protocols. Single-capability adapters become classes with one method. `MockProvider` either stays one class implementing multiple protocols, or is split into `MockPolicy`/`MockCost`/`MockGenerator`/... bundled via a `RunnableModel` factory — decided per the "Mock layout" open question below.
- Delete `BaseProvider`, `ProviderCapabilities`, and the `ProviderError.does not implement` stubs. Clean cutover.
- Rewrite the catalog in [providers/catalog.py](../../src/worldforge/providers/catalog.py) to return `RunnableModel` (or in single-capability cases, a bare capability implementation) from each factory. The registration logic in `framework.py` still walks the catalog at `WorldForge.__init__` and dispatches to the right registry.
- Update the capability-routed planner paths in [framework.py](../../src/worldforge/framework.py): `forge.plan(...)`, `forge.score_actions(...)`, `forge.select_actions(...)`, `forge.generate(...)`, diagnostics.
- Update `worldforge.testing.assert_provider_contract()` to walk protocols instead of flags, and add a new helper `assert_capability_contract(capability, impl)` for single-capability adapters.
- Update [scripts/generate_provider_docs.py](../../scripts/generate_provider_docs.py) to render per-capability tables derived from the new registry.
- Update all adapter tests, framework tests, contract tests, CLI tests, docs-drift tests, and evaluation/benchmark tests to the new API.
- Update public exports in [src/worldforge/__init__.py](../../src/worldforge/__init__.py) and [src/worldforge/providers/__init__.py](../../src/worldforge/providers/__init__.py).
- Update [docs/src/architecture.md](../../docs/src/architecture.md), [docs/src/provider-authoring-guide.md](../../docs/src/provider-authoring-guide.md), each provider page under [docs/src/providers/](../../docs/src/providers/), [README.md](../../README.md) where the provider model is described, [AGENTS.md](../../AGENTS.md), [CLAUDE.md](../../CLAUDE.md), and [CHANGELOG.md](../../CHANGELOG.md).

## Out of scope (explicit)
- Rename of "provider" → "adapter" or "capability impl" in file paths, module names, or user-visible CLI surfaces. The protocol module is the only new name; existing public names (`ProviderEvent`, `ProviderError`, `ProviderProfileSpec`, `ProviderRequestPolicy`, file path `src/worldforge/providers/`) stay. Rename is a possible follow-up.
- New capability surfaces beyond the existing eight. No new `Planner` semantics, no new `ScoreBatch` surface, no new bulk APIs.
- Changes to the `Action`, `World`, `ActionScoreResult`, `ActionPolicyResult`, `VideoClip`, `PredictionPayload` result types. Result dataclasses keep their shape; only the interface around them changes.
- Changes to persistence, request policy, retry, or HTTP utilities. These stay as helper modules the new protocol implementations use.
- Changes to CLI subcommands and output formats beyond whatever mechanical edits are needed to track new registry shape.
- Changes to the [evaluation/](../../src/worldforge/evaluation/) and [benchmark.py](../../src/worldforge/benchmark.py) pipelines beyond adapting call sites. Same suites, same reports.

## Target architecture

### Capability protocols

Every capability surface becomes a public `Protocol` in `worldforge.capabilities`:

```python
from typing import Protocol, runtime_checkable
from worldforge.models import (
    Action, ActionPolicyResult, ActionScoreResult,
    EmbeddingResult, GenerationOptions, JSONDict,
    ReasoningResult, VideoClip,
)
from worldforge.providers.base import PredictionPayload, ProviderProfileSpec

@runtime_checkable
class Cost(Protocol):
    name: str
    profile: ProviderProfileSpec | None
    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult: ...

@runtime_checkable
class Policy(Protocol):
    name: str
    profile: ProviderProfileSpec | None
    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult: ...

@runtime_checkable
class Generator(Protocol):
    name: str
    profile: ProviderProfileSpec | None
    def generate(self, prompt: str, duration_seconds: float,
                 *, options: GenerationOptions | None = None) -> VideoClip: ...

# ... Predictor, Reasoner, Embedder, Transferer, Planner
```

`runtime_checkable` lets the framework do `isinstance(x, Cost)` at registration time.

### Composite bundle

`RunnableModel` is an optional dataclass for things that genuinely implement several capabilities (mock, potentially future multi-capability vendors):

```python
@dataclass
class RunnableModel:
    name: str
    policy: Policy | None = None
    cost: Cost | None = None
    generator: Generator | None = None
    predictor: Predictor | None = None
    reasoner: Reasoner | None = None
    embedder: Embedder | None = None
    transferer: Transferer | None = None
    planner: Planner | None = None
    profile: ProviderProfileSpec | None = None
```

No special methods. `forge.register(bundle)` iterates non-`None` fields and calls the matching single-capability register for each.

### Registration

```python
class WorldForge:
    _policies: dict[str, Policy]
    _costs: dict[str, Cost]
    _generators: dict[str, Generator]
    # ... one dict per capability

    def register(self, x: RunnableModel | Policy | Cost | Generator | ...) -> None:
        """Dispatch by protocol membership."""
        if isinstance(x, RunnableModel):
            for field, impl in x.capability_fields():
                self._register_capability(field, impl)
            return
        matched = False
        if isinstance(x, Policy):   self._register_capability("policy", x);   matched = True
        if isinstance(x, Cost):     self._register_capability("cost", x);     matched = True
        if isinstance(x, Generator): self._register_capability("generator", x); matched = True
        # ... etc
        if not matched:
            raise WorldForgeError(f"{type(x).__name__} does not satisfy any capability protocol.")

    def register_cost(self, cost: Cost) -> None: ...
    def register_policy(self, policy: Policy) -> None: ...
    # ... etc
```

### Observability

Every registered implementation is wrapped by the framework at registration time:

```python
def _register_capability(self, kind: str, impl: object) -> None:
    wrapped = _ObservableCapability(impl, kind=kind, event_handler=self._event_handler)
    registry = self._registry_for(kind)
    registry[impl.name] = wrapped
```

`_ObservableCapability` is the single place that emits `ProviderEvent`s, times operations, and tracks health. User code writing a `Cost` implementation is pure — no event-emission boilerplate.

### Call sites

String lookup and direct instance both work:

```python
forge.score_actions(cost="leworldmodel", info=..., action_candidates=...)
forge.score_actions(cost=my_cost_obj, info=..., action_candidates=...)
forge.plan(world, policy="lerobot", cost="leworldmodel",
           policy_info=..., score_info=..., score_action_candidates=...)
```

Internally, string arguments resolve through the matching registry; object arguments are used directly (and implicitly wrapped in `_ObservableCapability` if not already).

## Acceptance criteria
- [ ] `worldforge.capabilities` module exists and exports eight `Protocol` classes: `Policy`, `Cost`, `Generator`, `Predictor`, `Reasoner`, `Embedder`, `Transferer`, `Planner`. All `@runtime_checkable`.
- [ ] `worldforge.capabilities.RunnableModel` dataclass exists with one optional slot per capability plus `name` and `profile`.
- [ ] `src/worldforge/providers/base.py` no longer exports `BaseProvider`, `ProviderCapabilities`. `ProviderError`, `ProviderProfileSpec`, `PredictionPayload`, `RemoteProvider` remain (or are relocated) — see plan.md for exact destination.
- [ ] Every concrete adapter implements exactly the protocols matching its capabilities. No adapter carries method stubs for capabilities it does not implement.
- [ ] `WorldForge.register(x)` dispatches correctly for all eight protocols and for `RunnableModel` bundles. `register_<capability>(...)` shortcuts exist for each.
- [ ] `forge.score_actions(cost=...)`, `forge.select_actions(policy=...)`, `forge.generate(generator=...)`, `forge.predict(predictor=...)`, `forge.reason(reasoner=...)`, `forge.embed(embedder=...)`, `forge.transfer(transferer=...)` all accept both a registered name (`str`) and a direct implementation instance.
- [ ] `forge.plan(...)` accepts `policy=` and `cost=` (and any other capability arg the planner composes) in the same dual form.
- [ ] Every registered implementation emits structured `ProviderEvent`s with correct `phase`/`operation`/`duration_ms` on success and failure.
- [ ] `worldforge.testing.assert_capability_contract(capability, impl)` exists and validates a single capability implementation against its protocol, including output-type validation.
- [ ] The legacy `assert_provider_contract(provider)` is removed (or rewritten to walk the composite's capability fields).
- [ ] [scripts/generate_provider_docs.py](../../scripts/generate_provider_docs.py) renders per-capability tables from the new registry. `uv run python scripts/generate_provider_docs.py --check` is clean.
- [ ] `uv run ruff check src tests examples scripts` and `uv run ruff format --check src tests examples scripts` are clean.
- [ ] `uv run pytest` is green.
- [ ] `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` passes the coverage gate.
- [ ] `bash scripts/test_package.sh` passes.
- [ ] The robotics showcase (`scripts/robotics-showcase`) runs end-to-end and produces the same output as before the refactor (bitwise-identical or documented differences).
- [ ] [CHANGELOG.md](../../CHANGELOG.md) documents the breaking API change with migration notes for external callers.
- [ ] [docs/src/provider-authoring-guide.md](../../docs/src/provider-authoring-guide.md) rewritten against the new API. Example: "implementing a custom cost model in four lines."

## Non-functional requirements
- **No flag lies.** A class that does not implement `score_actions` must not appear in the cost registry. `isinstance(x, Cost)` is the single source of truth.
- **Third-party-friendly.** A package depending on WorldForge can implement `Cost` without importing any class from `worldforge.providers`. Only `worldforge.capabilities` (and the result types in `worldforge.models`) are needed.
- **Observability parity.** The `ProviderEvent` stream emitted by a wrapped implementation is equivalent to what the corresponding `BaseProvider` subclass emitted before the refactor. No event shape changes; only the place the wrapping happens.
- **No torch/runtime regressions.** `worldforge.capabilities` is pure Python; no optional runtime imports. LeWorldModel/LeRobot/GR00T adapters still lazy-load torch and upstream packages inside methods.
- **Coverage gate unchanged.** 90% coverage holds after refactor. If any formerly-tested code path (e.g. the `BaseProvider.<method>` fail-closed branches) no longer exists, tests for it are removed cleanly — not skipped.
- **Zero change to result dataclasses.** `ActionScoreResult`, `ActionPolicyResult`, `VideoClip`, `PredictionPayload`, `ReasoningResult`, `EmbeddingResult` are untouched. Their validators still fire on construction.
- **Deterministic behavior preserved.** Mock's deterministic outputs are byte-identical across the refactor. Evaluation suites produce identical reports.

## Resolved decisions
1. **Mock layout.** Split into `MockPolicy`, `MockCost`, `MockGenerator`, `MockPredictor`, `MockReasoner`, `MockEmbedder`, `MockTransferer` — each a small focused class — bundled via a `RunnableModel` factory in the catalog. Decided 2026-04-24.
2. **Profile placement.** `profile: ProviderProfileSpec | None` lives on every protocol. Metadata stays with the impl; no separate registration-time record. Decided 2026-04-24.
3. **`RemoteProvider` helpers.** Keep `RemoteProvider` as a mixin class that remote capability impls inherit from. It no longer subclasses `BaseProvider`; it exposes `_require_credentials()` and `_require_request_policy()` only. Decided 2026-04-24.
4. **`PredictionPayload` location.** Move from [providers/base.py](../../src/worldforge/providers/base.py) to [src/worldforge/models.py](../../src/worldforge/models.py) alongside the other result types. Decided 2026-04-24.
5. **Name scoping.** Names are scoped per capability. `forge.register_cost(X(name="foo"))` + `forge.register_policy(Y(name="foo"))` is allowed; registries use capability-local namespaces. Lookup is `(capability, name)`. Decided 2026-04-24.
6. **Duplicate names within a capability.** `WorldForge.register(x)` raises `WorldForgeError` on duplicate name within a capability registry. Matches legacy `register_provider` behavior for parity. Decided 2026-04-24.

## References
- Current base class: [src/worldforge/providers/base.py](../../src/worldforge/providers/base.py)
- Current capability flags: `ProviderCapabilities` in [src/worldforge/models.py](../../src/worldforge/models.py)
- Current catalog: [src/worldforge/providers/catalog.py](../../src/worldforge/providers/catalog.py)
- Current contract test: [src/worldforge/testing/providers.py:166](../../src/worldforge/testing/providers.py:166)
- Original design discussion: conversation on branch `main` on 2026-04-24, captured in commit message of the first code-moving commit.
