"""Linux KVM Android Emulator reference backend."""

from __future__ import annotations

import math
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .runtime_backend import BackendKind, RuntimeProbeResult, built_in_backend_profiles
from .runtime_backend_adb import (
    AdbAttachedBackend,
    RuntimeBackendNotReady,
    _PACKAGE_PATTERN,
    _validate_adb_identity,
)
from .runtime_command import (
    RuntimeCommandExecutor,
    RuntimeCommandSpec,
    RuntimeOwnedProcess,
)
from .runtime_trace import RuntimeTraceRecorder


@dataclass(frozen=True)
class KvmRuntimeConfig:
    serial: str
    package: str
    component: str
    host_class: str
    emulator: Path
    emulator_check: Path
    adb: Path
    avd_name: str
    avd_home: Path
    console_port: int
    sdk_root: Optional[Path] = None
    angle_package: str = "org.chromium.angle"
    unity_command_line: Optional[str] = "-force-gfx-st"
    launch_game: bool = True
    manage_angle_routing: bool = False
    poll_interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        _validate_adb_identity(self.serial, self.package, self.component)
        if _PACKAGE_PATTERN.fullmatch(self.angle_package) is None:
            raise ValueError("ANGLE package is malformed")
        if self.unity_command_line not in (None, "-force-gfx-st"):
            raise ValueError("Unity command line is not allowlisted")
        if (
            not isinstance(self.host_class, str)
            or not self.host_class.strip()
            or not isinstance(self.avd_name, str)
            or not self.avd_name.strip()
        ):
            raise ValueError("KVM host class and AVD name cannot be empty")
        for path in (self.emulator, self.emulator_check, self.adb, self.avd_home):
            if not isinstance(path, Path):
                raise ValueError("KVM runtime paths must be pathlib.Path values")
        if self.sdk_root is not None and not isinstance(self.sdk_root, Path):
            raise ValueError("KVM SDK root must be a pathlib.Path value")
        if not isinstance(self.launch_game, bool) or not isinstance(
            self.manage_angle_routing, bool
        ):
            raise ValueError("KVM launch switches must be boolean")
        if self.manage_angle_routing and not self.launch_game:
            raise ValueError("managed ANGLE routing requires launch_game")
        if (
            isinstance(self.console_port, bool)
            or not isinstance(self.console_port, int)
            or not 5554 <= self.console_port <= 5680
            or self.console_port % 2
        ):
            raise ValueError("KVM emulator console port must be even and in [5554, 5680]")
        if self.serial != "emulator-{0}".format(self.console_port):
            raise ValueError("KVM serial must match its emulator console port")
        if (
            isinstance(self.poll_interval_seconds, bool)
            or not isinstance(self.poll_interval_seconds, (int, float))
            or not math.isfinite(float(self.poll_interval_seconds))
            or self.poll_interval_seconds <= 0
        ):
            raise ValueError("KVM polling interval must be positive")


def probe_linux_kvm() -> Tuple[bool, str, Mapping[str, str]]:
    if os.name != "posix":
        return False, "linux-required", {"platform": os.name}
    path = Path("/dev/kvm")
    try:
        mode = path.stat().st_mode
    except OSError:
        return False, "kvm-device-missing", {"platform": os.name}
    if not stat.S_ISCHR(mode):
        return False, "kvm-device-not-character", {"platform": os.name}
    if not os.access(str(path), os.R_OK | os.W_OK):
        return False, "kvm-device-permission-denied", {"platform": os.name}
    try:
        import fcntl

        descriptor = os.open(str(path), os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        try:
            api_version = int(fcntl.ioctl(descriptor, 0xAE00, 0))
        finally:
            os.close(descriptor)
    except (ImportError, OSError) as exc:
        return False, "kvm-ioctl-failed", {
            "platform": os.name,
            "exception_type": type(exc).__name__,
        }
    if api_version != 12:
        return False, "kvm-api-version-unexpected", {
            "platform": os.name,
            "kvm_api_version": str(api_version),
        }
    return True, "ready", {
        "platform": os.name,
        "kvm_api_version": str(api_version),
    }


class KvmBackend(AdbAttachedBackend):
    def __init__(
        self,
        config: KvmRuntimeConfig,
        executor: RuntimeCommandExecutor,
        trace: Optional[RuntimeTraceRecorder] = None,
        kvm_probe: Callable[[], Tuple[bool, str, Mapping[str, str]]] = probe_linux_kvm,
        **kwargs: Any
    ) -> None:
        self.config = config
        self.kvm_probe = kvm_probe
        self._owned_processes: Dict[str, RuntimeOwnedProcess] = {}
        super().__init__(
            built_in_backend_profiles()[BackendKind.KVM],
            config.serial,
            config.package,
            config.component,
            config.host_class,
            str(config.adb),
            config.angle_package,
            config.unity_command_line,
            config.manage_angle_routing,
            executor,
            config.launch_game,
            config.poll_interval_seconds,
            trace=trace,
            **kwargs
        )

    @property
    def avd_config_path(self) -> Path:
        return self.config.avd_home / (self.config.avd_name + ".avd") / "config.ini"

    def probe_host(self) -> RuntimeProbeResult:
        available, reason, fingerprint = self.kvm_probe()
        required = (
            self.config.emulator,
            self.config.emulator_check,
            self.config.adb,
            self.avd_config_path,
        )
        missing = [str(path) for path in required if not Path(path).is_file()]
        if missing:
            available = False
            reason = "kvm-runtime-path-missing"
        if available:
            acceleration = self.executor.run(
                RuntimeCommandSpec(
                    "emulator-acceleration-check",
                    (str(self.config.emulator_check), "accel"),
                    timeout_seconds=30.0,
                )
            )
            if not acceleration.succeeded:
                available = False
                reason = "emulator-acceleration-check-failed"
        host_fingerprint = dict(fingerprint)
        host_fingerprint["host_class"] = self.host_class
        if missing:
            host_fingerprint["missing_path_count"] = str(len(missing))
        return RuntimeProbeResult(available, BackendKind.KVM, reason, host_fingerprint)

    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        provisioned = super().provision(artifacts)
        if not self.avd_config_path.is_file():
            raise RuntimeBackendNotReady("kvm-avd-config-missing")
        provisioned.update(
            {
                "avd_name": self.config.avd_name,
                "avd_config": str(self.avd_config_path.resolve()),
            }
        )
        return provisioned

    def start(self, provisioned: Mapping[str, Any]) -> Mapping[str, Any]:
        devices = self.executor.run(
            RuntimeCommandSpec(
                "adb-device-inventory",
                (str(self.config.adb), "devices"),
                timeout_seconds=10.0,
            )
        )
        if not devices.succeeded:
            raise RuntimeBackendNotReady("adb-device-inventory-failed")
        for line in devices.stdout.splitlines()[1:]:
            columns = line.split()
            if columns and columns[0] == self.serial:
                raise RuntimeBackendNotReady("emulator-serial-already-in-use")
        environment = {"ANDROID_AVD_HOME": str(self.config.avd_home.resolve())}
        if self.config.sdk_root is not None:
            environment["ANDROID_SDK_ROOT"] = str(self.config.sdk_root.resolve())
        arguments = (
            str(self.config.emulator),
            "-avd",
            self.config.avd_name,
            "-port",
            str(self.config.console_port),
            "-no-window",
            "-no-audio",
            "-no-boot-anim",
            "-no-snapshot-load",
            "-no-snapshot-save",
            "-gpu",
            "swiftshader_indirect",
            "-accel",
            "on",
            "-camera-back",
            "none",
            "-camera-front",
            "none",
            "-no-metrics",
        )
        instance_id = uuid.uuid4().hex
        process = self.executor.start(
            RuntimeCommandSpec(
                "kvm-emulator-start",
                arguments,
                timeout_seconds=30.0,
                mutating=True,
                environment=environment,
            ),
            handle_id=instance_id,
        )
        self._owned_processes[instance_id] = process
        return {
            "instance_id": instance_id,
            "serial": self.serial,
            "owned": True,
            "pid": process.pid,
        }

    def stop(self, instance: Mapping[str, Any]) -> None:
        cleanup_failure: Optional[Exception] = None
        try:
            self._restore_angle_routing(instance)
        except Exception as exc:
            cleanup_failure = exc
        try:
            self._close_observer(instance)
        except Exception as exc:
            if cleanup_failure is None:
                cleanup_failure = exc
        instance_id = str(instance.get("instance_id", ""))
        process = self._owned_processes.pop(instance_id, None)
        if process is not None:
            try:
                self._adb(
                    "emulator-stop",
                    ("emu", "kill"),
                    timeout_seconds=15.0,
                    mutating=True,
                )
            except Exception as exc:
                if cleanup_failure is None:
                    cleanup_failure = exc
            try:
                self.executor.stop_owned(process, timeout_seconds=30.0)
            except Exception as exc:
                if cleanup_failure is None:
                    cleanup_failure = exc
        if cleanup_failure is not None:
            raise cleanup_failure

    def restart_game(self, instance: Mapping[str, Any]) -> None:
        self._close_observer(instance)
        self._launch_game_process(
            instance,
            60.0,
            "game-force-stop",
            "game-relaunch",
        )

    def restart_android(self, instance: Mapping[str, Any]) -> None:
        self._close_observer(instance)
        result = self._adb("android-reboot", ("reboot",), mutating=True)
        self._require_success(result, "android-reboot-failed")

    def supports_recovery(self, recovery: str) -> bool:
        return recovery in ("game", "android")

    def qualification_plan(
        self, runtime_lock: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        plan = dict(super().qualification_plan(runtime_lock))
        plan["state_changes"] = [
            "start-owned-emulator",
            "launch-game" if self.launch_game else "observe-existing-game",
            "create-adb-forward",
            "stop-owned-emulator",
        ]
        plan["compatibility_start_profile"] = {
            "gpu": "swiftshader_indirect",
            "acceleration": "kvm",
            "snapshots": "load-save-disabled-for-qualification",
            "experimental_tuning": False,
        }
        plan["game_launch_profile"] = {
            "force_stop_before_launch": self.launch_game,
            "unity_command_line": self.unity_command_line,
            "angle_routing": (
                "managed-ephemeral" if self.manage_angle_routing else "verify-only"
            ),
        }
        if self.manage_angle_routing:
            plan["state_changes"].insert(1, "temporarily-set-and-restore-angle-routing")
        return plan
