"""Mutable world runtime and planning facade for WorldForge.

This module owns the in-process world state object: local scene/history mutation,
provider-backed prediction, comparison, planning, execution, and evaluation. The top-level
``WorldForge`` facade remains in ``framework.py`` and imports ``World`` for backwards
compatibility.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from worldforge._results import Comparison, Plan, PlanExecution, Prediction
from worldforge._state import (
    SCHEMA_VERSION,
)
from worldforge._state import (
    restore_history_entries as _restore_history_entries,
)
from worldforge._state import (
    restore_scene_objects as _restore_scene_objects,
)
from worldforge._state import (
    validate_storage_id as _validate_storage_id,
)
from worldforge._state import (
    validate_world_state_payload as _validate_world_state_payload,
)
from worldforge._world_planning import normalize_provider_name as _normalize_provider_name
from worldforge._world_planning import plan_execution_provider as _plan_execution_provider
from worldforge._world_planning import plan_world as _plan_world
from worldforge.models import (
    Action,
    HistoryEntry,
    JSONDict,
    SceneObject,
    SceneObjectPatch,
    StructuredGoal,
    WorldForgeError,
    WorldStateError,
    dump_json,
    generate_id,
    require_json_dict,
    require_positive_int,
)
from worldforge.models import (
    require_non_empty_text as _require_non_empty_text,
)
from worldforge.providers import BaseProvider

if TYPE_CHECKING:
    from worldforge.control import PlannerConfig, ScoreCandidateEncoder
    from worldforge.evaluation import EvaluationReport
    from worldforge.framework import WorldForge


def _clone_state(state: JSONDict) -> JSONDict:
    return deepcopy(state)


def _world_forge(forge: WorldForge | None) -> WorldForge:
    if forge is not None:
        return forge
    from worldforge.framework import WorldForge

    return WorldForge()


def _world_storage_id(world_id: str | None) -> str:
    return _validate_storage_id(world_id or generate_id("world"), name="world_id")


def _world_metadata(metadata: JSONDict | None, *, name: str) -> JSONDict:
    world_metadata = require_json_dict(metadata or {}, name="World metadata")
    world_metadata.setdefault("name", name)
    return world_metadata


def _world_max_history(max_history: int | None) -> int | None:
    if max_history is None:
        return None
    return require_positive_int(max_history, name="World max_history")


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
        self._forge = _world_forge(forge)
        self.id = _world_storage_id(world_id)
        self.name = _require_non_empty_text(
            name,
            name="World name",
            message="World name must not be empty.",
        )
        self.provider = _require_non_empty_text(provider, name="World provider")
        self.description = description
        self.step = 0
        self.metadata = _world_metadata(metadata, name=self.name)
        self.max_history = _world_max_history(max_history)
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

    @staticmethod
    def _require_scene_object_patch(patch: object) -> SceneObjectPatch:
        if not isinstance(patch, SceneObjectPatch):
            raise WorldForgeError("update_object_patch() patch must be a SceneObjectPatch.")
        return patch

    def _scene_object_for_update(self, object_id: str) -> SceneObject:
        try:
            return self.scene_objects[object_id]
        except KeyError as exc:
            raise WorldForgeError(
                f"Object '{object_id}' is not present in world '{self.id}'."
            ) from exc

    @staticmethod
    def _patched_scene_object(before: SceneObject, patch: SceneObjectPatch) -> SceneObject:
        staged_object = before.copy()
        staged_object.apply_patch(patch)
        return staged_object.copy()

    @staticmethod
    def _object_update_action(
        *,
        before: SceneObject,
        updated: SceneObject,
        changes: JSONDict,
    ) -> Action:
        return Action(
            "update_object",
            {
                "object_id": updated.id,
                "changes": changes,
                "before": before.to_dict(),
                "after": updated.to_dict(),
            },
        )

    def _commit_object_update(
        self,
        *,
        before: SceneObject,
        updated: SceneObject,
        changes: JSONDict,
    ) -> None:
        staged_scene_objects = {**self.scene_objects, updated.id: updated}
        history_entry = self._make_history_entry(
            summary=f"updated object {updated.id}",
            action=self._object_update_action(
                before=before,
                updated=updated,
                changes=changes,
            ),
            state=self._snapshot_with(scene_objects=staged_scene_objects),
        )
        self.scene_objects = staged_scene_objects
        self._append_history_entry(history_entry)

    def update_object_patch(self, object_id: str, patch: SceneObjectPatch) -> SceneObject:
        patch = self._require_scene_object_patch(patch)
        before = self._scene_object_for_update(object_id).copy()
        changes = self._object_patch_payload(patch)
        if not changes:
            return before
        updated = self._patched_scene_object(before, patch)
        self._commit_object_update(before=before, updated=updated, changes=changes)
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

    @staticmethod
    def _comparison_providers(providers: str | Sequence[str]) -> list[str]:
        ordered = [providers] if isinstance(providers, str) else list(providers)
        if not ordered:
            raise WorldForgeError("compare() requires at least one provider.")
        return ordered

    def _comparison_prediction(
        self,
        *,
        provider_name: str,
        state: JSONDict,
        action: Action,
        steps: int,
    ) -> Prediction:
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

    def _comparison_predictions(
        self,
        *,
        providers: Sequence[str],
        state: JSONDict,
        action: Action,
        steps: int,
    ) -> list[Prediction]:
        def predict_one(provider_name: str) -> Prediction:
            return self._comparison_prediction(
                provider_name=provider_name,
                state=state,
                action=action,
                steps=steps,
            )

        if len(providers) == 1:
            return [predict_one(providers[0])]
        with ThreadPoolExecutor(max_workers=min(8, len(providers))) as pool:
            return list(pool.map(predict_one, providers))

    def compare(self, action: Action, providers: str | Sequence[str], steps: int = 1) -> Comparison:
        """Predict the same ``(action, steps)`` against several providers and collect results.

        ``providers`` may be a single provider name or a sequence of names. Predictions for
        multiple providers are dispatched concurrently; each receives an independent snapshot
        copy of the world state. Returns a :class:`Comparison` whose
        :meth:`Comparison.best_prediction` selects the highest-scoring provider.

        Raises :class:`WorldForgeError` if ``providers`` is empty or ``steps`` is non-positive.
        """

        require_positive_int(steps, name="steps")
        return Comparison(
            self._comparison_predictions(
                providers=self._comparison_providers(providers),
                state=self._snapshot(),
                action=action,
                steps=steps,
            )
        )

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
        planner_config: PlannerConfig | None = None,
        candidate_encoder: ScoreCandidateEncoder | None = None,
        goal_info: JSONDict | None = None,
        execution_provider: str | None = None,
        **_: Any,
    ) -> Plan:
        """Plan actions through a predictive, score, policy, or policy-plus-score path.

        The selected path is determined by the capability-specific inputs:
        ``candidate_actions`` or score arguments choose score planning, ``policy_info`` chooses
        policy planning, and both together compose policy proposals with score-provider ranking.
        Without those inputs, the world uses a predictive provider and records predicted states.
        """

        return _plan_world(
            forge=self._forge,
            scene_objects=self.scene_objects,
            snapshot=self._snapshot,
            default_provider=self.provider,
            goal=goal,
            goal_spec=goal_spec,
            goal_json=goal_json,
            planner=planner,
            max_steps=max_steps,
            provider=provider,
            candidate_actions=candidate_actions,
            policy_provider=policy_provider,
            policy_info=policy_info,
            score_provider=score_provider,
            score_info=score_info,
            score_action_candidates=score_action_candidates,
            planner_config=planner_config,
            candidate_encoder=candidate_encoder,
            goal_info=goal_info,
            execution_provider=execution_provider,
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

        selected_provider = _plan_execution_provider(plan, args=args, provider=provider)
        self._require_plan_execution_provider(selected_provider)
        executed_world = self._world_after_plan_actions(
            plan.actions,
            provider=selected_provider,
        )
        return PlanExecution(executed_world, plan.actions)

    def _require_plan_execution_provider(self, provider: str) -> None:
        if self._forge.provider_profile(provider).capabilities.predict:
            return
        raise WorldForgeError(
            f"Provider '{provider}' cannot execute plans because it does not "
            "support predict(). Pass an execution provider that supports predict()."
        )

    def _world_after_plan_actions(
        self,
        actions: Sequence[Action],
        *,
        provider: str,
    ) -> World:
        executed_world = World.from_state(self._forge, self.to_dict())
        for action in actions:
            executed_world.predict(action, steps=1, provider=provider)
        return executed_world

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
