import unittest

from alas_headless.runtime_backend import (
    BackendKind,
    RuntimeBackend,
    RuntimeBackendRegistry,
    RuntimeProbeResult,
    built_in_backend_profiles,
)


class FakeBackend(RuntimeBackend):
    def __init__(self, kind, available, reason="probe complete"):
        super().__init__(built_in_backend_profiles()[kind])
        self.available = available
        self.reason = reason

    def probe_host(self):
        return RuntimeProbeResult(
            self.available,
            self.profile.backend,
            self.reason,
            {"host_class": "test"},
        )

    def resolve_artifacts(self, runtime_lock):
        return dict(runtime_lock)

    def provision(self, artifacts):
        return dict(artifacts)

    def start(self, provisioned):
        return {"id": "test"}

    def wait_adb(self, instance, timeout_seconds):
        return "test-serial"

    def wait_android_ready(self, instance, timeout_seconds):
        return {"ready": True}

    def wait_game_ready(self, instance, timeout_seconds):
        return {"ready": True}

    def wait_observer_ready(self, instance, timeout_seconds):
        return {"ready": True}

    def fingerprint(self, instance):
        return {"backend": self.profile.backend.value}

    def restart_game(self, instance):
        return None

    def restart_android(self, instance):
        return None

    def stop(self, instance):
        return None


class RuntimeBackendTests(unittest.TestCase):
    def test_profiles_keep_backend_specific_policy_out_of_common_contract(self):
        profiles = built_in_backend_profiles()
        self.assertEqual(set(profiles), set(BackendKind))
        self.assertEqual(
            profiles[BackendKind.TCG].backend_options["optimization_policy"],
            "frozen-until-real-workload",
        )
        self.assertTrue(profiles[BackendKind.KVM].capabilities.snapshot_restore)
        self.assertFalse(
            profiles[BackendKind.EXTERNAL_ADB].capabilities.persistent_userdata
        )

    def test_auto_selection_records_failures_and_freezes_winner(self):
        registry = RuntimeBackendRegistry()
        registry.register(FakeBackend(BackendKind.KVM, False, "KVM unavailable"))
        tcg = FakeBackend(BackendKind.TCG, True)
        registry.register(tcg)
        selected = registry.select(
            "auto", auto_order=(BackendKind.KVM, BackendKind.TCG)
        )
        self.assertIs(selected, tcg)
        self.assertEqual(registry.selection.backend, BackendKind.TCG)
        self.assertIs(registry.select("auto"), tcg)
        with self.assertRaises(RuntimeError):
            registry.select("kvm")

    def test_explicit_unavailable_backend_fails_closed(self):
        registry = RuntimeBackendRegistry()
        registry.register(FakeBackend(BackendKind.REDROID, False, "binderfs absent"))
        with self.assertRaisesRegex(RuntimeError, "binderfs absent"):
            registry.select("redroid")


if __name__ == "__main__":
    unittest.main()
