# Capability Negotiation Reports

WorldForge can report — before any workflow runs — whether the currently registered and
known providers can satisfy a capability set. The report is useful when triaging a CI
failure, picking a host before running an evaluation suite, or choosing a benchmark preset
that has both policy and score providers ready.

## Workflows

Out of the box, WorldForge knows the following workflow shapes:

| Workflow | Required capabilities |
| --- | --- |
| `predict-only` | predict |
| `generate-only` | generate |
| `score-only` | score |
| `policy-only` | policy |
| `transfer-only` | transfer |
| `reason-only` | reason |
| `embed-only` | embed |
| `policy-plus-score` | policy, score |
| `evaluation-generation` | generate |
| `evaluation-physics` | predict |
| `evaluation-planning` | predict |
| `evaluation-reasoning` | reason |
| `evaluation-transfer` | transfer |

The `evaluation-*` workflows mirror the built-in evaluation suites' required capabilities.
Hosts can register additional providers through `WorldForge.register_provider()`; the
negotiation report includes them automatically.

## CLI

```bash
uv run worldforge negotiate --list
uv run worldforge negotiate --workflow policy-plus-score
uv run worldforge negotiate --workflow generate-only --format json
uv run worldforge negotiate                                # every workflow at once
```

The CLI exits non-zero when at least one workflow is `BLOCKED`, which makes it suitable as
a CI guard before a release-evidence run. Output formats:

- **Markdown** (default): a per-workflow status table that lists every candidate provider's
  registration, capability, configuration, health, readiness state, and a typed reason if
  it cannot serve the capability today, plus a "Recommended actions" footer.
- **JSON**: stable machine-readable shape suitable for run-manifest attachment.

For a checkout-safe preflight demo that preserves ready, missing-config, missing-dependency,
unsupported, and not-registered examples, run:

```bash
uv run python scripts/demo_showcases.py run capability-negotiation-preflight --workspace-dir .worldforge/demo-showcases --overwrite
```

The workflow writes JSON and Markdown negotiation reports under the selected demo workspace and
records the recommended first commands without installing dependencies, configuring credentials, or
executing a fallback workflow.

## Python

```python
from worldforge import (
    list_workflow_names,
    negotiate_capabilities,
    WorldForge,
)

forge = WorldForge()
report = negotiate_capabilities(["policy-plus-score"], forge=forge)
for negotiation in report.workflows:
    print(negotiation.workflow.name, "ready" if negotiation.ready else "blocked")
    for action in negotiation.recommended_actions:
        print("  →", action)
```

Public surface (provisional under
[Public API Stability](./api-stability.md)):

| Symbol | Purpose |
| --- | --- |
| `WorkflowSpec` | Frozen dataclass describing one named workflow. |
| `WorkflowNegotiation` | Result of negotiating one workflow against the live forge. |
| `CapabilityRequirement` | One capability slot with all candidate providers. |
| `CapabilityProviderStatus` | Per-provider readiness for one capability. |
| `CapabilityNegotiationReport` | Top-level report covering one or more workflows. |
| `list_workflows`, `list_workflow_names`, `get_workflow` | Registry helpers. |
| `negotiate_capabilities` | Run negotiation. |
| `CAPABILITY_NEGOTIATION_SCHEMA_VERSION` | Currently `1`. |

## Readiness states

| State | Meaning |
| --- | --- |
| `ready` | Provider is registered, configured, healthy, and supports the capability. |
| `missing-config` | Provider supports the capability but its runtime profile is missing required environment (e.g. `COSMOS_BASE_URL`). |
| `missing-dependency` | Provider is registered and configured but its health check is unhealthy (e.g. an optional runtime is not reachable). |
| `unsupported` | Provider is in the catalog but does not advertise the capability. |
| `not-registered` | Provider is in the catalog and would satisfy the capability but is not currently registered on this forge. |

## Recommended actions

Each blocked capability emits one focused recommendation. Examples:

- `Configure provider 'cosmos' to serve capability 'generate': provider profile 'cosmos' is not configured: missing COSMOS_BASE_URL.`
- `Register or configure a provider that supports capability 'score'.`

These are human-readable diagnostics, not machine-parseable command strings. Follow the
linked provider pages for actual setup.

## Validation

```bash
uv run pytest tests/test_capability_negotiation.py tests/test_cli_doctor.py tests/test_provider_profiles.py tests/test_runtime_profiles.py
uv run mkdocs build --strict
```
