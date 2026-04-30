from __future__ import annotations

import json
from base64 import b64encode
from pathlib import Path

import httpx
import pytest

from worldforge import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    ProviderBenchmarkHarness,
    ProviderCapabilities,
    ProviderEvent,
    ProviderRequestPolicy,
    WorldForge,
    WorldForgeError,
)
from worldforge.benchmark import (
    BenchmarkBudget,
    BenchmarkInputs,
    BenchmarkResult,
    load_benchmark_budgets,
    load_benchmark_inputs,
)
from worldforge.models import JSONDict
from worldforge.providers import CosmosProvider, RunwayProvider
from worldforge.providers.base import BaseProvider, ProviderError, ProviderProfileSpec

ROOT = Path(__file__).resolve().parents[1]


class _ScoreBenchmarkProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="scorebench",
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(description="Injected score provider for benchmark tests."),
        )
        self.calls: list[dict[str, object]] = []

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        self.calls.append({"info": info, "action_candidates": action_candidates})
        result = ActionScoreResult(
            provider=self.name,
            scores=[0.4, 0.1],
            best_index=1,
            lower_is_better=True,
            metadata={"candidate_count": 2},
        )
        self._emit_event(
            ProviderEvent(
                provider=self.name,
                operation="score",
                phase="success",
                duration_ms=0.1,
                metadata={"candidate_count": 2},
            )
        )
        return result


class _PolicyBenchmarkProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="policybench",
            capabilities=ProviderCapabilities(policy=True),
            profile=ProviderProfileSpec(
                description="Injected policy provider for benchmark tests."
            ),
        )
        self.calls: list[JSONDict] = []

    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        self.calls.append(info)
        candidate_plans = [
            [Action.move_to(0.1, 0.5, 0.0)],
            [Action.move_to(0.3, 0.5, 0.0)],
        ]
        result = ActionPolicyResult(
            provider=self.name,
            actions=list(candidate_plans[0]),
            raw_actions={"candidate_count": len(candidate_plans)},
            action_horizon=1,
            embodiment_tag="benchmark",
            metadata={"candidate_count": len(candidate_plans)},
            action_candidates=candidate_plans,
        )
        self._emit_event(
            ProviderEvent(
                provider=self.name,
                operation="policy",
                phase="success",
                duration_ms=0.1,
                metadata={"candidate_count": len(candidate_plans)},
            )
        )
        return result


def test_provider_benchmark_harness_reports_mock_operations(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    harness = ProviderBenchmarkHarness(forge=forge)

    report = harness.run(
        "mock",
        operations=["predict", "reason", "generate", "transfer", "embed"],
        iterations=2,
        concurrency=2,
    )

    assert len(report.results) == 5
    assert json.loads(report.to_json())["results"][0]["provider"] == "mock"
    assert report.to_csv().startswith("provider,operation,iterations")
    assert report.to_markdown().startswith("# Benchmark Report")
    for result in report.results:
        assert result.provider == "mock"
        assert result.success_count == 2
        assert result.error_count == 0
        assert result.retry_count == 0
        assert result.average_latency_ms is not None
        assert result.operation_metrics["provider"] == "mock"
        assert result.operation_metrics["events"]
    payload = json.loads(report.to_json())
    assert "adapter-path latency" in payload["claim_boundary"]
    assert "ProviderEvent" in payload["metric_semantics"]


def test_benchmark_report_evaluates_budget_gates(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    report = ProviderBenchmarkHarness(forge=forge).run(
        "mock",
        operations=["generate"],
        iterations=2,
    )

    passing = report.evaluate_budgets(
        [
            BenchmarkBudget(
                provider="mock",
                operation="generate",
                min_success_rate=1.0,
                max_error_count=0,
                max_retry_count=0,
                max_average_latency_ms=10_000.0,
                max_p95_latency_ms=10_000.0,
                min_throughput_per_second=0.0,
            )
        ]
    )

    assert passing.passed is True
    assert passing.checked_result_count == 1
    assert passing.to_markdown().startswith("# Benchmark Gate Report")
    assert passing.to_csv().startswith("provider,operation,metric")
    assert json.loads(passing.to_json())["passed"] is True

    failing = report.evaluate_budgets(
        [
            BenchmarkBudget(
                provider="mock",
                operation="generate",
                max_average_latency_ms=0.0,
            ),
            BenchmarkBudget(provider="mock", operation="policy", max_error_count=0),
        ]
    )

    assert failing.passed is False
    assert {violation.metric for violation in failing.violations} == {
        "average_latency_ms",
        "matching_results",
    }
    assert json.loads(failing.to_json())["violation_count"] == 2


def test_benchmark_result_contract_rejects_incoherent_public_payloads() -> None:
    result = BenchmarkResult(
        provider="mock",
        operation="generate",
        iterations=2,
        concurrency=1,
        success_count=1,
        error_count=1,
        retry_count=0,
        total_time_ms=2.0,
        average_latency_ms=1.0,
        min_latency_ms=0.5,
        max_latency_ms=1.5,
        p50_latency_ms=1.0,
        p95_latency_ms=1.45,
        throughput_per_second=0.5,
        operation_metrics={"events": []},
        errors=["simulated failure"],
    )

    assert result.to_dict()["operation"] == "generate"

    with pytest.raises(WorldForgeError, match="operation must be one of"):
        BenchmarkResult(
            provider="mock",
            operation="not-real",
            iterations=1,
            concurrency=1,
            success_count=1,
            error_count=0,
            retry_count=0,
            total_time_ms=1.0,
            average_latency_ms=1.0,
            min_latency_ms=1.0,
            max_latency_ms=1.0,
            p50_latency_ms=1.0,
            p95_latency_ms=1.0,
            throughput_per_second=1.0,
        )
    with pytest.raises(WorldForgeError, match="must sum to iterations"):
        BenchmarkResult(
            provider="mock",
            operation="generate",
            iterations=2,
            concurrency=1,
            success_count=2,
            error_count=1,
            retry_count=0,
            total_time_ms=1.0,
            average_latency_ms=1.0,
            min_latency_ms=1.0,
            max_latency_ms=1.0,
            p50_latency_ms=1.0,
            p95_latency_ms=1.0,
            throughput_per_second=1.0,
        )
    with pytest.raises(WorldForgeError, match="operation_metrics"):
        BenchmarkResult(
            provider="mock",
            operation="generate",
            iterations=1,
            concurrency=1,
            success_count=1,
            error_count=0,
            retry_count=0,
            total_time_ms=1.0,
            average_latency_ms=1.0,
            min_latency_ms=1.0,
            max_latency_ms=1.0,
            p50_latency_ms=1.0,
            p95_latency_ms=1.0,
            throughput_per_second=1.0,
            operation_metrics={"bad": object()},
        )
    with pytest.raises(WorldForgeError, match="errors length"):
        BenchmarkResult(
            provider="mock",
            operation="generate",
            iterations=1,
            concurrency=1,
            success_count=0,
            error_count=1,
            retry_count=0,
            total_time_ms=1.0,
            average_latency_ms=1.0,
            min_latency_ms=1.0,
            max_latency_ms=1.0,
            p50_latency_ms=1.0,
            p95_latency_ms=1.0,
            throughput_per_second=0.0,
            errors=[],
        )


def test_documented_benchmark_fixtures_load_and_pass_gate(tmp_path) -> None:
    input_file = ROOT / "examples" / "benchmark-inputs.json"
    budget_file = ROOT / "examples" / "benchmark-budget.json"
    inputs = load_benchmark_inputs(json.loads(input_file.read_text()), base_path=input_file.parent)
    budgets = load_benchmark_budgets(json.loads(budget_file.read_text()))
    forge = WorldForge(state_dir=tmp_path)

    report = ProviderBenchmarkHarness(forge=forge).run(
        "mock",
        operations=["predict", "embed", "generate"],
        iterations=1,
        inputs=inputs,
    )
    gate = report.evaluate_budgets(budgets)

    assert {result.operation for result in report.results} == {"predict", "embed", "generate"}
    assert gate.passed is True


def test_runway_benchmark_input_fixtures_are_separate_and_valid() -> None:
    generate_file = ROOT / "examples" / "runway-generate-benchmark-inputs.json"
    transfer_file = ROOT / "examples" / "runway-transfer-benchmark-inputs.json"

    generate_payload = json.loads(generate_file.read_text(encoding="utf-8"))
    transfer_payload = json.loads(transfer_file.read_text(encoding="utf-8"))
    generate_inputs = load_benchmark_inputs(generate_payload, base_path=generate_file.parent)
    transfer_inputs = load_benchmark_inputs(transfer_payload, base_path=transfer_file.parent)

    assert generate_payload["metadata"]["operation"] == "generate"
    assert transfer_payload["metadata"]["operation"] == "transfer"
    assert generate_inputs.generation_prompt.startswith("a calibrated robot arm")
    assert generate_inputs.generation_duration_seconds == 5.0
    assert transfer_inputs.transfer_prompt.startswith("rerender the clip")
    assert transfer_inputs.transfer_clip.content_type() == "video/mp4"


def test_load_benchmark_budgets_accepts_list_or_object_payload() -> None:
    loaded = load_benchmark_budgets(
        {
            "budgets": [
                {
                    "provider": "mock",
                    "operation": "generate",
                    "min_success_rate": 1.0,
                    "max_error_count": 0,
                }
            ]
        }
    )

    assert loaded == [
        BenchmarkBudget(
            provider="mock",
            operation="generate",
            min_success_rate=1.0,
            max_error_count=0,
        )
    ]
    assert load_benchmark_budgets([{"max_retry_count": 0}]) == [BenchmarkBudget(max_retry_count=0)]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "non-empty 'budgets' list"),
        ([], "non-empty list"),
        ({"budgets": [{"max_error_count": 0}], "unexpected": True}, "unknown key"),
        ([{"operation": "not-real", "max_error_count": 0}], "operation must be one of"),
        ([{"provider": "", "max_error_count": 0}], "provider must be a non-empty string"),
        ([{"provider": "mock"}], "requires at least one threshold"),
        ([{"max_error_count": -1}], "max_error_count must be an integer"),
        ([{"max_error_count": 0, "max_erorr_count": 0}], "unknown key"),
    ],
)
def test_load_benchmark_budgets_rejects_invalid_payloads(
    payload: object,
    message: str,
) -> None:
    with pytest.raises(WorldForgeError, match=message):
        load_benchmark_budgets(payload)


def test_provider_benchmark_harness_reports_score_and_policy_operations(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    score_provider = _ScoreBenchmarkProvider()
    policy_provider = _PolicyBenchmarkProvider()
    forge.register_provider(score_provider)
    forge.register_provider(policy_provider)
    harness = ProviderBenchmarkHarness(forge=forge)

    report = harness.run(["scorebench", "policybench"], iterations=2)

    assert [(result.provider, result.operation) for result in report.results] == [
        ("scorebench", "score"),
        ("policybench", "policy"),
    ]
    for result in report.results:
        assert result.success_count == 2
        assert result.error_count == 0
        assert result.operation_metrics["events"][0]["operation"] == result.operation

    assert score_provider.calls[0]["info"]["metadata"]["mode"] == "benchmark-score"
    assert policy_provider.calls[0]["observation"]["language"] == "move the cube toward the target"


class _TensorLikeCandidates:
    shape = (1, 2, 2, 3)


def test_benchmark_inputs_preview_provider_native_score_candidates() -> None:
    inputs = BenchmarkInputs(score_action_candidates=_TensorLikeCandidates())

    payload = inputs.to_dict()

    assert payload["score_action_candidates"] == {
        "type": f"{_TensorLikeCandidates.__module__}.{_TensorLikeCandidates.__qualname__}",
        "json_serializable": False,
        "shape": [1, 2, 2, 3],
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"prediction_action": {"type": "move_to"}}, "prediction_action must be an Action"),
        ({"embedding_text": ""}, "embedding_text must be a non-empty string"),
        ({"score_info": {}}, "score_info must be a non-empty JSON object"),
        ({"score_action_candidates": None}, "score_action_candidates must not be None"),
        ({"policy_info": []}, "policy_info must be a non-empty JSON object"),
        ({"transfer_clip": {}}, "transfer_clip must be a VideoClip"),
    ],
)
def test_benchmark_inputs_validate_planning_surface_inputs(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(WorldForgeError, match=message):
        BenchmarkInputs(**kwargs)


def test_load_benchmark_inputs_accepts_fixture_payload_and_relative_clip(tmp_path) -> None:
    clip_path = tmp_path / "seed.bin"
    clip_path.write_bytes(b"transfer-seed")

    inputs = load_benchmark_inputs(
        {
            "metadata": {"fixture": "unit"},
            "inputs": {
                "prediction_action": {
                    "type": "move_to",
                    "parameters": {
                        "target": {"x": 0.4, "y": 0.5, "z": 0.0},
                        "speed": 0.75,
                        "object_id": "cube",
                    },
                },
                "prediction_steps": 3,
                "reason_query": "fixture query",
                "generation_prompt": "fixture generation",
                "generation_duration_seconds": 1.5,
                "transfer_prompt": "fixture transfer",
                "transfer_width": 640,
                "transfer_height": 360,
                "transfer_fps": 24.0,
                "transfer_clip": {
                    "path": "seed.bin",
                    "fps": 6.0,
                    "resolution": [80, 45],
                    "duration_seconds": 0.5,
                    "metadata": {"fixture": "clip"},
                },
                "embedding_text": "fixture embedding",
                "score_info": {"observation": [[0.0]], "goal": [[1.0]]},
                "score_action_candidates": [[[[0.0]], [[1.0]]]],
                "policy_info": {"observation": {"language": "fixture"}, "mode": "select_action"},
            },
        },
        base_path=tmp_path,
    )

    assert inputs.prediction_action.parameters["object_id"] == "cube"
    assert inputs.prediction_steps == 3
    assert inputs.reason_query == "fixture query"
    assert inputs.generation_prompt == "fixture generation"
    assert inputs.transfer_width == 640
    assert inputs.transfer_height == 360
    assert inputs.transfer_clip.blob() == b"transfer-seed"
    assert inputs.transfer_clip.fps == 6.0
    assert inputs.transfer_clip.resolution == (80, 45)
    assert inputs.embedding_text == "fixture embedding"
    assert inputs.score_info["goal"] == [[1.0]]
    assert inputs.score_action_candidates == [[[[0.0]], [[1.0]]]]
    assert inputs.policy_info["mode"] == "select_action"


def test_load_benchmark_inputs_accepts_inline_base64_transfer_frames() -> None:
    inputs = load_benchmark_inputs(
        {
            "transfer_clip": {
                "frames_base64": [
                    b64encode(b"frame-a").decode("ascii"),
                    b64encode(b"frame-b").decode("ascii"),
                ],
                "fps": 10.0,
                "resolution": [100, 50],
                "duration_seconds": 0.2,
            }
        }
    )

    assert inputs.transfer_clip.frames == [b"frame-a", b"frame-b"]
    assert inputs.transfer_clip.resolution == (100, 50)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not an object", "Benchmark input payload must be a JSON object"),
        ({}, "at least one input field"),
        ({"inputs": {}, "extra": True}, "Unknown benchmark input wrapper fields"),
        ({"unknown": True}, "Unknown benchmark input fields"),
        ({"prediction_action": []}, "prediction_action must be a JSON object"),
        ({"reason_query": ""}, "reason_query must be a non-empty string"),
        ({"generation_duration_seconds": 0}, "generation_duration_seconds must be greater"),
        ({"transfer_width": True}, "transfer_width must be an integer"),
        ({"transfer_clip": []}, "transfer_clip must be a JSON object"),
        (
            {"transfer_clip": {"frames_base64": ["Zm9v"], "unknown": True}},
            "Unknown transfer_clip fields",
        ),
        ({"transfer_clip": {"frames_base64": []}}, "frames_base64 must be a non-empty list"),
        ({"transfer_clip": {"frames_base64": [""]}}, "must be a non-empty base64 string"),
        (
            {"transfer_clip": {"path": "missing.bin", "frames_base64": ["Zm9v"]}},
            "exactly one of 'path' or 'frames_base64'",
        ),
        ({"transfer_clip": {"frames_base64": ["not base64"]}}, "valid base64 bytes"),
        (
            {"transfer_clip": {"frames_base64": ["Zm9v"], "duration_seconds": -1}},
            "duration_seconds must be greater",
        ),
        (
            {"transfer_clip": {"frames_base64": ["Zm9v"], "metadata": []}},
            "metadata must be a JSON object",
        ),
        ({"transfer_clip": {"frames_base64": ["Zm9v"], "resolution": [0, 50]}}, "greater"),
        ({"score_info": []}, "score_info must be a non-empty JSON object"),
        ({"score_action_candidates": float("nan")}, "finite numbers"),
    ],
)
def test_load_benchmark_inputs_rejects_invalid_payloads(
    payload: object,
    message: str,
) -> None:
    with pytest.raises(WorldForgeError, match=message):
        load_benchmark_inputs(payload)


def test_provider_benchmark_harness_uses_custom_score_and_policy_inputs(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    score_provider = _ScoreBenchmarkProvider()
    policy_provider = _PolicyBenchmarkProvider()
    forge.register_provider(score_provider)
    forge.register_provider(policy_provider)
    inputs = load_benchmark_inputs(
        {
            "score_info": {
                "pixels": [[[[1.0]]]],
                "goal": [[[0.1, 0.2, 0.3]]],
                "action": [[[0.0, 0.0, 0.0]]],
                "metadata": {"fixture": "custom"},
            },
            "score_action_candidates": [[[[0.1, 0.2, 0.3]], [[0.4, 0.5, 0.6]]]],
            "policy_info": {
                "observation": {"state": {"object": [1.0, 2.0, 3.0]}, "language": "custom"},
                "mode": "select_action",
            },
        }
    )

    ProviderBenchmarkHarness(forge=forge).run(
        ["scorebench", "policybench"],
        iterations=1,
        inputs=inputs,
    )

    assert score_provider.calls == [
        {
            "info": inputs.score_info,
            "action_candidates": inputs.score_action_candidates,
        }
    ]
    assert policy_provider.calls == [inputs.policy_info]


def test_provider_benchmark_harness_captures_retry_metrics(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RUNWAYML_API_SECRET", "runway-test-key")
    attempts = {"poll": 0, "download": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/image_to_video":
            return httpx.Response(200, json={"id": "task_generate"})

        if request.method == "GET" and request.url.path == "/v1/tasks/task_generate":
            attempts["poll"] += 1
            if attempts["poll"] == 1:
                return httpx.Response(503, text="retry poll")
            return httpx.Response(
                200,
                json={
                    "id": "task_generate",
                    "status": "SUCCEEDED",
                    "output": ["https://downloads.example.com/generated.mp4"],
                },
            )

        if request.method == "GET" and request.url.host == "downloads.example.com":
            attempts["download"] += 1
            if attempts["download"] == 1:
                return httpx.Response(503, text="retry download")
            return httpx.Response(200, content=b"benchmark-generated")

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(
        RunwayProvider(
            request_policy=ProviderRequestPolicy.remote_defaults(
                request_timeout_seconds=30.0,
                read_retry_attempts=2,
                read_backoff_seconds=0.0,
            ),
            transport=httpx.MockTransport(handler),
            poll_interval_seconds=0.0,
            max_polls=1,
        )
    )

    report = ProviderBenchmarkHarness(forge=forge).run(
        "runway",
        operations=["generate"],
        iterations=1,
    )

    result = report.results[0]
    assert result.provider == "runway"
    assert result.operation == "generate"
    assert result.success_count == 1
    assert result.error_count == 0
    assert result.retry_count == 2
    emitted_operations = {event["operation"] for event in result.operation_metrics["events"]}
    assert emitted_operations == {
        "generation request",
        "task poll",
        "artifact download",
    }


def test_provider_benchmark_harness_rejects_unsupported_operations(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(CosmosProvider(base_url="http://cosmos.test"))
    harness = ProviderBenchmarkHarness(forge=forge)

    with pytest.raises(WorldForgeError, match="unsupported operations: transfer"):
        harness.run("cosmos", operations=["transfer"], iterations=1)


def test_provider_benchmark_harness_rejects_unknown_invoke_operation(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    harness = ProviderBenchmarkHarness(forge=forge)

    with pytest.raises(WorldForgeError, match="Unknown benchmark operation"):
        harness._invoke_operation("mock", "not-a-real-op", BenchmarkInputs())


def test_provider_benchmark_harness_records_provider_error_samples(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    harness = ProviderBenchmarkHarness(forge=forge)

    def _boom(provider: str, inputs: BenchmarkInputs) -> None:
        raise ProviderError("simulated provider outage")

    # Swap the predict handler so the narrowed except branch fires without an outbound call.
    harness._operation_handlers["predict"] = _boom

    report = harness.run("mock", operations=["predict"], iterations=2, concurrency=1)
    result = report.results[0]
    assert result.success_count == 0
    assert result.error_count == 2
    assert result.average_latency_ms is None
    assert result.p95_latency_ms is None
    assert all("simulated provider outage" in message for message in result.errors)

    gate = report.evaluate_budgets(
        [BenchmarkBudget(provider="mock", operation="predict", max_average_latency_ms=1.0)]
    )
    assert gate.passed is False
    assert gate.violations[0].metric == "average_latency_ms"
    assert gate.violations[0].observed is None


def test_provider_benchmark_harness_propagates_unexpected_exceptions(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    harness = ProviderBenchmarkHarness(forge=forge)

    class _UnexpectedError(Exception):
        pass

    def _boom(provider: str, inputs: BenchmarkInputs) -> None:
        raise _UnexpectedError("this must propagate")

    harness._operation_handlers["predict"] = _boom

    with pytest.raises(_UnexpectedError, match="this must propagate"):
        harness.run("mock", operations=["predict"], iterations=1, concurrency=1)
