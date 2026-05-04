# Capability Fixture Corpus

This directory ships canonical input fixtures for every WorldForge provider capability
(`predict`, `reason`, `embed`, `generate`, `transfer`, `score`, `policy`). The corpus is
public testing API: it is part of the WorldForge wheel and consumers should reach it through
`worldforge.testing.load_capability_fixture` rather than path-walking.

## Cardinality

Each capability ships:

- exactly one `valid_baseline.json` representing a minimal-but-realistic public input,
- at least two `invalid_<reason>.json` fixtures that name distinct boundary failures.

Adding a new boundary case is welcome; loosen the cardinality only after confirming the new
fixture exercises a public-input invariant the existing files do not.

## Envelope shape

Every fixture file is a JSON object with the following keys (`schema_version: 1`):

| Field | Description |
| --- | --- |
| `schema_version` | Currently `1`. Bump only with a corresponding loader migration. |
| `id` | `<capability>.<name>` matching the file path (`predict/valid_baseline.json` → `predict.valid_baseline`). |
| `capability` | One of `predict`, `reason`, `embed`, `generate`, `transfer`, `score`, `policy`. |
| `data_class` | `synthetic` (hand-authored), `captured` (recorded from a real provider/run), or `host-supplied` (provided by an integrator at runtime; the file ships an example). |
| `expected` | `valid` or `invalid`. |
| `expected_error_pattern` | Regex hint for the error message a `WorldForgeError` raises. Required for invalid fixtures, must be `null` for valid fixtures. |
| `description` | One-sentence human-readable note on what the fixture exercises. |
| `payload` | Capability-specific dict whose keys map onto the matching `assert_*_conformance()` keyword arguments. |

The corpus is owned by the evaluation/quality stream. Fixture files are intentionally tiny
(JSON only; binary clip frames are inlined as `frames_base64`). Do not add real provider
captures, large media artifacts, or host-specific data; instead document the host requirement
and use `data_class = "host-supplied"` with a synthetic placeholder payload.

## Reuse

```python
from worldforge.testing import iter_capability_fixtures, load_capability_fixture

baseline = load_capability_fixture("score", "valid_baseline")
score_info = baseline.payload["info"]
candidates = baseline.payload["action_candidates"]

for fixture in iter_capability_fixtures("policy"):
    print(fixture.id, fixture.expected)
```

The `worldforge.testing.providers.assert_*_conformance` helpers accept the same keyword
arguments used by `payload`, so fixtures can be passed straight through with `**`.

## When to add a fixture

- A new public-input invariant lands (e.g. a stricter validator). Add an invalid fixture that
  trips the new check and reference the fixture from the regression test.
- A provider exposes a capability shape that the corpus does not cover yet (e.g. a new
  observation key for `policy`). Prefer extending an existing `valid_baseline.json`; only add
  a separate fixture when the variant exercises a contractually different code path.
- A bug-fix needs a regression input. Capture the minimum payload that reproduced the issue
  as a fixture and add a test that loads it.

## When NOT to add a fixture

- Marketing or end-to-end demos (use `examples/` instead).
- Provider-specific success or error responses (use `tests/fixtures/providers/`).
- Large benchmark inputs (use `examples/benchmark-inputs.json` and friends).
