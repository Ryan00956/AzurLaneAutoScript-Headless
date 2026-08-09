import unittest
from pathlib import Path


class AlasIntegrationPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.patch_text = (
            root / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
        ).read_text(encoding="utf-8")

    def test_reward_hook_brackets_instead_of_replacing_alas_state_machine(self):
        self.assertIn("semantic_adapter.begin_mission_reward", self.patch_text)
        self.assertIn("semantic_adapter.end_mission_reward", self.patch_text)
        self.assertIn("+        try:", self.patch_text)
        self.assertIn("+        finally:", self.patch_text)
        self.assertIn("+                self._reward_mission_all()", self.patch_text)
        self.assertIn("+                self._reward_mission_weekly()", self.patch_text)
        self.assertNotIn("semantic_adapter.run_mission_reward", self.patch_text)

    def test_all_reward_observation_primitives_route_to_semantic_adapter(self):
        self.assertIn("appear = semantic_adapter.appear(button)", self.patch_text)
        self.assertIn(
            "appear = semantic_adapter.match_template_color(button)",
            self.patch_text,
        )
        self.assertIn("return semantic_adapter.image_color_count(", self.patch_text)

    def test_raw_input_fallbacks_remain_rejected(self):
        for operation in (
            "low-level click",
            "multi_click",
            "long_click",
            "swipe",
            "drag",
        ):
            self.assertIn(operation, self.patch_text)

    def test_ocr_layer_uses_context_bound_typed_text(self):
        self.assertIn("diff --git a/module/ocr/ocr.py", self.patch_text)
        self.assertIn("bind_semantic_session", self.patch_text)
        self.assertIn("current_semantic_session", self.patch_text)
        self.assertIn("semantic_session.ocr_text(", self.patch_text)
        self.assertIn("direct OCR without screen areas", self.patch_text)
        self.assertNotIn(
            "-        result_list = self.cnocr.atomic_ocr_for_single_lines",
            self.patch_text,
        )


if __name__ == "__main__":
    unittest.main()
