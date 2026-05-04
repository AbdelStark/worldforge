# Capability Fixture Corpus

WorldForge ships a small, packaged corpus of canonical input fixtures for every provider
capability — `predict`, `reason`, `embed`, `generate`, `transfer`, `score`, and `policy`.
Conformance tests, evaluation suites, and provider authors can reuse the corpus instead of
hand-rolling payloads in each test file.

The corpus lives at `src/worldforge/testing/fixtures/` and is exposed through the public
testing API at `worldforge.testing` (so it is part of the wheel; no checkout-time path
discovery is needed).

## Cardinality

For each capability the corpus ships:

- exactly one `valid_baseline.json` representing a minimal-but-realistic public input,
- at least two `invalid_<reason>.json` fixtures that name distinct boundary failures.

This guarantees seven valid baselines and at least fourteen invalid boundary fixtures, so
every conformance helper can be exercised without re-deriving payloads.

## Envelope

Each fixture file is a JSON object with `schema_version: 1` and the following keys:

| Field | Description |
| --- | --- |
| `id` | `<capability>.<name>` matching the file path (e.g. `predict.valid_baseline`). |
| `capability` | One of `predict`, `reason`, `embed`, `generate`, `transfer`, `score`, `policy`. |
| `data_class` | `synthetic` (hand-authored), `captured` (recorded from a real provider/run), or `host-supplied` (provided by an integrator at runtime; the file ships an example). |
| `expected` | `valid` or `invalid`. |
| `expected_error_pattern` | Regex hint for the error message a `WorldForgeError` raises. Required for invalid fixtures, must be `null` for valid fixtures. |
| `description` | One-sentence note on what the fixture exercises. |
| `payload` | Capability-specific dict whose keys map directly onto the matching `assert_*_conformance()` keyword arguments. |

The complete contributor charter — including ownership, when to add a new fixture, and what
*not* to put in the corpus — lives in
[`src/worldforge/testing/fixtures/README.md`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/testing/fixtures/README.md).

## Loading fixtures

```python
from worldforge.testing import (
    iter_capability_fixtures,
    load_capability_fixture,
)

baseline = load_capability_fixture("score", "valid_baseline")
score_info = baseline.payload["info"]
candidates = baseline.payload["action_candidates"]

for fixture in iter_capability_fixtures("policy"):
    print(fixture.id, fixture.expected, fixture.description)
```

Available helpers (re-exported from `worldforge.testing`):

| Symbol | Purpose |
| --- | --- |
| `CAPABILITY_FIXTURE_NAMES` | Tuple of capability names covered by the corpus. |
| `CapabilityFixture` | Frozen dataclass returned by the loader. |
| `FIXTURE_SCHEMA_VERSION` | Currently `1`; bump only with a loader migration. |
| `list_fixture_names(capability)` | Sorted file stems for a capability. |
| `load_capability_fixture(capability, name)` | Validate and return one fixture. |
| `iter_capability_fixtures(capability)` | Iterate validated fixtures for one capability. |
| `iter_all_fixtures()` | Iterate every fixture across the corpus. |

## Using fixtures in conformance tests

The `payload` keys mirror the keyword arguments of `assert_*_conformance()`, so a fixture can
flow straight into the existing helpers:

```python
from worldforge import Action, MockProvider
from worldforge.testing import (
    assert_embed_conformance,
    assert_predict_conformance,
    load_capability_fixture,
)

provider = MockProvider()

predict_fx = load_capability_fixture("predict", "valid_baseline")
assert_predict_conformance(
    provider,
    world_state=predict_fx.payload["world_state"],
    action=Action.from_dict(predict_fx.payload["action"]),
    steps=predict_fx.payload["steps"],
)

embed_fx = load_capability_fixture("embed", "valid_baseline")
assert_embed_conformance(provider, text=embed_fx.payload["text"])
```

For invalid fixtures, callers can compile `expected_error_pattern` into a regex and assert
that the corresponding API surface raises `WorldForgeError` with a matching message. Some
invalid fixtures document a contract claim that the framework does not yet enforce; those
fixtures still ship so future validators can lock against them, and the description spells
the situation out.

## Data ownership

Fixtures are owned by the evaluation/quality stream alongside the deterministic evaluation
suites. They are deliberately:

- **synthetic by default** — hand-authored JSON shapes that exercise public-input boundaries.
- **tiny** — JSON only; binary clip frames are inlined as `frames_base64` strings rather than
  shipped as media files.
- **provider-agnostic where possible** — provider-specific shapes (e.g. `policy_info`
  variants for LeRobot vs GR00T) belong here only if more than one consumer would benefit;
  otherwise keep them in `tests/fixtures/providers/` next to the provider fixtures used for
  parser and retry tests.

Captured payloads (`data_class: "captured"`) are accepted when they reproduce a real bug or
regression and are sanitized of secrets, signed URLs, host paths, and proprietary content.
Host-supplied payloads (`data_class: "host-supplied"`) ship a synthetic placeholder; the
`description` field documents what the integrator should substitute.

## Validation

```bash
uv run pytest tests/test_capability_fixtures.py tests/test_provider_contracts.py
bash scripts/test_package.sh
uv run mkdocs build --strict
```
