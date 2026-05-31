# TensorBoard Integration

WorldForge ships an optional TensorBoard bridge for inspecting the LeWorldModel
checkpoint used during local inference in the robotics showcase. It writes
sanitized provenance text, latency and cost scalars, a histogram of candidate
costs, and a per-event text feed to a local ``tfevents`` log directory.

The integration is host-owned and local-only:

- TensorBoard is **not** a provider capability and the catalog never advertises
  it.
- The base WorldForge install does **not** depend on ``tensorboard`` or
  ``torch``. The bridge module imports the SDK lazily so the integration is a
  no-op when the optional extra is absent.
- ``tfevents`` files stay under the host-chosen log directory. WorldForge never
  uploads them to a hosted service.

## What you see in TensorBoard

| Tag prefix | Plugin | What it shows |
| --- | --- | --- |
| ``worldforge/leworldmodel/checkpoint/*`` | Text, Scalars | LeWorldModel checkpoint path, policy, repo, revision, provenance JSON, and a `created` indicator. |
| ``worldforge/leworldmodel/robotics_showcase/*`` | Text | Task description, checkpoint display path, state directory, sanitized JSON of the full run summary, inputs, and health snapshot. |
| ``worldforge/leworldmodel/scores/*`` | Scalars, Histogram | Per-candidate costs, min/max/mean, best index, best score, and a histogram of the cost distribution. |
| ``worldforge/leworldmodel/metrics/*`` | Scalars | Score stats and end-to-end latency metrics from the summary. |
| ``worldforge/leworldmodel/events/<provider>/<operation>/*`` | Scalars, Text | Per-event attempt count, duration, status code, failure/retry flags, and the sanitized event message. |
| ``worldforge/leworldmodel/weights/*`` | Histogram | Optional per-parameter weight distributions when a host passes a state dict to ``log_state_dict_histograms``. |

The bridge sanitizes secret-like ``key=value`` fragments and signed-URL query
parameters before writing text panels, so ``tfevents`` files are safe to share
in adoption stories or evidence bundles.

## Install

```bash
uv add "worldforge-ai[tensorboard]"
```

For repository development:

```bash
uv sync --group dev --extra tensorboard
```

The extra installs ``tensorboard>=2.16,<3``. Base WorldForge still depends only
on ``httpx``. If the host already provides ``torch.utils.tensorboard`` (for
example, through an existing PyTorch install) the bridge uses that;
``tensorboardX`` is accepted as a fallback when both ``torch`` and
``tensorboard`` are absent.

## Robotics showcase flags

``scripts/robotics-showcase`` enables the bridge by default when an interactive
showcase is requested:

| Flag | Default | Purpose |
| --- | --- | --- |
| ``--tensorboard`` | implied (unless ``--no-tensorboard`` / ``--health-only`` / ``--json-only``) | Enable the writer with a default log dir under ``.worldforge/tensorboard/``. |
| ``--tensorboard-logdir <path>`` | ``.worldforge/tensorboard`` | Override the destination directory. Relative paths resolve against the repo root. |
| ``--tensorboard-run-name <name>`` | timestamped name | Subdirectory under ``--tensorboard-logdir`` for this run. Pick a stable name to make repeated runs comparable in the same TensorBoard view. |
| ``--tensorboard-flush-secs <int>`` | ``30`` | Flush interval (seconds) for the ``SummaryWriter``. |
| ``--no-tensorboard`` | off | Disable the wrapper's default TensorBoard recording. |

A typical inspection workflow:

```bash
# Record a real LeRobot + LeWorldModel run (TensorBoard enabled by default).
scripts/robotics-showcase --json-only --no-tui --no-rerun

# Open the run alongside the published checkpoint.
uvx --from "tensorboard>=2.16,<3" tensorboard --logdir .worldforge/tensorboard
```

For an explicit destination:

```bash
scripts/robotics-showcase \
  --tensorboard-logdir .worldforge/tensorboard/pusht \
  --tensorboard-run-name baseline \
  --no-tui --no-rerun --json-only
```

The summary JSON gains a ``"tensorboard"`` block listing ``log_dir``,
``run_name``, ``flush_secs``, and an ``events_written`` flag that mirrors what
the wrapper would show under the ``Artifacts`` section of the visual report.

The Textual showcase report (`worldforge.harness.tui.RoboticsShowcaseApp`)
surfaces the run with a ``RoboticsTensorBoardPane`` and a ``t`` keybinding that
launches
``uvx --from "tensorboard>=2.16,<3" --with "setuptools<81" tensorboard --logdir <path> --port 6006``
in a detached subprocess. The ``setuptools<81`` constraint keeps
``pkg_resources`` available for TensorBoard's import path (TensorBoard still
calls ``import pkg_resources`` at startup but ``setuptools>=81`` removed that
package). The shortcut is also visible in the footer alongside ``o`` for Rerun.

Because TensorBoard is a web server (not a GUI app like Rerun), the binding
then runs a Textual background worker that polls ``localhost:6006`` every
~0.5 s for up to ~60 s and only opens the browser to ``http://localhost:6006/``
once the port responds. This survives a slow first-run ``uvx`` resolve where
TensorBoard takes longer than a couple of seconds to bind. The URL is surfaced
in the pane and in the notification so headless / remote users can copy-paste
it (or set up an SSH tunnel). If ``webbrowser`` cannot find a default browser,
the binding emits a warning telling the user to visit the URL manually.

The TensorBoard subprocess's ``stdout`` and ``stderr`` are captured to
``tensorboard.stdout.log`` and ``tensorboard.stderr.log`` next to the run's
``events.out.tfevents.*`` files. When the server never comes up within the
poll window, the binding emits an error notification pointing at the stderr
log so the failure is debuggable rather than silent.

If the summary lacks a ``"tensorboard"`` block (for example when
``--no-tensorboard`` is passed), the pane is omitted, no subprocess is
started, no browser is opened, and the keybinding emits a warning
notification instead.

## Non-interactive launcher (`worldforge-open-tensorboard`)

The same launch / poll / probe flow is available as a CLI for non-interactive
use - validating the wiring in CI, opening TensorBoard from a shell without
running the Textual report, or testing changes to the launch command:

```bash
uv run worldforge-open-tensorboard --logdir .worldforge/tensorboard/<run>
```

Common flags:

| Flag | Default | Purpose |
| --- | --- | --- |
| ``--logdir <path>`` | required | Run directory with ``events.out.tfevents.*`` files. |
| ``--port <int>`` | ``6006`` | TCP port to bind. |
| ``--host <host>`` | ``localhost`` | Host to poll and probe. |
| ``--ready-timeout <sec>`` | ``60`` | How long to wait for the port to bind. |
| ``--poll-interval <sec>`` | ``0.5`` | Seconds between TCP probes during the ready wait. |
| ``--probe`` | off | After ready, fetch ``http://host:port/`` and assert the body contains the ``TensorBoard`` marker. Tears the subprocess down on success or failure. Useful for "did it actually work" smoke checks. |
| ``--no-browser`` | off | Skip ``webbrowser.open`` after the server is ready. |
| ``--keep-running`` | off (implied without ``--probe``) | Block until the subprocess exits or SIGINT is received. |
| ``--shutdown-timeout <sec>`` | ``5`` | Seconds to wait for graceful subprocess teardown. |

Exit codes: ``0`` on success, ``1`` on ready timeout or probe failure, ``2``
on bad input (missing ``--logdir``, non-positive timing, launch ``OSError``).

Example smoke check:

```bash
mkdir -p /tmp/tb-smoke
uv run worldforge-open-tensorboard \
  --logdir /tmp/tb-smoke \
  --probe --no-browser \
  --ready-timeout 120
```

## Programmatic surface

Hosts that already drive WorldForge directly can use the bridge without going
through the showcase script. The public surface mirrors
``worldforge.rerun`` and lives in ``worldforge.tensorboard``:

```python
from worldforge.tensorboard import (
    TensorBoardCheckpointInspector,
    TensorBoardLogConfig,
    TensorBoardSession,
    create_tensorboard_inspector,
)

inspector = create_tensorboard_inspector(
    log_dir=".worldforge/tensorboard/checkpoint-inspection",
    run_name="baseline",
)
inspector.log_checkpoint_summary(
    {
        "output": "/path/to/pusht/lewm_object.ckpt",
        "policy": "pusht/lewm",
        "repo_id": "galilai/lewm-pusht",
        "revision": "<commit-sha>",
    }
)
inspector.log_score_distribution(scores, best_index=1, best_score=scores[1])
inspector.log_metrics({"plan_latency_ms": 25.0, "total_latency_ms": 30.0})

# Optional: surface per-parameter weight histograms when host has the live
# checkpoint loaded. Tensor-like values (``detach``/``cpu``/``numpy``) are
# flattened automatically.
inspector.log_state_dict_histograms(model.state_dict())

inspector.flush()
inspector.close()
```

The session is initialized lazily, so constructing an inspector is free of side
effects until the first ``log_*`` call. ``close()`` is idempotent.

## Boundaries

- The bridge never advertises ``predict``, ``embed``, ``plan``, ``score``, or ``policy``
  capabilities. It is purely
  observability.
- The bridge never imports torch on its own. Weight histograms require the host
  to pass tensor-like objects through ``log_state_dict_histograms`` -
  appropriate when the LeWorldModel runtime is already loaded host-side.
- The bridge never reads ``.env`` or any other secret file. Provider event
  messages are sanitized in :mod:`worldforge.models` before they reach the
  bridge; the bridge then applies a second pass that strips ``api_key=``,
  ``token=``, ``secret=``, ``signature=``, and signed-URL ``?signature=`` /
  ``?token=`` query fragments before writing text panels.
- ``tfevents`` files stay local. If you want to share a TensorBoard run as
  release evidence, archive the log directory the same way you archive any
  other showcase artifact.
