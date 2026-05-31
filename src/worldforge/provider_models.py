"""Public compatibility facade for provider-facing model contracts.

The concrete provider contracts live in focused leaf modules:

- :mod:`worldforge.provider_profiles` owns capability and profile metadata.
- :mod:`worldforge.provider_request_policy` owns timeout and retry policy models.
- :mod:`worldforge.provider_events` owns structured provider-event validation.
- :mod:`worldforge.provider_diagnostics` owns health, lifecycle, and doctor reports.
- :mod:`worldforge.provider_redaction` owns shared log/artifact redaction helpers.

Names remain re-exported here for source compatibility with code that imports from
``worldforge.provider_models`` or from the higher-level ``worldforge.models`` facade.
"""

from __future__ import annotations

from worldforge.provider_diagnostics import (  # noqa: F401
    PROVIDER_LIFECYCLE_HOOKS,
    PROVIDER_LIFECYCLE_STATUSES,
    DoctorReport,
    ProviderDoctorStatus,
    ProviderHealth,
    ProviderLifecycleResult,
    ProviderLifecycleStatus,
    _provider_lifecycle_status_evidence,
    _provider_lifecycle_status_provider,
    _provider_lifecycle_status_status,
    _provider_lifecycle_status_text,
    _require_optional_provider_lifecycle_hook,
    _require_provider_lifecycle_hook,
    _validate_provider_lifecycle_result,
    _validate_provider_lifecycle_results,
)
from worldforge.provider_events import (  # noqa: F401
    ProviderEvent,
    _normalize_provider_event_duration,
    _normalize_provider_event_message,
    _normalize_provider_event_metadata,
    _normalize_provider_event_method,
    _normalize_provider_event_status_code,
    _require_provider_event_attempts,
    _require_provider_event_name,
)
from worldforge.provider_profiles import (  # noqa: F401
    CAPABILITY_NAMES,
    ProviderCapabilities,
    ProviderInfo,
    ProviderProfile,
)
from worldforge.provider_redaction import (  # noqa: F401
    _redact_observable_text,
    _redact_observable_value,
    _sanitize_observable_id,
    _sanitize_observable_target,
)
from worldforge.provider_request_policy import (  # noqa: F401
    ProviderRequestPolicy,
    RequestOperationPolicy,
    RetryPolicy,
    _validate_retry_status_code,
    _validated_retry_backoff_multiplier,
    _validated_retry_backoff_seconds,
    _validated_retry_max_attempts,
    _validated_retry_status_codes,
)
