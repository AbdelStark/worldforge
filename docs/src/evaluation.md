# Evaluation

WorldForge ships five built-in suites:

- `generation`: prompt-only and image-conditioned video generation checks
- `physics`: deterministic object stability and action-response checks
- `planning`: relocation, neighbor placement, swap, and spawn execution validation over the predict-driven planner
- `reasoning`: scene-count and scene-identity checks for providers that implement `reason()`
- `transfer`: prompt-guided and reference-guided video transfer checks

## Python

```python
from worldforge.evaluation import EvaluationSuite

suite = EvaluationSuite.from_builtin("planning")
report = suite.run_report(["mock"], forge=forge)

print(report.results[0].passed)
print(report.to_json())
```

## CLI

```bash
uv run worldforge eval --suite generation --provider mock
uv run worldforge eval --suite physics --provider mock
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge eval --suite reasoning --provider mock --format csv
uv run worldforge eval --suite transfer --provider mock
```

Repeat `--provider` to compare multiple registered providers in one report.

Use `--run-workspace` when an evaluation should leave a manifest-backed evidence bundle:

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
```

The run workspace stores `run_manifest.json`, JSON/Markdown/CSV reports, and a result summary under
`.worldforge/runs/<run-id>/`.

When a suite has failures, the JSON and Markdown reports include a compact failure gallery. The
gallery is also exported through `report.artifacts()` as `failure_gallery.json` and
`failure_gallery.md` for issue attachments:

```python
gallery = report.failure_gallery()
print(gallery.to_markdown())
```

Each gallery case records a fixture id such as `evaluation:planning:object-relocation`, the
provider, scenario, score, expected contract note, observed summary, small metrics preview, and
triage steps. Metric previews are sanitized: secret-shaped values are redacted, signed URL query
strings are stripped, host-local paths are replaced, and tensor-like arrays are summarized instead
of copied raw.

To package one or more preserved evaluation or benchmark runs for issue triage or release review,
generate a checkout-safe evidence bundle:

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --preset mock-smoke --run-workspace .worldforge
uv run worldforge runs bundle <run-id>
uv run python scripts/generate_evidence_bundle.py --workspace-dir .worldforge
```

The bundle defaults to `.worldforge/evidence-bundles/<timestamp>/` and writes
`evidence_manifest.json` plus `summary.md`. The manifest records copied reports, run manifests,
event logs, preset input and budget files, fixture digests, SHA-256 file digests, and
`safe_to_attach` flags. Unsupported binary artifacts, host-local absolute paths, signed URLs, and
secret-like text are excluded or marked local-only by default.

Use `worldforge runs bundle <run-id>` for a smaller issue-ready export of one run. It writes
`issue.md` beside the digest manifest and summary, and the printed issue template includes the
command, expected signal, observed failure, safe-to-attach notes, and first triage step.

The same built-in suites are available from TheWorldHarness. Launch
`uv run --extra harness worldforge-harness --flow eval`, pick a suite and provider, and the TUI
writes the canonical JSON report under `.worldforge/reports/` before opening the Run Inspector.
Capability mismatches remain `WorldForgeError` failures; the TUI surfaces the message instead of
silently skipping the suite.

## Report formats

- Markdown: provenance section, provider summary table, scenario-level detail table
- JSON: `suite_id`, `suite`, `claim_boundary`, `metric_semantics`, `provider_summaries`,
  scenario `results`, a `provenance` envelope, and `failure_gallery` when failed scenarios exist
- CSV: one row per provider/scenario pair with serialized metrics payloads (envelope omitted
  to keep the table import-compatible with prior releases)
- Failure gallery JSON/Markdown: representative failed cases with fixture ids, expected contract
  notes, sanitized metrics previews, and first triage steps

Every JSON and Markdown report carries an explicit claim boundary. Built-in suites are
deterministic adapter contract checks; their scores are not physical-fidelity, media-quality,
safety, or real robot performance claims. Failure galleries follow the same boundary: they are for
issue triage and provider-review debugging, not provider quality ranking.

## Provenance envelope

Reports built through `EvaluationSuite.run_report()` and the `worldforge eval` CLI carry a
`provenance` envelope (`schema_version: 2`) so claims, regressions, and release evidence can be
audited without console logs:

| Field | Description |
| --- | --- |
| `schema_version` | Envelope schema version (currently `2`). |
| `kind` | `"evaluation"`. |
| `suite_id`, `suite_version` | Suite identifier and contract version (e.g. `evaluation:1`). |
| `worldforge_version` | Package version that produced the report. |
| `created_at` | UTC ISO timestamp. |
| `command` | The command argv vector when produced through the CLI. |
| `providers`, `capabilities` | Providers exercised and capabilities they covered. |
| `runtime_manifests` | Provider runtime manifest references when available. |
| `input_digest`, `result_digest` | Deterministic `sha256:<hex>` digests of inputs and results. |
| `event_count` | Emitted `ProviderEvent` count. |
| `claim_boundary`, `metric_semantics` | Mirrors the report-level claim text. |
| `notes` | Optional free-form note. |

To cite a result in an issue or release evidence, paste the `provenance` block from the JSON
report (or the bullet list from Markdown). It carries every field a reviewer needs to map the
claim back to the WorldForge version, suite contract, and input fixture.

### Migration

Previous reports omitted `provenance`. The CSV renderer and the existing `suite_id`, `suite`,
`claim_boundary`, `metric_semantics`, `provider_summaries`, and `results` keys are unchanged.
Tools that consume the JSON output should treat `provenance` as optional and fall back to the
existing fields when re-rendering historical reports.

## Capability checks

Each suite declares the provider capabilities it needs. For example:

- `generation` requires `generate`
- `physics` and `planning` require `predict`
- `reasoning` requires `reason`
- `transfer` requires `transfer`

WorldForge raises `WorldForgeError` when a caller asks a provider to run a suite it cannot satisfy.
