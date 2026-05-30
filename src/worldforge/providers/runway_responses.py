"""Runway response parsers and safe output summaries."""

from __future__ import annotations

from dataclasses import dataclass

from worldforge.models import _sanitize_observable_target

from .base import ProviderError


def artifact_url_summary(url: str) -> str:
    sanitized = _sanitize_observable_target(url)
    if sanitized is None:
        raise ProviderError("Runway task output URL must be a non-empty string.")
    return sanitized


@dataclass(slots=True, frozen=True)
class RunwayOrganizationResponse:
    """Validated response from Runway organization health checks."""

    organization_id: str | None = None
    name: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
    ) -> RunwayOrganizationResponse:
        organization_id = _optional_runway_organization_text(
            payload.get("id"),
            provider_name=provider_name,
            field_name="id",
        )
        name = _optional_runway_organization_text(
            payload.get("name"),
            provider_name=provider_name,
            field_name="name",
        )
        _validate_runway_organization_identity(
            organization_id=organization_id,
            name=name,
            provider_name=provider_name,
        )
        return cls(
            organization_id=organization_id,
            name=name,
        )

    def details(self) -> str:
        return self.name or self.organization_id or "organization ok"


def _optional_runway_organization_text(
    value: object,
    *,
    provider_name: str,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ProviderError(
        f"Provider '{provider_name}' organization response field '{field_name}' "
        "must be a non-empty string when present."
    )


def _validate_runway_organization_identity(
    *,
    organization_id: str | None,
    name: str | None,
    provider_name: str,
) -> None:
    if organization_id is not None or name is not None:
        return
    raise ProviderError(
        f"Provider '{provider_name}' organization response must include 'id' or 'name'."
    )


@dataclass(slots=True, frozen=True)
class RunwayTaskCreationResponse:
    """Validated response returned when creating a Runway task."""

    task_id: str

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
        operation_name: str,
    ) -> RunwayTaskCreationResponse:
        task_id = payload.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ProviderError(
                f"Provider '{provider_name}' {operation_name} response field 'id' "
                "must be a non-empty task id."
            )
        return cls(task_id=task_id.strip())


@dataclass(slots=True, frozen=True)
class RunwayTaskStatusResponse:
    """Validated response returned when polling a Runway task."""

    task_id: str
    status: str
    outputs: tuple[str, ...] = ()
    message: str = ""

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
        expected_task_id: str,
    ) -> RunwayTaskStatusResponse:
        return cls(
            task_id=_task_status_id(
                payload,
                provider_name=provider_name,
                expected_task_id=expected_task_id,
            ),
            status=_task_status_value(
                payload,
                provider_name=provider_name,
                task_id=expected_task_id,
            ),
            outputs=_task_status_outputs(
                payload,
                provider_name=provider_name,
                task_id=expected_task_id,
            ),
            message=_payload_message(payload),
        )

    def require_outputs(self, *, provider_name: str) -> tuple[str, ...]:
        if not self.outputs:
            raise ProviderError(
                f"Provider '{provider_name}' task {self.task_id} completed without outputs."
            )
        return self.outputs


def _payload_message(payload: dict[str, object]) -> str:
    for key in ("failure", "error", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested_message = value.get("message")
            if isinstance(nested_message, str) and nested_message.strip():
                return nested_message.strip()
    return "no failure detail returned"


def _task_status_id(
    payload: dict[str, object],
    *,
    provider_name: str,
    expected_task_id: str,
) -> str:
    task_id = payload.get("id")
    if task_id is None:
        return expected_task_id
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProviderError(
            f"Provider '{provider_name}' task response field 'id' "
            "must be a non-empty string when present."
        )
    if task_id.strip() != expected_task_id:
        raise ProviderError(
            f"Provider '{provider_name}' task response id '{task_id}' "
            f"does not match requested task '{expected_task_id}'."
        )
    return expected_task_id


def _task_status_value(
    payload: dict[str, object],
    *,
    provider_name: str,
    task_id: str,
) -> str:
    status = payload.get("status")
    if not isinstance(status, str) or not status.strip():
        raise ProviderError(
            f"Provider '{provider_name}' task {task_id} response field "
            "'status' must be a non-empty string."
        )
    return status.strip().upper()


def _task_status_outputs(
    payload: dict[str, object],
    *,
    provider_name: str,
    task_id: str,
) -> tuple[str, ...]:
    outputs_payload = payload.get("output", [])
    if outputs_payload is None:
        return ()
    if not isinstance(outputs_payload, list):
        raise ProviderError(
            f"Provider '{provider_name}' task {task_id} response field "
            "'output' must be a list when present."
        )
    return _validated_task_output_items(
        outputs_payload,
        provider_name=provider_name,
        task_id=task_id,
    )


def _validated_task_output_items(
    outputs_payload: list[object],
    *,
    provider_name: str,
    task_id: str,
) -> tuple[str, ...]:
    outputs: list[str] = []
    invalid_indexes: list[int] = []
    for index, item in enumerate(outputs_payload):
        if isinstance(item, str) and item.strip():
            outputs.append(item.strip())
        else:
            invalid_indexes.append(index)
    if invalid_indexes:
        joined = ", ".join(str(index) for index in invalid_indexes)
        raise ProviderError(
            f"Provider '{provider_name}' task {task_id} response field "
            f"'output' contains invalid entries at index(es): {joined}."
        )
    return tuple(outputs)
