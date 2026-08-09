import unittest
from unittest.mock import patch

from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    AndroidPackageFingerprint,
    Bounds,
    PINNED_CN_GAME_FINGERPRINT,
    PinnedPackageGate,
    Point,
    SemanticGateClosed,
)
from alas_headless.semantic_oracle import ActionReceipt, AdbObserverBridge


class NamedButton:
    def __init__(self, name):
        self.name = name


class FakeOracle:
    def __init__(self):
        self.enabled_calls = []
        self.bounds_calls = []
        self.click_calls = []

    def enabled(self, semantic_id):
        self.enabled_calls.append(semantic_id)
        return True

    def bounds(self, semantic_id):
        self.bounds_calls.append(semantic_id)
        return Bounds(1, 2, 3, 4)

    def click(self, semantic_id):
        self.click_calls.append(semantic_id)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="root/target",
        )


class FakePackageBridge:
    def __init__(self):
        self.pid = 1234
        self.calls = []

    def require_package_fingerprint(self, expected):
        self.calls.append(expected)
        return expected


class AlasSemanticAdapterTests(unittest.TestCase):
    def make_adapter(self):
        oracle = FakeOracle()
        gate_calls = []
        adapter = AlasSemanticAdapter(oracle, lambda: gate_calls.append(True))
        return adapter, oracle, gate_calls

    def test_confirmed_main_aliases_route_to_semantic_targets(self):
        adapter, oracle, gate_calls = self.make_adapter()

        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))
        receipt = adapter.click(NamedButton("MAIN_GOTO_FLEET"))

        self.assertEqual(oracle.enabled_calls, ["main/battle"])
        self.assertEqual(oracle.click_calls, ["main/formation"])
        self.assertEqual(receipt.semantic_id, "main/formation")
        self.assertEqual(len(gate_calls), 2)

    def test_unmapped_resource_fails_before_identity_or_input(self):
        adapter, oracle, gate_calls = self.make_adapter()

        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_missing_stable_name_fails_closed(self):
        adapter, _, gate_calls = self.make_adapter()

        self.assertFalse(adapter.supports(object()))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(object())
        self.assertEqual(gate_calls, [])

    def test_raw_coordinate_input_is_always_rejected(self):
        adapter, oracle, gate_calls = self.make_adapter()

        with self.assertRaises(SemanticGateClosed):
            adapter.reject_raw_input("swipe")

        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_package_gate_verifies_once_per_bridge_pid(self):
        bridge = FakePackageBridge()
        gate = PinnedPackageGate(bridge)

        gate()
        gate()
        bridge.pid = 5678
        gate()

        self.assertEqual(
            bridge.calls,
            [PINNED_CN_GAME_FINGERPRINT, PINNED_CN_GAME_FINGERPRINT],
        )

    def test_package_gate_requires_open_bridge(self):
        bridge = FakePackageBridge()
        bridge.pid = None

        with self.assertRaises(SemanticGateClosed):
            PinnedPackageGate(bridge)()

    def test_lazy_session_rejects_unmapped_before_opening_adb(self):
        session = AlasSemanticSession(
            "emulator-test", "be80ce591a481c12d60c50d6040d40c035b40a2b"
        )

        with self.assertRaises(AlasSemanticUnmapped):
            session.click(NamedButton("BACK_ARROW"))

        self.assertIsNone(session.bridge.transport)

    def test_environment_factory_requires_explicit_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            )
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")


class ScriptedAdbBridge(AdbObserverBridge):
    def __init__(self, outputs):
        super().__init__("emulator-test", "com.bilibili.azurlane")
        self.outputs = outputs

    def _run(self, arguments, timeout_seconds=None):
        try:
            return self.outputs[tuple(arguments)]
        except KeyError as exc:
            raise AssertionError("unexpected ADB command: {0}".format(arguments)) from exc


class PackageFingerprintTests(unittest.TestCase):
    def test_reads_independent_version_abi_and_hash_identity(self):
        expected = AndroidPackageFingerprint(
            version_name="9.7.10",
            version_code=9710,
            primary_abi="x86_64",
            base_apk_sha256="a" * 64,
            il2cpp_sha256="b" * 64,
        )
        native_dir = "/data/app/~~token/pkg/lib/x86_64"
        base_apk = "/data/app/~~token/pkg/base.apk"
        il2cpp = native_dir + "/libil2cpp.so"
        bridge = ScriptedAdbBridge(
            {
                ("shell", "dumpsys", "package", bridge_package()): (
                    "versionCode=9710 minSdk=21\n"
                    "versionName=9.7.10\n"
                    "primaryCpuAbi=x86_64\n"
                    "legacyNativeLibraryDir={0}\n".format(native_dir)
                ),
                ("shell", "pm", "path", bridge_package()): "package:" + base_apk,
                (
                    "shell",
                    "find",
                    native_dir,
                    "-type",
                    "f",
                    "-name",
                    "libil2cpp.so",
                    "-print",
                ): il2cpp,
                ("shell", "sha256sum", base_apk): "{0}  {1}".format(
                    expected.base_apk_sha256, base_apk
                ),
                ("shell", "sha256sum", il2cpp): "{0}  {1}".format(
                    expected.il2cpp_sha256, il2cpp
                ),
            }
        )

        self.assertEqual(bridge.require_package_fingerprint(expected), expected)

    def test_rejects_non_allowlisted_fingerprint(self):
        expected = AndroidPackageFingerprint("1", 1, "x86_64", "a" * 64, "b" * 64)
        actual = AndroidPackageFingerprint("2", 2, "x86_64", "c" * 64, "d" * 64)

        class MismatchBridge(ScriptedAdbBridge):
            def package_fingerprint(self):
                return actual

        with self.assertRaises(SemanticGateClosed):
            MismatchBridge({}).require_package_fingerprint(expected)


def bridge_package():
    return "com.bilibili.azurlane"


if __name__ == "__main__":
    unittest.main()
