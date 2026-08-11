"""Bounded, opt-in runtime tracing for lifecycle and observer measurements."""

from __future__ import annotations

import json
import math
import queue
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Mapping, Optional


RUNTIME_TRACE_SCHEMA = "alas-headless.runtime-trace/v1"
RUNTIME_LIFECYCLE_PHASES = frozenset(
    (
        "provision",
        "probe-host",
        "resolve-artifacts",
        "start",
        "adb-ready",
        "android-ready",
        "game-ready",
        "observer-ready",
        "fingerprint",
        "restart-game",
        "restart-android",
        "adb-offline",
        "adb-recovered",
        "android-recovered",
        "game-recovered",
        "observer-recovered",
        "fingerprint-recovered",
        "stop",
    )
)
_SENTINEL = object()
_SENSITIVE_FIELD_FRAGMENTS = (
    "account",
    "cookie",
    "credential",
    "email",
    "password",
    "phone",
    "secret",
    "token",
)


class RuntimeTraceError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeProcessSample:
    scope: str
    cpu_time_ns: Optional[int] = None
    rss_bytes: Optional[int] = None
    pss_bytes: Optional[int] = None
    read_bytes: Optional[int] = None
    write_bytes: Optional[int] = None
    network_receive_bytes: Optional[int] = None
    network_transmit_bytes: Optional[int] = None
    instance_index: Optional[int] = None

    def fields(self) -> Mapping[str, Any]:
        if self.scope not in ("host-runtime", "android-system", "game"):
            raise RuntimeTraceError("runtime process sample scope is unsupported")
        output: Dict[str, Any] = {"scope": self.scope}
        for name in (
            "cpu_time_ns",
            "rss_bytes",
            "pss_bytes",
            "read_bytes",
            "write_bytes",
            "network_receive_bytes",
            "network_transmit_bytes",
            "instance_index",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeTraceError(
                    "runtime process sample field must be non-negative: {0}".format(name)
                )
            output[name] = value
        return output


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_fields(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeTraceError("runtime trace fields must be a mapping")

    def clean(item: Any, path: str) -> Any:
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise RuntimeTraceError("runtime trace field is not finite: {0}".format(path))
            return item
        if isinstance(item, (list, tuple)):
            return [clean(child, path) for child in item]
        if isinstance(item, dict):
            output = {}
            for key, child in item.items():
                if not isinstance(key, str) or not key:
                    raise RuntimeTraceError("runtime trace field keys must be non-empty text")
                normalized = key.lower().replace("-", "_")
                if any(fragment in normalized for fragment in _SENSITIVE_FIELD_FRAGMENTS):
                    raise RuntimeTraceError("sensitive runtime trace field refused: {0}".format(key))
                output[key] = clean(child, path + "." + key)
            return output
        raise RuntimeTraceError("unsupported runtime trace field type: {0}".format(path))

    return clean(dict(value), "fields")


class RuntimeTraceRecorder:
    """Write JSONL without allowing telemetry backpressure to block ALAS."""

    def __init__(
        self,
        output_path: Optional[Path] = None,
        enabled: bool = False,
        run_id: Optional[str] = None,
        maximum_queue_size: int = 4096,
        wall_clock: Callable[[], str] = _utc_now,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if maximum_queue_size < 1:
            raise ValueError("runtime trace queue size must be positive")
        if enabled and output_path is None:
            raise ValueError("enabled runtime tracing requires an output path")
        self.enabled = bool(enabled)
        self.output_path = Path(output_path) if output_path is not None else None
        self.run_id = run_id or uuid.uuid4().hex
        self._wall_clock = wall_clock
        self._monotonic_ns = monotonic_ns
        self._queue = queue.Queue(maxsize=maximum_queue_size)
        self._sequence = 0
        self._lock = threading.Lock()
        self._closed = False
        self._dropped = 0
        self._invalid = 0
        self._written = 0
        self._writer_error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        if self.enabled:
            assert self.output_path is not None
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self._thread = threading.Thread(
                target=self._writer,
                name="alas-runtime-trace",
                daemon=True,
            )
            self._thread.start()

    def emit(
        self,
        event: str,
        outcome: str = "ok",
        duration_ns: Optional[int] = None,
        fields: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        if not self.enabled:
            return False
        if not isinstance(event, str) or not event.strip():
            self._invalid += 1
            raise RuntimeTraceError("runtime trace event must be non-empty text")
        if outcome not in ("ok", "error", "refused", "timeout"):
            self._invalid += 1
            raise RuntimeTraceError("runtime trace outcome is unsupported")
        if duration_ns is not None and (
            isinstance(duration_ns, bool)
            or not isinstance(duration_ns, int)
            or duration_ns < 0
        ):
            self._invalid += 1
            raise RuntimeTraceError("runtime trace duration must be non-negative nanoseconds")
        try:
            safe = _safe_fields(dict(fields or {}))
        except RuntimeTraceError:
            self._invalid += 1
            raise
        with self._lock:
            if self._closed:
                return False
            self._sequence += 1
            sequence = self._sequence
        record = {
            "schema": RUNTIME_TRACE_SCHEMA,
            "run_id": self.run_id,
            "sequence": sequence,
            "captured_at_utc": self._wall_clock(),
            "monotonic_ns": self._monotonic_ns(),
            "event": event.strip(),
            "outcome": outcome,
            "duration_ns": duration_ns,
            "fields": safe,
        }
        try:
            self._queue.put_nowait(record)
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False

    @contextmanager
    def span(
        self, event: str, fields: Optional[Mapping[str, Any]] = None
    ) -> Iterator[None]:
        started = self._monotonic_ns()
        try:
            yield
        except BaseException as exc:
            safe = dict(fields or {})
            safe["exception_type"] = type(exc).__name__
            self.emit(
                event,
                outcome="error",
                duration_ns=max(0, self._monotonic_ns() - started),
                fields=safe,
            )
            raise
        else:
            self.emit(
                event,
                duration_ns=max(0, self._monotonic_ns() - started),
                fields=fields,
            )

    @contextmanager
    def lifecycle_span(
        self,
        backend: str,
        profile_id: str,
        phase: str,
        fields: Optional[Mapping[str, Any]] = None,
    ) -> Iterator[None]:
        if (
            not isinstance(backend, str)
            or not backend.strip()
            or not isinstance(profile_id, str)
            or not profile_id.strip()
        ):
            raise RuntimeTraceError("runtime lifecycle identity cannot be empty")
        if phase not in RUNTIME_LIFECYCLE_PHASES:
            raise RuntimeTraceError("runtime lifecycle phase is unsupported")
        combined = dict(fields or {})
        combined.update(
            {"backend": backend, "profile_id": profile_id, "phase": phase}
        )
        with self.span("runtime.lifecycle", combined):
            yield

    @contextmanager
    def alas_action_span(
        self,
        method: str,
        task_phase: str,
        fields: Optional[Mapping[str, Any]] = None,
    ) -> Iterator[None]:
        if (
            not isinstance(method, str)
            or not method.strip()
            or not isinstance(task_phase, str)
            or not task_phase.strip()
        ):
            raise RuntimeTraceError("ALAS action identity cannot be empty")
        combined = dict(fields or {})
        combined.update({"method": method.strip(), "task_phase": task_phase.strip()})
        with self.span("alas.action", combined):
            yield

    def process_sample(self, sample: RuntimeProcessSample) -> bool:
        if not isinstance(sample, RuntimeProcessSample):
            raise RuntimeTraceError("runtime process sample has the wrong type")
        return self.emit("runtime.process.sample", fields=sample.fields())

    def _writer(self) -> None:
        assert self.output_path is not None
        try:
            with self.output_path.open("a", encoding="utf-8", newline="\n") as handle:
                while True:
                    item = self._queue.get()
                    try:
                        if item is _SENTINEL:
                            return
                        handle.write(
                            json.dumps(
                                item,
                                sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        handle.flush()
                        self._written += 1
                    finally:
                        self._queue.task_done()
        except BaseException as exc:
            self._writer_error = type(exc).__name__

    def close(self, timeout_seconds: float = 5.0) -> Mapping[str, Any]:
        with self._lock:
            already_closed = self._closed
            self._closed = True
        if already_closed:
            return self.summary()
        if self._thread is not None:
            try:
                self._queue.put(_SENTINEL, timeout=timeout_seconds)
            except queue.Full:
                self._writer_error = "close-timeout"
            self._thread.join(timeout_seconds)
            if self._thread.is_alive():
                self._writer_error = "writer-timeout"
        return self.summary()

    def summary(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "schema": RUNTIME_TRACE_SCHEMA,
                "run_id": self.run_id,
                "enabled": self.enabled,
                "recorded": self._written,
                "dropped": self._dropped,
                "invalid": self._invalid,
                "writer_error": self._writer_error,
            }

    def __enter__(self) -> "RuntimeTraceRecorder":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def summarize_runtime_trace(path: Path) -> Mapping[str, Any]:
    """Produce deterministic latency distributions from one trace file."""

    groups: Dict[str, list] = {}
    outcomes: Dict[str, Dict[str, int]] = {}
    records = 0
    run_ids = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeTraceError(
                    "invalid trace JSON at line {0}".format(line_number)
                ) from exc
            if not isinstance(record, dict) or record.get("schema") != RUNTIME_TRACE_SCHEMA:
                raise RuntimeTraceError("trace schema mismatch at line {0}".format(line_number))
            event = record.get("event")
            outcome = record.get("outcome")
            duration = record.get("duration_ns")
            if not isinstance(event, str) or not isinstance(outcome, str):
                raise RuntimeTraceError("trace identity is malformed at line {0}".format(line_number))
            records += 1
            run_ids.add(record.get("run_id"))
            outcomes.setdefault(event, {})[outcome] = outcomes.setdefault(event, {}).get(outcome, 0) + 1
            if isinstance(duration, int) and not isinstance(duration, bool) and duration >= 0:
                groups.setdefault(event, []).append(duration)

    def percentile(values: list, fraction: float) -> Optional[int]:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, int(math.ceil(fraction * len(ordered))) - 1)
        return ordered[index]

    events = {}
    for event in sorted(set(groups) | set(outcomes)):
        values = groups.get(event, [])
        event_outcomes = outcomes.get(event, {})
        total = sum(event_outcomes.values())
        errors = sum(
            count for name, count in event_outcomes.items() if name != "ok"
        )
        events[event] = {
            "count": total,
            "timed_count": len(values),
            "mean_ns": int(sum(values) / len(values)) if values else None,
            "p50_ns": percentile(values, 0.50),
            "p95_ns": percentile(values, 0.95),
            "p99_ns": percentile(values, 0.99),
            "error_rate": (float(errors) / total) if total else 0.0,
            "outcomes": dict(sorted(event_outcomes.items())),
        }
    return {
        "schema": "alas-headless.runtime-trace-summary/v1",
        "records": records,
        "run_ids": sorted(run_id for run_id in run_ids if isinstance(run_id, str)),
        "events": events,
    }
