import sys
import unittest

from alas_headless.runtime_command import (
    RuntimeCommandExecutor,
    RuntimeCommandSpec,
    RuntimeExecutionPolicy,
    RuntimeMutationRefused,
)


class RuntimeCommandTests(unittest.TestCase):
    def test_exact_argv_execution_does_not_use_a_shell(self):
        executor = RuntimeCommandExecutor(maximum_output_bytes=4096)
        marker = "; this-is-data-not-a-command"
        result = executor.run(
            RuntimeCommandSpec(
                "argv-smoke",
                (sys.executable, "-c", "import sys; print(sys.argv[1])", marker),
            )
        )
        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, marker)

    def test_mutation_requires_explicit_policy(self):
        executor = RuntimeCommandExecutor(RuntimeExecutionPolicy())
        with self.assertRaises(RuntimeMutationRefused):
            executor.run(
                RuntimeCommandSpec(
                    "mutating-smoke",
                    (sys.executable, "-c", "raise SystemExit(0)"),
                    mutating=True,
                )
            )

    def test_home_overrides_are_rejected(self):
        with self.assertRaises(ValueError):
            RuntimeCommandSpec(
                "bad-environment",
                (sys.executable, "--version"),
                environment={"HOME": "not-allowed"},
            )

    def test_command_boundary_rejects_type_coercion_and_non_finite_timeout(self):
        with self.assertRaises(ValueError):
            RuntimeExecutionPolicy(allow_runtime_mutation="false")
        with self.assertRaises(ValueError):
            RuntimeCommandSpec("invalid-argv", ["python"])
        with self.assertRaises(ValueError):
            RuntimeCommandSpec(
                "invalid-timeout", ("python",), timeout_seconds=float("nan")
            )


if __name__ == "__main__":
    unittest.main()
