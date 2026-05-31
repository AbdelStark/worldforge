# DimOS Go2 Replay Arena

Checkout-safe replay arena for testing whether WorldForge adds decision evidence above a DimOS
Go2 replay or simulation surface.

This example does not import DimOS, connect to hardware, start a browser simulator, or claim a
learned latent model. It consumes a small JSON fixture shaped like a DimOS replay frame, generates
candidate Go2 actions, scores them with transparent costs, and writes a decision trace plus a
compact report.

## Run

```bash
uv run python examples/dimos-go2-replay-arena/run.py \
  --fixture examples/dimos-go2-replay-arena/fixtures/go2_office_replay_frame.json \
  --out .worldforge/dimos-go2-replay-arena
```

Expected success signal:

- `.worldforge/dimos-go2-replay-arena/decision-trace.json` exists.
- `.worldforge/dimos-go2-replay-arena/report.md` exists.
- The trace includes `selected_action`, `score_margin`, `baseline_regret`, and scored
  counterfactual candidates.

First triage step: open `decision-trace.json` and verify that the candidate count matches the
fixture and that every scored candidate has `distance_cost`, `obstacle_risk`, `uncertainty_cost`,
and `relocalization_cost` components.

The bundled fixtures exercise both sides of the decision-evidence claim:

- `go2_office_replay_frame.json` should reject the hardcoded `baseline_forward` action and choose
  `stop_relocalize` because localization is weak and forward motion clips risky map geometry.
- `go2_clear_hallway_replay_frame.json` should preserve `baseline_forward` because the hallway is
  clear and the baseline reaches the goal with the lowest transparent cost.

## Kill Criterion

WorldForge earns its place only if it improves robot decision-making evidence. If this arena only
logs a DimOS command without choosing, explaining, comparing, or exposing counterfactual actions,
the integration should be stopped or redesigned.
