"""Fail-closed placeholders for runtime backends without provisioners."""

from __future__ import annotations

from typing import Any, Mapping

from .runtime_backend import (
    BackendKind,
    RuntimeBackend,
    RuntimeProbeResult,
    built_in_backend_profiles,
)
from .runtime_backend_adb import RuntimeBackendNotReady


class DeferredRuntimeBackend(RuntimeBackend):
    """Visible plan-only adapter that cannot be accidentally selected."""

    def __init__(self, kind: BackendKind, reason: str, host_class: str) -> None:
        if kind not in (BackendKind.REDROID, BackendKind.TCG, BackendKind.ARM64_QEMU):
            raise ValueError("deferred backend kind is unsupported")
        super().__init__(built_in_backend_profiles()[kind])
        if not isinstance(host_class, str) or not host_class.strip():
            raise ValueError("deferred backend host class cannot be empty")
        self.reason = reason
        self.host_class = host_class

    def probe_host(self) -> RuntimeProbeResult:
        return RuntimeProbeResult(False, self.profile.backend, self.reason)

    def _refuse(self) -> None:
        raise RuntimeBackendNotReady(self.reason)

    def resolve_artifacts(self, runtime_lock: Mapping[str, Any]) -> Mapping[str, Any]:
        self._refuse()

    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        self._refuse()

    def start(self, provisioned: Mapping[str, Any]) -> Mapping[str, Any]:
        self._refuse()

    def wait_adb(self, instance: Mapping[str, Any], timeout_seconds: float) -> str:
        self._refuse()

    def wait_android_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        self._refuse()

    def wait_game_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        self._refuse()

    def wait_observer_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        self._refuse()

    def fingerprint(self, instance: Mapping[str, Any]) -> Mapping[str, Any]:
        self._refuse()

    def restart_game(self, instance: Mapping[str, Any]) -> None:
        self._refuse()

    def restart_android(self, instance: Mapping[str, Any]) -> None:
        self._refuse()

    def stop(self, instance: Mapping[str, Any]) -> None:
        self._refuse()

    def qualification_plan(
        self, runtime_lock: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return {
            "schema": "alas-headless.runtime-qualification-plan/v1",
            "backend": self.profile.backend.value,
            "profile_id": self.profile.profile_id,
            "executable": False,
            "reason": self.reason,
            "state_changes": [],
        }
