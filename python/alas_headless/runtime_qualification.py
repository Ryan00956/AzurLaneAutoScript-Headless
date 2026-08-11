"""Fail-closed lifecycle orchestration and exact-fingerprint manifests."""

from __future__ import annotations

import json
import math
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .runtime_artifacts import RuntimeLock
from .runtime_backend import RuntimeBackend
from .runtime_evidence import RuntimeFingerprint
from .runtime_trace import RuntimeTraceRecorder


RUNTIME_QUALIFICATION_SCHEMA = "alas-headless.runtime-qualification/v1"
RUNTIME_RECOVERY_KINDS = ("game", "android")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _failure_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", code):
        return code
    value = re.sub(r"(?<!^)(?=[A-Z])", "-", type(exc).__name__).lower()
    return value or "runtime-error"


class RuntimeQualificationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def expected_runtime_fingerprint(
    runtime_lock: RuntimeLock, backend: RuntimeBackend
) -> Mapping[str, str]:
    document = runtime_lock.document
    host_class = getattr(backend, "host_class", "")
    if not isinstance(host_class, str) or not host_class.strip():
        raise ValueError("runtime backend must declare a host_class")
    value = {
        "backend": backend.profile.backend.value,
        "host_class": host_class,
        "android_fingerprint": document["android"]["build_fingerprint"],
        "game_version": document["game"]["version_name"],
        "game_abi": document["game"]["abi"],
        "libil2cpp_sha256": document["game"]["libil2cpp_sha256"],
        "angle_sha256": document["angle"]["apk_sha256"],
        "observer_schema": document["angle"]["observer_schema"],
        "core_commit": document["core"]["core_commit"],
        "runtime_lock_sha256": runtime_lock.sha256,
    }
    return RuntimeFingerprint.from_mapping(value).as_mapping()


@dataclass(frozen=True)
class RuntimeQualificationTimeouts:
    adb_ready_seconds: float = 180.0
    adb_disconnect_seconds: float = 60.0
    android_ready_seconds: float = 300.0
    game_ready_seconds: float = 300.0
    observer_ready_seconds: float = 120.0

    def __post_init__(self) -> None:
        for value in (
            self.adb_ready_seconds,
            self.adb_disconnect_seconds,
            self.android_ready_seconds,
            self.game_ready_seconds,
            self.observer_ready_seconds,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise ValueError("runtime qualification timeouts must be positive")


class RuntimeQualificationRunner:
    def __init__(
        self,
        backend: RuntimeBackend,
        runtime_lock: RuntimeLock,
        output_directory: Path,
        timeouts: RuntimeQualificationTimeouts = RuntimeQualificationTimeouts(),
        utc_now: Callable[[], str] = _utc_now,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.backend = backend
        self.runtime_lock = runtime_lock
        self.output_directory = Path(output_directory)
        self.timeouts = timeouts
        self.utc_now = utc_now
        self.monotonic_ns = monotonic_ns

    def qualify(self, recovery: Optional[str] = None) -> Mapping[str, Any]:
        if recovery is not None and recovery not in RUNTIME_RECOVERY_KINDS:
            raise ValueError("runtime recovery kind is unsupported")
        if recovery is not None and not self.backend.supports_recovery(recovery):
            raise ValueError("runtime recovery is not enabled for this backend")
        self.output_directory.mkdir(parents=True, exist_ok=False)
        run_id = uuid.uuid4().hex
        trace = RuntimeTraceRecorder(
            self.output_directory / "runtime-trace.jsonl",
            enabled=True,
            run_id=run_id,
        )
        if getattr(self.backend, "trace", None) is None:
            try:
                setattr(self.backend, "trace", trace)
            except (AttributeError, TypeError):
                pass
        started_utc = self.utc_now()
        phases = []
        instance: Optional[Mapping[str, Any]] = None
        observed_fingerprint: Optional[Mapping[str, str]] = None
        baseline_fingerprint: Optional[Mapping[str, str]] = None
        baseline_observer: Optional[Mapping[str, Any]] = None
        recovery_record: Optional[Dict[str, Any]] = None
        failure: Optional[BaseException] = None
        cleanup_failure: Optional[BaseException] = None

        def phase(name: str, operation: Callable[[], Any]) -> Any:
            phase_started_utc = self.utc_now()
            phase_started_ns = self.monotonic_ns()
            try:
                with trace.lifecycle_span(
                    self.backend.profile.backend.value,
                    self.backend.profile.profile_id,
                    name,
                ):
                    value = operation()
            except Exception as exc:
                phases.append(
                    {
                        "phase": name,
                        "started_at_utc": phase_started_utc,
                        "duration_ns": max(0, self.monotonic_ns() - phase_started_ns),
                        "outcome": "fail",
                        "failure_code": _failure_code(exc),
                    }
                )
                raise
            phases.append(
                {
                    "phase": name,
                    "started_at_utc": phase_started_utc,
                    "duration_ns": max(0, self.monotonic_ns() - phase_started_ns),
                    "outcome": "pass",
                    "failure_code": None,
                }
            )
            return value

        try:
            def require_probe() -> Any:
                value = self.backend.probe_host()
                if not value.available:
                    raise RuntimeQualificationError(
                        "backend-probe-{0}".format(value.reason)
                    )
                return value

            phase("probe-host", require_probe)
            artifacts = phase(
                "resolve-artifacts",
                lambda: self.backend.resolve_artifacts(self.runtime_lock),
            )
            provisioned = phase(
                "provision", lambda: self.backend.provision(artifacts)
            )
            instance = phase("start", lambda: self.backend.start(provisioned))
            phase(
                "adb-ready",
                lambda: self.backend.wait_adb(
                    instance, self.timeouts.adb_ready_seconds
                ),
            )
            phase(
                "android-ready",
                lambda: self.backend.wait_android_ready(
                    instance, self.timeouts.android_ready_seconds
                ),
            )
            phase(
                "game-ready",
                lambda: self.backend.wait_game_ready(
                    instance, self.timeouts.game_ready_seconds
                ),
            )
            baseline_observer = phase(
                "observer-ready",
                lambda: self.backend.wait_observer_ready(
                    instance, self.timeouts.observer_ready_seconds
                ),
            )
            baseline_fingerprint = phase(
                "fingerprint", lambda: self.backend.fingerprint(instance)
            )
            baseline_fingerprint = RuntimeFingerprint.from_mapping(
                baseline_fingerprint
            ).as_mapping()
            observed_fingerprint = baseline_fingerprint

            if recovery is not None:
                recovery_record = {
                    "kind": recovery,
                    "baseline_observer": dict(baseline_observer),
                    "recovered_observer": None,
                    "game_pid_changed": None,
                    "runtime_fingerprint_preserved": None,
                }
                if recovery == "game":
                    phase("restart-game", lambda: self.backend.restart_game(instance))
                    recovered_game = phase(
                        "game-recovered",
                        lambda: self.backend.wait_recovered_game_ready(
                            instance, self.timeouts.game_ready_seconds
                        ),
                    )
                else:
                    phase(
                        "restart-android",
                        lambda: self.backend.restart_android(instance),
                    )
                    phase(
                        "adb-offline",
                        lambda: self.backend.wait_android_offline(
                            instance, self.timeouts.adb_disconnect_seconds
                        ),
                    )
                    phase(
                        "adb-recovered",
                        lambda: self.backend.wait_adb(
                            instance, self.timeouts.adb_ready_seconds
                        ),
                    )
                    phase(
                        "android-recovered",
                        lambda: self.backend.wait_android_ready(
                            instance, self.timeouts.android_ready_seconds
                        ),
                    )
                    recovered_game = phase(
                        "game-recovered",
                        lambda: self.backend.wait_game_ready(
                            instance, self.timeouts.game_ready_seconds
                        ),
                    )
                recovered_observer = phase(
                    "observer-recovered",
                    lambda: self.backend.wait_observer_ready(
                        instance, self.timeouts.observer_ready_seconds
                    ),
                )
                observed_fingerprint = phase(
                    "fingerprint-recovered",
                    lambda: self.backend.fingerprint(instance),
                )
                observed_fingerprint = RuntimeFingerprint.from_mapping(
                    observed_fingerprint
                ).as_mapping()
                baseline_pid = baseline_observer.get("pid")
                recovered_pid = recovered_observer.get("pid")
                game_pid = recovered_game.get("pid")
                recovery_record.update(
                    {
                        "recovered_observer": dict(recovered_observer),
                        "game_pid_changed": recovered_pid != baseline_pid,
                        "runtime_fingerprint_preserved": (
                            observed_fingerprint == baseline_fingerprint
                        ),
                    }
                )
                if recovered_pid == baseline_pid:
                    raise RuntimeQualificationError("game-pid-did-not-change")
                if recovered_pid != game_pid:
                    raise RuntimeQualificationError(
                        "recovered-game-observer-pid-mismatch"
                    )
                if observed_fingerprint != baseline_fingerprint:
                    raise RuntimeQualificationError(
                        "recovered-runtime-fingerprint-mismatch"
                    )
        except Exception as exc:
            failure = exc
        finally:
            if instance is not None:
                try:
                    phase("stop", lambda: self.backend.stop(instance))
                except Exception as exc:
                    cleanup_failure = exc

        trace_summary = trace.close()
        expected_fingerprint = expected_runtime_fingerprint(
            self.runtime_lock, self.backend
        )
        if failure is None and observed_fingerprint != expected_fingerprint:
            failure = RuntimeQualificationError(
                "observed-runtime-fingerprint-mismatch"
            )
        if failure is None and cleanup_failure is not None:
            failure = cleanup_failure
        if failure is None and (
            trace_summary["dropped"] != 0
            or trace_summary["invalid"] != 0
            or trace_summary["writer_error"] is not None
        ):
            failure = RuntimeQualificationError("runtime-trace-incomplete")

        manifest = {
            "schema": RUNTIME_QUALIFICATION_SCHEMA,
            "gate": (
                "runtime-lifecycle"
                if recovery is None
                else "runtime-recovery-{0}".format(recovery)
            ),
            "outcome": "pass" if failure is None else "fail",
            "captured_at_utc": started_utc,
            "run_id": run_id,
            "backend": self.backend.profile.backend.value,
            "profile_id": self.backend.profile.profile_id,
            "runtime_lock_sha256": self.runtime_lock.sha256,
            "runtime_fingerprint": observed_fingerprint or expected_fingerprint,
            "expected_runtime_fingerprint": expected_fingerprint,
            "observed_runtime_fingerprint": observed_fingerprint,
            "baseline_runtime_fingerprint": baseline_fingerprint,
            "recovery": recovery_record,
            "phases": phases,
            "failure_code": _failure_code(failure) if failure is not None else None,
            "cleanup_failure_code": (
                _failure_code(cleanup_failure)
                if cleanup_failure is not None
                else None
            ),
            "trace_summary": trace_summary,
            "input_injected": False,
            "runtime_state_changed": bool(
                (instance is not None and instance.get("owned") is True)
                or getattr(self.backend, "launch_game", False)
            ),
        }
        self._write_json_atomic(self.output_directory / "manifest.json", manifest)
        return manifest

    @staticmethod
    def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
