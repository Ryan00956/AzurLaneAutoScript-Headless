import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    AlasCampaignDecisionPreview,
    MissionClaimableDetected,
    AndroidPackageFingerprint,
    Bounds,
    BuildPool,
    ButtonState,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapState,
    CampaignMapViewportSwipeProof,
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


class CampaignGridButton:
    def __init__(self, global_location):
        self.location = (0, 0)
        self.corner = object()
        self.button = (1, 2, 3, 4)
        self.__str__ = global_location


def make_campaign_combat_state(generation=51, *, after=False):
    cell = CampaignMapCellState(
        row=6,
        column=4,
        node="D6",
        button_path="root/DragLayer/plane/quads/chapter_cell_quad_6_4",
        point=Point(640, 360),
        bounds=Bounds(600, 320, 680, 400),
    )
    enemies = () if after else (
        CampaignMapEnemyState(
            row=6,
            column=4,
            node="D6",
            object_id=104,
            sprite="zl2",
            scale=2,
            genre="Main",
            level=114,
            fighting=True,
        ),
    )
    return CampaignMapState(
        generation=generation,
        stage_code="12-4",
        rows=8,
        columns=11,
        cells=(cell,),
        land_nodes=("A1",),
        fleets=(
            CampaignMapFleetState(
                marker="cell_fleet_shengwang_younv",
                node="D6",
                ammo=(4 if after else 5),
                ammo_capacity=5,
            ),
        ),
        enemies=enemies,
        pickups=(),
        displayed_fleet_index=1,
        current_fleet_marker="cell_fleet_shengwang_younv",
        current_fleet_roster_sprites=("shengwang_younv",),
    )


def make_campaign_combat_decision(generation=51):
    return AlasCampaignDecisionPreview(
        generation=generation,
        stage_code="12-4",
        battle_count=0,
        branch_name="battle_0",
        fleet_index=1,
        fleet_marker="cell_fleet_shengwang_younv",
        origin_node="D6",
        target_node="D6",
        target_kind="enemy",
        expected="combat",
        cost=0,
        weight=50.0,
        route_nodes=("D6",),
        goto_nodes=("D6",),
        step_optimize=False,
        turning_optimize=True,
    )


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
        self.research_projects_visible_value = True
        self.research_detail_value = SimpleNamespace(
            code="G-412",
            resource_id="gold",
            resource_required=1500,
            can_start=True,
            can_queue=True,
            is_running=False,
        )
        self.research_queue_visible_value = True
        self.research_queue_value = SimpleNamespace(
            entries=(),
            reward_claimable=False,
            empty_slots=5,
            first_remaining_seconds=0,
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
        self.build_queue_visible_value = False
        self.main_gold_value = 10000
        self.build_gold_value = 10000
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
        self.dorm_empty_food_cancel_value = False
        self.campaign_menu_value = False
        self.campaign_page_value = False
        self.campaign_page_error = None
        self.campaign_state_value = SimpleNamespace(
            generation=20,
            chapter_name="第一章",
            stages=(),
        )
        self.campaign_preparation_value = None
        self.campaign_preparation_error = None
        self.campaign_fleet_generation = 30
        self.campaign_fleets = {
            "fleet1": 1,
            "fleet2": 2,
            "submarine": 1,
        }
        self.campaign_fleet_dropdown_row = None
        self.campaign_oil_value = 9504
        self.campaign_in_map_value = False
        self.campaign_map_generation = 50
        self.campaign_map_state_calls = []
        self.campaign_map_target_raycast_top = True
        self.campaign_map_swipe_calls = []
        self.campaign_map_state_value = SimpleNamespace(
            generation=51,
            stage_code="12-4",
            rows=8,
            columns=11,
            cells=tuple(range(68)),
            land_nodes=tuple(range(20)),
            fleets=(SimpleNamespace(node="D6"), SimpleNamespace(node="F8")),
            enemies=(SimpleNamespace(node="C6"), SimpleNamespace(node="D6")),
            pickups=(SimpleNamespace(node="F2"),),
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
        if not self.research_projects_visible_value:
            raise SemanticGateClosed("research page identity is not proven")
        return tuple(self.research_project_values)

    def click_research_project(self, slot):
        self.click_calls.append("research/project/{0}".format(slot))
        return self.click_receipt("research/project/{0}".format(slot))

    def research_detail_state(self):
        return self.research_detail_value

    def research_queue_state(self):
        if not self.research_queue_visible_value:
            raise SemanticGateClosed("research queue identity is not proven")
        return self.research_queue_value

    def research_start_prompt_cost(self):
        return self.research_prompt_cost

    def research_queue_add_available(self):
        return self.enabled_values.get("research/detail/queue", True)

    def click_research_queue_add(self):
        return self.click("research/detail/queue")

    def build_selected_pool(self):
        return self.build_pool_value

    def build_costs(self):
        return self.build_cost_value

    def build_submit_state(self):
        return self.build_submit_value

    def build_coins_owned(self):
        return self.build_gold_value

    def build_queue_empty(self):
        return self.build_queue_empty_value

    def build_queue_timers(self):
        if not self.build_queue_visible_value:
            raise SemanticGateClosed("construction queue is not visible")
        return self.build_queue_timer_values

    def main_gold(self):
        return self.main_gold_value

    def dorm_state(self):
        return self.dorm_state_value

    def dorm_feed_state(self):
        return self.dorm_feed_state_value

    def dorm_empty_food_cancel_available(self):
        return self.dorm_empty_food_cancel_value

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
        if self.campaign_page_error is not None:
            raise self.campaign_page_error
        return self.campaign_page_value

    def campaign_page_state(self):
        return self.campaign_state_value

    def campaign_is_in_map(self):
        return self.campaign_in_map_value

    def campaign_map_entry_state(self):
        if not self.campaign_in_map_value:
            raise SemanticGateClosed("campaign map-scene identity is absent")
        return SimpleNamespace(
            generation=self.campaign_map_generation,
            root_path="LevelCamera/Canvas/UIMain/LevelGrid",
            button_paths=(
                "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat",
            ),
            image_paths=(
                "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                "display/mask/sea",
            ),
        )

    def campaign_map_state(
        self,
        stage_code,
        *,
        columns,
        rows,
        land_cells,
        expected_fleet_count,
    ):
        self.campaign_map_state_calls.append(
            (
                stage_code,
                columns,
                rows,
                tuple(land_cells),
                expected_fleet_count,
            )
        )
        return self.campaign_map_state_value

    def campaign_map_cell_input(self, state, node):
        cell = next(item for item in state.cells if item.node == node)
        return ButtonState(
            name="chapter_cell_quad_6_4",
            path=cell.button_path,
            active_in_hierarchy=True,
            active_and_enabled=True,
            interactable=True,
            raycast_top=True,
            point=cell.point,
            bounds=cell.bounds,
            raw={},
        )

    def campaign_map_cell_viewport_target(self, state, node):
        return replace(
            self.campaign_map_cell_input(state, node),
            raycast_top=self.campaign_map_target_raycast_top,
        )

    def campaign_map_viewport_swipe(
        self,
        state,
        target_node,
        intent,
        *,
        start,
        end,
        duration_ms,
        columns,
        rows,
        land_cells,
        expected_fleet_count,
    ):
        self.campaign_map_swipe_calls.append(
            (
                target_node,
                intent,
                start,
                end,
                duration_ms,
                columns,
                rows,
                tuple(land_cells),
                expected_fleet_count,
            )
        )
        target = next(cell for cell in state.cells if cell.node == target_node)
        after_point = Point(target.point.x + 200, target.point.y)
        after_bounds = Bounds(
            target.bounds.left + 200,
            target.bounds.top,
            target.bounds.right + 200,
            target.bounds.bottom,
        )
        post_state = replace(
            state,
            generation=state.generation + 2,
            cells=tuple(
                replace(cell, point=after_point, bounds=after_bounds)
                if cell.node == target_node
                else cell
                for cell in state.cells
            ),
        )
        self.campaign_map_state_value = post_state
        self.campaign_map_target_raycast_top = True
        return CampaignMapViewportSwipeProof(
            semantic_id="campaign/map/viewport/" + target_node,
            target_node=target_node,
            pre_generation=state.generation,
            input_generation=state.generation + 1,
            post_generation=post_state.generation,
            name=intent.name,
            grid_vector=intent.grid_vector,
            pixel_vector=intent.pixel_vector,
            start=start,
            end=end,
            duration_ms=duration_ms,
            coherent_cell_count=len(state.cells),
            median_cell_delta=(200.0, 0.0),
            maximum_delta_residual=0.0,
            target_path=target.button_path,
            target_before_point=target.point,
            target_after_point=after_point,
            target_after_bounds=after_bounds,
            post_state=post_state,
        )

    def click_campaign_map_cell(self, state, node):
        target = self.campaign_map_cell_input(state, node)
        semantic_id = "campaign/map/grid/" + node
        self.click_calls.append(semantic_id)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation + 1,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_mode_switch_state(self):
        return "hard"

    def campaign_oil(self):
        return self.campaign_oil_value

    def campaign_stage_actionable(self, stage_code):
        return any(
            stage.stage_code == stage_code and stage.button.actionable
            for stage in self.campaign_state_value.stages
        )

    def click_campaign_stage(self, stage_code):
        self.click_calls.append("campaign/stage/" + stage_code)
        self.campaign_preparation_value = SimpleNamespace(kind="map")
        return self.click_receipt("campaign/stage/" + stage_code, generation=7)

    def campaign_preparation_state(self, stage_code):
        if self.campaign_preparation_error is not None:
            raise self.campaign_preparation_error
        return self.campaign_preparation_value

    def click_campaign_map_preparation(self, stage_code):
        self.click_calls.append("campaign/map-preparation/proceed")
        self.campaign_preparation_value = SimpleNamespace(kind="fleet")
        return self.click_receipt(
            "campaign/map-preparation/proceed", generation=8
        )

    def cancel_campaign_map_preparation(self, stage_code):
        self.click_calls.append("campaign/map-preparation/cancel")
        self.campaign_preparation_value = None
        return self.click_receipt(
            "campaign/map-preparation/cancel", generation=9
        )

    def cancel_campaign_fleet_preparation(self, stage_code):
        self.click_calls.append("campaign/fleet-preparation/cancel")
        self.campaign_preparation_value = None
        return self.click_receipt(
            "campaign/fleet-preparation/cancel", generation=9
        )

    def campaign_fleet_selection_state(self, stage_code):
        rows = tuple(
            SimpleNamespace(
                row_key=row_key,
                selected_fleet=(selected or None),
                in_use=bool(selected),
                ship_levels=((100,) if selected else ()),
                clear_button=SimpleNamespace(
                    generation=self.campaign_fleet_generation,
                    point=Point(2, 3),
                    bounds=Bounds(1, 2, 3, 4),
                    path="root/{0}/clear".format(row_key),
                ),
            )
            for row_key, selected in self.campaign_fleets.items()
        )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            stage_code=stage_code,
            surface_fleets=(
                int(bool(self.campaign_fleets["fleet1"]))
                + int(bool(self.campaign_fleets["fleet2"])),
                2,
            ),
            submarine_fleets=(int(bool(self.campaign_fleets["submarine"])), 1),
            mob_oil_cost=42,
            boss_oil_cost=55,
            submarine_oil_cost=17,
            rows=rows,
            sortie_button=SimpleNamespace(actionable=True),
        )

    def campaign_fleet_dropdown_state(self):
        if self.campaign_fleet_dropdown_row is None:
            return None
        if self.campaign_fleet_dropdown_row == "submarine":
            selected = (self.campaign_fleets["submarine"],)
        else:
            selected = (
                self.campaign_fleets["fleet1"],
                self.campaign_fleets["fleet2"],
            )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            active_indices=tuple(
                sorted(set(value for value in selected if value))
            ),
        )

    def click_campaign_fleet_row(self, row_key, action):
        if action == "select":
            self.campaign_fleet_dropdown_row = row_key
        elif action == "clear":
            self.campaign_fleets[row_key] = 0
        else:
            raise AssertionError("unexpected fake campaign fleet action")
        self.campaign_fleet_generation += 1
        semantic_row = (
            "submarine/1"
            if row_key == "submarine"
            else row_key.replace("fleet", "fleet/")
        )
        semantic_id = "campaign/fleet-preparation/{0}/{1}".format(
            semantic_row, action
        )
        self.click_calls.append(semantic_id)
        return self.click_receipt(
            semantic_id, generation=self.campaign_fleet_generation
        )

    def click_campaign_fleet_option(self, index):
        if self.campaign_fleet_dropdown_row is None:
            raise AssertionError("fake campaign fleet dropdown is closed")
        if self.campaign_fleet_dropdown_row == "submarine":
            active = {self.campaign_fleets["submarine"]}
        else:
            active = {
                self.campaign_fleets["fleet1"],
                self.campaign_fleets["fleet2"],
            }
        active.discard(0)
        if index not in active:
            self.campaign_fleets[self.campaign_fleet_dropdown_row] = index
        self.campaign_fleet_dropdown_row = None
        self.campaign_fleet_generation += 1
        semantic_id = "campaign/fleet-preparation/option/{0}".format(index)
        self.click_calls.append(semantic_id)
        return self.click_receipt(
            semantic_id, generation=self.campaign_fleet_generation
        )

    def click_campaign_sortie(self, stage_code):
        self.click_calls.append("campaign/fleet-preparation/sortie")
        self.campaign_preparation_value = None
        self.campaign_in_map_value = True
        self.campaign_map_generation = self.campaign_fleet_generation + 3
        return self.click_receipt(
            "campaign/fleet-preparation/sortie",
            generation=self.campaign_fleet_generation,
        )

    def tactical_slots(self):
        return tuple(self.tactical_slot_values)

    def tactical_books(self):
        return tuple(self.tactical_book_values)

    def tactical_remaining_seconds(self):
        return tuple(self.tactical_remaining_values)

    def tactical_continue_prompt_text(self):
        return self.tactical_prompt_text

    @staticmethod
    def click_receipt(semantic_id, generation=7):
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=generation,
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

    def test_original_login_handler_uses_exact_semantic_entry_context(self):
        adapter, oracle, _ = self.make_adapter()

        adapter.begin_login()
        self.assertTrue(adapter.match_template_color(NamedButton("LOGIN_CHECK")))
        receipt = adapter.click(NamedButton("LOGIN_CHECK"))
        original_enabled = oracle.enabled

        def stale_login_probe(_semantic_id):
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = stale_login_probe
        self.assertFalse(adapter.match_template_color(NamedButton("LOGIN_CHECK")))
        oracle.enabled = original_enabled
        self.assertFalse(adapter.appear(NamedButton("ANDROID_NO_RESPOND")))
        adapter._login_context.passive_transition_until = 0.0
        bulletin = adapter.click(NamedButton("LOGIN_ANNOUNCE"))
        self.assertFalse(adapter.appear(NamedButton("LOGIN_RETURN_SIGN")))

        self.assertEqual(receipt.semantic_id, "login/enter")
        self.assertEqual(bulletin.semantic_id, "overlay/bulletin/close")
        self.assertEqual(
            oracle.click_calls, ["login/enter", "overlay/bulletin/close"]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "nested semantic"):
            adapter.begin_campaign_pre_sortie("12-4")

        adapter.end_login()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("ANDROID_NO_RESPOND"))

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

    def test_original_login_popup_handler_uses_exact_expired_data_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/login-data-expired/confirm"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = False
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM_WHITE")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_WHITE_LOGIN"))

        self.assertEqual(receipt.semantic_id, "overlay/login-data-expired/confirm")
        self.assertEqual(
            oracle.click_calls, ["overlay/login-data-expired/confirm"]
        )
        self.assertGreater(
            adapter._login_context.passive_transition_until,
            time.monotonic() + 50.0,
        )

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
        self.assertEqual(
            adapter.semantic_id_for("DORM_FEED_CANCEL"),
            "dorm/empty-food/cancel",
        )
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BUILD_CHECK"))

    def test_dorm_page_check_yields_to_empty_food_modal(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.dorm_empty_food_cancel_value = True

        self.assertFalse(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        receipt = adapter.click(NamedButton("DORM_FEED_CANCEL"))

        self.assertEqual(receipt.semantic_id, "dorm/empty-food/cancel")

    def test_dorm_page_check_yields_to_feed_panel_close(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = True

        self.assertFalse(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        receipt = adapter.click(NamedButton("DORM_FEED_CANCEL"))

        self.assertEqual(receipt.semantic_id, "dorm/feed/close")

    def test_dorm_feed_entry_suppresses_only_transition_close(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["dorm/feed/close"] = False

        entry = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertGreater(
            adapter._dorm_context.passive_transition_until,
            time.monotonic() + 40.0,
        )
        oracle.enabled_values["dorm/feed/close"] = True
        self.assertFalse(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        duplicate = adapter.click(NamedButton("DORM_FEED_ENTER"))

        self.assertEqual(duplicate, entry)
        self.assertEqual(oracle.click_calls, ["dorm/feed"])

        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CHECK")))
        close = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertEqual(close.semantic_id, "dorm/feed/close")
        self.assertEqual(oracle.click_calls, ["dorm/feed", "dorm/feed/close"])

    def test_dorm_empty_food_cancel_allows_a_fresh_entry(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["dorm/feed/close"] = False

        adapter.click(NamedButton("DORM_FEED_ENTER"))
        duplicate = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertEqual(duplicate.semantic_id, "dorm/feed")
        self.assertEqual(oracle.click_calls, ["dorm/feed"])

        oracle.dorm_empty_food_cancel_value = True
        adapter.click(NamedButton("DORM_FEED_CANCEL"))
        oracle.dorm_empty_food_cancel_value = False
        adapter.click(NamedButton("DORM_FEED_ENTER"))

        self.assertEqual(
            oracle.click_calls,
            ["dorm/feed", "dorm/empty-food/cancel", "dorm/feed"],
        )

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
        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_RESEARCH_START"))

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

    def test_research_start_budget_can_admit_one_existing_running_queue_add(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                code="G-412",
                status=ResearchProjectStatus.RUNNING,
            )
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()
        adapter.click(NamedButton("ENTRANCE_1"))

        receipt = adapter.click(NamedButton("RESEARCH_QUEUE_ADD"))
        duplicate = adapter.click(NamedButton("RESEARCH_QUEUE_ADD"))

        self.assertEqual(receipt.semantic_id, "research/detail/queue")
        self.assertEqual(duplicate, receipt)
        self.assertEqual(adapter._research_context.start_budget, 1)
        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        confirm = adapter.click(NamedButton("POPUP_CONFIRM_RESEARCH_QUEUE"))
        self.assertEqual(confirm.semantic_id, "research/queue/confirm")
        self.assertEqual(adapter._research_context.start_budget, 0)
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/queue",
                "research/queue/confirm",
            ],
        )

        gated = AlasSemanticAdapter(oracle, lambda: None)
        gated.begin_research()
        gated.click(NamedButton("ENTRANCE_1"))
        with self.assertRaisesRegex(SemanticGateClosed, "budgeted running project"):
            gated.click(NamedButton("RESEARCH_QUEUE_ADD"))

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

    def test_dorm_feed_postcondition_tolerates_transient_card_animation(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()
        original = oracle.dorm_feed_state
        transient = {"raised": False}

        def flaky_state():
            if oracle.click_calls and not transient["raised"]:
                transient["raised"] = True
                raise SemanticGateClosed("dorm feed item image is absent or ambiguous")
            return original()

        oracle.dorm_feed_state = flaky_state
        receipts = adapter.dorm_feed_food(0, 1)

        self.assertTrue(transient["raised"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.click_calls, ["dorm/feed/item/50001"])

    def test_dorm_feed_precondition_waits_for_stable_panel(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()
        original = oracle.dorm_feed_state
        transient = {"raised": False}

        def flaky_state():
            if not transient["raised"]:
                transient["raised"] = True
                raise SemanticGateClosed("dorm feed panel identity is not proven")
            return original()

        oracle.dorm_feed_state = flaky_state
        receipts = adapter.dorm_feed_food(0, 1)

        self.assertTrue(transient["raised"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.click_calls, ["dorm/feed/item/50001"])

    def test_dorm_feed_state_waits_for_complete_typed_panel(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        original = oracle.dorm_feed_state
        attempts = 0

        def flaky_state():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise SemanticGateClosed("dorm feed panel identity is not proven")
            return original()

        oracle.dorm_feed_state = flaky_state
        state = adapter.dorm_feed_state()

        self.assertEqual(state.food, 0)
        self.assertEqual(attempts, 3)

    def test_dorm_feed_proof_allows_only_bounded_ship_consumption(self):
        oracle = FakeOracle()
        original_click = oracle.click_dorm_food

        def click_with_one_consumption_tick(item_id):
            receipt = original_click(item_id)
            state = oracle.dorm_feed_state_value
            oracle.dorm_feed_state_value = SimpleNamespace(
                food=state.food - 18,
                capacity=state.capacity,
                items=state.items,
            )
            return receipt

        oracle.click_dorm_food = click_with_one_consumption_tick
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 1)

        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.dorm_feed_state_value.food, 982)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 4)

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

    def test_build_coin_count_falls_back_to_proven_build_resource_panel(self):
        oracle = FakeOracle()
        oracle.build_gold_value = 81908
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_build()

        self.assertEqual(adapter.build_coins_owned(), 81908)
        self.assertEqual(adapter._build_context.coins_owned, 81908)

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

    def test_build_warning_accepts_only_alas_gacha_prep_alias(self):
        oracle = FakeOracle()
        oracle.enabled_values["build/warning/confirm"] = True
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_PREP"))

        self.assertEqual(receipt.semantic_id, "build/warning/confirm")
        self.assertEqual(oracle.click_calls, ["build/warning/confirm"])

        oracle.enabled_values["build/warning/confirm"] = False
        oracle.enabled_values["build/prep/confirm"] = True
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM_GACHA_PREP")))
        with self.assertRaisesRegex(SemanticGateClosed, "exact warning"):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_PREP"))

    def test_build_navbars_and_queue_observations_feed_alas_primitives(self):
        oracle = FakeOracle()
        oracle.build_queue_visible_value = True
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

    def test_build_queue_goto_main_uses_typed_queue_identity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.build_queue_visible_value = True
        oracle.enabled_values["build/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "build/page/back")
        self.assertEqual(oracle.click_calls, ["build/page/back"])

    def test_tactical_navigation_from_build_queue_has_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.build_queue_visible_value = True
        oracle.enabled_values["build/page/back"] = True

        adapter.click(NamedButton("GOTO_MAIN"))

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_tactical_back_has_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.enabled_values["tactical/dock/back"] = False
        oracle.enabled_values["tactical/page/back"] = True

        receipt = adapter.click(NamedButton("BACK_ARROW"))
        oracle.enabled_values.clear()
        oracle.enabled_values["tactical/dock/back"] = False
        oracle.enabled_values["tactical/page/back"] = False
        duplicate = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(receipt.semantic_id, "tactical/page/back")
        self.assertEqual(duplicate, receipt)
        self.assertEqual(oracle.click_calls, ["tactical/page/back"])
        self.assertFalse(adapter.appear(NamedButton("SP_CHECK")))

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

    def test_campaign_menu_entry_has_bounded_transition_grace(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_error = SemanticGateClosed(
            "campaign page identity is not proven"
        )

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            receipt = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_CAMPAIGN"))
            duplicate = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_CAMPAIGN"))
            self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))

        self.assertEqual(duplicate, receipt)
        self.assertEqual(oracle.click_calls, ["campaign-menu/normal"])
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=31.0):
            with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
                adapter.appear(NamedButton("CAMPAIGN_CHECK"))
        adapter.end_campaign_pre_sortie()

    def test_resumed_map_completes_campaign_menu_navigation_hop(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_in_map_value = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))

    def test_campaign_chapter_check_and_back_require_typed_page_identity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertEqual(adapter.campaign_page_state().chapter_name, "第一章")
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BACK_ARROW"))
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_page_state_retries_only_generation_coherence(self):
        adapter, oracle, _ = self.make_adapter()
        expected = oracle.campaign_state_value
        attempts = []

        def transient_page_state():
            attempts.append(True)
            if len(attempts) < 3:
                raise SemanticGateClosed("campaign snapshots are not coherent")
            return expected

        oracle.campaign_page_state = transient_page_state

        self.assertIs(adapter.campaign_page_state(), expected)
        self.assertEqual(len(attempts), 3)

        def identity_failure():
            raise SemanticGateClosed("campaign page identity is not proven")

        oracle.campaign_page_state = identity_failure
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            adapter.campaign_page_state()

    def test_campaign_stage_entry_is_exact_and_spends_one_independent_budget(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云下",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.campaign_stage_entry_allowed())
        self.assertTrue(adapter.appear(button))
        receipt = adapter.click(button)

        self.assertEqual(receipt.semantic_id, "campaign/stage/12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        self.assertEqual(oracle.click_calls, ["campaign/stage/12-4"])
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.click(button)
        adapter.end_campaign_pre_sortie()

    def test_campaign_stage_entry_hides_only_bounded_duplicate_probe(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            adapter.click(button)

            def identity_failure(_stage_code):
                raise SemanticGateClosed("campaign page identity is not proven")

            oracle.campaign_stage_actionable = identity_failure
            self.assertFalse(adapter.appear(button))

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=31.0):
            with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
                adapter.appear(button)

        adapter.end_campaign_pre_sortie()

    def test_campaign_stage_entry_defaults_closed_and_rejects_identity_change(self):
        adapter, oracle, _ = self.make_adapter()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云下",
            stages=(stage,),
        )
        button = NamedButton("12-3")
        button.semantic_campaign_stage_code = "12-3"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            adapter.appear(button)
        adapter.end_campaign_pre_sortie()

    def test_campaign_startup_in_map_probe_reuses_typed_non_map_gate(self):
        adapter, _, _ = self.make_adapter()

        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.appear(NamedButton("UNREVIEWED_PAGE_CHECK")))
        adapter.end_campaign_pre_sortie()

    def test_campaign_map_proof_allows_only_passive_unknown_probes(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        oracle.campaign_in_map_value = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("EXERCISE_CHECK"))
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_unknown_surface_keeps_passive_probe_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter._campaign_context.passive_transition_until = time.monotonic() - 1

        def unknown_surface():
            raise SemanticGateClosed("campaign startup surface is not reviewed")

        oracle.campaign_is_in_map = unknown_surface
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_event_list_back_uses_exact_typed_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("BACK_ARROW")))
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])

    def test_campaign_mode_switch_reports_exact_destination_without_input(self):
        adapter, oracle, _ = self.make_adapter()

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("SWITCH_1_HARD")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_1_NORMAL")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_2_HARD")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_2_EX")))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(oracle.click_calls, [])

    def test_campaign_oil_is_typed_and_scoped_to_active_flow(self):
        adapter, _, _ = self.make_adapter()
        with self.assertRaisesRegex(SemanticGateClosed, "outside ALAS"):
            adapter.campaign_oil()

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertEqual(adapter.campaign_oil(), 9504)
        adapter.end_campaign_pre_sortie()

    def test_campaign_auto_search_resources_feed_original_alas_switch(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = True
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)

        for name in (
            "AUTO_SEARCH_ON",
            "AUTO_SEARCH_ON2",
            "AUTO_SEARCH_ON3",
            "AUTO_SEARCH_ON4",
        ):
            self.assertTrue(adapter.appear(NamedButton(name)))
        for name in (
            "AUTO_SEARCH_OFF",
            "AUTO_SEARCH_OFF2",
            "AUTO_SEARCH_OFF3",
            "AUTO_SEARCH_OFF4",
        ):
            self.assertFalse(adapter.appear(NamedButton(name)))

        receipt = adapter.click(NamedButton("AUTO_SEARCH_ON"))
        self.assertEqual(
            receipt.semantic_id, "campaign/map-preparation/auto-search"
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = False
        self.assertTrue(adapter.appear(NamedButton("AUTO_SEARCH_OFF")))
        with self.assertRaisesRegex(SemanticGateClosed, "single-use"):
            adapter.click(NamedButton("AUTO_SEARCH_OFF"))

        self.assertEqual(
            oracle.click_calls,
            ["campaign/stage/12-4", "campaign/map-preparation/auto-search"],
        )

    def test_campaign_pre_sortie_reuses_prepare_and_cancel_states(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_map_preparation_committed())
        adapter.click(entrance)
        self.assertFalse(adapter.campaign_map_preparation_committed())
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation snapshots are not coherent"
        )
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.campaign_preparation_error = None
        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION")))
        with patch.object(
            adapter, "_campaign_preparation_kind", return_value=None
        ):
            adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.campaign_map_preparation_committed())
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation controls are not proven"
        )
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map preparation is transitioning away"
        )
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))
        oracle.campaign_preparation_error = None
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
        self.assertTrue(adapter.appear(NamedButton("FLEET_PREPARATION")))
        with self.assertRaisesRegex(SemanticGateClosed, "authorized budget"):
            adapter.click(NamedButton("FLEET_PREPARATION"))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign fleet preparation is transitioning away"
        )
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))
        oracle.campaign_preparation_error = None
        oracle.campaign_page_value = True
        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        proof = adapter.confirm_campaign_pre_sortie()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "12-4")
        self.assertEqual(proof.preparation_kind, "fleet")
        self.assertEqual(proof.entry_generation, 7)
        self.assertEqual(proof.cancel_generation, 9)
        self.assertEqual(proof.restored_generation, 12)
        self.assertEqual(
            oracle.click_calls,
            [
                "campaign/stage/12-4",
                "campaign/map-preparation/proceed",
                "campaign/fleet-preparation/cancel",
            ],
        )

    def test_campaign_map_to_fleet_transition_has_bounded_slow_adb_grace(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            adapter.click(entrance)
            adapter.click(NamedButton("MAP_PREPARATION"))

        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation controls are not proven"
        )
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=69.0):
            self.assertFalse(adapter.appear(NamedButton("FLEET_PREPARATION")))
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=71.0):
            with self.assertRaisesRegex(SemanticGateClosed, "controls are not proven"):
                adapter.appear(NamedButton("FLEET_PREPARATION"))

        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_defaults_closed_without_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        authorized = adapter.authorize_campaign_fleet_preparation(1, 2, 0)

        self.assertFalse(authorized)
        self.assertEqual(oracle.click_calls, [])
        with self.assertRaisesRegex(SemanticGateClosed, "remaining mutation"):
            adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preflight_rejects_insufficient_budget_before_input(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=2,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        with self.assertRaisesRegex(SemanticGateClosed, "2 < 3"):
            adapter.authorize_campaign_fleet_preparation(1, 2, 0)

        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preflight_uses_submarine_capacity_not_occupancy(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["fleet2"] = 0
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=2,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")

        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 1))
        receipt = adapter.click(NamedButton("FLEET_2_CLEAR"))
        self.assertEqual(
            receipt.semantic_id,
            "campaign/fleet-preparation/fleet/2/clear",
        )
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_reuses_alas_sequence_and_cancels(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))

        # This is the input sequence emitted by ALAS FleetPreparation for the
        # fake initial state (1, 2, 1). Dropdown open/close remains ALAS-owned;
        # only the exact semantic endpoints replace screenshot coordinates.
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        self.assertTrue(adapter.campaign_fleet_row_allowed("fleet2"))
        self.assertFalse(adapter.campaign_fleet_operator_in_use("fleet2"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        self.assertEqual(adapter.campaign_fleet_selected_indices("fleet1"), [1])
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        prepared = adapter.confirm_campaign_fleet_selection()

        self.assertEqual(
            tuple(row.selected_fleet or 0 for row in prepared.rows),
            (1, 2, 0),
        )
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        oracle.campaign_page_value = True
        proof = adapter.confirm_campaign_fleet_preparation()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.initial_fleets, (1, 2, 1))
        self.assertEqual(proof.requested_fleets, (1, 2, 0))
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertEqual(
            proof.mutation_semantic_ids,
            (
                "campaign/fleet-preparation/fleet/2/clear",
                "campaign/fleet-preparation/submarine/1/clear",
                "campaign/fleet-preparation/option/2",
            ),
        )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)

    def test_campaign_fleet_dropdown_rollback_closes_empty_row_without_mutation(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=3,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))

        adapter.close_campaign_fleet_dropdown_for_rollback()

        self.assertIsNone(oracle.campaign_fleet_dropdown_state())
        self.assertEqual(oracle.campaign_fleets, {
            "fleet1": 1,
            "fleet2": 0,
            "submarine": 0,
        })
        adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_defaults_closed_after_fleet_proof(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        self.assertFalse(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        with self.assertRaisesRegex(SemanticGateClosed, "authorized budget"):
            adapter.click(NamedButton("FLEET_PREPARATION"))
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_reuses_exact_alas_click_and_proves_map_root(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        receipt = adapter.click(NamedButton("FLEET_PREPARATION"))
        self.assertEqual(receipt.semantic_id, "campaign/fleet-preparation/sortie")
        self.assertTrue(adapter.campaign_sortie_committed())
        self.assertTrue(adapter.appear(NamedButton("IN_MAP")))
        proof = adapter.confirm_campaign_sortie()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "12-4")
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertEqual(proof.oil_before_sortie, 9504)
        self.assertEqual(proof.required_oil, 97)
        self.assertGreater(proof.map_generation, proof.sortie_generation)
        self.assertEqual(
            proof.map_root_path, "LevelCamera/Canvas/UIMain/LevelGrid"
        )
        self.assertEqual(oracle.click_calls[-1], "campaign/fleet-preparation/sortie")

    def test_campaign_sortie_preconditions_fail_before_input(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "auto search"):
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()

    def test_campaign_map_model_is_read_only_and_context_bound(self):
        oracle = FakeOracle()
        package_checks = []
        adapter = AlasSemanticAdapter(oracle, lambda: package_checks.append(True))
        adapter.begin_campaign_pre_sortie("12-4")

        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((5, 0), (6, 0)),
            expected_fleet_count=2,
        )

        self.assertIs(state, oracle.campaign_map_state_value)
        self.assertEqual(
            oracle.campaign_map_state_calls,
            [("12-4", 11, 8, ((5, 0), (6, 0)), 2)],
        )
        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(len(package_checks), 2)
        adapter.end_campaign_pre_sortie()

        with self.assertRaisesRegex(SemanticGateClosed, "pre-sortie flow"):
            adapter.campaign_map_state(
                columns=11,
                rows=8,
                land_cells=((5, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_combat_defaults_closed_after_alas_decision(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        self.assertIsNone(admission)
        self.assertEqual(oracle.click_calls, [])
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.click(CampaignGridButton((3, 5)))
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_binds_alas_grid_click_and_proves_post_state(self):
        oracle = FakeOracle()
        before = make_campaign_combat_state()
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        self.assertIsNotNone(admission)
        receipt = adapter.click(CampaignGridButton((3, 5)))
        self.assertEqual(receipt.semantic_id, "campaign/map/grid/D6")
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.click(CampaignGridButton((3, 5)))

        oracle.campaign_map_state_value = make_campaign_combat_state(
            generation=55, after=True
        )
        proof = adapter.confirm_campaign_combat(battle_count_after=1)
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.target_node, "D6")
        self.assertEqual(proof.enemy_object_id, 104)
        self.assertEqual((proof.ammo_before, proof.ammo_after), (5, 4))
        self.assertEqual((proof.battle_count_before, proof.battle_count_after), (0, 1))
        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])

    def test_campaign_viewport_swipe_is_one_use_and_updates_exact_grid_geometry(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        self.assertIsNotNone(admission)

        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.375,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        self.assertTrue(adapter.campaign_map_viewport_swipe_committed())
        self.assertEqual(proof.target_before_point, Point(640, 360))
        self.assertEqual(proof.target_after_point, Point(840, 360))
        camera_state = adapter.campaign_camera_state()
        recheck = adapter.recheck_campaign_combat_target_after_camera_view(
            camera_state
        )
        self.assertEqual(recheck.target_node, "D6")
        self.assertEqual(recheck.camera_state_generation, 53)
        with self.assertRaisesRegex(SemanticGateClosed, "token changed"):
            adapter.recheck_campaign_combat_target_after_camera_view(
                replace(camera_state, generation=54)
            )
        receipt = adapter.click(CampaignGridButton((3, 5)))
        self.assertEqual(receipt.point, Point(840, 360))
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.begin_campaign_map_swipe_vector(
                (200.0, 0.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_defaults_closed_and_raw_swipe_stays_rejected(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        oracle.campaign_map_target_raycast_top = False
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "viewport swipe budget"):
            adapter.authorize_campaign_combat(
                make_campaign_combat_decision(), state
            )
        with self.assertRaisesRegex(SemanticGateClosed, "raw ALAS input"):
            adapter.swipe(
                (500, 400),
                (700, 400),
                duration=0.375,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_accepts_alas_whitelist_fallback_only_in_padded_domain(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        intent = adapter.begin_campaign_map_swipe_vector(
            (14.0, -201.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=((900, 600, 1000, 650),),
            blacklist_area=None,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )
        proof = adapter.swipe(
            (772, 482),
            (786, 281),
            duration=0.3375,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        self.assertEqual(proof.end, (786, 281))
        self.assertEqual(len(oracle.campaign_map_swipe_calls), 1)
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_rejects_endpoint_outside_alas_padded_domain(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        intent = adapter.begin_campaign_map_swipe_vector(
            (14.0, -201.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "selection domain"):
            adapter.swipe(
                (126, 482),
                (140, 281),
                duration=0.3375,
                name="MAP_SWIPE_0_2",
                distance_check=True,
            )
        adapter.end_campaign_map_swipe_vector(intent)
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_camera_positioning_is_separate_one_use_empty_cell_contract(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        empty = CampaignMapCellState(
            row=3,
            column=6,
            node="F3",
            button_path="root/DragLayer/plane/quads/chapter_cell_quad_3_6",
            point=Point(640, 80),
            bounds=Bounds(600, 40, 680, 120),
        )
        state = replace(state, cells=state.cells + (empty,))
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_camera_positioning_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        admission = adapter.authorize_campaign_camera_positioning(
            "F3", current
        )
        self.assertEqual(admission.target_node, "F3")
        intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 200.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 300),
            (500, 500),
            duration=0.35,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)
        positioned_state = adapter.campaign_camera_state()
        completed = adapter.complete_campaign_camera_positioning(
            positioned_state
        )

        self.assertEqual(proof.target_node, "F3")
        self.assertEqual(completed, (proof,))
        self.assertTrue(adapter.campaign_camera_positioning_committed())
        self.assertIs(adapter.campaign_camera_positioning_proof(), proof)
        with self.assertRaisesRegex(SemanticGateClosed, "not proven"):
            adapter.campaign_map_viewport_swipe_proof()
        with self.assertRaisesRegex(SemanticGateClosed, "budget unit"):
            adapter.authorize_campaign_camera_positioning("F3", current)
        adapter.end_campaign_pre_sortie()

    def test_campaign_camera_positioning_rejects_enemy_or_default_zero_budget(self):
        state = make_campaign_combat_state()
        for budget, message in ((0, "budget"), (1, "empty sea cell")):
            oracle = FakeOracle()
            oracle.campaign_map_state_value = state
            adapter = AlasSemanticAdapter(
                oracle,
                lambda: None,
                campaign_camera_positioning_budget=budget,
            )
            adapter.begin_campaign_pre_sortie("12-4")
            current = adapter.campaign_map_state(
                columns=11,
                rows=8,
                land_cells=((0, 0),),
                expected_fleet_count=1,
            )
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.authorize_campaign_camera_positioning(
                        "D6", current
                    )
            adapter.end_campaign_pre_sortie()
        with self.assertRaisesRegex(ValueError, "at most two"):
            AlasSemanticAdapter(
                FakeOracle(),
                lambda: None,
                campaign_camera_positioning_budget=3,
            )
        with self.assertRaisesRegex(ValueError, "at most two"):
            AlasSemanticSession(
                "emulator-test",
                "be80ce591a481c12d60c50d6040d40c035b40a2b",
                campaign_camera_positioning_budget=3,
            )

    def test_campaign_camera_positioning_allows_two_original_focus_corrections_then_closes(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        empty = CampaignMapCellState(
            row=3,
            column=6,
            node="F3",
            button_path="root/DragLayer/plane/quads/chapter_cell_quad_3_6",
            point=Point(640, 80),
            bounds=Bounds(600, 40, 680, 120),
        )
        oracle.campaign_map_state_value = replace(
            state, cells=state.cells + (empty,)
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_camera_positioning_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_camera_positioning("F3", current)

        first_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 260.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        first = adapter.swipe(
            (500, 250),
            (500, 510),
            duration=0.35,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(first_intent)
        second_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 80.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-1",
            distance_check=True,
        )
        second = adapter.swipe(
            (500, 370),
            (500, 450),
            duration=0.35,
            name="MAP_SWIPE_0_-1",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(second_intent)
        positioned_state = adapter.campaign_camera_state()

        completed = adapter.complete_campaign_camera_positioning(
            positioned_state
        )

        self.assertEqual(completed, (first, second))
        self.assertEqual(
            adapter.campaign_camera_positioning_proofs(),
            (first, second),
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.begin_campaign_map_swipe_vector(
                (0.0, 80.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_0_-1",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_rejects_route_drift_before_input(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        decision = replace(
            make_campaign_combat_decision(),
            cost=1,
            route_nodes=("D6", "D5"),
        )

        with self.assertRaisesRegex(SemanticGateClosed, "same-cell or three-step route"):
            adapter.authorize_campaign_combat(decision, current)

        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_rejects_failed_postcondition_without_replay(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), current
        )
        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = replace(state, generation=55)

        with self.assertRaisesRegex(SemanticGateClosed, "enemy still exists"):
            adapter.confirm_campaign_combat(battle_count_after=1)

        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_anomalous_receipt_cannot_replay_input(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), current
        )
        exact_click = oracle.click_campaign_map_cell

        def anomalous_click(map_state, node):
            return replace(exact_click(map_state, node), path="wrong/path")

        oracle.click_campaign_map_cell = anomalous_click
        with self.assertRaisesRegex(SemanticGateClosed, "receipt changed"):
            adapter.click(CampaignGridButton((3, 5)))
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.click(CampaignGridButton((3, 5)))

        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])
        adapter.end_campaign_pre_sortie()

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
        adapter.begin_research()
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

    def test_tactical_passive_continue_probe_is_false_without_prompt_or_opt_in(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_tactical()

        self.assertFalse(adapter.cancel_tactical_continue_if_present())

        oracle.tactical_prompt_text = "舰船学习完成，是否继续学习该技能？"
        with self.assertRaises(SemanticGateClosed):
            adapter.cancel_tactical_continue_if_present()

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
        self.assertEqual(
            adapter.semantic_id_for("AUTO_SEARCH_MENU_EXIT"),
            "reward/campaign-total/exit",
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
        adapter._commission_context.passive_transition_until = time.monotonic() - 1
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
        for message in (
            "observer snapshot is stale",
            "observer endpoints are not generation-coherent",
            "Msgbox snapshots are not coherent",
        ):
            with self.subTest(message=message):
                adapter, oracle, _ = self.make_adapter()

                def stale(_semantic_id):
                    raise SemanticGateClosed(message)

                oracle.enabled = stale
                self.assertFalse(adapter.appear(NamedButton("REWARD_CHECK")))
                adapter._observer_stale_since = time.monotonic() - 6.0
                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.appear(NamedButton("REWARD_CHECK"))

    def test_login_activity_handoff_has_bounded_presence_grace(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        adapter.begin_login()
        self.assertFalse(adapter.appear(NamedButton("LOGIN_CHECK")))
        adapter._observer_stale_since = time.monotonic() - 6.0
        self.assertFalse(adapter.appear(NamedButton("LOGIN_CHECK")))
        adapter._login_context.passive_transition_until = 0.0
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
            adapter.appear(NamedButton("LOGIN_CHECK"))

    def test_activity_handoff_outside_login_remains_fail_closed(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
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

    def test_bounded_task_flows_allow_passive_scan_on_proven_surface(self):
        cases = (
            ("begin_research", "reward/page/back"),
            ("begin_dorm", "dorm/page/back"),
            ("begin_build", "build/page/start"),
        )
        for begin_name, semantic_id in cases:
            with self.subTest(flow=begin_name):
                adapter, oracle, _ = self.make_adapter()
                getattr(adapter, begin_name)()
                oracle.exists_values[semantic_id] = True

                self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_bounded_task_flows_begin_with_page_discovery_grace(self):
        for begin_name in (
            "begin_commission",
            "begin_tactical",
            "begin_research",
            "begin_dorm",
            "begin_build",
        ):
            with self.subTest(flow=begin_name):
                adapter, _, _ = self.make_adapter()
                getattr(adapter, begin_name)()
                self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_research_navigation_has_bounded_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        main_entry = adapter.click(NamedButton("MAIN_GOTO_RESHMENU"))
        main_duplicate = adapter.click(NamedButton("MAIN_GOTO_RESHMENU_WHITE"))
        research_entry = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        research_duplicate = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        queue_entry = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))
        queue_duplicate = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))
        back = adapter.click(NamedButton("BACK_ARROW"))
        back_duplicate = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(main_duplicate, main_entry)
        self.assertEqual(research_duplicate, research_entry)
        self.assertEqual(queue_duplicate, queue_entry)
        self.assertEqual(back_duplicate, back)
        self.assertEqual(
            oracle.click_calls,
            [
                "main/tech",
                "research-menu/research",
                "research/queue/enter",
                "research/page/back",
            ],
        )
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        adapter._research_context.passive_transition_until = time.monotonic() - 1.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_research_goto_main_is_idempotent_during_page_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True
        oracle.enabled_values["research/page/back"] = True

        first = adapter.click(NamedButton("GOTO_MAIN"))
        duplicate = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(duplicate, first)
        self.assertEqual(oracle.click_calls, ["research/page/back"])

    def test_dorm_navigation_is_idempotent_during_page_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()

        main = adapter.click(NamedButton("MAIN_GOTO_DORMMENU"))
        main_duplicate = adapter.click(NamedButton("MAIN_GOTO_DORMMENU_WHITE"))
        entry = adapter.click(NamedButton("DORMMENU_GOTO_DORM"))
        entry_duplicate = adapter.click(NamedButton("DORMMENU_GOTO_DORM"))
        back = adapter.click(NamedButton("DORM_GOTO_MAIN"))
        back_duplicate = adapter.click(NamedButton("DORM_GOTO_MAIN"))

        self.assertEqual(main_duplicate, main)
        self.assertEqual(entry_duplicate, entry)
        self.assertEqual(back_duplicate, back)
        self.assertEqual(
            oracle.click_calls,
            ["main/live", "dorm-menu/dorm", "dorm/page/back"],
        )

    def test_cross_flow_virtual_probe_is_false_but_input_stays_forbidden(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("DOCK_CHECK"))

    def test_research_queue_snapshot_is_bounded_across_queue_exit(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        self.assertEqual(adapter.research_queue_empty_slots(), 5)
        oracle.research_queue_visible_value = False

        self.assertEqual(adapter.research_queue_empty_slots(), 5)
        adapter._research_context.last_queue_observed_at = time.monotonic() - 31.0
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            adapter.research_queue_empty_slots()

    def test_research_fill_slots_are_limited_by_current_run_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        self.assertEqual(adapter.research_queue_fill_slots(), 5)
        adapter._research_context.start_budget = 0
        oracle.research_queue_visible_value = False
        self.assertEqual(adapter.research_queue_fill_slots(), 0)

    def test_research_detail_availability_is_false_before_selection(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True

        def absent_detail():
            raise SemanticGateClosed("research detail identity is not proven")

        oracle.research_detail_state = absent_detail

        self.assertFalse(adapter.research_detail_available())

    def test_research_detail_availability_includes_current_run_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_research()

        self.assertFalse(adapter.research_detail_available())
        self.assertTrue(adapter.appear(NamedButton("RESEARCH_UNAVAILABLE")))

        adapter._research_context.start_budget = 1
        self.assertTrue(adapter.research_detail_available())
        self.assertFalse(adapter.appear(NamedButton("RESEARCH_UNAVAILABLE")))

    def test_research_project_snapshot_has_short_render_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        self.assertEqual(adapter.research_projects(), ())
        oracle.research_projects_visible_value = False

        self.assertEqual(adapter.research_projects(), ())
        adapter._research_context.last_projects_observed_at = time.monotonic() - 6.0
        with self.assertRaisesRegex(SemanticGateClosed, "page identity is not proven"):
            adapter.research_projects()

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
            session.click(NamedButton("UNREVIEWED_CLICK"))

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

    def test_environment_factory_bounds_explicit_adb_timeout(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")
        self.assertEqual(session.bridge.command_timeout_seconds, 30.0)

        for malformed in ("030", "0", "121"):
            environment["ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS"] = malformed
            with self.subTest(value=malformed):
                with patch.dict("os.environ", environment, clear=True):
                    with self.assertRaises((SemanticGateClosed, ValueError)):
                        AlasSemanticSession.from_environment("emulator-test")

    def test_session_bounds_observer_freshness_and_process_lease_types(self):
        revision = "be80ce591a481c12d60c50d6040d40c035b40a2b"
        session = AlasSemanticSession(
            "emulator-test",
            revision,
            observer_max_age_ms=300000,
        )
        self.assertEqual(session.observer_max_age_ms, 300000)

        for malformed in (True, 0, 300001):
            with self.subTest(value=malformed):
                with self.assertRaisesRegex(ValueError, "observer max age"):
                    AlasSemanticSession(
                        "emulator-test",
                        revision,
                        observer_max_age_ms=malformed,
                    )
        with self.assertRaisesRegex(ValueError, "package lease"):
            AlasSemanticSession(
                "emulator-test",
                revision,
                package_process_lease=object(),
            )

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
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "7",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": "8",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "9",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": "10",
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": "11",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertEqual(session.tactical_assign_budget, 1)
        self.assertEqual(session.research_reward_budget, 2)
        self.assertEqual(session.research_start_budget, 3)
        self.assertEqual(session.dorm_collect_budget, 4)
        self.assertEqual(session.dorm_feed_budget, 5)
        self.assertEqual(session.build_submit_budget, 6)
        self.assertEqual(session.campaign_stage_entry_budget, 7)
        self.assertEqual(session.campaign_fleet_mutation_budget, 8)
        self.assertEqual(session.campaign_sortie_budget, 9)
        self.assertEqual(session.campaign_combat_budget, 10)
        self.assertEqual(session.campaign_viewport_swipe_budget, 11)
        self.assertEqual(session.campaign_camera_positioning_budget, 0)

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
