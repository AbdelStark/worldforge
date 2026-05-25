"""Provider contract evidence for adapter authors and CLI workflows."""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from worldforge.models import JSONDict, WorldForgeError, _redact_observable_text, dump_json
from worldforge.providers import BaseProvider
from worldforge.providers.catalog import ProviderEventHandler
from worldforge.testing.providers import (
    assert_provider_contract,
    assert_provider_metadata_conformance,
)

PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION = 1
PROVIDER_CONTRACT_STATUSES: tuple[str, ...] = ("passed", "failed", "skipped")

_HOST_LOCAL_PATH_PATTERN = re.compile(r"(/Users/|/private/|/tmp/|/var/folders/|[A-Za-z]:[\\/])")
_SECRET_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|secret|signature|token)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProviderContractCheck:
    """One provider contract check row."""

    name: str
    status: str
    detail: str
    next_step: str

    def __post_init__(self) -> None:
        if self.status not in PROVIDER_CONTRACT_STATUSES:
            allowed = ", ".join(PROVIDER_CONTRACT_STATUSES)
            raise WorldForgeError(f"ProviderContractCheck status must be one of: {allowed}.")

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "next_step": self.next_step,
        }


@dataclass(frozen=True, slots=True)
class ProviderContractEvidence:
    """Issue-ready contract evidence for one provider."""

    provider: str
    registered: bool
    configured: bool
    profile: JSONDict
    health: JSONDict
    checks: tuple[ProviderContractCheck, ...]
    validation_commands: tuple[str, ...]
    factory_path: str | None = None
    live: bool = False
    safe_to_attach: bool = True
    schema_version: int = PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION
    claim_boundary: str = (
        "Provider contract evidence checks declared WorldForge adapter surfaces. "
        "Skipped host-owned checks are not promotion evidence, and passing checks do not claim "
        "physical fidelity, media quality, or real robot safety."
    )

    @property
    def passed_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "passed")

    @property
    def failed_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "failed")

    @property
    def skipped_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "skipped")

    @property
    def status(self) -> str:
        return "failed" if self.failed_count else "passed"

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "registered": self.registered,
            "configured": self.configured,
            "live": self.live,
            "factory_path": self.factory_path,
            "status": self.status,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "safe_to_attach": self.safe_to_attach,
            "claim_boundary": self.claim_boundary,
            "profile": self.profile,
            "health": self.health,
            "checks": [check.to_dict() for check in self.checks],
            "validation_commands": list(self.validation_commands),
            "next_steps": [
                check.next_step for check in self.checks if check.status in {"failed", "skipped"}
            ],
        }
        dump_json(payload)
        return payload

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# Provider Contract Evidence",
            "",
            f"- provider: `{self.provider}`",
            f"- status: `{self.status}`",
            f"- registered: `{str(self.registered).lower()}`",
            f"- configured: `{str(self.configured).lower()}`",
            f"- live: `{str(self.live).lower()}`",
            f"- safe_to_attach: `{str(self.safe_to_attach).lower()}`",
            f"- passed: {self.passed_count}",
            f"- failed: {self.failed_count}",
            f"- skipped: {self.skipped_count}",
            "",
            self.claim_boundary,
            "",
            "## Checks",
            "",
            "| Check | Status | Detail | Next step |",
            "| --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| `{check.name}` | `{check.status}` | {check.detail} | {check.next_step} |"
            for check in self.checks
        )
        lines.extend(["", "## Validation Commands", ""])
        lines.extend(f"- `{command}`" for command in self.validation_commands)
        return "\n".join(lines) + "\n"


def provider_from_factory_path(
    factory_path: str,
    *,
    event_handler: ProviderEventHandler = None,
) -> BaseProvider:
    """Load a ``module:factory`` provider factory path and construct its provider."""

    module_name, separator, attribute_path = factory_path.partition(":")
    if not separator or not module_name.strip() or not attribute_path.strip():
        raise WorldForgeError("Provider factory path must use 'module:factory' syntax.")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        detail = _safe_detail(str(exc))
        raise WorldForgeError(
            f"Provider factory module '{module_name}' could not be imported: {detail}"
        ) from exc
    target: object = module
    for attribute in attribute_path.split("."):
        if not attribute:
            raise WorldForgeError("Provider factory path contains an empty attribute segment.")
        try:
            target = getattr(target, attribute)
        except AttributeError as exc:
            raise WorldForgeError(
                f"Provider factory path '{factory_path}' is missing attribute '{attribute}'."
            ) from exc
    if not callable(target):
        raise WorldForgeError("Provider factory path must resolve to a callable.")
    try:
        provider = _call_provider_factory(target, event_handler=event_handler)
    except Exception as exc:
        detail = _safe_detail(str(exc) or type(exc).__name__)
        raise WorldForgeError(f"Provider factory '{factory_path}' raised: {detail}") from exc
    if not isinstance(provider, BaseProvider):
        raise WorldForgeError(
            f"Provider factory returned {type(provider).__name__}, expected BaseProvider."
        )
    return provider


def run_provider_contract(
    provider: BaseProvider,
    *,
    registered: bool,
    factory_path: str | None = None,
    live: bool = False,
    score_info: JSONDict | None = None,
    score_action_candidates: object | None = None,
    policy_info: JSONDict | None = None,
) -> ProviderContractEvidence:
    """Run provider contract checks and return safe-to-attach evidence."""

    checks: list[ProviderContractCheck] = []
    try:
        metadata_report = assert_provider_metadata_conformance(provider)
    except AssertionError as exc:
        profile = provider.profile().to_dict()
        health = provider.health().to_dict()
        checks.append(
            _failed_check(
                "metadata",
                exc,
                provider=provider.name,
                factory_path=factory_path,
            )
        )
        return _evidence(
            provider=provider,
            registered=registered,
            configured=provider.configured(),
            profile=profile,
            health=health,
            checks=checks,
            factory_path=factory_path,
            live=live,
        )

    profile = metadata_report.profile
    health = metadata_report.health
    configured = metadata_report.configured
    checks.append(
        ProviderContractCheck(
            name="metadata",
            status="passed",
            detail="provider profile, info, health, and capability metadata are coherent",
            next_step="keep metadata and capability declarations synchronized with implementation",
        )
    )
    advertised = tuple(
        capability for capability in profile.capabilities.enabled_names() if capability != "plan"
    )
    if not advertised:
        checks.append(
            ProviderContractCheck(
                name="capabilities",
                status="skipped",
                detail="provider advertises no executable provider capability",
                next_step="advertise a capability only after its method passes the contract helper",
            )
        )
    elif configured and not live and not profile.is_local:
        checks.extend(_host_owned_skips(advertised))
    else:
        try:
            contract_report = assert_provider_contract(
                provider,
                score_info=score_info,
                score_action_candidates=score_action_candidates,
                policy_info=policy_info,
            )
        except Exception as exc:
            checks.append(
                _failed_check(
                    "capability-contract",
                    exc,
                    provider=provider.name,
                    factory_path=factory_path,
                )
            )
        else:
            exercised = set(contract_report.exercised_operations)
            for capability in advertised:
                if capability in exercised:
                    checks.append(
                        ProviderContractCheck(
                            name=capability,
                            status="passed",
                            detail=f"{capability} returned a valid WorldForge result",
                            next_step=f"keep {capability} fixture coverage with the provider",
                        )
                    )
                else:
                    checks.append(
                        ProviderContractCheck(
                            name=capability,
                            status="skipped",
                            detail=(
                                "provider is not configured; fail-closed ProviderError behavior "
                                "was verified"
                            ),
                            next_step=(
                                "configure the host runtime and rerun with --live only when live "
                                "provider calls are intended"
                            ),
                        )
                    )

    return _evidence(
        provider=provider,
        registered=registered,
        configured=configured,
        profile=profile.to_dict(),
        health=health.to_dict(),
        checks=checks,
        factory_path=factory_path,
        live=live,
    )


def load_json_contract_input(path: Path | None, *, name: str) -> object | None:
    """Load optional JSON input used by provider contract checks."""

    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldForgeError(f"Failed to read {name} file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{name} file {path} contains invalid JSON: {exc}") from exc
    return payload


def _call_provider_factory(
    factory: Callable[..., object],
    *,
    event_handler: ProviderEventHandler,
) -> object:
    try:
        return factory(event_handler=event_handler)
    except TypeError as keyword_error:
        try:
            return factory(event_handler)
        except TypeError:
            try:
                return factory()
            except TypeError:
                raise keyword_error from None


def _host_owned_skips(capabilities: Sequence[str]) -> list[ProviderContractCheck]:
    return [
        ProviderContractCheck(
            name=capability,
            status="skipped",
            detail="configured provider is not local; capability requires --live to call",
            next_step=f"rerun with --live on a prepared host to exercise {capability}",
        )
        for capability in capabilities
    ]


def _failed_check(
    name: str,
    exc: BaseException,
    *,
    provider: str,
    factory_path: str | None,
) -> ProviderContractCheck:
    detail = _safe_detail(str(exc) or type(exc).__name__)
    command = (
        f"uv run worldforge provider contract --factory {factory_path} --format json"
        if factory_path is not None
        else f"uv run worldforge provider contract {provider} --format json"
    )
    return ProviderContractCheck(
        name=name,
        status="failed",
        detail=detail,
        next_step=f"fix provider '{provider}' or its fixtures, then rerun `{command}`",
    )


def _evidence(
    *,
    provider: BaseProvider,
    registered: bool,
    configured: bool,
    profile: JSONDict,
    health: JSONDict,
    checks: list[ProviderContractCheck],
    factory_path: str | None,
    live: bool,
) -> ProviderContractEvidence:
    return ProviderContractEvidence(
        provider=provider.name,
        registered=registered,
        configured=configured,
        profile=profile,
        health=health,
        checks=tuple(checks),
        validation_commands=_validation_commands(
            provider.name,
            factory_path=factory_path,
            live=live,
        ),
        factory_path=factory_path,
        live=live,
    )


def _validation_commands(provider: str, *, factory_path: str | None, live: bool) -> tuple[str, ...]:
    command = (
        f"uv run worldforge provider contract --factory {factory_path} --format json"
        if factory_path is not None
        else f"uv run worldforge provider contract {provider} --format json"
    )
    if live:
        command += " --live"
    return (
        command,
        "uv run pytest tests/test_provider_contracts.py tests/test_provider_entry_points.py",
    )


def _safe_detail(detail: str) -> str:
    redacted = _HOST_LOCAL_PATH_PATTERN.sub("[host-local-path]", _redact_observable_text(detail))
    return _SECRET_PATTERN.sub("[redacted]", redacted)


__all__ = [
    "PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION",
    "PROVIDER_CONTRACT_STATUSES",
    "ProviderContractCheck",
    "ProviderContractEvidence",
    "load_json_contract_input",
    "provider_from_factory_path",
    "run_provider_contract",
]
