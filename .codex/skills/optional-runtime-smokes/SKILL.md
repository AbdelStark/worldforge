---
name: optional-runtime-smokes
description: "Use for LeWorldModel, GR00T, LeRobot, PushT robotics showcase, real-checkpoint smoke scripts, checkpoint building, and host-owned optional runtime dependencies. Keeps real-runtime validation explicit without adding heavy ML/robotics packages or artifacts to the base project."
---

# Optional Runtime Smokes

## Runtime Boundary

- Checkout-safe demos may inject deterministic runtimes. Do not describe them as neural inference.
- Live smokes require host-installed packages, checkpoints, credentials, and task-specific observation/action translators.
- Keep `stable_worldmodel`, torch, LeRobot, Isaac GR00T, CUDA, TensorRT, datasets, checkpoints, and robot packages out of `project.dependencies`.
- Never commit downloaded assets, checkpoints, datasets, cache directories, or runtime-specific credentials.
- Do not pad, project, or reinterpret mismatched action spaces inside WorldForge.

## Command Selection

| Need | Start here |
| --- | --- |
| LeWorldModel adapter/planner path in a clean checkout | `uv run worldforge-demo-leworldmodel` |
| PushT robotics dependency/checkpoint status | `scripts/robotics-showcase --health-only` |
| Real LeWorldModel checkpoint smoke | `uv run --python 3.13 --with "stable-worldmodel[train] @ git+https://github.com/galilai-group/stable-worldmodel.git" --with "datasets>=2.21" worldforge-smoke-leworldmodel ...` |
| Build LeWorldModel object checkpoint | `worldforge-build-leworldmodel-checkpoint` with host-owned runtime deps |
| GR00T policy smoke | host-owned Isaac GR00T server or reachable remote policy server |
| LeRobot policy smoke | host-owned LeRobot install, policy checkpoint, observation builder, action translator |

## Rules

- `scripts/robotics-showcase --health-only` is non-mutating; it must not auto-build or download missing checkpoints.
- Use `--revision` or `LEWORLDMODEL_REVISION` to pin Hugging Face asset resolution.
- Keep `torch.load(..., weights_only=True)` unless a trusted legacy artifact explicitly requires `--allow-unsafe-pickle`.
- Keep warning filters narrow. Use `WORLDFORGE_SHOW_RUNTIME_WARNINGS=1` when raw third-party stderr is needed.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| LeWorldModel import fails | PyPI/source/runtime mismatch | Use GitHub `stable-worldmodel[train]` plus `datasets>=2.21` in the process |
| Missing object checkpoint | Host cache lacks `*_object.ckpt` | Run checkpoint builder with host-owned deps or supply `--cache-dir` |
| GR00T cannot start locally | Unsupported CUDA/TensorRT host | Connect to a remote policy server |
| Policy+score shape mismatch | Task action spaces differ | Stop and require task-aligned translator/candidate bridge |
