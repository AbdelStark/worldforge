"""Public model compatibility facade for WorldForge.

The concrete model implementations live in narrower leaf modules:

- :mod:`worldforge.scene_models` owns geometry, actions, scene objects, and local world-history
  entries.
- :mod:`worldforge.structured_goals` owns structured planning-goal parsing and serialization.
- :mod:`worldforge.capability_results` owns capability return payloads such as embedding,
  score, and policy results.
- :mod:`worldforge._model_utils` owns public framework errors and shared JSON/native validators.
- :mod:`worldforge.provider_models` owns provider-facing profile, lifecycle, event, and request
  policy contracts.

All names remain re-exported from this module for source compatibility with existing adapter,
CLI, docs, and test code that imports from ``worldforge.models``.
"""

from __future__ import annotations

from worldforge._model_utils import (  # noqa: F401
    JSONDict,
    WorldForgeError,
    WorldStateError,
    average,
    deterministic_floats,
    dump_json,
    ensure_directory,
    generate_id,
    require_bool,
    require_finite_number,
    require_json_dict,
    require_non_empty_text,
    require_non_negative_int,
    require_positive_int,
    require_probability,
)
from worldforge.capability_results import (  # noqa: F401
    ActionPolicyResult,
    ActionScoreResult,
    EmbeddingResult,
    _validate_score_best_index_direction,
    _validated_action_scores,
    _validated_score_best_index,
    _validated_score_direction,
    _validated_score_metadata,
    _validated_score_provider,
)
from worldforge.provider_diagnostics import (  # noqa: F401
    PROVIDER_LIFECYCLE_HOOKS,
    PROVIDER_LIFECYCLE_STATUSES,
    DoctorReport,
    ProviderDoctorStatus,
    ProviderHealth,
    ProviderLifecycleResult,
    ProviderLifecycleStatus,
)
from worldforge.provider_events import ProviderEvent  # noqa: F401
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
)
from worldforge.scene_models import (  # noqa: F401
    Action,
    BBox,
    HistoryEntry,
    Pose,
    Position,
    Rotation,
    SceneObject,
    SceneObjectPatch,
)
from worldforge.structured_goals import StructuredGoal  # noqa: F401
