import json
import tempfile
import unittest
from pathlib import Path

from alas_headless.runtime_artifacts import RuntimeLock, resource_set_id
from alas_headless.runtime_backend import BackendKind
from alas_headless.runtime_backends import (
    DeferredRuntimeBackend,
    ExternalAdbBackend,
    ExternalAdbConfig,
    KvmBackend,
    KvmRuntimeConfig,
    RuntimeIdentityMismatch,
    backend_from_config,
)
from alas_headless.runtime_command import (
    RuntimeCommandResult,
    RuntimeExecutionPolicy,
    RuntimeOwnedProcess,
)
from alas_headless.semantic_oracle import AndroidPackageFingerprint


HASH = "a" * 64
COMMIT = "b" * 40
PACKAGE = "com.bilibili.azurlane"
COMPONENT = PACKAGE + "/com.manjuu.azurlane.MainActivity"


def make_lock(backend):
    manifest_hash = HASH
    abi = "arm64-v8a" if backend in ("external-adb", "arm64-qemu") else "x86_64"
    return RuntimeLock.from_mapping(
        {
            "schema": "alas-headless.runtime-lock/v1",
            "core": {
                "core_commit": COMMIT,
                "alas_upstream_commit": "c" * 40,
                "alas_patch_sha256": HASH,
            },
            "angle": {
                "revision": "d" * 40,
                "patchset_sha256": HASH,
                "abi": abi,
                "apk_sha256": HASH,
                "observer_schema": "alas-headless.observer/v1",
            },
            "android": {
                "backend": backend,
                "build_fingerprint": "test/android/build",
                "api_level": 35,
                "abi": abi,
                "system_image_sha256": HASH,
                "provision_profile_sha256": HASH,
            },
            "game": {
                "package": PACKAGE,
                "region": "cn",
                "version_name": "9.9.9",
                "version_code": 999,
                "abi": abi,
                "base_apk_sha256": HASH,
                "libil2cpp_sha256": HASH,
            },
            "resources": {
                "resource_set_id": resource_set_id("cn", "9.9.9", manifest_hash),
                "resource_epoch": 1,
                "manifest_sha256": manifest_hash,
                "shared_public_paths": ["game/public-assets"],
            },
            "userdata": {
                "generation": 1,
                "account_scope": (
                    "external-device" if backend == "external-adb" else "per-instance"
                ),
            },
        }
    )


class ScriptedExecutor:
    def __init__(self, results=None):
        self.results = dict(results or {})
        self.calls = []
        self.started = []
        self.stopped = []
        self.policy = RuntimeExecutionPolicy(True, True)

    def run(self, spec):
        self.calls.append(spec)
        value = self.results.get(spec.label, (0, "", ""))
        if isinstance(value, list):
            value = value.pop(0)
        return RuntimeCommandResult(spec.label, value[0], value[1], value[2], 1)

    def start(self, spec, handle_id):
        self.started.append(spec)
        return RuntimeOwnedProcess(handle_id, 4321, spec.label)

    def stop_owned(self, process, timeout_seconds=30.0):
        self.stopped.append(process)
        return 0


class FakeBridge:
    def __init__(self, serial, package, **kwargs):
        self.serial = serial
        self.package = package
        self.pid = 1234
        self.closed = False

    def open(self):
        return self

    def request(self, request):
        if request == "GET /v1/state\n":
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": {
                    "protocol_schema": "alas-headless.observer/v1",
                    "status": "ok",
                    "snapshot_schema": 1,
                    "package": PACKAGE,
                    "pid": 1234,
                    "driver_revision": "d" * 40,
                    "generation": 10,
                },
                "buttons": {
                    "protocol_schema": "alas-headless.observer/v1",
                    "semantic_schema": "alas-headless.buttons/v1",
                    "status": "ok",
                    "schema": 1,
                    "package": PACKAGE,
                    "pid": 1234,
                    "driver_revision": "d" * 40,
                    "generation": 10,
                },
            }
        raise AssertionError(request)

    def package_fingerprint(self):
        return AndroidPackageFingerprint("9.9.9", 999, "arm64-v8a", HASH, HASH)

    def close(self):
        self.closed = True


class FlakyObserverBridge(FakeBridge):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_count = 0

    def request(self, request):
        self.request_count += 1
        if self.request_count == 1:
            raise RuntimeError("observer is still starting")
        return super().request(request)


class StartingObserverBridge(FakeBridge):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_count = 0

    def request(self, request):
        self.request_count += 1
        value = super().request(request)
        if self.request_count == 1:
            value["snapshot"]["status"] = "initializing"
        return value


class RuntimeBackendsTests(unittest.TestCase):
    def test_external_adb_reference_backend_completes_read_only_identity_path(self):
        results = {
            "adb-version": (0, "Android Debug Bridge version 1", ""),
            "adb-get-state": (0, "device", ""),
            "android-boot-completed": (0, "1", ""),
            "android-package-manager": (0, "package:/system/framework/framework-res.apk", ""),
            "game-pid": (0, "1234", ""),
            "game-foreground": (
                0,
                "topResumedActivity=ActivityRecord{x u0 " + COMPONENT + " t1}",
                "",
            ),
            "android-build-fingerprint": (0, "test/android/build", ""),
            "android-primary-abi": (0, "arm64-v8a", ""),
            "android-api-level": (0, "35", ""),
            "angle-package-path": (
                0,
                "package:/data/app/~~install/org.chromium.angle/base.apk",
                "",
            ),
            "angle-apk-sha256": (0, HASH, ""),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1", PACKAGE, COMPONENT, "android-arm64-test"
            ),
            executor,
            bridge_factory=FakeBridge,
            sleep=lambda _: None,
        )
        lock = make_lock("external-adb")
        self.assertTrue(backend.probe_host().available)
        artifacts = backend.resolve_artifacts(lock)
        instance = backend.start(backend.provision(artifacts))
        self.assertEqual(backend.wait_adb(instance, 1.0), "device-1")
        self.assertTrue(backend.wait_android_ready(instance, 1.0)["boot_completed"])
        self.assertEqual(backend.wait_game_ready(instance, 1.0)["pid"], 1234)
        self.assertTrue(backend.wait_observer_ready(instance, 1.0)["atomic"])
        self.assertEqual(backend.fingerprint(instance)["backend"], "external-adb")
        backend.stop(instance)

        executor.results["angle-apk-sha256"] = (0, "b" * 64, "")
        mismatched = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1", PACKAGE, COMPONENT, "android-arm64-test"
            ),
            executor,
            bridge_factory=FakeBridge,
            sleep=lambda _: None,
        )
        mismatched.resolve_artifacts(lock)
        mismatch_instance = mismatched.start({})
        mismatched.wait_observer_ready(mismatch_instance, 1.0)
        with self.assertRaisesRegex(
            RuntimeIdentityMismatch, "angle-package-fingerprint-mismatch"
        ):
            mismatched.fingerprint(mismatch_instance)
        mismatched.stop(mismatch_instance)

    def test_kvm_backend_refuses_serial_reuse_and_uses_compatibility_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            emulator = root / "emulator"
            emulator_check = root / "emulator-check"
            adb = root / "adb"
            avd_home = root / "avd"
            config_path = avd_home / "test.avd" / "config.ini"
            config_path.parent.mkdir(parents=True)
            for path in (emulator, emulator_check, adb, config_path):
                path.write_text("test", encoding="utf-8")
            executor = ScriptedExecutor(
                {
                    "emulator-acceleration-check": (0, "accel: 0", ""),
                    "adb-device-inventory": (0, "List of devices attached\nemulator-5600\tdevice", ""),
                }
            )
            backend = KvmBackend(
                KvmRuntimeConfig(
                    "emulator-5600",
                    PACKAGE,
                    COMPONENT,
                    "linux-x86_64-kvm",
                    emulator,
                    emulator_check,
                    adb,
                    "test",
                    avd_home,
                    5600,
                ),
                executor,
                kvm_probe=lambda: (True, "ready", {"kvm_api_version": "12"}),
            )
            self.assertTrue(backend.probe_host().available)
            backend.resolve_artifacts(make_lock("kvm"))
            provisioned = backend.provision({"runtime_lock_sha256": HASH})
            with self.assertRaisesRegex(Exception, "emulator-serial-already-in-use"):
                backend.start(provisioned)
            plan = backend.qualification_plan(make_lock("kvm"))
            self.assertFalse(plan["compatibility_start_profile"]["experimental_tuning"])
            self.assertNotIn("vcpu", json.dumps(plan).lower())
            self.assertNotIn("mttcg", json.dumps(plan).lower())

    def test_observer_readiness_retries_transient_transport_failure(self):
        executor = ScriptedExecutor()
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1", PACKAGE, COMPONENT, "android-arm64-test"
            ),
            executor,
            bridge_factory=FlakyObserverBridge,
            sleep=lambda _: None,
        )
        backend.resolve_artifacts(make_lock("external-adb"))
        instance = backend.start({})
        state = backend.wait_observer_ready(instance, 1.0)
        self.assertTrue(state["atomic"])
        backend.stop(instance)

    def test_observer_readiness_retries_transient_non_ok_state(self):
        executor = ScriptedExecutor()
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1", PACKAGE, COMPONENT, "android-arm64-test"
            ),
            executor,
            bridge_factory=StartingObserverBridge,
            sleep=lambda _: None,
        )
        backend.resolve_artifacts(make_lock("external-adb"))
        instance = backend.start({})
        state = backend.wait_observer_ready(instance, 1.0)
        self.assertTrue(state["atomic"])
        backend.stop(instance)

    def test_game_launch_requires_pinned_angle_route_and_unity_command_line(self):
        results = {
            "angle-setting-read-angle-debug-package": (
                0,
                "org.chromium.angle",
                "",
            ),
            "angle-setting-read-angle-gl-driver-selection-pkgs": (
                0,
                PACKAGE,
                "",
            ),
            "angle-setting-read-angle-gl-driver-selection-values": (
                0,
                "angle",
                "",
            ),
            "angle-setting-read-show-angle-in-use-dialog-box": (0, "0", ""),
            "game-force-stop-before-launch": (0, "", ""),
            "game-launch": (0, "Status: ok", ""),
            "game-pid": (0, "1234", ""),
            "game-foreground": (
                0,
                "topResumedActivity=ActivityRecord{x u0 " + COMPONENT + " t1}",
                "",
            ),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                launch_game=True,
                unity_command_line="-force-gfx-st",
            ),
            executor,
            sleep=lambda _: None,
        )
        state = backend.wait_game_ready({"instance_id": "test"}, 1.0)
        self.assertEqual(state["pid"], 1234)
        launch = next(spec for spec in executor.calls if spec.label == "game-launch")
        self.assertIn("-force-gfx-st", launch.argv)
        self.assertTrue(launch.mutating)

        executor.results[
            "angle-setting-read-angle-gl-driver-selection-values"
        ] = (0, "native", "")
        with self.assertRaisesRegex(RuntimeIdentityMismatch, "angle-routing-mismatch"):
            backend.wait_game_ready({"instance_id": "test"}, 1.0)

    def test_game_recovery_reuses_pinned_unity_command_line(self):
        results = {
            "angle-setting-read-angle-debug-package": (0, "org.chromium.angle", ""),
            "angle-setting-read-angle-gl-driver-selection-pkgs": (0, PACKAGE, ""),
            "angle-setting-read-angle-gl-driver-selection-values": (0, "angle", ""),
            "angle-setting-read-show-angle-in-use-dialog-box": (0, "0", ""),
            "game-force-stop": (0, "", ""),
            "game-relaunch": (0, "Status: ok", ""),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                unity_command_line="-force-gfx-st",
                allow_game_restart=True,
            ),
            executor,
            sleep=lambda _: None,
        )
        self.assertTrue(backend.supports_recovery("game"))
        backend.restart_game({"instance_id": "test"})
        relaunch = next(
            spec for spec in executor.calls if spec.label == "game-relaunch"
        )
        self.assertIn("-force-gfx-st", relaunch.argv)
        self.assertTrue(relaunch.mutating)

    def test_managed_angle_route_is_restored_after_game_launch(self):
        results = {
            "angle-setting-read-angle-debug-package": [
                (0, "null", ""),
                (0, "org.chromium.angle", ""),
                (0, "org.chromium.angle", ""),
                (0, "null", ""),
            ],
            "angle-setting-read-angle-gl-driver-selection-pkgs": [
                (0, "other.package", ""),
                (0, PACKAGE, ""),
                (0, PACKAGE, ""),
                (0, "other.package", ""),
            ],
            "angle-setting-read-angle-gl-driver-selection-values": [
                (0, "native", ""),
                (0, "angle", ""),
                (0, "angle", ""),
                (0, "native", ""),
            ],
            "angle-setting-read-show-angle-in-use-dialog-box": [
                (0, "1", ""),
                (0, "0", ""),
                (0, "0", ""),
                (0, "1", ""),
            ],
            "game-force-stop-before-launch": (0, "", ""),
            "game-launch": (0, "Status: ok", ""),
            "game-pid": (0, "1234", ""),
            "game-foreground": (
                0,
                "topResumedActivity=ActivityRecord{x u0 " + COMPONENT + " t1}",
                "",
            ),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                launch_game=True,
                manage_angle_routing=True,
                unity_command_line="-force-gfx-st",
            ),
            executor,
            sleep=lambda _: None,
        )
        instance = backend.start({})
        backend.wait_game_ready(instance, 1.0)
        backend.stop(instance)
        labels = [spec.label for spec in executor.calls]
        self.assertIn("angle-setting-delete-angle-debug-package", labels)
        restored_packages = [
            spec
            for spec in executor.calls
            if spec.label
            == "angle-setting-put-angle-gl-driver-selection-pkgs"
        ]
        self.assertEqual(restored_packages[-1].argv[-1], "other.package")

    def test_deferred_backends_are_visible_but_never_available(self):
        backend = DeferredRuntimeBackend(
            BackendKind.REDROID, "redroid-adapter-not-implemented", "linux-redroid"
        )
        self.assertFalse(backend.probe_host().available)
        self.assertFalse(backend.qualification_plan({})["executable"])

    def test_config_factory_is_strict(self):
        executor = ScriptedExecutor()
        value = {
            "schema": "alas-headless.runtime-config/v1",
            "backend": "external-adb",
            "serial": "device-1",
            "package": PACKAGE,
            "component": COMPONENT,
            "host_class": "android-arm64-test",
        }
        self.assertIsInstance(backend_from_config(value, executor), ExternalAdbBackend)
        invalid = dict(value)
        invalid["unknown"] = True
        with self.assertRaises(ValueError):
            backend_from_config(invalid, executor)


if __name__ == "__main__":
    unittest.main()
