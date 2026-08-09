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
        self.assertIn("semantic_adapter.mission_reward_active", self.patch_text)
        self.assertIn("semantic_adapter.mission_claim_allowed", self.patch_text)
        self.assertIn("Semantic mode uses typed text, skip early_ocr_import", self.patch_text)
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

    def test_mail_hook_brackets_instead_of_replacing_alas_state_machine(self):
        self.assertIn("diff --git a/module/freebies/mail_white.py", self.patch_text)
        self.assertIn("semantic_adapter.begin_mail()", self.patch_text)
        self.assertIn("semantic_adapter.end_mail()", self.patch_text)
        self.assertIn("+            self.mail_claim(", self.patch_text)

    def test_commission_hook_brackets_instead_of_replacing_alas_state_machine(self):
        self.assertIn("diff --git a/module/commission/commission.py", self.patch_text)
        self.assertIn("diff --git a/module/commission/project.py", self.patch_text)
        self.assertIn("semantic_adapter.begin_commission()", self.patch_text)
        self.assertIn("semantic_adapter.end_commission()", self.patch_text)
        self.assertIn("Commission.from_semantic", self.patch_text)
        self.assertIn("semantic_adapter.commission_start_allowed()", self.patch_text)
        self.assertIn("semantic_adapter.commission_start_proof()", self.patch_text)
        self.assertIn("semantic_adapter.close_started_commission_detail()", self.patch_text)
        self.assertIn("+            self.commission_receive()", self.patch_text)
        self.assertIn("+            self.commission_start()", self.patch_text)

    def test_research_pixel_helpers_route_to_typed_project_model(self):
        self.assertIn("diff --git a/module/research/project.py", self.patch_text)
        self.assertIn("semantic_session.research_finished_index()", self.patch_text)
        self.assertIn("semantic_session.research_series()", self.patch_text)
        self.assertIn("semantic_session.research_statuses()", self.patch_text)

    def test_tactical_state_machine_uses_typed_countdowns_and_safe_cancel(self):
        self.assertIn("diff --git a/module/tactical/tactical_class.py", self.patch_text)
        self.assertIn("semantic_adapter.begin_tactical()", self.patch_text)
        self.assertIn("semantic_adapter.end_tactical()", self.patch_text)
        self.assertIn("semantic_session.tactical_remaining_seconds()", self.patch_text)
        self.assertIn(
            "semantic_session.cancel_tactical_continue_if_present()",
            self.patch_text,
        )

    def test_dorm_scheduler_uses_typed_occupied_slot_count(self):
        self.assertIn("diff --git a/module/dorm/dorm.py", self.patch_text)
        self.assertIn("semantic_session.dorm_state().occupied_slots", self.patch_text)


if __name__ == "__main__":
    unittest.main()
