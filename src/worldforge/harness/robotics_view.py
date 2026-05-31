"""Textual-free robotics showcase view helpers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from worldforge.harness import tensorboard_launcher

ROBOTICS_HELP_SECTION_CLASS = "robotics-help-section"
RoboticsRequiredArtifact = Literal["", "rerun", "tensorboard"]


@dataclass(frozen=True, slots=True)
class RoboticsHelpSectionSpec:
    text: str
    style_token: str = ""
    classes: str = ROBOTICS_HELP_SECTION_CLASS


@dataclass(frozen=True, slots=True)
class RoboticsTabletopHelpSpec:
    card_id: str
    title_id: str
    title: str
    sections: tuple[RoboticsHelpSectionSpec, ...]


@dataclass(frozen=True, slots=True)
class RoboticsBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


@dataclass(frozen=True, slots=True)
class RoboticsShowcaseStageSpec:
    stage_id: str
    message: str
    required_artifact: RoboticsRequiredArtifact = ""


@dataclass(frozen=True, slots=True)
class RoboticsShowcaseAppSpec:
    title: str
    subtitle: str
    body_id: str
    initial_progress_message: str
    default_stage_delay_s: float
    arm_frame_interval_s: float
    bindings: tuple[RoboticsBindingSpec, ...]
    stages: tuple[RoboticsShowcaseStageSpec, ...]

    @property
    def body_selector(self) -> str:
        return f"#{self.body_id}"


def robotics_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def robotics_nested(payload: dict[str, object], *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def robotics_candidate_targets(payload: dict[str, object]) -> list[dict[str, object]]:
    value = robotics_nested(payload, "visualization", "candidate_targets")
    return [dict(item) for item in value] if isinstance(value, list) else []


def robotics_scores(payload: dict[str, object]) -> list[float]:
    value = robotics_nested(payload, "score_result", "scores")
    if not isinstance(value, list):
        return []
    scores: list[float] = []
    for item in value:
        number = robotics_number(item)
        if number is not None:
            scores.append(number)
    return scores


def robotics_selected_index(payload: dict[str, object]) -> int | None:
    value = robotics_nested(payload, "score_result", "best_index")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def robotics_event_duration(
    payload: dict[str, object],
    *,
    provider: str,
    operation: str,
) -> float | None:
    events = payload.get("provider_events")
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        if event.get("provider") == provider and event.get("operation") == operation:
            return robotics_number(event.get("duration_ms"))
    return None


def robotics_final_position(payload: dict[str, object]) -> dict[str, float] | None:
    position = robotics_nested(payload, "execution", "final_block_position")
    if not isinstance(position, dict):
        return None
    x = robotics_number(position.get("x"))
    y = robotics_number(position.get("y"))
    z = robotics_number(position.get("z"))
    if x is None or y is None or z is None:
        return None
    return {"x": x, "y": y, "z": z}


def robotics_rerun_recording_path(payload: dict[str, object]) -> Path | None:
    rerun = payload.get("rerun")
    if not isinstance(rerun, dict):
        return None
    save_path = rerun.get("save_path")
    if not isinstance(save_path, str) or not save_path.strip():
        return None
    path = Path(save_path).expanduser()
    return path if path.is_absolute() else path.resolve()


def robotics_rerun_viewer_command(path: Path) -> list[str]:
    return [
        "uvx",
        "--from",
        "rerun-sdk>=0.24,<0.32",
        "rerun",
        str(path),
    ]


def robotics_rerun_viewer_command_text(path: Path) -> str:
    return " ".join(shlex.quote(part) for part in robotics_rerun_viewer_command(path))


def robotics_tensorboard_log_dir(payload: dict[str, object]) -> Path | None:
    tensorboard = payload.get("tensorboard")
    if not isinstance(tensorboard, dict):
        return None
    log_dir = tensorboard.get("log_dir")
    if not isinstance(log_dir, str) or not log_dir.strip():
        return None
    path = Path(log_dir).expanduser()
    return path if path.is_absolute() else path.resolve()


ROBOTICS_TENSORBOARD_DEFAULT_PORT = tensorboard_launcher.DEFAULT_PORT
ROBOTICS_TENSORBOARD_READY_TIMEOUT_S = tensorboard_launcher.DEFAULT_READY_TIMEOUT_S
ROBOTICS_TENSORBOARD_POLL_INTERVAL_S = tensorboard_launcher.DEFAULT_POLL_INTERVAL_S
ROBOTICS_TENSORBOARD_STDOUT_LOG = tensorboard_launcher.STDOUT_LOG
ROBOTICS_TENSORBOARD_STDERR_LOG = tensorboard_launcher.STDERR_LOG
ROBOTICS_TABLETOP_WIDTH = 62
ROBOTICS_TABLETOP_HEIGHT = 12
ROBOTICS_TABLETOP_START = (0.0, 0.5)
ROBOTICS_TABLETOP_GOAL = (0.5, 0.5)
ROBOTICS_SHOWCASE_DEFAULT_STAGE_DELAY_S = 0.35
ROBOTICS_ARM_FRAME_INTERVAL_S = 0.32


def tensorboard_port_open(host: str, port: int, *, timeout: float = 1.0) -> bool:
    """Return True when a TCP connect to ``host:port`` succeeds within ``timeout``."""

    return tensorboard_launcher.port_open(host, port, timeout=timeout)


def robotics_tensorboard_viewer_command(path: Path) -> list[str]:
    return tensorboard_launcher.viewer_command(
        path,
        port=ROBOTICS_TENSORBOARD_DEFAULT_PORT,
    )


def robotics_tensorboard_viewer_command_text(path: Path) -> str:
    return tensorboard_launcher.viewer_command_text(
        path,
        port=ROBOTICS_TENSORBOARD_DEFAULT_PORT,
    )


def robotics_tensorboard_url() -> str:
    return tensorboard_launcher.viewer_url(port=ROBOTICS_TENSORBOARD_DEFAULT_PORT)


def robotics_color(token: str) -> str:
    return {
        "accent": "cyan",
        "success": "green",
        "warning": "yellow",
        "muted": "bright_black",
        "panel": "blue",
    }.get(token, "white")


ROBOTICS_REPORT_GUIDE_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "Runtime bars",
        "policy, score, plan, and total are wall-clock milliseconds for the completed run.",
        "Policy is the LeRobot checkpoint call; score is the LeWorldModel cost call.",
    ),
    (
        "Tensor contract",
        "tensor MB and elements describe the preprocessed score tensors sent to LeWorldModel.",
        "They explain runtime size and shape, not physical skill or task success by themselves.",
    ),
    (
        "Candidate ranking",
        "lower cost wins; SELECTED is the action chunk WorldForge mock-replays.",
        "The selected row should agree with the tabletop target/final marker and best_index.",
    ),
)

ROBOTICS_TABLETOP_DIAGRAM = """Tabletop replay
---------------
legend: S=start, G=goal, T=selected target, F=mock final, X=selected+final
selected candidate: #2
+------------------------------------------+
|                                          |
|                                          |
|                                          |
|                               0          |
|                          1               |
|                                          |
|S                   G                     |
|                                          |
|               X                          |
|                                          |
|                                          |
|                                          |
|                                          |
+------------------------------------------+
x=0.00             x=0.50             x=1.00"""

ROBOTICS_TABLETOP_HELP_TEXT = (
    "Read the tabletop replay as a top-down map of the PushT workspace. "
    "S is the start, G is the goal, numbered marks are non-selected policy "
    "candidates, T is the selected target, F is the mock final position, and "
    "X means the selected target and mock final state overlap on the same rendered cell. "
    "Mentally: LeRobot proposes possible pushes, LeWorldModel assigns costs, "
    "WorldForge picks the lowest-cost candidate, then the local mock world replays that action. "
    "This is a planning visualization, not a hardware camera feed or robot-control trace."
)
ROBOTICS_TABLETOP_HELP_ELI5_TEXT = (
    "ELI5: the policy suggests a few pushes, the world model scores them, "
    "WorldForge chooses the cheapest one, and the mock world shows where that "
    "choice ended. If T and F overlap, the map prints X."
)
ROBOTICS_TABLETOP_HELP_BOUNDARY_TEXT = (
    "Boundary: this visualizes simulation/replay planning only. It is not a "
    "hardware command stream, safety check, or physical success proof."
)
ROBOTICS_TABLETOP_HELP_SCREEN_SPEC = RoboticsTabletopHelpSpec(
    card_id="robotics-help-card",
    title_id="robotics-help-title",
    title="Reading the tabletop replay",
    sections=(
        RoboticsHelpSectionSpec(ROBOTICS_TABLETOP_HELP_TEXT),
        RoboticsHelpSectionSpec(ROBOTICS_TABLETOP_DIAGRAM, style_token="success"),
        RoboticsHelpSectionSpec(ROBOTICS_TABLETOP_HELP_ELI5_TEXT),
        RoboticsHelpSectionSpec(ROBOTICS_TABLETOP_HELP_BOUNDARY_TEXT),
    ),
)
ROBOTICS_TABLETOP_HELP_BINDING_SPECS: tuple[RoboticsBindingSpec, ...] = (
    RoboticsBindingSpec("escape", "dismiss", "Close"),
    RoboticsBindingSpec("q", "dismiss", "Close", show=False),
)
ROBOTICS_SHOWCASE_APP_SPEC = RoboticsShowcaseAppSpec(
    title="WorldForge Robotics Showcase",
    subtitle="LeRobot policy + LeWorldModel checkpoint scoring replay",
    body_id="robotics-body",
    initial_progress_message="Preparing visual replay from completed real inference summary...",
    default_stage_delay_s=ROBOTICS_SHOWCASE_DEFAULT_STAGE_DELAY_S,
    arm_frame_interval_s=ROBOTICS_ARM_FRAME_INTERVAL_S,
    bindings=(
        RoboticsBindingSpec("?", "show_tabletop_help", "Help"),
        RoboticsBindingSpec("o", "open_rerun", "Open Rerun"),
        RoboticsBindingSpec("t", "open_tensorboard", "Open TensorBoard"),
        RoboticsBindingSpec("q", "quit", "Quit"),
        RoboticsBindingSpec("ctrl+t", "toggle_theme", "Theme"),
    ),
    stages=(
        RoboticsShowcaseStageSpec("hero", "Loaded real policy + score summary."),
        RoboticsShowcaseStageSpec("pipeline", "Tracing the policy-to-world-model pipeline."),
        RoboticsShowcaseStageSpec(
            "guide",
            "Explaining how to read the runtime, tensor, and candidate panes.",
        ),
        RoboticsShowcaseStageSpec(
            "rerun",
            "Attaching Rerun artifact location and viewer command.",
            required_artifact="rerun",
        ),
        RoboticsShowcaseStageSpec(
            "tensorboard",
            "Attaching TensorBoard log directory and viewer command.",
            required_artifact="tensorboard",
        ),
        RoboticsShowcaseStageSpec("metrics", "Rendering latency and tensor contract metrics."),
        RoboticsShowcaseStageSpec(
            "arm",
            "Animating the selected action chunk as an illustrative arm replay.",
        ),
        RoboticsShowcaseStageSpec(
            "candidates",
            "Ranking LeRobot action candidates by LeWorldModel cost.",
        ),
        RoboticsShowcaseStageSpec(
            "tabletop",
            "Drawing the tabletop replay with stable markers.",
        ),
        RoboticsShowcaseStageSpec("events", "Attaching provider event log."),
    ),
)
ROBOTICS_SHOWCASE_BODY_SELECTOR = ROBOTICS_SHOWCASE_APP_SPEC.body_selector


def robotics_showcase_stage_enabled(
    stage: RoboticsShowcaseStageSpec,
    *,
    has_rerun_recording: bool,
    has_tensorboard_logs: bool,
) -> bool:
    if stage.required_artifact == "rerun":
        return has_rerun_recording
    if stage.required_artifact == "tensorboard":
        return has_tensorboard_logs
    return True


def robotics_tabletop_map_lines(summary: dict[str, object]) -> list[str]:
    cells = robotics_tabletop_cells(summary)
    lines = ["+" + "-" * ROBOTICS_TABLETOP_WIDTH + "+"]
    lines.extend(robotics_tabletop_row(cells, row) for row in range(ROBOTICS_TABLETOP_HEIGHT))
    lines.append("+" + "-" * ROBOTICS_TABLETOP_WIDTH + "+")
    lines.append("x=0.00                         x=0.50                         x=1.00")
    return lines


def robotics_tabletop_cells(summary: dict[str, object]) -> dict[tuple[int, int], set[str]]:
    cells: dict[tuple[int, int], set[str]] = {}
    selected = robotics_selected_index(summary)
    place_robotics_tabletop_marker(cells, *ROBOTICS_TABLETOP_START, marker="S")
    place_robotics_tabletop_marker(cells, *ROBOTICS_TABLETOP_GOAL, marker="G")
    for target in robotics_candidate_targets(summary):
        index = int(target.get("index", -1))
        x = robotics_number(target.get("x"))
        y = robotics_number(target.get("y"))
        if x is None or y is None:
            continue
        marker = "T" if index == selected else str(index % 10)
        place_robotics_tabletop_marker(cells, x, y, marker=marker)
    final_position = robotics_final_position(summary)
    if final_position is not None:
        place_robotics_tabletop_marker(
            cells,
            final_position["x"],
            final_position["y"],
            marker="F",
        )
    return cells


def place_robotics_tabletop_marker(
    cells: dict[tuple[int, int], set[str]],
    x: float,
    y: float,
    *,
    marker: str,
) -> None:
    column = max(0, min(ROBOTICS_TABLETOP_WIDTH - 1, round(x * (ROBOTICS_TABLETOP_WIDTH - 1))))
    row = max(
        0,
        min(ROBOTICS_TABLETOP_HEIGHT - 1, round((1.0 - y) * (ROBOTICS_TABLETOP_HEIGHT - 1))),
    )
    cells.setdefault((row, column), set()).add(marker)


def robotics_tabletop_row(cells: dict[tuple[int, int], set[str]], row: int) -> str:
    characters = [
        robotics_tabletop_cell_marker(cells.get((row, column), set()))
        for column in range(ROBOTICS_TABLETOP_WIDTH)
    ]
    return "|" + "".join(characters) + "|"


def robotics_tabletop_cell_marker(markers: set[str]) -> str:
    if not markers:
        return " "
    if "F" in markers and "T" in markers:
        return "X"
    if "F" in markers:
        return "F"
    if "T" in markers:
        return "T"
    if len(markers) > 1:
        return "*"
    return next(iter(markers))
