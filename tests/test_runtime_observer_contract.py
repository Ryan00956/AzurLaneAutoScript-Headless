import unittest
from pathlib import Path


class RuntimeObserverContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.server = (
            root
            / "overlays"
            / "angle-g3"
            / "src"
            / "libANGLE"
            / "renderer"
            / "null"
            / "ObserverServer.cpp"
        ).read_text(encoding="utf-8")
        cls.build_script = (
            root / "scripts" / "wsl" / "build-angle-null-observer.sh"
        ).read_text(encoding="utf-8")

    def test_state_endpoint_requires_same_published_generation(self):
        self.assertIn('request == "GET /v1/state\\n"', self.server)
        self.assertIn(
            "observerSnapshot.requestGeneration ==",
            self.server,
        )
        self.assertIn("semanticSnapshot.requestGeneration", self.server)
        self.assertIn('response.append(",\\\"buttons\\\":")', self.server)

    def test_observer_build_fails_when_state_endpoint_is_missing(self):
        self.assertIn("Atomic state observer endpoint is missing", self.build_script)


if __name__ == "__main__":
    unittest.main()
