"""Textual-free provider-screen view helpers for TheWorldHarness."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from worldforge.harness.connectors import ProviderConnectorSummary
from worldforge.harness.tui_log_view import RichLogSpec
from worldforge.models import CAPABILITY_NAMES

PROVIDERS_EMPTY_MESSAGE = "No providers registered — set env vars or run with provider mock."
PROVIDERS_DETAIL_EMPTY_MESSAGE = "Select a provider."
PROVIDER_REGISTRATION_EMPTY_ERROR = "Provider id must be non-empty."
PROVIDER_FIELD_LABEL_CLASS = "field-label"


@dataclass(frozen=True, slots=True)
class ProviderButtonSpec:
    widget_id: str
    label: str
    variant: str


@dataclass(frozen=True, slots=True)
class ProviderInputSpec:
    widget_id: str
    label: str
    placeholder: str = ""


@dataclass(frozen=True, slots=True)
class RegisterProviderModalSpec:
    card_id: str
    title_id: str
    title: str
    name: ProviderInputSpec
    note_id: str
    note: str
    actions_id: str
    cancel: ProviderButtonSpec
    submit: ProviderButtonSpec


@dataclass(frozen=True, slots=True)
class ProviderActionSpec:
    widget_id: str
    label: str
    variant: str
    action: str


@dataclass(frozen=True, slots=True)
class ProviderBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


@dataclass(frozen=True, slots=True)
class ProviderOutputSpec:
    widget_id: str
    message: str = ""

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class ProviderTableSpec:
    widget_id: str
    columns: tuple[str, ...]

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class ProviderScreenSpec:
    root_id: str
    body_id: str
    table_wrap_id: str
    table: ProviderTableSpec
    empty: ProviderOutputSpec
    detail: ProviderOutputSpec
    log: RichLogSpec
    actions_id: str


REGISTER_PROVIDER_MODAL_SPEC = RegisterProviderModalSpec(
    card_id="register-provider-card",
    title_id="register-provider-title",
    title="Register deterministic provider",
    name=ProviderInputSpec("register-provider-name", "Provider id", "mock-lab"),
    note_id="register-provider-note",
    note="Registers a MockProvider variant. Live optional runtimes remain host-owned.",
    actions_id="register-provider-actions",
    cancel=ProviderButtonSpec("register-provider-cancel", "Cancel", "default"),
    submit=ProviderButtonSpec("register-provider-submit", "Register", "primary"),
)
PROVIDER_SCREEN_SPEC = ProviderScreenSpec(
    root_id="providers-root",
    body_id="providers-body",
    table_wrap_id="providers-table-wrap",
    table=ProviderTableSpec(
        "providers-table",
        ("provider", "status", "credentials", "runtime", *CAPABILITY_NAMES),
    ),
    empty=ProviderOutputSpec("providers-empty", PROVIDERS_EMPTY_MESSAGE),
    detail=ProviderOutputSpec("providers-detail", PROVIDERS_DETAIL_EMPTY_MESSAGE),
    log=RichLogSpec("providers-log"),
    actions_id="providers-actions",
)
PROVIDER_ACTION_SPECS: tuple[ProviderActionSpec, ...] = (
    ProviderActionSpec("provider-run", "Run predict", "primary", "run"),
    ProviderActionSpec("provider-cancel", "Cancel", "warning", "cancel"),
    ProviderActionSpec("provider-register", "Register", "default", "register"),
)
PROVIDER_BINDING_SPECS: tuple[ProviderBindingSpec, ...] = (
    ProviderBindingSpec("enter", "select_provider", "Use"),
    ProviderBindingSpec("p", "run_predict", "Predict"),
    ProviderBindingSpec("r", "register_provider", "Register"),
    ProviderBindingSpec("escape", "cancel_or_back", "Cancel/Back"),
)
REGISTER_PROVIDER_BINDING_SPECS: tuple[ProviderBindingSpec, ...] = (
    ProviderBindingSpec("escape", "cancel", "Cancel"),
)
PROVIDER_TABLE_SELECTOR = PROVIDER_SCREEN_SPEC.table.selector
PROVIDER_EMPTY_SELECTOR = PROVIDER_SCREEN_SPEC.empty.selector
PROVIDER_DETAIL_SELECTOR = PROVIDER_SCREEN_SPEC.detail.selector
PROVIDER_LOG_SELECTOR = PROVIDER_SCREEN_SPEC.log.selector
PROVIDER_RUN_BUTTON_ID = PROVIDER_ACTION_SPECS[0].widget_id
PROVIDER_CANCEL_BUTTON_ID = PROVIDER_ACTION_SPECS[1].widget_id
PROVIDER_REGISTER_BUTTON_ID = PROVIDER_ACTION_SPECS[2].widget_id


@dataclass(frozen=True, slots=True)
class ProviderRegistrationValidation:
    """Validation result for the register-provider modal."""

    provider_name: str | None = None
    error: str | None = None


def provider_table_row(
    row: ProviderConnectorSummary,
    *,
    capability_names: Sequence[str] = CAPABILITY_NAMES,
) -> tuple[str, ...]:
    return (
        row.name,
        row.status,
        provider_credentials_label(row),
        provider_runtime_label(row),
        *(
            provider_capability_cell(
                capability in row.capabilities,
                implementation_status=row.implementation_status,
            )
            for capability in capability_names
        ),
    )


def provider_credentials_label(row: ProviderConnectorSummary) -> str:
    if row.status == "scaffold":
        return "n/a"
    if row.missing_env_vars:
        return "missing"
    return "ok"


def provider_runtime_label(row: ProviderConnectorSummary) -> str:
    if row.status == "scaffold":
        return "scaffold"
    if row.status == "missing_dependency":
        return "deps"
    return "ok"


def provider_capability_cell(
    enabled: bool,
    *,
    implementation_status: str,
) -> str:
    if not enabled:
        return ""
    return "○" if implementation_status == "scaffold" else "●"


def provider_registration_from_form(value: str | None) -> ProviderRegistrationValidation:
    """Return a normalized provider name or user-facing validation error."""

    name = (value or "").strip()
    if not name:
        return ProviderRegistrationValidation(error=PROVIDER_REGISTRATION_EMPTY_ERROR)
    return ProviderRegistrationValidation(provider_name=name)


def provider_predict_target(
    *,
    current_provider: object,
    current_row_provider: str | None,
    provider_names: Sequence[str],
) -> str:
    """Choose the provider for a predict action from current app/table state."""

    if isinstance(current_provider, str) and current_provider in provider_names:
        return current_provider
    return current_row_provider or "mock"


def provider_cancel_target(
    *,
    current_provider: object,
    current_row_provider: str | None,
) -> str:
    """Choose the provider name to attach to a cancellation event."""

    if isinstance(current_provider, str):
        return current_provider
    return current_row_provider or "mock"


def provider_success_summary(latency_ms: float) -> dict[str, float | int | str]:
    """Return the detail-pane summary for a successful provider call."""

    return {
        "phase": "success",
        "latency_ms": latency_ms,
        "retries": 0,
    }
