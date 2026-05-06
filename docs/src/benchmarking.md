# Benchmarking

WorldForge includes a capability-aware benchmark harness for registered full providers and
registered capability protocol implementations. It can measure direct provider surfaces:
`predict`, `reason`, `generate`, `transfer`, `embed`, `score`, and `policy`. `plan` remains a
WorldForge facade workflow, so benchmark score providers and policy providers directly when you
need planning-path latency.

## Python

```python
from worldforge import ProviderBenchmarkHarness

harness = ProviderBenchmarkHarness(forge=forge)
report = harness.run(
    ["mock"],
    operations=["predict", "generate", "transfer", "embed"],
    iterations=5,
    concurrency=2,
)

print(report.to_markdown())
```

If the optional Rerun integration is installed, `RerunArtifactLogger.log_benchmark_report(report)`
records the same report JSON plus per-result metric scalars into a `.rrd` inspection artifact.

Score and policy providers use the same benchmark runner with provider-native inputs supplied by
the host:

```python
from worldforge import BenchmarkInputs, ProviderBenchmarkHarness

inputs = BenchmarkInputs(
    score_info={
        "pixels": [[[[0.0]]]],
        "goal": [[[0.3, 0.5, 0.0]]],
        "action": [[[0.0, 0.5, 0.0]]],
    },
    score_action_candidates=[[[[0.0, 0.5, 0.0]], [[0.3, 0.5, 0.0]]]],
    policy_info={
        "observation": {
            "state": {"cube": [0.0, 0.5, 0.0]},
            "language": "move the cube",
        },
        "mode": "select_action",
    },
)

report = ProviderBenchmarkHarness(forge=forge).run(
    ["leworldmodel", "lerobot"],
    iterations=3,
    inputs=inputs,
)
```

## CLI

```bash
uv run worldforge benchmark --provider mock --iterations 5
uv run worldforge benchmark --provider mock --operation generate --format json
uv run worldforge benchmark --provider mock --operation embed --format markdown
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
```

Use `--run-workspace` when benchmark numbers need manifest-backed provenance:

```bash
uv run worldforge benchmark \
  --provider mock \
  --operation predict \
  --iterations 5 \
  --run-workspace .worldforge
```

The run workspace stores the manifest, JSON/Markdown/CSV reports, result summary, budget verdict
when supplied, and event count under `.worldforge/runs/<run-id>/`.

Compare preserved benchmark runs before citing a regression, release claim, or provider change:

```bash
uv run worldforge runs compare \
  .worldforge/runs/<baseline-run-id> \
  .worldforge/runs/<candidate-run-id> \
  --format markdown

uv run worldforge runs compare \
  .worldforge/runs/<baseline-run-id> \
  .worldforge/runs/<candidate-run-id> \
  --format csv \
  --output .worldforge/runs/benchmark-comparison.csv
```

`runs compare` accepts run directories, `run_manifest.json` files, or `reports/report.json` files.
It refuses mixed eval and benchmark reports, and it also stops on capability mismatch, operation
mismatch, fixture digest mismatch, budget mismatch, or suite version mismatch. Different providers
are expected: each provider becomes a separate row only after the shared comparison context matches.
Markdown starts with claim boundary language and the shared context; JSON, Markdown, and CSV rows
include metric deltas, event counts, budget status, missing evidence, skip reasons, artifact paths,
and input or budget provenance references. The output is stable enough to attach to issues, but it
is not a public leaderboard or a ranking across different tasks or capabilities.

Use `--input-file` when a benchmark result needs to be reproducible from preserved inputs. The
file can contain input fields directly, or an `inputs` object plus metadata. The checked-in
`examples/benchmark-inputs.json` fixture is checkout-safe for the mock provider's `predict`,
`generate`, `transfer`, and `embed` operations; score and policy entries require providers that
advertise those capabilities.

```json
{
  "metadata": {
    "run": "release-smoke"
  },
  "inputs": {
    "prediction_action": {
      "type": "move_to",
      "parameters": {
        "target": { "x": 0.25, "y": 0.5, "z": 0.0 },
        "speed": 1.0
      }
    },
    "prediction_steps": 2,
    "reason_query": "How many objects are tracked?",
    "generation_prompt": "benchmark orbiting cube",
    "generation_duration_seconds": 1.0,
    "transfer_prompt": "benchmark transfer rerender",
    "transfer_width": 320,
    "transfer_height": 180,
    "transfer_fps": 12.0,
    "transfer_clip": {
      "path": "seed-transfer.bin",
      "fps": 8.0,
      "resolution": [160, 90],
      "duration_seconds": 1.0,
      "metadata": { "content_type": "application/octet-stream" }
    },
    "embedding_text": "benchmark cube state",
    "score_info": {
      "pixels": [[[[0.0]]]],
      "goal": [[[0.3, 0.5, 0.0]]],
      "action": [[[0.0, 0.5, 0.0]]]
    },
    "score_action_candidates": [[[[0.0, 0.5, 0.0]], [[0.3, 0.5, 0.0]]]],
    "policy_info": {
      "observation": {
        "state": { "cube": [0.0, 0.5, 0.0] },
        "language": "move the cube"
      },
      "mode": "select_action"
    }
  }
}
```

Omitted fields keep deterministic defaults. A `transfer_clip.path` is resolved relative to the
input JSON file; use `frames_base64` instead of `path` when the clip bytes must be contained
inside the JSON fixture.

Remote media providers can need capability-specific fixtures because generate and transfer exercise
different upstream surfaces. Runway includes separate examples so a host can benchmark each surface
without accidentally reusing a transfer seed for generation:

```bash
uv run worldforge benchmark --provider runway --operation generate \
  --input-file examples/runway-generate-benchmark-inputs.json
uv run worldforge benchmark --provider runway --operation transfer \
  --input-file examples/runway-transfer-benchmark-inputs.json
```

The same provider-operation runner is available from TheWorldHarness:

```bash
uv run --extra harness worldforge-harness --flow benchmark
```

The TUI streams per-sample latency while the run is active, then writes the canonical JSON report
under `.worldforge/reports/` and opens it in the Run Inspector. Treat those reports like CLI
benchmark artifacts: cite numbers only when the JSON behind them is preserved.

Use a budget file when a benchmark run is part of a release gate, regression check, or public
claim. Budget selectors can pin a provider and operation, or omit either field to apply the
threshold to every matching result:

```json
{
  "budgets": [
    {
      "provider": "mock",
      "operation": "generate",
      "min_success_rate": 1.0,
      "max_error_count": 0,
      "max_retry_count": 0,
      "max_average_latency_ms": 250.0,
      "max_p95_latency_ms": 400.0,
      "min_throughput_per_second": 2.0
    }
  ]
}
```

```bash
uv run worldforge benchmark \
  --provider mock \
  --operation generate \
  --iterations 5 \
  --format json \
  --budget-file examples/benchmark-budget.json
```

With `--budget-file`, the command prints both the benchmark report and a gate report. A failing gate
exits non-zero after printing violations such as latency, retry, error-count, success-rate, or
unmatched-budget checks. JSON output contains `benchmark` and `gate` objects; Markdown prints both
reports; CSV prints the gate violation table.

## Budget calibration

Benchmark budgets should be calibrated from preserved baseline reports, not from console memory or
one-off local observations. Generate candidate budget artifacts from one or more saved benchmark
JSON reports:

```bash
uv run worldforge benchmark --preset release-evidence --format json --run-workspace .worldforge
uv run python scripts/calibrate_benchmark_budgets.py \
  --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json \
  --output .worldforge/benchmark-calibration/release-evidence-candidate \
  --machine-class "macos-arm64-local"
```

The calibration command writes:

- `budget-calibration.json`: full provenance, baseline context, source report digests, and diffs.
- `candidate-budgets.json`: a loadable budget file using the existing benchmark budget schema.
- `budget-calibration.md`: the human review report for pull requests or release notes.

Success signal: the candidate budget file loads through the same parser used by
`worldforge benchmark --budget-file`, and every diff row names the provider, operation, old
threshold, candidate threshold, observed baseline, and rationale. The command never edits the
current budget file.

Threshold loosening requires human review. Reviewers should compare the source report digest,
machine class, Python version, command, provider, operation, sample count, input fixture digest,
old threshold, candidate threshold, observed baseline, and rationale before replacing any release
budget file. Budget changes are allowed when they follow an intentional workload change, provider
adapter change, dependency/runtime upgrade, or documented machine-class change. They are not allowed
to mask a regression, create a machine-independent performance claim, or add flaky live-provider
budgets to default CI.

First triage step for a surprising candidate: open `budget-calibration.md`, confirm the source
report digest matches the preserved benchmark JSON, then rerun the exact benchmark command on the
same machine class before changing a release budget.

## Core checkout performance guard

Use the core performance gate to detect regressions in framework paths that should stay cheap in a
clean checkout:

```bash
uv run python scripts/check_core_performance.py \
  --workspace-dir .worldforge/core-performance \
  --output .worldforge/core-performance/core-performance.json
```

The command measures world persistence, benchmark input fixture loading, provider catalog
diagnostics, evidence-bundle creation, and evaluation report rendering against local millisecond
budgets. Success signal: the JSON report has `passed: true`, result rows include measured
`duration_ms` and `budget_ms`, and preserved workspaces include artifact paths for each operation.
First triage step: inspect the failing row, verify the artifact path and changed code path, then fix
the regression before changing budgets. These budgets are checkout-safe regression guards only; they
are not a leaderboard, cross-machine claim, or optional-runtime benchmark.

## Report contents

- per-provider, per-operation success and error counts
- retry totals derived from emitted `ProviderEvent` records
- total wall-clock time and throughput
- average, min/max, p50, and p95 latency
- serialized provider-operation event aggregates for deeper inspection
- optional budget-gate results for release or claim-oriented thresholds

Every JSON and Markdown report includes `claim_boundary` and `metric_semantics` fields. The
benchmark harness is synthetic. It measures operation latency, retries, and throughput for the
selected provider adapter path; it does not score media quality, physical fidelity, safety, or
production load capacity.

## Presets

Named presets bundle a deterministic input fixture, an optional budget file, and a runtime
gate so maintainers can run release-regression workloads without re-deriving inputs and
budgets each time. Five presets ship with the wheel today, grouped into four categories:

| Preset | Category | Providers | Operations | Iterations | Failure tolerance |
| --- | --- | --- | --- | ---: | --- |
| `mock-smoke` | checkout-safe | `mock` | predict, generate, embed | 5 | fail-on-violation |
| `parser-overhead` | checkout-safe | `mock` | predict, reason, generate, transfer, embed | 20 | fail-on-violation |
| `remote-media-dryrun` | remote-media | `cosmos`, `runway` | generate | 1 | skip-when-env-missing |
| `prepared-host` | prepared-host | `leworldmodel`, `lerobot`, `gr00t` | score, policy | 3 | skip-when-env-missing |
| `release-evidence` | release | `mock` | predict, reason, generate, transfer, embed | 10 | fail-on-violation |

List, inspect, and run presets through the existing `benchmark` subcommand:

```bash
uv run worldforge benchmark --list-presets
uv run worldforge benchmark --show-preset release-evidence
uv run worldforge benchmark --preset mock-smoke
uv run worldforge benchmark --preset release-evidence --format json --run-workspace .worldforge
```

`--preset` overrides `--provider`, `--operation`, `--iterations`, `--concurrency`, `--input-file`,
and `--budget-file`. The `--format` and `--run-workspace` flags still apply.

### Failure tolerance and skip semantics

- **fail-on-violation** (`mock-smoke`, `parser-overhead`, `release-evidence`). The preset runs
  unconditionally; budget violations exit non-zero with the standard violation table that
  carries provider, operation, metric, observed value, threshold, and budget selector.
- **skip-when-env-missing** (`remote-media-dryrun`, `prepared-host`). Each gated preset checks
  every provider runtime profile it requires through
  `worldforge.testing.runtime_profiles.provider_profile_skip_reason`. If no eligible runtime
  is configured the preset prints a typed reason and exits 0; release CI treats this as
  "evidence not available on this host" rather than a failure.

### Adding a preset

`BenchmarkPreset` is a frozen dataclass under `worldforge.benchmark_presets`. Add a new entry
to the `_BENCHMARK_PRESETS` tuple, ship the matching `inputs-*.json` and (optionally)
`budget-*.json` next to it under `src/worldforge/benchmark_presets/_data/`, and add coverage
in `tests/test_benchmark_presets.py`. Keep the inputs deterministic and small; binary clip
frames belong inside the JSON via `frames_base64` rather than as separate media files.

## Provenance envelope

Reports built through `ProviderBenchmarkHarness.run()` and the `worldforge benchmark` CLI carry
a `provenance` envelope (`schema_version: 2`) so a claim can be reproduced, audited, or cited
without console logs:

| Field | Description |
| --- | --- |
| `schema_version` | Envelope schema version (currently `2`). |
| `kind` | `"benchmark"`. |
| `suite_id`, `suite_version` | `"benchmark"` and the contract version (e.g. `benchmark:1`). |
| `worldforge_version` | Package version that produced the report. |
| `created_at` | UTC ISO timestamp. |
| `command` | The command argv vector when produced through the CLI. |
| `providers`, `capabilities` | Providers exercised and operations they covered. |
| `runtime_manifests` | Provider runtime manifest references when available. |
| `input_digest`, `result_digest` | Deterministic `sha256:<hex>` digests of inputs and results. |
| `budget_file` | `path`, `sha256:<hex>`, and `metadata` summary when a budget gate ran. |
| `event_count` | Sum of `request_count` across emitted `ProviderEvent` records. |
| `claim_boundary`, `metric_semantics` | Mirrors the report-level claim text. |
| `notes` | Optional free-form note. |

Cite a benchmark number by attaching the envelope (paste the JSON `provenance` block or the
Markdown provenance section) alongside the report in any issue, release note, or evidence
bundle. The envelope intentionally duplicates `claim_boundary` and `metric_semantics` so a
single block carries the full provenance for a claim.

### Migration

Previous reports omitted `provenance`. The CSV renderer, `claim_boundary`, `metric_semantics`,
`run_metadata`, and `results` fields are unchanged; `run_metadata.input_file` and
`run_metadata.budget_file` continue to expose the raw hex digest used by earlier tooling. New
consumers should prefer the envelope `input_digest`, `result_digest`, and `budget_file` fields,
which carry `sha256:<hex>` digests and the `runtime_manifests` map.
