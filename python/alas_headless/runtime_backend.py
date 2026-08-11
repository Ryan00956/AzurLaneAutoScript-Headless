"""Backend-neutral lifecycle contracts for headless Android runtimes.

This module is deliberately policy-light.  It describes the lifecycle shared by
all runtimes while keeping provisioning and tuning inside backend implementations
and their immutable profiles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


RUNTIME_BACKEND_SCHEMA = "alas-headless.runtime-backend/v1"


class BackendKind(str, Enum):
    KVM = "kvm"
    REDROID = "redroid"
    TCG = "tcg"
    ARM64_QEMU = "arm64-qemu"
    EXTERNAL_ADB = "external-adb"


@dataclass(frozen=True)
class RuntimeCapabilities:
    persistent_userdata: bool
    shared_public_resources: bool
    snapshot_restore: bool
    multi_instance: bool
    host_metrics: bool
    hardware_acceleration: bool


@dataclass(frozen=True)
class RuntimeBackendProfile:
    backend: BackendKind
    profile_id: str
    capabilities: RuntimeCapabilities
    required_host_features: Tuple[str, ...] = ()
    lifecycle_phases: Tuple[str, ...] = (
        "provision",
        "start",
        "adb-ready",
        "android-ready",
        "game-ready",
        "observer-ready",
        "stop",
    )
    backend_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.profile_id or any(char.isspace() for char in self.profile_id):
            raise ValueError("runtime profile_id must be a non-empty token")
        if len(set(self.lifecycle_phases)) != len(self.lifecycle_phases):
            raise ValueError("runtime lifecycle phases must be unique")
        if not self.lifecycle_phases:
            raise ValueError("runtime lifecycle phases cannot be empty")


@dataclass(frozen=True)
class RuntimeProbeResult:
    available: bool
    backend: BackendKind
    reason: str
    host_fingerprint: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("runtime probe result requires a reason")


@dataclass(frozen=True)
class RuntimeSelection:
    schema: str
    backend: BackendKind
    profile_id: str
    host_fingerprint: Mapping[str, str]


class RuntimeBackend(ABC):
    """Lifecycle boundary implemented by one environment-specific backend."""

    def __init__(self, profile: RuntimeBackendProfile) -> None:
        self.profile = profile

    @abstractmethod
    def probe_host(self) -> RuntimeProbeResult:
        """Perform a read-only host capability probe."""

    @abstractmethod
    def resolve_artifacts(self, runtime_lock: Mapping[str, Any]) -> Mapping[str, Any]:
        """Resolve immutable artifacts without updating or starting the runtime."""

    @abstractmethod
    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        """Prepare backend-specific storage and configuration."""

    @abstractmethod
    def start(self, provisioned: Mapping[str, Any]) -> Mapping[str, Any]:
        """Start the runtime and return a backend-owned instance handle."""

    @abstractmethod
    def wait_adb(self, instance: Mapping[str, Any], timeout_seconds: float) -> str:
        """Wait for ADB and return the exact serial."""

    @abstractmethod
    def wait_android_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        """Wait for framework/package-manager readiness."""

    @abstractmethod
    def wait_game_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        """Wait for the exact game package and foreground component."""

    @abstractmethod
    def wait_observer_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        """Wait for the local semantic observer contract."""

    @abstractmethod
    def fingerprint(self, instance: Mapping[str, Any]) -> Mapping[str, Any]:
        """Collect runtime identity used to join evidence safely."""

    @abstractmethod
    def restart_game(self, instance: Mapping[str, Any]) -> None:
        """Restart only the game process."""

    @abstractmethod
    def restart_android(self, instance: Mapping[str, Any]) -> None:
        """Restart the Android userspace/runtime."""

    def wait_recovered_game_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        """Wait for a restarted game without implicitly restarting it again."""

        return self.wait_game_ready(instance, timeout_seconds)

    def wait_android_offline(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        """Require an observable ADB disconnect after an Android restart."""

        raise NotImplementedError("backend does not expose an Android restart boundary")

    def supports_recovery(self, recovery: str) -> bool:
        """Declare whether one explicit recovery mutation is executable."""

        return False

    @abstractmethod
    def stop(self, instance: Mapping[str, Any]) -> None:
        """Stop the runtime without deleting persistent data."""

    def collect_host_metrics(self, instance: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self.profile.capabilities.host_metrics:
            return {}
        raise NotImplementedError("backend declares host metrics but did not implement them")

    def qualification_plan(
        self, runtime_lock: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Describe lifecycle effects without probing, starting, or mutating."""

        return {
            "schema": "alas-headless.runtime-qualification-plan/v1",
            "backend": self.profile.backend.value,
            "profile_id": self.profile.profile_id,
            "phases": list(self.profile.lifecycle_phases),
            "state_changes": [],
        }


class RuntimeBackendRegistry:
    """Select one backend once; never silently switch an active run."""

    DEFAULT_AUTO_ORDER = (
        BackendKind.KVM,
        BackendKind.REDROID,
        BackendKind.EXTERNAL_ADB,
        BackendKind.TCG,
        BackendKind.ARM64_QEMU,
    )

    def __init__(self) -> None:
        self._backends: Dict[BackendKind, RuntimeBackend] = {}
        self._selection: Optional[RuntimeSelection] = None

    def register(self, backend: RuntimeBackend) -> None:
        kind = backend.profile.backend
        if kind in self._backends:
            raise ValueError("runtime backend already registered: {0}".format(kind.value))
        self._backends[kind] = backend

    @property
    def selection(self) -> Optional[RuntimeSelection]:
        return self._selection

    def select(
        self,
        requested: str,
        auto_order: Optional[Sequence[BackendKind]] = None,
    ) -> RuntimeBackend:
        if self._selection is not None:
            if requested not in ("auto", self._selection.backend.value):
                raise RuntimeError("runtime backend selection is already frozen")
            return self._backends[self._selection.backend]

        candidates: Iterable[BackendKind]
        if requested == "auto":
            candidates = auto_order or self.DEFAULT_AUTO_ORDER
        else:
            try:
                candidates = (BackendKind(requested),)
            except ValueError as exc:
                raise ValueError("unknown runtime backend: {0}".format(requested)) from exc

        failures = []
        for kind in candidates:
            backend = self._backends.get(kind)
            if backend is None:
                failures.append("{0}: not registered".format(kind.value))
                continue
            probe = backend.probe_host()
            if probe.backend != kind:
                raise RuntimeError("runtime backend returned a mismatched probe identity")
            if not probe.available:
                failures.append("{0}: {1}".format(kind.value, probe.reason))
                continue
            self._selection = RuntimeSelection(
                schema=RUNTIME_BACKEND_SCHEMA,
                backend=kind,
                profile_id=backend.profile.profile_id,
                host_fingerprint=dict(probe.host_fingerprint),
            )
            return backend
        raise RuntimeError("no runtime backend is available ({0})".format("; ".join(failures)))


def built_in_backend_profiles() -> Mapping[BackendKind, RuntimeBackendProfile]:
    """Return conservative profiles with no experimental tuning parameters."""

    return {
        BackendKind.KVM: RuntimeBackendProfile(
            BackendKind.KVM,
            "kvm-default-v1",
            RuntimeCapabilities(True, True, True, True, True, True),
            required_host_features=("kvm", "adb"),
            backend_options={"storage_model": "golden-avd-plus-userdata"},
        ),
        BackendKind.REDROID: RuntimeBackendProfile(
            BackendKind.REDROID,
            "redroid-default-v1",
            RuntimeCapabilities(True, True, False, True, True, True),
            required_host_features=("binderfs", "cgroup-v2", "adb"),
            backend_options={"storage_model": "oci-plus-persistent-data"},
        ),
        BackendKind.TCG: RuntimeBackendProfile(
            BackendKind.TCG,
            "tcg-frozen-v1",
            RuntimeCapabilities(True, True, True, True, True, False),
            required_host_features=("qemu", "adb"),
            backend_options={"optimization_policy": "frozen-until-real-workload"},
        ),
        BackendKind.ARM64_QEMU: RuntimeBackendProfile(
            BackendKind.ARM64_QEMU,
            "arm64-qemu-default-v1",
            RuntimeCapabilities(True, True, True, False, True, False),
            required_host_features=("qemu-system-aarch64", "adb"),
            backend_options={"storage_model": "payload-disk-plus-userdata"},
        ),
        BackendKind.EXTERNAL_ADB: RuntimeBackendProfile(
            BackendKind.EXTERNAL_ADB,
            "external-adb-default-v1",
            RuntimeCapabilities(False, False, False, False, False, True),
            required_host_features=("adb",),
            backend_options={"device_ownership": "external"},
        ),
    }
