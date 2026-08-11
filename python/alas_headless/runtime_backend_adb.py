"""Shared ADB lifecycle and the external-device reference backend."""

from __future__ import annotations

import hashlib
import math
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from .runtime_artifacts import RuntimeLock
from .runtime_backend import (
    BackendKind,
    RuntimeBackend,
    RuntimeBackendProfile,
    RuntimeProbeResult,
    built_in_backend_profiles,
)
from .runtime_command import (
    RuntimeCommandExecutor,
    RuntimeCommandResult,
    RuntimeCommandSpec,
)
from .runtime_trace import RuntimeTraceRecorder
from .semantic_oracle import (
    AdbObserverBridge,
    AndroidPackageFingerprint,
    BUTTON_SCHEMA,
    OBSERVER_SCHEMA,
    request_observer_state,
)


class RuntimeBackendError(RuntimeError):
    def __init__(self, code: str) -> None:
        if (
            not isinstance(code, str)
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", code) is None
        ):
            raise ValueError("runtime backend error code is malformed")
        super().__init__(code)
        self.code = code


class RuntimeBackendNotReady(RuntimeBackendError):
    pass


class RuntimeIdentityMismatch(RuntimeBackendError):
    pass


_SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")


def _validate_adb_identity(serial: str, package: str, component: str) -> None:
    if not all(isinstance(value, str) for value in (serial, package, component)):
        raise ValueError("ADB identity fields must be text")
    if _SERIAL_PATTERN.fullmatch(serial) is None:
        raise ValueError("ADB serial is malformed")
    if _PACKAGE_PATTERN.fullmatch(package) is None:
        raise ValueError("Android package is malformed")
    if not component.startswith(package + "/") or any(char.isspace() for char in component):
        raise ValueError("Android component is malformed")


@dataclass(frozen=True)
class ExternalAdbConfig:
    serial: str
    package: str
    component: str
    host_class: str
    adb: str = "adb"
    angle_package: str = "org.chromium.angle"
    unity_command_line: Optional[str] = None
    launch_game: bool = False
    manage_angle_routing: bool = False
    allow_game_restart: bool = False
    allow_android_restart: bool = False
    poll_interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        _validate_adb_identity(self.serial, self.package, self.component)
        if _PACKAGE_PATTERN.fullmatch(self.angle_package) is None:
            raise ValueError("ANGLE package is malformed")
        if self.unity_command_line not in (None, "-force-gfx-st"):
            raise ValueError("Unity command line is not allowlisted")
        if not isinstance(self.host_class, str) or not self.host_class.strip():
            raise ValueError("external ADB host class cannot be empty")
        if not isinstance(self.adb, str) or not self.adb:
            raise ValueError("external ADB executable cannot be empty")
        for value in (
            self.launch_game,
            self.manage_angle_routing,
            self.allow_game_restart,
            self.allow_android_restart,
        ):
            if not isinstance(value, bool):
                raise ValueError("external ADB feature switches must be booleans")
        if self.manage_angle_routing and not self.launch_game:
            raise ValueError("managed ANGLE routing requires launch_game")
        if (
            isinstance(self.poll_interval_seconds, bool)
            or not isinstance(self.poll_interval_seconds, (int, float))
            or not math.isfinite(float(self.poll_interval_seconds))
            or self.poll_interval_seconds <= 0
        ):
            raise ValueError("ADB polling interval must be positive")



class AdbAttachedBackend(RuntimeBackend):
    """Shared read/identity path for externally owned and VM-backed Android."""

    def __init__(
        self,
        profile: RuntimeBackendProfile,
        serial: str,
        package: str,
        component: str,
        host_class: str,
        adb: str,
        angle_package: str,
        unity_command_line: Optional[str],
        manage_angle_routing: bool,
        executor: RuntimeCommandExecutor,
        launch_game: bool,
        poll_interval_seconds: float,
        trace: Optional[RuntimeTraceRecorder] = None,
        bridge_factory: Callable[..., AdbObserverBridge] = AdbObserverBridge,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(profile)
        self.serial = serial
        self.package = package
        self.component = component
        self.host_class = host_class
        self.adb = adb
        self.angle_package = angle_package
        self.unity_command_line = unity_command_line
        self.manage_angle_routing = manage_angle_routing
        self.executor = executor
        self.launch_game = bool(launch_game)
        self.poll_interval_seconds = poll_interval_seconds
        self.trace = trace
        self.bridge_factory = bridge_factory
        self.monotonic = monotonic
        self.sleep = sleep
        self._runtime_lock: Optional[RuntimeLock] = None
        self._bridges: Dict[str, AdbObserverBridge] = {}
        self._original_angle_settings: Dict[str, Mapping[str, Optional[str]]] = {}

    _ANGLE_SETTINGS = (
        "angle_debug_package",
        "angle_gl_driver_selection_pkgs",
        "angle_gl_driver_selection_values",
        "show_angle_in_use_dialog_box",
    )

    def _adb_spec(
        self,
        label: str,
        arguments: Sequence[str],
        timeout_seconds: float = 30.0,
        mutating: bool = False,
    ) -> RuntimeCommandSpec:
        return RuntimeCommandSpec(
            label,
            tuple([self.adb, "-s", self.serial] + list(arguments)),
            timeout_seconds=timeout_seconds,
            mutating=mutating,
        )

    def _adb(
        self,
        label: str,
        arguments: Sequence[str],
        timeout_seconds: float = 30.0,
        mutating: bool = False,
    ) -> RuntimeCommandResult:
        return self.executor.run(
            self._adb_spec(label, arguments, timeout_seconds, mutating)
        )

    @staticmethod
    def _require_success(result: RuntimeCommandResult, failure_code: str) -> str:
        if not result.succeeded:
            raise RuntimeBackendNotReady(failure_code)
        return result.stdout.strip()

    def _wait_for(
        self,
        timeout_seconds: float,
        operation: Callable[[], Optional[Mapping[str, Any]]],
        failure_code: str,
    ) -> Mapping[str, Any]:
        deadline = self.monotonic() + timeout_seconds
        while True:
            value = operation()
            if value is not None:
                return value
            if self.monotonic() >= deadline:
                raise RuntimeBackendNotReady(failure_code)
            self.sleep(min(self.poll_interval_seconds, max(0.0, deadline - self.monotonic())))

    def _read_angle_settings(self) -> Mapping[str, Optional[str]]:
        values: Dict[str, Optional[str]] = {}
        for name in self._ANGLE_SETTINGS:
            output = self._require_success(
                self._adb(
                    "angle-setting-read-" + name.replace("_", "-"),
                    ("shell", "settings", "get", "global", name),
                ),
                "angle-routing-unavailable",
            )
            values[name] = None if output in ("", "null") else output
        return values

    def _expected_angle_settings(self) -> Mapping[str, str]:
        return {
            "angle_debug_package": self.angle_package,
            "angle_gl_driver_selection_pkgs": self.package,
            "angle_gl_driver_selection_values": "angle",
            "show_angle_in_use_dialog_box": "0",
        }

    def _write_angle_setting(self, name: str, value: Optional[str]) -> None:
        operation = "delete" if value is None else "put"
        arguments = ["shell", "settings", operation, "global", name]
        if value is not None:
            arguments.append(value)
        result = self._adb(
            "angle-setting-{0}-{1}".format(operation, name.replace("_", "-")),
            tuple(arguments),
            mutating=True,
        )
        self._require_success(result, "angle-routing-update-failed")

    def _configure_angle_routing(self, instance: Mapping[str, Any]) -> None:
        instance_id = str(instance.get("instance_id", ""))
        if not instance_id:
            raise RuntimeBackendNotReady("angle-routing-ownership-invalid")
        current = self._read_angle_settings()
        if instance_id not in self._original_angle_settings:
            self._original_angle_settings[instance_id] = current
        for name, value in self._expected_angle_settings().items():
            if current.get(name) != value:
                self._write_angle_setting(name, value)
        if self._read_angle_settings() != self._expected_angle_settings():
            raise RuntimeIdentityMismatch("angle-routing-mismatch")

    def _restore_angle_routing(self, instance: Mapping[str, Any]) -> None:
        instance_id = str(instance.get("instance_id", ""))
        original = self._original_angle_settings.pop(instance_id, None)
        if original is None:
            return
        failed = False
        for name in self._ANGLE_SETTINGS:
            try:
                self._write_angle_setting(name, original[name])
            except Exception:
                failed = True
        try:
            if self._read_angle_settings() != original:
                failed = True
        except Exception:
            failed = True
        if failed:
            raise RuntimeBackendNotReady("angle-routing-restore-failed")

    def resolve_artifacts(self, runtime_lock: Mapping[str, Any]) -> Mapping[str, Any]:
        lock = (
            runtime_lock
            if isinstance(runtime_lock, RuntimeLock)
            else RuntimeLock.from_mapping(runtime_lock)
        )
        backend = lock.document["android"]["backend"]
        if backend != self.profile.backend.value:
            raise RuntimeIdentityMismatch("runtime-lock-backend-mismatch")
        if lock.document["game"]["package"] != self.package:
            raise RuntimeIdentityMismatch("runtime-lock-package-mismatch")
        self._runtime_lock = lock
        return {
            "runtime_lock_sha256": lock.sha256,
            "backend": backend,
            "resource_set_id": lock.document["resources"]["resource_set_id"],
            "userdata_generation": lock.document["userdata"]["generation"],
        }

    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._runtime_lock is None:
            raise RuntimeBackendNotReady("runtime-lock-not-resolved")
        return dict(artifacts)

    def start(self, provisioned: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "instance_id": uuid.uuid4().hex,
            "serial": self.serial,
            "owned": False,
        }

    def wait_adb(self, instance: Mapping[str, Any], timeout_seconds: float) -> str:
        def ready() -> Optional[Mapping[str, Any]]:
            result = self._adb("adb-get-state", ("get-state",), timeout_seconds=5.0)
            if result.succeeded and result.stdout.strip() == "device":
                return {"serial": self.serial}
            return None

        self._wait_for(timeout_seconds, ready, "adb-ready-timeout")
        return self.serial

    def wait_android_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        def ready() -> Optional[Mapping[str, Any]]:
            boot = self._adb(
                "android-boot-completed",
                ("shell", "getprop", "sys.boot_completed"),
                timeout_seconds=5.0,
            )
            packages = self._adb(
                "android-package-manager",
                ("shell", "cmd", "package", "path", "android"),
                timeout_seconds=10.0,
            )
            if (
                boot.succeeded
                and boot.stdout.strip() == "1"
                and packages.succeeded
                and packages.stdout.strip().startswith("package:")
            ):
                return {"boot_completed": True, "package_manager_ready": True}
            return None

        return self._wait_for(
            timeout_seconds, ready, "android-framework-ready-timeout"
        )

    def _launch_game_process(
        self,
        instance: Mapping[str, Any],
        timeout_seconds: float,
        force_stop_label: str,
        launch_label: str,
    ) -> None:
        if self.manage_angle_routing:
            self._configure_angle_routing(instance)
        if self._read_angle_settings() != self._expected_angle_settings():
            raise RuntimeIdentityMismatch("angle-routing-mismatch")
        force_stop = self._adb(
            force_stop_label,
            ("shell", "am", "force-stop", self.package),
            mutating=True,
        )
        self._require_success(force_stop, "game-force-stop-failed")
        launch_arguments = ["shell", "am", "start", "-W"]
        if self.unity_command_line is not None:
            launch_arguments.extend(("--es", "unity", self.unity_command_line))
        launch_arguments.extend(("-n", self.component))
        launch = self._adb(
            launch_label,
            tuple(launch_arguments),
            timeout_seconds=min(timeout_seconds, 60.0),
            mutating=True,
        )
        self._require_success(
            launch,
            (
                "game-relaunch-failed"
                if launch_label == "game-relaunch"
                else "game-launch-failed"
            ),
        )

    def _wait_game_foreground(
        self, timeout_seconds: float
    ) -> Mapping[str, Any]:
        def ready() -> Optional[Mapping[str, Any]]:
            pid_result = self._adb(
                "game-pid", ("shell", "pidof", self.package), timeout_seconds=5.0
            )
            activity = self._adb(
                "game-foreground",
                ("shell", "dumpsys", "activity", "activities"),
                timeout_seconds=10.0,
            )
            if not pid_result.succeeded or not pid_result.stdout.strip().isdigit():
                return None
            match = (
                AdbObserverBridge._FOREGROUND_PATTERN.search(activity.stdout)
                if activity.succeeded
                else None
            )
            if match is not None and match.group(1) == self.component:
                return {"pid": int(pid_result.stdout.strip()), "component": self.component}
            return None

        return self._wait_for(timeout_seconds, ready, "game-ready-timeout")

    def wait_game_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        if self.launch_game:
            self._launch_game_process(
                instance,
                timeout_seconds,
                "game-force-stop-before-launch",
                "game-launch",
            )
        return self._wait_game_foreground(timeout_seconds)

    def wait_recovered_game_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        return self._wait_game_foreground(timeout_seconds)

    def wait_android_offline(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        def offline() -> Optional[Mapping[str, Any]]:
            state = self._adb(
                "adb-restart-boundary",
                ("get-state",),
                timeout_seconds=5.0,
            )
            if not state.succeeded or state.stdout.strip() != "device":
                return {"adb_offline_observed": True}
            return None

        return self._wait_for(
            timeout_seconds, offline, "android-restart-boundary-timeout"
        )

    def wait_observer_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        instance_id = str(instance.get("instance_id", ""))
        if not instance_id:
            raise RuntimeBackendNotReady("runtime-instance-id-missing")
        bridge = self.bridge_factory(
            self.serial,
            self.package,
            adb=self.adb,
            command_timeout_seconds=min(120.0, max(1.0, timeout_seconds)),
            trace=self.trace,
        )
        try:
            bridge.open()
        except Exception:
            bridge.close()
            raise RuntimeBackendNotReady("observer-bridge-open-failed")
        if self._runtime_lock is None:
            bridge.close()
            raise RuntimeBackendNotReady("runtime-lock-not-resolved")
        expected_revision = self._runtime_lock.document["angle"]["revision"]

        def ready() -> Optional[Mapping[str, Any]]:
            try:
                snapshot, buttons, atomic = request_observer_state(bridge.request)
            except Exception:
                return None
            if not isinstance(snapshot, dict) or not isinstance(buttons, dict):
                raise RuntimeBackendNotReady("observer-state-contract-mismatch")
            if any(
                value.get("protocol_schema") != OBSERVER_SCHEMA
                for value in (snapshot, buttons)
            ):
                raise RuntimeBackendNotReady("observer-protocol-schema-mismatch")
            if any(value.get("status") != "ok" for value in (snapshot, buttons)):
                return None
            if any(
                value.get("package") != self.package
                for value in (snapshot, buttons)
            ):
                raise RuntimeBackendNotReady("observer-package-mismatch")
            if any(value.get("pid") != bridge.pid for value in (snapshot, buttons)):
                raise RuntimeBackendNotReady("observer-pid-mismatch")
            if any(
                value.get("driver_revision") != expected_revision
                for value in (snapshot, buttons)
            ):
                raise RuntimeBackendNotReady("observer-driver-revision-mismatch")
            if snapshot.get("snapshot_schema") != 1:
                raise RuntimeBackendNotReady("observer-snapshot-schema-mismatch")
            if (
                buttons.get("semantic_schema") != BUTTON_SCHEMA
                or buttons.get("schema") != 1
            ):
                raise RuntimeBackendNotReady("observer-button-schema-mismatch")
            snapshot_generation = snapshot.get("generation")
            button_generation = buttons.get("generation")
            coherent = (
                isinstance(snapshot_generation, int)
                and not isinstance(snapshot_generation, bool)
                and isinstance(button_generation, int)
                and not isinstance(button_generation, bool)
                and (
                    button_generation == snapshot_generation
                    if atomic
                    else snapshot_generation <= button_generation <= snapshot_generation + 2
                )
            )
            if not coherent:
                return None
            return {
                "pid": bridge.pid,
                "generation": snapshot_generation,
                "observer_schema": OBSERVER_SCHEMA,
                "atomic": atomic,
            }

        try:
            state = self._wait_for(timeout_seconds, ready, "observer-ready-timeout")
        except Exception:
            bridge.close()
            raise
        self._bridges[instance_id] = bridge
        return state

    def fingerprint(self, instance: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._runtime_lock is None:
            raise RuntimeBackendNotReady("runtime-lock-not-resolved")
        instance_id = str(instance.get("instance_id", ""))
        bridge = self._bridges.get(instance_id)
        if bridge is None:
            raise RuntimeBackendNotReady("observer-bridge-not-open")
        package_fingerprint = bridge.package_fingerprint()
        android_fingerprint = self._require_success(
            self._adb(
                "android-build-fingerprint",
                ("shell", "getprop", "ro.build.fingerprint"),
            ),
            "android-fingerprint-unavailable",
        )
        android_abi = self._require_success(
            self._adb(
                "android-primary-abi",
                ("shell", "getprop", "ro.product.cpu.abi"),
            ),
            "android-abi-unavailable",
        )
        api_level = self._require_success(
            self._adb(
                "android-api-level",
                ("shell", "getprop", "ro.build.version.sdk"),
            ),
            "android-api-unavailable",
        )
        angle_path_output = self._require_success(
            self._adb(
                "angle-package-path",
                ("shell", "pm", "path", self.angle_package),
            ),
            "angle-package-unavailable",
        )
        angle_paths = [
            line[len("package:") :]
            for line in angle_path_output.splitlines()
            if line.startswith("package:")
        ]
        if len(angle_paths) != 1 or re.fullmatch(
            r"/[A-Za-z0-9._/+=:@~-]+", angle_paths[0]
        ) is None:
            raise RuntimeIdentityMismatch("angle-package-path-mismatch")
        angle_sha256_output = self._require_success(
            self._adb(
                "angle-apk-sha256",
                ("shell", "sha256sum", angle_paths[0]),
                timeout_seconds=120.0,
            ),
            "angle-package-hash-unavailable",
        )
        angle_sha256_match = re.match(r"^([0-9a-fA-F]{64})(?:\s|$)", angle_sha256_output)
        if angle_sha256_match is None:
            raise RuntimeIdentityMismatch("angle-package-hash-malformed")
        angle_sha256 = angle_sha256_match.group(1).lower()
        document = self._runtime_lock.document
        expected_package = AndroidPackageFingerprint(
            version_name=document["game"]["version_name"],
            version_code=document["game"]["version_code"],
            primary_abi=document["game"]["abi"],
            base_apk_sha256=document["game"]["base_apk_sha256"],
            il2cpp_sha256=document["game"]["libil2cpp_sha256"],
        )
        if package_fingerprint != expected_package:
            raise RuntimeIdentityMismatch("game-package-fingerprint-mismatch")
        if (
            android_fingerprint != document["android"]["build_fingerprint"]
            or android_abi != document["android"]["abi"]
            or api_level != str(document["android"]["api_level"])
        ):
            raise RuntimeIdentityMismatch("android-runtime-fingerprint-mismatch")
        if angle_sha256 != document["angle"]["apk_sha256"]:
            raise RuntimeIdentityMismatch("angle-package-fingerprint-mismatch")
        return {
            "backend": self.profile.backend.value,
            "host_class": self.host_class,
            "android_fingerprint": android_fingerprint,
            "game_version": package_fingerprint.version_name,
            "game_abi": package_fingerprint.primary_abi,
            "libil2cpp_sha256": package_fingerprint.il2cpp_sha256,
            "angle_sha256": angle_sha256,
            "observer_schema": document["angle"]["observer_schema"],
            "core_commit": document["core"]["core_commit"],
            "runtime_lock_sha256": self._runtime_lock.sha256,
        }

    def restart_game(self, instance: Mapping[str, Any]) -> None:
        raise RuntimeBackendNotReady("game-restart-not-enabled")

    def restart_android(self, instance: Mapping[str, Any]) -> None:
        raise RuntimeBackendNotReady("android-restart-not-enabled")

    def _close_observer(self, instance: Mapping[str, Any]) -> None:
        instance_id = str(instance.get("instance_id", ""))
        bridge = self._bridges.pop(instance_id, None)
        if bridge is not None:
            bridge.close()

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
        if cleanup_failure is not None:
            raise cleanup_failure

    def qualification_plan(
        self, runtime_lock: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return {
            "schema": "alas-headless.runtime-qualification-plan/v1",
            "backend": self.profile.backend.value,
            "profile_id": self.profile.profile_id,
            "serial_sha256": hashlib.sha256(self.serial.encode("utf-8")).hexdigest(),
            "phases": [
                "resolve-artifacts",
                "provision",
                "start",
                "adb-ready",
                "android-ready",
                "game-ready",
                "observer-ready",
                "fingerprint",
                "stop",
            ],
            "state_changes": (
                (["launch-game"] if self.launch_game else [])
                + (
                    ["temporarily-set-and-restore-angle-routing"]
                    if self.manage_angle_routing
                    else []
                )
                + ["create-and-remove-adb-forward"]
            ),
            "commands": [
                "adb-get-state",
                "android-readiness",
                "game-readiness",
                "observer-forward",
                "runtime-fingerprint",
            ],
        }


class ExternalAdbBackend(AdbAttachedBackend):
    def __init__(
        self,
        config: ExternalAdbConfig,
        executor: RuntimeCommandExecutor,
        trace: Optional[RuntimeTraceRecorder] = None,
        **kwargs: Any
    ) -> None:
        self.config = config
        super().__init__(
            built_in_backend_profiles()[BackendKind.EXTERNAL_ADB],
            config.serial,
            config.package,
            config.component,
            config.host_class,
            config.adb,
            config.angle_package,
            config.unity_command_line,
            config.manage_angle_routing,
            executor,
            config.launch_game,
            config.poll_interval_seconds,
            trace=trace,
            **kwargs
        )

    def probe_host(self) -> RuntimeProbeResult:
        version = self.executor.run(
            RuntimeCommandSpec("adb-version", (self.adb, "version"), timeout_seconds=10.0)
        )
        state = self._adb("adb-get-state", ("get-state",), timeout_seconds=10.0)
        available = version.succeeded and state.succeeded and state.stdout.strip() == "device"
        return RuntimeProbeResult(
            available,
            BackendKind.EXTERNAL_ADB,
            "ready" if available else "adb-device-unavailable",
            {
                "host_class": self.host_class,
                "serial_sha256": hashlib.sha256(self.serial.encode("utf-8")).hexdigest(),
            },
        )

    def restart_game(self, instance: Mapping[str, Any]) -> None:
        if not self.config.allow_game_restart:
            super().restart_game(instance)
        self._close_observer(instance)
        self._launch_game_process(
            instance,
            60.0,
            "game-force-stop",
            "game-relaunch",
        )

    def restart_android(self, instance: Mapping[str, Any]) -> None:
        if not self.config.allow_android_restart:
            super().restart_android(instance)
        self._close_observer(instance)
        result = self._adb("android-reboot", ("reboot",), mutating=True)
        self._require_success(result, "android-reboot-failed")

    def supports_recovery(self, recovery: str) -> bool:
        return (
            recovery == "game" and self.config.allow_game_restart
        ) or (
            recovery == "android" and self.config.allow_android_restart
        )
