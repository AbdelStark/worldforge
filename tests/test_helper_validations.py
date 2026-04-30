from __future__ import annotations

import json
import math

import httpx
import pytest

import worldforge.providers.http_utils as http_utils
from worldforge import (
    Action,
    ActionPolicyResult,
    BBox,
    Comparison,
    EmbeddingResult,
    GenerationOptions,
    Pose,
    Position,
    ProviderBudgetExceededError,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    ProviderRequestPolicy,
    ReasoningResult,
    RequestOperationPolicy,
    RetryPolicy,
    Rotation,
    SceneObject,
    SceneObjectPatch,
    VideoClip,
    World,
    WorldForge,
    WorldForgeError,
    WorldStateError,
)
from worldforge.models import HistoryEntry, average, dump_json
from worldforge.providers import PredictionPayload, ProviderError
from worldforge.providers.http_utils import (
    asset_to_uri,
    parse_size,
    poll_json_task,
    request_json_with_policy,
)


def test_http_utils_validate_assets_size_and_polling(tmp_path) -> None:
    image_path = tmp_path / "seed.png"
    image_path.write_bytes(b"png")

    asset_uri = asset_to_uri(str(image_path), default_content_type="image/png")
    assert asset_uri is not None
    assert asset_uri.startswith("data:image/png;base64,")

    with pytest.raises(ProviderError, match="does not exist"):
        asset_to_uri(str(tmp_path / "missing.png"), default_content_type="image/png")

    assert parse_size(GenerationOptions(size="640x360"), fallback=(1280, 720)) == (640, 360)
    assert parse_size(GenerationOptions(ratio="16:9"), fallback=(1280, 720)) == (16, 9)

    with pytest.raises(ProviderError, match="greater than 0"):
        parse_size(GenerationOptions(size="0x360"), fallback=(1280, 720))

    processing_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "PROCESSING"})
        ),
        base_url="http://providers.test",
    )
    with (
        processing_client as client,
        pytest.raises(ProviderError, match="did not complete before timeout"),
    ):
        poll_json_task(
            client,
            path="/tasks/1",
            success_values={"SUCCEEDED"},
            failure_values={"FAILED"},
            poll_interval_seconds=0.0,
            max_polls=1,
            provider_name="mock",
            operation_policy=ProviderRequestPolicy.remote_defaults(
                request_timeout_seconds=10.0,
                read_backoff_seconds=0.0,
            ).polling,
        )

    failed_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "FAILED"})
        ),
        base_url="http://providers.test",
    )
    with (
        failed_client as client,
        pytest.raises(ProviderError, match="task failed with status FAILED"),
    ):
        poll_json_task(
            client,
            path="/tasks/2",
            success_values={"SUCCEEDED"},
            failure_values={"FAILED"},
            poll_interval_seconds=0.0,
            max_polls=1,
            provider_name="mock",
            operation_policy=ProviderRequestPolicy.remote_defaults(
                request_timeout_seconds=10.0,
                read_backoff_seconds=0.0,
            ).polling,
        )

    with pytest.raises(WorldForgeError, match="max_attempts"):
        RetryPolicy(max_attempts=0)

    default_request_policy = ProviderRequestPolicy.remote_defaults(request_timeout_seconds=12.0)
    assert default_request_policy.request.retry.max_attempts == 1
    assert default_request_policy.download.retry.max_attempts == 3
    assert default_request_policy.to_dict()["health"]["timeout_seconds"] == 10.0
    budgeted_request_policy = ProviderRequestPolicy.remote_defaults(
        request_timeout_seconds=12.0,
        health_max_elapsed_seconds=2.0,
        request_max_elapsed_seconds=3.0,
        polling_max_elapsed_seconds=4.0,
        download_max_elapsed_seconds=5.0,
    )
    assert budgeted_request_policy.health.max_elapsed_seconds == 2.0
    assert budgeted_request_policy.to_dict()["request"]["max_elapsed_seconds"] == 3.0

    with pytest.raises(WorldForgeError, match="max_elapsed_seconds"):
        RequestOperationPolicy(timeout_seconds=1.0, max_elapsed_seconds=0.0)

    event = ProviderEvent(
        provider="mock",
        operation="predict",
        phase="success",
        duration_ms=12.5,
        metadata={"steps": 1},
    )
    assert event.to_dict()["metadata"] == {"steps": 1}

    with pytest.raises(WorldForgeError, match="duration_ms"):
        ProviderEvent(provider="mock", operation="predict", phase="success", duration_ms=-1.0)


def test_http_request_policy_budget_failures_are_observable() -> None:
    events: list[ProviderEvent] = []
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503, text="warming")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://providers.test")
    with (
        client,
        pytest.raises(ProviderBudgetExceededError, match="exceeded budget"),
    ):
        request_json_with_policy(
            client,
            method="GET",
            url="/health",
            provider_name="mock",
            operation_name="healthcheck",
            policy=RequestOperationPolicy(
                timeout_seconds=1.0,
                retry=RetryPolicy(max_attempts=3, backoff_seconds=2.0),
                max_elapsed_seconds=1.0,
            ),
            emit_event=events.append,
        )

    assert attempts["count"] == 1
    assert [(event.operation, event.phase) for event in events] == [
        ("healthcheck", "budget_exceeded")
    ]
    assert events[0].metadata == {"max_elapsed_seconds": 1.0}


def test_http_request_policy_budget_can_fail_before_first_attempt(monkeypatch) -> None:
    events: list[ProviderEvent] = []
    attempts = {"count": 0}
    times = iter([0.0, 2.0, 2.0, 2.0])

    monkeypatch.setattr(http_utils, "perf_counter", lambda: next(times))

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://providers.test")
    with (
        client,
        pytest.raises(ProviderBudgetExceededError, match="exceeded budget"),
    ):
        request_json_with_policy(
            client,
            method="GET",
            url="/health",
            provider_name="mock",
            operation_name="healthcheck",
            policy=RequestOperationPolicy(timeout_seconds=1.0, max_elapsed_seconds=1.0),
            emit_event=events.append,
        )

    assert attempts["count"] == 0
    assert events[0].phase == "budget_exceeded"
    assert events[0].duration_ms == 2000.0


def test_poll_json_task_budget_blocks_silent_poll_loops() -> None:
    events: list[ProviderEvent] = []
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, json={"status": "PROCESSING"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://providers.test")
    with (
        client,
        pytest.raises(ProviderBudgetExceededError, match="task poll exceeded budget"),
    ):
        poll_json_task(
            client,
            path="/tasks/1",
            success_values={"SUCCEEDED"},
            failure_values={"FAILED"},
            poll_interval_seconds=2.0,
            max_polls=5,
            provider_name="mock",
            operation_policy=RequestOperationPolicy(
                timeout_seconds=1.0,
                max_elapsed_seconds=1.0,
            ),
            emit_event=events.append,
        )

    assert attempts["count"] == 1
    assert events[-1].operation == "task poll"
    assert events[-1].phase == "budget_exceeded"


def test_framework_helpers_and_error_paths(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world_from_prompt("empty room", provider="mock")
    assert world.object_count == 1
    assert world.list_objects() == ["cube"]

    prediction = world.predict(Action.move_to(0.1, 0.5, 0.0), steps=1)
    assert prediction.output_world().object_count == world.object_count

    comparison = world.compare(Action.move_to(0.2, 0.5, 0.0), "mock", steps=1)
    artifacts = comparison.artifacts()
    assert set(artifacts) == {"json", "markdown", "csv"}

    assert forge.provider_info("mock").name == "mock"
    assert [health.name for health in forge.provider_healths(capability="generate")] == ["mock"]

    clip = forge.generate("a cube rolling across a table", "mock", duration_seconds=1.0)
    saved_clip_path = clip.save(tmp_path / "clip.bin")
    assert saved_clip_path.exists()
    with pytest.raises(WorldForgeError, match="duration_seconds"):
        forge.generate("a cube rolling across a table", "mock", duration_seconds=math.nan)
    with pytest.raises(WorldForgeError, match="prompt"):
        forge.generate(" ", "mock", duration_seconds=1.0)
    with pytest.raises(WorldForgeError, match="width"):
        forge.transfer(clip, "mock", width=True, height=180, fps=12.0)  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="fps"):
        forge.transfer(clip, "mock", width=320, height=180, fps=math.inf)

    assert Comparison([prediction]).prediction_count == 1

    with pytest.raises(ValueError, match="Comparison has no predictions"):
        Comparison([]).best_prediction()

    with pytest.raises(WorldForgeError, match="World name must not be empty"):
        forge.create_world("", "mock")

    with pytest.raises(WorldForgeError, match="World max_history"):
        World("limited", "mock", max_history=True)

    with pytest.raises(WorldForgeError, match="Only json export"):
        forge.export_world("missing", format="yaml")

    with pytest.raises(WorldForgeError, match="Only json import"):
        forge.import_world("{}", format="yaml")


def test_public_models_reject_non_finite_and_incoherent_values(tmp_path) -> None:
    with pytest.raises(WorldForgeError, match=r"Position\.x"):
        Position(math.nan, 0.0, 0.0)

    with pytest.raises(WorldForgeError, match="BBox min coordinates"):
        BBox(Position(1.0, 0.0, 0.0), Position(0.0, 0.0, 0.0))

    with pytest.raises(WorldForgeError, match="speed"):
        Action.move_to(0.0, 0.0, 0.0, speed=0.0)
    with pytest.raises(WorldForgeError, match="Action parameters"):
        Action("bad", {"not_json": object()})

    policy_result = ActionPolicyResult(
        provider="policy",
        actions=[Action.move_to(0.1, 0.5, 0.0)],
        raw_actions={"arm": [[[0.1, 0.5, 0.0]]]},
        action_horizon=1,
        embodiment_tag="TEST",
    )
    assert policy_result.action_candidates == [[Action.move_to(0.1, 0.5, 0.0)]]
    assert policy_result.to_dict()["embodiment_tag"] == "TEST"

    with pytest.raises(WorldForgeError, match="actions"):
        ActionPolicyResult(provider="policy", actions=[])

    with pytest.raises(WorldForgeError, match="raw_actions"):
        ActionPolicyResult(
            provider="policy",
            actions=[Action.move_to(0.1, 0.5, 0.0)],
            raw_actions=[],  # type: ignore[arg-type]
        )

    with pytest.raises(WorldForgeError, match="action_horizon"):
        ActionPolicyResult(
            provider="policy",
            actions=[Action.move_to(0.1, 0.5, 0.0)],
            action_horizon=0,
        )

    with pytest.raises(WorldForgeError, match="GenerationOptions fps"):
        GenerationOptions(fps=math.inf)

    with pytest.raises(WorldForgeError, match="timeout_seconds"):
        ProviderRequestPolicy.remote_defaults(request_timeout_seconds=math.nan)

    with pytest.raises(WorldForgeError, match="status_code"):
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            status_code=99,
        )

    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("invariant-world", "mock")
    cube = world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )
    with pytest.raises(WorldForgeError, match="already present"):
        world.add_object(cube)

    bad_state = {
        "schema_version": 1,
        "id": "world_bad",
        "name": "bad",
        "provider": "mock",
        "step": 0,
        "scene": {
            "objects": {
                "obj_key": SceneObject(
                    "cube",
                    Position(0.0, 0.5, 0.0),
                    BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
                    id="obj_embedded",
                ).to_dict()
            }
        },
        "metadata": {},
    }
    with pytest.raises(WorldStateError, match="does not match embedded id"):
        forge.import_world(json.dumps(bad_state))


def test_public_validation_guards_cover_boundary_failure_modes() -> None:
    assert average([]) == 0.0

    with pytest.raises(WorldForgeError):
        dump_json({"bad": math.nan})

    with pytest.raises(WorldForgeError):
        Position.from_dict(["not-a-position"])  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        Position.from_dict({"x": 0.0, "y": 0.0})
    with pytest.raises(WorldForgeError):
        Rotation.from_dict(["not-a-rotation"])  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        Pose("not-a-position")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        BBox("not-a-position", Position(0.0, 0.0, 0.0))  # type: ignore[arg-type]

    with pytest.raises(WorldForgeError):
        Action("", {})
    with pytest.raises(WorldForgeError):
        Action("move", [])  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        Action.move_to(0.0, 0.0, 0.0, object_id="")
    with pytest.raises(WorldForgeError):
        Action.spawn_object("")
    with pytest.raises(WorldForgeError):
        Action.from_dict(["not-an-action"])  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        Action.from_dict({"type": "move_to", "parameters": []})  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        Action.from_dict({"move_to": {}, "noop": {}})
    with pytest.raises(WorldForgeError):
        Action.from_dict({"move_to": []})  # type: ignore[arg-type]

    patch = SceneObjectPatch()
    with pytest.raises(WorldForgeError):
        patch.set_name("")
    with pytest.raises(WorldForgeError):
        patch.set_position("not-a-position")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="graspable"):
        patch.set_graspable("true")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        SceneObject(
            "",
            Position(0.0, 0.0, 0.0),
            BBox(Position(0.0, 0.0, 0.0), Position(1.0, 1.0, 1.0)),
        )
    with pytest.raises(WorldForgeError):
        SceneObject(
            "cube",
            "not-a-position",  # type: ignore[arg-type]
            BBox(Position(0.0, 0.0, 0.0), Position(1.0, 1.0, 1.0)),
        )
    with pytest.raises(WorldForgeError):
        SceneObject(
            "cube",
            Position(0.0, 0.0, 0.0),
            "not-a-bbox",  # type: ignore[arg-type]
        )
    with pytest.raises(WorldForgeError):
        SceneObject(
            "cube",
            Position(0.0, 0.0, 0.0),
            BBox(Position(0.0, 0.0, 0.0), Position(1.0, 1.0, 1.0)),
            id="",
        )
    with pytest.raises(WorldForgeError):
        SceneObject(
            "cube",
            Position(0.0, 0.0, 0.0),
            BBox(Position(0.0, 0.0, 0.0), Position(1.0, 1.0, 1.0)),
            is_graspable="false",  # type: ignore[arg-type]
        )
    with pytest.raises(WorldForgeError):
        SceneObject.from_dict(
            {
                "id": "obj_1",
                "name": "cube",
                "pose": Pose(Position(0.0, 0.0, 0.0)).to_dict(),
                "bbox": BBox(
                    Position(0.0, 0.0, 0.0),
                    Position(1.0, 1.0, 1.0),
                ).to_dict(),
                "is_graspable": "false",
            }
        )

    assert ProviderCapabilities().enabled_names() == []
    assert ProviderCapabilities(generate=True).supports("generate") is True
    assert ProviderCapabilities(generate=True).supports("predict") is False
    with pytest.raises(WorldForgeError, match="ProviderCapabilities predict"):
        ProviderCapabilities(predict="true")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="Unknown provider capability"):
        ProviderCapabilities().supports("generation")
    with pytest.raises(WorldForgeError, match="HistoryEntry step"):
        HistoryEntry(step=-1, state={}, summary="bad")
    with pytest.raises(WorldForgeError, match="HistoryEntry state"):
        HistoryEntry(step=0, state=[], summary="bad")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="summary"):
        HistoryEntry(step=0, state={}, summary="")
    with pytest.raises(WorldForgeError, match="action_json"):
        HistoryEntry(step=0, state={}, summary="bad", action_json="{broken")
    with pytest.raises(WorldForgeError, match=r"Action\.from_dict"):
        HistoryEntry(step=0, state={}, summary="bad", action_json="[]")
    with pytest.raises(WorldForgeError):
        SceneObject(
            "cube",
            Position(0.0, 0.0, 0.0),
            BBox(Position(0.0, 0.0, 0.0), Position(1.0, 1.0, 1.0)),
            metadata=[],  # type: ignore[arg-type]
        )
    with pytest.raises(WorldForgeError, match="SceneObject metadata"):
        SceneObject(
            "cube",
            Position(0.0, 0.0, 0.0),
            BBox(Position(0.0, 0.0, 0.0), Position(1.0, 1.0, 1.0)),
            metadata={"not_json": object()},
        )

    with pytest.raises(WorldForgeError):
        RetryPolicy(max_attempts=True)  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        RetryPolicy(backoff_seconds=math.inf)
    with pytest.raises(WorldForgeError):
        RetryPolicy(backoff_multiplier=0.5)
    with pytest.raises(WorldForgeError):
        RetryPolicy(retryable_status_codes=(99,))
    with pytest.raises(WorldForgeError):
        GenerationOptions(seed=True)  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        GenerationOptions(reference_images="bad")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        GenerationOptions(extras=[])  # type: ignore[arg-type]

    with pytest.raises(WorldForgeError):
        ProviderEvent(provider="", operation="predict", phase="success")
    with pytest.raises(WorldForgeError):
        ProviderEvent(provider="mock", operation="", phase="success")
    with pytest.raises(WorldForgeError):
        ProviderEvent(provider="mock", operation="predict", phase="")
    with pytest.raises(WorldForgeError):
        ProviderEvent(provider="mock", operation="predict", phase="success", attempt=0)
    with pytest.raises(WorldForgeError):
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            attempt=2,
            max_attempts=1,
        )
    with pytest.raises(WorldForgeError):
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            duration_ms=-1.0,
        )
    with pytest.raises(WorldForgeError):
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            metadata=[],  # type: ignore[arg-type]
        )
    with pytest.raises(WorldForgeError, match="metadata"):
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            metadata={"shape": (1, 2, 3)},
        )

    health = ProviderHealth(
        name=" provider ",
        healthy=True,
        latency_ms=0.0,
        details='{"api_key":"health-secret"}',
    )
    assert health.name == "provider"
    assert health.healthy is True
    assert health.latency_ms == 0.0
    assert "health-secret" not in health.details
    with pytest.raises(WorldForgeError, match="ProviderHealth name"):
        ProviderHealth(name="", healthy=True, latency_ms=0.0)
    with pytest.raises(WorldForgeError, match="ProviderHealth healthy"):
        ProviderHealth(name="mock", healthy="yes", latency_ms=0.0)  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="ProviderHealth latency_ms"):
        ProviderHealth(name="mock", healthy=True, latency_ms=math.nan)
    with pytest.raises(WorldForgeError, match="ProviderHealth details"):
        ProviderHealth(name="mock", healthy=True, latency_ms=0.0, details=[])  # type: ignore[arg-type]

    with pytest.raises(WorldForgeError):
        VideoClip(frames=[object()], fps=1.0, resolution=(1, 1), duration_seconds=0.0)
    with pytest.raises(WorldForgeError):
        VideoClip(frames=[b"ok"], fps=0.0, resolution=(1, 1), duration_seconds=0.0)
    with pytest.raises(WorldForgeError):
        VideoClip(frames=[b"ok"], fps=1.0, resolution=(1,), duration_seconds=0.0)
    with pytest.raises(WorldForgeError):
        VideoClip(frames=[b"ok"], fps=1.0, resolution=(0, 1), duration_seconds=0.0)
    with pytest.raises(WorldForgeError):
        VideoClip(frames=[b"ok"], fps=1.0, resolution=(1, 1), duration_seconds=math.nan)
    with pytest.raises(WorldForgeError):
        VideoClip(
            frames=[b"ok"],
            fps=1.0,
            resolution=(1, 1),
            duration_seconds=0.0,
            metadata=[],  # type: ignore[arg-type]
        )

    with pytest.raises(WorldForgeError):
        ReasoningResult(provider="", answer="answer", confidence=0.5)
    with pytest.raises(WorldForgeError):
        ReasoningResult(provider="mock", answer=1, confidence=0.5)  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        ReasoningResult(provider="mock", answer="answer", confidence=2.0)
    with pytest.raises(WorldForgeError):
        ReasoningResult(
            provider="mock",
            answer="answer",
            confidence=0.5,
            evidence="bad",  # type: ignore[arg-type]
        )

    with pytest.raises(WorldForgeError):
        EmbeddingResult(provider="", model="model", vector=[0.0])
    with pytest.raises(WorldForgeError):
        EmbeddingResult(provider="mock", model="", vector=[0.0])
    with pytest.raises(WorldForgeError):
        EmbeddingResult(provider="mock", model="model", vector=[])  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError):
        EmbeddingResult(provider="mock", model="model", vector=[math.nan])

    valid_state = {
        "schema_version": 1,
        "id": "world",
        "name": "world",
        "provider": "mock",
        "scene": {"objects": {}},
        "metadata": {},
        "step": 0,
    }
    with pytest.raises(WorldForgeError):
        PredictionPayload(
            state=[],  # type: ignore[arg-type]
            confidence=0.5,
            physics_score=0.5,
            frames=[],
            metadata={},
            latency_ms=0.0,
        )
    with pytest.raises(WorldForgeError):
        PredictionPayload(
            state=valid_state,
            confidence=1.5,
            physics_score=0.5,
            frames=[],
            metadata={},
            latency_ms=0.0,
        )
    with pytest.raises(WorldForgeError):
        PredictionPayload(
            state=valid_state,
            confidence=0.5,
            physics_score=0.5,
            frames=[object()],  # type: ignore[list-item]
            metadata={},
            latency_ms=0.0,
        )
    with pytest.raises(WorldForgeError):
        PredictionPayload(
            state=valid_state,
            confidence=0.5,
            physics_score=0.5,
            frames=[],
            metadata=[],  # type: ignore[arg-type]
            latency_ms=0.0,
        )
    invalid_nested_state = dict(valid_state)
    invalid_nested_state["metadata"] = {"bad": object()}
    with pytest.raises(WorldForgeError, match="PredictionPayload state"):
        PredictionPayload(
            state=invalid_nested_state,
            confidence=0.5,
            physics_score=0.5,
            frames=[],
            metadata={},
            latency_ms=0.0,
        )
    with pytest.raises(WorldForgeError, match="PredictionPayload metadata"):
        PredictionPayload(
            state=valid_state,
            confidence=0.5,
            physics_score=0.5,
            frames=[],
            metadata={"bad": object()},
            latency_ms=0.0,
        )
    with pytest.raises(WorldForgeError):
        PredictionPayload(
            state=valid_state,
            confidence=0.5,
            physics_score=0.5,
            frames=[],
            metadata={},
            latency_ms=-1.0,
        )
