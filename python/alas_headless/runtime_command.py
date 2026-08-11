"""Shell-free command execution boundary for runtime backends."""

from __future__ import annotations

import math
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


class RuntimeCommandError(RuntimeError):
    pass


class RuntimeMutationRefused(RuntimeCommandError):
    pass


@dataclass(frozen=True)
class RuntimeExecutionPolicy:
    allow_read_only: bool = True
    allow_runtime_mutation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allow_read_only, bool) or not isinstance(
            self.allow_runtime_mutation, bool
        ):
            raise ValueError("runtime execution policy switches must be booleans")


@dataclass(frozen=True)
class RuntimeCommandSpec:
    label: str
    argv: Tuple[str, ...]
    timeout_seconds: float = 30.0
    mutating: bool = False
    environment: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("runtime command requires a non-empty label")
        if not isinstance(self.argv, tuple) or not self.argv or any(
            not isinstance(item, str) or not item for item in self.argv
        ):
            raise ValueError("runtime command argv must contain non-empty strings")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("runtime command timeout must be positive")
        if not isinstance(self.mutating, bool):
            raise ValueError("runtime command mutation flag must be boolean")
        if not isinstance(self.environment, Mapping):
            raise ValueError("runtime command environment must be a mapping")
        for key, value in self.environment.items():
            if not isinstance(key, str) or not key or not isinstance(value, str):
                raise ValueError("runtime command environment is malformed")
            if key.upper() in ("HOME", "CODEX_HOME"):
                raise ValueError("runtime commands cannot override broad home variables")


@dataclass(frozen=True)
class RuntimeCommandResult:
    label: str
    returncode: int
    stdout: str
    stderr: str
    duration_ns: int
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and self.returncode == 0


@dataclass(frozen=True)
class RuntimeOwnedProcess:
    handle_id: str
    pid: int
    label: str


class RuntimeCommandExecutor:
    """Execute exact argv vectors; never invoke a command shell."""

    def __init__(
        self,
        policy: RuntimeExecutionPolicy = RuntimeExecutionPolicy(),
        maximum_output_bytes: int = 1024 * 1024,
    ) -> None:
        if (
            isinstance(maximum_output_bytes, bool)
            or not isinstance(maximum_output_bytes, int)
            or maximum_output_bytes < 1024
        ):
            raise ValueError("runtime command output limit is too small")
        self.policy = policy
        self.maximum_output_bytes = maximum_output_bytes
        self._processes: Dict[str, subprocess.Popen] = {}

    def _authorize(self, spec: RuntimeCommandSpec) -> None:
        if spec.mutating and not self.policy.allow_runtime_mutation:
            raise RuntimeMutationRefused(
                "runtime mutation is disabled: {0}".format(spec.label)
            )
        if not spec.mutating and not self.policy.allow_read_only:
            raise RuntimeMutationRefused(
                "read-only runtime commands are disabled: {0}".format(spec.label)
            )

    @staticmethod
    def _environment(overrides: Mapping[str, str]) -> Mapping[str, str]:
        environment = dict(os.environ)
        environment.update(overrides)
        return environment

    def run(self, spec: RuntimeCommandSpec) -> RuntimeCommandResult:
        self._authorize(spec)
        started = time.monotonic_ns()
        try:
            completed = subprocess.run(
                list(spec.argv),
                check=False,
                capture_output=True,
                timeout=spec.timeout_seconds,
                env=self._environment(spec.environment),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            return RuntimeCommandResult(
                spec.label,
                -1,
                self._decode(stdout),
                self._decode(stderr),
                time.monotonic_ns() - started,
                timed_out=True,
            )
        except OSError as exc:
            return RuntimeCommandResult(
                spec.label,
                -1,
                "",
                type(exc).__name__,
                time.monotonic_ns() - started,
            )
        return RuntimeCommandResult(
            spec.label,
            completed.returncode,
            self._decode(completed.stdout),
            self._decode(completed.stderr),
            time.monotonic_ns() - started,
        )

    def start(self, spec: RuntimeCommandSpec, handle_id: str) -> RuntimeOwnedProcess:
        if not spec.mutating:
            raise RuntimeCommandError("background runtime commands must be mutating")
        self._authorize(spec)
        if not handle_id or handle_id in self._processes:
            raise RuntimeCommandError("runtime process handle is invalid or already owned")
        try:
            process = subprocess.Popen(
                list(spec.argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._environment(spec.environment),
            )
        except OSError as exc:
            raise RuntimeCommandError("runtime process failed to start") from exc
        self._processes[handle_id] = process
        return RuntimeOwnedProcess(handle_id, process.pid, spec.label)

    def process_running(self, process: RuntimeOwnedProcess) -> bool:
        owned = self._processes.get(process.handle_id)
        if owned is None or owned.pid != process.pid:
            raise RuntimeCommandError("runtime process is not owned by this executor")
        return owned.poll() is None

    def stop_owned(
        self, process: RuntimeOwnedProcess, timeout_seconds: float = 30.0
    ) -> Optional[int]:
        owned = self._processes.get(process.handle_id)
        if owned is None or owned.pid != process.pid:
            raise RuntimeCommandError("runtime process is not owned by this executor")
        if owned.poll() is None:
            try:
                owned.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                owned.terminate()
                try:
                    owned.wait(timeout=min(10.0, timeout_seconds))
                except subprocess.TimeoutExpired:
                    owned.kill()
                    owned.wait(timeout=10.0)
        returncode = owned.returncode
        del self._processes[process.handle_id]
        return returncode

    def _decode(self, value: Any) -> str:
        if isinstance(value, str):
            encoded = value.encode("utf-8", errors="replace")
        else:
            encoded = bytes(value or b"")
        if len(encoded) > self.maximum_output_bytes:
            encoded = encoded[: self.maximum_output_bytes]
        return encoded.decode("utf-8", errors="replace").strip()
