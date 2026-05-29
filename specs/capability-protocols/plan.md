# Plan — Capability protocols refactor

## Status
Draft · 2026-04-24

## Strategy summary
Clean cutover across a sequence of milestones (M0–M6), each a self-contained PR. No `BaseProvider` compat shim. The ordering is chosen so that each milestone leaves the tree in a buildable, fully-tested state; mid-refactor branches are never green-but-inconsistent.

Early milestones (M0, M1) are additive: the new protocol module and registry land alongside the existing `BaseProvider` machinery, and nothing calls them yet. M2–M5 migrate concrete adapters one cluster at a time, switching call sites to the new API per adapter. M6 deletes the legacy `BaseProvider`, `ProviderCapabilities`, and contract helper, once every adapter and test has been migrated off them. M7 updates docs.

## Dependencies on other work
- None. This refactor does not depend on other in-flight milestones. It does touch files that overlap with the harness milestones (M3 live providers reads the catalog); the harness side consumes the registry read-only and will adopt the new shape automatically once M6 lands, assuming we preserve the `forge.score_actions(...)` call shape in the planner.
- `uv` / `ruff` / `pytest` toolchain versions from [pyproject.toml](../../pyproject.toml) and [uv.lock](../../uv.lock) do not change.

## Milestones

### M0 — Protocol module and registry scaffolding (additive, no behavior change)
Land `worldforge.capabilities` with the eight `Protocol` definitions and the `RunnableModel` dataclass. Add `WorldForge._policies`, `_costs`, `_generators`, ... registries next to the existing `_providers`. Add `WorldForge.register(x)` dispatch and `register_<capability>()` shortcuts — these populate the new registries only; the existing `register_provider(...)` keeps the old `_providers` map.

Also land the `_ObservableCapability` wrapper class. No adapter is wrapped by it yet.

**Deliverables:**
- `src/worldforge/capabilities/__init__.py` with the protocols and `RunnableModel`.
- `src/worldforge/providers/observable.py` with `_ObservableCapability`.
- Expanded `WorldForge` with dual registries.
- Unit tests for the protocols (runtime_checkable membership), `RunnableModel.capability_fields()`, and `_ObservableCapability` event emission.

**Acceptance:** `uv run pytest` green. No adapter migrated. No call site migrated. `worldforge doctor` produces the same output as before.

### M1 — Dual-routing call sites
Rewrite the capability-routed methods on `WorldForge` (`score_actions`, `select_actions`, `generate`, `predict`, `reason`, `embed`, `transfer`, `plan`) to check the new per-capability registry first and fall back to the legacy `_providers` map. Accept both string names and direct instances on every call.

No new adapters land on the new side yet — both registries contain the same set of wrapped providers during this transitional milestone, because the `_ObservableCapability` wrapper knows how to wrap a `BaseProvider` instance by reading its capability flags.

**Deliverables:**
- Dual-routing in `framework.py` capability methods.
- Legacy `BaseProvider`s get mirrored into the new registries at `WorldForge.__init__` via an `_adopt_legacy_provider(bp)` helper.
- Tests covering both name and instance call forms for every capability method.

**Acceptance:** Full test suite green. Call sites like `forge.score_actions(cost="leworldmodel", ...)` and `forge.score_actions("leworldmodel", ...)` produce identical `ActionScoreResult` output.

### M2 — Migrate MockProvider (the hardest case first)
Split `MockProvider` into focused capability classes: `MockPolicy`, `MockCost`, `MockGenerator`, `MockPredictor`, `MockReasoner`, `MockEmbedder`, `MockTransferer`. Each is a small class with one method. Add a `RunnableModel` factory that bundles them under the name `"mock"`.

Delete `MockProvider` class. Update the catalog factory for mock to return the bundle.

**Deliverables:**
- `src/worldforge/providers/mock/__init__.py` (new package replacing `mock.py`) with one file per capability class.
- `RunnableModel` factory returning a bundle named `"mock"`.
- Updated catalog entry.
- Mock-focused tests rewritten against the new classes.

**Acceptance:** Mock exercises every capability end-to-end as before. Contract tests pass. Coverage for the mock implementation stays ≥90%.

### M3 — Migrate LeWorldModel, LeRobot, GR00T (local runtime adapters)
Rewrite each of these as a direct capability class (not a bundle — each is single-capability):
- `LeWorldModelCost` implements `Cost`.
- `LeRobotPolicy` implements `Policy`.
- `GrootPolicy` implements `Policy`.

Catalog factories return the capability instance directly. Registration dispatches to the single matching registry. Lazy torch/upstream imports preserved inside methods.

**Deliverables:**
- `src/worldforge/providers/leworldmodel.py`, `lerobot.py`, `gr00t.py` rewritten.
- Profile metadata moved from `ProviderProfileSpec` constructor kwarg to class-attribute or `__init__`.
- `_policy.py`, `_tensor_validation.py`, `_config.py` helper modules unchanged — same usage patterns.
- Adapter tests rewritten against the new classes.

**Acceptance:** All local-runtime adapter tests pass. Robotics showcase runs with the refactored adapters and produces the same report JSON at `/tmp/worldforge-robotics-showcase/real-run.json` (deterministic paths only — mock-replay portion).

### M4 — Migrate remote HTTP adapters (Cosmos, Runway)
Rewrite as `CosmosGenerator` (implements `Generator`), `RunwayGenerator` + `RunwayTransferer` (implements `Generator` and `Transferer`). Decide per open question #3 whether `RemoteProvider` stays as a mixin base or is extracted to free functions. Recommendation: keep as mixin.

Catalog factories return the capability instance or a `RunnableModel` bundle for Runway's two capabilities.

**Deliverables:**
- `src/worldforge/providers/cosmos.py`, `runway.py`, `remote.py` rewritten.
- `RemoteProvider` repurposed as a credential/request-policy mixin (no longer subclasses anything).
- Adapter tests rewritten including fixture-driven parser tests under `tests/fixtures/providers/`.

**Acceptance:** All HTTP-adapter tests and fixture tests pass. Provider event shapes unchanged (retry/success/failure phases, duration, metadata redaction).

### M5 — Migrate scaffolds (jepa, genie, jepa-wms)
Rewrite the scaffold adapters against the new protocol shape. These are env-gated mock-backed reservations; they implement no real capability. Decide whether they become placeholder `RunnableModel` bundles with mock capability instances inside, or a new `Scaffold` protocol.

Recommendation: placeholder `RunnableModel` with mock capabilities and an explicit `implementation_status="scaffold"` on the profile.

**Deliverables:**
- `src/worldforge/providers/remote.py` (JepaProvider, GenieProvider) and `jepa_wms.py` rewritten.
- Catalog entries updated.

**Acceptance:** Catalog renders scaffolds as "scaffold" in the generated docs table. Auto-registration behavior unchanged.

### M6 — Delete legacy BaseProvider, ProviderCapabilities, dual-routing, and legacy contract test
All adapters now live on the new side. Remove:
- `BaseProvider` class from `src/worldforge/providers/base.py`.
- `ProviderCapabilities` from `src/worldforge/models.py`.
- `_adopt_legacy_provider` in `framework.py`.
- Dual-routing fallbacks in `WorldForge` capability methods.
- `assert_provider_contract()` from `src/worldforge/testing/providers.py`, replaced by `assert_capability_contract()` added in M0.
- The legacy `_providers` registry and `register_provider()` method on `WorldForge`.

Also: remove any remaining imports of these names across the codebase, tests, and docs.

**Deliverables:**
- The above deletions.
- Public exports cleaned up in `src/worldforge/__init__.py`, `src/worldforge/providers/__init__.py`.
- Final test pass.

**Acceptance:** `grep -r "BaseProvider\|ProviderCapabilities" src tests examples scripts` returns zero matches (outside of migration CHANGELOG references). Every legacy fallback branch removed. Full gate green.

### M7 — Docs and CHANGELOG
Rewrite:
- [docs/src/architecture.md](../../docs/src/architecture.md) — new capability-protocol architecture diagram and explanation.
- [docs/src/provider-authoring-guide.md](../../docs/src/provider-authoring-guide.md) — "implement one capability in four lines" example, registration walkthrough, `RunnableModel` composition pattern.
- Each provider page under [docs/src/providers/](../../docs/src/providers/) to reflect the class rename and single-capability shape.
- [README.md](../../README.md) — capability table, code sample updated.
- [AGENTS.md](../../AGENTS.md) — `<provider_contracts>` section replaced with capability-protocol contracts.
- [CLAUDE.md](../../CLAUDE.md) — `<priority_rules>` rule #1 and the provider-docs command list updated.
- [CHANGELOG.md](../../CHANGELOG.md) — breaking change note with migration guide.

**Acceptance:** `uv run python scripts/generate_provider_docs.py --check` clean. Manual review of docs for consistency. MkDocs site builds without warnings.

## Test strategy

### Per-milestone
Each milestone adds or migrates tests as part of its deliverables — no end-of-refactor test catch-up. After each milestone:
- `uv run ruff check src tests examples scripts`
- `uv run ruff format --check src tests examples scripts`
- `uv run pytest`
- `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90`

### Coverage gate
Stays at 90%. If a milestone removes code whose coverage was hard-won (e.g., the fail-closed `BaseProvider.<method>` stubs), the tests for that code are removed at the same commit, not skipped or marked xfail. Coverage of `worldforge.capabilities` protocols, registration dispatch, and `_ObservableCapability` wrapper must reach 90% on the milestone that introduces them.

### Behavior-equivalence tests
For each adapter migration milestone (M2–M5), add a brief behavior-equivalence test that runs the same input through both old and new code paths and asserts identical output. These tests are deleted in M6 alongside the legacy side.

Example for LeWorldModel:
```python
def test_leworldmodel_behavior_equivalence():
    legacy = LegacyLeWorldModelProvider(model_loader=fake_loader, tensor_module=fake_torch, policy="demo/pusht-lewm")
    modern = LeWorldModelCost(model_loader=fake_loader, tensor_module=fake_torch, policy="demo/pusht-lewm")
    assert legacy.score_actions(info=SAMPLE, action_candidates=CANDIDATES) == \
           modern.score_actions(info=SAMPLE, action_candidates=CANDIDATES)
```

### Contract tests
Rewrite `assert_provider_contract` as `assert_capability_contract(protocol, impl)` in M0. During M1–M5, both assertions run — the legacy one against the not-yet-migrated adapters, the new one against the migrated ones. In M6, the legacy one is deleted.

### Integration tests
The full gate runs after every milestone. The robotics showcase runs after M3 and M4. The package-contract script (`scripts/test_package.sh`) runs after M6 and M7 before the branch is considered mergeable.

## Risks and rollback

### Risks
1. **Registration dispatch ambiguity.** An implementation that structurally satisfies multiple protocols (e.g. a Mock class that implements all six) gets registered into all matching registries. Intended behavior, but caller surprise if they expect a `register_cost(x)` call to populate only the cost registry. Mitigation: `register_cost(x)` is typed — it validates `isinstance(x, Cost)` and indexes only into `_costs`. The multi-registry dispatch is the `register(x)` entry point only.

2. **Profile metadata drift.** Profile fields (description, deterministic, required_env_vars, supported_modalities, notes) live on the protocol in the target design. If an adapter forgets to set them, docs render incomplete. Mitigation: `assert_capability_contract` checks that `profile` is non-`None` and exercises each required field, matching the existing `assert_provider_contract` rigor.

3. **Public API breakage for in-repo callers.** `forge.register_provider(...)` callers in tests, examples, scripts, smokes — all need migration. Scope is bounded; grep finds them. Clean cutover at M6.

4. **Third-party consumers.** Private repo per current guidance, so no third-party consumers to worry about. If that changes, a migration doc in `CHANGELOG.md` at M7 is the mitigation.

5. **Hidden coupling to `BaseProvider`.** Some code paths may depend on attributes of `BaseProvider` that the protocol doesn't expose (`configured()`, `health()`, `info()`, `profile()`). These are real methods used by `worldforge doctor` and diagnostics. Mitigation: `_ObservableCapability` provides these methods by delegation to the wrapped impl (reading `impl.profile`, synthesizing `configured` from env var membership, etc.). Callers see the same surface.

### Rollback
Each milestone is a single PR; revert the PR to roll back. Because milestones are ordered and each keeps the tree green, rolling back any milestone > M0 requires rolling back every later milestone too. No partial rollback across the M2–M5 adapter migrations.

Recovery from a merged-and-broken state: revert the bad milestone and its successors; re-open the task list for the reverted portion.

## Resolved decisions
All six spec-level open questions resolved 2026-04-24. No blockers before M0. See [spec.md](./spec.md) § "Resolved decisions".

Summary:
- Mock layout: split per capability, bundled via `RunnableModel`.
- Profile placement: on every protocol.
- `RemoteProvider`: kept as a mixin class for HTTP adapters.
- `PredictionPayload`: moved to [src/worldforge/models.py](../../src/worldforge/models.py).
- Name scoping: per capability (local namespaces).
- Duplicate name handling: raises `WorldForgeError` within a capability.

## Dependencies on other milestones
None. This refactor is self-contained within the providers/framework/testing layers.
