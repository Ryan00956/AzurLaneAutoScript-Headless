import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from alas_headless.runtime_evidence import (
    RuntimeEvidenceError,
    index_runtime_evidence,
    runtime_evidence_markdown,
)


def fingerprint(backend="kvm", runtime_lock_sha256="d" * 64):
    return {
        "backend": backend,
        "host_class": "ci-test",
        "android_fingerprint": "android/test",
        "game_version": "1.0",
        "game_abi": "x86_64",
        "libil2cpp_sha256": "a" * 64,
        "angle_sha256": "b" * 64,
        "observer_schema": "alas-headless.observer/v1",
        "core_commit": "c" * 40,
        "runtime_lock_sha256": runtime_lock_sha256,
    }


def write_manifest(
    root,
    name,
    outcome,
    captured,
    backend="kvm",
    include_fingerprint=True,
    runtime_lock_sha256="d" * 64,
):
    directory = root / name
    directory.mkdir()
    value = {
        "gate": "G3",
        "outcome": outcome,
        "captured_at_utc": captured,
    }
    if include_fingerprint:
        value["runtime_fingerprint"] = fingerprint(backend, runtime_lock_sha256)
    (directory / "manifest.json").write_text(json.dumps(value), encoding="utf-8")


class RuntimeEvidenceTests(unittest.TestCase):
    def test_index_keeps_latest_gate_per_exact_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_manifest(root, "old", "pass", "2026-08-10T01:00:00Z")
            write_manifest(root, "new", "fail", "2026-08-11T01:00:00Z")
            write_manifest(root, "redroid", "pass", "2026-08-09T01:00:00Z", "redroid")
            write_manifest(root, "legacy", "pass", "2026-08-11T02:00:00Z", include_fingerprint=False)
            index = index_runtime_evidence([root])
            self.assertEqual(len(index["fingerprints"]), 2)
            groups = {group["runtime_fingerprint"]["backend"]: group for group in index["fingerprints"]}
            self.assertEqual(groups["kvm"]["gates"]["G3"]["outcome"], "fail")
            self.assertEqual(groups["redroid"]["gates"]["G3"]["outcome"], "pass")
            self.assertEqual(len(index["rejected"]), 1)
            self.assertIn("kvm / x86_64 / 1.0", runtime_evidence_markdown(index))

    def test_requires_explicit_existing_root(self):
        with self.assertRaises(RuntimeEvidenceError):
            index_runtime_evidence([])
        with self.assertRaises(RuntimeEvidenceError):
            index_runtime_evidence([Path("missing-runtime-evidence-root")])

    def test_different_runtime_locks_never_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_manifest(
                root,
                "first-lock",
                "pass",
                "2026-08-10T01:00:00Z",
                runtime_lock_sha256="d" * 64,
            )
            write_manifest(
                root,
                "second-lock",
                "fail",
                "2026-08-11T01:00:00Z",
                runtime_lock_sha256="e" * 64,
            )
            index = index_runtime_evidence([root])
            self.assertEqual(len(index["fingerprints"]), 2)
            outcomes = {
                group["runtime_fingerprint"]["runtime_lock_sha256"]: group[
                    "gates"
                ]["G3"]["outcome"]
                for group in index["fingerprints"]
            }
            self.assertEqual(outcomes["d" * 64], "pass")
            self.assertEqual(outcomes["e" * 64], "fail")

    def test_cli_writes_json_and_markdown_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            root.mkdir()
            write_manifest(root, "run", "pass", "2026-08-11T01:00:00Z")
            output = Path(directory) / "out" / "runtime-status.json"
            markdown = Path(directory) / "out" / "runtime-status.md"
            repository = Path(__file__).resolve().parents[1]
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(repository / "python")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(repository / "scripts" / "python" / "index_runtime_evidence.py"),
                    "--root",
                    str(root),
                    "--output",
                    str(output),
                    "--markdown",
                    str(markdown),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["schema"],
                "alas-headless.runtime-evidence-index/v1",
            )
            self.assertIn("G3", markdown.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
