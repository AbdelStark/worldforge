"""Deterministic local provider used for tests and examples."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from time import perf_counter

from worldforge.models import (
    Action,
    BBox,
    EmbeddingResult,
    JSONDict,
    Position,
    ProviderCapabilities,
    ProviderEvent,
    SceneObject,
    deterministic_floats,
)

from .base import (
    BaseProvider,
    PredictionPayload,
    ProviderError,
    ProviderProfileSpec,
)


def _frame_bytes(seed: str, index: int) -> bytes:
    return f"{seed}:frame:{index}".encode()


class MockProvider(BaseProvider):
    """Deterministic provider for examples, tests, and contract checks."""

    def __init__(
        self,
        name: str = "mock",
        *,
        event_handler: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(
                predict=True,
                embed=True,
            ),
            profile=ProviderProfileSpec(
                is_local=True,
                description=(
                    "Deterministic local provider for examples, tests, and contract checks."
                ),
                implementation_status="stable",
                deterministic=True,
                supported_modalities=("world_state", "text"),
                artifact_types=("prediction", "embedding"),
                notes=("Reference implementation for adapter contract tests.",),
                default_model="mock-deterministic-v1",
                supported_models=("mock-deterministic-v1",),
            ),
            event_handler=event_handler,
        )

    def _emit_success_event(
        self,
        *,
        operation: str,
        duration_ms: float,
        metadata: JSONDict | None = None,
    ) -> None:
        self._emit_event(
            ProviderEvent(
                provider=self.name,
                operation=operation,
                phase="success",
                duration_ms=duration_ms,
                metadata=dict(metadata or {}),
            )
        )

    def _updated_world_state(self, world_state: JSONDict, action: Action, steps: int) -> JSONDict:
        updated = deepcopy(world_state)
        scene_objects = updated.setdefault("scene", {}).setdefault("objects", {})
        action_data = action.to_dict()

        if action.kind == "move_to" and scene_objects:
            target = action.parameters["target"]
            object_id = action.parameters.get("object_id")
            if object_id is not None:
                try:
                    scene_object = scene_objects[str(object_id)]
                except KeyError as exc:
                    raise ProviderError(
                        f"Object '{object_id}' is not present in the world state."
                    ) from exc
            else:
                first_object_id = next(iter(scene_objects))
                scene_object = scene_objects[first_object_id]
            scene_object["pose"]["position"] = dict(target)
            scene_object.setdefault("metadata", {})["last_action"] = action_data
            scene_object["metadata"]["moved_by_provider"] = self.name
        elif action.kind == "spawn_object":
            obj = SceneObject(
                name=str(action.parameters["name"]),
                position=Position.from_dict(action.parameters["position"]),
                bbox=BBox.from_dict(action.parameters["bbox"]),
            )
            scene_objects[obj.id] = obj.to_dict()
        elif action.kind == "noop":
            updated.setdefault("metadata", {})["noop"] = True

        updated["step"] = int(updated.get("step", 0)) + max(1, int(steps))
        updated.setdefault("metadata", {})["provider"] = self.name
        updated["metadata"]["last_action"] = action_data
        return updated

    def predict(self, world_state: JSONDict, action: Action, steps: int) -> PredictionPayload:
        started = perf_counter()
        updated_state = self._updated_world_state(world_state, action, steps)
        object_count = len(updated_state.get("scene", {}).get("objects", {}))
        physics_score = max(0.6, min(0.99, 0.72 + (0.03 * object_count)))
        confidence = max(0.65, min(0.99, physics_score - 0.02))
        frame_count = max(1, steps)
        latency_ms = max(0.1, (perf_counter() - started) * 1000)
        payload = PredictionPayload(
            state=updated_state,
            confidence=confidence,
            physics_score=physics_score,
            frames=[_frame_bytes(self.name, index) for index in range(frame_count)],
            metadata={
                "provider": self.name,
                "steps": steps,
                "frame_count": frame_count,
                "mode": "deterministic-mock",
            },
            latency_ms=latency_ms,
        )
        self._emit_success_event(
            operation="predict",
            duration_ms=latency_ms,
            metadata={"steps": steps, "frame_count": frame_count},
        )
        return payload

    def embed(self, *, text: str) -> EmbeddingResult:
        started = perf_counter()
        result = EmbeddingResult(
            provider=self.name,
            model="mock-embedding-v1",
            vector=deterministic_floats(f"{self.name}:{text}", 32),
        )
        self._emit_success_event(
            operation="embed",
            duration_ms=max(0.1, (perf_counter() - started) * 1000),
            metadata={"dimensions": len(result.vector)},
        )
        return result
