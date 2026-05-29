# Tasks — Capability protocols refactor

## Status
Draft · 2026-04-24

Checkable task list matching the milestones in [plan.md](./plan.md). Each group corresponds to one PR on `refactor/capability-protocols`.

## Pre-M0 — resolved decisions
- [x] Mock layout: split per capability, bundle via `RunnableModel`. (2026-04-24)
- [x] `PredictionPayload` destination: move to `worldforge.models`. (2026-04-24)
- [x] Name-scoping semantics: per-capability namespaces. (2026-04-24)
- [x] `RemoteProvider` disposition: keep as mixin. (2026-04-24)
- [ ] Lock final protocol signatures (spec.md target architecture). No signature drift once M0 lands.

## M0 — Protocol module and registry scaffolding
- [ ] Create `src/worldforge/capabilities/__init__.py`.
- [ ] Define `Policy`, `Cost`, `Generator`, `Predictor`, `Reasoner`, `Embedder`, `Transferer`, `Planner` protocols with `@runtime_checkable`.
- [ ] Define `RunnableModel` dataclass with one optional slot per capability + `name` + `profile`.
- [ ] Add `RunnableModel.capability_fields()` helper iterating non-`None` slots.
- [ ] Create `src/worldforge/providers/observable.py` with `_ObservableCapability` wrapper class.
- [ ] Wrapper delegates `name`, `profile`, `configured()`, `health()`, `info()` to the wrapped impl.
- [ ] Wrapper emits `ProviderEvent` with `phase` ∈ {`retry`, `success`, `failure`} around every capability method call.
- [ ] Wrapper records `duration_ms` from `perf_counter`.
- [ ] Add per-capability registries to `WorldForge`: `_policies`, `_costs`, `_generators`, `_predictors`, `_reasoners`, `_embedders`, `_transferers`, `_planners`.
- [ ] Add `WorldForge.register(x)` with `isinstance`-based dispatch.
- [ ] Add typed shortcuts: `register_policy`, `register_cost`, `register_generator`, `register_predictor`, `register_reasoner`, `register_embedder`, `register_transferer`, `register_planner`.
- [ ] Raise `WorldForgeError` on duplicate name within a capability registry.
- [ ] Unit tests for each protocol (runtime_checkable membership for positive and negative cases).
- [ ] Unit tests for `RunnableModel.capability_fields()`.
- [ ] Unit tests for `_ObservableCapability` event emission on success and failure.
- [ ] Unit tests for `WorldForge.register(x)` dispatch (including multi-protocol impls and `RunnableModel` bundles).
- [ ] Full gate green (ruff, pytest, coverage, docs-check, package-contract).

## M1 — Dual-routing call sites
- [ ] Rewrite `WorldForge.score_actions(...)` to accept `cost: str | Cost`, fall back to legacy `_providers` lookup when needed.
- [ ] Rewrite `WorldForge.select_actions(...)` similarly with `policy: str | Policy`.
- [ ] Rewrite `WorldForge.generate(...)` with `generator: str | Generator`.
- [ ] Rewrite `WorldForge.predict(...)` with `predictor: str | Predictor`.
- [ ] Rewrite `WorldForge.reason(...)` with `reasoner: str | Reasoner`.
- [ ] Rewrite `WorldForge.embed(...)` with `embedder: str | Embedder`.
- [ ] Rewrite `WorldForge.transfer(...)` with `transferer: str | Transferer`.
- [ ] Rewrite `WorldForge.plan(...)` to accept `policy: str | Policy` and `cost: str | Cost` (keep existing arg names as deprecated aliases during migration).
- [ ] Add `_adopt_legacy_provider(bp)` helper: reads `bp.capabilities`, wraps `bp` in `_ObservableCapability`, indexes into every matching new registry.
- [ ] Auto-adopt every legacy `BaseProvider` at `WorldForge.__init__` so both registries are populated during migration.
- [ ] Tests: string and instance forms for every capability method produce identical results.
- [ ] Tests: `forge.register(RunnableModel(...))` is equivalent to calling `register_<cap>` for each non-`None` field.
- [ ] Full gate green.

## M2 — Migrate MockProvider
- [ ] Create `src/worldforge/providers/mock/` package directory.
- [ ] Create `mock/policy.py` with `MockPolicy` class implementing `Policy`.
- [ ] Create `mock/cost.py` with `MockCost` class implementing `Cost`.
- [ ] Create `mock/generator.py` with `MockGenerator` class implementing `Generator`.
- [ ] Create `mock/predictor.py` with `MockPredictor` class implementing `Predictor`.
- [ ] Create `mock/reasoner.py` with `MockReasoner` class implementing `Reasoner`.
- [ ] Create `mock/embedder.py` with `MockEmbedder` class implementing `Embedder`.
- [ ] Create `mock/transferer.py` with `MockTransferer` class implementing `Transferer`.
- [ ] Create `mock/__init__.py` exporting a `build_mock()` factory returning a `RunnableModel` bundle named `"mock"`.
- [ ] Port existing `MockProvider` deterministic logic into each focused class.
- [ ] Delete `src/worldforge/providers/mock.py` (the old monolithic module).
- [ ] Update catalog factory `_mock` in `providers/catalog.py` to return the `RunnableModel` bundle.
- [ ] Rewrite mock tests against the new classes (positive: each capability produces deterministic output; negative: does not accidentally satisfy unrelated protocols).
- [ ] Behavior-equivalence test: legacy vs new output byte-identical for the sample inputs.
- [ ] Full gate green.

## M3 — Migrate local-runtime adapters
- [ ] Rewrite `LeWorldModelProvider` as `LeWorldModelCost` implementing `Cost`. Single file, single method.
- [ ] Rewrite `LeRobotPolicyProvider` as `LeRobotPolicy` implementing `Policy`.
- [ ] Rewrite `GrootPolicyClientProvider` as `GrootPolicy` implementing `Policy`.
- [ ] Profile metadata attached as class attribute or set in `__init__` on each new class.
- [ ] Lazy torch imports preserved inside methods (no top-level torch import).
- [ ] Shared helpers in `_policy.py`, `_tensor_validation.py`, `_config.py` unchanged — same call patterns from new classes.
- [ ] Update catalog factories `_leworldmodel`, `_lerobot`, `_gr00t` to return the new capability instances.
- [ ] Rewrite `tests/test_leworldmodel_provider.py`, `tests/test_lerobot_provider.py`, `tests/test_gr00t_provider.py` (or equivalents) against the new classes.
- [ ] Behavior-equivalence test for each adapter.
- [ ] Robotics showcase (`scripts/robotics-showcase`) runs end-to-end with the refactored adapters.
- [ ] Full gate green.

## M4 — Migrate remote HTTP adapters
- [ ] Rewrite `CosmosProvider` as `CosmosGenerator` implementing `Generator`.
- [ ] Rewrite `RunwayProvider` as two classes: `RunwayGenerator` (implements `Generator`) and `RunwayTransferer` (implements `Transferer`). Bundle via `build_runway()` → `RunnableModel`.
- [ ] Repurpose `RemoteProvider` as a credential/request-policy mixin. No longer a base class of `BaseProvider`.
- [ ] Update `_require_credentials()` and `_require_request_policy()` signatures.
- [ ] `http_utils.py` unchanged — same usage patterns.
- [ ] Update catalog factories `_cosmos`, `_runway` to return the new instances/bundle.
- [ ] Rewrite fixture-driven tests under `tests/fixtures/providers/` and corresponding test modules.
- [ ] Behavior-equivalence tests for each HTTP adapter using stubbed `httpx` transport.
- [ ] Event-shape parity: retry/success/failure phases emit with same metadata keys as before.
- [ ] Full gate green.

## M5 — Migrate scaffolds
- [ ] Rewrite `JepaProvider` and `GenieProvider` in `providers/remote.py` as placeholder `RunnableModel` bundles with mock capability impls and `implementation_status="scaffold"` profile.
- [ ] Rewrite `JEPAWMSProvider` in `providers/jepa_wms.py` similarly (still not exported or auto-registered per project rules).
- [ ] Update catalog entries `_jepa`, `_genie` to return the new bundles.
- [ ] Keep env-gated auto-registration semantics intact.
- [ ] Update `scripts/generate_provider_docs.py` to render scaffolds as `scaffold` in the new per-capability tables.
- [ ] Tests for scaffold registration behavior (env present → registered; absent → not registered).
- [ ] Full gate green.

## M6 — Delete legacy BaseProvider and duals
- [ ] Delete `BaseProvider` class from `src/worldforge/providers/base.py`.
- [ ] Delete `ProviderCapabilities` from `src/worldforge/models.py`.
- [ ] Delete `_adopt_legacy_provider` from `framework.py`.
- [ ] Remove legacy `_providers` registry and `register_provider()` method from `WorldForge`.
- [ ] Remove dual-routing fallbacks from every capability method; new registries are the only path.
- [ ] Delete `assert_provider_contract()` from `src/worldforge/testing/providers.py`. Ensure `assert_capability_contract()` covers its former behavior.
- [ ] Remove `BaseProvider`, `ProviderCapabilities` from `src/worldforge/__init__.py` and `src/worldforge/providers/__init__.py` exports.
- [ ] Update `CAPABILITY_NAMES` definition in `models.py` if affected, or confirm it still applies.
- [ ] Search for any remaining imports: `grep -r "BaseProvider\|ProviderCapabilities\|assert_provider_contract\|register_provider" src tests examples scripts docs` returns zero matches.
- [ ] Update CLI, benchmark, evaluation, harness modules for any vestigial references.
- [ ] Full gate green, including `bash scripts/test_package.sh`.

## M7 — Docs and CHANGELOG
- [ ] Rewrite `docs/src/architecture.md` with new capability-protocol architecture section.
- [ ] Rewrite `docs/src/provider-authoring-guide.md` with "four-line cost model" example and `RunnableModel` composition pattern.
- [ ] Update each provider page under `docs/src/providers/` for the class rename and single-capability shape.
- [ ] Update `README.md` capability table and the README code sample showing provider registration.
- [ ] Update `AGENTS.md` `<provider_contracts>` section.
- [ ] Update `CLAUDE.md` `<priority_rules>` rule #1 language from "capabilities" flags to "capability protocols".
- [ ] Update `CLAUDE.md` `<provider_contracts>` table for the new class names.
- [ ] Add `CHANGELOG.md` entry under a new `[Unreleased]` section documenting the breaking change with migration snippets:
  - Old: `class MyCost(BaseProvider): ... capabilities=ProviderCapabilities(score=True)`
  - New: `class MyCost: def score_actions(...): ...`
  - Old: `forge.register_provider(x)` → New: `forge.register(x)` or typed shortcut.
  - Old: `forge.score_actions("name", ...)` still works; new: `forge.score_actions(cost="name", ...)` or `forge.score_actions(cost=obj, ...)`.
- [ ] Run `uv run python scripts/generate_provider_docs.py --check` — clean.
- [ ] Build MkDocs site locally, verify no warnings.
- [ ] Full gate green.

## Post-merge
- [ ] (Optional follow-up) Rename "provider" → "adapter" or "capability" across module paths and user-visible surfaces. Separate spec.
- [ ] (Optional follow-up) Add `ScoringProvider.from_callable(fn, name=...)` convenience wrapper for ultra-light custom costs.
- [ ] (Optional follow-up) Investigate protocol-driven validation hooks that catch unimplemented methods at class-definition time, not just `isinstance` check time.
