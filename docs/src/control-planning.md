# Control And Planning

This is WorldForge's backbone loop: **plan and score action candidates with an action-conditioned
predictive world model, in latent space.** It separates three roles:

- **Policy** providers propose actions from observations and instructions.
- **Score** providers rank candidate actions or action horizons against an observation and goal,
  acting as a cost oracle.
- **Controllers** own the optimizer: they decide how to sample, score, refine, and return
  executable WorldForge `Action` chunks. The world model stays a pure oracle; the controller stays
  a pure optimizer.

`LatentMPCController` is the built-in controller. It implements a checkout-safe Cross-Entropy Method
(CEM) loop over the `score_actions(...)` capability:

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

## Standalone Controller (primary entry point)

Drive `LatentMPCController` directly against anything that exposes the `score_actions(...)` surface
— a registered `WorldForge` provider or your own cost oracle. This is the recommended way to run the
backbone loop, and it needs no local world state.

```python
from worldforge import LatentMPCController, PlannerConfig, WorldForge

controller = LatentMPCController(
    forge=WorldForge(),
    score_provider="my-score-provider",
    config=PlannerConfig(horizon=1, num_samples=64, num_iterations=5),
)
step = controller.plan_step(
    observation_info={"observation_id": "frame-001"},
    goal_info={"target": [0.6, 0.5, 0.2]},
)
print(step.actions[0], step.best_score, step.metadata["control_mode"])
```

`examples/latent_mpc_planning.py` is a runnable, checkout-safe version that brings its own score
oracle, so the whole loop runs with no credentials, GPU, or robot. The host owns receding-horizon
closure: execute up to `execute_k` actions, collect a new observation, then call `plan_step(...)`
again.

## World.plan Entry Point (local-state convenience)

`World.plan(planner="latent-mpc", ...)` runs the same solve from within the local-state `World`
runtime. It is a convenience for hosts already using local JSON state; the standalone controller
above is the primary entry point.

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
