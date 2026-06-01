# Control And Planning

WorldForge separates three roles in physical-AI planning:

- **Policy** providers propose actions from observations and instructions.
- **Score** providers rank candidate actions or action horizons against an observation and goal.
- **Controllers** decide how to sample, score, refine, and return executable WorldForge `Action`
  chunks.

`LatentMPCController` is the first built-in controller. It implements a checkout-safe
Cross-Entropy Method (CEM) loop over the existing `score_actions(...)` capability:

```text
sample action horizons
-> encode candidates for the score provider
-> score candidates
-> refit the Gaussian proposal from elites
-> return the best execute_k actions
```

The controller runs entirely in Python action space. It does not import `torch`, execute a robot,
step an environment, or train a world model. Tensor conversion, image preprocessing, model
inference, simulation, hardware execution, and safety interlocks remain host-owned or
provider-owned.

## World.plan Entry Point

Use `World.plan(planner="latent-mpc", ...)` when the host wants one MPC solve over a score
provider:

```python
from worldforge import PlannerConfig

plan = world.plan(
    goal="move toward the goal latent",
    planner="latent-mpc",
    score_provider="my-score-provider",
    score_info={"observation_id": "frame-001"},
    goal_info={"target_x": 0.5},
    planner_config=PlannerConfig(
        horizon=2,
        num_samples=96,
        num_iterations=5,
        num_elites=12,
        execute_k=1,
        seed=19,
        action_kind="velocity",
        action_parameter_bounds={"x": (-2.0, 2.0)},
    ),
)
```

Latent MPC requires an explicit `score_provider`. The world default provider is not used as an
implicit cost oracle because control loops should make the scoring model visible in plan metadata
and workflow traces.

The returned plan uses:

- `plan.planner == "latent-mpc"`
- `plan.metadata["planning_mode"] == "latent-mpc"`
- `plan.metadata["control_mode"] == "mpc"`
- `plan.metadata["optimizer"] == "cem"`
- `plan.metadata["iteration_best_scores"]` for every CEM iteration
- `plan.metadata["iteration_costs"]` when the score provider declares `lower_is_better=True`

The host owns receding-horizon closure: execute up to `execute_k` actions, collect a new
observation, then call `World.plan(planner="latent-mpc", ...)` again.

## Encoders

`ScoreCandidateEncoder` maps sampled WorldForge action horizons into the payload expected by a
score provider. The default `ActionPlanCandidateEncoder` serializes candidate actions with
`Action.to_dict()` and sends observation and goal dictionaries:

```text
info = {"observation": observation_info, "goal": goal_info}
action_candidates = [[action.to_dict(), ...], ...]
```

Prepared-host robotics or simulation integrations can supply a custom encoder that converts the
same sampled action horizons into provider-native tensors or nested numeric arrays. Keep that
conversion behind the provider or host boundary; do not add optional runtime dependencies to the
base package.

## Current Scope

The first implementation supports Gaussian CEM sampling. Policy warm-start is intentionally
rejected with a typed `WorldForgeError` until the public contract is implemented and tested.

Use existing `policy+score` planning when a policy provider should propose concrete candidate
actions directly. Use latent MPC when WorldForge should sample and refine action horizons through
a score provider.
