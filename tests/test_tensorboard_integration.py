from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

import worldforge.tensorboard as tensorboard_module
from worldforge.models import ProviderEvent, WorldForgeError
from worldforge.tensorboard import (
    TensorBoardCheckpointInspector,
    TensorBoardLogConfig,
    TensorBoardSession,
    create_tensorboard_inspector,
    default_run_name,
)


class _FakeSummaryWriter:
    """In-memory stand-in for ``torch.utils.tensorboard.SummaryWriter``."""

    def __init__(
        self,
        *,
        log_dir: str,
        flush_secs: int = 30,
        max_queue: int = 10,
        filename_suffix: str = "",
        purge_step: int | None = None,
    ) -> None:
        self.log_dir = log_dir
        self.flush_secs = flush_secs
        self.max_queue = max_queue
        self.filename_suffix = filename_suffix
        self.purge_step = purge_step
        self.scalars: list[tuple[str, float, int]] = []
        self.texts: list[tuple[str, str, int]] = []
        self.histograms: list[tuple[str, Any, int, str | int]] = []
        self.closed = False
        self.flushes = 0

    def add_scalar(self, tag: str, value: float, step: int) -> None:
        self.scalars.append((tag, float(value), int(step)))

    def add_text(self, tag: str, text: str, step: int) -> None:
        self.texts.append((tag, text, int(step)))

    def add_histogram(self, tag: str, values: Any, step: int, *, bins: str | int = "auto") -> None:
        self.histograms.append((tag, values, int(step), bins))

    def flush(self) -> None:
        self.flushes += 1

    def close(self) -> None:
        self.closed = True


def _factory(captured: list[_FakeSummaryWriter]) -> Any:
    def _build(**kwargs: Any) -> _FakeSummaryWriter:
        writer = _FakeSummaryWriter(**kwargs)
        captured.append(writer)
        return writer

    return _build


def _inspector(
    tmp_path: Path, captured: list[_FakeSummaryWriter] | None = None
) -> tuple[TensorBoardCheckpointInspector, list[_FakeSummaryWriter]]:
    captured = captured if captured is not None else []
    config = TensorBoardLogConfig(log_dir=tmp_path, run_name="unit")
    session = TensorBoardSession(config=config, sdk=_factory(captured))
    inspector = TensorBoardCheckpointInspector(session=session)
    return inspector, captured


def test_log_config_validates_inputs(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="log_dir must be a string or Path"):
        TensorBoardLogConfig(log_dir=42)  # type: ignore[arg-type]

    with pytest.raises(WorldForgeError, match="run_name must be a non-empty string"):
        TensorBoardLogConfig(log_dir=tmp_path, run_name="   ")

    with pytest.raises(WorldForgeError, match="flush_secs must be a positive integer"):
        TensorBoardLogConfig(log_dir=tmp_path, flush_secs=0)

    with pytest.raises(WorldForgeError, match="max_queue must be a positive integer"):
        TensorBoardLogConfig(log_dir=tmp_path, max_queue=0)

    with pytest.raises(WorldForgeError, match="filename_suffix must be a string"):
        TensorBoardLogConfig(log_dir=tmp_path, filename_suffix=12)  # type: ignore[arg-type]

    with pytest.raises(WorldForgeError, match="purge_step must be a non-negative integer"):
        TensorBoardLogConfig(log_dir=tmp_path, purge_step=-1)

    with pytest.raises(WorldForgeError, match="write_to_disk must be a boolean"):
        TensorBoardLogConfig(log_dir=tmp_path, write_to_disk="yes")  # type: ignore[arg-type]


def test_log_config_resolved_log_dir_includes_run_name(tmp_path: Path) -> None:
    base = TensorBoardLogConfig(log_dir=tmp_path)
    assert base.resolved_log_dir == tmp_path

    nested = TensorBoardLogConfig(log_dir=tmp_path, run_name="run-001")
    assert nested.resolved_log_dir == tmp_path / "run-001"


def test_session_initializes_writer_lazily_and_creates_directory(tmp_path: Path) -> None:
    captured: list[_FakeSummaryWriter] = []
    config = TensorBoardLogConfig(log_dir=tmp_path, run_name="run-x", flush_secs=15)
    session = TensorBoardSession(config=config, sdk=_factory(captured))

    assert captured == []
    assert not (tmp_path / "run-x").exists()

    session.start()
    session.start()  # idempotent
    session.close()
    session.close()

    assert len(captured) == 1
    writer = captured[0]
    assert writer.log_dir == str(tmp_path / "run-x")
    assert writer.flush_secs == 15
    assert (tmp_path / "run-x").is_dir()
    assert writer.closed is True
    assert writer.flushes >= 1


def test_session_skips_directory_creation_when_disabled(tmp_path: Path) -> None:
    captured: list[_FakeSummaryWriter] = []
    config = TensorBoardLogConfig(
        log_dir=tmp_path / "nope",
        run_name="run-y",
        write_to_disk=False,
    )
    session = TensorBoardSession(config=config, sdk=_factory(captured))

    session.start()
    assert not (tmp_path / "nope" / "run-y").exists()


def test_session_reports_missing_optional_extra(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def missing_import(name: str) -> object:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(tensorboard_module, "import_module", missing_import)
    session = TensorBoardSession(config=TensorBoardLogConfig(log_dir=tmp_path))

    with pytest.raises(WorldForgeError, match="optional 'tensorboard' extra"):
        session.start()


def test_session_uses_tensorboardx_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[_FakeSummaryWriter] = []
    fake_module = type("FakeTBX", (), {"SummaryWriter": _factory(captured)})

    def import_first_match(name: str) -> object:
        if name == "torch.utils.tensorboard":
            raise ModuleNotFoundError(name)
        if name == "tensorboardX":
            return fake_module
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(tensorboard_module, "import_module", import_first_match)

    session = TensorBoardSession(config=TensorBoardLogConfig(log_dir=tmp_path, run_name="tbx"))
    session.start()
    assert len(captured) == 1


def test_session_rejects_missing_summary_writer_class(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_module = type("EmptyTB", (), {})

    def import_returns_empty(name: str) -> object:
        if name == "torch.utils.tensorboard":
            return fake_module
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(tensorboard_module, "import_module", import_returns_empty)
    session = TensorBoardSession(config=TensorBoardLogConfig(log_dir=tmp_path))

    with pytest.raises(WorldForgeError, match="missing the SummaryWriter class"):
        session.start()


def test_inspector_validates_namespace(tmp_path: Path) -> None:
    config = TensorBoardLogConfig(log_dir=tmp_path)
    session = TensorBoardSession(config=config, sdk=_factory([]))

    with pytest.raises(WorldForgeError, match="namespace must be a non-empty string"):
        TensorBoardCheckpointInspector(session=session, namespace="")

    with pytest.raises(WorldForgeError, match="namespace must contain at least one"):
        TensorBoardCheckpointInspector(session=session, namespace="///")

    with pytest.raises(WorldForgeError, match="namespace must not contain reserved"):
        TensorBoardCheckpointInspector(session=session, namespace="__reserved")

    with pytest.raises(WorldForgeError, match="default_step must be a non-negative integer"):
        TensorBoardCheckpointInspector(session=session, default_step=-1)


def test_inspector_log_methods_sanitize_and_dispatch(tmp_path: Path) -> None:
    inspector, captured = _inspector(tmp_path)

    inspector.log_text("greeting", "hello world api_key=supersecret")
    inspector.log_text(
        "links",
        "open https://example.com/path?signature=abc&other=keep",
    )
    inspector.log_json("payload", {"alpha": 1, "beta": [1, 2, 3]})
    inspector.log_scalar("metrics/latency_ms", 12.5)
    inspector.log_scalar("metrics/latency_ms", float("nan"))  # silently dropped
    inspector.log_histogram("scores/values", [0.1, 0.2, 0.3, float("nan")])
    inspector.log_histogram("scores/empty", [float("nan")])  # silently dropped
    inspector.log_metrics({"plan_latency_ms": 25.0, "skip_me": "not numeric"})

    writer = captured[0]
    texts = {tag: body for tag, body, _ in writer.texts}
    assert "worldforge/leworldmodel/greeting" in texts
    assert "api_key=[REDACTED]" in texts["worldforge/leworldmodel/greeting"]
    assert "supersecret" not in texts["worldforge/leworldmodel/greeting"]
    assert "signature=[REDACTED]" in texts["worldforge/leworldmodel/links"]
    assert "alpha" in texts["worldforge/leworldmodel/payload"]
    assert any(
        tag == "worldforge/leworldmodel/metrics/latency_ms" and math.isclose(value, 12.5)
        for tag, value, _ in writer.scalars
    )
    assert all(value == value for _tag, value, _ in writer.scalars)  # no NaN survives
    assert any(tag == "worldforge/leworldmodel/scores/values" for tag, *_ in writer.histograms)
    assert not any(tag == "worldforge/leworldmodel/scores/empty" for tag, *_ in writer.histograms)
    assert any(
        tag == "worldforge/leworldmodel/metrics/plan_latency_ms"
        for tag, _value, _step in writer.scalars
    )


def test_inspector_text_requires_string_and_metrics_mapping(tmp_path: Path) -> None:
    inspector, _ = _inspector(tmp_path)

    with pytest.raises(WorldForgeError, match="text must be a string"):
        inspector.log_text("tag", 42)  # type: ignore[arg-type]

    with pytest.raises(WorldForgeError, match="metrics must be a mapping"):
        inspector.log_metrics([("a", 1)])  # type: ignore[arg-type]


def test_inspector_log_checkpoint_summary(tmp_path: Path) -> None:
    inspector, captured = _inspector(tmp_path)

    inspector.log_checkpoint_summary(
        {
            "created": True,
            "output": "/tmp/lewm/pusht/lewm_object.ckpt",
            "policy": "pusht/lewm",
            "repo_id": "galilai/lewm-pusht",
            "revision": "abc123",
        }
    )
    writer = captured[0]
    tags = {tag for tag, *_ in writer.texts}
    assert "worldforge/leworldmodel/checkpoint/provenance" in tags
    assert "worldforge/leworldmodel/checkpoint/path" in tags
    assert "worldforge/leworldmodel/checkpoint/revision" in tags
    assert "worldforge/leworldmodel/checkpoint/repo" in tags
    assert "worldforge/leworldmodel/checkpoint/policy" in tags
    scalar_tags = {tag for tag, *_ in writer.scalars}
    assert "worldforge/leworldmodel/checkpoint/created" in scalar_tags


def test_inspector_log_provider_event_emits_scalars_and_text(tmp_path: Path) -> None:
    inspector, captured = _inspector(tmp_path)

    inspector.log_provider_event(
        ProviderEvent(
            provider="leworldmodel",
            operation="score",
            phase="success",
            duration_ms=12.3,
            status_code=200,
            attempt=2,
            max_attempts=3,
            message="ok",
        )
    )
    inspector.log_provider_event(
        ProviderEvent(
            provider="leworldmodel",
            operation="score",
            phase="failure",
        )
    )

    writer = captured[0]
    tags = {tag for tag, *_ in writer.scalars}
    assert "worldforge/leworldmodel/events/leworldmodel/score/duration_ms" in tags
    assert "worldforge/leworldmodel/events/leworldmodel/score/failure" in tags
    failure_values = [
        value
        for tag, value, _ in writer.scalars
        if tag == "worldforge/leworldmodel/events/leworldmodel/score/failure"
    ]
    assert failure_values[-1] == 1.0

    with pytest.raises(WorldForgeError, match="log_provider_event accepts ProviderEvent only"):
        inspector.log_provider_event("oops")  # type: ignore[arg-type]


def test_inspector_log_score_distribution_emits_histogram_and_stats(tmp_path: Path) -> None:
    inspector, captured = _inspector(tmp_path)

    inspector.log_score_distribution(
        [0.4, 0.1, 0.6, float("inf"), 0.2],
        best_index=1,
        best_score=0.1,
    )

    writer = captured[0]
    candidate_tags = sorted(tag for tag, *_ in writer.scalars if "/scores/candidate_" in tag)
    assert len(candidate_tags) == 4
    summary_tags = {tag for tag, *_ in writer.scalars}
    assert "worldforge/leworldmodel/scores/min" in summary_tags
    assert "worldforge/leworldmodel/scores/max" in summary_tags
    assert "worldforge/leworldmodel/scores/mean" in summary_tags
    assert "worldforge/leworldmodel/scores/best_index" in summary_tags
    assert "worldforge/leworldmodel/scores/best_score" in summary_tags
    histogram_tags = {tag for tag, *_ in writer.histograms}
    assert "worldforge/leworldmodel/scores/cost_distribution" in histogram_tags


def test_inspector_log_robotics_showcase_summary_dispatches_all_panels(
    tmp_path: Path,
) -> None:
    inspector, captured = _inspector(tmp_path)
    summary = {
        "task": "PushT policy+world-model planning",
        "checkpoint_display": "~/lewm/pusht/lewm_object.ckpt",
        "checkpoint": "/tmp/lewm/pusht/lewm_object.ckpt",
        "state_dir": "/tmp/state",
        "inputs": {"score_action_candidates_shape": [3, 8, 2]},
        "health": {"lerobot": {"healthy": True}},
        "score_result": {
            "scores": [0.5, 0.4, 0.6],
            "best_index": 1,
            "best_score": 0.4,
        },
        "score_stats": {
            "score_min": 0.4,
            "score_max": 0.6,
            "score_mean": 0.5,
            "score_median": 0.5,
            "score_range": 0.2,
            "gap_to_runner_up": 0.1,
        },
        "metrics": {"plan_latency_ms": 25.0, "total_latency_ms": 30.0},
        "provider_events": [
            {
                "provider": "lerobot",
                "operation": "policy",
                "phase": "success",
                "attempt": 1,
                "max_attempts": 1,
                "duration_ms": 11.0,
            },
            "not an event",  # tolerated silently
            {"provider": "missing fields"},  # invalid, tolerated silently
        ],
    }
    inspector.log_robotics_showcase_summary(summary)

    writer = captured[0]
    text_tags = {tag for tag, *_ in writer.texts}
    assert "worldforge/leworldmodel/robotics_showcase/summary" in text_tags
    assert "worldforge/leworldmodel/robotics_showcase/task" in text_tags
    assert "worldforge/leworldmodel/robotics_showcase/inputs" in text_tags
    assert "worldforge/leworldmodel/robotics_showcase/health" in text_tags
    scalar_tags = {tag for tag, *_ in writer.scalars}
    assert "worldforge/leworldmodel/scores/best_index" in scalar_tags
    assert "worldforge/leworldmodel/metrics/score_mean" in scalar_tags
    assert "worldforge/leworldmodel/metrics/plan_latency_ms" in scalar_tags
    assert "worldforge/leworldmodel/events/lerobot/policy/duration_ms" in scalar_tags


def test_inspector_state_dict_histograms(tmp_path: Path) -> None:
    class _TensorStub:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def detach(self) -> _TensorStub:
            return self

        def cpu(self) -> _TensorStub:
            return self

        def numpy(self) -> list[float]:
            return self._values

    inspector, captured = _inspector(tmp_path)
    logged = inspector.log_state_dict_histograms(
        {
            "encoder.layer.0.weight": _TensorStub([0.1, -0.2, 0.05]),
            "encoder.layer.0.bias": _TensorStub([0.0, 0.1]),
            "metadata.note": "non-tensor entry",
        }
    )
    assert logged == 2
    writer = captured[0]
    histogram_tags = {tag for tag, *_ in writer.histograms}
    assert "worldforge/leworldmodel/weights/encoder.layer.0.weight" in histogram_tags
    assert "worldforge/leworldmodel/weights/encoder.layer.0.bias" in histogram_tags

    with pytest.raises(WorldForgeError, match="state_dict must be a mapping"):
        inspector.log_state_dict_histograms([("encoder", _TensorStub([0.0]))])  # type: ignore[arg-type]


def test_inspector_state_dict_histograms_tolerates_broken_tensor(tmp_path: Path) -> None:
    class _BadTensor:
        def detach(self) -> _BadTensor:
            return self

        def cpu(self) -> _BadTensor:
            return self

        def numpy(self) -> list[float]:
            raise RuntimeError("backend missing")

    inspector, captured = _inspector(tmp_path)
    logged = inspector.log_state_dict_histograms({"weights.bad": _BadTensor()})
    assert logged == 0
    # Broken tensor short-circuits before the writer is initialized.
    assert captured == [] or captured[0].histograms == []


def test_create_inspector_helper_and_default_run_name(tmp_path: Path) -> None:
    captured: list[_FakeSummaryWriter] = []
    inspector = create_tensorboard_inspector(
        log_dir=tmp_path,
        run_name=default_run_name(prefix="unit-test"),
        flush_secs=5,
        sdk=_factory(captured),
    )
    inspector.log_scalar("metrics/test", 1.0)
    inspector.flush()
    inspector.close()
    assert captured[0].flush_secs == 5
    assert captured[0].closed is True


def test_inspector_handles_unfinite_scalars_and_nonnumeric_metrics(tmp_path: Path) -> None:
    inspector, captured = _inspector(tmp_path)
    inspector.log_scalar("metrics/inf", float("inf"))
    inspector.log_scalar("metrics/string", "not a number")  # type: ignore[arg-type]
    # Non-finite scalars are silently dropped before initializing the writer.
    assert captured == [] or captured[0].scalars == []


def test_log_histogram_with_tensor_like_values(tmp_path: Path) -> None:
    class _Tensor:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def detach(self) -> _Tensor:
            return self

        def cpu(self) -> _Tensor:
            return self

        def numpy(self) -> list[float]:
            return self._values

    inspector, captured = _inspector(tmp_path)
    inspector.log_histogram("scores/tensor", _Tensor([1.0, 2.0, 3.0]))
    assert len(captured[0].histograms) == 1
    assert captured[0].histograms[0][0] == "worldforge/leworldmodel/scores/tensor"


def test_log_histogram_skips_non_iterable_values(tmp_path: Path) -> None:
    inspector, captured = _inspector(tmp_path)
    inspector.log_histogram("scores/scalar", 42)  # type: ignore[arg-type]
    inspector.log_histogram("scores/string", "not iterable")
    assert captured == [] or captured[0].histograms == []


def test_log_json_rejects_unserializable_payload(tmp_path: Path) -> None:
    inspector, _ = _inspector(tmp_path)
    with pytest.raises(WorldForgeError):
        inspector.log_json("bad", {"value": float("inf")})
