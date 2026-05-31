# CLI Reference

WorldForge ships a local-first CLI for provider diagnostics, persisted mock worlds, evaluation,
benchmarking, packaged examples, and optional visual harnesses. Commands run against the same typed
Python surfaces as the library.

Use `uv run worldforge --help` and each subcommand's `--help` output as the exact parser contract.
This page is the stable operator map.

## Discovery

```bash
uv run worldforge --help
uv run worldforge examples
uv run worldforge examples --format json
```

Contributor setup and static release-support checks:

```bash
uv run python scripts/contributor_doctor.py --format markdown
uv run python scripts/contributor_doctor.py --format json
uv run python scripts/check_docs_commands.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_core_performance.py
```

`contributor_doctor.py` reports missing required tools as setup failures, optional runtime
dependencies as skips, and missing GitHub CLI auth as a publishing warning rather than a local
validation failure.

Operator failure drills:

```bash
uv run worldforge drills list
uv run worldforge drills run missing-credentials --workspace-dir .worldforge/drills
uv run worldforge drills run unsafe-event-metadata --workspace-dir .worldforge/drills --bundle
```

The drill command surface is checkout-safe by default. Each run preserves a manifest, records the
expected failure and recovery command, and confines generated state to the requested temporary or
documented workspace.

## Provider Diagnostics

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge provider contract mock --format json
uv run worldforge provider docs
uv run worldforge provider health mock
uv run worldforge negotiate --list
uv run worldforge negotiate --workflow policy-plus-score
```

Use `doctor` first when a provider is missing. Optional providers such as LeWorldModel, LeRobot,
GR00T, Cosmos-Policy, and LeWorldModel only register when their host-owned environment variables and runtimes are
available. `worldforge negotiate` answers the higher-level question "can my providers satisfy this
workflow before I run it?" — see [Capability Negotiation](./capability-negotiation.md).

## Local Worlds

```bash
uv run worldforge world create lab --provider mock
uv run worldforge world list
uv run worldforge world show <world-id>
uv run worldforge world objects <world-id>
uv run worldforge world history <world-id>
uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge
uv run worldforge world migration-preview <world-id> --state-dir .worldforge/worlds
uv run worldforge world migration-preview world.json --source-path
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name imported-lab
uv run worldforge world fork <world-id> --name forked-lab
uv run worldforge world delete <world-id>
uv run worldforge world diff <source-id> <target-id>
uv run worldforge scenario validate examples/scenarios/cube-on-table.json
uv run worldforge scenario run examples/scenarios/spawn-and-move.json --state-dir .worldforge/worlds
```

World IDs are local JSON file stems. Values with path separators or traversal-shaped input are
rejected before filesystem access.

`world preflight` is read-only. It checks the world state directory, requested `--world-id` values,
corrupted world JSON, invalid history entries, object bounding-box coherence, preserved run
manifests, stale run directories, unsafe artifact paths, and run-retention pressure. JSON output is
safe to attach by default; the command exits non-zero when it finds error-severity state.

`world migration-preview` is also read-only. It accepts either a persisted world id or
`--source-path` pointing at persisted or exported world JSON, then reports the world schema version,
required canonicalization changes, invalid fields, unsafe IDs, bounding-box corrections,
`can_apply_safely`, and the first triage step. It does not rewrite state; actual migration remains
an explicit second step.

## Scene Mutations And Prediction

```bash
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world update-object <world-id> cube-1 --x 0.2 --y 0.5 --z 0
uv run worldforge world remove-object <world-id> cube-1
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
```

Scene mutations append typed history entries. Position patches keep bounding boxes translated with
the pose, and predictions append provider action entries after the provider returns the next state.

## Evaluation

```bash
uv run worldforge eval --suite physics --provider mock
uv run worldforge eval --suite planning --provider mock --format json
```

Built-in suites are deterministic contract checks. They are useful for adapter regression testing,
not claims of physical fidelity, media quality, or real-world safety.

## Benchmarking

```bash
uv run worldforge benchmark --provider mock --iterations 5 --format json
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation predict --budget-file examples/benchmark-budget.json
```

Budget files can make latency, throughput, success-rate, retry-count, and error-count limits fail
with a non-zero exit code. Preserve benchmark artifacts before using numbers in a release note,
paper, or public claim.

## Robotics Showcase TUI

```bash
scripts/robotics-showcase
scripts/robotics-showcase --no-tui
uv run worldforge runs list --status failed --artifact-type json
```

The robotics showcase report is optional and Textual-backed. It keeps Textual out of the base
package while visualizing the prepared-host LeRobot plus LeWorldModel policy+score run. The run
history commands are checkout-safe and work without Textual; they report preserved-run filters,
sanitized rerun commands, and first recovery actions without printing secret values.

Expected success signal: the selected flow reaches a completed run workspace and the inspector
shows its saved artifact paths. For `cosmos-policy`, the replay should report
`raw_action_shape: [50, 14]`, `translated_actions: 50`, and
`saved_replay_artifact: artifacts/cosmos-policy-replay.json`. For `gr00t-replay`, expect
`translated_actions: 40` and `saved_replay_artifact: artifacts/gr00t-replay.json`. For
`robotics-compare`, expect `total_translated_actions: 92` and
`comparison_artifact: artifacts/robotics-policy-comparison.json`. First triage step: open the saved
run workspace and inspect `logs/provider-events.jsonl` plus the flow-specific artifact, either
`artifacts/cosmos-policy-replay.json`, `artifacts/gr00t-replay.json`, or
`artifacts/robotics-policy-comparison.json`; for live-provider readiness checks, run
`uv run worldforge provider workbench cosmos-policy --format json --live`.

## Packaged Demos

Checkout-safe demos use injected deterministic runtimes:

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
uv run --extra rerun worldforge-demo-rerun
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases
```

They validate WorldForge's provider adapters, planning, execution, persistence, reload, and event
paths without installing optional model runtimes or downloading checkpoints. The Rerun demo
requires the `rerun` extra and records events, worlds, plans, 3D object boxes, and benchmark
metrics to a `.rrd` artifact. The demo showcase runner preserves ten issue-backed workflows with
`run_manifest.json`, JSON summaries, Markdown summaries, safe issue bundles, and first triage
steps. See [Demo Showcase Workflows](./demo-showcases.md) and
[Use Case Cookbook](./use-case-cookbook.md).

## Optional Runtime Smokes

Real LeWorldModel checkpoint scoring:

```bash
scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu
```

LeRobot policy plus LeWorldModel checkpoint scoring replay:

```bash
scripts/robotics-showcase --health-only
scripts/robotics-showcase
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

Open the run's TensorBoard logs without launching the Textual report - useful
for non-interactive verification or for opening TensorBoard from a shell:

```bash
uv run worldforge-open-tensorboard --logdir .worldforge/tensorboard/<run>
uv run worldforge-open-tensorboard --logdir .worldforge/tensorboard/<run> --probe --no-browser
```

See [TensorBoard Integration](./tensorboard.md) for the full flag reference.

Live GR00T and LeRobot policy smoke helpers:

```bash
uv run worldforge-smoke-cosmos-policy --help
uv run worldforge-smoke-jepa-wms --help
uv run worldforge-smoke-lerobot-leworldmodel --help
uv run python scripts/smoke_gr00t_policy.py --help
uv run python scripts/smoke_lerobot_policy.py --help
```

Optional-runtime commands require host-owned runtimes, checkpoints, credentials, observations, and
task-specific action translators. WorldForge does not add those dependencies to the base package and
does not treat injected demos as real upstream inference.

More detail:

- [Robotics Replay Showcase](./robotics-showcase.md)
- [Robotics Replay Showcase](./robotics-showcase.md)
- [Examples And CLI Commands](./examples.md)
- [User And Operator Playbooks](./playbooks.md)
