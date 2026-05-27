"""Optional TensorBoard bridge for LeWorldModel checkpoint inspection.

This module mirrors the optional-runtime shape of :mod:`worldforge.rerun`: the
TensorBoard SDK is imported lazily so the base WorldForge install never pulls in
``tensorboard`` or ``torch``. Hosts that want to inspect a LeWorldModel checkpoint
during the robotics showcase install the optional extra and pass a configured
:class:`TensorBoardSession` (or let the showcase wire one for them).

The bridge is intentionally narrow: it logs provenance text, latency and cost
scalars, a histogram of candidate-action costs, and a per-event text feed. It
does not own any torch tensors or model graphs by itself — when the host
already has live tensors (e.g. a loaded ``stable_worldmodel`` checkpoint), it
can pass them through :meth:`TensorBoardCheckpointInspector.log_state_dict_histograms`
to surface per-parameter weight distributions. The bridge is a no-op when the
optional ``tensorboard`` extra is missing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import Any

from worldforge.models import (
    JSONDict,
    ProviderEvent,
    WorldForgeError,
    _redact_observable_text,
    require_json_dict,
)

_DEFAULT_NAMESPACE = "worldforge/leworldmodel"
_TAG_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9_.\-/]+")


def _require_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _require_optional_text(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, name=name)


def _require_non_negative_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorldForgeError(f"{name} must be a non-negative integer.")
    return value


def _require_positive_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorldForgeError(f"{name} must be a positive integer.")
    return value


def _tag_segment(value: object, *, fallback: str = "item") -> str:
    text = str(value).strip().strip("/")
    if not text:
        return fallback
    segment = _TAG_SEGMENT_PATTERN.sub("_", text).strip("._-")
    if not segment or segment.startswith("__"):
        return fallback
    return segment


def _join_tag(namespace: str, *segments: object) -> str:
    cleaned = [_tag_segment(namespace, fallback="worldforge")]
    for segment in segments:
        raw = str(segment).strip("/")
        if not raw:
            cleaned.append(_tag_segment(segment))
            continue
        cleaned.extend(_tag_segment(part) for part in raw.split("/") if part)
    return "/".join(cleaned)


def _validate_namespace(value: object, *, name: str) -> str:
    text = _require_text(value, name=name).strip("/")
    if not text:
        raise WorldForgeError(f"{name} must contain at least one tag segment.")
    parts = text.split("/")
    if any(part.strip().startswith("__") for part in parts):
        raise WorldForgeError(f"{name} must not contain reserved tag segments.")
    cleaned = [_tag_segment(part) for part in parts]
    return "/".join(cleaned)


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _sanitize_text(value: str) -> str:
    return _redact_observable_text(value).replace("[redacted]", "[REDACTED]")


def _pretty_json(payload: JSONDict) -> str:
    try:
        return json.dumps(payload, sort_keys=True, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorldForgeError(
            "TensorBoard text payloads must be JSON-serializable and contain only finite numbers."
        ) from exc


def _markdown_text(text: str) -> str:
    sanitized = _sanitize_text(text)
    return f"```\n{sanitized}\n```"


def _load_summary_writer_class(sdk: object | None) -> Any:
    """Return a callable that constructs a SummaryWriter-like object.

    ``sdk`` may be either a class/callable returning a writer (used in tests)
    or ``None`` (the production path that imports torch.utils.tensorboard).
    """

    if sdk is not None:
        return sdk
    try:
        module = import_module("torch.utils.tensorboard")
    except ModuleNotFoundError:
        try:
            module = import_module("tensorboardX")
        except ModuleNotFoundError as exc:
            raise WorldForgeError(
                "TensorBoard integration requires the optional 'tensorboard' extra. Install with "
                "`pip install 'worldforge-ai[tensorboard]'` or install `tensorboard` (and "
                "`torch.utils.tensorboard` or `tensorboardX`) in the host environment."
            ) from exc
    writer_cls = getattr(module, "SummaryWriter", None)
    if writer_cls is None:
        raise WorldForgeError(
            "TensorBoard module is missing the SummaryWriter class; install a supported "
            "tensorboard or tensorboardX release."
        )
    return writer_cls


def _try_load_numpy() -> Any | None:
    try:
        return import_module("numpy")
    except ModuleNotFoundError:
        return None


def _call_if_present(target: object, name: str, *args: object, **kwargs: object) -> object | None:
    method = getattr(target, name, None)
    if method is None:
        return None
    return method(*args, **kwargs)


def _is_tensor_like(value: object) -> bool:
    return all(
        callable(getattr(value, attr, None)) for attr in ("detach", "cpu", "numpy")
    ) and not isinstance(value, dict | list | tuple | str | bytes)


@dataclass(slots=True)
class TensorBoardLogConfig:
    """Configuration for a TensorBoard recording.

    The recording is local-only: ``log_dir`` (combined with the optional
    ``run_name`` subdirectory) is the destination for ``tfevents`` files. The
    integration never uploads logs to a hosted service.
    """

    log_dir: str | Path
    run_name: str | None = None
    flush_secs: int = 30
    max_queue: int = 10
    filename_suffix: str = ""
    purge_step: int | None = None
    write_to_disk: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.log_dir, str | Path):
            raise WorldForgeError("log_dir must be a string or Path.")
        path = Path(self.log_dir).expanduser()
        if not str(path):
            raise WorldForgeError("log_dir must not be empty.")
        self.log_dir = path
        self.run_name = _require_optional_text(self.run_name, name="run_name")
        self.flush_secs = _require_positive_int(self.flush_secs, name="flush_secs")
        self.max_queue = _require_positive_int(self.max_queue, name="max_queue")
        if not isinstance(self.filename_suffix, str):
            raise WorldForgeError("filename_suffix must be a string.")
        if self.purge_step is not None:
            self.purge_step = _require_non_negative_int(self.purge_step, name="purge_step")
        if not isinstance(self.write_to_disk, bool):
            raise WorldForgeError("write_to_disk must be a boolean.")

    @property
    def resolved_log_dir(self) -> Path:
        """Return the final on-disk directory (``log_dir/run_name`` if set)."""

        base = Path(self.log_dir).expanduser()
        if self.run_name:
            return base / self.run_name
        return base


@dataclass(slots=True)
class TensorBoardSession:
    """Lazy TensorBoard ``SummaryWriter`` session.

    The optional SDK is loaded on the first call to :meth:`start`; constructing
    a :class:`TensorBoardSession` is free of side effects, which keeps the
    base import path light and matches the Rerun bridge contract.
    """

    config: TensorBoardLogConfig
    sdk: object | None = None
    _writer: object | None = field(default=None, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    @property
    def log_dir(self) -> Path:
        return self.config.resolved_log_dir

    def start(self) -> TensorBoardSession:
        """Initialize the SummaryWriter and create the log directory."""

        with self._lock:
            if self._started:
                return self
            writer_cls = _load_summary_writer_class(self.sdk)
            target = self.config.resolved_log_dir
            if self.config.write_to_disk:
                target.mkdir(parents=True, exist_ok=True)
            writer = writer_cls(
                log_dir=str(target),
                flush_secs=self.config.flush_secs,
                max_queue=self.config.max_queue,
                filename_suffix=self.config.filename_suffix,
                purge_step=self.config.purge_step,
            )
            self._writer = writer
            self._started = True
        return self

    @property
    def writer(self) -> Any:
        """Return the initialized ``SummaryWriter``-like instance."""

        return self.start()._writer

    def flush(self) -> None:
        with self._lock:
            if self._writer is None:
                return
            _call_if_present(self._writer, "flush")

    def close(self) -> None:
        with self._lock:
            if not self._started or self._writer is None:
                return
            _call_if_present(self._writer, "flush")
            _call_if_present(self._writer, "close")
            self._writer = None
            self._started = False


@dataclass(slots=True)
class TensorBoardCheckpointInspector:
    """Log LeWorldModel checkpoint provenance and per-run inference signals."""

    session: TensorBoardSession
    namespace: str = _DEFAULT_NAMESPACE
    default_step: int = 0
    _event_counter: int = field(default=0, init=False, repr=False)
    _numpy: Any | None = field(default=None, init=False, repr=False)
    _numpy_loaded: bool = field(default=False, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.namespace = _validate_namespace(self.namespace, name="namespace")
        self.default_step = _require_non_negative_int(self.default_step, name="default_step")

    @property
    def log_dir(self) -> Path:
        return self.session.log_dir

    def close(self) -> None:
        self.session.close()

    def flush(self) -> None:
        self.session.flush()

    def _numpy_module(self) -> Any | None:
        if not self._numpy_loaded:
            self._numpy = _try_load_numpy()
            self._numpy_loaded = True
        return self._numpy

    def _writer(self) -> Any:
        return self.session.writer

    def _next_event_step(self) -> int:
        with self._lock:
            step = self._event_counter
            self._event_counter += 1
        return step

    def log_text(self, tag: str, text: str, *, step: int | None = None) -> None:
        """Log a sanitized text panel under ``namespace/tag``."""

        clean_tag = _join_tag(self.namespace, _require_text(tag, name="tag"))
        if not isinstance(text, str):
            raise WorldForgeError("text must be a string.")
        writer = self._writer()
        add_text = getattr(writer, "add_text", None)
        if add_text is None:
            return
        add_text(clean_tag, _markdown_text(text), step or self.default_step)

    def log_json(self, tag: str, payload: object, *, step: int | None = None) -> None:
        """Log a JSON dict as a sanitized text panel."""

        dict_payload = require_json_dict(payload, name="payload")
        rendered = _pretty_json(dict_payload)
        self.log_text(tag, rendered, step=step)

    def log_scalar(self, tag: str, value: object, *, step: int | None = None) -> None:
        """Log a finite float scalar under ``namespace/tag``."""

        number = _finite_float(value)
        if number is None:
            return
        clean_tag = _join_tag(self.namespace, _require_text(tag, name="tag"))
        writer = self._writer()
        add_scalar = getattr(writer, "add_scalar", None)
        if add_scalar is None:
            return
        add_scalar(clean_tag, number, step or self.default_step)

    def log_histogram(
        self,
        tag: str,
        values: object,
        *,
        step: int | None = None,
        bins: str | int = "auto",
    ) -> None:
        """Log a histogram of finite floats under ``namespace/tag``.

        Falls back to no-op when numpy and torch are both unavailable.
        """

        cleaned = self._numeric_array(values)
        if cleaned is None or len(cleaned) == 0:
            return
        clean_tag = _join_tag(self.namespace, _require_text(tag, name="tag"))
        writer = self._writer()
        add_histogram = getattr(writer, "add_histogram", None)
        if add_histogram is None:
            return
        add_histogram(clean_tag, cleaned, step or self.default_step, bins=bins)

    def log_checkpoint_summary(self, payload: object) -> None:
        """Log LeWorldModel checkpoint provenance fields as text and scalars."""

        data = require_json_dict(payload, name="checkpoint_summary")
        self.log_json("checkpoint/provenance", data)
        path = data.get("output") or data.get("checkpoint")
        if isinstance(path, str) and path.strip():
            self.log_text("checkpoint/path", path)
        revision = data.get("revision")
        if isinstance(revision, str) and revision.strip():
            self.log_text("checkpoint/revision", revision)
        repo_id = data.get("repo_id")
        if isinstance(repo_id, str) and repo_id.strip():
            self.log_text("checkpoint/repo", repo_id)
        policy = data.get("policy")
        if isinstance(policy, str) and policy.strip():
            self.log_text("checkpoint/policy", policy)
        for key in ("created",):
            value = data.get(key)
            if isinstance(value, bool):
                self.log_scalar(f"checkpoint/{key}", 1.0 if value else 0.0)

    def log_score_distribution(
        self,
        scores: Iterable[object],
        *,
        step: int | None = None,
        best_index: int | None = None,
        best_score: object = None,
    ) -> None:
        """Log per-candidate cost scalars and a histogram of the distribution."""

        finite_scores: list[float] = []
        for index, raw in enumerate(scores):
            number = _finite_float(raw)
            if number is None:
                continue
            finite_scores.append(number)
            self.log_scalar(f"scores/candidate_{index:03d}", number, step=step)
        if not finite_scores:
            return
        self.log_histogram("scores/cost_distribution", finite_scores, step=step)
        self.log_scalar("scores/min", min(finite_scores), step=step)
        self.log_scalar("scores/max", max(finite_scores), step=step)
        self.log_scalar(
            "scores/mean",
            sum(finite_scores) / len(finite_scores),
            step=step,
        )
        if isinstance(best_index, int) and not isinstance(best_index, bool):
            self.log_scalar("scores/best_index", float(best_index), step=step)
        best_number = _finite_float(best_score)
        if best_number is not None:
            self.log_scalar("scores/best_score", best_number, step=step)

    def log_metrics(self, metrics: Mapping[str, object], *, step: int | None = None) -> None:
        """Log a mapping of metric names to finite scalars."""

        if not isinstance(metrics, Mapping):
            raise WorldForgeError("metrics must be a mapping.")
        for key, value in metrics.items():
            number = _finite_float(value)
            if number is None:
                continue
            self.log_scalar(f"metrics/{_tag_segment(key)}", number, step=step)

    def log_provider_event(self, event: ProviderEvent) -> None:
        """Append a sanitized provider event entry to the text feed."""

        if not isinstance(event, ProviderEvent):
            raise WorldForgeError(
                "TensorBoardCheckpointInspector.log_provider_event accepts ProviderEvent only.",
            )
        step = self._next_event_step()
        tag_suffix = f"events/{_tag_segment(event.provider)}/{_tag_segment(event.operation)}"
        message = event.message or f"{event.provider}.{event.operation} {event.phase}"
        self.log_text(f"{tag_suffix}/log", message, step=step)
        self.log_scalar(f"{tag_suffix}/attempt", float(event.attempt), step=step)
        self.log_scalar(
            f"{tag_suffix}/max_attempts",
            float(event.max_attempts),
            step=step,
        )
        if event.duration_ms is not None:
            self.log_scalar(f"{tag_suffix}/duration_ms", event.duration_ms, step=step)
        if event.status_code is not None:
            self.log_scalar(f"{tag_suffix}/status_code", float(event.status_code), step=step)
        self.log_scalar(
            f"{tag_suffix}/failure",
            1.0 if event.phase == "failure" else 0.0,
            step=step,
        )
        self.log_scalar(
            f"{tag_suffix}/retry",
            1.0 if event.phase == "retry" else 0.0,
            step=step,
        )

    def log_robotics_showcase_summary(self, summary: object) -> None:
        """Log the robotics showcase summary as text, scalars, and a histogram."""

        payload = require_json_dict(summary, name="robotics_showcase_summary")
        self.log_text(
            "robotics_showcase/summary",
            _pretty_json(payload),
        )
        for key in ("task", "checkpoint_display", "checkpoint", "state_dir"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                self.log_text(f"robotics_showcase/{key}", value)
        inputs = payload.get("inputs")
        if isinstance(inputs, dict):
            self.log_json("robotics_showcase/inputs", inputs)
        health = payload.get("health")
        if isinstance(health, dict):
            self.log_json("robotics_showcase/health", health)
        score_result = payload.get("score_result")
        if isinstance(score_result, dict):
            self.log_score_distribution(
                score_result.get("scores", []),
                best_index=score_result.get("best_index"),
                best_score=score_result.get("best_score"),
            )
        score_stats = payload.get("score_stats")
        if isinstance(score_stats, dict):
            mapped = {
                "score_min": score_stats.get("score_min"),
                "score_max": score_stats.get("score_max"),
                "score_mean": score_stats.get("score_mean"),
                "score_median": score_stats.get("score_median"),
                "score_range": score_stats.get("score_range"),
                "gap_to_runner_up": score_stats.get("gap_to_runner_up"),
            }
            self.log_metrics(mapped)
        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            self.log_metrics(metrics)
        events = payload.get("provider_events")
        if isinstance(events, list):
            for entry in events:
                provider_event = self._coerce_provider_event(entry)
                if provider_event is not None:
                    self.log_provider_event(provider_event)

    def log_state_dict_histograms(
        self,
        state_dict: Mapping[str, object],
        *,
        step: int | None = None,
    ) -> int:
        """Log per-parameter weight histograms from a state-dict mapping.

        Tensor-like values (objects exposing ``detach``/``cpu``/``numpy``) are
        flattened and logged as histograms. Other values are ignored. Returns
        the number of parameters that produced a histogram.
        """

        if not isinstance(state_dict, Mapping):
            raise WorldForgeError("state_dict must be a mapping.")
        logged = 0
        for name, tensor in state_dict.items():
            if not _is_tensor_like(tensor):
                continue
            try:
                array = tensor.detach().cpu().numpy()  # type: ignore[union-attr]
            except Exception:
                continue
            self.log_histogram(f"weights/{_tag_segment(name)}", array, step=step)
            logged += 1
        return logged

    def _coerce_provider_event(self, candidate: object) -> ProviderEvent | None:
        if isinstance(candidate, ProviderEvent):
            return candidate
        if not isinstance(candidate, dict):
            return None
        provider = candidate.get("provider")
        operation = candidate.get("operation")
        phase = candidate.get("phase")
        if (
            not isinstance(provider, str)
            or not isinstance(operation, str)
            or not isinstance(
                phase,
                str,
            )
        ):
            return None
        kwargs: dict[str, object] = {
            "provider": provider,
            "operation": operation,
            "phase": phase,
        }
        for field_name in (
            "attempt",
            "max_attempts",
            "method",
            "target",
            "status_code",
            "duration_ms",
            "message",
            "metadata",
            "run_id",
            "request_id",
            "trace_id",
            "span_id",
            "artifact_id",
            "input_digest",
        ):
            if field_name in candidate:
                kwargs[field_name] = candidate[field_name]
        try:
            return ProviderEvent(**kwargs)  # type: ignore[arg-type]
        except (WorldForgeError, TypeError, ValueError):
            return None

    def _numeric_array(self, values: object) -> Any:
        if _is_tensor_like(values):
            try:
                return values.detach().cpu().numpy()  # type: ignore[union-attr]
            except Exception:
                return None
        if not isinstance(values, Iterable) or isinstance(values, str | bytes):
            return None
        finite_values: list[float] = []
        for raw in values:
            number = _finite_float(raw)
            if number is not None:
                finite_values.append(number)
        if not finite_values:
            return []
        numpy = self._numpy_module()
        if numpy is not None:
            return numpy.asarray(finite_values, dtype="float64")
        return finite_values


def default_run_name(prefix: str = "run") -> str:
    """Return a timestamped run name suitable for ``run_name``."""

    safe_prefix = _tag_segment(prefix, fallback="run")
    return f"{safe_prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def create_tensorboard_inspector(
    *,
    log_dir: str | Path,
    run_name: str | None = None,
    namespace: str = _DEFAULT_NAMESPACE,
    flush_secs: int = 30,
    sdk: object | None = None,
) -> TensorBoardCheckpointInspector:
    """Create a configured :class:`TensorBoardCheckpointInspector`."""

    config = TensorBoardLogConfig(
        log_dir=log_dir,
        run_name=run_name,
        flush_secs=flush_secs,
    )
    session = TensorBoardSession(config=config, sdk=sdk)
    return TensorBoardCheckpointInspector(session=session, namespace=namespace)


__all__ = [
    "TensorBoardCheckpointInspector",
    "TensorBoardLogConfig",
    "TensorBoardSession",
    "create_tensorboard_inspector",
    "default_run_name",
]
