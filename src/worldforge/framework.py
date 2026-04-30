"""Framework runtime objects for WorldForge.

This module owns the in-process orchestration boundary: provider registration, world state,
planning, local JSON persistence, and diagnostics. It deliberately does not own deployment,
multi-writer storage, optional model runtimes, robot controllers, or production telemetry export.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from worldforge.capabilities import (
    CAPABILITY_FIELD_NAMES,
    CAPABILITY_FIELD_TO_NAME,
    CAPABILITY_PROTOCOLS,
    Cost,
    Embedder,
    Generator,
    Planner,
    Policy,
    Predictor,
    Reasoner,
    RunnableModel,
    Transferer,
)
from worldforge.models import (
    CAPABILITY_NAMES,
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    BBox,
    DoctorReport,
    EmbeddingResult,
    GenerationOptions,
    HistoryEntry,
    JSONDict,
    Position,
    ProviderCapabilities,
    ProviderDoctorStatus,
    ProviderEvent,
    ProviderHealth,
    ProviderInfo,
    ProviderProfile,
    ReasoningResult,
    SceneObject,
    SceneObjectPatch,
    StructuredGoal,
    VideoClip,
    WorldForgeError,
    WorldStateError,
    average,
    dump_json,
    ensure_directory,
    generate_id,
    require_finite_number,
    require_json_dict,
    require_non_negative_int,
    require_positive_int,
    require_probability,
)
from worldforge.providers import (
    BaseProvider,
    PredictionPayload,
    ProviderConfigSummary,
    ProviderError,
    validate_generation_request,
    validate_transfer_request,
)
from worldforge.providers.catalog import PROVIDER_CATALOG, create_known_providers
from worldforge.providers.observable import CAPABILITY_METHOD_MAP, _ObservableCapability

if TYPE_CHECKING:
    from worldforge.evaluation import EvaluationReport, EvaluationResult

SCHEMA_VERSION = 1
_STORAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _clone_state(state: JSONDict) -> JSONDict:
    return deepcopy(state)


def _normalize_provider_name(provider: str | None, fallback: str) -> str:
    return provider or fallback


def _dedupe_text(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _join_non_empty(values: Sequence[str], *, separator: str = " ") -> str:
    return separator.join(value for value in values if value)


def _require_non_empty_text(value: object, *, name: str, message: str | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(message or f"{name} must be a non-empty string.")
    return value.strip()


def _validate_storage_id(value: object, *, name: str) -> str:
    """Return a file-safe local storage identifier or raise ``WorldForgeError``.

    World IDs become local JSON file stems. Rejecting separators and traversal-shaped values here
    keeps every persistence read and write inside ``WorldForge.state_dir``.
    """

    identifier = _require_non_empty_text(value, name=name)
    if (
        identifier in {".", ".."}
        or "/" in identifier
        or "\\" in identifier
        or _STORAGE_ID_PATTERN.fullmatch(identifier) is None
    ):
        raise WorldForgeError(
            f"{name} must be a file-safe identifier using only letters, numbers, '.', '_', or '-'."
        )
    return identifier


def _is_sequence_of_actions(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


def _normalize_candidate_action_plans(
    candidate_actions: Sequence[Action | Sequence[Action]],
) -> list[list[Action]]:
    if not _is_sequence_of_actions(candidate_actions) or not candidate_actions:
        raise WorldForgeError("candidate_actions must be a non-empty sequence.")

    normalized: list[list[Action]] = []
    for index, candidate in enumerate(candidate_actions):
        if isinstance(candidate, Action):
            normalized.append([candidate])
            continue
        if not _is_sequence_of_actions(candidate) or not candidate:
            raise WorldForgeError(
                f"candidate_actions[{index}] must be an Action or non-empty sequence of Actions."
            )
        actions = list(candidate)
        if not all(isinstance(action, Action) for action in actions):
            raise WorldForgeError(f"candidate_actions[{index}] must contain only Action instances.")
        normalized.append(actions)
    return normalized


def _action_plans_to_score_payload(
    candidate_action_plans: Sequence[Sequence[Action]],
) -> list[list[JSONDict]]:
    return [[action.to_dict() for action in candidate] for candidate in candidate_action_plans]


def _require_score_count_matches_candidates(
    *,
    provider: str,
    score_result: ActionScoreResult,
    candidate_count: int,
) -> None:
    score_count = len(score_result.scores)
    if score_count != candidate_count:
        raise WorldForgeError(
            f"Provider '{provider}' returned {score_count} score(s) for "
            f"{candidate_count} candidate action plan(s)."
        )


def _world_file(state_dir: Path, world_id: str) -> Path:
    return state_dir / f"{_validate_storage_id(world_id, name='world_id')}.json"


def _offset_position(base: Position, offset: Position) -> Position:
    return Position(base.x + offset.x, base.y + offset.y, base.z + offset.z)


def _validate_world_state_payload(state: JSONDict, *, context: str) -> None:
    """Validate a serialized world before it is restored, saved, or applied.

    The validator is recursive because persisted history contains historical world snapshots. A
    malformed snapshot is still part of the state contract and must fail before it can be written
    back to disk or returned through public APIs.
    """

    if not isinstance(state, dict):
        raise WorldStateError(f"{context} must be a JSON object.")

    missing_keys = [key for key in ("schema_version", "id", "name", "provider") if key not in state]
    if missing_keys:
        joined = ", ".join(sorted(missing_keys))
        raise WorldStateError(f"{context} is missing required keys: {joined}.")
    try:
        schema_version = require_positive_int(
            state["schema_version"],
            name=f"{context} field 'schema_version'",
        )
        if schema_version != SCHEMA_VERSION:
            raise WorldForgeError(f"{context} field 'schema_version' must be {SCHEMA_VERSION}.")
        _validate_storage_id(state["id"], name=f"{context} field 'id'")
        _require_non_empty_text(state["name"], name=f"{context} field 'name'")
        _require_non_empty_text(state["provider"], name=f"{context} field 'provider'")
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc

    scene = state.get("scene", {})
    if not isinstance(scene, dict):
        raise WorldStateError(f"{context} field 'scene' must be a JSON object.")

    objects = scene.get("objects", {})
    if not isinstance(objects, dict):
        raise WorldStateError(f"{context} field 'scene.objects' must be a JSON object.")
    for object_id, object_state in objects.items():
        if not isinstance(object_id, str) or not object_id.strip():
            raise WorldStateError(f"{context} scene object ids must be non-empty strings.")
        if not isinstance(object_state, dict):
            raise WorldStateError(f"{context} scene object '{object_id}' must be a JSON object.")
        embedded_id = object_state.get("id")
        if embedded_id is not None and str(embedded_id) != str(object_id):
            raise WorldStateError(
                f"{context} scene object key '{object_id}' does not match embedded id "
                f"'{embedded_id}'."
            )
        object_payload = dict(object_state)
        object_payload.setdefault("id", object_id)
        try:
            SceneObject.from_dict(object_payload)
        except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
            raise WorldStateError(
                f"{context} scene object '{object_id}' is invalid: {exc}"
            ) from exc

    metadata = state.get("metadata", {})
    try:
        require_json_dict(metadata, name=f"{context} field 'metadata'")
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc

    history = state.get("history", [])
    if not isinstance(history, list):
        raise WorldStateError(f"{context} field 'history' must be a JSON array.")

    try:
        step = require_non_negative_int(state.get("step", 0), name=f"{context} field 'step'")
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc

    for index, entry in enumerate(history):
        if not isinstance(entry, dict):
            raise WorldStateError(f"{context} history[{index}] must be a JSON object.")
        try:
            history_entry = HistoryEntry.from_dict(entry)
        except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
            raise WorldStateError(f"{context} history[{index}] is invalid: {exc}") from exc
        if history_entry.step > step:
            raise WorldStateError(
                f"{context} history[{index}] step must not be greater than current step."
            )
        try:
            _validate_world_state_payload(
                history_entry.state,
                context=f"{context} history[{index}].state",
            )
        except WorldStateError as exc:
            raise WorldStateError(f"{context} history[{index}] has invalid state: {exc}") from exc


def _restore_scene_objects(state: JSONDict, *, context: str) -> dict[str, SceneObject]:
    objects = state.get("scene", {}).get("objects", {})
    restored: dict[str, SceneObject] = {}
    for object_id, object_state in objects.items():
        object_payload = dict(object_state)
        object_payload.setdefault("id", str(object_id))
        try:
            restored[str(object_id)] = SceneObject.from_dict(object_payload)
        except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
            raise WorldStateError(
                f"{context} scene object '{object_id}' could not be restored: {exc}"
            ) from exc
    return restored


def _restore_history_entries(
    state: JSONDict,
    *,
    context: str,
    fallback: HistoryEntry,
) -> list[HistoryEntry]:
    entries = state.get("history", [])
    restored: list[HistoryEntry] = []
    for index, entry in enumerate(entries):
        try:
            restored.append(HistoryEntry.from_dict(entry))
        except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
            raise WorldStateError(
                f"{context} history[{index}] could not be restored: {exc}"
            ) from exc
    return restored or [fallback]


@dataclass(slots=True)
class Prediction:
    """Result of a world prediction."""

    provider: str
    confidence: float
    physics_score: float
    frames: list[bytes]
    world_state: JSONDict
    metadata: JSONDict
    latency_ms: float
    _forge: WorldForge

    def __post_init__(self) -> None:
        self.provider = _require_non_empty_text(self.provider, name="Prediction provider")
        self.confidence = require_probability(self.confidence, name="Prediction confidence")
        self.physics_score = require_probability(
            self.physics_score,
            name="Prediction physics_score",
        )
        if not isinstance(self.frames, list) or not all(
            isinstance(frame, bytes) for frame in self.frames
        ):
            raise WorldForgeError("Prediction frames must be a list of bytes.")
        if not isinstance(self.metadata, dict):
            raise WorldForgeError("Prediction metadata must be a JSON object.")
        if not isinstance(self.world_state, dict):
            raise WorldForgeError("Prediction world_state must be a JSON object.")
        _validate_world_state_payload(self.world_state, context="Prediction world_state")
        self.latency_ms = require_finite_number(self.latency_ms, name="Prediction latency_ms")
        if self.latency_ms < 0.0:
            raise WorldForgeError("Prediction latency_ms must be non-negative.")
        dump_json(self.metadata)
        dump_json(self.world_state)
        self.frames = list(self.frames)
        self.metadata = dict(self.metadata)
        self.world_state = _clone_state(self.world_state)

    def output_world(self) -> World:
        """Return a fresh :class:`World` hydrated from this prediction's snapshot.

        The new world is detached from the source: mutations on it do not affect the original.
        Raises :class:`WorldStateError` if ``world_state`` cannot be parsed as a valid snapshot.
        """

        return World.from_state(self._forge, _clone_state(self.world_state))


class Comparison:
    """Result of comparing predictions from multiple providers for the same input.

    Use :meth:`best_prediction` to pick the highest-scoring result, or render the comparison via
    :meth:`to_markdown`, :meth:`to_csv`, :meth:`to_json`, and :meth:`artifacts` for reports.
    """

    def __init__(self, predictions: Sequence[Prediction]) -> None:
        self.results = list(predictions)

    @property
    def prediction_count(self) -> int:
        """Number of provider predictions captured in this comparison."""

        return len(self.results)

    def best_prediction(self) -> Prediction:
        """Return the prediction with the highest ``(physics_score, confidence)`` tuple.

        Raises ``ValueError`` if the comparison has no predictions.
        """

        if not self.results:
            raise ValueError("Comparison has no predictions.")
        return max(self.results, key=lambda item: (item.physics_score, item.confidence))

    def to_markdown(self) -> str:
        """Render the comparison as a Markdown table sorted in result order."""

        lines = [
            "# WorldForge Comparison",
            "",
            "| provider | physics_score | confidence | latency_ms |",
            "| --- | ---: | ---: | ---: |",
        ]
        lines.extend(
            (
                f"| {result.provider} | {result.physics_score:.2f} | "
                f"{result.confidence:.2f} | {result.latency_ms:.2f} |"
            )
            for result in self.results
        )
        return "\n".join(lines)

    def to_csv(self) -> str:
        """Render the comparison as CSV with a single header row."""

        rows = ["provider,physics_score,confidence,latency_ms"]
        rows.extend(
            (
                f"{result.provider},{result.physics_score:.4f},"
                f"{result.confidence:.4f},{result.latency_ms:.4f}"
            )
            for result in self.results
        )
        return "\n".join(rows)

    def to_json(self) -> str:
        """Render the comparison as a JSON document with one entry per prediction."""

        return dump_json(
            {
                "predictions": [
                    {
                        "provider": result.provider,
                        "physics_score": result.physics_score,
                        "confidence": result.confidence,
                        "latency_ms": result.latency_ms,
                        "metadata": result.metadata,
                    }
                    for result in self.results
                ]
            }
        )

    def artifacts(self) -> dict[str, str]:
        """Return all renderings keyed by format name (``json``, ``markdown``, ``csv``)."""

        return {
            "json": self.to_json(),
            "markdown": self.to_markdown(),
            "csv": self.to_csv(),
        }


class Plan:
    """Deterministic multi-step execution plan."""

    def __init__(
        self,
        *,
        goal: str,
        planner: str,
        provider: str,
        actions: Sequence[Action],
        predicted_states: Sequence[JSONDict],
        success_probability: float,
        goal_spec: JSONDict | None = None,
        metadata: JSONDict | None = None,
    ) -> None:
        self.goal = _require_non_empty_text(goal, name="Plan goal")
        self.planner = _require_non_empty_text(planner, name="Plan planner")
        self.provider = _require_non_empty_text(provider, name="Plan provider")
        if not _is_sequence_of_actions(actions) or not all(
            isinstance(action, Action) for action in actions
        ):
            raise WorldForgeError("Plan actions must be a sequence of Action instances.")
        self.actions = list(actions)
        if not isinstance(predicted_states, Sequence) or isinstance(
            predicted_states,
            str | bytes,
        ):
            raise WorldForgeError("Plan predicted_states must be a sequence of JSON objects.")
        self.predicted_states = [_clone_state(state) for state in predicted_states]
        for index, state in enumerate(self.predicted_states):
            if not isinstance(state, dict):
                raise WorldForgeError(f"Plan predicted_states[{index}] must be a JSON object.")
            _validate_world_state_payload(state, context=f"Plan predicted_states[{index}]")
        self.success_probability = require_probability(
            success_probability,
            name="Plan success_probability",
        )
        if goal_spec is not None and not isinstance(goal_spec, dict):
            raise WorldForgeError("Plan goal_spec must be a JSON object when provided.")
        self.goal_spec = _clone_state(goal_spec) if goal_spec is not None else None
        if metadata is not None and not isinstance(metadata, dict):
            raise WorldForgeError("Plan metadata must be a JSON object when provided.")
        self.metadata = _clone_state(metadata or {})
        dump_json(self.to_dict())

    @property
    def action_count(self) -> int:
        return len(self.actions)

    def to_dict(self) -> JSONDict:
        return {
            "goal": self.goal,
            "goal_spec": self.goal_spec,
            "planner": self.planner,
            "provider": self.provider,
            "actions": [action.to_dict() for action in self.actions],
            "action_count": self.action_count,
            "success_probability": self.success_probability,
            "predicted_states": self.predicted_states,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return dump_json(self.to_dict())


class PlanExecution:
    """Result of applying a :class:`Plan` against a :class:`World`.

    ``actions_applied`` is the subset of plan actions that were materialised onto the world (the
    full action list when execution succeeds end to end). Use :meth:`final_world` to get the
    post-execution world snapshot.
    """

    def __init__(self, final_world: World, actions_applied: Sequence[Action]) -> None:
        self._final_world = final_world
        self.actions_applied = list(actions_applied)

    def final_world(self) -> World:
        """Return the world after the plan's actions were applied."""

        return self._final_world


class World:
    """Mutable world state bound to a provider registry."""

    def __init__(
        self,
        name: str,
        provider: str = "mock",
        *,
        forge: WorldForge | None = None,
        description: str = "",
        world_id: str | None = None,
        metadata: JSONDict | None = None,
        max_history: int | None = None,
    ) -> None:
        self._forge = forge or WorldForge()
        self.id = _validate_storage_id(world_id or generate_id("world"), name="world_id")
        self.name = _require_non_empty_text(
            name,
            name="World name",
            message="World name must not be empty.",
        )
        self.provider = _require_non_empty_text(provider, name="World provider")
        self.description = description
        self.step = 0
        self.metadata = require_json_dict(metadata or {}, name="World metadata")
        self.metadata.setdefault("name", self.name)
        self.max_history = (
            require_positive_int(max_history, name="World max_history")
            if max_history is not None
            else None
        )
        self.scene_objects: dict[str, SceneObject] = {}
        self._history: list[HistoryEntry] = []
        self._record_history(summary="world initialized", action=None)

    @classmethod
    def from_state(cls, forge: WorldForge, state: JSONDict) -> World:
        _validate_world_state_payload(state, context="World state")
        try:
            world = cls(
                name=str(state["name"]),
                provider=str(state["provider"]),
                forge=forge,
                description=str(state.get("description", "")),
                world_id=str(state["id"]),
                metadata=dict(state.get("metadata", {})),
            )
            world.step = int(state.get("step", 0))
            world.scene_objects = _restore_scene_objects(state, context="World state")
            world._history = _restore_history_entries(
                state,
                context="World state",
                fallback=HistoryEntry(
                    step=world.step,
                    state=world._snapshot(),
                    summary="world restored",
                    action_json=None,
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WorldStateError(f"World state could not be restored: {exc}") from exc
        return world

    @property
    def object_count(self) -> int:
        return len(self.scene_objects)

    @property
    def history_length(self) -> int:
        return len(self._history)

    def _snapshot(self) -> JSONDict:
        return self._snapshot_with()

    def _snapshot_with(
        self,
        *,
        scene_objects: dict[str, SceneObject] | None = None,
        metadata: JSONDict | None = None,
    ) -> JSONDict:
        selected_scene_objects = self.scene_objects if scene_objects is None else scene_objects
        selected_metadata = self.metadata if metadata is None else metadata
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "description": self.description,
            "step": self.step,
            "scene": {
                "objects": {
                    object_id: obj.to_dict() for object_id, obj in selected_scene_objects.items()
                }
            },
            "metadata": dict(selected_metadata),
        }

    def _apply_state(self, state: JSONDict, *, preserve_history: bool = False) -> None:
        _validate_world_state_payload(state, context="World state")
        try:
            self.id = str(state["id"])
            self.name = str(state["name"])
            self.provider = str(state["provider"])
            self.description = str(state.get("description", ""))
            self.step = int(state.get("step", 0))
            self.metadata = dict(state.get("metadata", {}))
            self.scene_objects = _restore_scene_objects(state, context="World state")
            if not preserve_history:
                self._history = _restore_history_entries(
                    state,
                    context="World state",
                    fallback=HistoryEntry(
                        step=self.step,
                        state=self._snapshot(),
                        summary="world restored",
                        action_json=None,
                    ),
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise WorldStateError(f"World state could not be applied: {exc}") from exc

    def _make_history_entry(
        self,
        *,
        summary: str,
        action: Action | None,
        state: JSONDict | None = None,
    ) -> HistoryEntry:
        entry = HistoryEntry(
            step=self.step,
            state=_clone_state(state if state is not None else self._snapshot()),
            summary=summary,
            action_json=action.to_json() if action else None,
        )
        dump_json(entry.to_dict())
        return entry

    def _append_history_entry(self, entry: HistoryEntry) -> None:
        self._history.append(entry)
        # Trim the oldest entries first when a bound is set; this is a ring buffer
        # on write, so `history_state(0)` after a trim refers to the oldest kept entry.
        if self.max_history is not None:
            overflow = len(self._history) - self.max_history
            if overflow > 0:
                del self._history[:overflow]

    def _record_history(self, *, summary: str, action: Action | None) -> None:
        self._append_history_entry(self._make_history_entry(summary=summary, action=action))

    @staticmethod
    def _object_patch_payload(patch: SceneObjectPatch) -> JSONDict:
        changes: JSONDict = {}
        if patch.name is not None:
            changes["name"] = patch.name
        if patch.position is not None:
            changes["position"] = patch.position.to_dict()
        if patch.graspable is not None:
            changes["is_graspable"] = patch.graspable
        return changes

    def to_dict(self) -> JSONDict:
        state = self._snapshot()
        state["history"] = [entry.to_dict() for entry in self._history]
        return state

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def add_object(self, obj: SceneObject) -> SceneObject:
        """Insert ``obj`` into the world and append a history entry.

        Returns a defensive copy of the inserted object. Raises :class:`WorldForgeError` if an
        object with the same ``id`` is already present.
        """

        if obj.id in self.scene_objects:
            raise WorldForgeError(f"Object id '{obj.id}' is already present in world '{self.id}'.")
        added = obj.copy()
        staged_scene_objects = {**self.scene_objects, added.id: added}
        staged_metadata = {**self.metadata, "name": self.name}
        action = Action("add_object", {"object": added.to_dict()})
        history_entry = self._make_history_entry(
            summary=f"added object {added.id}",
            action=action,
            state=self._snapshot_with(
                scene_objects=staged_scene_objects,
                metadata=staged_metadata,
            ),
        )
        self.scene_objects = staged_scene_objects
        self.metadata = staged_metadata
        self._append_history_entry(history_entry)
        return added

    def list_objects(self) -> list[str]:
        """Return the human-readable ``name`` of every scene object in insertion order."""

        return [obj.name for obj in self.scene_objects.values()]

    def objects(self) -> list[SceneObject]:
        """Return defensive copies of every scene object in insertion order.

        Mutating an entry in the returned list does not affect the world.
        """

        return [obj.copy() for obj in self.scene_objects.values()]

    def get_object_by_id(self, object_id: str) -> SceneObject | None:
        """Return a copy of the scene object with ``object_id``, or ``None`` if absent."""

        scene_object = self.scene_objects.get(object_id)
        return scene_object.copy() if scene_object else None

    def update_object_patch(self, object_id: str, patch: SceneObjectPatch) -> SceneObject:
        if not isinstance(patch, SceneObjectPatch):
            raise WorldForgeError("update_object_patch() patch must be a SceneObjectPatch.")
        try:
            scene_object = self.scene_objects[object_id]
        except KeyError as exc:
            raise WorldForgeError(
                f"Object '{object_id}' is not present in world '{self.id}'."
            ) from exc
        before = scene_object.copy()
        changes = self._object_patch_payload(patch)
        if not changes:
            return before
        staged_object = before.copy()
        staged_object.apply_patch(patch)
        updated = staged_object.copy()
        staged_scene_objects = {**self.scene_objects, object_id: updated}
        action = Action(
            "update_object",
            {
                "object_id": updated.id,
                "changes": changes,
                "before": before.to_dict(),
                "after": updated.to_dict(),
            },
        )
        history_entry = self._make_history_entry(
            summary=f"updated object {updated.id}",
            action=action,
            state=self._snapshot_with(scene_objects=staged_scene_objects),
        )
        self.scene_objects = staged_scene_objects
        self._append_history_entry(history_entry)
        return updated

    def remove_object_by_id(self, object_id: str) -> SceneObject | None:
        removed = self.scene_objects.get(object_id)
        if removed is None:
            return None
        removed_copy = removed.copy()
        staged_scene_objects = {
            existing_id: scene_object
            for existing_id, scene_object in self.scene_objects.items()
            if existing_id != object_id
        }
        staged_metadata = {**self.metadata, "name": self.name}
        action = Action(
            "remove_object",
            {
                "object_id": removed_copy.id,
                "object": removed_copy.to_dict(),
            },
        )
        history_entry = self._make_history_entry(
            summary=f"removed object {removed_copy.id}",
            action=action,
            state=self._snapshot_with(
                scene_objects=staged_scene_objects,
                metadata=staged_metadata,
            ),
        )
        self.scene_objects = staged_scene_objects
        self.metadata = staged_metadata
        self._append_history_entry(history_entry)
        return removed_copy

    def history(self) -> list[HistoryEntry]:
        return [HistoryEntry.from_dict(entry.to_dict()) for entry in self._history]

    def history_state(self, index: int) -> World:
        if index < 0 or index >= len(self._history):
            raise WorldForgeError(f"History index {index} is out of range for world '{self.id}'.")
        entry = self._history[index]
        state = _clone_state(entry.state)
        state["history"] = [item.to_dict() for item in self._history[: index + 1]]
        return World.from_state(self._forge, state)

    def restore_history(self, index: int) -> None:
        restored = self.history_state(index)
        self._apply_state(restored.to_dict())

    def _provider(self, provider_name: str | None = None) -> BaseProvider:
        return self._forge._require_provider(_normalize_provider_name(provider_name, self.provider))

    def predict(self, action: Action, steps: int = 1, provider: str | None = None) -> Prediction:
        require_positive_int(steps, name="steps")
        if not isinstance(action, Action):
            raise WorldForgeError("predict() action must be an Action.")
        action.to_json()
        selected_provider = _normalize_provider_name(provider, self.provider)
        payload = self._forge.predict(
            self._snapshot(),
            action,
            steps=steps,
            provider=selected_provider,
        )
        next_state = _clone_state(payload.state)
        dump_json(next_state)
        self._apply_state(next_state, preserve_history=True)
        self.provider = selected_provider
        self.metadata["name"] = self.name
        self._record_history(summary=f"predicted via {selected_provider}", action=action)
        return Prediction(
            provider=selected_provider,
            confidence=payload.confidence,
            physics_score=payload.physics_score,
            frames=list(payload.frames),
            world_state=self._snapshot(),
            metadata=dict(payload.metadata),
            latency_ms=payload.latency_ms,
            _forge=self._forge,
        )

    def compare(self, action: Action, providers: str | Sequence[str], steps: int = 1) -> Comparison:
        """Predict the same ``(action, steps)`` against several providers and collect results.

        ``providers`` may be a single provider name or a sequence of names. Predictions for
        multiple providers are dispatched concurrently; each receives an independent snapshot
        copy of the world state. Returns a :class:`Comparison` whose
        :meth:`Comparison.best_prediction` selects the highest-scoring provider.

        Raises :class:`WorldForgeError` if ``providers`` is empty or ``steps`` is non-positive.
        """

        require_positive_int(steps, name="steps")
        if isinstance(providers, str):
            providers = [providers]
        if not providers:
            raise WorldForgeError("compare() requires at least one provider.")
        state = self._snapshot()
        ordered = list(providers)

        def _predict_one(provider_name: str) -> Prediction:
            # Each thread gets its own copy of the immutable-by-convention state
            # dict so nothing aliases if a provider accidentally mutates input.
            payload = self._forge.predict(
                _clone_state(state),
                action,
                steps=steps,
                provider=provider_name,
            )
            return Prediction(
                provider=provider_name,
                confidence=payload.confidence,
                physics_score=payload.physics_score,
                frames=list(payload.frames),
                world_state=_clone_state(payload.state),
                metadata=dict(payload.metadata),
                latency_ms=payload.latency_ms,
                _forge=self._forge,
            )

        if len(ordered) == 1:
            return Comparison([_predict_one(ordered[0])])
        with ThreadPoolExecutor(max_workers=min(8, len(ordered))) as pool:
            predictions = list(pool.map(_predict_one, ordered))
        return Comparison(predictions)

    def _resolve_goal_object(
        self,
        *,
        object_id: str | None,
        object_name: str | None,
        label: str,
    ) -> SceneObject:
        if object_id:
            scene_object = self.scene_objects.get(object_id)
            if scene_object is None:
                raise WorldForgeError(
                    f"Structured goal references missing {label} id '{object_id}'."
                )
            if object_name and scene_object.name != object_name:
                raise WorldForgeError(
                    f"Structured goal {label} id/name selectors do not match the same object."
                )
            return scene_object.copy()

        matches = [
            scene_object.copy()
            for scene_object in self.scene_objects.values()
            if scene_object.name == object_name
        ]
        if not matches:
            raise WorldForgeError(
                f"Structured goal references unknown {label} name '{object_name}'."
            )
        if len(matches) > 1:
            raise WorldForgeError(
                f"Structured goal {label} name '{object_name}' is ambiguous; use object_id instead."
            )
        return matches[0]

    def _actions_for_goal_spec(self, goal_spec: StructuredGoal) -> list[Action]:
        if goal_spec.kind == "spawn_object":
            return [
                Action.spawn_object(
                    goal_spec.object_name or "cube",
                    position=goal_spec.position,
                )
            ]

        target_object = self._resolve_goal_object(
            object_id=goal_spec.object_id,
            object_name=goal_spec.object_name,
            label="object",
        )
        if goal_spec.kind == "object_near":
            reference_object = self._resolve_goal_object(
                object_id=goal_spec.reference_object_id,
                object_name=goal_spec.reference_object_name,
                label="reference object",
            )
            if reference_object.id == target_object.id:
                raise WorldForgeError(
                    "Structured goal object_near requires distinct primary and reference objects."
                )
            offset = goal_spec.offset
            if offset is None:
                raise WorldForgeError("Structured goal object_near must carry a non-null offset.")
            target_position = _offset_position(reference_object.position, offset)
            return [
                Action.move_to(
                    target_position.x,
                    target_position.y,
                    target_position.z,
                    object_id=target_object.id,
                )
            ]

        if goal_spec.kind == "swap_objects":
            reference_object = self._resolve_goal_object(
                object_id=goal_spec.reference_object_id,
                object_name=goal_spec.reference_object_name,
                label="reference object",
            )
            if reference_object.id == target_object.id:
                raise WorldForgeError(
                    "Structured goal swap_objects requires distinct primary and reference objects."
                )
            return [
                Action.move_to(
                    reference_object.position.x,
                    reference_object.position.y,
                    reference_object.position.z,
                    object_id=target_object.id,
                ),
                Action.move_to(
                    target_object.position.x,
                    target_object.position.y,
                    target_object.position.z,
                    object_id=reference_object.id,
                ),
            ]

        position = goal_spec.position
        if position is None:
            raise WorldForgeError(
                f"Structured goal {goal_spec.kind!r} must carry a non-null position."
            )
        return [
            Action.move_to(
                position.x,
                position.y,
                position.z,
                object_id=target_object.id,
            )
        ]

    def _goal_actions(self, goal: str, goal_json: str | None = None) -> list[Action]:
        if goal_json:
            return self._actions_for_goal_spec(StructuredGoal.from_json(goal_json))

        lowered = goal.lower()
        if "spawn" in lowered:
            object_name = "cube"
            for candidate in ("cube", "ball", "block", "mug"):
                if candidate in lowered:
                    object_name = candidate
                    break
            return [Action.spawn_object(object_name)]

        if self.scene_objects:
            primary = next(iter(self.scene_objects.values()))
            target = primary.position
            if "right" in lowered:
                return [Action.move_to(target.x + 1.0, target.y, target.z)]
            if "dishwasher" in lowered:
                return [Action.move_to(target.x + 0.8, target.y, target.z - 0.4)]
            return [Action.move_to(target.x + 0.3, target.y, target.z)]

        return [Action.spawn_object("cube")]

    def plan(
        self,
        goal: str | None = None,
        *,
        goal_spec: StructuredGoal | None = None,
        goal_json: str | None = None,
        planner: str = "cem",
        max_steps: int = 20,
        provider: str | None = None,
        candidate_actions: Sequence[Action | Sequence[Action]] | None = None,
        policy_provider: str | None = None,
        policy_info: JSONDict | None = None,
        score_provider: str | None = None,
        score_info: JSONDict | None = None,
        score_action_candidates: object | None = None,
        execution_provider: str | None = None,
        **_: Any,
    ) -> Plan:
        """Plan actions through a predictive, score, policy, or policy-plus-score path.

        The selected path is determined by the capability-specific inputs:
        ``candidate_actions`` or score arguments choose score planning, ``policy_info`` chooses
        policy planning, and both together compose policy proposals with score-provider ranking.
        Without those inputs, the world uses a predictive provider and records predicted states.
        """

        require_positive_int(max_steps, name="max_steps")
        if goal is not None and not isinstance(goal, str):
            raise WorldForgeError("goal must be a string when provided.")
        if goal_json is not None and goal_spec is not None:
            raise WorldForgeError("plan() accepts at most one of goal_json or goal_spec.")
        if goal is not None and not goal.strip():
            raise WorldForgeError("goal must not be empty when provided.")
        selected_provider = _normalize_provider_name(provider, self.provider)
        uses_policy_planning = policy_info is not None or policy_provider is not None
        uses_score_planning = any(
            item is not None
            for item in (candidate_actions, score_provider, score_info, score_action_candidates)
        )
        selected_policy_provider = policy_provider or selected_provider
        if uses_policy_planning:
            if not self._forge.provider_profile(selected_policy_provider).capabilities.policy:
                raise WorldForgeError(
                    f"Provider '{selected_policy_provider}' does not support policy planning."
                )
            if policy_info is None:
                raise WorldForgeError("Policy planning requires policy_info.")
            if candidate_actions is not None:
                raise WorldForgeError(
                    "Policy planning derives candidate actions from the policy provider; do not "
                    "pass candidate_actions."
                )
        selected_score_provider = score_provider or selected_provider
        if uses_score_planning:
            if not self._forge.provider_profile(selected_score_provider).capabilities.score:
                raise WorldForgeError(
                    f"Provider '{selected_score_provider}' does not support score-based planning."
                )
            if not uses_policy_planning and candidate_actions is None:
                raise WorldForgeError(
                    "Score-based planning requires candidate_actions unless policy planning "
                    "provides candidates."
                )
            if score_info is None:
                raise WorldForgeError("Score-based planning requires score_info.")

        resolved_goal_spec = goal_spec
        if goal_json is not None:
            resolved_goal_spec = StructuredGoal.from_json(goal_json)

        if resolved_goal_spec is not None:
            resolved_goal = resolved_goal_spec.summary()
            serialized_goal_spec = resolved_goal_spec.to_dict()
            actions = self._actions_for_goal_spec(resolved_goal_spec)
        else:
            if goal is None:
                raise WorldForgeError("plan() requires goal, goal_json, or goal_spec.")
            resolved_goal = goal
            serialized_goal_spec = None
            actions = self._goal_actions(resolved_goal)
        actions = actions[: min(max_steps, len(actions))]

        if uses_policy_planning:
            if policy_info is None:
                raise WorldForgeError("Policy planning is active but policy_info is missing.")
            policy_result = self._forge.select_actions(selected_policy_provider, info=policy_info)
            candidate_action_plans = [
                candidate[:max_steps] for candidate in policy_result.action_candidates
            ]
            if not candidate_action_plans:
                raise WorldForgeError(
                    f"Provider '{selected_policy_provider}' returned no policy action candidates."
                )
            if uses_score_planning:
                if score_info is None:
                    raise WorldForgeError("Score planning is active but score_info is missing.")
                score_payload = (
                    score_action_candidates
                    if score_action_candidates is not None
                    else _action_plans_to_score_payload(candidate_action_plans)
                )
                score_result = self._forge.score_actions(
                    selected_score_provider,
                    info=score_info,
                    action_candidates=score_payload,
                )
                _require_score_count_matches_candidates(
                    provider=selected_score_provider,
                    score_result=score_result,
                    candidate_count=len(candidate_action_plans),
                )
                if score_result.best_index >= len(candidate_action_plans):
                    raise WorldForgeError(
                        f"Provider '{selected_score_provider}' selected candidate index "
                        f"{score_result.best_index}, but policy provider "
                        f"'{selected_policy_provider}' returned only "
                        f"{len(candidate_action_plans)} candidate action plan(s)."
                    )
                selected_actions = candidate_action_plans[score_result.best_index]
                best_score = max(0.0, score_result.best_score)
                success_probability = 1.0 / (1.0 + best_score)
                metadata = {
                    "planning_mode": "policy+score",
                    "policy_provider": selected_policy_provider,
                    "score_provider": selected_score_provider,
                    "policy_result": policy_result.to_dict(),
                    "score_result": score_result.to_dict(),
                    "candidate_count": len(candidate_action_plans),
                    "success_probability_source": "inverse_best_cost_heuristic",
                }
                if execution_provider is not None:
                    metadata["execution_provider"] = execution_provider
                return Plan(
                    goal=resolved_goal,
                    goal_spec=serialized_goal_spec,
                    planner=planner,
                    provider=selected_score_provider,
                    actions=selected_actions,
                    predicted_states=[],
                    success_probability=max(0.0, min(1.0, success_probability)),
                    metadata=metadata,
                )

            selected_actions = policy_result.actions[:max_steps]
            metadata = {
                "planning_mode": "policy",
                "policy_provider": selected_policy_provider,
                "policy_result": policy_result.to_dict(),
                "candidate_count": len(candidate_action_plans),
                "success_probability_source": "policy_provider_no_world_model",
            }
            if execution_provider is not None:
                metadata["execution_provider"] = execution_provider
            return Plan(
                goal=resolved_goal,
                goal_spec=serialized_goal_spec,
                planner=planner,
                provider=selected_policy_provider,
                actions=selected_actions,
                predicted_states=[],
                success_probability=0.5,
                metadata=metadata,
            )

        if uses_score_planning:
            if candidate_actions is None or score_info is None:
                raise WorldForgeError(
                    "Score planning (without policy planning) requires provider, "
                    "candidate_actions, and score_info."
                )
            candidate_action_plans = _normalize_candidate_action_plans(candidate_actions)
            score_payload = (
                score_action_candidates
                if score_action_candidates is not None
                else _action_plans_to_score_payload(candidate_action_plans)
            )
            score_result = self._forge.score_actions(
                selected_score_provider,
                info=score_info,
                action_candidates=score_payload,
            )
            _require_score_count_matches_candidates(
                provider=selected_score_provider,
                score_result=score_result,
                candidate_count=len(candidate_action_plans),
            )
            if score_result.best_index >= len(candidate_action_plans):
                raise WorldForgeError(
                    f"Provider '{selected_score_provider}' selected candidate index "
                    f"{score_result.best_index}, but only {len(candidate_action_plans)} "
                    "candidate action plan(s) were provided."
                )
            selected_actions = candidate_action_plans[score_result.best_index][:max_steps]
            best_score = max(0.0, score_result.best_score)
            success_probability = 1.0 / (1.0 + best_score)
            metadata: JSONDict = {
                "planning_mode": "score",
                "score_result": score_result.to_dict(),
                "candidate_count": len(candidate_action_plans),
                "success_probability_source": "inverse_best_cost_heuristic",
            }
            if execution_provider is not None:
                metadata["execution_provider"] = execution_provider
            return Plan(
                goal=resolved_goal,
                goal_spec=serialized_goal_spec,
                planner=planner,
                provider=selected_score_provider,
                actions=selected_actions,
                predicted_states=[],
                success_probability=max(0.0, min(1.0, success_probability)),
                metadata=metadata,
            )

        simulated_state = self._snapshot()
        predicted_states: list[JSONDict] = []
        scores: list[float] = []
        for action in actions:
            payload = self._forge.predict(
                simulated_state,
                action,
                steps=1,
                provider=selected_provider,
            )
            simulated_state = _clone_state(payload.state)
            predicted_states.append(simulated_state)
            scores.append(payload.physics_score)

        return Plan(
            goal=resolved_goal,
            goal_spec=serialized_goal_spec,
            planner=planner,
            provider=selected_provider,
            actions=actions,
            predicted_states=predicted_states,
            success_probability=max(0.65, min(0.98, average(scores) if scores else 0.7)),
            metadata={"planning_mode": "predict"},
        )

    def execute_plan(
        self,
        plan: Plan,
        *args: Any,
        provider: str | None = None,
    ) -> PlanExecution:
        """Materialise ``plan.actions`` against a fresh copy of this world.

        The execution provider is resolved in priority order: ``provider`` keyword, then the
        first positional ``str`` in ``*args`` (legacy convenience), then
        ``plan.metadata["execution_provider"]``, then ``plan.provider``. The resolved provider
        must support ``predict``; otherwise :class:`WorldForgeError` is raised. The current
        ``World`` instance is not mutated; the post-execution snapshot is returned in the
        :class:`PlanExecution`.
        """

        selected_provider = provider
        if selected_provider is None:
            selected_provider = next((arg for arg in args if isinstance(arg, str)), None)
        if selected_provider is None:
            selected_provider = str(plan.metadata.get("execution_provider") or plan.provider)
        if not self._forge.provider_profile(selected_provider).capabilities.predict:
            raise WorldForgeError(
                f"Provider '{selected_provider}' cannot execute plans because it does not "
                "support predict(). Pass an execution provider that supports predict()."
            )
        executed_world = World.from_state(self._forge, self.to_dict())
        for action in plan.actions:
            executed_world.predict(action, steps=1, provider=selected_provider)
        return PlanExecution(executed_world, plan.actions)

    def evaluate(self, suite: str = "physics") -> EvaluationReport:
        """Run a built-in evaluation suite against this world's bound provider.

        ``suite`` selects one of the names registered in :func:`list_eval_suites`. The suite
        runs deterministic adapter-contract checks (not physical-fidelity measurements) and
        returns an :class:`EvaluationReport` ready for rendering.
        """

        from worldforge.evaluation import EvaluationSuite

        return EvaluationSuite.from_builtin(suite).run_report(
            self.provider,
            world=self,
            forge=self._forge,
        )


def _seed_kitchen(world: World) -> None:
    world.add_object(
        SceneObject(
            "countertop",
            Position(0.0, 0.9, 0.0),
            BBox(Position(-1.0, 0.85, -0.5), Position(1.0, 0.95, 0.5)),
        )
    )


def _seed_mug(world: World) -> None:
    world.add_object(
        SceneObject(
            "mug",
            Position(0.0, 0.8, 0.0),
            BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
            is_graspable=True,
        )
    )


def _seed_default_cube(world: World) -> None:
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )


# Order matters: prompts may match multiple templates and every match seeds its objects.
# The fallback only runs when no template matched.
_PROMPT_SEED_TEMPLATES: tuple[tuple[Callable[[str], bool], Callable[[World], None]], ...] = (
    (lambda prompt: "kitchen" in prompt, _seed_kitchen),
    (lambda prompt: "mug" in prompt, _seed_mug),
)
_DEFAULT_PROMPT_SEED: Callable[[World], None] = _seed_default_cube


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
    ) -> None:
        self.state_dir = Path(state_dir or ".worldforge/worlds").expanduser().resolve()
        ensure_directory(self.state_dir)
        self._providers: dict[str, BaseProvider] = {}
        self._event_handler = event_handler
        # Per-capability registries for the new capability-protocol API. One dict per capability;
        # names are scoped per capability so the same name in different registries is allowed.
        self._capability_registries: dict[str, dict[str, _ObservableCapability]] = {
            field: {} for field in CAPABILITY_FIELD_NAMES
        }
        for entry in PROVIDER_CATALOG:
            provider = entry.create(event_handler=self._event_handler)
            if entry.always_register or (auto_register_remote and provider.configured()):
                self.register_provider(provider)

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

        if self._event_handler is not None and provider.event_handler is None:
            provider.event_handler = self._event_handler
        self._providers[provider.name] = provider

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
        if isinstance(impl, RunnableModel):
            matched = False
            for field_name, capability_impl in impl.capability_fields():
                self._register_capability(field_name, capability_impl)
                matched = True
            if not matched:
                raise WorldForgeError(
                    f"RunnableModel '{impl.name}' does not contain any capability impls."
                )
            return
        matched = False
        for field_name, protocol in CAPABILITY_PROTOCOLS.items():
            if isinstance(impl, protocol):
                self._register_capability(field_name, impl)
                matched = True
        if not matched:
            raise WorldForgeError(
                f"{type(impl).__name__} does not satisfy any capability protocol. "
                f"Expected one of: {', '.join(sorted(CAPABILITY_PROTOCOLS))}."
            )

    def register_policy(self, policy: Policy) -> None:
        """Register a :class:`~worldforge.capabilities.Policy` implementation."""

        self._register_typed("policy", policy, Policy)

    def register_cost(self, cost: Cost) -> None:
        """Register a :class:`~worldforge.capabilities.Cost` implementation."""

        self._register_typed("cost", cost, Cost)

    def register_generator(self, generator: Generator) -> None:
        """Register a :class:`~worldforge.capabilities.Generator` implementation."""

        self._register_typed("generator", generator, Generator)

    def register_predictor(self, predictor: Predictor) -> None:
        """Register a :class:`~worldforge.capabilities.Predictor` implementation."""

        self._register_typed("predictor", predictor, Predictor)

    def register_reasoner(self, reasoner: Reasoner) -> None:
        """Register a :class:`~worldforge.capabilities.Reasoner` implementation."""

        self._register_typed("reasoner", reasoner, Reasoner)

    def register_embedder(self, embedder: Embedder) -> None:
        """Register an :class:`~worldforge.capabilities.Embedder` implementation."""

        self._register_typed("embedder", embedder, Embedder)

    def register_transferer(self, transferer: Transferer) -> None:
        """Register a :class:`~worldforge.capabilities.Transferer` implementation."""

        self._register_typed("transferer", transferer, Transferer)

    def register_planner(self, planner: Planner) -> None:
        """Register a :class:`~worldforge.capabilities.Planner` implementation."""

        self._register_typed("planner", planner, Planner)

    def _register_typed(self, field_name: str, impl: object, protocol: type) -> None:
        if not isinstance(impl, protocol):
            raise WorldForgeError(
                f"{type(impl).__name__} does not satisfy the "
                f"{protocol.__name__} capability protocol."
            )
        self._register_capability(field_name, impl)

    def _register_capability(self, field_name: str, impl: object) -> None:
        registry = self._capability_registries[field_name]
        impl_name = getattr(impl, "name", None)
        if not isinstance(impl_name, str) or not impl_name.strip():
            raise WorldForgeError(
                f"Capability impl '{type(impl).__name__}' must declare "
                f"a non-empty 'name' attribute."
            )
        if impl_name in registry:
            raise WorldForgeError(
                f"Capability '{field_name}' already has a registered implementation named "
                f"'{impl_name}'. Names must be unique within a capability registry."
            )
        wrapped = _ObservableCapability(
            impl,
            kind=field_name,
            event_handler=self._event_handler,
        )
        registry[impl_name] = wrapped

    def _registered_capability_names(self) -> set[str]:
        return {name for registry in self._capability_registries.values() for name in registry}

    def _capability_wrappers_for_name(self, name: str) -> tuple[_ObservableCapability, ...]:
        return tuple(
            registry[name]
            for field_name in CAPABILITY_FIELD_NAMES
            for registry in (self._capability_registries[field_name],)
            if name in registry
        )

    def _registered_provider_names(self) -> set[str]:
        return set(self._providers) | self._registered_capability_names()

    def _provider_view_names(self, *, include_known: bool) -> list[str]:
        names = set(self._registered_provider_names())
        if include_known:
            names.update(self._provider_catalog(include_known=True))
        return sorted(names)

    def _merged_capabilities(
        self,
        *,
        legacy_profile: ProviderProfile | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderCapabilities:
        flags = (
            legacy_profile.capabilities.to_dict()
            if legacy_profile is not None
            else dict.fromkeys(CAPABILITY_NAMES, False)
        )
        for wrapper in wrappers:
            flags[CAPABILITY_FIELD_TO_NAME[wrapper.kind]] = True
        return ProviderCapabilities(**flags)

    def _merged_profile(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderProfile:
        wrapper_profiles = [wrapper.profile() for wrapper in wrappers]
        legacy_profile = legacy_provider.profile() if legacy_provider is not None else None
        profiles = [
            profile for profile in (legacy_profile, *wrapper_profiles) if profile is not None
        ]
        if not profiles:
            raise ProviderError(f"Provider '{name}' is unknown.")
        primary = profiles[0]
        required_env_vars = _dedupe_text(
            [env_var for profile in profiles for env_var in profile.required_env_vars]
        )
        credential_env_var = next(
            (profile.credential_env_var for profile in profiles if profile.credential_env_var),
            required_env_vars[0] if required_env_vars else None,
        )
        request_policy = next(
            (profile.request_policy for profile in profiles if profile.request_policy is not None),
            None,
        )
        default_model = next(
            (profile.default_model for profile in profiles if profile.default_model),
            None,
        )
        description = primary.description or _join_non_empty(
            [profile.description for profile in profiles],
            separator="; ",
        )
        return ProviderProfile(
            name=name,
            capabilities=self._merged_capabilities(
                legacy_profile=legacy_profile,
                wrappers=wrappers,
            ),
            is_local=any(profile.is_local for profile in profiles),
            description=description,
            package=primary.package,
            implementation_status=primary.implementation_status,
            deterministic=all(profile.deterministic for profile in profiles),
            requires_credentials=any(profile.requires_credentials for profile in profiles),
            credential_env_var=credential_env_var,
            required_env_vars=required_env_vars,
            supported_modalities=_dedupe_text(
                [item for profile in profiles for item in profile.supported_modalities]
            ),
            artifact_types=_dedupe_text(
                [item for profile in profiles for item in profile.artifact_types]
            ),
            notes=_dedupe_text([item for profile in profiles for item in profile.notes]),
            default_model=default_model,
            supported_models=_dedupe_text(
                [item for profile in profiles for item in profile.supported_models]
            ),
            request_policy=request_policy,
        )

    def _merged_health(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderHealth:
        healths: list[ProviderHealth] = []
        if legacy_provider is not None:
            healths.append(legacy_provider.health())
        healths.extend(wrapper.health() for wrapper in wrappers)
        if not healths:
            raise ProviderError(f"Provider '{name}' is unknown.")
        if len(healths) == 1:
            return healths[0]
        healthy = all(health.healthy for health in healths)
        if healthy:
            details = "configured"
        else:
            details = "; ".join(
                f"{health.name}: {health.details}" for health in healths if not health.healthy
            )
        return ProviderHealth(
            name=name,
            healthy=healthy,
            latency_ms=sum(health.latency_ms for health in healths),
            details=details,
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
            registry = self._capability_registries[field_name]
            if target_name in registry:
                return registry[target_name]
            return self._require_provider(target_name)
        if isinstance(target, BaseProvider):
            if self._event_handler is not None and target.event_handler is None:
                target.event_handler = self._event_handler
            return target
        if not isinstance(target, protocol):
            capability_name = CAPABILITY_FIELD_TO_NAME[field_name]
            raise WorldForgeError(
                f"{type(target).__name__} does not satisfy the "
                f"{protocol.__name__} capability protocol for '{capability_name}'."
            )
        return _ObservableCapability(
            target,
            kind=field_name,
            event_handler=self._event_handler,
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
        resolved = self._resolve_capability_target(
            field_name=field_name,
            protocol=protocol,
            target=target,
            operation=operation,
            target_label=target_label,
        )
        if isinstance(resolved, _ObservableCapability):
            return resolved.call(*args, **dict(kwargs or {}))
        method_name = CAPABILITY_METHOD_MAP[field_name][0]
        return getattr(resolved, method_name)(*args, **dict(kwargs or {}))

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

        legacy_catalog = self._provider_catalog(include_known=not registered_only)
        statuses: list[ProviderDoctorStatus] = []
        issues: list[str] = []

        for name in self._provider_view_names(include_known=not registered_only):
            legacy_provider = legacy_catalog.get(name)
            wrappers = self._capability_wrappers_for_name(name)
            profile = self._merged_profile(
                name,
                legacy_provider=legacy_provider,
                wrappers=wrappers,
            )
            if capability and not profile.capabilities.supports(capability):
                continue
            health = self._merged_health(
                name,
                legacy_provider=legacy_provider,
                wrappers=wrappers,
            )
            statuses.append(
                ProviderDoctorStatus(
                    registered=name in self._registered_provider_names(),
                    profile=profile,
                    health=health,
                )
            )
            if not health.healthy:
                missing_configuration = bool(profile.required_env_vars) and (
                    (legacy_provider is not None and not legacy_provider.configured())
                    or any(not wrapper.configured() for wrapper in wrappers)
                )
                if missing_configuration:
                    required = ", ".join(profile.required_env_vars)
                    issues.append(
                        f"Provider '{name}' is unavailable: missing or invalid {required}."
                    )
                else:
                    issues.append(f"Provider '{name}' is unhealthy: {health.details}.")

        return DoctorReport(
            state_dir=str(self.state_dir),
            world_count=len(self.list_worlds()),
            providers=statuses,
            issues=issues,
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
        prompt = _require_non_empty_text(prompt, name="Prompt")
        world = self.create_world(name or "prompt-world", provider, description=prompt)
        prompt_lower = prompt.lower()
        for matches, seed in _PROMPT_SEED_TEMPLATES:
            if matches(prompt_lower):
                seed(world)
        if not world.scene_objects:
            _DEFAULT_PROMPT_SEED(world)
        world._history = []
        world._record_history(summary="world seeded from prompt", action=None)
        return world

    def save_world(self, world: World) -> str:
        """Validate and atomically write a world to the local JSON state directory."""

        path = _world_file(self.state_dir, world.id)
        tmp_path = path.with_name(f".{path.name}.{generate_id('tmp')}.tmp")
        try:
            # Round-trip the dict through `from_state` to reject any payload that
            # would fail to load later — cheaper than serializing to JSON first.
            state = world.to_dict()
            World.from_state(self, state)
            tmp_path.write_text(dump_json(state), encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            raise WorldStateError(f"Failed to save world '{world.id}' to {path}: {exc}") from exc
        except WorldStateError as exc:
            raise WorldStateError(
                f"World '{world.id}' is not valid for persistence: {exc}"
            ) from exc
        finally:
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)
        return world.id

    def load_world(self, world_id: str) -> World:
        """Load a world from local JSON after validating its storage identifier and payload."""

        path = _world_file(self.state_dir, world_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return World.from_state(self, payload)
        except OSError as exc:
            raise WorldStateError(f"Failed to load world '{world_id}' from {path}: {exc}") from exc
        except ValueError as exc:
            raise WorldStateError(f"World file '{path}' is invalid: {exc}") from exc

    def delete_world(self, world_id: str) -> str:
        """Delete a persisted world file after validating its storage identifier."""

        safe_id = _validate_storage_id(world_id, name="world_id")
        path = self.state_dir / f"{safe_id}.json"
        try:
            path.unlink(missing_ok=False)
        except FileNotFoundError as exc:
            raise WorldStateError(f"World '{safe_id}' is not present at {path}.") from exc
        except OSError as exc:
            raise WorldStateError(f"Failed to delete world '{safe_id}' at {path}: {exc}") from exc
        return safe_id

    def list_worlds(self) -> list[str]:
        return sorted(path.stem for path in self.state_dir.glob("*.json"))

    def export_world(self, world_id: str, *, format: str = "json") -> str:
        if format != "json":
            raise WorldForgeError("Only json export is supported.")
        world = self.load_world(world_id)
        return dump_json({"schema_version": SCHEMA_VERSION, "state": world.to_dict()})

    def import_world(
        self,
        payload: str,
        *,
        format: str = "json",
        new_id: bool = False,
        name: str | None = None,
    ) -> World:
        """Restore a world from exported JSON without saving it automatically."""

        if format != "json":
            raise WorldForgeError("Only json import is supported.")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WorldStateError(f"Import payload is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise WorldStateError("Import payload must decode to a JSON object.")
        try:
            state = dict(data["state"]) if "state" in data else dict(data)
        except (TypeError, ValueError) as exc:
            raise WorldStateError("Import payload state must be a JSON object.") from exc
        if new_id:
            state["id"] = generate_id("world")
        if name:
            state["name"] = name
            metadata = dict(state.get("metadata", {}))
            metadata["name"] = name
            state["metadata"] = metadata
        return World.from_state(self, state)

    def fork_world(
        self, world_id: str, *, history_index: int = 0, name: str | None = None
    ) -> World:
        fork = self.load_world(world_id).history_state(history_index)
        if name:
            fork.name = name
            fork.metadata["name"] = name
        fork.id = generate_id("world")
        fork._history = []
        fork._record_history(summary="world forked", action=None)
        return fork

    def generate(
        self,
        prompt: str,
        provider: str | Generator | BaseProvider | None = None,
        *,
        generator: str | Generator | BaseProvider | None = None,
        duration_seconds: float = 1.0,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        prompt, duration_seconds, options = validate_generation_request(
            prompt,
            duration_seconds,
            options=options,
        )
        target = self._select_capability_target(
            provider,
            generator,
            operation="generate",
            keyword_name="generator",
        )
        return cast(
            VideoClip,
            self._call_capability(
                field_name="generator",
                protocol=Generator,
                target=target,
                operation="generate",
                target_label="generator",
                args=(prompt, duration_seconds),
                kwargs={"options": options},
            ),
        )

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

    def transfer(
        self,
        clip: VideoClip,
        provider: str | Transferer | BaseProvider | None = None,
        *,
        transferer: str | Transferer | BaseProvider | None = None,
        width: int,
        height: int,
        fps: float,
        prompt: str = "",
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        clip, width, height, fps, prompt, options = validate_transfer_request(
            clip,
            width=width,
            height=height,
            fps=fps,
            prompt=prompt,
            options=options,
        )
        target = self._select_capability_target(
            provider,
            transferer,
            operation="transfer",
            keyword_name="transferer",
        )
        return cast(
            VideoClip,
            self._call_capability(
                field_name="transferer",
                protocol=Transferer,
                target=target,
                operation="transfer",
                target_label="transferer",
                args=(clip,),
                kwargs={
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "prompt": prompt,
                    "options": options,
                },
            ),
        )

    def reason(
        self,
        provider: str | Reasoner | BaseProvider | None = None,
        query: str | None = None,
        *,
        reasoner: str | Reasoner | BaseProvider | None = None,
        world: World | None = None,
    ) -> ReasoningResult:
        if query is None:
            raise WorldForgeError("reason() requires a query.")
        world_state = world._snapshot() if world else None
        target = self._select_capability_target(
            provider,
            reasoner,
            operation="reason",
            keyword_name="reasoner",
        )
        return cast(
            ReasoningResult,
            self._call_capability(
                field_name="reasoner",
                protocol=Reasoner,
                target=target,
                operation="reason",
                target_label="reasoner",
                args=(query,),
                kwargs={"world_state": world_state},
            ),
        )

    def embed(
        self,
        provider: str | Embedder | BaseProvider | None = None,
        *,
        embedder: str | Embedder | BaseProvider | None = None,
        text: str,
    ) -> EmbeddingResult:
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
