"""Validated evaluation scenario and result contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from worldforge.models import (
    JSONDict,
    WorldForgeError,
    require_bool,
    require_finite_number,
    require_json_dict,
    require_non_negative_int,
    require_probability,
)

if TYPE_CHECKING:
    from worldforge.framework import WorldForge

EvaluationScenarioEvaluator = Callable[
    ["EvaluationContext"],
    "EvaluationScenarioOutcome | EvaluationResult | JSONDict",
]

EVALUATION_CLAIM_BOUNDARY = (
    "Built-in evaluation suites are deterministic adapter contract checks. Scores are synthetic "
    "workflow signals, not claims of physical fidelity, media quality, safety, or real robot "
    "performance."
)
EVALUATION_METRIC_SEMANTICS = (
    "Scenario scores and pass rates measure whether a provider satisfied the suite's typed "
    "contract under preserved inputs."
)


def required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, require_finite_number(value, name="evaluation score")))


@dataclass(frozen=True, slots=True)
class EvaluationScenarioOutcome:
    """Validated score, pass flag, and metrics returned by a custom scenario."""

    score: float
    passed: bool
    metrics: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", require_probability(self.score, name="outcome score"))
        object.__setattr__(self, "passed", require_bool(self.passed, name="outcome passed"))
        object.__setattr__(
            self,
            "metrics",
            require_json_dict(self.metrics, name="EvaluationScenarioOutcome metrics"),
        )


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Runtime context passed to custom evaluation scenario callables."""

    suite_id: str
    suite: str
    scenario: EvaluationScenario
    provider: str
    forge: WorldForge
    index: int

    def outcome(
        self,
        *,
        score: float,
        passed: bool,
        metrics: JSONDict | None = None,
    ) -> EvaluationScenarioOutcome:
        return EvaluationScenarioOutcome(
            score=score,
            passed=passed,
            metrics=metrics or {},
        )


@dataclass(slots=True)
class EvaluationScenario:
    """A single scenario inside an evaluation suite."""

    name: str
    description: str
    required_capabilities: tuple[str, ...] = ()
    evaluator: EvaluationScenarioEvaluator | None = None

    def __post_init__(self) -> None:
        self.name = required_text(self.name, name="EvaluationScenario name")
        self.description = required_text(
            self.description,
            name="EvaluationScenario description",
        )
        if not isinstance(self.required_capabilities, tuple):
            self.required_capabilities = tuple(self.required_capabilities)
        for capability in self.required_capabilities:
            required_text(capability, name="EvaluationScenario required capability")
        if self.evaluator is not None and not callable(self.evaluator):
            raise WorldForgeError("EvaluationScenario evaluator must be callable when provided.")

    @classmethod
    def from_callable(
        cls,
        *,
        name: str,
        description: str,
        evaluator: EvaluationScenarioEvaluator,
        required_capabilities: Sequence[str] = (),
    ) -> EvaluationScenario:
        """Create a custom scenario from a deterministic evaluator callable."""

        return cls(
            name=name,
            description=description,
            required_capabilities=tuple(required_capabilities),
            evaluator=evaluator,
        )


@dataclass(slots=True)
class EvaluationResult:
    """The result for one scenario/provider pair."""

    suite_id: str
    suite: str
    scenario: str
    provider: str
    score: float
    passed: bool
    metrics: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.suite_id = required_text(self.suite_id, name="EvaluationResult suite_id")
        self.suite = required_text(self.suite, name="EvaluationResult suite")
        self.scenario = required_text(self.scenario, name="EvaluationResult scenario")
        self.provider = required_text(self.provider, name="EvaluationResult provider")
        self.score = require_probability(self.score, name="EvaluationResult score")
        self.passed = require_bool(self.passed, name="EvaluationResult passed")
        self.metrics = require_json_dict(self.metrics, name="EvaluationResult metrics")

    def to_dict(self) -> JSONDict:
        return {
            "suite_id": self.suite_id,
            "suite": self.suite,
            "scenario": self.scenario,
            "provider": self.provider,
            "score": self.score,
            "passed": self.passed,
            "metrics": self.metrics,
        }


@dataclass(slots=True)
class ProviderSummary:
    """Aggregate summary for a provider across a suite run."""

    provider: str
    average_score: float
    scenario_count: int
    passed_scenario_count: int
    failed_scenario_count: int

    def __post_init__(self) -> None:
        self.provider = required_text(self.provider, name="ProviderSummary provider")
        self.average_score = require_probability(
            self.average_score,
            name="ProviderSummary average_score",
        )
        self.scenario_count = require_non_negative_int(
            self.scenario_count,
            name="ProviderSummary scenario_count",
        )
        self.passed_scenario_count = require_non_negative_int(
            self.passed_scenario_count,
            name="ProviderSummary passed_scenario_count",
        )
        self.failed_scenario_count = require_non_negative_int(
            self.failed_scenario_count,
            name="ProviderSummary failed_scenario_count",
        )
        if self.passed_scenario_count + self.failed_scenario_count != self.scenario_count:
            raise WorldForgeError(
                "ProviderSummary passed and failed scenario counts must sum to scenario_count."
            )

    @property
    def pass_rate(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return self.passed_scenario_count / self.scenario_count

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "average_score": self.average_score,
            "scenario_count": self.scenario_count,
            "passed_scenario_count": self.passed_scenario_count,
            "failed_scenario_count": self.failed_scenario_count,
            "pass_rate": self.pass_rate,
        }
