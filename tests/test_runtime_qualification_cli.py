import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RuntimeQualificationCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = Path(__file__).resolve().parents[1]
        cls.script = cls.repository / "scripts" / "python" / "qualify_runtime.py"
        cls.example_lock = (
            cls.repository / "integration" / "runtime" / "runtime-lock.example.json"
        )
        cls.example_config = (
            cls.repository / "integration" / "runtime" / "kvm.config.example.json"
        )

    def run_cli(self, *arguments):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(self.repository / "python")
        return subprocess.run(
            [sys.executable, str(self.script), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_default_mode_writes_only_a_plan_without_probing_kvm(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_output = Path(directory) / "plan.json"
            completed = self.run_cli(
                "--backend",
                "kvm",
                "--config",
                self.example_config,
                "--lock",
                self.example_lock,
                "--plan-output",
                plan_output,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = json.loads(plan_output.read_text(encoding="utf-8"))
            self.assertEqual(
                plan["schema"], "alas-headless.runtime-qualification-plan/v1"
            )
            self.assertTrue(plan["executable"])
            self.assertFalse(
                plan["compatibility_start_profile"]["experimental_tuning"]
            )
            self.assertEqual(json.loads(completed.stdout), plan)

    def test_execute_requires_the_separate_mutation_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_cli(
                "--backend",
                "kvm",
                "--config",
                self.example_config,
                "--lock",
                self.example_lock,
                "--execute",
                "--output",
                Path(directory) / "evidence",
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(
                "--execute requires --allow-runtime-mutation", completed.stderr
            )
            self.assertFalse((Path(directory) / "evidence").exists())

    def test_recovery_plan_expands_mutations_and_phases_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_output = Path(directory) / "plan.json"
            completed = self.run_cli(
                "--backend",
                "kvm",
                "--config",
                self.example_config,
                "--lock",
                self.example_lock,
                "--recovery",
                "android",
                "--plan-output",
                plan_output,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = json.loads(plan_output.read_text(encoding="utf-8"))
            self.assertEqual(plan["gate"], "runtime-recovery-android")
            self.assertIn("restart-android", plan["state_changes"])
            self.assertIn("adb-offline", plan["phases"])
            self.assertTrue(plan["executable"])

    def test_deferred_backend_cannot_cross_the_execute_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = json.loads(self.example_lock.read_text(encoding="utf-8"))
            lock["android"]["backend"] = "redroid"
            lock_path = root / "runtime-lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            config_path = root / "runtime-config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema": "alas-headless.runtime-config/v1",
                        "backend": "redroid",
                        "host_class": "linux-x86_64-redroid",
                    }
                ),
                encoding="utf-8",
            )
            output = root / "evidence"
            completed = self.run_cli(
                "--backend",
                "redroid",
                "--config",
                config_path,
                "--lock",
                lock_path,
                "--execute",
                "--allow-runtime-mutation",
                "--output",
                output,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("backend is plan-only", completed.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
