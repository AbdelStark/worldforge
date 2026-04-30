# Examples

Runnable examples are split into checkout scripts and packaged console commands.

Use the CLI index for the current command list and JSON metadata:

```bash
uv run worldforge examples
uv run worldforge examples --format json
```

## Visual Harness

| Example | Surface | Command |
| --- | --- | --- |
| `theworldharness` | E2E flows, provider diagnostics, benchmark comparison | `uv run --extra harness worldforge-harness` |

```bash
uv run --extra harness worldforge-harness
uv run --extra harness worldforge-harness --flow lerobot
uv run --extra harness worldforge-harness --flow diagnostics
```

TheWorldHarness is optional and depends on Textual through the `harness` extra. It currently
includes score-planning, policy-plus-score planning, and provider diagnostics plus benchmark
comparison flows.

## Prediction And Evaluation

| Example | Surface | Command |
| --- | --- | --- |
| `basic-prediction` | prediction, planning, evaluation | `uv run python examples/basic_prediction.py` |

## Provider Comparison

| Example | Surface | Command |
| --- | --- | --- |
| `cross-provider-compare` | provider registration, comparison | `uv run python examples/cross_provider_compare.py` |

## Score Planning

| Example | Surface | Command |
| --- | --- | --- |
| `leworldmodel-score-planning` | score provider, planning, persistence | `uv run worldforge-demo-leworldmodel` |

## Policy Plus Score Planning

| Example | Surface | Command |
| --- | --- | --- |
| `lerobot-policy-score-planning` | policy provider, score provider, planning, persistence | `uv run worldforge-demo-lerobot` |

## Service Host Reference

| Example | Surface | Command |
| --- | --- | --- |
| `service-host` | HTTP liveness/readiness, provider diagnostics, mock workflow, configurable generate workflow | `uv run python examples/hosts/service/app.py --provider mock --port 8080` |

The service host uses Python's stdlib HTTP server so it does not add a base dependency. It is a
reference for embedding WorldForge in a host process, not a WorldForge deployment boundary:
production services still own authentication, alerting, telemetry export, upstream SLA handling,
and artifact retention.

## Optional Runtime Smoke

| Example | Surface | Command |
| --- | --- | --- |
| `leworldmodel-real-checkpoint-smoke` | real checkpoint smoke | `scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu` |
| `lerobot-leworldmodel-real-robotics` | real policy plus real world-model scoring replay | `scripts/robotics-showcase` |

The explicit command behind the wrapper is:

```bash
uv run --python 3.13 \
  --with "stable-worldmodel[train] @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  --with "opencv-python" \
  --with "imageio" \
  lewm-real \
    --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
    --device cpu
```

It runs real LeWorldModel checkpoint scoring over deterministic synthetic PushT-shaped tensors
through the official `stable_worldmodel.policy.AutoCostModel` loading path and prints a visual
pipeline, tensor shapes, latency metrics, provider events, and ranked candidate costs.

The real robotics showcase composes LeRobot and LeWorldModel through WorldForge policy-plus-score
planning with a packaged PushT bridge. The wrapper opens a Textual report by default and writes the
same run summary to `/tmp/worldforge-robotics-showcase/real-run.json`. The report reveals each stage
in sequence, includes an illustrative animated robot-arm replay, and gives candidate ranking plus
tabletop replay their own full-width sections. Use `--no-tui` for the plain terminal report.

```bash
scripts/robotics-showcase
```

Use the lower-level runner when bringing a different task observation, score tensor source, or
candidate bridge:

```bash
scripts/lewm-lerobot-real \
  --policy-path lerobot/diffusion_pusht \
  --policy-type diffusion \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --device cpu \
  --mode select_action \
  --observation-module /path/to/pusht_obs.py:build_observation \
  --score-info-npz /path/to/lewm_score_tensors.npz \
  --translator worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions \
  --candidate-builder /path/to/pusht_lewm_bridge.py:build_action_candidates
```

Use custom hooks only with task-aligned inputs: the LeRobot policy, observation, LeWorldModel score
tensors, and candidate bridge must describe the same robotics task. The wrapper runs real model
inference, then executes the selected WorldForge action chunk in the local mock world for reporting.

## Runtime Boundary

The packaged demos use real WorldForge provider surfaces with injected deterministic runtimes. They
are intended to verify the framework path in a clean checkout.

- `worldforge-demo-leworldmodel` exercises `LeWorldModelProvider`, score planning, execution,
  persistence, and reload without installing `stable_worldmodel`, torch, or checkpoints.
- `worldforge-demo-lerobot` exercises `LeRobotPolicyProvider`, policy-plus-score planning,
  execution, persistence, and reload without installing LeRobot, torch, or policy checkpoints.

Optional live smoke scripts are separate because they require host-owned model runtimes,
credentials, checkpoints, robot observations, or action translators.
