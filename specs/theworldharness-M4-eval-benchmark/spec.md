# Milestone M4 — Eval + Benchmark

## Status
Implemented · 2026-04-21

## Outcome (one sentence)
A user of TheWorldHarness can run any built-in evaluation suite or benchmark against any registered provider from the TUI, watch honest live progress, and land the result in `RunInspectorScreen` with JSON / Markdown / CSV export that matches the `worldforge` CLI byte-for-byte.

## Why this milestone
TheWorldHarness is the front face of WorldForge and, per the roadmap vision ([`../../.codex/skills/tui-development/references/roadmap.md`](../../.codex/skills/tui-development/references/roadmap.md) §1), its job is to leave a user with the integration pattern in their head. Until M4, the harness only exercises provider `predict` events (from M3). Evaluation suites and the benchmark harness are two of the most visible public surfaces of WorldForge, and they are where users will look to answer "what can this provider actually do" and "how fast is it". If those paths are only reachable through the CLI, the TUI is by definition incomplete as an integration reference.

M4 closes that gap under the claim-hygiene discipline the evaluation-benchmarking skill codifies ([`../../.codex/skills/evaluation-benchmarking/SKILL.md`](../../.codex/skills/evaluation-benchmarking/SKILL.md)): suites measure adapter behavior (not realism), benchmarks measure latency / retries / throughput (not quality), every externally cited number must be preserved to disk, and capability mismatches are a hard `WorldForgeError` that the TUI must never silently swallow. The M4 screens must surface — not sand off — those invariants.

## In scope
- `EvalScreen`: pick a built-in suite (`generation`, `physics`, `planning`, `reasoning`, `transfer`) × one or more providers that advertise the suite's required capabilities; mismatch is a hard toast pointing the user at `ProvidersScreen` (cross-reference M3 capability matrix).
- `BenchmarkScreen`: pick a provider × one or more operations (from `BENCHMARKABLE_OPERATIONS`) × iterations × format; a live `ProgressBar` with rolling median and p95 latency pulled from the run-so-far.
- Runs land in `RunInspectorScreen` (from M1) as a `HarnessRun` whose metrics pane reflects `EvaluationReport` / `BenchmarkReport` fields; JSON / Markdown / CSV preview pane switches format *in place* without rerunning.
- Export is unified: both screens write a JSON report to `.worldforge/reports/<suite-or-benchmark>-<timestamp>-<run-id>.json`, the Markdown and CSV variants are regeneratable from the JSON, and a success toast prints the absolute path so the file backing any cited number is discoverable.
- Both workflows are reachable from the command palette (Ctrl+P) as `"Run eval suite …"` and `"Run benchmark …"` — feature exists iff it is palette-searchable per roadmap §5.
- Cancellation: `Esc` cancels the active worker; the partial run is still visible in `RunInspectorScreen` with a "Cancelled" status.

## Out of scope (explicit)
- Live optional-runtime evals / benchmarks against CUDA / TensorRT / real checkpoints — those belong to `optional-runtime-smokes` and stay host-owned.
- Multi-run comparison views (side-by-side diffing of two benchmark reports, or tracking a "last-good" baseline) — listed under Open questions; not required to call M4 done.
- Auto-publishing reports to the docs site — explicit non-goal per roadmap §11.
- Benchmark budget gate configuration from the TUI (the CLI `--budget-file` path is the source of truth) — may be layered on later; the TUI shows gate outcomes if a budget file is selected, but editing is out of scope.
- Custom / user-defined suites beyond the five built-ins — defer until there is a registered discovery hook on `EvaluationSuite`.

## User stories
1. As a researcher evaluating a new deterministic provider, I press `e` on `HomeScreen`, pick the `planning` suite and `mock`, and within a few seconds I see a pass verdict, per-scenario metrics, and a preserved JSON report path — so that I can cite "5/5 scenarios passed" in a PR with a file behind it.
2. As a researcher comparing adapter latency, I open `BenchmarkScreen`, pick `mock` × `predict` × 20 iterations, and watch the rolling median / p95 update live as iterations complete — so that I can spot variance before the run finishes and export the JSON at the end.
3. As a newcomer, I try to run the `generation` suite against `leworldmodel`, and I get a hard, high-contrast error toast explaining that `leworldmodel` does not advertise `generate`, plus a one-key action to jump to `ProvidersScreen` — so that the capability model teaches me instead of hiding.
4. As a reviewer reading a PR, I receive a run ID plus a path under `.worldforge/reports/` — so that I can `jq` / `diff` / re-render the exact numbers without rerunning anything.

## Acceptance criteria
- [ ] `EvalScreen` launches the selected suite through `EvaluationSuite.run_report(providers=..., forge=...)` inside a `@work(thread=True, group="eval", exclusive=True)` worker; the UI never blocks.
- [ ] `BenchmarkScreen` launches through `ProviderBenchmarkHarness(forge=forge).run(...)` inside a `@work(thread=True, group="benchmark", exclusive=True)` worker; iteration samples stream to a `RichLog` via `call_from_thread`.
- [ ] Capability mismatch raises `WorldForgeError` from the worker. The screen's exception handler catches it *only* to render a `$error`-colored toast and post a `CapabilityMismatch` message; the error is **not** swallowed, not converted to a generic log line, and not allowed to leave the worker silently.
- [ ] The toast copy names the missing capability and the provider, and offers a one-key ("p") jump to `ProvidersScreen` with the offending provider pre-selected.
- [ ] Every completed run writes a JSON report to `.worldforge/reports/<kind>-<timestamp>-<run-id>.json`, where `<kind>` is `eval-<suite-id>` or `benchmark`. The Markdown and CSV outputs shown in the preview pane come from the same `EvaluationReport.artifacts()` / benchmark report rendering path the CLI uses — one source of truth, not a parallel TUI renderer.
- [ ] After a successful run, a `$success` toast shows `"Report saved: <absolute path>"` and includes a "copy path" binding.
- [ ] `RunInspectorScreen` can show both eval and benchmark results; switching `report_format` between `json` / `markdown` / `csv` reflows the preview pane without rerunning the suite.
- [ ] `Esc` during a run cancels the worker via `self.workers.cancel_group("eval"|"benchmark")`; the partial run surface is labelled `"Cancelled"` in the transcript and still writes whatever JSON was already assembled (empty-results JSON is acceptable and documented).
- [ ] Both screens expose their primary action via (a) a screen binding shown in the footer, (b) a command palette entry, and (c) a click target on the form — mouse + keyboard parity per roadmap §5.
- [ ] A Pilot test drives a capability-mismatch attempt and asserts the toast contains the `WorldForgeError` message text verbatim (proof that nothing is swallowed).
- [ ] A Pilot test runs `planning` × `mock` end-to-end and asserts (i) `RunInspectorScreen` is active after success, (ii) the saved JSON path exists on disk, (iii) loading that JSON round-trips to the same `EvaluationReport.to_dict()` shape.
- [ ] Snapshot tests cover: `EvalScreen` idle, `EvalScreen` mid-run, `EvalScreen` verdict-pass, `EvalScreen` verdict-fail, `BenchmarkScreen` live metrics, `RunInspectorScreen` with a JSON export preview — each pinned at `terminal_size=(120, 40)`.
- [ ] Coverage gate (`uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90`) passes with the new screens and tests.

## Non-functional requirements
- **Honest progress.** `ProgressBar(total=None)` until the total iteration count is known (known at start for benchmark, known at start for eval = `len(scenarios) * len(providers)`), then switch to a determinate bar. No looping spinners when the worker is idle or cancelled.
- **One renderer.** The JSON / Markdown / CSV produced by the TUI is byte-identical to the CLI's — shared code path (`EvaluationReport.to_json` / `.to_markdown` / `.to_csv`, and the matching benchmark report methods). The TUI may pretty-print its own preview pane, but the *saved* artifact and the *copied* artifact must go through the canonical renderer.
- **Theming parity.** `EvalScreen` and `BenchmarkScreen` render correctly on `worldforge-dark` and `worldforge-light`. No hex literals anywhere in the new TCSS — semantic variables only (`$success` for pass, `$error` for fail and for capability-mismatch toasts, `$accent` for the selected format tab, `$warning` for cancelled state).
- **No event-loop block.** A slow-mock provider (e.g., 50 ms per call × 100 iterations) must not freeze the UI; the benchmark progress bar must update between iterations.
- **Empty-state legibility.** Before any suite / provider is chosen, the screen shows a centred `Static` with the next action: `"No suite selected — press [b]s[/] to pick one"` / `"No provider selected — press [b]p[/]"`.

## Open questions
- Should benchmark preset configurations (a named tuple of `{provider, operation, iterations, concurrency, format}`) be user-savable to `.worldforge/benchmark-presets.json` and exposed as dynamic palette entries? Needed for M5 polish; not required to call M4 done.
- Should eval verdicts pin a "last good" baseline so regressions surface in the TUI verdict banner? Would require a `.worldforge/reports/index.json` convention; defer until after M4 ships.
- Should `RunInspectorScreen` gain a small diff view when the user opens two consecutive benchmark reports? Potentially M5.
- Should the TUI allow pointing `--budget-file` at an existing JSON to display benchmark gate violations inline, or is that strictly a CLI concern? Lean toward read-only display in M5.
- When a cancellation produces an empty `EvaluationReport`, should the JSON be written at all, or only a `.cancelled` marker? Current spec writes the empty report for traceability; revisit if noisy.
