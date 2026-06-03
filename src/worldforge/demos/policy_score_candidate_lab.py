"""Checkout-safe policy+score candidate planning demo.

The lab drives the WorldForge capability surface directly: a deterministic policy
provider proposes candidate action chunks via ``forge.select_actions``, a
deterministic score provider ranks them via ``forge.score_actions``, the lowest-cost
chunk is selected by ``best_index``, and that chunk is rolled forward with
``forge.predict``. There is no symbolic ``World`` runtime.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from worldforge import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    BBox,
    Position,
    ProviderCapabilities,
    SceneObject,
    WorldForge,
    action_candidates_to_score_payload,
    bounded_move_grid_candidates,
)
from worldforge.artifact_io import write_json_artifact as _write_json
from worldforge.demos import execute_plan_over_state, seed_world_state
from worldforge.models import JSONDict
from worldforge.providers import BaseProvider, ProviderProfileSpec
from worldforge.providers.base import ProviderError

CANDIDATE_LAB_CLAIM_BOUNDARY = (
    "Checkout-safe deterministic candidate lab only; no robot controller, simulator, "
    "checkpoint download, or physical-performance claim."
)

CANDIDATE_LAB_SUMMARY = (
    "Generated deterministic action candidates, preserved raw policy actions, ranked "
    "them with a score provider, selected the lowest-cost action, and captured invalid "
    "bounds plus missing-translator failures."
)

CANDIDATE_LAB_FIRST_TRIAGE_STEP = (
    "Open `policy-score-candidate-lab.md` and verify the selected row matches "
    "`score_result.best_index`."
)


@dataclass(frozen=True, slots=True)
class CandidateLabConfig:
    world_id: str = "candidate-lab-world"
    object_id: str = "cube-1"
    object_name: str = "cube"
    object_position: tuple[float, float, float] = (0.0, 0.5, 0.0)
    object_bbox_min: tuple[float, float, float] = (-0.05, 0.45, -0.05)
    object_bbox_max: tuple[float, float, float] = (0.05, 0.55, 0.05)
    x_bounds: tuple[float, float] = (0.1, 0.7)
    y_bounds: tuple[float, float] = (0.5, 0.5)
    z_bounds: tuple[float, float] = (0.0, 0.0)
    x_steps: int = 3
    y_steps: int = 1
    z_steps: int = 1
    scores: tuple[float, ...] = (0.72, 0.18, 0.44)
    policy_logits: tuple[float, ...] = (0.2, 0.6, 0.2)
    planning_goal: str = "choose the lowest-cost candidate"
    policy_observation: str = "checkout-safe grid"
    score_goal: str = "move cube near center"
    policy_provider: str = "candidate-lab-policy"
    score_provider: str = "candidate-lab-score"
    execution_provider: str = "mock"


@dataclass(frozen=True, slots=True)
class CandidateLabRun:
    candidate_plans: list[list[Action]]
    score_payload: list[list[JSONDict]]
    scores: list[float]
    policy_result: ActionPolicyResult
    score_result: ActionScoreResult
    selected_actions: list[Action]
    final_step: int
    selected_index: int


DEFAULT_CANDIDATE_LAB_CONFIG = CandidateLabConfig()


class CandidateLabPolicy(BaseProvider):
    def __init__(
        self,
        candidate_plans: list[list[Action]],
        *,
        provider_name: str,
        policy_logits: Sequence[float],
        translator_available: bool = True,
    ) -> None:
        super().__init__(
            provider_name,
            capabilities=ProviderCapabilities(policy=True),
            profile=ProviderProfileSpec(
                description="Deterministic checkout-safe policy candidate lab provider.",
                implementation_status="demo",
                is_local=True,
                deterministic=True,
            ),
        )
        self._candidate_plans = candidate_plans
        self._policy_logits = tuple(policy_logits)
        self._translator_available = translator_available

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        if not self._translator_available:
            raise ProviderError("candidate lab action_translator is required.")
        raw_actions = {
            "policy_logits": list(self._policy_logits),
            "raw_policy_action_preserved": True,
            "observation_keys": sorted(info),
        }
        return ActionPolicyResult(
            provider=self.name,
            actions=list(self._candidate_plans[0]),
            raw_actions=raw_actions,
            action_horizon=len(self._candidate_plans[0]),
            embodiment_tag="candidate-lab",
            metadata={
                "candidate_count": len(self._candidate_plans),
                "translator": "checkout-safe deterministic mapper",
            },
            action_candidates=[list(plan) for plan in self._candidate_plans],
        )


class CandidateLabScore(BaseProvider):
    def __init__(self, *, provider_name: str, scores: Sequence[float]) -> None:
        super().__init__(
            provider_name,
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(
                description="Deterministic checkout-safe candidate scorer.",
                implementation_status="demo",
                is_local=True,
                deterministic=True,
            ),
        )
        self._scores = tuple(scores)

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        if not isinstance(action_candidates, list) or len(action_candidates) != len(self._scores):
            raise ProviderError("candidate lab scorer received mismatched action candidates.")
        return ActionScoreResult(
            provider=self.name,
            scores=list(self._scores),
            best_index=min(range(len(self._scores)), key=self._scores.__getitem__),
            metadata={
                "candidate_count": len(self._scores),
                "score_source": "deterministic checkout lab",
                "goal": str(info.get("goal", "")),
            },
        )


def run_policy_score_candidate_lab_workflow(
    workflow_dir: Path,
    *,
    config: CandidateLabConfig = DEFAULT_CANDIDATE_LAB_CONFIG,
) -> JSONDict:
    run = run_policy_score_candidate_lab(workflow_dir, config=config)
    report = candidate_lab_report(run, candidate_lab_expected_failures(config))
    artifact_paths = write_candidate_lab_artifacts(workflow_dir, report)
    return candidate_lab_summary(report, artifact_paths)


def candidate_lab_candidates(
    config: CandidateLabConfig = DEFAULT_CANDIDATE_LAB_CONFIG,
) -> list[list[Action]]:
    return bounded_move_grid_candidates(
        x_bounds=config.x_bounds,
        y_bounds=config.y_bounds,
        z_bounds=config.z_bounds,
        x_steps=config.x_steps,
        y_steps=config.y_steps,
        z_steps=config.z_steps,
        object_id=config.object_id,
    )


def run_policy_score_candidate_lab(
    workflow_dir: Path,
    *,
    config: CandidateLabConfig = DEFAULT_CANDIDATE_LAB_CONFIG,
) -> CandidateLabRun:
    candidate_plans = candidate_lab_candidates(config)
    score_payload = action_candidates_to_score_payload(candidate_plans)
    scores = list(config.scores)
    forge = WorldForge(auto_register_remote=False)
    forge.register_provider(
        CandidateLabPolicy(
            candidate_plans,
            provider_name=config.policy_provider,
            policy_logits=config.policy_logits,
        )
    )
    forge.register_provider(CandidateLabScore(provider_name=config.score_provider, scores=scores))

    # Policy proposes the candidate chunks; the score provider ranks them; pick best_index.
    policy_result = forge.select_actions(
        config.policy_provider,
        info={"observation": config.policy_observation},
    )
    score_result = forge.score_actions(
        config.score_provider,
        info={"goal": config.score_goal},
        action_candidates=action_candidates_to_score_payload(policy_result.action_candidates),
    )
    selected_index = score_result.best_index
    selected_actions = list(policy_result.action_candidates[selected_index])

    cube = SceneObject(
        config.object_name,
        _position(config.object_position),
        BBox(_position(config.object_bbox_min), _position(config.object_bbox_max)),
        id=config.object_id,
    )
    final_state = execute_plan_over_state(
        forge,
        seed_world_state([cube]),
        selected_actions,
        provider=config.execution_provider,
    )
    return CandidateLabRun(
        candidate_plans=candidate_plans,
        score_payload=score_payload,
        scores=scores,
        policy_result=policy_result,
        score_result=score_result,
        selected_actions=selected_actions,
        final_step=int(final_state.get("step", 0)),
        selected_index=selected_index,
    )


def candidate_lab_expected_failures(
    config: CandidateLabConfig = DEFAULT_CANDIDATE_LAB_CONFIG,
) -> JSONDict:
    return {
        "invalid_candidate_bounds": candidate_lab_invalid_bounds_error(config),
        "missing_translator": candidate_lab_missing_translator_error(config),
    }


def candidate_lab_invalid_bounds_error(
    config: CandidateLabConfig = DEFAULT_CANDIDATE_LAB_CONFIG,
) -> str:
    try:
        bounded_move_grid_candidates(
            x_bounds=(1.0, 0.0),
            y_bounds=config.y_bounds,
            z_bounds=config.z_bounds,
            x_steps=config.x_steps,
            y_steps=config.y_steps,
            z_steps=config.z_steps,
        )
    except Exception as exc:
        return str(exc)
    return ""


def candidate_lab_missing_translator_error(
    config: CandidateLabConfig = DEFAULT_CANDIDATE_LAB_CONFIG,
) -> str:
    try:
        CandidateLabPolicy(
            candidate_lab_candidates(config),
            provider_name=config.policy_provider,
            policy_logits=config.policy_logits,
            translator_available=False,
        ).select_actions(info={"observation": config.policy_observation})
    except ProviderError as exc:
        return str(exc)
    return ""


def candidate_lab_table(run: CandidateLabRun) -> list[JSONDict]:
    return [
        {
            "index": index,
            "score": score,
            "selected": index == run.selected_index,
            "actions": [action.to_dict() for action in candidate],
        }
        for index, (score, candidate) in enumerate(
            zip(run.scores, run.candidate_plans, strict=True)
        )
    ]


def candidate_lab_report(run: CandidateLabRun, expected_failures: JSONDict) -> JSONDict:
    return {
        "schema_version": 1,
        "safe_to_attach": True,
        "planning_mode": "policy+score",
        "policy_provider": run.policy_result.provider,
        "score_provider": run.score_result.provider,
        "candidate_count": len(run.candidate_plans),
        "score_payload": run.score_payload,
        "candidate_table": candidate_lab_table(run),
        "selected_candidate_index": run.selected_index,
        "selected_action": run.selected_actions[0].to_dict(),
        "raw_policy_actions": run.policy_result.raw_actions,
        "score_metadata": run.score_result.metadata,
        "execution_final_step": run.final_step,
        "expected_failures": expected_failures,
        "claim_boundary": CANDIDATE_LAB_CLAIM_BOUNDARY,
    }


def write_candidate_lab_artifacts(workflow_dir: Path, report: JSONDict) -> dict[str, str]:
    report_path = workflow_dir / "policy-score-candidate-lab.json"
    _write_json(report_path, report)
    markdown_path = workflow_dir / "policy-score-candidate-lab.md"
    markdown_path.write_text(render_candidate_lab_markdown(report), encoding="utf-8")
    return {"lab_report": str(report_path), "lab_markdown": str(markdown_path)}


def render_candidate_lab_markdown(report: JSONDict) -> str:
    markdown_lines = [
        "# Policy+Score Candidate Lab",
        "",
        f"- planning_mode: `{report['planning_mode']}`",
        f"- selected_candidate_index: `{report['selected_candidate_index']}`",
        f"- candidate_count: `{report['candidate_count']}`",
        "",
        "| index | score | selected | target_x |",
        "| ---: | ---: | --- | ---: |",
    ]
    markdown_lines.extend(
        "| {index} | {score:.2f} | {selected} | {target_x:.2f} |".format(
            index=row["index"],
            score=row["score"],
            selected="yes" if row["selected"] else "no",
            target_x=row["actions"][0]["parameters"]["target"]["x"],
        )
        for row in report["candidate_table"]
    )
    expected_failures = report["expected_failures"]
    markdown_lines.extend(
        [
            "",
            "## Expected Failures",
            "",
            f"- invalid_candidate_bounds: {expected_failures['invalid_candidate_bounds']}",
            f"- missing_translator: {expected_failures['missing_translator']}",
            "",
            report["claim_boundary"],
        ]
    )
    return "\n".join(markdown_lines) + "\n"


def candidate_lab_summary(report: JSONDict, artifact_paths: dict[str, str]) -> JSONDict:
    return {
        "status": "passed",
        "provider": "candidate-lab-policy+candidate-lab-score",
        "safe_to_attach": True,
        "summary": CANDIDATE_LAB_SUMMARY,
        "report": report,
        "artifact_paths": artifact_paths,
        "first_triage_step": CANDIDATE_LAB_FIRST_TRIAGE_STEP,
        "claim_boundary": report["claim_boundary"],
    }


def _position(values: tuple[float, float, float]) -> Position:
    return Position(*values)
