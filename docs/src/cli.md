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

## Provider Diagnostics

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge provider docs
uv run worldforge provider health mock
```

Use `doctor` first when a provider is missing. Optional providers such as LeWorldModel, LeRobot,
GR00T, Cosmos, and Runway only register when their host-owned environment variables and runtimes are
available.

## Local Worlds

```bash
uv run worldforge world create lab --provider mock
uv run worldforge world list
uv run worldforge world show <world-id>
uv run worldforge world objects <world-id>
uv run worldforge world history <world-id>
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name imported-lab
uv run worldforge world fork <world-id> --name forked-lab
uv run worldforge world delete <world-id>
```

World IDs are local JSON file stems. Values with path separators or traversal-shaped input are
rejected before filesystem access.

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
uv run worldforge eval --suite reasoning --provider mock
uv run worldforge eval --suite generation --provider mock
uv run worldforge eval --suite transfer --provider mock
```

Built-in suites are deterministic contract checks. They are useful for adapter regression testing,
not claims of physical fidelity, media quality, or real-world safety.

## Benchmarking

```bash
uv run worldforge benchmark --provider mock --iterations 5 --format json
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation generate --budget-file examples/benchmark-budget.json
```

Budget files can make latency, throughput, success-rate, retry-count, and error-count limits fail
with a non-zero exit code. Preserve benchmark artifacts before using numbers in a release note,
paper, or public claim.

## Visual Harness

```bash
uv run --extra harness worldforge-harness
uv run --extra harness worldforge-harness --flow leworldmodel
uv run --extra harness worldforge-harness --flow lerobot
uv run --extra harness worldforge-harness --flow diagnostics
uv run worldforge harness --list
uv run worldforge harness --connectors --format json
```

TheWorldHarness is optional and Textual-backed. It keeps Textual out of the base package while
providing a visual workspace for checkout-safe flows, provider diagnostics, local worlds, evals, and
benchmarks. The connector metadata command is checkout-safe and works without Textual; it reports
provider readiness categories, missing env-var names, optional runtime dependencies, and first smoke
commands without printing secret values.

## Packaged Demos

Checkout-safe demos use injected deterministic runtimes:

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
uv run --extra rerun worldforge-demo-rerun
```

They validate WorldForge's provider adapters, planning, execution, persistence, reload, and event
paths without installing optional model runtimes or downloading checkpoints. The Rerun demo
requires the `rerun` extra and records events, worlds, plans, 3D object boxes, and benchmark
metrics to a `.rrd` artifact.

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

Live GR00T and LeRobot policy smoke helpers:

```bash
uv run python scripts/smoke_gr00t_policy.py --help
uv run python scripts/smoke_lerobot_policy.py --help
```

Optional-runtime commands require host-owned runtimes, checkpoints, credentials, observations, and
task-specific action translators. WorldForge does not add those dependencies to the base package and
does not treat injected demos as real upstream inference.

More detail:

- [Robotics Replay Showcase](./robotics-showcase.md)
- [TheWorldHarness](./theworldharness.md)
- [Examples And CLI Commands](./examples.md)
- [User And Operator Playbooks](./playbooks.md)
