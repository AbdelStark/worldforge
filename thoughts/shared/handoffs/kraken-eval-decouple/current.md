# Kraken Handoff: Inc B — re-center evaluation/ off World

## Checkpoints
**Task:** Re-center evaluation/ on forge.predict / forge.score_actions / LatentMPCController (no symbolic World)
**Started:** 2026-06-03

### Phase Status
- Phase 0 (Analyze): ✓ VALIDATED (read all evaluation/, tests, mpc, mock, framework)
- Phase 1 (Source refactor): ✓ VALIDATED (suites green, both run via mock)
- Phase 2 (Tests update): ✓ VALIDATED (1407 passed locally; added default-predict test)
- Phase 3 (Docs + CHANGELOG): ✓ VALIDATED (evaluation.md + CHANGELOG updated)
- Phase 4 (Full gate green): ✓ VALIDATED (ruff/format/provider-docs OK; 1407 passed, 2 skipped; coverage 90.88%)

### Key decisions
- `_world.py:evaluate()` calls `run_report(self.provider, world=self, ...)` and is NON-modifiable.
  Therefore `run_report`/`run_report_artifacts` keep an OPTIONAL, IGNORED `world=None` kwarg
  (no `World` type import) so the forbidden file keeps working. Internal methods
  (`evaluate_scenario`, `_evaluate_custom_scenario`, `run`, renamed `_run_one_provider`) drop `world`.
- physics suite stays `required_capabilities=("predict",)` (test_provenance asserts ("predict",)).
- planning suite becomes `required_capabilities=("score",)` (mock supports score).
- Keep _CONTRACT_NOTES keys + "relocates the selected object" wording (failure-gallery test asserts).
- Keep all suite_ids + scenario names. Keep metric keys physics_score/confidence and
  success_probability where tests assert.

### Baseline
- 50 passed in affected files before changes.
