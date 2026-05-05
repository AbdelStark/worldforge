# Claim-To-Evidence Map

Issue: [#140](https://github.com/AbdelStark/worldforge/issues/140)

Status: active public evidence map.

This page maps public WorldForge claims to the evidence class that supports them. Use it when
citing README claims in issues, release evidence, or provider promotion reviews. It does not add
new benchmark numbers, broaden provider capabilities, or turn deterministic checks into physical
fidelity claims.

## Evidence Classes

| Class | Meaning | Expected evidence |
| --- | --- | --- |
| `checkout-tested` | Runs from a clean checkout without credentials, network, GPUs, or optional model runtimes. | Local pytest, CLI, docs, and package commands. |
| `fixture-tested` | Covered by synthetic JSON fixtures or recorded parser fixtures that stay in the repository. | `tests/fixtures/`, `worldforge.testing` fixtures, provider parser tests, or contract helpers. |
| `prepared-host smoke-tested` | Requires host-owned credentials, checkpoints, optional runtimes, or robot/model assets. | A documented command plus sanitized `run_manifest.json` or live-smoke registry row. |
| `release-gated` | Part of release evidence or CI quality gates. | Coverage, package contract, benchmark preset, docs build, or release evidence report. |
| `deferred` | A design or scaffold exists, but executable public behavior is intentionally withheld. | Explicit blocker, revisit trigger, or fail-closed scaffold docs. |
| `unsupported` | WorldForge does not claim or own this behavior. | Public non-claim and first routing step to host or upstream owner. |

## Capability Claims

| Public claim | Evidence class | Evidence | Command or artifact | Boundary |
| --- | --- | --- | --- | --- |
| `predict` is a provider capability for state rollout. | `checkout-tested` | `tests/test_world_lifecycle.py`, `tests/test_provider_contracts.py`, `tests/test_capability_fixtures.py` | `uv run worldforge world predict <world-id> --object-id <object-id> --x 0.4 --y 0.5 --z 0` | Built-in deterministic checks do not prove physical fidelity. |
| `score` ranks action candidates for score-model workflows. | `fixture-tested`; `prepared-host smoke-tested` for real runtimes | `tests/test_leworldmodel_provider.py`, `tests/test_jepa_provider.py`, `tests/test_jepa_wms_provider.py`, `tests/fixtures/providers/*score*` | `uv run worldforge-demo-leworldmodel`; live-smoke registry rows for `leworldmodel`, `jepa`, and `jepa-wms` | Tensors, checkpoints, preprocessing, and devices stay host-owned. |
| `policy` returns embodiment-specific action chunks. | `fixture-tested`; `prepared-host smoke-tested` for real runtimes | `tests/test_lerobot_provider.py`, `tests/test_gr00t_provider.py`, `tests/test_provider_contracts.py` | `scripts/robotics-showcase --json-only --no-tui --no-rerun`; uploaded `run_manifest.json` in live robotics CI | WorldForge preserves raw actions and requires host-owned translators before executable actions. |
| `generate` produces media artifacts. | `checkout-tested`; `fixture-tested`; `prepared-host smoke-tested` for remote APIs | `tests/test_cosmos_provider.py`, `tests/test_runway_provider.py`, `tests/test_remote_video_providers.py` | `uv run worldforge benchmark --preset remote-media-dryrun` on a configured host | Returned media is an artifact contract, not a quality or safety claim. |
| `transfer` transforms a media artifact. | `checkout-tested`; `fixture-tested` | `tests/test_remote_video_providers.py`, `tests/test_provider_contracts.py`, `src/worldforge/testing/fixtures/transfer/` | `uv run worldforge benchmark --provider mock --operation transfer --input-file examples/benchmark-inputs.json` | Remote transfer requires provider credentials and artifact retention by the host. |
| `reason` and `embed` are narrow mock-supported capability surfaces. | `checkout-tested` | `tests/test_provider_contracts.py`, `tests/test_capability_fixtures.py`, `tests/test_benchmark.py` | `uv run worldforge benchmark --preset parser-overhead` | They are contract and adapter-path checks, not general-purpose LLM or embedding quality claims. |
| `plan` is a WorldForge facade over composed surfaces. | `checkout-tested` | `tests/test_evaluation_and_planning.py`, `tests/test_capability_dual_routing.py` | `uv run worldforge eval --suite planning --provider mock --format json` | `plan` is not advertised as a provider-owned capability by default. |

## Provider And Runtime Claims

| Public claim | Evidence class | Evidence | Command or artifact | Boundary |
| --- | --- | --- | --- | --- |
| The `mock` provider is stable and deterministic. | `checkout-tested`; `release-gated` | `tests/test_provider_contracts.py`, `tests/test_benchmark_presets.py` | `uv run worldforge benchmark --preset mock-smoke` | Synthetic provider behavior is not runtime fidelity evidence. |
| Cosmos and Runway are remote media adapters. | `fixture-tested`; `prepared-host smoke-tested` when configured | `tests/fixtures/providers/cosmos_*.json`, `tests/fixtures/providers/runway_*.json`, provider docs | `uv run worldforge benchmark --preset remote-media-dryrun` | Credentials, upstream availability, returned artifact retention, and paid usage stay host-owned. |
| LeWorldModel exposes `score`. | `fixture-tested`; `prepared-host smoke-tested` | `tests/test_leworldmodel_provider.py`, `tests/test_lerobot_leworldmodel_smoke_script.py`, live-smoke registry | `scripts/robotics-showcase --json-only --no-tui --no-rerun` | `stable-worldmodel`, torch, checkpoints, tensors, and device behavior are optional runtime concerns. |
| LeRobot and GR00T expose `policy`. | `fixture-tested`; `prepared-host smoke-tested` | `tests/test_lerobot_provider.py`, `tests/test_gr00t_provider.py`, live-smoke registry | `scripts/robotics-showcase` for LeRobot; `scripts/smoke_gr00t_policy.py --help` for GR00T setup | Robot controllers, safety checks, and action translators are host-owned. |
| JEPA is experimental and score-only. | `fixture-tested`; `prepared-host smoke-tested` only when host evidence exists | `tests/test_jepa_provider.py`, `tests/test_jepa_wms_provider.py`, runtime manifest docs | `uv run worldforge-smoke-jepa-wms --help` | Torch-hub runtime, weights, preprocessing, and license review stay host-owned. |
| Genie is a scaffold reservation. | `deferred` | `tests/test_remote_scaffold_providers.py`, `docs/src/providers/genie.md` | Revisit trigger in the Genie provider docs | No public automation API contract is claimed; scaffold behavior remains fail-closed. |
| Nano World Model is a candidate, not a provider surface. | `deferred` | `docs/src/provider-cohort-selection.md` | Follow the assigned candidate issue before any catalog claim | No `nanowm` provider is exported or auto-registered. |

## Workflow And Artifact Claims

| Public claim | Evidence class | Evidence | Command or artifact | Boundary |
| --- | --- | --- | --- | --- |
| Evaluation reports carry provenance and claim boundaries. | `checkout-tested`; `release-gated` | `tests/test_provenance.py`, `tests/test_evaluation_and_planning.py`, `docs/src/evaluation.md` | `uv run worldforge eval --suite planning --provider mock --format json` | Scores are deterministic contract signals, not physical or media-quality metrics. |
| Failed evaluation reports include issue-ready failure galleries. | `checkout-tested`; `release-gated` | `tests/test_evaluation_failure_gallery.py`, `docs/src/evaluation.md`, `docs/src/api/python.md` | `uv run worldforge eval --suite planning --provider mock --format json` plus `report.artifacts()["failure_gallery.json"]` | Galleries are sanitized deterministic contract triage, not provider ranking or fidelity evidence. |
| Benchmark reports carry provenance, budgets, and preset gates. | `checkout-tested`; `release-gated` | `tests/test_benchmark.py`, `tests/test_benchmark_presets.py`, `docs/src/benchmarking.md` | `uv run worldforge benchmark --preset release-evidence --format json --run-workspace .worldforge` | Timings are process-local adapter-path measurements, not machine-independent performance claims. |
| Benchmark budget changes have a preserved baseline review path. | `checkout-tested`; `release-gated` | `tests/test_benchmark_budget_calibration.py`, `scripts/calibrate_benchmark_budgets.py`, `docs/src/benchmarking.md` | `uv run python scripts/calibrate_benchmark_budgets.py --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json` | Candidate budgets are review artifacts; they do not automatically weaken release gates. |
| Evaluation evidence bundles package preserved runs. | `checkout-tested`; `release-gated` | `tests/test_evidence_bundle.py`, `scripts/generate_evidence_bundle.py`, `docs/src/evaluation.md` | `uv run python scripts/generate_evidence_bundle.py --workspace-dir .worldforge` | Unsafe, local-only, signed, or binary artifacts are excluded or marked; the bundle does not upload anything. |
| Live-smoke evidence is indexed in a publishable registry. | `prepared-host smoke-tested`; `release-gated` | `tests/test_live_smoke_evidence.py`, `docs/src/live-smoke-evidence.json` | `uv run python scripts/generate_release_evidence.py --live-smoke-registry docs/src/live-smoke-evidence.json` | Missing optional runtimes or credentials are explicit skip states, not silent omissions. |
| Rerun records sanitized events and artifacts when the extra is installed. | `checkout-tested`; `prepared-host smoke-tested` for robotics showcase | `tests/test_rerun_integration.py`, `tests/test_robotics_showcase.py` | `uv run --extra rerun worldforge-demo-rerun`; `/tmp/worldforge-robotics-showcase/real-run.rrd` | Rerun is optional observability, not a provider capability or base dependency. |
| TheWorldHarness is optional and Textual-isolated. | `checkout-tested`; `release-gated` | `tests/test_harness_flows.py`, `tests/test_harness_cli.py`, `tests/test_harness_tui.py` | `uv run --extra harness worldforge-harness` | Non-TUI flow logic stays independent from Textual imports. |
| Local JSON persistence is the authoritative built-in store. | `checkout-tested` | `tests/test_world_lifecycle.py`, `tests/test_cli_world_commands.py`, persistence ADR | `uv run worldforge world export <world-id> --output world.json` | It is not a concurrent multi-writer database or service-grade durable store. |
| Quality gates run on Python 3.13 with coverage, docs, package, and lint checks. | `release-gated` | `.github/workflows/ci.yml`, `scripts/test_package.sh`, `docs/src/quality.md` | `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` | Passing gates does not expand runtime capability claims. |

## Unsupported Or Non-Claims

| Non-claim | Evidence class | First routing step |
| --- | --- | --- |
| Physical fidelity, media quality, robot safety certification, or real-world control safety. | `unsupported` | Treat the WorldForge report as adapter evidence only; use task-specific host evaluation and safety review. |
| Upstream provider SLA, paid API availability, rate limits, credential management, or artifact retention. | `unsupported` | Check the provider's upstream status, credentials, and host retention policy. |
| Training LeWorldModel, JEPA, NanoWM, GR00T, LeRobot, or any other model inside WorldForge. | `unsupported` | Use the upstream training repository and keep artifacts out of the WorldForge base package. |
| Service-grade persistence, database migrations, lock files, or multi-writer storage. | `unsupported` | Follow the persistence adapter boundary ADR before introducing a host-owned store. |
| Hosted dashboard, telemetry service, queue, deployment, auth, or alerting. | `unsupported` | Implement these in the host application and attach sanitized WorldForge run artifacts. |

## Usage

For issue or release notes, cite the row by claim and include the matching command or artifact.
Expected success signals are the explicit test pass count, a benchmark gate with `Status: passed`,
or a validated `run_manifest.json`. If the command fails, the first triage step is to open the
linked docs page for that row and check whether the provider is checkout-safe, fixture-backed,
credentialed, prepared-host, deferred, or unsupported.
