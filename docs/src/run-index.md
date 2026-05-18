# Run Artifact Index

`worldforge runs index` walks `<workspace-dir>/runs/` read-only and emits a
sanitized summary of every preserved run workspace. The index is the
companion to `worldforge runs list` for hosts with many preserved runs:
filters narrow the view by provider, capability, status, date range, or
safe-artifact type, and three output formats (JSON, Markdown, CSV) make
attaching evidence to issues, pasting into release notes, or piping into
spreadsheets straightforward.

## When to use it

- You have dozens or hundreds of preserved run workspaces and need to find
  which ones match a specific provider, capability, or status.
- You want a single safe-to-attach artifact summarizing a release window — a
  Markdown table for the PR body, a CSV for triage spreadsheets, JSON for
  scripted post-processing.
- You want to surface stale or corrupted run directories before running
  `worldforge runs cleanup`.

## When not to use it

- You only have one or two preserved runs — `worldforge runs list` is
  simpler.
- You need the contents of a single run rather than a summary across runs —
  use `worldforge runs bundle <run-id>` instead.
- You need a long-running daemon, multi-host index, or shared database.
  WorldForge intentionally has none of those; the indexer re-walks the
  filesystem on every call and never persists its own state.

## Quick reference

```bash
# Default JSON to stdout.
uv run worldforge runs index --workspace-dir .worldforge

# Markdown table for an issue body.
uv run worldforge runs index --workspace-dir .worldforge --format markdown

# CSV for triage spreadsheets, written to a file.
uv run worldforge runs index --workspace-dir .worldforge \
    --format csv --output review/runs.csv

# Filter to failed cosmos runs from the last week.
uv run worldforge runs index --workspace-dir .worldforge \
    --provider cosmos --status failed --created-from 2026-04-29
```

All filters are optional and combine with AND semantics. Provider matches
are substring + case-insensitive; capability, status, and artifact-type
matches are exact.

## Output shape

Every format includes the same fields. The JSON envelope is:

```json
{
  "schema_version": 1,
  "workspace_dir": ".worldforge",
  "generated_at": "2026-05-06T12:00:00Z",
  "filter_applied": {"provider": null, "capability": null, "status": null,
                      "created_from": null, "created_to": null,
                      "artifact_type": null},
  "entry_count": 7,
  "issue_count": 1,
  "entries": [/* RunHistoryRecord rows */],
  "issues": [/* RunIndexIssue rows */]
}
```

Markdown adds a header with `workspace`, `generated_at`, `schema_version`,
and the active filter, followed by an entries table and an issues section.
CSV emits one row per entry with `run_id, kind, status, provider,
capability, created_at, artifact_count, safe_artifact_types, event_count,
failure_summary, path` columns.

## Issue rows for stale or corrupted workspaces

The walker tolerates broken run directories instead of aborting. Each
problem appears in the `issues` list with one of the typed reasons:

| Reason | Meaning |
| --- | --- |
| `manifest-missing` | Run directory has no `run_manifest.json` |
| `manifest-unreadable` | OS error reading the manifest (permissions, broken symlink) |
| `manifest-invalid-json` | Manifest exists but is not valid JSON |
| `manifest-not-object` | Manifest parses but is not a JSON object |

Each issue carries a short `detail` string for triage. None of the issue
records include the raw manifest contents; only the directory path and
machine-readable reason.

## Retention and cleanup interaction

The indexer is read-only. It does not delete or rewrite anything. Two
companion commands reclaim disk space:

- `worldforge runs cleanup --workspace-dir <dir> --keep N` — drops the
  oldest workspaces past the `--keep` newest count, irrespective of
  age. Quick blanket trim.
- `worldforge runs prune --workspace-dir <dir>` — applies a typed
  retention policy (`--max-age-days`, `--keep-latest`, repeatable
  `--family <kind>`) with explicit dry-run by default. `--apply`
  actually deletes. Use this when you want to keep recent runs of
  every kind but trim older `eval` or `benchmark` directories
  selectively. The 24-hour safety window blocks deletion of very fresh
  runs unless you pass `--max-age-days=0`.

Two recommended workflows:

1. **Pre-cleanup audit.** Run `runs index --format markdown` and attach
   the table to a cleanup issue. After approval, run `runs prune
   --apply --max-age-days 30 --keep-latest 10` (or `runs cleanup`) and
   re-run `runs index` to confirm only the kept runs remain.
2. **Stale-directory triage.** If the `issues` list is non-empty,
   investigate each `run_dir` before cleanup. `runs cleanup` and `runs
   prune` only operate on workspaces under `<workspace>/runs/`;
   corrupted directories with no manifest may need manual removal.

`runs prune` accepts `--retention-profile <path>` pointing at a
non-secret config profile that declares a `runs_retention` block
(`max_age_days`, `keep_latest`, `families`). CLI flags passed in any
argparse form (`--max-age-days 7` *or* `--max-age-days=7`) still
override the profile values.

`keep_latest` is **scoped to the family filter**: when `--family eval`
is set, the policy retains the newest `keep_latest` runs that match
`kind=eval` rather than the newest `keep_latest` runs across all kinds.
This avoids the surprise where a newer non-matching run silently
consumes the keep slot reserved for the filtered family. With no
`--family` flag, `keep_latest` is global.

`runs prune` only deletes paths that resolve under the resolved
`<workspace>/runs/` root (symlinks pointing outside that tree are
caught by the path check, not followed for deletion). `shutil.rmtree`
failures during `--apply` are wrapped as `WorldForgeError` so CLI
callers see a stable error envelope rather than a traceback.

## Public Python surface

The same data is available without going through the CLI:

```python
from pathlib import Path
from worldforge.harness.run_history import RunHistoryFilter
from worldforge.harness.run_index import build_run_index

index = build_run_index(
    Path(".worldforge"),
    filters=RunHistoryFilter.from_strings(provider="cosmos", status="failed"),
)
print(index.to_markdown())
```

`build_run_index()` is read-only, deterministic, and tolerates missing or
malformed run directories — it does not raise on corrupted workspaces.

## Validation

The indexer does not produce safe-to-attach artifacts that include raw
provider output. Only sanitized manifest fields, safe-artifact suffix
metadata, and failure summaries reach the index. Hosts that need raw
artifacts should still use `worldforge runs bundle` (sanitization +
SHA-256 digests) or copy the run directory directly.
