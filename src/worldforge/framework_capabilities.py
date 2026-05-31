"""Capability protocol registration and dispatch helpers for ``WorldForge``."""

from __future__ import annotations

from collections.abc import Callable

from worldforge.capabilities import (
    CAPABILITY_FIELD_NAMES,
    CAPABILITY_FIELD_TO_NAME,
    CAPABILITY_PROTOCOLS,
    RunnableModel,
)
from worldforge.models import JSONDict, ProviderEvent, WorldForgeError
from worldforge.providers.base import BaseProvider
from worldforge.providers.observable import CAPABILITY_METHOD_MAP, _ObservableCapability


def provider_with_event_handler(
    provider: BaseProvider,
    event_handler: Callable[[ProviderEvent], None] | None,
) -> BaseProvider:
    if event_handler is None or provider.event_handler is not None:
        return provider
    provider.event_handler = event_handler
    return provider


def _capability_protocol_error(
    *,
    target: object,
    protocol: type,
    field_name: str,
) -> WorldForgeError:
    capability_name = CAPABILITY_FIELD_TO_NAME[field_name]
    return WorldForgeError(
        f"{type(target).__name__} does not satisfy the "
        f"{protocol.__name__} capability protocol for '{capability_name}'."
    )


def _unknown_capability_impl_error(impl: object) -> WorldForgeError:
    return WorldForgeError(
        f"{type(impl).__name__} does not satisfy any capability protocol. "
        f"Expected one of: {', '.join(sorted(CAPABILITY_PROTOCOLS))}."
    )


def _capability_call_kwargs(kwargs: JSONDict | None) -> JSONDict:
    return dict(kwargs or {})


def call_resolved_capability(
    *,
    field_name: str,
    resolved: object,
    args: tuple[object, ...],
    kwargs: JSONDict | None,
) -> object:
    call_kwargs = _capability_call_kwargs(kwargs)
    if isinstance(resolved, _ObservableCapability):
        return resolved.call(*args, **call_kwargs)
    method_name = CAPABILITY_METHOD_MAP[field_name][0]
    return getattr(resolved, method_name)(*args, **call_kwargs)


def _capability_impl_name(impl: object) -> str:
    impl_name = getattr(impl, "name", None)
    if not isinstance(impl_name, str) or not impl_name.strip():
        raise WorldForgeError(
            f"Capability impl '{type(impl).__name__}' must declare a non-empty 'name' attribute."
        )
    return impl_name


def _require_unique_capability_name(
    *,
    field_name: str,
    impl_name: str,
    registry: dict[str, _ObservableCapability],
) -> None:
    if impl_name not in registry:
        return
    raise WorldForgeError(
        f"Capability '{field_name}' already has a registered implementation named "
        f"'{impl_name}'. Names must be unique within a capability registry."
    )


class CapabilityRegistry:
    """Own per-capability observable wrappers and structural protocol dispatch."""

    def __init__(self, event_handler: Callable[[ProviderEvent], None] | None) -> None:
        self._event_handler = event_handler
        self._registries: dict[str, dict[str, _ObservableCapability]] = {
            field: {} for field in CAPABILITY_FIELD_NAMES
        }

    @property
    def registries(self) -> dict[str, dict[str, _ObservableCapability]]:
        return self._registries

    def register(self, impl: object) -> None:
        if isinstance(impl, RunnableModel):
            self._register_runnable_model(impl)
            return
        if self._register_matching_capabilities(impl):
            return
        raise _unknown_capability_impl_error(impl)

    def _register_runnable_model(self, impl: RunnableModel) -> None:
        capability_fields = list(impl.capability_fields())
        if not capability_fields:
            raise WorldForgeError(
                f"RunnableModel '{impl.name}' does not contain any capability impls."
            )
        for field_name, capability_impl in capability_fields:
            self.register_capability(field_name, capability_impl)

    def _register_matching_capabilities(self, impl: object) -> bool:
        matched = False
        for field_name, protocol in CAPABILITY_PROTOCOLS.items():
            if isinstance(impl, protocol):
                self.register_capability(field_name, impl)
                matched = True
        return matched

    def register_typed(self, field_name: str, impl: object, protocol: type) -> None:
        if not isinstance(impl, protocol):
            raise WorldForgeError(
                f"{type(impl).__name__} does not satisfy the "
                f"{protocol.__name__} capability protocol."
            )
        self.register_capability(field_name, impl)

    def register_capability(self, field_name: str, impl: object) -> None:
        registry = self._registries[field_name]
        impl_name = _capability_impl_name(impl)
        _require_unique_capability_name(
            field_name=field_name,
            impl_name=impl_name,
            registry=registry,
        )
        registry[impl_name] = _ObservableCapability(
            impl,
            kind=field_name,
            event_handler=self._event_handler,
        )

    def registered_names(self) -> set[str]:
        return {name for registry in self._registries.values() for name in registry}

    def wrappers_for_name(self, name: str) -> tuple[_ObservableCapability, ...]:
        return tuple(
            registry[name]
            for field_name in CAPABILITY_FIELD_NAMES
            for registry in (self._registries[field_name],)
            if name in registry
        )

    def named_target(self, field_name: str, target_name: str) -> _ObservableCapability | None:
        return self._registries[field_name].get(target_name)

    def direct_target(
        self,
        *,
        field_name: str,
        protocol: type,
        target: object,
    ) -> object:
        if isinstance(target, BaseProvider):
            return provider_with_event_handler(target, self._event_handler)
        if not isinstance(target, protocol):
            raise _capability_protocol_error(
                target=target,
                protocol=protocol,
                field_name=field_name,
            )
        return _ObservableCapability(
            target,
            kind=field_name,
            event_handler=self._event_handler,
        )
