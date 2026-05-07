"""Tests for provider routing and fallback policies (WF-FEAT-005)."""

from __future__ import annotations

import pytest

from worldforge import (
    ProviderCapabilities,
    ProviderEvent,
    ProviderRoutingPolicy,
    RoutingAttempt,
    RoutingResult,
    WorldForge,
    WorldForgeError,
    route_capability,
)
from worldforge.provider_routing import ROUTING_ATTEMPT_STATUSES
from worldforge.providers import BaseProvider, MockProvider, ProviderError
from worldforge.providers.base import ProviderProfileSpec


def _make_forge(tmp_path) -> WorldForge:
    return WorldForge(state_dir=tmp_path, auto_register_remote=False)


def _generate_only_provider(name: str) -> BaseProvider:
    return BaseProvider(
        name=name,
        capabilities=ProviderCapabilities(generate=True),
        profile=ProviderProfileSpec(
            description=f"Test-only generate provider {name}.",
            implementation_status="experimental",
            is_local=True,
        ),
    )


def test_policy_validates_known_capability() -> None:
    with pytest.raises(WorldForgeError, match="must be one of"):
        ProviderRoutingPolicy(capability="not-a-capability", preferred="mock")


def test_policy_validates_non_empty_preferred() -> None:
    with pytest.raises(WorldForgeError, match="non-empty string"):
        ProviderRoutingPolicy(capability="predict", preferred="   ")


def test_policy_validates_fallbacks_are_strings() -> None:
    with pytest.raises(WorldForgeError, match="fallbacks"):
        ProviderRoutingPolicy(
            capability="predict",
            preferred="mock",
            fallbacks=("",),
        )


def test_policy_rejects_duplicate_provider_in_chain() -> None:
    with pytest.raises(WorldForgeError, match="duplicated in chain"):
        ProviderRoutingPolicy(
            capability="predict",
            preferred="mock",
            fallbacks=("alt", "alt"),
        )

    with pytest.raises(WorldForgeError, match="duplicated in chain"):
        ProviderRoutingPolicy(
            capability="predict",
            preferred="mock",
            fallbacks=("mock",),
        )


def test_policy_normalises_whitespace_and_serialises() -> None:
    policy = ProviderRoutingPolicy(
        capability="generate",
        preferred="  mock  ",
        fallbacks=("  alt  ",),
        operation="  remote-fallback  ",
    )
    assert policy.preferred == "mock"
    assert policy.fallbacks == ("alt",)
    assert policy.operation == "remote-fallback"
    assert policy.chain() == ("mock", "alt")
    assert policy.to_dict() == {
        "capability": "generate",
        "preferred": "mock",
        "fallbacks": ["alt"],
        "require_capability": True,
        "operation": "remote-fallback",
    }


def test_routing_attempt_validates_status() -> None:
    assert "succeeded" in ROUTING_ATTEMPT_STATUSES
    with pytest.raises(WorldForgeError, match="status must be one of"):
        RoutingAttempt(provider="mock", capability="predict", status="weird")


def test_routing_result_to_dict_includes_attempts() -> None:
    result = RoutingResult(
        capability="predict",
        chosen="mock",
        succeeded=True,
        attempts=(RoutingAttempt(provider="mock", capability="predict", status="succeeded"),),
        value={"answer": 42},
    )
    payload = result.to_dict()
    assert payload["capability"] == "predict"
    assert payload["chosen"] == "mock"
    assert payload["succeeded"] is True
    assert payload["attempts"][0]["status"] == "succeeded"


def test_route_capability_returns_first_success(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="primary"))
    forge.register_provider(MockProvider(name="alt"))

    invoked: list[str] = []

    def invoke(name: str) -> str:
        invoked.append(name)
        return f"result-from-{name}"

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="primary",
        fallbacks=("alt",),
    )
    result = route_capability(policy, forge, invoke=invoke)

    assert result.succeeded is True
    assert result.chosen == "primary"
    assert result.value == "result-from-primary"
    assert invoked == ["primary"]
    assert [a.status for a in result.attempts] == ["succeeded"]


def test_route_capability_falls_back_on_provider_error(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="flaky"))
    forge.register_provider(MockProvider(name="alt"))

    invoked: list[str] = []

    def invoke(name: str) -> str:
        invoked.append(name)
        if name == "flaky":
            raise ProviderError("flaky exhausted retry budget")
        return f"recovered-from-{name}"

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="flaky",
        fallbacks=("alt",),
    )
    result = route_capability(policy, forge, invoke=invoke)

    assert result.succeeded is True
    assert result.chosen == "alt"
    assert result.value == "recovered-from-alt"
    assert invoked == ["flaky", "alt"]
    assert [a.status for a in result.attempts] == ["failed", "succeeded"]
    failed = result.failed_attempts()[0]
    assert failed.provider == "flaky"
    assert failed.error_type == "ProviderError"
    assert "flaky exhausted retry budget" in (failed.error_message or "")


def test_route_capability_skips_unregistered_providers(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="alt"))

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="ghost",
        fallbacks=("alt",),
    )
    result = route_capability(policy, forge, invoke=lambda name: name)

    assert result.succeeded is True
    assert result.chosen == "alt"
    skipped = result.skipped_attempts()
    assert len(skipped) == 1
    assert skipped[0].provider == "ghost"
    assert skipped[0].status == "skipped-not-registered"


def test_route_capability_skips_capability_incompatible_providers(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(_generate_only_provider("gen-only"))
    forge.register_provider(MockProvider(name="alt"))

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="gen-only",
        fallbacks=("alt",),
    )
    result = route_capability(policy, forge, invoke=lambda name: name)

    assert result.succeeded is True
    assert result.chosen == "alt"
    skipped = result.skipped_attempts()
    assert [s.provider for s in skipped] == ["gen-only"]
    assert skipped[0].status == "skipped-incompatible"
    assert "does not advertise capability" in (skipped[0].reason or "")


def test_route_capability_can_disable_capability_check(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(_generate_only_provider("gen-only"))

    invoked: list[str] = []

    def invoke(name: str) -> str:
        invoked.append(name)
        return "ok"

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="gen-only",
        require_capability=False,
    )
    result = route_capability(policy, forge, invoke=invoke)

    assert result.succeeded is True
    assert result.chosen == "gen-only"
    assert invoked == ["gen-only"]


def test_route_capability_returns_failure_when_chain_exhausted(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="primary"))
    forge.register_provider(MockProvider(name="alt"))

    def invoke(name: str) -> str:
        raise ProviderError(f"{name} unavailable")

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="primary",
        fallbacks=("alt",),
    )
    result = route_capability(policy, forge, invoke=invoke)

    assert result.succeeded is False
    assert result.chosen is None
    assert result.value is None
    assert [a.status for a in result.attempts] == ["failed", "failed"]
    assert {a.provider for a in result.attempts} == {"primary", "alt"}


def test_route_capability_preserves_chain_order_for_determinism(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="a"))
    forge.register_provider(MockProvider(name="b"))
    forge.register_provider(MockProvider(name="c"))

    seen: list[str] = []

    def invoke(name: str) -> str:
        seen.append(name)
        if name in ("a", "b"):
            raise ProviderError(f"{name} cold")
        return name

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="a",
        fallbacks=("b", "c"),
    )
    result = route_capability(policy, forge, invoke=invoke)

    assert seen == ["a", "b", "c"]
    assert result.chosen == "c"
    assert [a.provider for a in result.attempts] == ["a", "b", "c"]


def test_route_capability_does_not_invoke_after_first_success(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="primary"))
    forge.register_provider(MockProvider(name="alt"))

    invoked: list[str] = []

    def invoke(name: str) -> str:
        invoked.append(name)
        return name

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="primary",
        fallbacks=("alt",),
    )
    route_capability(policy, forge, invoke=invoke)

    assert invoked == ["primary"]


def test_route_capability_propagates_underlying_provider_events(tmp_path) -> None:
    events: list[ProviderEvent] = []
    forge = WorldForge(
        state_dir=tmp_path,
        auto_register_remote=False,
        event_handler=events.append,
    )
    forge.register_provider(MockProvider(name="primary"))

    policy = ProviderRoutingPolicy(
        capability="generate",
        preferred="primary",
    )

    def invoke(name: str) -> object:
        return forge.generate("orbiting cube", name, duration_seconds=1.0)

    result = route_capability(policy, forge, invoke=invoke)

    assert result.succeeded is True
    success_events = [e for e in events if e.phase == "success"]
    assert any(e.provider == "primary" and e.operation == "generate" for e in success_events)


def test_route_capability_validates_inputs(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="mock"))

    with pytest.raises(WorldForgeError, match="ProviderRoutingPolicy"):
        route_capability("not-a-policy", forge, invoke=lambda name: name)  # type: ignore[arg-type]

    policy = ProviderRoutingPolicy(capability="predict", preferred="mock")
    with pytest.raises(WorldForgeError, match="invoke"):
        route_capability(policy, forge, invoke=None)  # type: ignore[arg-type]


def test_route_capability_records_unexpected_exceptions_as_failed(tmp_path) -> None:
    forge = _make_forge(tmp_path)
    forge.register_provider(MockProvider(name="primary"))
    forge.register_provider(MockProvider(name="alt"))

    def invoke(name: str) -> str:
        if name == "primary":
            raise RuntimeError("unexpected internal failure")
        return "ok"

    policy = ProviderRoutingPolicy(
        capability="predict",
        preferred="primary",
        fallbacks=("alt",),
    )
    result = route_capability(policy, forge, invoke=invoke)

    assert result.succeeded is True
    assert result.chosen == "alt"
    failed = result.failed_attempts()[0]
    assert failed.provider == "primary"
    assert failed.error_type == "RuntimeError"


def test_policy_rejects_non_sequence_fallbacks() -> None:
    with pytest.raises(WorldForgeError, match="sequence of provider names"):
        ProviderRoutingPolicy(
            capability="predict",
            preferred="mock",
            fallbacks="alt",  # type: ignore[arg-type]
        )


def test_policy_rejects_non_bool_require_capability() -> None:
    with pytest.raises(WorldForgeError, match="require_capability must be a bool"):
        ProviderRoutingPolicy(
            capability="predict",
            preferred="mock",
            require_capability="yes",  # type: ignore[arg-type]
        )


def test_policy_rejects_blank_operation() -> None:
    with pytest.raises(WorldForgeError, match="operation must be a non-empty string"):
        ProviderRoutingPolicy(
            capability="predict",
            preferred="mock",
            operation="   ",
        )


def test_routing_attempt_rejects_blank_provider() -> None:
    with pytest.raises(WorldForgeError, match="provider must be a non-empty string"):
        RoutingAttempt(provider="   ", capability="predict", status="succeeded")


def test_routing_attempt_rejects_unknown_capability() -> None:
    with pytest.raises(WorldForgeError, match="capability must be one of"):
        RoutingAttempt(provider="mock", capability="bogus", status="succeeded")


def test_routing_result_rejects_non_bool_succeeded() -> None:
    with pytest.raises(WorldForgeError, match="succeeded must be a bool"):
        RoutingResult(
            capability="predict",
            chosen="mock",
            succeeded="yes",  # type: ignore[arg-type]
            attempts=(),
        )


def test_routing_result_validates_construction_inputs() -> None:
    with pytest.raises(WorldForgeError, match="capability must be one of"):
        RoutingResult(
            capability="bogus",
            chosen=None,
            succeeded=False,
            attempts=(),
        )

    with pytest.raises(WorldForgeError, match="attempts must be a tuple"):
        RoutingResult(
            capability="predict",
            chosen=None,
            succeeded=False,
            attempts=["not-a-routing-attempt"],  # type: ignore[arg-type]
        )

    with pytest.raises(WorldForgeError, match="chosen must be"):
        RoutingResult(
            capability="predict",
            chosen="   ",
            succeeded=False,
            attempts=(),
        )
