import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    MissionClaimableDetected,
    AndroidPackageFingerprint,
    Bounds,
    BuildPool,
    MissionDisposition,
    PINNED_CN_GAME_FINGERPRINT,
    PinnedPackageGate,
    Point,
    ResearchProjectStatus,
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
        self.wait_calls = []
        self.wait_any_calls = []
        self.mission_disposition = MissionDisposition.UNFINISHED
        self.mission_dispositions = []
        self.streaming_mission_dispositions = []
        self.streaming_generation = 0
        self.enabled_values = {}
        self.exists_values = {}
        self.enable_main_after_overlay_click = False
        self.text_groups = ()
        self.image_selected_values = {"task/nav/all": True}
        self.toggle_selected_values = {}
        self.mail_empty = False
        self.research_project_values = []
        self.research_detail_value = SimpleNamespace(
            code="G-412",
            resource_id="gold",
            resource_required=1500,
            can_start=True,
            can_queue=True,
            is_running=False,
        )
        self.research_prompt_cost = ("gold", 1500)
        self.tactical_slot_values = []
        self.tactical_remaining_values = ()
        self.tactical_prompt_text = None
        self.tactical_book_values = []
        self.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=0,
            oil_cost=0,
        )
        self.commission_transition_value = SimpleNamespace(
            name="日常资源开发III",
            before_duration_seconds=3600,
            after_duration_seconds=3595,
            after_status_sprite="tag_ongoing",
        )
        self.commission_scroll_value = SimpleNamespace(
            position=0.0,
            page_fraction=0.8,
            scrollable=True,
            at_top=True,
            at_bottom=False,
        )
        self.commission_scroll_calls = []
        self.reward_summary_values = []
        self.state_generation = 20
        self.build_pool_value = BuildPool.LIGHT
        self.build_cost_value = SimpleNamespace(
            cubes_owned=10,
            cubes_per_build=1,
            coins_per_build=600,
        )
        self.build_submit_value = SimpleNamespace(
            count=1,
            cubes_owned=10,
            cubes_required=1,
            coins_required=600,
        )
        self.build_queue_empty_value = True
        self.build_queue_timer_values = ("99:99:99", "99:99:99")
        self.main_gold_value = 10000
        self.dorm_state_value = SimpleNamespace(
            occupied_slots=2,
            total_slots=6,
            food=20000,
            food_capacity=40000,
            comfort=300,
            floor=1,
            food_countdown_seconds=3600,
        )
        self.dorm_feed_state_value = SimpleNamespace(
            food=0,
            capacity=40000,
            items=tuple(
                SimpleNamespace(item_id=50001 + index, value=1000, count=5)
                for index in range(6)
            ),
        )
        self.campaign_menu_value = False
        self.campaign_page_value = False
        self.campaign_state_value = SimpleNamespace(
            chapter_name="第一章",
            stages=(),
        )

    def enabled(self, semantic_id):
        self.enabled_calls.append(semantic_id)
        return self.enabled_values.get(semantic_id, True)

    def exists(self, semantic_id):
        return self.exists_values.get(semantic_id, False)

    def bounds(self, semantic_id):
        self.bounds_calls.append(semantic_id)
        return Bounds(1, 2, 3, 4)

    def text_groups_in_bounds(self, bounds):
        self.last_text_bounds = tuple(bounds)
        return self.text_groups

    @staticmethod
    def _bounds_overlap(left, right):
        width = max(0.0, min(left.right, right.right) - max(left.left, right.left))
        height = max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
        return width * height

    def click(self, semantic_id):
        self.click_calls.append(semantic_id)
        if self.enable_main_after_overlay_click and semantic_id.startswith("overlay/"):
            self.enabled_values["main/task"] = True
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="root/target",
        )

    def image_selected(self, semantic_id):
        return self.image_selected_values.get(semantic_id, False)

    def click_image(self, semantic_id):
        self.click_calls.append(semantic_id)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=8,
            point=Point(50, 50),
            bounds=Bounds(0, 0, 100, 100),
            path="root/tagRoot/target/Image",
        )

    def toggle_selected(self, semantic_id):
        return self.toggle_selected_values.get(semantic_id, False)

    def click_toggle(self, semantic_id):
        self.click_calls.append(semantic_id)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=8,
            point=Point(50, 50),
            bounds=Bounds(0, 0, 100, 100),
            path="root/toggle",
        )

    def mail_is_empty(self):
        return self.mail_empty

    def research_projects(self):
        return tuple(self.research_project_values)

    def click_research_project(self, slot):
        self.click_calls.append("research/project/{0}".format(slot))
        return self.click_receipt("research/project/{0}".format(slot))

    def research_detail_state(self):
        return self.research_detail_value

    def research_start_prompt_cost(self):
        return self.research_prompt_cost

    def build_selected_pool(self):
        return self.build_pool_value

    def build_costs(self):
        return self.build_cost_value

    def build_submit_state(self):
        return self.build_submit_value

    def build_queue_empty(self):
        return self.build_queue_empty_value

    def build_queue_timers(self):
        return self.build_queue_timer_values

    def main_gold(self):
        return self.main_gold_value

    def dorm_state(self):
        return self.dorm_state_value

    def dorm_feed_state(self):
        return self.dorm_feed_state_value

    def click_dorm_food(self, item_id):
        before = self.dorm_feed_state_value
        items = []
        for item in before.items:
            items.append(
                SimpleNamespace(
                    item_id=item.item_id,
                    value=item.value,
                    count=item.count - (1 if item.item_id == item_id else 0),
                )
            )
        selected = next(item for item in before.items if item.item_id == item_id)
        self.dorm_feed_state_value = SimpleNamespace(
            food=before.food + selected.value,
            capacity=before.capacity,
            items=tuple(items),
        )
        self.click_calls.append("dorm/feed/item/{0}".format(item_id))
        return self.click_receipt("dorm/feed/item/{0}".format(item_id))

    def campaign_menu_is_entry(self):
        return self.campaign_menu_value

    def campaign_page_is_normal(self):
        return self.campaign_page_value

    def campaign_page_state(self):
        return self.campaign_state_value

    def tactical_slots(self):
        return tuple(self.tactical_slot_values)

    def tactical_books(self):
        return tuple(self.tactical_book_values)

    def tactical_remaining_seconds(self):
        return tuple(self.tactical_remaining_values)

    def tactical_continue_prompt_text(self):
        return self.tactical_prompt_text

    @staticmethod
    def click_receipt(semantic_id):
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="root/target",
        )

    def commission_scroll_state(self):
        self.commission_scroll_calls.append("state")
        return self.commission_scroll_value

    def commission_scroll_next(self):
        self.commission_scroll_calls.append("next")
        return SimpleNamespace(direction="next")

    def commission_scroll_to_top(self):
        self.commission_scroll_calls.append("top")
        return SimpleNamespace(direction="top")

    def wait_for(self, semantic_id, timeout_seconds, minimum_generation=None):
        self.wait_calls.append((semantic_id, timeout_seconds, minimum_generation))
        return SimpleNamespace(path="root/" + semantic_id)

    def wait_for_mission_state(self, timeout_seconds):
        disposition = (
            self.mission_dispositions.pop(0)
            if self.mission_dispositions
            else self.mission_disposition
        )
        return SimpleNamespace(
            disposition=disposition,
            generation=9,
            claim_all=(object() if disposition == MissionDisposition.CLAIMABLE_ALL else None),
            claim_rows=((object(),) if disposition == MissionDisposition.CLAIMABLE_ROW else ()),
            unfinished_rows=(object(),),
        )

    def mission_page_state(self):
        disposition = (
            self.streaming_mission_dispositions.pop(0)
            if self.streaming_mission_dispositions
            else self.mission_disposition
        )
        self.streaming_generation += 1
        return SimpleNamespace(
            disposition=disposition,
            generation=self.streaming_generation,
            signature=(disposition,),
            claim_all=(
                object()
                if disposition == MissionDisposition.CLAIMABLE_ALL
                else None
            ),
            claim_rows=(
                (object(),)
                if disposition == MissionDisposition.CLAIMABLE_ROW
                else ()
            ),
            unfinished_rows=(
                (object(),)
                if disposition == MissionDisposition.UNFINISHED
                else ()
            ),
        )

    def wait_for_any(
        self, semantic_ids, timeout_seconds, minimum_generation=None
    ):
        self.wait_any_calls.append(
            (semantic_ids, timeout_seconds, minimum_generation)
        )
        return (
            "reward/award-info/close",
            SimpleNamespace(path="root/AwardInfoUI(Clone)/items/close"),
        )

    def commission_rows(self):
        return ()

    def commission_is_empty(self):
        return False

    def reward_summary_count(self, section, counter):
        self.last_reward_summary_query = (section, counter)
        if not self.reward_summary_values:
            return 0
        return self.reward_summary_values.pop(0)

    def read_state(self):
        return SimpleNamespace(generation=self.state_generation)

    def commission_detail_state(self):
        return self.commission_detail_value

    def click_commission_row(self, signature):
        self.click_calls.append("commission/row/{0}".format(signature[0]))
        return ActionReceipt(
            semantic_id="commission/row/{0}".format(signature[0]),
            generation=10,
            point=Point(640, 190),
            bounds=Bounds(100, 100, 1180, 250),
            path="root/commission/row/{0}".format(signature[0]),
        )

    def click_commission_recommend(self, signature):
        self.click_calls.append("commission/detail/recommend")
        return ActionReceipt(
            semantic_id="commission/detail/recommend",
            generation=11,
            point=Point(935, 363),
            bounds=Bounds(855, 316, 1015, 410),
            path="root/commission/detail/recommend",
        )

    def click_commission_start(self, signature):
        self.click_calls.append("commission/detail/start")
        return ActionReceipt(
            semantic_id="commission/detail/start",
            generation=12,
            point=Point(1092, 363),
            bounds=Bounds(1012, 316, 1172, 410),
            path="root/commission/detail/start",
        )

    def commission_start_transition(self, signature):
        self.last_commission_transition_signature = tuple(signature)
        return self.commission_transition_value


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

    def test_network_reconnect_popup_uses_only_exact_semantic_targets(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values.update(
            {
                "overlay/network-reconnect/cancel": True,
                "overlay/network-reconnect/confirm": True,
            }
        )

        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_UI_ADDITIONAL"))

        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(oracle.click_calls, ["overlay/network-reconnect/confirm"])

    def test_main_dorm_and_research_menus_use_distinct_typed_buttons(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(
            adapter.semantic_id_for("MAIN_GOTO_DORMMENU"), "main/live"
        )
        self.assertEqual(
            adapter.semantic_id_for("MAIN_GOTO_RESHMENU_WHITE"), "main/tech"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORMMENU_GOTO_DORM"), "dorm-menu/dorm"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORMMENU_GOTO_ACADEMY"),
            "dorm-menu/academy",
        )

    def test_build_dorm_and_menu_page_checks_are_presence_only(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["build/page/start"] = True
        oracle.exists_values["dorm-menu/page/root"] = True
        oracle.exists_values["research-menu/page/back"] = True
        oracle.exists_values["research/page/back"] = True
        oracle.exists_values["dorm/page/manage"] = True

        self.assertTrue(adapter.appear(NamedButton("BUILD_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORMMENU_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("RESHMENU_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("RESEARCH_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertEqual(
            adapter.semantic_id_for("DORM_GOTO_MAIN"), "dorm/page/back"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORM_INFO"), "dorm/statistics/confirm"
        )
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BUILD_CHECK"))

    def test_build_and_dorm_typed_state_is_exposed_without_mutation(self):
        adapter, oracle, _ = self.make_adapter()

        self.assertEqual(adapter.build_selected_pool(), BuildPool.LIGHT)
        self.assertEqual(adapter.build_costs().cubes_owned, 10)
        self.assertEqual(adapter.dorm_state().occupied_slots, 2)
        self.assertEqual(oracle.click_calls, [])

    def test_research_start_budget_is_spent_only_on_matching_final_confirm(self):
        oracle = FakeOracle()
        project = SimpleNamespace(
            slot=1,
            code="G-412",
            status=ResearchProjectStatus.DETAIL,
            button=SimpleNamespace(actionable=True),
        )
        oracle.research_project_values = [project]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        adapter.click(NamedButton("ENTRANCE_1"))
        adapter.click(NamedButton("RESEARCH_START"))
        self.assertEqual(adapter._research_context.start_budget, 1)
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(receipt.semantic_id, "research/start/confirm")
        self.assertEqual(adapter._research_context.start_budget, 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/start",
                "research/start/confirm",
            ],
        )

    def test_tactical_assignment_budget_is_spent_only_on_course_confirm(self):
        oracle = FakeOracle()
        oracle.tactical_book_values = [
            SimpleNamespace(position=1, selected=True, count=6)
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            tactical_assign_budget=1,
        )
        adapter.begin_tactical()

        adapter.click(NamedButton("TACTICAL_CLASS_START"))
        self.assertEqual(adapter._commission_context.assign_budget, 1)
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(receipt.semantic_id, "tactical/course/confirm")
        self.assertEqual(adapter._commission_context.assign_budget, 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM"))

    def test_dorm_feed_budget_requires_inventory_and_food_mutation_proof(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 1)

        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].semantic_id, "dorm/feed/item/50001")
        self.assertEqual(adapter._dorm_context.feed_budget, 0)
        self.assertEqual(oracle.dorm_feed_state_value.food, 1000)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 4)
        with self.assertRaises(SemanticGateClosed):
            adapter.dorm_feed_food(0, 1)

    def test_build_submit_budget_checks_coins_and_is_single_use(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        self.assertEqual(receipt.semantic_id, "build/prep/confirm")
        self.assertEqual(adapter._build_context.submit_budget, 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        insufficient = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        insufficient.begin_build()
        insufficient._build_context.coins_owned = 599
        with self.assertRaises(SemanticGateClosed):
            insufficient.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

    def test_build_warning_confirmation_is_admitted_once(self):
        oracle = FakeOracle()
        oracle.enabled_values["build/warning/confirm"] = True
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(receipt.semantic_id, "build/warning/confirm")
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM"))

    def test_build_navbars_and_queue_observations_feed_alas_primitives(self):
        oracle = FakeOracle()
        oracle.toggle_selected_values.update(
            {
                "build/nav/pools": False,
                "build/nav/queue": True,
                "build/nav/support": False,
                "build/nav/unseam": False,
                "build/pool/light": False,
                "build/pool/heavy": True,
                "build/pool/special": False,
            }
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None, build_submit_budget=1)
        adapter.begin_build()

        self.assertTrue(adapter.supports(NamedButton("GACHA_SIDE_NAVBAR_0_1")))
        self.assertTrue(adapter.supports(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0")))
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("GACHA_SIDE_NAVBAR_0_1"),
                color=(247, 255, 173),
                threshold=221,
                count=100,
            )
        )
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0"),
                color=(247, 227, 148),
                threshold=180,
                count=100,
            )
        )
        self.assertFalse(
            adapter.image_color_count(
                NamedButton("CONSTRUCT_BOTTOM_NAVBAR_0_0"),
                color=(189, 231, 247),
                threshold=180,
                count=50,
            )
        )
        self.assertTrue(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertTrue(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.click(NamedButton("GACHA_SIDE_NAVBAR_0_0"))
        session.click(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0"))
        self.assertEqual(
            oracle.click_calls,
            ["build/nav/pools", "build/pool/heavy"],
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("BUILD_FINISH_ORDERS"))

        oracle.build_queue_empty_value = False
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("BUILD_QUEUE_EMPTY"))

    def test_build_goto_main_uses_exact_reviewed_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["build/page/start"] = True
        oracle.enabled_values["build/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "build/page/back")
        self.assertEqual(oracle.click_calls, ["build/page/back"])

    def test_campaign_menu_uses_presence_check_and_exact_navigation_targets(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))
        self.assertEqual(
            adapter.semantic_id_for("CAMPAIGN_MENU_GOTO_CAMPAIGN"),
            "campaign-menu/normal",
        )
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        self.assertEqual(oracle.click_calls, ["campaign-menu/page/back"])

    def test_campaign_chapter_check_and_back_require_typed_page_identity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertEqual(adapter.campaign_page_state().chapter_name, "第一章")
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BACK_ARROW"))
        self.assertEqual(oracle.click_calls, [])

    def test_goto_main_from_mission_uses_exact_task_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.enabled_values["task/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "task/page/back")
        self.assertEqual(oracle.click_calls, ["task/page/back"])

    def test_research_menu_entries_use_exact_typed_buttons(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(
            adapter.semantic_id_for("RESHMENU_GOTO_RESEARCH"),
            "research-menu/research",
        )
        self.assertEqual(
            adapter.semantic_id_for("RESHMENU_GOTO_SHIPYARD"),
            "research-menu/shipyard",
        )
        self.assertEqual(
            adapter.semantic_id_for("ENTRANCE_3"), "research/project/3"
        )

    def test_research_ocr_companions_use_typed_project_model(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                series=9,
                status=ResearchProjectStatus.DETAIL,
            ),
            SimpleNamespace(
                slot=2,
                series=8,
                status=ResearchProjectStatus.RUNNING,
            ),
        ]

        self.assertEqual(adapter.research_series(), [9, 8])
        self.assertEqual(adapter.research_statuses(), ["detail", "running"])
        self.assertIsNone(adapter.research_finished_index())

    def test_tactical_countdown_and_safe_continue_cancel_use_typed_state(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_tactical_rewards=True,
        )
        oracle.tactical_slot_values = [SimpleNamespace(slot=1)]
        oracle.tactical_remaining_values = (3723, 90)
        oracle.tactical_prompt_text = "「舰船」学习完成，「技能」技能获得450点经验是否继续学习该技能？"
        adapter.begin_tactical()

        self.assertEqual(len(adapter.tactical_slots()), 1)
        self.assertEqual(adapter.tactical_remaining_seconds(), (3723, 90))
        self.assertTrue(adapter.cancel_tactical_continue_if_present())
        self.assertFalse(adapter.cancel_tactical_continue_if_present())
        self.assertEqual(oracle.click_calls, ["tactical/continue/cancel"])
        adapter.end_commission()

    def test_mail_page_identity_and_manage_use_exact_semantic_targets(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(adapter.semantic_id_for("MAIL_CHECK"), "mail/page/back")
        self.assertEqual(adapter.semantic_id_for("MAIL_MANAGE"), "mail/manage")

    def test_mail_context_reuses_alas_state_machine_and_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["main/mail"] = True
        oracle.enabled_values["mail/page/back"] = True
        oracle.enabled_values["mail/manage/claim"] = False
        oracle.enabled_values["mail/manage/delete"] = False
        adapter.begin_mail()

        adapter.click(NamedButton("MAIL_ENTER"))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN_WHITE")))
        self.assertFalse(adapter.appear(NamedButton("MAIL_BATCH_CLAIM")))
        self.assertFalse(adapter.appear(NamedButton("UNRELATED_MAIL_POPUP")))
        receipt = adapter.click(NamedButton("GOTO_MAIN_WHITE"))

        self.assertEqual(receipt.semantic_id, "mail/page/back")
        self.assertEqual(oracle.click_calls, ["main/mail", "mail/page/back"])
        adapter.end_mail()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("MAIL_BATCH_CLAIM"))

    def test_mail_reward_popup_uses_reviewed_award_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_mail()

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_2")))
        receipt = adapter.click(NamedButton("GET_ITEMS_2"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")

    def test_mail_manager_close_and_filters_use_typed_controls(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.enabled_values["mail/manage/back"] = True
        oracle.toggle_selected_values["mail/manage/merit"] = True

        self.assertTrue(
            adapter.image_color_count(
                NamedButton("MAIL_SELECT_MERIT"),
                color=(57, 56, 57),
                threshold=221,
                count=50,
            )
        )
        toggle = adapter.click(NamedButton("MAIL_SELECT_OIL"))
        close = adapter.click(NamedButton("MAIL_MANAGE"))

        self.assertEqual(toggle.semantic_id, "mail/manage/oil")
        self.assertEqual(close.semantic_id, "mail/manage/back")

    def test_mail_mutations_require_separate_opt_in(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.enabled_values["mail/manage/claim"] = True

        self.assertTrue(adapter.appear(NamedButton("MAIL_BATCH_CLAIM")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MAIL_BATCH_CLAIM"))

        opted_in = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        opted_in.begin_mail()
        receipt = opted_in.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertEqual(receipt.semantic_id, "mail/manage/claim")

    def test_mail_empty_never_uses_button_absence(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()

        self.assertFalse(adapter.appear(NamedButton("MAIL_WHITE_EMPTY")))
        oracle.mail_empty = True
        self.assertTrue(adapter.appear(NamedButton("MAIL_WHITE_EMPTY")))

    def test_commission_reward_and_navigation_are_distinct_alas_inputs(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()

        self.assertEqual(
            adapter.semantic_id_for("REWARD_1"), "reward/commission/finish"
        )
        self.assertEqual(
            adapter.semantic_id_for("REWARD_GOTO_COMMISSION"),
            "reward/commission/go",
        )
        self.assertTrue(adapter.appear(NamedButton("REWARD_1")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("REWARD_1"))
        self.assertEqual(oracle.click_calls, [])

    def test_commission_reward_chain_uses_one_budget_and_typed_counter_proof(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values = {
            "reward/commission/finish": True,
            "reward/ship-exp/close": True,
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
            "commission/page/back": True,
        }
        oracle.reward_summary_values = [1, 1, 0]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        claim = adapter.click(NamedButton("REWARD_1"))
        duplicate = adapter.click(NamedButton("REWARD_1_WHITE"))
        self.assertTrue(adapter.appear(NamedButton("EXP_INFO_S_REWARD")))
        exp = adapter.click(NamedButton("REWARD_SAVE_CLICK"))
        exp_duplicate = adapter.click(NamedButton("EXP_INFO_S_REWARD"))
        award = adapter.click(NamedButton("GET_ITEMS_3"))
        award_duplicate = adapter.click(NamedButton("GET_ITEMS_1"))
        oracle.enabled_values["reward/award-info/close"] = False
        award_after_disappear = adapter.click(NamedButton("GET_ITEMS_2"))
        proof = adapter.confirm_commission_reward()

        self.assertEqual(claim, duplicate)
        self.assertEqual(exp, exp_duplicate)
        self.assertEqual(award, award_duplicate)
        self.assertEqual(award, award_after_disappear)
        self.assertEqual(exp.semantic_id, "reward/ship-exp/close")
        self.assertEqual(award.semantic_id, "reward/award-info/close")
        self.assertEqual(proof.before_finished_count, 1)
        self.assertEqual(proof.after_finished_count, 0)
        self.assertEqual(
            proof.close_semantic_ids,
            ("reward/ship-exp/close", "reward/award-info/close"),
        )
        self.assertEqual(
            oracle.click_calls,
            [
                "reward/commission/finish",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "commission/page/back",
            ],
        )

    def test_commission_reward_refuses_multiple_finished_rows(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values["reward/commission/finish"] = True
        oracle.reward_summary_values = [2]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertFalse(adapter.commission_reward_allowed())
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("REWARD_1"))
        self.assertEqual(oracle.click_calls, [])

    def test_commission_reward_revalidates_count_immediately_before_input(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values["reward/commission/finish"] = True
        oracle.reward_summary_values = [1, 2]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("REWARD_1"))

        self.assertEqual(oracle.click_calls, [])

    def test_unknown_commission_presence_is_false_only_on_proven_surface(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("OIL_MAXED")))
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))

        oracle.exists_values.clear()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("OIL_MAXED"))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("GUILD_POPUP_CONFIRM"))

    def test_commission_page_transition_has_bounded_passive_probe_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()
        adapter.click(NamedButton("REWARD_GOTO_COMMISSION"))

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

        adapter._commission_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))

    def test_commission_scroll_delegates_only_inside_commission_context(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaises(SemanticGateClosed):
            adapter.commission_scroll_state()

        adapter.begin_commission()
        state = adapter.commission_scroll_state()
        next_proof = adapter.commission_scroll_next()
        top_proof = adapter.commission_scroll_to_top()

        self.assertTrue(state.scrollable)
        self.assertEqual(next_proof.direction, "next")
        self.assertEqual(top_proof.direction, "top")
        self.assertEqual(
            oracle.commission_scroll_calls,
            ["state", "next", "top"],
        )

    def test_commission_start_uses_exact_row_and_independent_one_input_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature

        adapter.click(row)
        self.assertTrue(adapter.appear(NamedButton("COMMISSION_ADVICE")))
        adapter.click(NamedButton("COMMISSION_ADVICE"))
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=0,
        )
        self.assertTrue(adapter.appear(NamedButton("COMMISSION_START")))
        first = adapter.click(NamedButton("COMMISSION_START"))
        duplicate = adapter.click(NamedButton("COMMISSION_START"))

        self.assertEqual(first, duplicate)
        self.assertFalse(adapter.commission_start_allowed())
        self.assertEqual(
            oracle.click_calls,
            [
                "commission/row/1",
                "commission/detail/recommend",
                "commission/detail/start",
            ],
        )

    def test_commission_start_rejects_nonzero_oil_even_with_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=10,
        )

        self.assertFalse(adapter.appear(NamedButton("COMMISSION_START")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("COMMISSION_START"))
        self.assertEqual(oracle.click_calls, ["commission/row/1"])

    def test_commission_start_proof_precedes_exact_detail_close(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=0,
        )
        adapter.click(NamedButton("COMMISSION_START"))

        proof = adapter.commission_start_proof()
        receipt = adapter.close_started_commission_detail()

        self.assertEqual(proof.after_status_sprite, "tag_ongoing")
        self.assertEqual(
            oracle.last_commission_transition_signature,
            signature,
        )
        self.assertEqual(receipt.semantic_id, "commission/detail/back")
        self.assertEqual(
            oracle.wait_calls[-1],
            ("reward/page/back", 12.0, receipt.generation),
        )

    def test_commission_start_defaults_closed(self):
        adapter, _, _ = self.make_adapter()
        adapter.begin_commission()
        self.assertFalse(adapter.commission_start_allowed())

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

    def test_semantic_ocr_reads_typed_unity_text_and_strips_markup(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="<color=#fff>01:23:45</color>",
                    bounds=Bounds(100, 100, 200, 130),
                    truncated=False,
                ),
            ),
        )

        value = adapter.ocr_text([(90, 90, 210, 140)], alphabet="0123456789:")

        self.assertEqual(value, "01:23:45")
        self.assertEqual(oracle.last_text_bounds, (Bounds(90, 90, 210, 140),))
        self.assertEqual(len(gate_calls), 1)

    def test_semantic_ocr_rejects_missing_or_overlapping_text(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.text_groups = ((),)
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="123456", bounds=Bounds(100, 100, 180, 130), truncated=True
                ),
            ),
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="12", bounds=Bounds(100, 100, 180, 130), truncated=False
                ),
                SimpleNamespace(
                    text="34", bounds=Bounds(110, 100, 190, 130), truncated=False
                ),
            ),
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

    def test_alas_owned_state_machine_consumes_stable_semantic_inputs(self):
        oracle = FakeOracle()
        oracle.enabled_values = {
            "main/task": True,
            "task/page/back": True,
            "reward/award-info/close": False,
            "reward/award-info1/close": False,
        }
        oracle.exists_values["main/task"] = True
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL
        gate_calls = []
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: gate_calls.append(True),
            allow_mission_claim_once=True,
        )

        adapter.begin_mission_reward(daily=True, weekly=True)
        self.assertTrue(adapter.appear(NamedButton("MISSION_NOTICE")))
        adapter.click(NamedButton("MAIN_GOTO_MISSION"))
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_0"),
                color=(247, 255, 173),
                threshold=180,
                count=100,
            )
        )
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_1"),
                color=(140, 162, 181),
                threshold=180,
                count=50,
            )
        )
        self.assertFalse(adapter.appear(NamedButton("MISSION_MULTI")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_MULTI")))

        receipt = adapter.click(NamedButton("MISSION_MULTI"))

        self.assertEqual(receipt.semantic_id, "task/claim/all")
        self.assertEqual(
            oracle.click_calls,
            ["main/task", "task/claim/all"],
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))
        self.assertEqual(oracle.click_calls.count("task/claim/all"), 1)
        adapter.end_mission_reward()
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("MISSION_NOTICE"))
        self.assertGreaterEqual(len(gate_calls), 1)

    def test_alas_owned_claim_requires_separate_opt_in(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertFalse(adapter.mission_claim_allowed())
        self.assertFalse(adapter.appear(NamedButton("MISSION_MULTI")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_MULTI")))

        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))

        self.assertNotIn("task/claim/all", oracle.click_calls)

        opted_in = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mission_claim_once=True,
        )
        opted_in.begin_mission_reward(daily=True, weekly=False)
        self.assertTrue(opted_in.mission_claim_allowed())

    def test_alas_owned_reward_popup_alias_uses_exact_semantic_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_alas_owned_reward_popup_alias_rejects_ambiguity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": True,
        }
        adapter.begin_mission_reward(daily=True, weekly=False)

        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("GET_ITEMS_1"))
        self.assertEqual(oracle.click_calls, [])

    def test_alas_owned_guild_popup_cancel_alias_uses_reviewed_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {"overlay/guild-message/close": True}
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))
        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("GUILD_POPUP_CONFIRM"))

    def test_weekly_only_and_numeric_row_paths_remain_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mission_reward(daily=False, weekly=True)

        self.assertFalse(adapter.appear(NamedButton("MISSION_NOTICE")))
        self.assertFalse(
            adapter.image_color_count(
                NamedButton("MISSION_WEEKLY_RED_DOT"),
                color=(206, 81, 66),
                threshold=221,
                count=20,
            )
        )
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW
        self.assertFalse(adapter.match_template_color(NamedButton("MISSION_SINGLE")))
        self.assertTrue(adapter.match_template_color(NamedButton("MISSION_SINGLE")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_SINGLE"))
        self.assertEqual(oracle.click_calls, [])

    def test_default_navbar_requires_exact_mission_entry_click(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        with self.assertRaises(SemanticGateClosed):
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_0"),
                color=(247, 255, 173),
                threshold=180,
                count=100,
            )

    def test_mission_navbar_reuses_alas_click_with_typed_image_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=True)
        adapter.click(NamedButton("MAIN_GOTO_MISSION"))

        receipt = adapter.click(NamedButton("REWARD_SIDE_NAVBAR_0_4"))

        self.assertEqual(receipt.semantic_id, "task/nav/weekly")
        self.assertEqual(oracle.click_calls, ["main/task", "task/nav/weekly"])

    def test_unknown_presence_is_false_only_on_proven_mission_surface(self):
        adapter, oracle, gate_calls = self.make_adapter()
        adapter.begin_mission_reward(daily=True, weekly=False)
        oracle.exists_values["main/task"] = True

        self.assertFalse(adapter.appear(NamedButton("UNRELATED_PAGE_CHECK")))

        oracle.exists_values.clear()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("UNRELATED_PAGE_CHECK"))
        self.assertGreaterEqual(len(gate_calls), 1)

    def test_reward_surface_keeps_passive_alas_page_scan_fail_closed(self):
        adapter, oracle, _ = self.make_adapter()

        self.assertFalse(adapter.mission_reward_active())
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertTrue(adapter.mission_reward_active())
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

        adapter.end_mission_reward()
        self.assertFalse(adapter.mission_reward_active())
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_render_transition_staleness_has_bounded_presence_grace(self):
        adapter, oracle, _ = self.make_adapter()

        def stale(_semantic_id):
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = stale
        self.assertFalse(adapter.appear(NamedButton("REWARD_CHECK")))
        adapter._observer_stale_since = time.monotonic() - 6.0
        with self.assertRaisesRegex(SemanticGateClosed, "snapshot is stale"):
            adapter.appear(NamedButton("REWARD_CHECK"))

    def test_reviewed_mission_transition_has_bounded_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        adapter.click(NamedButton("GOTO_MAIN"))
        oracle.exists_values.clear()
        oracle.enabled_values.clear()

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        adapter._mission_context.passive_transition_until = time.monotonic() - 1.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))

    def test_mission_entry_alias_cannot_double_click_during_transition(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["main/task"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        adapter.click(NamedButton("MAIN_GOTO_MISSION"))
        duplicate = adapter.click(NamedButton("MAIN_GOTO_MISSION_WHITE"))

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_MISSION_WHITE")))
        self.assertEqual(oracle.click_calls, ["main/task"])
        self.assertEqual(duplicate.semantic_id, "main/task")

    def test_reward_summary_entry_alias_is_idempotent(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mission_reward(daily=True, weekly=False)

        first = adapter.click(NamedButton("MAIN_GOTO_REWARD"))
        duplicate = adapter.click(NamedButton("MAIN_GOTO_REWARD_WHITE"))

        self.assertEqual(first, duplicate)
        self.assertEqual(oracle.click_calls, ["main/more"])

    def test_mission_no_claim_round_trip_enters_and_exits(self):
        adapter, oracle, gate_calls = self.make_adapter()

        receipt = adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(receipt.outcome, "nothing-claimable")
        self.assertFalse(receipt.claim_injected)
        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(
            [call[0] for call in oracle.wait_calls],
            ["task/page/back", "main/task"],
        )
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claimable_state_exits_then_fails_closed(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL

        with self.assertRaises(MissionClaimableDetected) as raised:
            adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(
            raised.exception.page.disposition,
            MissionDisposition.CLAIMABLE_ALL,
        )
        self.assertFalse(hasattr(raised.exception, "claim_receipt"))
        self.assertEqual(len(gate_calls), 1)

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_mission_dismisses_only_reviewed_overlay_close(self, _sleep):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values = {
            "main/task": False,
            "overlay/bulletin/close": False,
            "overlay/guild-message/close": True,
        }
        oracle.enable_main_after_overlay_click = True

        receipt = adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(
            receipt.dismissed_overlays,
            ("overlay/guild-message/close",),
        )
        self.assertEqual(
            oracle.click_calls,
            ["overlay/guild-message/close", "main/task", "task/page/back"],
        )
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claim_all_closes_popup_and_proves_unfinished(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_dispositions = [
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.UNFINISHED,
        ]

        receipt = adapter.claim_mission_rewards_once(timeout_seconds=12)

        self.assertEqual(receipt.outcome, "claimed-all-once")
        self.assertEqual(receipt.claim_input_count, 1)
        self.assertEqual(
            oracle.click_calls,
            [
                "main/task",
                "task/claim/all",
                "reward/award-info/close",
                "task/page/back",
            ],
        )
        self.assertEqual(
            oracle.wait_any_calls[0][0],
            (
                "reward/award-info/close",
                "reward/award-info1/close",
            ),
        )
        self.assertEqual(len(gate_calls), 1)

    def test_reward_hook_claim_requires_separate_opt_in(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_dispositions = [
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.UNFINISHED,
        ]

        receipt = adapter.run_mission_reward(
            timeout_seconds=12,
            allow_claim_once=True,
        )

        self.assertEqual(receipt.outcome, "claimed-all-once")
        self.assertEqual(receipt.claim_input_count, 1)
        self.assertIn("task/claim/all", oracle.click_calls)
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claim_refuses_row_only_before_claim_input(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW

        with self.assertRaises(SemanticGateClosed):
            adapter.claim_mission_rewards_once(timeout_seconds=12)

        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(len(gate_calls), 1)

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

    def test_environment_factory_captures_one_claim_budget_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertTrue(session.allow_mission_claim_once)

    def test_environment_factory_parses_commission_reward_budget(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertEqual(session.commission_reward_budget, 1)

        environment["ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET"] = "01"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_rejects_removed_boolean_reward_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_keeps_tactical_reward_opt_in_separate(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertTrue(session.allow_tactical_rewards)
        self.assertEqual(session.commission_reward_budget, 0)

    def test_environment_factory_parses_canonical_commission_start_budget(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_COMMISSION_START_BUDGET": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")
        self.assertEqual(session.commission_start_budget, 1)

        environment["ALAS_SEMANTIC_COMMISSION_START_BUDGET"] = "01"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_parses_new_bounded_mutation_budgets(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET": "1",
            "ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET": "2",
            "ALAS_SEMANTIC_RESEARCH_START_BUDGET": "3",
            "ALAS_SEMANTIC_DORM_COLLECT_BUDGET": "4",
            "ALAS_SEMANTIC_DORM_FEED_BUDGET": "5",
            "ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET": "6",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertEqual(session.tactical_assign_budget, 1)
        self.assertEqual(session.research_reward_budget, 2)
        self.assertEqual(session.research_start_budget, 3)
        self.assertEqual(session.dorm_collect_budget, 4)
        self.assertEqual(session.dorm_feed_budget, 5)
        self.assertEqual(session.build_submit_budget, 6)

        environment["ALAS_SEMANTIC_DORM_FEED_BUDGET"] = "05"
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
    def test_swipe_uses_one_exact_adb_input_command(self):
        command = (
            "shell",
            "input",
            "swipe",
            "1257",
            "330",
            "1257",
            "390",
            "500",
        )
        bridge = ScriptedAdbBridge({command: ""})

        bridge.swipe(1257, 330, 1257, 390, 500)

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
