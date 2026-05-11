# Demo Showcase Workflows

`scripts/demo_showcases.py` is the checkout-safe demo evidence runner for the current showcase
roadmap stream. It composes existing WorldForge examples, diagnostics, preserved-run workspaces,
issue bundles, replay fixtures, and host examples without installing optional model runtimes,
calling paid providers, opening GUIs, or controlling robots.

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases
uv run python scripts/demo_showcases.py run first-run --format json --overwrite
```

Expected success signal: the command exits `0`, reports `status: passed`, and writes one
`run_manifest.json` plus `results/summary.json` and `reports/summary.md` for every selected
workflow. First triage step: open the failed workflow's `workflow-result.json`, then inspect the
referenced preserved run manifest.

## Artifact Layout

The default workspace is `.worldforge/demo-showcases/`.

| Path | Purpose | Safe attachment note |
| --- | --- | --- |
| `<workflow>/workflow-result.json` | short machine-readable workflow result | safe when `safe_to_attach` is `true` |
| `<workflow>/runs/<run-id>/run_manifest.json` | preserved command, provider, operation, status, artifacts | safe by construction; no raw secrets or signed URLs |
| `<workflow>/runs/<run-id>/results/summary.json` | full workflow summary | safe unless the workflow marks otherwise |
| `<workflow>/runs/<run-id>/reports/summary.md` | human summary with claim boundary and first triage step | safe unless the workflow marks otherwise |
| `<workflow>/issue-bundle/` | issue-ready evidence bundle for the diagnostics workflow | attach only when `evidence_manifest.json` says `safe_to_attach: true` |

## Workflow Matrix

| Workflow | Issue | Command | Expected output | Primary artifact | First triage step |
| --- | ---: | --- | --- | --- | --- |
| `first-run` | #189 | `uv run python scripts/demo_showcases.py run first-run` | mock world created, object added, prediction recorded, export and preflight written | `first-run/exported-world.json` and `first-run/preflight.json` | run `uv run worldforge world preflight --state-dir <demo>/worlds` |
| `diagnostics-issue-bundle` | #190 | `uv run python scripts/demo_showcases.py run diagnostics-issue-bundle` | skipped provider diagnostic preserved and bundled | `diagnostics-issue-bundle/issue-bundle/issue.md` | inspect `evidence_manifest.json` before attaching |
| `robotics-replay` | #191 | `uv run python scripts/demo_showcases.py run robotics-replay` | deterministic policy-plus-score replay summary | `robotics-replay/robotics-replay-manifest.json` | run `uv run worldforge-demo-lerobot` before prepared-host commands |
| `remote-media-dry-run` | #192 | `uv run python scripts/demo_showcases.py run remote-media-dry-run` | sanitized Cosmos success and Runway expired-artifact fixture events | `remote-media-dry-run/remote-media-events.json` | inspect redacted provider event targets before any live smoke |
| `adapter-author` | #193 | `uv run python scripts/demo_showcases.py run adapter-author` | provider scaffold generated under demo output and promotion blockers reported | `adapter-author/generated-provider/` | replace placeholder fixtures, then run the generated provider test |
| `batch-eval` | #194 | `uv run python scripts/demo_showcases.py run batch-eval` | eval success and controlled benchmark budget failure preserved | `batch-eval/batch-host/runs/<run-id>/run_manifest.json` | inspect the failed benchmark manifest before changing budgets |
| `service-host` | #195 | `uv run python scripts/demo_showcases.py run service-host` | stdlib service host readiness and one mock request summary | `service-host/runs/<run-id>/results/summary.json` | run `uv run python examples/hosts/service/app.py --help` and inspect `/readyz` |
| `rerun-gallery` | #196 | `uv run python scripts/demo_showcases.py run rerun-gallery` | manifest-only Rerun gallery with missing-extra status | `rerun-gallery/rerun-gallery-manifest.json` | install the `rerun` extra before opening `.rrd` files |
| `failure-lab` | #197 | `uv run python scripts/demo_showcases.py run failure-lab` | isolated failure drills, preflight, and recovery commands | `failure-lab/failure-lab-report.json` | read `recovery_commands` before touching real `.worldforge` state |
| `use-case-cookbook` | #198 | `uv run python scripts/demo_showcases.py run use-case-cookbook` | cookbook recipe count and docs artifact reference | `docs/src/use-case-cookbook.md` | open the recipe matching the failed command and artifact |
| `external-provider-package` | #237 | `uv run python scripts/demo_showcases.py run external-provider-package` | temp external provider package generated and entry-point discovery report preserved | `external-provider-package/external-provider-discovery.json` | inspect the discovery report, then run the generated package tests before publishing |
| `custom-evaluation-suite` | #238 | `uv run python scripts/demo_showcases.py run custom-evaluation-suite` | custom suite runs with provenance, one controlled failure, and report artifacts | `custom-evaluation-suite/custom-eval-artifacts/` | open `markdown`, then inspect `failure_gallery.md` for the controlled failed case |
| `policy-score-candidate-lab` | #239 | `uv run python scripts/demo_showcases.py run policy-score-candidate-lab` | deterministic action candidates ranked by a score provider with raw policy actions preserved | `policy-score-candidate-lab/policy-score-candidate-lab.json` | verify the selected row matches `score_result.best_index` |

## Runtime Boundaries

These workflows prove the WorldForge integration layer and artifact contracts, not upstream model
quality or physical execution. Optional runtimes remain host-owned:

- LeWorldModel, LeRobot, GR00T, torch, checkpoints, simulators, and robot controllers are not
  installed by this runner.
- Cosmos and Runway paths use fixture-backed events and do not make paid API calls.
- Rerun is represented by a manifest in the checkout path; `.rrd` generation still requires the
  `rerun` extra or a prepared-host robotics run.
- Provider scaffolds generated by the adapter-author workflow are intentionally incomplete and must
  not be registered or promoted until real fixtures, runtime manifests, docs, and tests pass.
- External provider packages generated by the demo live under the selected workspace and prove
  package shape plus discovery behavior only; they are not published, installed globally, or
  treated as real adapter evidence.
- Custom evaluation suite output is deterministic adapter-contract evidence. Its controlled failed
  case demonstrates report and failure-gallery handling, not provider quality or physical fidelity.
- The policy+score candidate lab uses local deterministic providers to show candidate generation,
  scoring, raw action preservation, translator boundaries, and safe artifact shape. It is not a
  robot controller, simulator, checkpoint run, or physical-performance claim.
- Benchmark failures in the batch workflow are controlled budget failures so the issue and release
  evidence path can be tested without changing production thresholds.

For task-oriented commands, see the [Use Case Cookbook](./use-case-cookbook.md).
