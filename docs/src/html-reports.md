# Static HTML Reports

WorldForge can export evaluation reports, benchmark reports, run
comparisons, and issue-ready bundles as **self-contained, sanitized HTML
documents**. The HTML form is for cases where a single static file needs
to land in an issue body, a Slack post, or a release-review email
without forcing the reader to install WorldForge — JSON and Markdown are
still preferred for machine consumption and code review.

## Open-file workflow

```bash
# Eval report → HTML.
uv run worldforge eval --suite planning --provider mock --format html > report.html

# Benchmark report → HTML.
uv run worldforge benchmark --provider mock --operation predict \
    --iterations 5 --format html > benchmark.html

# Comparison across two preserved runs → HTML.
uv run worldforge runs compare path/to/run_a path/to/run_b \
    --format html --output review/compare.html

# Baseline-vs-candidate regression report → HTML.
uv run worldforge runs compare path/to/baseline path/to/candidate \
    --mode regression --format html --output review/regression.html

# Issue-ready bundle for one preserved run.
uv run worldforge runs bundle <run-id> --workspace-dir .worldforge \
    --format html > issue.html
```

Open the resulting file in any browser; it is self-contained — no
external CSS, no JavaScript, no network-loaded assets, no anchor links.
Drop it in an issue attachment, attach to a release-review email, or
preview alongside the JSON/Markdown counterparts under
`<workspace>/issue-bundles/<run-id>/`.

`worldforge runs bundle` always writes both `summary.html` and
`issue.html` next to the existing `summary.md` and `issue.md` files;
selecting `--format html` simply prints `issue.html` to stdout.

For a checkout-safe non-developer review package that combines evaluation,
benchmark, world-diff, and issue-bundle evidence into one static artifact set:

```bash
uv run python scripts/demo_showcases.py run non-developer-evidence-review \
  --workspace-dir .worldforge/demo-showcases
```

Attach the generated `review-package.html`, `review-package.json`, and
`review-package.md` only after checking the `share_policy` rows. Relative safe
artifacts are linked for local inspection; host-local paths, signed URLs, and
raw provider payloads are marked `local-only` or excluded and should not be
uploaded to issues or release review.

## When to use HTML

- The audience is non-developer (a release-review reader, a partner) and
  needs a rendered table without installing tools.
- A single artifact has to be attached and viewed offline.
- The report needs to be shared in a context where Markdown rendering is
  unreliable (an internal wiki that strips tables, an email client).

## When not to use HTML

- The reader is human, technical, and reading inside GitHub or the
  terminal — Markdown is shorter, diff-friendly, and renders the same
  tables.
- The reader is a script — JSON or CSV are stable contracts; HTML is
  a presentation format with a layout that may evolve between releases.
- The output needs to be diffed across runs in version control —
  Markdown is a stable text format; HTML wraps additional markup.

## Limitations

- HTML output is presentation-only. The structure may change between
  WorldForge releases as renderers improve. Treat JSON as the durable
  contract; HTML is a render of a JSON payload.
- The renderer never emits `<a href="…">` anchors. URLs that appear in
  manifest fields are escaped as plain text. This is deliberate — a
  malformed manifest cannot inject an exfiltration link or an XSS
  payload into a shared report.
- The HTML reader will not download or include external assets even if
  the source manifest references them. Use `worldforge runs bundle` to
  package the safe artifacts alongside the HTML when sharing.
- Unsafe artifacts (oversized files, suffixes outside the safe-attach
  list, host-local paths) are listed but not embedded. The issue-bundle
  HTML surfaces a warning banner when the bundle's `safe_to_attach`
  flag is `false`.

## Sanitization guarantees

- All user-supplied text (provider names, commands, failure summaries,
  validation errors, run identifiers) is escaped via `html.escape` with
  `quote=True` before insertion. A provider literally named `<script>`
  renders as `&lt;script&gt;` in the document.
- The renderer emits `<script>` tags in **zero** outputs. Tests assert
  this on every artifact kind.
- The renderer emits `<a>` tags in **zero** outputs. Tests assert this
  for the issue bundle path.
- The HTML document declares `lang="en"` and uses inline styles only;
  no `<link rel="stylesheet">`, no `<script src="…">`.

## Public Python surface

The renderer functions are re-exported on the top-level package:

```python
from worldforge import (
    render_evaluation_html,
    render_benchmark_html,
    render_comparison_html,
    render_evidence_bundle_html,
    render_issue_bundle_html,
)

# Or via `EvaluationReport.to_html()` / `BenchmarkReport.to_html()`
# and the `artifacts()` dict on each report class.
```

`HTML_REPORT_SCHEMA_VERSION` is exposed so callers can branch on
renderer-version drift; today it is `1`.

## Renderer Extension Points

External suites and host applications can register safe renderers without
patching WorldForge internals. A renderer declares its artifact family,
output format, media type, supported schema ids, and whether its output is
safe to attach or local-only. Registration accepts callable renderers only;
WorldForge does not load renderer plugins from arbitrary files.

```python
from worldforge import ReportRenderer, register_report_renderer, render_report_artifact


register_report_renderer(
    ReportRenderer(
        artifact_family="comparison",
        output_format="summary",
        media_type="text/plain",
        supported_schemas=("comparison:2",),
        safe_to_attach=True,
        render=lambda payload: f"runs={payload['run_count']}",
    )
)

artifact = render_report_artifact("comparison", "summary", {"run_count": 2})
assert artifact.safe_to_attach is True
```

Built-in renderer families include `comparison`, `evidence-bundle`, and
`issue-bundle`. Duplicate family/format registrations fail unless the caller
explicitly replaces a renderer. Safe-to-attach renderer output is validated for
secret-like material before it can be returned.
