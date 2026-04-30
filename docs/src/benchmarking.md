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
It refuses mixed eval and benchmark reports. Markdown includes each run command, provider,
operation, UTC date, report artifact paths, and input or budget provenance references. JSON and CSV
are stable enough to attach to issues.

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
