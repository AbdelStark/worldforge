# World State Diff And Patch

WorldForge can compare two persisted or exported world snapshots into a
schema-versioned, JSON-native diff, and promote that diff to a patch that
applies cleanly to a base snapshot. The artifact lives in
`worldforge.world_diff` and is exposed via `worldforge world diff` on the
CLI.

## When to use it

- A run preserved a world snapshot and the test that follows produced a
  different one — show the operator the structured difference.
- Two hosts ran the same scenario and produced subtly different worlds —
  attach the diff to an issue.
- Document an expected world transition by capturing it as a patch and
  asserting `apply_patch(base, patch) == expected` in a test.

## When not to use it

- Concurrent editing across multiple writers. The patch is a sequenced
  application against one base — there is no three-way merge or
  conflict-resolution layer. Out of scope, by design.
- Silently applying a malformed patch. Every `apply_patch` operation
  validates the resulting object through `SceneObject`, `Position`, and
  `BBox`, so traversal-shaped IDs, incoherent bboxes, or malformed pose
  payloads fail with `WorldStateError` instead of producing corrupt
  state.

## CLI

Two modes: persisted-world-id (default) or explicit JSON paths.

```bash
# Diff two persisted worlds in the default state directory.
uv run worldforge world diff alpha-id beta-id --format markdown

# Diff two exported JSON files (e.g. captured by `worldforge world export`).
uv run worldforge world diff a.json b.json \
    --source-path --target-path --format json > diff.json
```

The CLI exits non-zero when only one of `--source-path` and
`--target-path` is set; both flags are required together.

## Diff payload

```json
{
  "schema_version": 1,
  "source_label": "alpha-id",
  "target_label": "beta-id",
  "field_changes": [
    {"field": "step", "before": 0, "after": 7}
  ],
  "object_changes": [
    {"kind": "added", "object_id": "obj_mug_1", "before": null,
     "after": {"id": "obj_mug_1", "name": "mug", "pose": {...}, "bbox": {...}}}
  ],
  "history_summary": {"source": 1, "target": 7}
}
```

`field_changes` covers the top-level world fields (`name`, `provider`,
`description`, `step`, `metadata`). `object_changes` covers scene-object
add/remove/update with full before-and-after payloads — the consumer
gets enough information to render a side-by-side view without
re-reading the source files.

## Python surface

```python
from pathlib import Path
from worldforge import (
    diff_worlds,
    diff_worlds_from_paths,
    WorldPatch,
    apply_patch,
)

# Compare two World instances or JSON dicts.
diff = diff_worlds(world_a.to_dict(), world_b.to_dict())
print(diff.to_markdown())

# Or compare two on-disk world files (persisted or exported).
diff = diff_worlds_from_paths(Path("a.json"), Path("b.json"))

# Promote to a patch and apply to a base snapshot.
patch = WorldPatch.from_diff(diff)
new_state = apply_patch(world_a.to_dict(), patch)
```

The diff is read-only — neither input is mutated. `apply_patch` returns
a new dict; the original is untouched.

## How fixtures differ from diffs

Provider fixtures under `tests/fixtures/providers/` capture provider
inputs and outputs for adapter-contract testing. World diffs capture
how a *world snapshot* changed — they live in the user's workspace
(or an issue attachment), not in the repository, and they are not part
of any provider contract. A diff is a debugging artifact, not a
specification.

## Validation guarantees

- `WorldDiff.schema_version` is `1`. Schema changes will bump it.
- `WorldFieldChange.field` is restricted to a typed set
  (`WORLD_FIELD_NAMES`); unknown fields raise `WorldForgeError` at
  construction.
- `ObjectChange.kind` is restricted to `added | removed | updated`.
- `ObjectChange.object_id` is rejected if it is empty, contains `/`,
  `\`, or equals `.` / `..` — the same traversal rules WorldForge
  applies to persisted world ids.
- `apply_patch` rejects: traversal-shaped object ids, incoherent bboxes
  (min > max), malformed pose payloads, attempts to add an existing
  id, attempts to remove or update a missing id, and non-integer or
  negative `step` values.
