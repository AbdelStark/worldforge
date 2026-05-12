# Capability Protocols Quickstart

Capability protocols are the small-registration path for host applications that already own a
local function, model wrapper, or service client. Use this path when a single in-process object can
score, select, predict, generate, reason, embed, or transfer without needing a full provider
package.

Use a `BaseProvider` subclass when the adapter needs catalog registration, custom health checks,
credential handling, generated provider docs, or multiple provider-owned surfaces. Use capability
protocols when the host application owns the runtime and only needs to plug one narrow capability
into `WorldForge`.

The runnable mini-demo lives at `examples/capability_protocols_mini.py`.

```bash
uv run python examples/capability_protocols_mini.py
```

The script registers three plain Python objects:

- `LocalPredictor` implements `predict(...)` and returns `PredictionPayload`.
- `LocalPolicy` implements `select_actions(...)` and returns `ActionPolicyResult` with candidate
  action plans.
- `LocalCost` implements `score_actions(...)` and returns `ActionScoreResult`.

Each object declares a non-empty `name` and an optional `ProviderProfileSpec`. No subclassing is
required:

<!-- worldforge-snippet: skip-illustrative -->
```python
forge = WorldForge(auto_register_remote=False, discover_entry_points=False)
forge.register_predictor(LocalPredictor())
forge.register_policy(LocalPolicy())
forge.register_cost(LocalCost())
```

After registration, the objects can be resolved by name just like provider-backed surfaces. The
demo creates a world whose default prediction provider is `local-predictor`, then asks
`World.plan(...)` to compose policy proposals with score-based ranking:

<!-- worldforge-snippet: skip-illustrative -->
```python
plan = world.plan(
    goal="keep the blue cube near the origin",
    policy_provider="local-policy",
    policy_info={"object_id": "cube-1"},
    score_provider="local-cost",
    score_info={"goal": "stay near origin"},
)
```

The resulting plan is deterministic JSON. Its metadata shows the composed path:

<!-- worldforge-snippet: skip-illustrative -->
```json
{
  "metadata": {
    "planning_mode": "policy+score",
    "policy_provider": "local-policy",
    "score_provider": "local-cost"
  }
}
```

Keep protocol implementations narrow. Validate caller input at the boundary, return the exact
WorldForge result type for the capability, and keep optional runtimes, credentials, checkpoints,
and telemetry export host-owned.

