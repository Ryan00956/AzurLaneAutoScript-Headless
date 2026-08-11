import tempfile
import unittest
from pathlib import Path

from alas_headless.runtime_backend import (
    BackendKind,
    RuntimeBackend,
    RuntimeProbeResult,
    built_in_backend_profiles,
)
from alas_headless.runtime_evidence import index_runtime_evidence
from alas_headless.runtime_qualification import RuntimeQualificationRunner
from tests.test_runtime_backends import make_lock


class QualificationBackend(RuntimeBackend):
    def __init__(
        self,
        runtime_lock,
        available=True,
        stop_failure=False,
        observed_android_fingerprint=None,
    ):
        super().__init__(built_in_backend_profiles()[BackendKind.EXTERNAL_ADB])
        self.runtime_lock = runtime_lock
        self.host_class = "android-arm64-test"
        self.available = available
        self.stop_failure = stop_failure
        self.observed_android_fingerprint = observed_android_fingerprint
        self.calls = []
        self.trace = None
        self.recovery = None

    def probe_host(self):
        self.calls.append("probe-host")
        return RuntimeProbeResult(
            self.available,
            BackendKind.EXTERNAL_ADB,
            "ready" if self.available else "adb-device-unavailable",
        )

    def resolve_artifacts(self, runtime_lock):
        self.calls.append("resolve-artifacts")
        return {"lock": self.runtime_lock.sha256}

    def provision(self, artifacts):
        self.calls.append("provision")
        return dict(artifacts)

    def start(self, provisioned):
        self.calls.append("start")
        return {"instance_id": "test", "owned": False}

    def wait_adb(self, instance, timeout_seconds):
        self.calls.append("adb-ready")
        return "test"

    def wait_android_ready(self, instance, timeout_seconds):
        self.calls.append("android-ready")
        return {"ready": True}

    def wait_game_ready(self, instance, timeout_seconds):
        self.calls.append("game-ready")
        return {
            "pid": 2222 if self.recovery is not None else 1111,
            "component": "test/component",
        }

    def wait_observer_ready(self, instance, timeout_seconds):
        self.calls.append("observer-ready")
        return {
            "pid": 2222 if self.recovery is not None else 1111,
            "generation": 3 if self.recovery is not None else 20,
            "observer_schema": "alas-headless.observer/v1",
            "atomic": True,
        }

    def fingerprint(self, instance):
        self.calls.append("fingerprint")
        document = self.runtime_lock.document
        return {
            "backend": "external-adb",
            "host_class": self.host_class,
            "android_fingerprint": (
                self.observed_android_fingerprint
                or document["android"]["build_fingerprint"]
            ),
            "game_version": document["game"]["version_name"],
            "game_abi": document["game"]["abi"],
            "libil2cpp_sha256": document["game"]["libil2cpp_sha256"],
            "angle_sha256": document["angle"]["apk_sha256"],
            "observer_schema": document["angle"]["observer_schema"],
            "core_commit": document["core"]["core_commit"],
            "runtime_lock_sha256": self.runtime_lock.sha256,
        }

    def restart_game(self, instance):
        self.calls.append("restart-game")
        self.recovery = "game"

    def restart_android(self, instance):
        self.calls.append("restart-android")
        self.recovery = "android"

    def wait_recovered_game_ready(self, instance, timeout_seconds):
        self.calls.append("game-recovered")
        return {"pid": 2222, "component": "test/component"}

    def wait_android_offline(self, instance, timeout_seconds):
        self.calls.append("adb-offline")
        return {"adb_offline_observed": True}

    def supports_recovery(self, recovery):
        return recovery in ("game", "android")

    def stop(self, instance):
        self.calls.append("stop")
        if self.stop_failure:
            raise RuntimeError("cleanup failed")


class RuntimeQualificationTests(unittest.TestCase):
    def test_success_manifest_is_indexable_and_stops_instance(self):
        lock = make_lock("external-adb")
        backend = QualificationBackend(lock)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            manifest = RuntimeQualificationRunner(backend, lock, output).qualify()
            self.assertEqual(manifest["outcome"], "pass")
            self.assertEqual(backend.calls[-1], "stop")
            self.assertTrue((output / "runtime-trace.jsonl").is_file())
            index = index_runtime_evidence([Path(directory)])
            self.assertEqual(
                index["fingerprints"][0]["gates"]["runtime-lifecycle"]["outcome"],
                "pass",
            )

    def test_probe_failure_writes_fail_manifest_without_start(self):
        lock = make_lock("external-adb")
        backend = QualificationBackend(lock, available=False)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            manifest = RuntimeQualificationRunner(backend, lock, output).qualify()
            self.assertEqual(manifest["outcome"], "fail")
            self.assertEqual(
                manifest["failure_code"],
                "backend-probe-adb-device-unavailable",
            )
            self.assertEqual(backend.calls, ["probe-host"])
            self.assertTrue((output / "manifest.json").is_file())

    def test_cleanup_failure_downgrades_success(self):
        lock = make_lock("external-adb")
        backend = QualificationBackend(lock, stop_failure=True)
        with tempfile.TemporaryDirectory() as directory:
            manifest = RuntimeQualificationRunner(
                backend, lock, Path(directory) / "run"
            ).qualify()
            self.assertEqual(manifest["outcome"], "fail")
            self.assertEqual(manifest["cleanup_failure_code"], "runtime-error")

    def test_observed_identity_mismatch_is_indexed_under_observed_runtime(self):
        lock = make_lock("external-adb")
        backend = QualificationBackend(
            lock, observed_android_fingerprint="other/android/build"
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            manifest = RuntimeQualificationRunner(backend, lock, output).qualify()
            self.assertEqual(manifest["outcome"], "fail")
            self.assertEqual(
                manifest["failure_code"],
                "observed-runtime-fingerprint-mismatch",
            )
            self.assertEqual(
                manifest["runtime_fingerprint"]["android_fingerprint"],
                "other/android/build",
            )
            self.assertEqual(
                manifest["expected_runtime_fingerprint"]["android_fingerprint"],
                "test/android/build",
            )
            index = index_runtime_evidence([Path(directory)])
            self.assertEqual(
                index["fingerprints"][0]["runtime_fingerprint"][
                    "android_fingerprint"
                ],
                "other/android/build",
            )

    def test_game_recovery_requires_a_new_pid_and_preserves_fingerprint(self):
        lock = make_lock("external-adb")
        backend = QualificationBackend(lock)
        with tempfile.TemporaryDirectory() as directory:
            manifest = RuntimeQualificationRunner(
                backend, lock, Path(directory) / "run"
            ).qualify("game")
            self.assertEqual(manifest["outcome"], "pass")
            self.assertEqual(manifest["gate"], "runtime-recovery-game")
            self.assertTrue(manifest["recovery"]["game_pid_changed"])
            self.assertTrue(
                manifest["recovery"]["runtime_fingerprint_preserved"]
            )
            self.assertIn("restart-game", backend.calls)
            self.assertIn("game-recovered", backend.calls)

    def test_android_recovery_observes_offline_boundary_before_readiness(self):
        lock = make_lock("external-adb")
        backend = QualificationBackend(lock)
        with tempfile.TemporaryDirectory() as directory:
            manifest = RuntimeQualificationRunner(
                backend, lock, Path(directory) / "run"
            ).qualify("android")
            self.assertEqual(manifest["outcome"], "pass")
            self.assertEqual(manifest["gate"], "runtime-recovery-android")
            restart = backend.calls.index("restart-android")
            offline = backend.calls.index("adb-offline")
            recovered_adb = backend.calls.index("adb-ready", restart + 1)
            self.assertLess(restart, offline)
            self.assertLess(offline, recovered_adb)


if __name__ == "__main__":
    unittest.main()
