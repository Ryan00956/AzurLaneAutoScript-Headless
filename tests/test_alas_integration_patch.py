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
        self.assertIn("list_mode=list_mode", self.patch_text)
        self.assertIn("self.semantic_row_key = (list_mode, state.index)", self.patch_text)
        self.assertIn("getattr(self, 'semantic_row_key', None)", self.patch_text)
        self.assertIn("semantic_adapter.commission_scroll_state()", self.patch_text)
        self.assertIn("semantic_adapter.commission_scroll_next()", self.patch_text)
        self.assertIn("semantic_adapter.commission_scroll_to_top()", self.patch_text)
        self.assertIn("semantic_adapter.commission_start_allowed()", self.patch_text)
        self.assertIn("semantic_adapter.commission_start_proof()", self.patch_text)
        self.assertIn("semantic_adapter.close_started_commission_detail()", self.patch_text)
        self.assertIn("semantic_adapter.commission_reward_pending()", self.patch_text)
        self.assertIn("semantic_adapter.confirm_commission_reward()", self.patch_text)
        self.assertIn("skip mode reset", self.patch_text)
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

    def test_five_new_flows_preserve_alas_state_machine_ownership(self):
        for begin, end in (
            ("begin_tactical()", "end_tactical()"),
            ("begin_research()", "end_research()"),
            ("begin_dorm()", "end_dorm()"),
            ("begin_build()", "end_build()"),
        ):
            self.assertIn("semantic_adapter." + begin, self.patch_text)
            self.assertIn("semantic_adapter." + end, self.patch_text)
        self.assertGreaterEqual(
            self.patch_text.count("def _run_alas_state_machine(self):"),
            3,
        )
        self.assertIn("return self._run_alas_state_machine()", self.patch_text)
        self.assertIn("self.tactical_class_receive()", self.patch_text)
        self.assertIn("semantic_session.research_projects()", self.patch_text)
        self.assertIn("semantic_session.research_detail_available()", self.patch_text)
        self.assertIn("semantic_session.research_detail_can_queue()", self.patch_text)
        self.assertIn("semantic_session.research_queue_fill_slots()", self.patch_text)
        self.assertIn("Book.from_semantic", self.patch_text)
        self.assertIn("semantic_session.tactical_select_book", self.patch_text)
        self.assertIn("semantic_session.dorm_feed_food(index, count)", self.patch_text)
        self.assertIn("semantic_session.build_submit_state()", self.patch_text)
        self.assertIn(
            "ALAS still owns selection, queue filling, retry, and scheduling.",
            self.patch_text,
        )
        self.assertIn(
            "ALAS still owns feed filtering, collect loop, and scheduling.",
            self.patch_text,
        )
        self.assertIn(
            "ALAS still owns pool choice, affordability, and submit scheduling.",
            self.patch_text,
        )

    def test_campaign_fleet_preparation_preserves_alas_state_machine(self):
        self.assertIn(
            "diff --git a/module/map/map_fleet_preparation.py",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.authorize_campaign_fleet_preparation(",
            self.patch_text,
        )
        self.assertIn(
            "+                                self.fleet_preparation()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.confirm_campaign_fleet_selection()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.close_campaign_fleet_dropdown_for_rollback()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.confirm_campaign_fleet_preparation()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.campaign_fleet_selected_indices(",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.authorize_campaign_sortie(",
            self.patch_text,
        )
        self.assertIn(
            "+                                    self.device.click(FLEET_PREPARATION)",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.campaign_sortie_committed()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.confirm_campaign_sortie()",
            self.patch_text,
        )
        self.assertIn(
            "+                                self.handle_2x_book_setting(mode='prep')",
            self.patch_text,
        )
        self.assertIn(
            "+                                self.handle_auto_search_setting()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.campaign_map_preparation_committed()",
            self.patch_text,
        )

    def test_campaign_map_model_replaces_only_the_read_only_input_boundary(self):
        self.assertIn("semantic_adapter.campaign_map_state(", self.patch_text)
        self.assertIn("columns=campaign_map.shape[0] + 1", self.patch_text)
        self.assertIn("grid.location for grid in campaign_map", self.patch_text)
        self.assertIn("if grid.is_land", self.patch_text)
        self.assertIn("expected_fleet_count=sum((", self.patch_text)
        self.assertIn("Semantic campaign map model:", self.patch_text)
        self.assertIn("+                    return True", self.patch_text)
        self.assertIn("logger.info('Already in map, retreating.')", self.patch_text)

    def test_campaign_map_projection_delegates_to_alas_without_movement(self):
        self.assertIn(
            "synchronize_alas_campaign_map,",
            self.patch_text,
        )
        self.assertIn(
            "synchronize_alas_campaign_map(",
            self.patch_text,
        )
        self.assertIn("self.campaign, state", self.patch_text)
        self.assertIn("Semantic ALAS map projection:", self.patch_text)
        self.assertIn("recommended_enemy_node", self.patch_text)
        self.assertIn("recommended_pickup_node", self.patch_text)
        self.assertIn("projection.displayed_fleet_index", self.patch_text)
        self.assertIn("projection.current_fleet_index", self.patch_text)
        self.assertIn("fleet.fleet_index", self.patch_text)
        self.assertIn("fleet.is_current", self.patch_text)
        self.assertNotIn("semantic_map_projection.goto", self.patch_text)
        self.assertNotIn("semantic_map_projection.map_control_init", self.patch_text)

    def test_campaign_decision_runs_alas_branch_but_intercepts_goto(self):
        self.assertIn(
            "preview_alas_campaign_decision,",
            self.patch_text,
        )
        self.assertIn(
            "decision = preview_alas_campaign_decision(",
            self.patch_text,
        )
        self.assertIn("self.campaign, projection", self.patch_text)
        self.assertIn("Semantic ALAS campaign decision:", self.patch_text)
        self.assertIn("decision.branch_name", self.patch_text)
        self.assertIn("decision.fleet_index", self.patch_text)
        self.assertIn("decision.target_node", self.patch_text)
        self.assertIn("decision.route_nodes", self.patch_text)
        self.assertIn("decision.goto_nodes", self.patch_text)
        self.assertNotIn("self.campaign.goto(decision", self.patch_text)
        self.assertNotIn("self.campaign._goto(decision", self.patch_text)

    def test_campaign_combat_admission_runs_captured_native_goto_prefix(self):
        self.assertIn(
            "semantic_adapter.authorize_campaign_combat(",
            self.patch_text,
        )
        self.assertIn("Semantic ALAS combat admission:", self.patch_text)
        self.assertIn(
            "preview_alas_campaign_goto_input,",
            self.patch_text,
        )
        self.assertIn(
            "goto_input = preview_alas_campaign_goto_input(",
            self.patch_text,
        )
        self.assertIn("Semantic ALAS goto input preview:", self.patch_text)
        self.assertIn("goto_input.call_order", self.patch_text)
        self.assertIn(
            "Semantic ALAS goto input preview validation complete",
            self.patch_text,
        )
        self.assertNotIn("self.campaign.goto(decision", self.patch_text)
        self.assertNotIn("self.campaign._goto(decision", self.patch_text)


if __name__ == "__main__":
    unittest.main()
