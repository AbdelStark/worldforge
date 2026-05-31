"""Deterministic generation and transfer evaluation suites."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from worldforge.evaluation.metrics import blob_score as _blob_score
from worldforge.evaluation.metrics import content_type_score as _content_type_score
from worldforge.evaluation.metrics import duration_score as _duration_score
from worldforge.evaluation.metrics import fps_score as _fps_score
from worldforge.evaluation.metrics import is_image_conditioned as _is_image_conditioned
from worldforge.evaluation.metrics import is_transfer_clip as _is_transfer_clip
from worldforge.evaluation.metrics import prompt_score as _prompt_score
from worldforge.evaluation.metrics import reference_count as _reference_count
from worldforge.evaluation.metrics import resolution_score as _resolution_score
from worldforge.evaluation.results import EvaluationResult, EvaluationScenario
from worldforge.evaluation.suite_base import EvaluationSuite
from worldforge.evaluation.suite_fixtures import SAMPLE_IMAGE_DATA_URI, sample_transfer_clip
from worldforge.models import GenerationOptions, average

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge


class GenerationEvaluationSuite(EvaluationSuite):
    """Built-in suite for text and image-conditioned video generation checks."""

    def __init__(self) -> None:
        super().__init__(
            "Generation Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "text-conditioned-video",
                    "Generates a prompt-only clip and scores basic output integrity.",
                    required_capabilities=("generate",),
                ),
                EvaluationScenario(
                    "image-conditioned-video",
                    (
                        "Generates a prompt plus image-conditioned clip and scores "
                        "conditioning metadata."
                    ),
                    required_capabilities=("generate",),
                ),
            ],
            suite_id="generation",
        )

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_text_conditioned_video(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        expected_duration = 1.0
        expected_resolution = (640, 360)
        prompt = "orbiting cube over a reflective floor"
        clip = forge.generate(
            prompt,
            provider,
            duration_seconds=expected_duration,
            options=GenerationOptions(ratio="640:360", fps=8.0),
        )
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=expected_duration,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and _duration_score(
                actual_seconds=clip.duration_seconds,
                expected_seconds=expected_duration,
            )
            >= 0.75
            and _resolution_score(clip, expected=expected_resolution) >= 0.75
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
            },
        )

    def _evaluate_image_conditioned_video(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        expected_duration = 1.0
        expected_resolution = (640, 360)
        prompt = "orbiting cube over a reflective floor"
        clip = forge.generate(
            prompt,
            provider,
            duration_seconds=expected_duration,
            options=GenerationOptions(
                image=SAMPLE_IMAGE_DATA_URI,
                ratio="640:360",
                fps=8.0,
            ),
        )
        image_conditioned = _is_image_conditioned(clip)
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=expected_duration,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
                1.0 if image_conditioned else 0.0,
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and image_conditioned
            and _duration_score(
                actual_seconds=clip.duration_seconds,
                expected_seconds=expected_duration,
            )
            >= 0.75
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
                "image_conditioned": image_conditioned,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "text-conditioned-video": _evaluate_text_conditioned_video,
        "image-conditioned-video": _evaluate_image_conditioned_video,
    }


class TransferEvaluationSuite(EvaluationSuite):
    """Built-in suite for prompt-guided and reference-guided transfer checks."""

    def __init__(self) -> None:
        super().__init__(
            "Transfer Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "prompt-guided-transfer",
                    (
                        "Transfers a seed clip to a new render while preserving "
                        "basic media constraints."
                    ),
                    required_capabilities=("transfer",),
                ),
                EvaluationScenario(
                    "reference-guided-transfer",
                    "Transfers a seed clip with reference guidance metadata.",
                    required_capabilities=("transfer",),
                ),
            ],
            suite_id="transfer",
        )

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_prompt_guided_transfer(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        input_clip = sample_transfer_clip()
        expected_resolution = (320, 180)
        expected_fps = 12.0
        prompt = "re-render the clip with sharper cinematic contrast"
        clip = forge.transfer(
            input_clip,
            provider,
            width=expected_resolution[0],
            height=expected_resolution[1],
            fps=expected_fps,
            prompt=prompt,
        )
        transfer_mode = _is_transfer_clip(clip)
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=input_clip.duration_seconds,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _fps_score(clip, expected_fps=expected_fps),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
                1.0 if transfer_mode else 0.0,
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and transfer_mode
            and _resolution_score(clip, expected=expected_resolution) == 1.0
            and _fps_score(clip, expected_fps=expected_fps) == 1.0
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
                "reference_count": _reference_count(clip),
            },
        )

    def _evaluate_reference_guided_transfer(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        input_clip = sample_transfer_clip()
        expected_resolution = (320, 180)
        expected_fps = 12.0
        prompt = "re-render the clip with sharper cinematic contrast"
        clip = forge.transfer(
            input_clip,
            provider,
            width=expected_resolution[0],
            height=expected_resolution[1],
            fps=expected_fps,
            prompt=prompt,
            options=GenerationOptions(reference_images=[SAMPLE_IMAGE_DATA_URI]),
        )
        reference_count = _reference_count(clip)
        transfer_mode = _is_transfer_clip(clip)
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=input_clip.duration_seconds,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _fps_score(clip, expected_fps=expected_fps),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
                1.0 if transfer_mode else 0.0,
                1.0 if reference_count >= 1 else 0.0,
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and transfer_mode
            and reference_count >= 1
            and _resolution_score(clip, expected=expected_resolution) == 1.0
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
                "reference_count": reference_count,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "prompt-guided-transfer": _evaluate_prompt_guided_transfer,
        "reference-guided-transfer": _evaluate_reference_guided_transfer,
    }


__all__ = ["GenerationEvaluationSuite", "TransferEvaluationSuite"]
