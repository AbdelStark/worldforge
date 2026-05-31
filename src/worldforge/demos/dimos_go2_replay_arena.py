"""Checkout-safe DimOS Go2 replay arena for decision-evidence experiments."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge import Action, ActionScoreResult, WorldForge
from worldforge.artifact_io import write_json_artifact
from worldforge.models import JSONDict, WorldForgeError, require_finite_number
from worldforge.providers.base import ProviderProfileSpec

_REPO_FIXTURE_RELATIVE_PATH = (
    Path("examples") / "dimos-go2-replay-arena" / "fixtures" / "go2_office_replay_frame.json"
)
DEFAULT_FIXTURE_PATH = (
    Path.cwd() / _REPO_FIXTURE_RELATIVE_PATH
    if (Path.cwd() / _REPO_FIXTURE_RELATIVE_PATH).is_file()
    else Path(__file__).resolve().parents[3] / _REPO_FIXTURE_RELATIVE_PATH
)

_PROGRESS_REWARD_WEIGHT = 0.25
_OBSTACLE_CLEARANCE_PENALTY_SCALE = 4.0
_SAFETY_ACTION_RELOCALIZATION_COST = 0.08
_UNCERTAIN_MOTION_BASE_COST = 0.6


@dataclass(frozen=True, slots=True)
class Go2ReplayArenaResult:
    trace: JSONDict
    report_markdown: str
    decision_trace_path: Path
    report_path: Path


@dataclass(frozen=True, slots=True)
class _Pose2D:
    x: float
    y: float
    yaw_rad: float


@dataclass(frozen=True, slots=True)
class _ScoredCandidate:
    action_id: str
    action: JSONDict
    endpoint: JSONDict
    total_cost: float
    components: JSONDict


class Go2ReplayScoreProvider:
    """Transparent score provider for a single Go2 replay fixture."""

    name = "dimos-go2-replay-score"
    profile = ProviderProfileSpec(
        description="Checkout-safe deterministic scorer for DimOS Go2 replay candidates.",
        implementation_status="demo",
        is_local=True,
        deterministic=True,
    )

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        observation, goal = _score_info_payload(info)
        candidates = _candidate_payloads(action_candidates)
        scored = [
            _score_candidate(candidate[0], observation=observation, goal=goal)
            for candidate in candidates
        ]
        scores = [candidate.total_cost for candidate in scored]
        best_index = min(range(len(scores)), key=lambda index: (scores[index], index))
        return ActionScoreResult(
            provider=self.name,
            scores=scores,
            best_index=best_index,
            metadata={
                "score_source": "deterministic transparent replay scoring",
                "candidate_count": len(scored),
                "scored_candidates": [_scored_candidate_payload(candidate) for candidate in scored],
            },
        )


def run_dimos_go2_replay_arena_workflow(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    output_dir: Path = Path(".worldforge/dimos-go2-replay-arena"),
) -> JSONDict:
    result = run_dimos_go2_replay_arena(fixture_path, output_dir)
    return {
        "selected_action_id": result.trace["selected_action"]["id"],
        "score_margin": result.trace["score_margin"],
        "baseline_regret": result.trace["baseline_regret"],
        "decision_trace_path": str(result.decision_trace_path),
        "report_path": str(result.report_path),
    }


def run_dimos_go2_replay_arena(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    output_dir: Path = Path(".worldforge/dimos-go2-replay-arena"),
) -> Go2ReplayArenaResult:
    fixture = load_go2_replay_fixture(fixture_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    forge = WorldForge(state_dir=output_dir / "worlds", auto_register_remote=False)
    forge.register_cost(Go2ReplayScoreProvider())
    world = forge.create_world(fixture["scenario_id"], provider="mock")
    candidate_plans = _candidate_action_plans(fixture)
    score_info = {"observation": fixture["observation"], "goal": fixture["goal"]}
    plan = world.plan(
        goal=str(fixture["goal"]["description"]),
        score_provider=Go2ReplayScoreProvider.name,
        score_info=score_info,
        candidate_actions=candidate_plans,
    )
    trace = _decision_trace(fixture, plan)
    report_markdown = render_go2_replay_report(trace)

    decision_trace_path = output_dir / "decision-trace.json"
    report_path = output_dir / "report.md"
    write_json_artifact(decision_trace_path, trace)
    report_path.write_text(report_markdown, encoding="utf-8")
    return Go2ReplayArenaResult(
        trace=trace,
        report_markdown=report_markdown,
        decision_trace_path=decision_trace_path,
        report_path=report_path,
    )


def load_go2_replay_fixture(path: Path) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        message = f"Go2 replay fixture not found: {path}"
        if path == DEFAULT_FIXTURE_PATH:
            message += (
                ". The bundled default is repo-local; pass --fixture with a checkout fixture "
                "or replay export when running from an installed wheel."
            )
        raise WorldForgeError(message) from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Go2 replay fixture is invalid JSON: {path}") from exc
    _validate_fixture(payload)
    return payload


def render_go2_replay_report(trace: JSONDict) -> str:
    selected = trace["selected_action"]
    best = trace["scored_candidates"][0]
    rejected = trace["scored_candidates"][1:4]
    lines = [
        "# DimOS Go2 Replay Arena",
        "",
        f"- Scenario: `{trace['scenario_id']}`",
        f"- Selected action: `{selected['id']}`",
        f"- Score margin: `{trace['score_margin']:.6f}`",
        f"- Baseline regret: `{trace['baseline_regret']:.6f}`",
        f"- WorldForge value: `{trace['worldforge_value']}`",
        "",
        "## Why Selected",
        "",
        (
            f"`{selected['id']}` had the lowest transparent cost: "
            f"distance `{best['components']['distance_cost']:.3f}`, "
            f"obstacle `{best['components']['obstacle_risk']:.3f}`, "
            f"map `{best['components']['map_cost']:.3f}`, "
            f"uncertainty `{best['components']['uncertainty_cost']:.3f}`, "
            f"relocalization `{best['components']['relocalization_cost']:.3f}`."
        ),
        "",
        "## Top Counterfactuals",
        "",
    ]
    if rejected:
        lines.extend(
            (
                f"- `{candidate['action_id']}` cost `{candidate['total_cost']:.6f}` "
                f"endpoint `({candidate['endpoint']['x']:.2f}, {candidate['endpoint']['y']:.2f})`"
            )
            for candidate in rejected
        )
    else:
        lines.append("- No rejected counterfactuals available.")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            (
                "Checkout-safe replay fixture only; no DimOS import, browser simulator, hardware "
                "connection, or learned world-model claim."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _validate_fixture(payload: object) -> None:
    if not isinstance(payload, dict):
        raise WorldForgeError("Go2 replay fixture must be a JSON object.")
    for field_name in ("scenario_id", "observation", "goal", "candidate_actions"):
        if field_name not in payload:
            raise WorldForgeError(f"Go2 replay fixture is missing '{field_name}'.")
    if payload.get("schema_version") != 1:
        raise WorldForgeError("Go2 replay fixture schema_version must be 1.")
    observation = _require_mapping(payload["observation"], "observation")
    _require_fields(
        observation,
        ("frame_id", "timestamp_s", "pose", "localization_confidence", "map"),
        "observation",
    )
    pose = _require_mapping(observation["pose"], "observation.pose")
    _require_fields(pose, ("x", "y", "yaw_rad"), "observation.pose")
    _number(observation["timestamp_s"], name="observation.timestamp_s")
    _number(observation["localization_confidence"], name="observation.localization_confidence")
    _number(pose["x"], name="observation.pose.x")
    _number(pose["y"], name="observation.pose.y")
    _number(pose["yaw_rad"], name="observation.pose.yaw_rad")
    _require_mapping(observation["map"], "observation.map")

    goal = _require_mapping(payload["goal"], "goal")
    _require_fields(goal, ("description", "x", "y"), "goal")
    _number(goal["x"], name="goal.x")
    _number(goal["y"], name="goal.y")

    if not isinstance(payload["candidate_actions"], list) or not payload["candidate_actions"]:
        raise WorldForgeError("Go2 replay fixture candidate_actions must be a non-empty list.")
    for index, candidate in enumerate(payload["candidate_actions"]):
        candidate_map = _require_mapping(candidate, f"candidate_actions[{index}]")
        _require_fields(candidate_map, ("id", "type", "parameters"), f"candidate_actions[{index}]")
        _require_mapping(candidate_map["parameters"], f"candidate_actions[{index}].parameters")


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorldForgeError(f"Go2 replay fixture '{field_name}' must be a JSON object.")
    return value


def _require_fields(
    payload: Mapping[str, Any],
    field_names: Sequence[str],
    parent_name: str,
) -> None:
    for field_name in field_names:
        if field_name not in payload:
            raise WorldForgeError(f"Go2 replay fixture {parent_name} is missing '{field_name}'.")


def _candidate_action_plans(fixture: JSONDict) -> list[list[Action]]:
    return [
        [
            Action(
                kind=str(candidate["type"]),
                parameters={
                    **candidate["parameters"],
                    "action_id": str(candidate["id"]),
                },
            )
        ]
        for candidate in fixture["candidate_actions"]
    ]


def _candidate_payloads(action_candidates: object) -> list[list[JSONDict]]:
    if not isinstance(action_candidates, list) or not action_candidates:
        raise WorldForgeError("Go2 replay scorer requires a non-empty action candidate list.")
    validated_candidates: list[list[JSONDict]] = []
    for index, candidate in enumerate(action_candidates):
        if not isinstance(candidate, list) or len(candidate) != 1:
            raise WorldForgeError(f"Go2 replay candidate {index} must be a one-action plan.")
        action = candidate[0]
        if not isinstance(action, Mapping):
            raise WorldForgeError(f"Go2 replay candidate {index} action must be a JSON object.")
        validated_candidates.append([dict(action)])
    return validated_candidates


def _score_info_payload(info: JSONDict) -> tuple[JSONDict, JSONDict]:
    for field_name in ("observation", "goal"):
        if field_name not in info:
            raise WorldForgeError(f"Go2 replay score info is missing '{field_name}'.")
    observation = _require_score_mapping(info["observation"], "observation")
    goal = _require_score_mapping(info["goal"], "goal")
    return observation, goal


def _require_score_mapping(value: object, field_name: str) -> JSONDict:
    if not isinstance(value, Mapping):
        raise WorldForgeError(f"Go2 replay score info '{field_name}' must be a JSON object.")
    return dict(value)


def _decision_trace(fixture: JSONDict, plan: Any) -> JSONDict:
    try:
        score_result = plan.metadata["score_result"]
    except KeyError as exc:
        raise WorldForgeError(
            "Go2 replay arena expected 'score_result' in plan metadata; "
            f"got keys: {sorted(plan.metadata)}"
        ) from exc
    scored_candidates = sorted(
        score_result["metadata"]["scored_candidates"],
        key=lambda candidate: (candidate["total_cost"], candidate["action_id"]),
    )
    best = scored_candidates[0]
    second_best = scored_candidates[1] if len(scored_candidates) > 1 else best
    baseline = _candidate_by_id(scored_candidates, str(fixture.get("baseline_action_id", "")))
    score_margin = float(second_best["total_cost"]) - float(best["total_cost"])
    baseline_regret = (
        float(baseline["total_cost"]) - float(best["total_cost"]) if baseline is not None else 0.0
    )
    return {
        "schema_version": 1,
        "artifact_kind": "worldforge.dimos_go2_replay_decision_trace",
        "scenario_id": fixture["scenario_id"],
        "source": fixture.get("source", {}),
        "goal": fixture["goal"],
        "observation": {
            "frame_id": fixture["observation"]["frame_id"],
            "timestamp_s": fixture["observation"]["timestamp_s"],
            "pose": fixture["observation"]["pose"],
            "localization_confidence": fixture["observation"]["localization_confidence"],
        },
        "candidate_count": len(scored_candidates),
        "selected_action": {
            "id": best["action_id"],
            "action": best["action"],
            "endpoint": best["endpoint"],
            "total_cost": best["total_cost"],
            "components": best["components"],
        },
        "baseline_action_id": fixture.get("baseline_action_id"),
        "baseline_regret": baseline_regret,
        "score_margin": score_margin,
        "worldforge_value": _worldforge_value(score_margin, baseline_regret),
        "scored_candidates": scored_candidates,
        "plan_metadata": {
            "planning_mode": plan.metadata["planning_mode"],
            "score_provider": plan.provider,
            "success_probability": plan.success_probability,
            "workflow_trace": plan.metadata["workflow_trace"],
        },
    }


def _worldforge_value(score_margin: float, baseline_regret: float) -> str:
    if baseline_regret > 0.0 and score_margin > 0.0:
        return "selected lower-cost action than baseline and exposed counterfactual margin"
    if score_margin > 0.0:
        return "ranked alternatives with a positive counterfactual margin"
    return "no demonstrated value beyond logging; pivot if this persists"


def _score_candidate(
    action: JSONDict,
    *,
    observation: JSONDict,
    goal: JSONDict,
) -> _ScoredCandidate:
    action_id = str(action["parameters"].get("action_id", action["type"]))
    endpoint = _simulate_endpoint(action, observation=observation)
    start_pose = _pose(observation["pose"])
    goal_xy = (_number(goal["x"], name="goal.x"), _number(goal["y"], name="goal.y"))
    start_distance = math.dist((start_pose.x, start_pose.y), goal_xy)
    endpoint_distance = math.dist((endpoint.x, endpoint.y), goal_xy)
    progress = start_distance - endpoint_distance
    obstacle_risk = _obstacle_risk(start_pose, endpoint, observation["map"])
    map_cost = _zone_cost(endpoint, observation["map"].get("cost_zones", []))
    uncertainty_cost = _zone_cost(endpoint, observation["map"].get("uncertainty_zones", []))
    relocalization_cost = _relocalization_cost(action, observation)
    distance_cost = endpoint_distance
    total_cost = (
        distance_cost
        + obstacle_risk
        + map_cost
        + uncertainty_cost
        + relocalization_cost
        - _PROGRESS_REWARD_WEIGHT * progress
    )
    components = {
        "distance_cost": distance_cost,
        "progress_m": progress,
        "obstacle_risk": obstacle_risk,
        "map_cost": map_cost,
        "uncertainty_cost": uncertainty_cost,
        "relocalization_cost": relocalization_cost,
    }
    return _ScoredCandidate(
        action_id=action_id,
        action=action,
        endpoint={"x": endpoint.x, "y": endpoint.y, "yaw_rad": endpoint.yaw_rad},
        total_cost=total_cost,
        components=components,
    )


def _simulate_endpoint(action: JSONDict, *, observation: JSONDict) -> _Pose2D:
    pose = _pose(observation["pose"])
    if action["type"] == "go2_safety_action":
        return pose
    params = action["parameters"]
    dx_m = _number(params.get("dx_m", 0.0), name="action.dx_m")
    dyaw_rad = _number(params.get("dyaw_rad", 0.0), name="action.dyaw_rad")
    heading = pose.yaw_rad + dyaw_rad / 2.0
    return _Pose2D(
        x=pose.x + dx_m * math.cos(heading),
        y=pose.y + dx_m * math.sin(heading),
        yaw_rad=pose.yaw_rad + dyaw_rad,
    )


def _obstacle_risk(start: _Pose2D, end: _Pose2D, map_payload: JSONDict) -> float:
    safety_margin = _number(map_payload.get("safety_margin_m", 0.25), name="safety_margin_m")
    risk = 0.0
    for obstacle in map_payload.get("obstacles", []):
        center = (
            _number(obstacle["x"], name="obstacle.x"),
            _number(obstacle["y"], name="obstacle.y"),
        )
        clearance = _segment_distance((start.x, start.y), (end.x, end.y), center)
        required = _number(obstacle["radius_m"], name="obstacle.radius_m") + safety_margin
        risk += max(0.0, required - clearance) * _OBSTACLE_CLEARANCE_PENALTY_SCALE
    return risk


def _zone_cost(endpoint: _Pose2D, zones: object) -> float:
    if not isinstance(zones, list):
        return 0.0
    total = 0.0
    for zone in zones:
        if not isinstance(zone, Mapping):
            continue
        distance = math.dist(
            (endpoint.x, endpoint.y),
            (_number(zone["x"], name="zone.x"), _number(zone["y"], name="zone.y")),
        )
        radius = _number(zone["radius_m"], name="zone.radius_m")
        if distance <= radius:
            total += _number(zone["cost"], name="zone.cost") * (1.0 - distance / radius)
    return total


def _relocalization_cost(action: JSONDict, observation: JSONDict) -> float:
    confidence = _number(
        observation.get("localization_confidence", 1.0),
        name="localization_confidence",
    )
    if confidence >= 0.5:
        return 0.0
    if action["type"] == "go2_safety_action":
        return _SAFETY_ACTION_RELOCALIZATION_COST
    speed = _number(action["parameters"].get("speed_mps", 0.0), name="action.speed_mps")
    return (0.5 - confidence) * (_UNCERTAIN_MOTION_BASE_COST + speed)


def _segment_distance(
    start: tuple[float, float],
    end: tuple[float, float],
    point: tuple[float, float],
) -> float:
    sx, sy = start
    ex, ey = end
    px, py = point
    dx = ex - sx
    dy = ey - sy
    if dx == 0.0 and dy == 0.0:
        return math.dist(start, point)
    t = ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.dist((sx + t * dx, sy + t * dy), point)


def _pose(payload: JSONDict) -> _Pose2D:
    return _Pose2D(
        x=_number(payload["x"], name="pose.x"),
        y=_number(payload["y"], name="pose.y"),
        yaw_rad=_number(payload["yaw_rad"], name="pose.yaw_rad"),
    )


def _number(value: object, *, name: str) -> float:
    return require_finite_number(value, name=name)


def _candidate_by_id(candidates: Sequence[JSONDict], action_id: str) -> JSONDict | None:
    return next(
        (candidate for candidate in candidates if candidate["action_id"] == action_id),
        None,
    )


def _scored_candidate_payload(candidate: _ScoredCandidate) -> JSONDict:
    return {
        "action_id": candidate.action_id,
        "action": candidate.action,
        "endpoint": candidate.endpoint,
        "total_cost": candidate.total_cost,
        "components": candidate.components,
    }


__all__ = [
    "DEFAULT_FIXTURE_PATH",
    "Go2ReplayArenaResult",
    "Go2ReplayScoreProvider",
    "load_go2_replay_fixture",
    "render_go2_replay_report",
    "run_dimos_go2_replay_arena",
    "run_dimos_go2_replay_arena_workflow",
]
