"""Generic evaluation suite runner and registry contract."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, ClassVar

from worldforge.dataset_manifests import dataset_manifest_references
from worldforge.evaluation.report import EvaluationReport
from worldforge.evaluation.results import (
    EVALUATION_CLAIM_BOUNDARY,
    EVALUATION_METRIC_SEMANTICS,
    EvaluationContext,
    EvaluationResult,
    EvaluationScenario,
    EvaluationScenarioOutcome,
)
from worldforge.evaluation.results import (
    clamp_score as _clamp_score,
)
from worldforge.evaluation.results import (
    required_text as _required_text,
)
from worldforge.models import Action, JSONDict, WorldForgeError
from worldforge.provenance import (
    EVALUATION_SUITE_CONTRACT_VERSION,
    ProvenanceEnvelope,
    collect_runtime_manifests,
    digest_payload,
)
from worldforge.workflow_trace import WorkflowArtifactRef, WorkflowTrace, WorkflowTraceStep

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge


class EvaluationSuite:
    """Group of :class:`EvaluationScenario` instances run against a single provider.

    Use :meth:`from_builtin` to construct one of the bundled suites (``physics``,
    ``planning``); construct directly to assemble
    custom scenario sequences. Suites are deterministic adapter-contract checks: a passing
    score asserts the provider returns well-formed payloads, not that it has physical or
    media fidelity.
    """

    def __init__(
        self,
        name: str,
        scenarios: Sequence[EvaluationScenario],
        *,
        suite_id: str | None = None,
        suite_version: str | None = None,
        claim_boundary: str = EVALUATION_CLAIM_BOUNDARY,
        metric_semantics: str = EVALUATION_METRIC_SEMANTICS,
    ) -> None:
        self.name = _required_text(name, name="EvaluationSuite name")
        self.scenarios = list(scenarios)
        if not self.scenarios:
            raise WorldForgeError("EvaluationSuite scenarios must contain at least one scenario.")
        if not all(isinstance(scenario, EvaluationScenario) for scenario in self.scenarios):
            raise WorldForgeError("EvaluationSuite scenarios must contain only EvaluationScenario.")
        self.suite_id = _required_text(
            suite_id or name.lower().replace(" ", "-"),
            name="EvaluationSuite suite_id",
        )
        self.suite_version = _required_text(
            suite_version or f"evaluation:{EVALUATION_SUITE_CONTRACT_VERSION}",
            name="EvaluationSuite suite_version",
        )
        self.claim_boundary = _required_text(
            claim_boundary,
            name="EvaluationSuite claim_boundary",
        )
        self.metric_semantics = _required_text(
            metric_semantics,
            name="EvaluationSuite metric_semantics",
        )

    _CUSTOM_REGISTRY: ClassVar[dict[str, Callable[[], EvaluationSuite]]] = {}

    @classmethod
    def custom(
        cls,
        *,
        suite_id: str,
        name: str,
        scenarios: Sequence[EvaluationScenario],
        suite_version: str,
        claim_boundary: str,
        metric_semantics: str = EVALUATION_METRIC_SEMANTICS,
    ) -> EvaluationSuite:
        """Build a deterministic custom evaluation suite from public scenario objects."""

        return cls(
            name,
            scenarios,
            suite_id=suite_id,
            suite_version=suite_version,
            claim_boundary=claim_boundary,
            metric_semantics=metric_semantics,
        )

    @classmethod
    def register(
        cls,
        name: str,
        factory: Callable[[], EvaluationSuite],
        *,
        replace: bool = False,
    ) -> None:
        """Register a process-local custom suite factory."""

        suite_name = _required_text(name, name="EvaluationSuite registry name")
        if not callable(factory):
            raise WorldForgeError("EvaluationSuite.register() factory must be callable.")
        if suite_name in cls._builtin_registry():
            raise WorldForgeError(
                f"Evaluation suite '{suite_name}' is built in and cannot be replaced."
            )
        if suite_name in cls._CUSTOM_REGISTRY and not replace:
            raise WorldForgeError(
                f"Evaluation suite '{suite_name}' is already registered; pass replace=True "
                "to overwrite it."
            )
        cls._CUSTOM_REGISTRY[suite_name] = factory

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a process-local custom suite registration if present."""

        cls._CUSTOM_REGISTRY.pop(_required_text(name, name="EvaluationSuite registry name"), None)

    @classmethod
    def registered_names(cls) -> list[str]:
        """Return built-in and process-local custom suite names."""

        return sorted((*cls._builtin_registry(), *cls._CUSTOM_REGISTRY))

    @classmethod
    def from_registered(cls, name: str) -> EvaluationSuite:
        """Construct a built-in or process-local registered suite by name."""

        suite_name = _required_text(name, name="EvaluationSuite registry name")
        if suite_name in cls._builtin_registry():
            return cls.from_builtin(suite_name)
        try:
            factory = cls._CUSTOM_REGISTRY[suite_name]
        except KeyError as exc:
            known = ", ".join(cls.registered_names())
            raise WorldForgeError(
                f"Unknown registered evaluation suite '{suite_name}'. Known suites: {known}."
            ) from exc
        suite = factory()
        if not isinstance(suite, EvaluationSuite):
            raise WorldForgeError(
                f"Registered evaluation suite '{suite_name}' factory must return EvaluationSuite."
            )
        return suite

    @classmethod
    def _builtin_registry(cls) -> dict[str, Callable[[], EvaluationSuite]]:
        from worldforge.evaluation.builtin_suites import (
            PhysicsEvaluationSuite,
            PlanningEvaluationSuite,
        )

        return {
            "physics": PhysicsEvaluationSuite,
            "planning": PlanningEvaluationSuite,
        }

    @classmethod
    def builtin_names(cls) -> list[str]:
        """Return the sorted names of every suite that :meth:`from_builtin` accepts."""

        return sorted(cls._builtin_registry())

    @classmethod
    def from_builtin(cls, name: str) -> EvaluationSuite:
        """Construct a built-in suite by name.

        Accepted names are listed by :meth:`builtin_names`. Raises :class:`WorldForgeError`
        for unknown names with a hint listing the valid set.
        """

        registry = cls._builtin_registry()
        try:
            factory = registry[name]
        except KeyError as exc:
            known = ", ".join(sorted(registry))
            raise WorldForgeError(
                f"Unknown evaluation suite '{name}'. Known suites: {known}."
            ) from exc
        return factory()

    def _required_capabilities(self) -> tuple[str, ...]:
        names = {
            capability
            for scenario in self.scenarios
            for capability in scenario.required_capabilities
        }
        return tuple(sorted(names))

    def _require_provider_capabilities(self, provider: str, *, forge: WorldForge) -> None:
        profile = forge.provider_profile(provider)
        missing = [
            capability
            for capability in self._required_capabilities()
            if not profile.capabilities.supports(capability)
        ]
        if missing:
            joined = ", ".join(missing)
            raise WorldForgeError(
                f"Provider '{provider}' cannot run evaluation suite '{self.suite_id}': "
                f"missing required capabilities: {joined}."
            )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        return forge.create_world(f"{self.suite_id}-evaluation-world", provider)

    def _ensure_world(
        self,
        provider: str,
        *,
        forge: WorldForge,
        world: World | None = None,
    ) -> World:
        from worldforge.framework import World

        if world is not None:
            return World.from_state(forge, world.to_dict())
        return self._build_world(provider, forge=forge)

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        if scenario.evaluator is not None:
            return self._evaluate_custom_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        prediction = world.predict(
            Action.move_to(0.1 * (index + 1), 0.5, 0.0),
            steps=1,
            provider=provider,
        )
        score = _clamp_score((prediction.physics_score + prediction.confidence) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=score >= 0.7,
            metrics={
                "physics_score": prediction.physics_score,
                "confidence": prediction.confidence,
            },
        )

    def _evaluate_custom_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        if scenario.evaluator is None:  # pragma: no cover - call-site guard
            raise WorldForgeError("Custom evaluation scenario is missing an evaluator.")
        context = EvaluationContext(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario,
            provider=provider,
            world=world,
            forge=forge,
            index=index,
        )
        return self._coerce_custom_result(
            scenario.evaluator(context),
            scenario=scenario,
            provider=provider,
        )

    def _coerce_custom_result(
        self,
        value: EvaluationScenarioOutcome | EvaluationResult | JSONDict,
        *,
        scenario: EvaluationScenario,
        provider: str,
    ) -> EvaluationResult:
        if isinstance(value, EvaluationResult):
            if value.suite_id != self.suite_id:
                raise WorldForgeError("Custom EvaluationResult suite_id must match its suite.")
            if value.suite != self.name:
                raise WorldForgeError("Custom EvaluationResult suite name must match its suite.")
            if value.scenario != scenario.name:
                raise WorldForgeError(
                    "Custom EvaluationResult scenario must match the evaluated scenario."
                )
            if value.provider != provider:
                raise WorldForgeError("Custom EvaluationResult provider must match the provider.")
            return value
        if isinstance(value, dict):
            outcome = EvaluationScenarioOutcome(
                score=value.get("score"),
                passed=value.get("passed"),
                metrics=value.get("metrics", {}),
            )
        elif isinstance(value, EvaluationScenarioOutcome):
            outcome = value
        else:
            raise WorldForgeError(
                "Custom evaluation scenarios must return EvaluationScenarioOutcome, "
                "EvaluationResult, or a JSON object with score, passed, and metrics."
            )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=outcome.score,
            passed=outcome.passed,
            metrics=outcome.metrics,
        )

    def run_with_world(
        self,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
    ) -> list[EvaluationResult]:
        self._require_provider_capabilities(provider, forge=forge)
        base_world = self._ensure_world(provider, forge=forge, world=world)
        results: list[EvaluationResult] = []
        for index, scenario in enumerate(self.scenarios):
            sandbox = self._ensure_world(provider, forge=forge, world=base_world)
            results.append(
                self.evaluate_scenario(
                    scenario,
                    provider,
                    world=sandbox,
                    forge=forge,
                    index=index,
                )
            )
        return results

    def run(self, provider: str, *, forge: WorldForge | None = None) -> list[EvaluationResult]:
        from worldforge.framework import WorldForge

        active_forge = forge or WorldForge()
        self._require_provider_capabilities(provider, forge=active_forge)
        world = self._ensure_world(provider, forge=active_forge)
        return self.run_with_world(provider, world=world, forge=active_forge)

    def run_report(
        self,
        providers: str | Sequence[str],
        *,
        world: World | None = None,
        forge: WorldForge | None = None,
        dataset_manifests: Sequence[object] | None = None,
    ) -> EvaluationReport:
        from worldforge.framework import WorldForge

        active_forge = forge or WorldForge()
        provider_names = [providers] if isinstance(providers, str) else list(providers)
        if not provider_names:
            raise WorldForgeError("run_report() requires at least one provider.")

        for provider in provider_names:
            # Fail fast on capability mismatch before spinning up threads.
            self._require_provider_capabilities(provider, forge=active_forge)

        def _run_one(provider: str) -> list[EvaluationResult]:
            return self.run_with_world(
                provider,
                world=self._ensure_world(provider, forge=active_forge, world=world),
                forge=active_forge,
            )

        results: list[EvaluationResult] = []
        if len(provider_names) == 1:
            results.extend(_run_one(provider_names[0]))
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(provider_names))) as pool:
                for provider_results in pool.map(_run_one, provider_names):
                    results.extend(provider_results)
        dataset_refs = dataset_manifest_references(dataset_manifests)
        provenance = self._build_provenance(provider_names, results, dataset_manifests=dataset_refs)
        return EvaluationReport(
            self.suite_id,
            self.name,
            results,
            provenance=provenance,
            workflow_trace=self._build_workflow_trace(provider_names, results),
            claim_boundary=self.claim_boundary,
            metric_semantics=self.metric_semantics,
        )

    def _build_workflow_trace(
        self,
        provider_names: Sequence[str],
        results: Sequence[EvaluationResult],
    ) -> WorkflowTrace:
        steps: list[WorkflowTraceStep] = [
            WorkflowTraceStep(
                step_id="evaluation",
                operation="run evaluation suite",
                status="success" if all(result.passed for result in results) else "failed",
                output_artifacts=(WorkflowArtifactRef(label="evaluation-report"),),
            )
        ]
        for provider_index, provider in enumerate(provider_names, start=1):
            provider_results = [result for result in results if result.provider == provider]
            provider_step_id = f"provider-{provider_index}"
            steps.append(
                WorkflowTraceStep(
                    step_id=provider_step_id,
                    parent_id="evaluation",
                    operation="evaluate provider",
                    status=(
                        "success"
                        if provider_results and all(result.passed for result in provider_results)
                        else "failed"
                    ),
                    provider=provider,
                    output_artifacts=(WorkflowArtifactRef(label=f"{provider}-results"),),
                )
            )
            for scenario_index, result in enumerate(provider_results, start=1):
                steps.append(
                    WorkflowTraceStep(
                        step_id=f"{provider_step_id}-scenario-{scenario_index}",
                        parent_id=provider_step_id,
                        operation=result.scenario,
                        status="success" if result.passed else "failed",
                        provider=provider,
                        output_artifacts=(WorkflowArtifactRef(label="scenario-result"),),
                    )
                )
        return WorkflowTrace(
            workflow_id=f"evaluation:{self.suite_id}",
            name=f"Evaluation suite ({self.suite_id})",
            steps=steps,
            metadata={
                "suite_id": self.suite_id,
                "suite_version": self.suite_version,
                "provider_count": len(provider_names),
                "scenario_count": len(self.scenarios),
            },
        )

    def _build_provenance(
        self,
        provider_names: Sequence[str],
        results: Sequence[EvaluationResult],
        *,
        dataset_manifests: Sequence[JSONDict] = (),
    ) -> ProvenanceEnvelope:
        result_payload = [result.to_dict() for result in results]
        return ProvenanceEnvelope(
            kind="evaluation",
            suite_id=self.suite_id,
            suite_version=self.suite_version,
            providers=tuple(provider_names),
            capabilities=self._required_capabilities(),
            runtime_manifests=collect_runtime_manifests(provider_names),
            input_digest=digest_payload(
                {
                    "suite_id": self.suite_id,
                    "suite": self.name,
                    "scenarios": [
                        {
                            "name": scenario.name,
                            "description": scenario.description,
                            "required_capabilities": list(scenario.required_capabilities),
                        }
                        for scenario in self.scenarios
                    ],
                    "providers": list(provider_names),
                    "dataset_manifests": list(dataset_manifests),
                }
            ),
            result_digest=digest_payload(result_payload),
            dataset_manifests=tuple(dataset_manifests),
            event_count=0,
            claim_boundary=self.claim_boundary,
            metric_semantics=self.metric_semantics,
        )

    def run_report_artifacts(
        self,
        *,
        providers: str | Sequence[str],
        world: World | None = None,
        forge: WorldForge | None = None,
    ) -> dict[str, str]:
        report = self.run_report(providers=providers, world=world, forge=forge)
        return report.artifacts()
