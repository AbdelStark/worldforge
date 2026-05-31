"""Framework runtime objects for WorldForge.

This module owns the in-process orchestration boundary: provider registration, local JSON
persistence, diagnostics, and provider-wide operations. The mutable ``World`` runtime lives in
``worldforge._world`` and is imported here for backward compatibility. The framework deliberately
does not own deployment, multi-writer storage, optional model runtimes, robot controllers, or
production telemetry export.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from worldforge._provider_merge import (
    merged_provider_health as _merged_provider_health,
)
from worldforge._provider_merge import (
    merged_provider_lifecycle_status as _merged_provider_lifecycle_status,
)
from worldforge._provider_merge import (
    merged_provider_profile as _merged_provider_profile,
)
from worldforge._provider_merge import (
    provider_health_components as _provider_health_components,
)
from worldforge._provider_merge import (
    provider_lifecycle_components as _provider_lifecycle_components,
)
from worldforge._state import SCHEMA_VERSION as _WORLD_STATE_SCHEMA_VERSION
from worldforge._world import World
from worldforge._world_prompt_seeders import _prompt_world_name, _seed_prompt_world
from worldforge.capabilities import (
    Cost,
    Embedder,
    Planner,
    Policy,
    Predictor,
)
from worldforge.framework_capabilities import (
    CapabilityRegistry,
)
from worldforge.framework_capabilities import (
    call_resolved_capability as _call_resolved_capability,
)
from worldforge.framework_capabilities import (
    provider_with_event_handler as _provider_with_event_handler,
)
from worldforge.framework_doctor import doctor_report as _doctor_report
from worldforge.framework_world_store import delete_world as _delete_world
from worldforge.framework_world_store import export_world as _export_world
from worldforge.framework_world_store import fork_world as _fork_world
from worldforge.framework_world_store import import_world as _import_world
from worldforge.framework_world_store import list_worlds as _list_worlds
from worldforge.framework_world_store import load_world as _load_world
from worldforge.framework_world_store import save_world as _save_world
from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    DoctorReport,
    EmbeddingResult,
    JSONDict,
    ProviderEvent,
    ProviderHealth,
    ProviderInfo,
    ProviderLifecycleStatus,
    ProviderProfile,
    WorldForgeError,
    ensure_directory,
    require_positive_int,
)
from worldforge.models import (
    require_non_empty_text as _require_non_empty_text,
)
from worldforge.providers import (
    BaseProvider,
    PredictionPayload,
    ProviderConfigSummary,
    ProviderError,
)
from worldforge.providers.catalog import (
    PROVIDER_CATALOG,
    ProviderCatalogEntry,
    create_known_providers,
)
from worldforge.providers.entry_points import (
    EntryPointDiscoveryReport,
    discover_entry_point_providers,
)
from worldforge.providers.observable import _ObservableCapability

if TYPE_CHECKING:
    from worldforge.evaluation import EvaluationResult

SCHEMA_VERSION = _WORLD_STATE_SCHEMA_VERSION


class WorldForge:
    """Top-level entry point for provider orchestration and local JSON persistence.

    ``WorldForge`` owns provider registration, diagnostics, world construction, and the local
    single-writer JSON store. Host applications remain responsible for credentials, optional model
    dependencies, durable storage, telemetry export, and deployment policy.
    """

    def __init__(
        self,
        *,
        state_dir: str | Path | None = None,
        auto_register_remote: bool = True,
        event_handler: Callable[[ProviderEvent], None] | None = None,
        discover_entry_points: bool | None = None,
    ) -> None:
        self.state_dir = Path(state_dir or ".worldforge/worlds").expanduser().resolve()
        ensure_directory(self.state_dir)
        self._providers: dict[str, BaseProvider] = {}
        self._event_handler = event_handler
        self._capability_registry = CapabilityRegistry(event_handler=self._event_handler)
        self._capability_registries = self._capability_registry.registries
        self._register_catalog_providers(auto_register_remote=auto_register_remote)
        self._entry_point_discovery = self._discover_entry_points(discover_entry_points)
        self._register_entry_point_providers(auto_register_remote=auto_register_remote)

    def _register_catalog_providers(self, *, auto_register_remote: bool) -> None:
        for entry in PROVIDER_CATALOG:
            provider = entry.create(event_handler=self._event_handler)
            if self._should_register_catalog_provider(
                entry,
                provider,
                auto_register_remote=auto_register_remote,
            ):
                self.register_provider(provider)

    @staticmethod
    def _should_register_catalog_provider(
        entry: ProviderCatalogEntry,
        provider: BaseProvider,
        *,
        auto_register_remote: bool,
    ) -> bool:
        return entry.always_register or (auto_register_remote and provider.configured())

    @staticmethod
    def _discover_entry_points(
        enabled: bool | None,
    ) -> EntryPointDiscoveryReport:
        return discover_entry_point_providers(enabled=enabled, catalog=PROVIDER_CATALOG)

    def _register_entry_point_providers(self, *, auto_register_remote: bool) -> None:
        for entry in self._entry_point_discovery.entries:
            self._register_entry_point_provider(
                entry,
                auto_register_remote=auto_register_remote,
            )

    def _register_entry_point_provider(
        self,
        entry: ProviderCatalogEntry,
        *,
        auto_register_remote: bool,
    ) -> None:
        provider = self._entry_point_provider(entry)
        if provider is None:
            return
        if self._should_register_entry_point_provider(
            provider,
            auto_register_remote=auto_register_remote,
        ):
            self.register_provider(provider)

    @staticmethod
    def _should_register_entry_point_provider(
        provider: BaseProvider,
        *,
        auto_register_remote: bool,
    ) -> bool:
        return auto_register_remote and provider.configured()

    def _entry_point_provider(self, entry: ProviderCatalogEntry) -> BaseProvider | None:
        try:
            return entry.create(event_handler=self._event_handler)
        except Exception as exc:
            self._entry_point_discovery = self._entry_point_discovery_with_skip(
                entry.name,
                str(entry.runtime_ownership),
                f"factory raised: {exc}",
            )
            return None

    def _entry_point_discovery_with_skip(
        self,
        name: str,
        value: str,
        reason: str,
    ) -> EntryPointDiscoveryReport:
        from worldforge.providers.entry_points import EntryPointSkip

        report = self._entry_point_discovery
        return EntryPointDiscoveryReport(
            enabled=report.enabled,
            entries=tuple(entry for entry in report.entries if entry.name != name),
            skipped=(*report.skipped, EntryPointSkip(name=name, value=value, reason=reason)),
            group=report.group,
        )

    def entry_point_discovery(self) -> EntryPointDiscoveryReport:
        """Return the entry-point discovery report captured at construction time.

        The report enumerates every external provider factory found through the
        ``worldforge.providers`` entry-point group, plus a typed skip reason for any factory
        that could not be loaded (missing dependency, duplicate name, non-callable, factory
        raised at instantiation, etc.). The report is provisional public API; downstream
        tools should treat ``EntryPointSkip.reason`` strings as human-readable.
        """

        return self._entry_point_discovery

    def _known_providers(self) -> tuple[BaseProvider, ...]:
        return create_known_providers(event_handler=self._event_handler)

    def _require_provider(self, name: str) -> BaseProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderError(f"Provider '{name}' is not registered.") from exc

    def register_provider(self, provider: BaseProvider) -> None:
        """Register a provider instance by name.

        If the forge has a global event handler and the provider does not, the provider inherits
        that handler so later provider calls emit through the same observability path.
        """

        self._providers[provider.name] = _provider_with_event_handler(provider, self._event_handler)

    # ------------------------------------------------------------------
    # New capability-protocol registration surface (M0).
    # ------------------------------------------------------------------

    def register(self, impl: object) -> None:
        """Register a capability impl or :class:`RunnableModel` bundle.

        Dispatches by structural protocol membership: an impl that satisfies several capability
        protocols is indexed into every matching registry. A :class:`RunnableModel` is unpacked and
        each non-``None`` capability slot is registered into the matching capability registry.
        Raises :class:`WorldForgeError` if ``impl`` does not satisfy any known capability protocol.
        """

        if isinstance(impl, BaseProvider):
            self.register_provider(impl)
            return
        self._capability_registry.register(impl)

    def register_policy(self, policy: Policy) -> None:
        """Register a :class:`~worldforge.capabilities.Policy` implementation."""

        self._register_typed("policy", policy, Policy)

    def register_cost(self, cost: Cost) -> None:
        """Register a :class:`~worldforge.capabilities.Cost` implementation."""

        self._register_typed("cost", cost, Cost)

    def register_predictor(self, predictor: Predictor) -> None:
        """Register a :class:`~worldforge.capabilities.Predictor` implementation."""

        self._register_typed("predictor", predictor, Predictor)

    def register_embedder(self, embedder: Embedder) -> None:
        """Register an :class:`~worldforge.capabilities.Embedder` implementation."""

        self._register_typed("embedder", embedder, Embedder)

    def register_planner(self, planner: Planner) -> None:
        """Register a :class:`~worldforge.capabilities.Planner` implementation."""

        self._register_typed("planner", planner, Planner)

    def _register_typed(self, field_name: str, impl: object, protocol: type) -> None:
        self._capability_registry.register_typed(field_name, impl, protocol)

    def _registered_capability_names(self) -> set[str]:
        return self._capability_registry.registered_names()

    def _capability_wrappers_for_name(self, name: str) -> tuple[_ObservableCapability, ...]:
        return self._capability_registry.wrappers_for_name(name)

    def _registered_provider_names(self) -> set[str]:
        return set(self._providers) | self._registered_capability_names()

    def _provider_view_names(self, *, include_known: bool) -> list[str]:
        names = set(self._registered_provider_names())
        if include_known:
            names.update(self._provider_catalog(include_known=True))
        return sorted(names)

    def _merged_profile(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderProfile:
        return _merged_provider_profile(
            name=name,
            legacy_provider=legacy_provider,
            wrappers=wrappers,
        )

    def _merged_health(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderHealth:
        return _merged_provider_health(
            name,
            _provider_health_components(
                legacy_provider=legacy_provider,
                wrappers=wrappers,
            ),
        )

    def _merged_lifecycle_status(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
        run_warmup: bool = False,
        run_teardown: bool = False,
    ) -> ProviderLifecycleStatus:
        return _merged_provider_lifecycle_status(
            name,
            _provider_lifecycle_components(
                legacy_provider=legacy_provider,
                wrappers=wrappers,
                run_warmup=run_warmup,
                run_teardown=run_teardown,
            ),
        )

    def _registered_or_known_provider(
        self,
        name: str,
        *,
        include_known: bool,
    ) -> BaseProvider | None:
        if name in self._providers:
            return self._providers[name]
        if include_known:
            return self._provider_catalog(include_known=True).get(name)
        return None

    def _resolve_capability_target(
        self,
        *,
        field_name: str,
        protocol: type,
        target: object | None,
        operation: str,
        target_label: str,
    ) -> object:
        if target is None:
            raise WorldForgeError(
                f"{operation}() requires a provider name or {target_label} target."
            )
        if isinstance(target, str):
            target_name = _require_non_empty_text(target, name=f"{operation} target")
            return self._resolve_named_capability_target(field_name, target_name)
        return self._resolve_direct_capability_target(
            field_name=field_name,
            protocol=protocol,
            target=target,
        )

    def _resolve_named_capability_target(self, field_name: str, target_name: str) -> object:
        capability_target = self._capability_registry.named_target(field_name, target_name)
        if capability_target is not None:
            return capability_target
        return self._require_provider(target_name)

    def _resolve_direct_capability_target(
        self,
        *,
        field_name: str,
        protocol: type,
        target: object,
    ) -> object:
        return self._capability_registry.direct_target(
            field_name=field_name,
            protocol=protocol,
            target=target,
        )

    def _call_capability(
        self,
        *,
        field_name: str,
        protocol: type,
        target: object | None,
        operation: str,
        target_label: str,
        args: tuple[object, ...] = (),
        kwargs: JSONDict | None = None,
    ) -> object:
        return _call_resolved_capability(
            field_name=field_name,
            resolved=self._resolve_capability_target(
                field_name=field_name,
                protocol=protocol,
                target=target,
                operation=operation,
                target_label=target_label,
            ),
            args=args,
            kwargs=kwargs,
        )

    def _select_capability_target(
        self,
        positional: object | None,
        keyword: object | None,
        *,
        operation: str,
        keyword_name: str,
    ) -> object | None:
        if positional is not None and keyword is not None:
            raise WorldForgeError(
                f"{operation}() accepts either positional provider or {keyword_name}=, not both."
            )
        return keyword if keyword is not None else positional

    def providers(self) -> list[str]:
        return sorted(self._registered_provider_names())

    def _provider_catalog(self, *, include_known: bool = True) -> dict[str, BaseProvider]:
        catalog: dict[str, BaseProvider] = {}
        if include_known:
            for provider in self._known_providers():
                catalog[provider.name] = provider
        for provider in self._providers.values():
            catalog[provider.name] = provider
        return catalog

    def list_providers(self) -> list[ProviderInfo]:
        return [self.provider_info(name) for name in self.providers()]

    def list_provider_profiles(self) -> list[ProviderProfile]:
        return [self.provider_profile(name) for name in self.providers()]

    def builtin_provider_profiles(self) -> list[ProviderProfile]:
        catalog = self._provider_catalog(include_known=True)
        return [catalog[name].profile() for name in sorted(catalog)]

    def provider_info(self, name: str) -> ProviderInfo:
        provider_name = _require_non_empty_text(name, name="Provider name")
        if provider_name not in self._registered_provider_names():
            raise ProviderError(f"Provider '{provider_name}' is not registered.")
        profile = self.provider_profile(provider_name)
        return ProviderInfo(
            name=profile.name,
            capabilities=profile.capabilities,
            is_local=profile.is_local,
            description=profile.description,
        )

    def provider_profile(self, name: str) -> ProviderProfile:
        provider_name = _require_non_empty_text(name, name="Provider name")
        legacy_provider = self._registered_or_known_provider(provider_name, include_known=True)
        wrappers = self._capability_wrappers_for_name(provider_name)
        return self._merged_profile(
            provider_name,
            legacy_provider=legacy_provider,
            wrappers=wrappers,
        )

    def provider_health(self, name: str) -> ProviderHealth:
        provider_name = _require_non_empty_text(name, name="Provider name")
        legacy_provider = self._registered_or_known_provider(provider_name, include_known=True)
        wrappers = self._capability_wrappers_for_name(provider_name)
        return self._merged_health(
            provider_name,
            legacy_provider=legacy_provider,
            wrappers=wrappers,
        )

    def provider_lifecycle_status(
        self,
        name: str,
        *,
        run_warmup: bool = False,
        run_teardown: bool = False,
    ) -> ProviderLifecycleStatus:
        provider_name = _require_non_empty_text(name, name="Provider name")
        legacy_provider = self._registered_or_known_provider(provider_name, include_known=True)
        wrappers = self._capability_wrappers_for_name(provider_name)
        return self._merged_lifecycle_status(
            provider_name,
            legacy_provider=legacy_provider,
            wrappers=wrappers,
            run_warmup=run_warmup,
            run_teardown=run_teardown,
        )

    def provider_config_summary(self, name: str) -> ProviderConfigSummary:
        """Return value-free configuration status for a registered or known provider."""

        provider_name = _require_non_empty_text(name, name="Provider name")
        legacy_provider = self._registered_or_known_provider(provider_name, include_known=True)
        if legacy_provider is not None:
            return legacy_provider.config_summary()
        if self._capability_wrappers_for_name(provider_name):
            return ProviderConfigSummary(provider=provider_name, configured=True, fields=())
        raise ProviderError(f"Provider '{provider_name}' is unknown.")

    def provider_healths(self, capability: str | None = None) -> list[ProviderHealth]:
        names = self.providers()
        if capability:
            names = [
                name
                for name in names
                if self.provider_profile(name).capabilities.supports(capability)
            ]
        return [self.provider_health(name) for name in names]

    def doctor(
        self,
        capability: str | None = None,
        *,
        registered_only: bool = False,
    ) -> DoctorReport:
        """Return provider, state-directory, and configuration diagnostics.

        By default diagnostics include known optional providers even when they are not registered,
        so missing environment variables or optional runtimes are visible before a workflow fails.
        Pass ``registered_only=True`` to inspect only the providers active in this process.
        """

        return _doctor_report(
            self,
            capability=capability,
            registered_only=registered_only,
        )

    def create_world(self, name: str, provider: str = "mock", *, description: str = "") -> World:
        """Create an empty world bound to a registered default provider."""

        selected_provider = _require_non_empty_text(provider, name="Provider name")
        if selected_provider not in self._registered_provider_names():
            raise ProviderError(f"Provider '{selected_provider}' is not registered.")
        return World(name=name, provider=selected_provider, forge=self, description=description)

    def create_world_from_prompt(
        self,
        prompt: str,
        *,
        provider: str = "mock",
        name: str | None = None,
    ) -> World:
        prompt_text = _require_non_empty_text(prompt, name="Prompt")
        world = self.create_world(
            _prompt_world_name(name),
            provider,
            description=prompt_text,
        )
        _seed_prompt_world(world, prompt_text)
        return world

    def save_world(self, world: World) -> str:
        """Validate and atomically write a world to the local JSON state directory."""

        return _save_world(self, world)

    def load_world(self, world_id: str) -> World:
        """Load a world from local JSON after validating its storage identifier and payload."""

        return _load_world(self, world_id)

    def delete_world(self, world_id: str) -> str:
        """Delete a persisted world file after validating its storage identifier."""

        return _delete_world(self, world_id)

    def list_worlds(self) -> list[str]:
        return _list_worlds(self)

    def export_world(self, world_id: str, *, format: str = "json") -> str:
        return _export_world(self, world_id, format=format)

    def import_world(
        self,
        payload: str,
        *,
        format: str = "json",
        new_id: bool = False,
        name: str | None = None,
    ) -> World:
        """Restore a world from exported JSON without saving it automatically."""

        return _import_world(self, payload, format=format, new_id=new_id, name=name)

    def fork_world(
        self, world_id: str, *, history_index: int = 0, name: str | None = None
    ) -> World:
        return _fork_world(self, world_id, history_index=history_index, name=name)

    def predict(
        self,
        world_state: JSONDict,
        action: Action,
        steps: int = 1,
        provider: str | Predictor | BaseProvider | None = None,
        *,
        predictor: str | Predictor | BaseProvider | None = None,
    ) -> PredictionPayload:
        require_positive_int(steps, name="steps")
        if not isinstance(action, Action):
            raise WorldForgeError("predict() action must be an Action.")
        action.to_json()
        target = self._select_capability_target(
            provider,
            predictor,
            operation="predict",
            keyword_name="predictor",
        )
        return cast(
            PredictionPayload,
            self._call_capability(
                field_name="predictor",
                protocol=Predictor,
                target=target,
                operation="predict",
                target_label="predictor",
                args=(world_state, action, steps),
            ),
        )

    def embed(
        self,
        provider: str | Embedder | BaseProvider | None = None,
        *,
        embedder: str | Embedder | BaseProvider | None = None,
        text: str,
    ) -> EmbeddingResult:
        text = _require_non_empty_text(
            text,
            name="embed() text",
            message="embed() text must be a non-empty string and not whitespace.",
        )
        target = self._select_capability_target(
            provider,
            embedder,
            operation="embed",
            keyword_name="embedder",
        )
        return cast(
            EmbeddingResult,
            self._call_capability(
                field_name="embedder",
                protocol=Embedder,
                target=target,
                operation="embed",
                target_label="embedder",
                kwargs={"text": text},
            ),
        )

    def score_actions(
        self,
        provider: str | Cost | BaseProvider | None = None,
        *,
        cost: str | Cost | BaseProvider | None = None,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult:
        target = self._select_capability_target(
            provider,
            cost,
            operation="score_actions",
            keyword_name="cost",
        )
        return cast(
            ActionScoreResult,
            self._call_capability(
                field_name="cost",
                protocol=Cost,
                target=target,
                operation="score_actions",
                target_label="cost",
                kwargs={
                    "info": info,
                    "action_candidates": action_candidates,
                },
            ),
        )

    def select_actions(
        self,
        provider: str | Policy | BaseProvider | None = None,
        *,
        policy: str | Policy | BaseProvider | None = None,
        info: JSONDict,
    ) -> ActionPolicyResult:
        target = self._select_capability_target(
            provider,
            policy,
            operation="select_actions",
            keyword_name="policy",
        )
        return cast(
            ActionPolicyResult,
            self._call_capability(
                field_name="policy",
                protocol=Policy,
                target=target,
                operation="select_actions",
                target_label="policy",
                kwargs={"info": info},
            ),
        )


def list_eval_suites() -> list[str]:
    """Return built-in evaluation suite identifiers."""

    from worldforge.evaluation import EvaluationSuite

    return EvaluationSuite.builtin_names()


def run_eval(
    suite: str,
    provider: str,
    *,
    forge: WorldForge | None = None,
) -> list[EvaluationResult]:
    """Run a built-in evaluation suite and return scenario-level results."""

    from worldforge.evaluation import EvaluationSuite

    active_forge = forge or WorldForge()
    return EvaluationSuite.from_builtin(suite).run(provider, forge=active_forge)
