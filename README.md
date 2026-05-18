<div align="center">

# WorldForge

**Testable world-model workflows for physical-AI systems.**

WorldForge is a Python integration layer that gives world-model providers, score models, embodied
policies, and media generators explicit capability contracts. It adds planning, evaluation,
benchmarks, diagnostics, local state, and CLI tools while keeping checkpoints, credentials, robot
controllers, and deployment host-owned.

[![CI](https://img.shields.io/github/actions/workflow/status/AbdelStark/worldforge/ci.yml?branch=main&label=CI&style=for-the-badge)](https://github.com/AbdelStark/worldforge/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/github/actions/workflow/status/AbdelStark/worldforge/pages.yml?branch=main&label=docs&style=for-the-badge)](https://abdelstark.github.io/worldforge/)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://github.com/AbdelStark/worldforge/blob/main/pyproject.toml)
[![PyPI](https://img.shields.io/pypi/v/worldforge-ai?style=for-the-badge&label=pypi&color=3f7cac)](https://pypi.org/project/worldforge-ai/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge)](./LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A590%25-brightgreen?style=for-the-badge)](./.github/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/typed-py.typed-3f7cac?style=for-the-badge)](./src/worldforge/py.typed)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=for-the-badge)](https://github.com/astral-sh/uv)
[![Status: pre-1.0](https://img.shields.io/badge/status-pre--1.0%20beta-orange?style=for-the-badge)](#project-status)
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-5-ee8449?style=for-the-badge)](#contributors)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

[**Quickstart**](#quickstart) ·
[**Docs Map**](https://abdelstark.github.io/worldforge/docs-map/) ·
[**CLI**](https://abdelstark.github.io/worldforge/cli/) ·
[**Showcases**](https://abdelstark.github.io/worldforge/demo-showcases/) ·
[**Providers**](#provider-surfaces) ·
[**Rerun**](https://abdelstark.github.io/worldforge/rerun/) ·
[**Capability Model**](#capability-model) ·
[**Architecture**](#architecture) ·
[**Quality**](https://abdelstark.github.io/worldforge/quality/) ·
[**Evidence**](https://abdelstark.github.io/worldforge/claim-evidence-map/) ·
[**Docs**](https://abdelstark.github.io/worldforge/) ·
[**Playbooks**](https://abdelstark.github.io/worldforge/playbooks/) ·
[**Support**](./SUPPORT.md) ·
[**Security**](./SECURITY.md)

</div>

## Robotics Showcase: LeRobot + LeWorldModel

WorldForge's front-door robotics demo composes a
[Hugging Face LeRobot](https://github.com/huggingface/lerobot) policy with a
[LeWorldModel](https://github.com/lucas-maes/le-wm) checkpoint. LeRobot proposes PushT action
candidates, WorldForge bridges those policy actions into LeWorldModel-native candidate tensors,
LeWorldModel scores the candidates, and WorldForge selects and mock-replays the lowest-cost action
chunk.

The LeWorldModel runtime path intentionally follows the official LeWM loading contract:
`stable_worldmodel.policy.AutoCostModel("pusht/lewm")` loads the Lucas Maes LeWM object checkpoint.
`stable-worldmodel` is the runtime/evaluation library used by the official LeWorldModel repo, not
a substitute score model.

This is simulation/replay planning. It demonstrates policy inference, score-model inference,
typed provider composition, candidate ranking, event capture, and visual replay. Hardware control,
safety checks, robot-controller integration, and task-specific preprocessing stay host-owned.

<div align="center">
<table>
  <tr>
    <td width="50%">
      <img src="./docs/src/assets/img/robotics-showcase-lerobot-leworldmodel-2.png" alt="WorldForge robotics showcase TUI with pipeline flow, runtime metrics, and tensor contract" width="100%" />
      <br />
      <sub><strong>Pipeline:</strong> real policy, real score checkpoint, WorldForge planner, local mock replay.</sub>
    </td>
    <td width="50%">
      <img src="./docs/src/assets/img/robotics-showcase-lerobot-leworldmodel-1.png" alt="WorldForge robotics showcase TUI with robot-arm illustration, candidate ranking, and tabletop replay" width="100%" />
      <br />
      <sub><strong>Decision:</strong> candidate ranking, robot-arm illustration, and fixed tabletop replay.</sub>
    </td>
  </tr>
</table>
</div>

```bash
scripts/robotics-showcase
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases
```

The first command launches a staged Textual report by default, writes the same run data to
`/tmp/worldforge-robotics-showcase/real-run.json`, and writes a visual Rerun recording to
`/tmp/worldforge-robotics-showcase/real-run.rrd`. Press `o` in the TUI to open that recording in
Rerun. Use `--tui-stage-delay 0.1` for a faster reveal, `--no-tui-animation` to skip sleeps and
arm motion, `--no-tui` for the plain terminal report, `--no-rerun` to skip the Rerun artifact,
`--json-only` for automation, or `--health-only` for a non-mutating dependency/checkpoint
preflight. Use `--lewm-revision <40-char-commit-sha>` to pin auto-built LeWorldModel assets.
The second command runs the checkout-safe demo showcase suite without external credentials.

The optional live robotics workflow, `.github/workflows/robotics-showcase.yml`, runs this same
showcase in non-interactive JSON mode on every pull request run and on pushes to `main`. It caches
Hugging Face downloads, LeWorldModel build assets, and the built object checkpoint with
`actions/cache`; CI uploads `real-run.json`, `stdout.json`, and `run_manifest.json` as evidence,
while checkpoint artifacts are not uploaded.

Read the walkthrough and implementation notes: [Robotics Replay Showcase](https://abdelstark.github.io/worldforge/robotics-showcase/)
and [Robotics Showcase Technical Deep Dive](https://abdelstark.github.io/worldforge/robotics-showcase-deep-dive/).

<details>
<summary><strong>TheWorldHarness TUI</strong> - checkout-safe visual harness for worlds, providers, evals, benchmarks, and packaged flows</summary>

TheWorldHarness is the optional Textual workspace for inspecting WorldForge flows without installing
robotics or model runtimes. It runs checkout-safe demos, provider diagnostics, benchmark comparison,
world editing, and saved report previews through the `harness` extra.

```bash
uv run --extra harness worldforge-harness
uv run --extra harness worldforge-harness --flow lerobot
uv run --extra harness worldforge-harness --flow cosmos-policy
uv run --extra harness worldforge-harness --flow gr00t-replay
uv run --extra harness worldforge-harness --flow robotics-compare
uv run --extra harness worldforge-harness --flow diagnostics
```

<div align="center">
<table>
  <tr>
    <td width="50%">
      <img src="./docs/src/assets/img/theworldharness-home-launchpad.png" alt="TheWorldHarness home screen with keyboard-first launch targets" width="100%" />
      <br />
      <sub><strong>Home:</strong> keyboard-first launchpad for worlds, providers, evals, and help.</sub>
    </td>
    <td width="50%">
      <img src="./docs/src/assets/img/theworldharness-run-inspector-score-planning.png" alt="TheWorldHarness run inspector showing a score-planning flow" width="100%" />
      <br />
      <sub><strong>Run inspector:</strong> flow trace with scored plans, metrics, and transcript.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="./docs/src/assets/img/theworldharness-world-editor.png" alt="TheWorldHarness world editor with saved state preview" width="100%" />
      <br />
      <sub><strong>World editor:</strong> persisted scene state, objects, provider, and preview in one place.</sub>
    </td>
    <td width="50%">
      <img src="./docs/src/assets/img/theworldharness-provider-help-overlay.png" alt="TheWorldHarness provider screen with bindings help overlay" width="100%" />
      <br />
      <sub><strong>Provider help:</strong> discoverable bindings over live provider diagnostics.</sub>
    </td>
  </tr>
</table>
</div>

More detail: [TheWorldHarness docs](https://abdelstark.github.io/worldforge/theworldharness/).

</details>

<details>
<summary><strong>Rerun observability</strong> - optional recording layer for events, world snapshots, plans, and benchmark artifacts</summary>

WorldForge can stream sanitized provider events and run artifacts into
[Rerun](https://github.com/rerun-io/rerun) without making Rerun a provider or base dependency.

```bash
uv run --extra rerun worldforge-demo-rerun
uv run --extra rerun rerun .worldforge/rerun/worldforge-rerun-showcase.rrd
scripts/robotics-showcase
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

The checkout-safe Rerun demo records provider event logs, world snapshots, a predictive plan,
workflow trace artifacts, 3D object boxes, and benchmark metrics into a local `.rrd` file. The
robotics showcase records the real PushT policy+score run with candidate target points, selected
trajectory, score bars, latency bars, provider events, plan payload, and replay snapshots. Use
`--spawn`, `--connect-url`, or `--serve-grpc-port` for live viewer workflows in the checkout-safe
demo.

More detail: [Rerun integration docs](https://abdelstark.github.io/worldforge/rerun/).

</details>

---

## Overview

A score model, a robot policy server, a video simulator, and a remote media API have different
inputs, runtimes, and failure modes. WorldForge does not flatten those differences. Each provider
adapter declares which of eight capabilities it supports (`predict`, `score`, `policy`, `generate`,
`transfer`, `reason`, `embed`, `plan`). The contract is strict and fail-closed: calling an
unsupported capability raises rather than quietly returning empty results.

Planning, evaluation, benchmarks, diagnostics, and persistence are built on top of that contract,
not on any specific runtime.
Benchmark budget files can turn success rate, error count, retry count, latency, and throughput
thresholds into non-zero CLI gates for release checks or preserved benchmark claims.
The [claim-to-evidence map](https://abdelstark.github.io/worldforge/claim-evidence-map/) links
public capability and runtime claims to concrete tests, commands, artifacts, and non-claims.

WorldForge is not a hosted service, a model API abstraction, or a training framework. Optional
runtimes, robot stacks, credentials, checkpoints, and durable storage remain the host
application's responsibility.

## Highlights

| | |
| --- | --- |
| **Capability contracts** | Eight named capabilities. Adapters advertise only what they actually implement and return typed WorldForge results. Unknown names raise instead of behaving like empty filters. |
| **Composable planning** | Combine predictive, score, and policy providers in a single planning loop. Rank candidates, roll out futures, execute actions, persist state. |
| **Deterministic by default** | Built-in `mock` provider, reusable contract assertions (`worldforge.testing`), and packaged demos that run from a clean checkout without credentials or GPUs. |
| **Host-owned runtimes** | No torch, CUDA, robot controllers, or checkpoints in base dependencies. LeWorldModel, GR00T, LeRobot, Cosmos, and Runway integrate through their own surfaces. |
| **Diagnostics** | `worldforge doctor`, provider events, workflow traces, benchmark and evaluation harnesses, and an optional Textual TUI (`TheWorldHarness`). |
| **Rerun observability** | Optional `rerun-sdk` bridge for event streams, workflow traces, world snapshots, plans, and benchmark artifacts. |
| **Quality gates** | `py.typed`, import-isolated pytest, ruff, a 90% coverage floor, strict docs, and wheel + sdist contract tests in CI on Python 3.13. |

## Install

### Library (recommended)

```bash
# From PyPI (recommended)
uv add worldforge-ai
# or
pip install worldforge-ai
```

The Python import path stays the same:

```python
import worldforge
```

If you want the optional Textual harness UI:

```bash
uv add "worldforge-ai[harness]"
```

If you want Rerun-backed event and artifact recording:

```bash
uv add "worldforge-ai[rerun]"
```

### From source (bleeding edge)

```bash
uv add "worldforge-ai @ git+https://github.com/AbdelStark/worldforge"
```

### Repository development

```bash
git clone https://github.com/AbdelStark/worldforge.git
cd worldforge
uv sync --group dev
cp .env.example .env
```

Optional extras:

```bash
uv sync --group dev --extra harness   # TheWorldHarness Textual TUI
uv sync --group dev --extra rerun     # Rerun event and artifact recording
```

Python 3.13 only. Base install depends only on `httpx`. Optional runtimes are host-owned.

## Quickstart

The short path is the mock provider: it runs from a clean checkout and exercises the same typed
world, provider, planning, persistence, and diagnostics surfaces used by richer runtimes.

Full references:
[Python API](https://abdelstark.github.io/worldforge/api/python/) ·
[CLI reference](https://abdelstark.github.io/worldforge/cli/) ·
[Examples index](https://abdelstark.github.io/worldforge/examples/)

<details>
<summary><strong>Python API sample</strong></summary>

```python
from worldforge import Action, BBox, Position, SceneObject, StructuredGoal, WorldForge

forge = WorldForge()
world = forge.create_world("kitchen", provider="mock")

world.add_object(
    SceneObject(
        "red_mug",
        Position(0.0, 0.8, 0.0),
        BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
    )
)

prediction = world.predict(Action.move_to(0.3, 0.8, 0.0), steps=2)
print(prediction.provider, prediction.physics_score)

plan = world.plan(
    goal_spec=StructuredGoal.object_at(
        object_name="red_mug",
        position=Position(0.3, 0.8, 0.0),
    )
)
print(plan.action_count, plan.success_probability)

doctor = forge.doctor()
print(doctor.healthy_provider_count, doctor.provider_count)
```

</details>

<details>
<summary><strong>CLI sample</strong></summary>

```bash
uv run worldforge examples                                              # runnable scripts index
uv run worldforge doctor --registered-only                              # active provider health
uv run worldforge world create lab --provider mock                      # save a local world
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0  # edit scene state
uv run worldforge world predict <world-id> --object-id <object-id> --x 0.4 --y 0.5 --z 0
uv run worldforge world list                                            # persisted worlds
uv run worldforge world objects <world-id>                              # scene objects
uv run worldforge world history <world-id>                              # object edits + predictions
uv run worldforge world preflight                                       # read-only local state diagnostics
uv run worldforge world migration-preview <world-id>                    # read-only schema review
uv run worldforge world export <world-id> --output world.json           # portable state JSON
uv run worldforge world delete <world-id>                               # remove local JSON state
uv run worldforge provider list                                         # registered providers
uv run worldforge provider info mock                                    # capability and lifecycle surface
uv run worldforge provider contract mock --format json                  # attachable contract evidence
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format json
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation generate --budget-file examples/benchmark-budget.json
```

Scene mutations append persisted history entries with typed action payloads. Position patches keep
the object's bounding box translated with the pose so saved snapshots stay coherent.

Full CLI reference: [worldforge/cli](https://abdelstark.github.io/worldforge/cli/).

</details>

## Capability Model

In WorldForge, a "capability" names an operation an adapter actually supports, not the upstream
model's branding.

| Capability | Signature | Example providers |
| --- | --- | --- |
| `predict` | `state + action → predicted state` | `mock` |
| `score` | `observations + goal + candidates → ranked candidates` | `leworldmodel` |
| `policy` | `observation + instruction → action chunks` | `cosmos-policy`, `gr00t`, `lerobot` |
| `generate` | `prompt + options → media artifact` | `cosmos`, `runway`, `mock` |
| `transfer` | `artifact + prompt/options → artifact` | `runway`, `mock` |
| `reason` | structured reasoning over state | `mock` |
| `embed` | observation → embedding | `mock` |
| `plan` | facade over composed surfaces | WorldForge facade |

Adapters can register a full `BaseProvider` or a narrow capability protocol implementation such
as a `Cost`, `Policy`, `Generator`, or `Predictor`. The protocol path is intentionally small:
declare `name`, optional profile metadata, and the one method behind the advertised capability.
Registered protocol implementations are visible through diagnostics, planning, and benchmarks
without forcing unrelated provider methods into the adapter.

LeWorldModel is a score provider, not a video generator. Cosmos-Policy, GR00T, and LeRobot are
policy providers, not predictive world models. Cosmos and Runway are media generators, not
controllable physical planning.

The canonical loop:

```text
observe state
  → propose candidate actions
  → score or roll out possible futures  (score / predict)
  → select an action sequence            (plan)
  → execute through a provider           (policy / predict)
  → persist, evaluate, observe again
```

## Provider Surfaces

<!-- provider-catalog-readme:start -->
| Provider | Maturity | Capability surface | Registration | Runtime ownership |
| --- | --- | --- | --- | --- |
| `mock` | `stable` | `predict`, `generate`, `transfer`, `reason`, `embed` | always registered | in-repo deterministic local provider |
| [`cosmos`](https://abdelstark.github.io/worldforge/providers/cosmos/) | `beta` | `generate` | `COSMOS_BASE_URL` | host supplies a reachable Cosmos deployment and optional `NVIDIA_API_KEY` |
| [`cosmos-policy`](https://abdelstark.github.io/worldforge/providers/cosmos-policy/) | `beta` | none (`policy` requires host `action_translator`) | `COSMOS_POLICY_BASE_URL` | WorldForge validates `/act` request/response and planning composition; host owns Cosmos-Policy reachability/CUDA/runtime, ALOHA observation construction, and translation of raw 14D rows into executable `Action` objects |
| [`runway`](https://abdelstark.github.io/worldforge/providers/runway/) | `beta` | `generate`, `transfer` | `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` | host supplies Runway credentials and persists returned artifacts |
| [`leworldmodel`](https://abdelstark.github.io/worldforge/providers/leworldmodel/) | `stable` | `score` | `LEWORLDMODEL_POLICY` or `LEWM_POLICY` | host installs the official LeWM loading path (`stable_worldmodel.policy.AutoCostModel`), torch, and compatible checkpoints |
| [`gr00t`](https://abdelstark.github.io/worldforge/providers/gr00t/) | `beta` | `policy` | `GROOT_POLICY_HOST` | host runs or reaches an Isaac GR00T policy server |
| [`lerobot`](https://abdelstark.github.io/worldforge/providers/lerobot/) | `stable` | `policy` | `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` | host installs LeRobot and compatible policy checkpoints |
| [`jepa`](https://abdelstark.github.io/worldforge/providers/jepa/) | `experimental` | `score` | `JEPA_MODEL_NAME` | host supplies torch, facebookresearch/jepa-wms runtime dependencies, and task preprocessing |
| [`genie`](https://abdelstark.github.io/worldforge/providers/genie/) | `scaffold` | scaffold | `GENIE_API_KEY` | capability-fail-closed reservation; Project Genie has no supported automation API contract |
<!-- provider-catalog-readme:end -->

`jepa` is a score-only adapter for host-owned `facebookresearch/jepa-wms` torch-hub runtimes.
`genie` remains a capability-closed reservation. Executable scaffold candidates stay outside
package exports and auto-registration until they have a validated runtime path, typed parser
coverage, request limits, and docs.

## Architecture

```text
  ┌──────────────────────────────────────────────┐
  │  Host application / CLI                      │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────┐
  │  WorldForge facade                           │
  │  catalog · registry · diagnostics · persist  │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────┐
  │  World runtime                               │
  │  state · history · planning · execution      │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────┐
  │  Provider adapter                            │
  │  capability contract · validation · events   │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────┐
  │  Upstream runtime or API                     │
  │  local model · policy server · media API     │
  └──────────────────────────────────────────────┘
```

## Development

Primary local gate (same as CI):

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run python scripts/check_core_performance.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

Before a tag, also run the locked dependency audit. The expanded gate and triage steps live in the
[operator playbooks](https://abdelstark.github.io/worldforge/playbooks/#9-prepare-a-release-or-public-branch).
If local setup fails before the gate starts, run
`uv run python scripts/contributor_doctor.py --format markdown` for a safe-to-attach diagnosis.

Scaffold a new provider:

```bash
uv run python scripts/scaffold_provider.py "Acme WM" \
  --taxonomy "JEPA latent predictive world model" \
  --implementation-status scaffold \
  --planned-capability score
```

Contributor guide: [CONTRIBUTING.md](./CONTRIBUTING.md). Repository agent context:
[AGENTS.md](./AGENTS.md).

## Citing WorldForge

If you use WorldForge in academic work, a BibTeX entry is:

```bibtex
@software{worldforge,
  title   = {WorldForge: An integration layer for physical-AI world models},
  author  = {AbdelStark and {WorldForge contributors}},
  year    = {2026},
  url     = {https://github.com/AbdelStark/worldforge},
  version = {0.5.0}
}
```

## Contributing

Issues, discussions, and pull requests are welcome. Please read
[CONTRIBUTING.md](./CONTRIBUTING.md) and open an issue for non-trivial changes before sending a
patch. For provider work, start with the
[provider authoring guide](https://abdelstark.github.io/worldforge/provider-authoring-guide/) and
the [playbooks](https://abdelstark.github.io/worldforge/playbooks/). External adopters can share
integration stories through the
[adoption case-study template](./docs/src/adoption-case-studies/README.md).

## License

WorldForge is released under the [MIT License](./LICENSE).

## Links

- Documentation: <https://abdelstark.github.io/worldforge/>
- Quickstart: <https://abdelstark.github.io/worldforge/quickstart/>
- Playbooks: <https://abdelstark.github.io/worldforge/playbooks/>
- Architecture: <https://abdelstark.github.io/worldforge/architecture/>
- World-model taxonomy: <https://abdelstark.github.io/worldforge/world-model-taxonomy/>
- Security policy: [SECURITY.md](./SECURITY.md)
- Repository: <https://github.com/AbdelStark/worldforge>
- Issues: <https://github.com/AbdelStark/worldforge/issues>

## Contributors

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/AbdelStark"><img src="https://avatars.githubusercontent.com/u/45264458?s=100" width="100px;" alt="Abdel"/><br /><sub><b>Abdel</b></sub></a><br /><a href="https://github.com/AbdelStark/worldforge/commits?author=AbdelStark" title="Code">💻</a> <a href="#ideas-AbdelStark" title="Ideas, Planning, & Feedback">🤔</a> <a href="#projectManagement-AbdelStark" title="Project Management">📆</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/0xLucqs"><img src="https://avatars.githubusercontent.com/u/70894690?s=100" width="100px;" alt="0xLucqs"/><br /><sub><b>0xLucqs</b></sub></a><br /><a href="https://github.com/AbdelStark/worldforge/commits?author=0xLucqs" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Th0rgal"><img src="https://avatars.githubusercontent.com/u/41830259?v=4?s=100" width="100px;" alt="Thomas Marchand"/><br /><sub><b>Thomas Marchand</b></sub></a><br /><a href="https://github.com/AbdelStark/worldforge/commits?author=Th0rgal" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/omarespejel"><img src="https://avatars.githubusercontent.com/u/4755430?v=4?s=100" width="100px;" alt="Omar U. Espejel"/><br /><sub><b>Omar U. Espejel</b></sub></a><br /><a href="https://github.com/AbdelStark/worldforge/commits?author=omarespejel" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/adrienlacombe"><img src="https://avatars.githubusercontent.com/u/6303520?v=4?s=100" width="100px;" alt="Adrien Lacombe"/><br /><sub><b>Adrien Lacombe</b></sub></a><br /><a href="https://github.com/AbdelStark/worldforge/commits?author=adrienlacombe" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

Made with love by [Abdel](https://github.com/AbdelStark) and the WorldForge community.
