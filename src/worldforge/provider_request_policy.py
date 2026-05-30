"""Typed request timeout and retry policies for remote providers."""

from __future__ import annotations

from dataclasses import dataclass, field

from worldforge._model_utils import JSONDict, WorldForgeError, require_finite_number


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    """Retry and backoff policy for one class of remote operations."""

    max_attempts: int = 1
    backoff_seconds: float = 0.0
    backoff_multiplier: float = 1.0
    retryable_status_codes: tuple[int, ...] = (408, 429, 500, 502, 503, 504)

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_attempts", _validated_retry_max_attempts(self.max_attempts))
        object.__setattr__(
            self,
            "backoff_seconds",
            _validated_retry_backoff_seconds(self.backoff_seconds),
        )
        object.__setattr__(
            self,
            "backoff_multiplier",
            _validated_retry_backoff_multiplier(self.backoff_multiplier),
        )
        object.__setattr__(
            self,
            "retryable_status_codes",
            _validated_retry_status_codes(self.retryable_status_codes),
        )

    def delay_for_attempt(self, attempt_number: int) -> float:
        """Return the sleep delay before the given attempt number."""

        if attempt_number <= 1 or self.backoff_seconds == 0.0:
            return 0.0
        return self.backoff_seconds * (self.backoff_multiplier ** (attempt_number - 2))

    def to_dict(self) -> JSONDict:
        return {
            "max_attempts": self.max_attempts,
            "backoff_seconds": self.backoff_seconds,
            "backoff_multiplier": self.backoff_multiplier,
            "retryable_status_codes": list(self.retryable_status_codes),
        }


def _validated_retry_max_attempts(max_attempts: object) -> int:
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise WorldForgeError("RetryPolicy max_attempts must be greater than or equal to 1.")
    return max_attempts


def _validated_retry_backoff_seconds(backoff_seconds: object) -> float:
    normalized = require_finite_number(backoff_seconds, name="RetryPolicy backoff_seconds")
    if normalized < 0.0:
        raise WorldForgeError("RetryPolicy backoff_seconds must be non-negative.")
    return normalized


def _validated_retry_backoff_multiplier(backoff_multiplier: object) -> float:
    normalized = require_finite_number(backoff_multiplier, name="RetryPolicy backoff_multiplier")
    if normalized < 1.0:
        raise WorldForgeError("RetryPolicy backoff_multiplier must be greater than or equal to 1.")
    return normalized


def _validated_retry_status_codes(retryable_status_codes: object) -> tuple[int, ...]:
    try:
        status_codes = tuple(retryable_status_codes)  # type: ignore[arg-type]
    except TypeError as exc:
        raise WorldForgeError(
            "RetryPolicy retryable_status_codes must contain valid HTTP status codes."
        ) from exc
    for status_code in status_codes:
        _validate_retry_status_code(status_code)
    return status_codes


def _validate_retry_status_code(status_code: object) -> None:
    if (
        isinstance(status_code, bool)
        or not isinstance(status_code, int)
        or status_code < 100
        or status_code > 599
    ):
        raise WorldForgeError(
            "RetryPolicy retryable_status_codes must contain valid HTTP status codes."
        )


@dataclass(slots=True, frozen=True)
class RequestOperationPolicy:
    """Timeout and retry policy for a single remote operation type."""

    timeout_seconds: float
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    max_elapsed_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            require_finite_number(
                self.timeout_seconds,
                name="RequestOperationPolicy timeout_seconds",
            ),
        )
        if self.timeout_seconds <= 0.0:
            raise WorldForgeError("RequestOperationPolicy timeout_seconds must be greater than 0.")
        if self.max_elapsed_seconds is not None:
            object.__setattr__(
                self,
                "max_elapsed_seconds",
                require_finite_number(
                    self.max_elapsed_seconds,
                    name="RequestOperationPolicy max_elapsed_seconds",
                ),
            )
            if self.max_elapsed_seconds <= 0.0:
                raise WorldForgeError(
                    "RequestOperationPolicy max_elapsed_seconds must be greater than 0."
                )

    def to_dict(self) -> JSONDict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "retry": self.retry.to_dict(),
            "max_elapsed_seconds": self.max_elapsed_seconds,
        }


@dataclass(slots=True, frozen=True)
class ProviderRequestPolicy:
    """Typed network policy for HTTP-backed provider operations."""

    health: RequestOperationPolicy
    request: RequestOperationPolicy
    polling: RequestOperationPolicy
    download: RequestOperationPolicy

    @classmethod
    def remote_defaults(
        cls,
        *,
        request_timeout_seconds: float,
        health_timeout_seconds: float | None = None,
        polling_timeout_seconds: float | None = None,
        download_timeout_seconds: float | None = None,
        health_max_elapsed_seconds: float | None = None,
        request_max_elapsed_seconds: float | None = None,
        polling_max_elapsed_seconds: float | None = None,
        download_max_elapsed_seconds: float | None = None,
        read_retry_attempts: int = 3,
        read_backoff_seconds: float = 0.25,
        read_backoff_multiplier: float = 2.0,
    ) -> ProviderRequestPolicy:
        read_retry = RetryPolicy(
            max_attempts=read_retry_attempts,
            backoff_seconds=read_backoff_seconds,
            backoff_multiplier=read_backoff_multiplier,
        )
        no_retry = RetryPolicy(max_attempts=1)
        resolved_request_timeout = require_finite_number(
            request_timeout_seconds,
            name="ProviderRequestPolicy request_timeout_seconds",
        )
        resolved_health_timeout = require_finite_number(
            health_timeout_seconds
            if health_timeout_seconds is not None
            else min(resolved_request_timeout, 10.0),
            name="ProviderRequestPolicy health_timeout_seconds",
        )
        resolved_polling_timeout = require_finite_number(
            polling_timeout_seconds
            if polling_timeout_seconds is not None
            else min(resolved_request_timeout, 30.0),
            name="ProviderRequestPolicy polling_timeout_seconds",
        )
        resolved_download_timeout = require_finite_number(
            download_timeout_seconds
            if download_timeout_seconds is not None
            else resolved_request_timeout,
            name="ProviderRequestPolicy download_timeout_seconds",
        )
        return cls(
            health=RequestOperationPolicy(
                timeout_seconds=resolved_health_timeout,
                retry=read_retry,
                max_elapsed_seconds=health_max_elapsed_seconds,
            ),
            request=RequestOperationPolicy(
                timeout_seconds=resolved_request_timeout,
                retry=no_retry,
                max_elapsed_seconds=request_max_elapsed_seconds,
            ),
            polling=RequestOperationPolicy(
                timeout_seconds=resolved_polling_timeout,
                retry=read_retry,
                max_elapsed_seconds=polling_max_elapsed_seconds,
            ),
            download=RequestOperationPolicy(
                timeout_seconds=resolved_download_timeout,
                retry=read_retry,
                max_elapsed_seconds=download_max_elapsed_seconds,
            ),
        )

    def to_dict(self) -> JSONDict:
        return {
            "health": self.health.to_dict(),
            "request": self.request.to_dict(),
            "polling": self.polling.to_dict(),
            "download": self.download.to_dict(),
        }
