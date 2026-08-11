import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from alas_headless.runtime_artifacts import (
    RuntimeLock,
    RuntimeLockError,
    UpdateAdmission,
    UpdateState,
    expected_artifact_hashes,
    resource_set_id,
    validate_shared_public_paths,
    verify_artifact_files,
)


HASH = "a" * 64
COMMIT = "b" * 40


def make_lock():
    manifest_hash = HASH
    return {
        "schema": "alas-headless.runtime-lock/v1",
        "core": {
            "core_commit": COMMIT,
            "alas_upstream_commit": "c" * 40,
            "alas_patch_sha256": HASH,
        },
        "angle": {
            "revision": "d" * 40,
            "patchset_sha256": HASH,
            "abi": "x86_64",
            "apk_sha256": HASH,
            "observer_schema": "alas-headless.observer/v1",
        },
        "android": {
            "backend": "kvm",
            "build_fingerprint": "test/android/build",
            "api_level": 35,
            "abi": "x86_64",
            "system_image_sha256": HASH,
            "provision_profile_sha256": HASH,
        },
        "game": {
            "package": "com.bilibili.azurlane",
            "region": "cn",
            "version_name": "9.9.9",
            "version_code": 999,
            "abi": "x86_64",
            "base_apk_sha256": HASH,
            "libil2cpp_sha256": HASH,
        },
        "resources": {
            "resource_set_id": resource_set_id("cn", "9.9.9", manifest_hash),
            "resource_epoch": 1,
            "manifest_sha256": manifest_hash,
            "shared_public_paths": ["game/public-assets", "game/cache/bundles"],
        },
        "userdata": {"generation": 1, "account_scope": "per-instance"},
    }


class RuntimeArtifactsTests(unittest.TestCase):
    def test_runtime_lock_is_canonical_and_rejects_abi_mismatch(self):
        first = RuntimeLock.from_mapping(make_lock())
        second_source = make_lock()
        second_source["schema"] = second_source.pop("schema")
        second = RuntimeLock.from_mapping(second_source)
        self.assertEqual(first.sha256, second.sha256)
        with self.assertRaises(TypeError):
            first.document["schema"] = "changed"
        with self.assertRaises(TypeError):
            first.document["game"]["version_name"] = "changed"

        mismatch = make_lock()
        mismatch["game"]["abi"] = "arm64-v8a"
        with self.assertRaisesRegex(RuntimeLockError, "ABIs must match"):
            RuntimeLock.from_mapping(mismatch)

    def test_public_resources_cannot_include_account_data_or_parent_paths(self):
        self.assertEqual(
            validate_shared_public_paths(["game/public-assets"]),
            ("game/public-assets",),
        )
        for path in ("../escape", "/data", "game/shared_prefs/settings.xml", "data"):
            with self.subTest(path=path):
                with self.assertRaises(RuntimeLockError):
                    validate_shared_public_paths([path])

    def test_file_hash_verification_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.bin"
            path.write_bytes(b"artifact")
            digest = hashlib.sha256(b"artifact").hexdigest()
            self.assertEqual(
                verify_artifact_files({"angle": digest}, {"angle": path}),
                {"angle": digest},
            )
            with self.assertRaisesRegex(RuntimeLockError, "hash mismatch"):
                verify_artifact_files({"angle": HASH}, {"angle": path})

    def test_update_admission_requires_order_and_quarantine_reason(self):
        update = UpdateAdmission("game-apk")
        update = update.transition(UpdateState.STAGED)
        update = update.transition(UpdateState.INTEGRITY_VERIFIED)
        update = update.transition(UpdateState.COMPATIBILITY_VERIFIED)
        update = update.transition(UpdateState.CANARY)
        self.assertEqual(update.transition(UpdateState.PROMOTED).state, UpdateState.PROMOTED)
        with self.assertRaises(RuntimeLockError):
            UpdateAdmission("bad").transition(UpdateState.PROMOTED)
        with self.assertRaises(RuntimeLockError):
            UpdateAdmission("bad").transition(UpdateState.QUARANTINED)
        with self.assertRaises(RuntimeLockError):
            UpdateAdmission("", UpdateState.DISCOVERED)
        with self.assertRaises(RuntimeLockError):
            UpdateAdmission("bad", UpdateState.PROMOTED, "unexpected")

    def test_resource_identity_anchors_version_and_manifest(self):
        first = resource_set_id("cn", "1.0", HASH)
        self.assertNotEqual(first, resource_set_id("cn", "1.1", HASH))

    def test_repository_example_is_valid(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "integration"
            / "runtime"
            / "runtime-lock.example.json"
        )
        lock = RuntimeLock.from_mapping(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(len(lock.sha256), 64)
        self.assertEqual(expected_artifact_hashes(lock)["angle-apk"], HASH)


if __name__ == "__main__":
    unittest.main()
