# Use Case Cookbook

These recipes are copy-pasteable paths for common WorldForge work. Each one names the command, the
expected output, the artifact to keep, the first triage step, and the non-claim boundary. Use the
matching demo workflow when you want a preserved showcase run for issue or release evidence.

### Recipe 1: First Local World

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | `status: passed`, one mock world, one object, one prediction, and preflight status |
| Artifact | `.worldforge/demo-showcases/first-run/exported-world.json` |
| First triage step | run `uv run worldforge world preflight --state-dir .worldforge/demo-showcases/first-run/worlds` |
| Boundary | mock provider only; no physical-fidelity or real-runtime claim |

### Recipe 2: Provider Diagnostic Issue Bundle

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run diagnostics-issue-bundle --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | skipped provider diagnostic with `safe_to_attach: true` |
| Artifact | `.worldforge/demo-showcases/diagnostics-issue-bundle/issue-bundle/issue.md` |
| First triage step | open `evidence_manifest.json` and confirm `safe_to_attach: true` |
| Boundary | fixture diagnostic only; do not paste raw provider credentials or signed URLs |

### Recipe 3: Robotics Replay Before Prepared-Host Work

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run robotics-replay --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | selected candidate index, candidate costs, policy result, score result, and event phases |
| Artifact | `.worldforge/demo-showcases/robotics-replay/robotics-replay-manifest.json` |
| First triage step | run `uv run worldforge-demo-lerobot` before `scripts/robotics-showcase --health-only` |
| Boundary | deterministic replay only; robot hardware, controllers, safety checks, and checkpoints stay host-owned |

### Recipe 4: Remote Media Dry Run

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run remote-media-dry-run --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | redacted Cosmos success and Runway expired-artifact events |
| Artifact | `.worldforge/demo-showcases/remote-media-dry-run/remote-media-events.json` |
| First triage step | inspect provider event `target`, `message`, and `metadata` for redaction before live smoke |
| Boundary | fixture-backed dry run only; no paid API calls or artifact-retention guarantee |

### Recipe 5: Adapter Author Scaffold

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run adapter-author --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | generated provider, generated test, docs stub, runtime manifest stub, and workbench report |
| Artifact | `.worldforge/demo-showcases/adapter-author/generated-provider/` |
| First triage step | replace placeholder fixtures and run the generated provider test before promotion |
| Boundary | scaffold is intentionally fail-closed and incomplete; it is not evidence of real provider behavior |

### Recipe 6: Batch Eval With Budget Failure

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run batch-eval --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | eval job passes, benchmark job returns controlled `exit_code: 1`, and both runs are preserved |
| Artifact | `.worldforge/demo-showcases/batch-eval/batch-host/runs/<run-id>/run_manifest.json` |
| First triage step | inspect the benchmark report and copied budget before changing thresholds |
| Boundary | mock provider and impossible budget only; no scheduler, durable storage, or release budget claim |

### Recipe 7: Stdlib Service Host Smoke

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run service-host --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | readiness is `ready`, one mock prediction request is summarized, and server shutdown is recorded |
| Artifact | `.worldforge/demo-showcases/service-host/runs/<run-id>/results/summary.json` |
| First triage step | run `uv run python examples/hosts/service/app.py --provider mock --port 8080` and inspect `/readyz` |
| Boundary | reference host only; auth, deployment, uptime, dashboards, and rollback remain host-owned |

### Recipe 8: Rerun Gallery Manifest

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run rerun-gallery --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | `status: skipped` with missing `rerun` extra and a gallery layer manifest |
| Artifact | `.worldforge/demo-showcases/rerun-gallery/rerun-gallery-manifest.json` |
| First triage step | install `worldforge-ai[rerun]`, then run `uv run --extra rerun worldforge-demo-rerun` |
| Boundary | checkout-safe manifest only; visual `.rrd` files require the optional Rerun runtime |

### Recipe 9: Failure Recovery Lab

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run failure-lab --workspace-dir .worldforge/demo-showcases --overwrite` |
| Expected output | missing credential, corrupted state, unsafe metadata drills, preflight, and recovery commands |
| Artifact | `.worldforge/demo-showcases/failure-lab/failure-lab-report.json` |
| First triage step | read `recovery_commands` before touching real `.worldforge` state |
| Boundary | mutates only the lab workspace; no real credentials, optional runtimes, or user state are used |

### Recipe 10: Full Showcase Evidence Sweep

| Field | Value |
| --- | --- |
| Command | `uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases --format json --overwrite` |
| Expected output | all ten workflows report `passed` or intentional `skipped`, and top-level status is `passed` |
| Artifact | `.worldforge/demo-showcases/<workflow>/runs/<run-id>/run_manifest.json` |
| First triage step | open the failed workflow's `workflow-result.json`, then its preserved `run_manifest.json` |
| Boundary | integration evidence only; optional runtimes, provider credentials, robots, and physical-fidelity claims stay outside the checkout path |
