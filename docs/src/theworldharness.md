# TheWorldHarness

TheWorldHarness is an optional Textual TUI for running WorldForge integration flows as visible,
inspectable traces. It is the default integration reference for how provider surfaces, planning,
execution, persistence, diagnostics, benchmarks, and event inspection fit together.

It is a local tool. It does not require optional ML runtimes unless a selected flow explicitly
does, and the current flows use deterministic checkout-safe paths.

The real robotics showcase also uses the Textual surface, but it is launched through
`scripts/robotics-showcase` rather than the checkout-safe harness flow. That command runs the real
LeRobot policy plus real LeWorldModel checkpoint path first, then opens a standalone report with the
pipeline, runtime metrics, staged reveal, illustrative robot-arm animation, candidate cost
landscape, provider events, and tabletop replay. Pass `--tui-stage-delay <seconds>` to tune the
reveal pace or `--no-tui` to keep the plain terminal report.

## Install Boundary

Textual is optional. The base package keeps `httpx` as its only runtime dependency.

```bash
uv run --extra harness worldforge-harness
uv run --extra harness worldforge-harness --flow lerobot
uv run --extra harness worldforge-harness --flow diagnostics
uv run --extra harness worldforge-harness --flow eval
uv run --extra harness worldforge-harness --flow benchmark
uv run worldforge harness --list
uv run worldforge harness --list --format json
uv run worldforge harness --connectors
uv run worldforge harness --connectors --format json
```

Installed package:

```bash
pip install "worldforge-ai[harness]"
worldforge-harness
```

Without the `harness` extra, metadata commands still work:

```bash
uv run worldforge harness --list
uv run worldforge harness --list --format json
uv run worldforge harness --connectors --format json
uv run worldforge provider workbench mock
uv run worldforge provider workbench runway --format json
```

Launching the TUI without Textual exits with an install hint instead of importing optional
dependencies at package import time.

## Current Flows

| Flow | Provider surface | What it visualizes |
| --- | --- | --- |
| `leworldmodel` | `score` | Deterministic LeWorldModel-shaped cost runtime, candidate scoring, score planning, execution, persistence, reload, provider events. |
| `lerobot` | `policy` plus score provider | Deterministic LeRobot-shaped policy, action translation, policy candidate ranking, execution, persistence, reload, provider events. |
| `diagnostics` | provider catalog plus benchmark harness | `doctor()` provider scan, registered/unregistered provider status, mock benchmark matrix across predict/reason/generate/transfer/embed, latency/throughput comparison, provider events. |

## Provider Connector Workspace

The Providers screen and `worldforge harness --connectors --format json` use the same
Textual-free readiness model. Each known provider is grouped as `configured`,
`missing_credentials`, `missing_dependency`, `unhealthy`, or `scaffold`, with value-free required
environment names, optional runtime dependency names, a first smoke command, and triage steps.

This surface intentionally reports presence and status only. It does not print environment values,
tokens, endpoints, checkpoint paths, or constructor-provided secrets.

## What The Interface Shows

The harness now exposes the main WorldForge surfaces directly:

- Home: jump cards plus recent worlds and preserved reports.
- Worlds: create, edit, save, fork, delete, and preview local JSON worlds through `WorldForge`.
- Providers: registered-provider capability matrix, health details, and cancellable `mock.predict`.
- Eval: built-in deterministic suites with capability errors surfaced as hard toasts.
- Benchmark: provider-operation latency, retry, and throughput runs with live samples.
- Run Inspector: timeline, metrics, transcript, and export preview for flows and reports.

Flow and report views are rendered from the same structured `HarnessRun` object used in tests.
The provider, eval, and benchmark screens call the same Python APIs as the CLI; report artifacts
use the canonical JSON / Markdown / CSV renderers.

The diagnostics, eval, and benchmark screens map directly to non-TUI commands:

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider list
uv run worldforge provider workbench mock
uv run worldforge benchmark --provider mock --iterations 2 --format json
uv run worldforge eval --suite planning --provider mock --format json
```

## Provider Workbench

`worldforge provider workbench <provider>` is the checkout-safe adapter author loop behind the
harness provider development workflow. It does not import Textual and does not make live provider
calls unless `--live` is passed explicitly. The default report is designed to paste into GitHub
issues: provider profile, required capability conformance helpers, fixture JSON status, docs/catalog
drift hints, redaction-safe provider event status, and exact follow-up commands.

```bash
uv run worldforge provider workbench mock
uv run worldforge provider workbench runway --format json
uv run worldforge provider workbench runway --live
```

For deterministic local providers such as `mock`, the workbench invokes the advertised capability
helpers. For HTTP adapters it validates matching `tests/fixtures/providers/<provider>_*.json`
playback files and lists the capability helpers that the provider test module must cover. For
host-owned local runtimes such as LeRobot and LeWorldModel, the default path inspects profile,
health, docs, and fixtures while leaving injected-runtime/live smoke execution to prepared hosts.
Run `uv run python scripts/generate_provider_docs.py --check` before opening a provider PR so
profile metadata and generated catalog tables stay in sync.

Completed checkout-safe flows also preserve a sanitized run workspace:

```text
.worldforge/runs/<run-id>/
|-- run_manifest.json
|-- inputs/
|-- results/
|-- reports/
|-- artifacts/
`-- logs/
```

Run IDs are UTC-sortable and file-safe (`YYYYMMDDTHHMMSSZ-xxxxxxxx`). The manifest records the
command, provider surface, status, input summary, result summary, event count, and relative artifact
paths. It intentionally stores summaries and report renderings, not credentials, raw signed URLs, or
provider-owned private data.

The CLI can write the same layout for evaluation and benchmark runs:

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --provider mock --operation predict --run-workspace .worldforge
uv run worldforge runs list
uv run worldforge runs compare .worldforge/runs/<run-a> .worldforge/runs/<run-b>
uv run worldforge runs cleanup --keep 20
```

Completed eval and benchmark TUI screens still write JSON under `.worldforge/reports/` relative to
the active state directory for the Home screen and `Ctrl+P` recent-report index. Use the run
workspace when a full issue attachment needs manifest, reports, logs, and result summaries together.
Use `runs compare --format json|markdown|csv` to export attachment-safe comparisons across
preserved eval runs or preserved benchmark runs.

## Interface Contract

The TUI is intentionally separated from the rest of the project:

| Module | Dependency boundary |
| --- | --- |
| `worldforge.harness.models` | Dataclasses only; no Textual import. |
| `worldforge.harness.flows` | Runs packaged demos and builds timeline, metrics, and transcript data; no Textual import. |
| `worldforge.harness.cli` | Lists flows without Textual; imports the TUI only when launching it. |
| `worldforge.harness.tui` | The only Textual-dependent module. |

The harness does not replace the Python APIs or command-line demos. It makes the same flows
observable: selected candidates, costs, action paths, saved world ids, final object positions,
provider health, benchmark latency, benchmark throughput, and provider event phases.

## Interaction Model

- `r`: run the selected flow.
- `1`: select LeWorldModel score planning.
- `2`: select LeRobot policy-plus-score planning.
- `3`: select provider diagnostics and benchmark comparison.
- `g w`: jump to Worlds.
- `g p`: jump to Providers.
- `g e`: jump to Eval.
- `g b`: jump to Benchmark.
- `Ctrl+P`: search static commands plus worlds, providers, and recent report files.
- `Ctrl+T`: cycle `worldforge-dark`, `worldforge-light`, and `worldforge-high-contrast`.
- `q`: quit.

Each run reveals stages through a timeline, then fills the inspector and transcript panes from the
same structured `HarnessRun` data used by tests.

## Themes

The harness registers three themes:

- `worldforge-dark`: default dark workspace.
- `worldforge-light`: light-terminal variant.
- `worldforge-high-contrast`: higher-contrast variant for dense screens and reduced-colour
  terminals.

Widget CSS uses semantic tokens only; raw colour values live in `worldforge.harness.theme`.

## Screenshot Refresh

The README image is regenerated from a deterministic harness state. The tracked refresh command is:

```bash
scripts/regen-harness-screenshot.sh
```

It seeds a local screenshot state directory, drives the providers screen through Textual's test
harness, exports SVG, and renders the README PNG with `rsvg-convert`.

## Roadmap

TheWorldHarness is evolving from the read-only demo viewer described above into the project's
front-door interactive workspace — keyboard-first, command-palette-driven, and the canonical
example of how to compose WorldForge from Python. The work is broken into six milestones
(M0–M5), each with a published spec triad (`spec.md` + `plan.md` + `tasks.md`) under
[`specs/`](https://github.com/AbdelStark/worldforge/tree/main/specs):

| Milestone | What it adds |
| --- | --- |
| [M0 — Theme + chrome reset](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M0-theme-chrome) | Registered light/dark themes, semantic CSS variables, header clock and breadcrumb. |
| [M1 — Screen architecture](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M1-screen-architecture) | App split into named `Screen`s, `push_screen` navigation, `?` help overlay, `Ctrl+P` system commands. |
| [M2 — Worlds CRUD](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M2-worlds-crud) | Create / edit / save / fork / delete worlds entirely from the TUI through the public `WorldForge` API. |
| [M3 — Live providers](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M3-live-providers) | `ProvidersScreen` with capability matrix and one real provider call streamed through a worker; `Esc` cancels. |
| [M4 — Eval + Benchmark](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M4-eval-benchmark) | `EvalScreen` and `BenchmarkScreen`; capability mismatch as a hard toast; reports preserved to disk and exportable. |
| [M5 — Polish + showcase](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M5-polish-showcase) | High-contrast theme, dynamic command-palette provider, recent items, screenshot export matrix, README screenshot refresh. |

The intent and design language behind these milestones are summarized in the public
[roadmap](./roadmap.md).
