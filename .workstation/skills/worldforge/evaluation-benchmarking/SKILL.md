---
name: evaluation-benchmarking
description: "Use for WorldForge evaluation suites, benchmark harness changes, benchmark input fixtures, budget gates, report rendering, metrics semantics, and any claims based on benchmark or evaluation output. Keeps benchmark/eval artifacts deterministic, coherent, and claim-bounded."
---

# Evaluation And Benchmarking

## Ground Rules

- Built-in eval suites are deterministic contract harnesses, not physical-fidelity or media-quality evidence.
- Benchmark direct provider operations only: `predict`, `embed`, `score`, and `policy`.
- `plan()` is a WorldForge facade workflow. Do not route benchmark `score` or `policy` through it.
- Preserve `BenchmarkBudget` non-zero exit behavior on violations.
- Preserve claim-boundary and metric-semantics metadata in JSON, Markdown, and CSV renderers.
- Treat benchmark/eval output as evidence only when the fixture, command, provider surface, and
  renderer semantics are all current and inspectable.

## Workflow

1. Read `src/worldforge/evaluation/suites.py` for eval changes or `src/worldforge/benchmark.py` for benchmark changes.
2. Validate inputs eagerly through `BenchmarkInputs` and `load_benchmark_inputs(...)`; reject unknown keys and non-finite metrics.
3. Keep `examples/benchmark-inputs.json` and `examples/benchmark-budget.json` reproducible and checkout-safe.
4. Keep score and policy payloads JSON-native; for provider-native tensors or arrays, preview type and shape rather than forcing raw encoding.
5. If operation surfaces or CLI text change, update help snapshots, harness diagnostics, README, `docs/src/benchmarking.md`, `docs/src/api/python.md`, `docs/src/playbooks.md`, and changelog together.
6. Test direct operation behavior, input parsing, budget pass/fail paths, and renderer output.

## Definition Of Done

- The changed suite or benchmark path has focused tests for success and failure behavior.
- Rendered artifacts remain JSON-native and internally coherent before Markdown/CSV output.
- Claims in README/docs/changelog match the actual command and provider used.
- The final validation includes the focused tests plus docs/provider checks when public text changed.

## Metric Semantics

- Latency is process-local wall-clock timing for successful samples.
- Retry counts come from emitted `ProviderEvent` records.
- Throughput is successful samples over elapsed time.
- Event rows can aggregate attempts; sum `request_count` when reporting actual request volume.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| `--input-file` rejects fixture | Unknown key or non-JSON payload | Match allowed `BenchmarkInputs` keys and JSON-native values |
| Budget gate exits non-zero | Threshold violation | Preserve artifact, inspect report, adjust code or documented budget with evidence |
| CLI help snapshot fails | Operation/help text changed | Update `tests/test_cli_help_snapshots.py` intentionally |
