import copy
import unittest
from collections import deque
from dataclasses import replace
from types import SimpleNamespace

from alas_headless import (
    Bounds,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapPickupState,
    CampaignMapState,
    Point,
    SemanticGateClosed,
    prepare_alas_campaign_combat_admission,
    preview_alas_campaign_decision,
    preview_alas_campaign_goto_input,
    synchronize_alas_campaign_map,
)


class FakeGrid:
    def __init__(
        self,
        location,
        *,
        is_land=False,
        may_enemy=False,
        may_boss=False,
        may_ammo=False,
        weight=50,
    ):
        self.location = location
        self.is_land = is_land
        self.may_enemy = may_enemy
        self.may_boss = may_boss
        self.may_ammo = may_ammo
        self.weight = weight
        self.reset()

    def reset(self):
        self.is_fleet = False
        self.is_current_fleet = False
        self.is_enemy = False
        self.is_siren = False
        self.is_portal = False
        self.is_ammo = False
        self.enemy_scale = 0
        self.enemy_genre = None
        self.cost = 9999
        self.cost_1 = 9999
        self.cost_2 = 9999
        self.connection = None


class FakeMap:
    def __init__(self):
        self.name = "12-4"
        self.shape = (2, 1)
        self.camera_sight = (-3, -1, 3, 2)
        self.grids = {
            (0, 0): FakeGrid((0, 0), may_enemy=True),
            (1, 0): FakeGrid((1, 0), is_land=True),
            (2, 0): FakeGrid((2, 0), may_ammo=True),
            (0, 1): FakeGrid((0, 1)),
            (1, 1): FakeGrid((1, 1)),
            (2, 1): FakeGrid((2, 1)),
        }
        self.path_starts = []

    def __iter__(self):
        return iter(self.grids.values())

    def __getitem__(self, location):
        return self.grids[tuple(location)]

    def select(self, **attributes):
        return [
            grid
            for grid in self
            if all(getattr(grid, name) == value for name, value in attributes.items())
        ]

    def grid_covered(self, grid, location=None):
        del grid, location
        return []

    def reset(self):
        for grid in self:
            grid.reset()

    def find_path_initial(self, location, has_ambush=True, has_enemy=True):
        del has_ambush, has_enemy
        start = tuple(location)
        self.path_starts.append(start)
        for grid in self:
            grid.cost = 9999
            grid.connection = None
        self[start].cost = 0
        queue = deque((start,))
        while queue:
            current = queue.popleft()
            for offset in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                neighbor = (current[0] + offset[0], current[1] + offset[1])
                if neighbor not in self.grids or self[neighbor].is_land:
                    continue
                cost = self[current].cost + 1
                if cost >= self[neighbor].cost:
                    continue
                self[neighbor].cost = cost
                self[neighbor].connection = current
                if not self[neighbor].is_enemy:
                    queue.append(neighbor)

    def find_path_initial_multi_fleet(self, location_dict, current, has_ambush):
        for fleet, location in sorted(
            location_dict.items(),
            key=lambda item: int(tuple(item[1]) == tuple(current)),
        ):
            self.find_path_initial(location, has_ambush=has_ambush)
            for grid in self:
                setattr(grid, "cost_" + str(fleet), grid.cost)

    def _find_path(self, location):
        location = tuple(location)
        if self[location].cost >= 9999:
            return None
        route = [location]
        while self[route[-1]].connection is not None:
            route.append(self[route[-1]].connection)
        route.reverse()
        return route

    def find_path(self, location, step=0, turning_optimize=False):
        del step, turning_optimize
        return self._find_path(location)


class FakeCampaign:
    def __init__(self):
        self.MAP = FakeMap()
        self.map = "original-map"
        self.config = SimpleNamespace(
            Campaign_UseFleetLock=True,
            Emotion_Mode="ignore",
            EnemyPriority_EnemyScaleBalanceWeight="default_mode",
            MAP_CLEAR_ALL_THIS_TIME=False,
            MAP_HAS_AMBUSH=False,
            MAP_HAS_FLEET_STEP=False,
            MAP_HAS_FORTRESS=False,
            MAP_HAS_MAZE=False,
            MAP_HAS_PORTAL=False,
            POOR_MAP_DATA=True,
        )
        self.map_data_init_calls = 0
        self.fleet_1_location = ()
        self.fleet_2_location = ()
        self.battle_count = 0

    def map_data_init(self, map_):
        self.map_data_init_calls += 1
        self.map = map_
        self.map.reset()
        self.fleet_1_location = ()
        self.fleet_2_location = ()
        self.config.POOR_MAP_DATA = False

    def click(self, *args):
        raise AssertionError("read-only ALAS synchronization attempted input")

    @property
    def fleet_current(self):
        if self.fleet_current_index == 2:
            return self.fleet_2_location
        return self.fleet_1_location

    def find_path_initial(self):
        locations = {1: self.fleet_1_location}
        if self.fleet_2_location:
            locations[2] = self.fleet_2_location
        self.map.find_path_initial_multi_fleet(
            locations,
            current=self.fleet_current,
            has_ambush=self.config.MAP_HAS_AMBUSH,
        )

    def battle_function(self):
        enemies = self.map.select(is_enemy=True)
        enemies = sorted(enemies, key=lambda grid: (grid.weight, grid.cost))
        if not enemies:
            return False
        self.goto(enemies[0], expected="combat")
        return True


class FakeGotoCampaign(FakeCampaign):
    def __init__(self):
        super().__init__()
        self.config.HpControl_UseLowHpRetreat = False
        self.config.HpControl_LowHpRetreatThreshold = 0.2
        self.config.MAP_GRID_CENTER_TOLERANCE = 0.1
        self.fleet_submarine_location = ()
        self.hp = (1.0,)
        self.hp_has_ship = (True,)

    @property
    def _walk_sight(self):
        sight = self.map.camera_sight
        return sight[0], 0, sight[2], sight[3]

    def hp_retreat_triggered(self):
        return bool(
            self.config.HpControl_UseLowHpRetreat
            and any(
                hp < self.config.HpControl_LowHpRetreatThreshold
                for hp, has_ship in zip(self.hp, self.hp_has_ship)
                if has_ship
            )
        )

    def withdraw(self):
        self.device.screenshot()

    def fleet_set(self, index=None, skip_first_screenshot=True):
        del index, skip_first_screenshot
        self.device.screenshot()

    def fleet_ensure(self, index):
        return self.fleet_set(index=index)

    def focus_to(self, location):
        location = tuple(location)
        if location != tuple(self.camera):
            self.device.swipe_vector((1, 1))

    def in_sight(self, location, sight=None):
        location = tuple(location)
        sight = self.map.camera_sight if sight is None else tuple(sight)
        diff = (location[0] - self.camera[0], location[1] - self.camera[1])
        x = max(sight[0], min(sight[2], diff[0]))
        y = max(sight[1], min(sight[3], diff[1]))
        self.focus_to((location[0] - x, location[1] - y))

    def focus_to_grid_center(self, tolerance=None):
        tolerance = (
            self.config.MAP_GRID_CENTER_TOLERANCE
            if tolerance is None
            else tolerance
        )
        if any(abs(value - 0.5) > tolerance for value in self.view.center_offset):
            self.device.swipe_vector((0, 0))
            return True
        return False

    def convert_global_to_local(self, location):
        local = (
            int(location[0] - self.camera[0] + self.view.center_loca[0]),
            int(location[1] - self.camera[1] + self.view.center_loca[1]),
        )
        if local in self.view:
            return self.view[local]
        self.focus_to(location)
        return self.view[local]

    def ambush_color_initial(self):
        del self.device.image

    def enemy_searching_color_initial(self):
        pass

    def grid_annotation(self, location):
        return location

    def before_grid_click(self):
        pass

    def _goto(self, location, expected=""):
        del expected
        location = tuple(location)
        self.movable_before = self.map.select(is_siren=True)
        self.movable_before_normal = self.map.select(is_enemy=True)
        if self.hp_retreat_triggered():
            self.withdraw()
        is_portal = self.map[location].is_portal
        del is_portal
        may_submarine_icon = self.map.grid_covered(
            self.map[location], location=[(0, -1)]
        )
        may_submarine_icon = (
            may_submarine_icon
            and self.fleet_submarine_location
            == may_submarine_icon[0].location
        )
        del may_submarine_icon
        self.fleet_ensure(self.fleet_current_index)
        self.in_sight(location, sight=self._walk_sight)
        self.focus_to_grid_center()
        grid = self.convert_global_to_local(location)
        self.ambush_color_initial()
        self.enemy_searching_color_initial()
        grid.__str__ = self.grid_annotation(location)
        self.before_grid_click()
        self.device.click(grid)
        self.device.screenshot()


def make_state(pickup_node="C1"):
    cells = []
    for row, column, node in (
        (1, 1, "A1"),
        (1, 3, "C1"),
        (2, 1, "A2"),
        (2, 2, "B2"),
        (2, 3, "C2"),
    ):
        cells.append(
            CampaignMapCellState(
                row=row,
                column=column,
                node=node,
                button_path="root/" + node,
                point=Point(10.0, 10.0),
                bounds=Bounds(0.0, 0.0, 20.0, 20.0),
            )
        )
    return CampaignMapState(
        generation=20,
        stage_code="12-4",
        rows=2,
        columns=3,
        cells=tuple(cells),
        land_nodes=("B1",),
        fleets=(
            CampaignMapFleetState("alpha", "A2", 5, 5),
            CampaignMapFleetState("beta", "B2", 4, 5),
        ),
        enemies=(
            CampaignMapEnemyState(
                row=1,
                column=1,
                node="A1",
                object_id=1001,
                sprite="qx1",
                scale=1,
                genre="Light",
                level=10,
                fighting=False,
            ),
        ),
        pickups=(
            CampaignMapPickupState(
                row=int(pickup_node[1:]),
                column=ord(pickup_node[0]) - ord("A") + 1,
                node=pickup_node,
                kind="ammo",
                sprite="event4",
            ),
        ),
        displayed_fleet_index=1,
        current_fleet_marker="alpha",
        current_fleet_roster_sprites=("alpha", "support"),
    )


def make_zero_distance_state():
    state = make_state()
    return replace(
        state,
        fleets=(
            CampaignMapFleetState("alpha", "A1", 5, 5),
            CampaignMapFleetState("beta", "B2", 4, 5),
        ),
        enemies=(replace(state.enemies[0], fighting=True),),
    )


class AlasCampaignMapSyncTests(unittest.TestCase):
    def test_projects_typed_state_and_delegates_routes_to_alas_map(self):
        campaign = FakeCampaign()

        projection = synchronize_alas_campaign_map(campaign, make_state())

        self.assertEqual(campaign.map_data_init_calls, 1)
        self.assertTrue(campaign.map[(0, 1)].is_fleet)
        self.assertTrue(campaign.map[(1, 1)].is_fleet)
        self.assertTrue(campaign.map[(0, 1)].is_current_fleet)
        self.assertTrue(campaign.map[(0, 0)].is_enemy)
        self.assertEqual(campaign.map[(0, 0)].enemy_scale, 1)
        self.assertEqual(campaign.map[(0, 0)].enemy_genre, "Light")
        self.assertTrue(campaign.map[(2, 0)].is_ammo)
        self.assertEqual(campaign.map.path_starts, [(0, 1), (1, 1)])
        self.assertEqual(campaign.fleet_show_index, 1)
        self.assertEqual(campaign.fleet_current_index, 1)
        self.assertEqual(campaign.fleet_1_location, (0, 1))
        self.assertEqual(campaign.fleet_2_location, (1, 1))
        self.assertTrue(campaign.config.POOR_MAP_DATA)
        self.assertEqual(
            campaign.semantic_fleet_locations,
            {"alpha": (0, 1), "beta": (1, 1)},
        )
        self.assertIs(campaign.semantic_map_projection, projection)
        self.assertEqual(
            tuple(
                (
                    fleet.fleet_index,
                    fleet.is_current,
                    fleet.marker,
                    fleet.origin_node,
                    fleet.recommended_enemy_node,
                    fleet.recommended_pickup_node,
                )
                for fleet in projection.fleets
            ),
            (
                (1, True, "alpha", "A2", "A1", "C1"),
                (2, False, "beta", "B2", "A1", "C1"),
            ),
        )
        self.assertEqual(
            projection.fleets[0].enemy_routes[0].nodes,
            ("A2", "A1"),
        )
        self.assertEqual(
            projection.fleets[0].pickup_routes[0].nodes,
            ("A2", "B2", "C2", "C1"),
        )
        self.assertTrue(all(grid.cost == 9999 for grid in campaign.map))

    def test_maps_displayed_fleet_through_alas_reversed_order(self):
        campaign = FakeCampaign()
        campaign.fleets_reversed = True

        projection = synchronize_alas_campaign_map(campaign, make_state())

        self.assertEqual(projection.displayed_fleet_index, 1)
        self.assertEqual(projection.current_fleet_index, 2)
        self.assertEqual(campaign.fleet_show_index, 1)
        self.assertEqual(campaign.fleet_current_index, 2)
        self.assertEqual(campaign.fleet_1_location, (1, 1))
        self.assertEqual(campaign.fleet_2_location, (0, 1))
        self.assertTrue(campaign.map[(0, 1)].is_current_fleet)
        self.assertEqual(
            tuple((fleet.fleet_index, fleet.marker) for fleet in projection.fleets),
            ((1, "beta"), (2, "alpha")),
        )

    def test_rejects_fleet_roster_identity_disagreement(self):
        campaign = FakeCampaign()
        state = replace(
            make_state(),
            current_fleet_roster_sprites=("beta", "support"),
        )

        with self.assertRaisesRegex(SemanticGateClosed, "roster identity"):
            synchronize_alas_campaign_map(campaign, state)

        self.assertEqual(campaign.map_data_init_calls, 0)

    def test_rejects_static_map_mismatch_before_mutating_campaign(self):
        campaign = FakeCampaign()
        original_map = campaign.map

        with self.assertRaisesRegex(SemanticGateClosed, "pickup violates"):
            synchronize_alas_campaign_map(campaign, make_state(pickup_node="C2"))

        self.assertIs(campaign.map, original_map)
        self.assertEqual(campaign.map_data_init_calls, 0)
        self.assertFalse(hasattr(campaign, "semantic_map_projection"))

    def test_rejects_normal_enemy_on_boss_only_static_node(self):
        campaign = FakeCampaign()
        campaign.MAP[(0, 0)].may_enemy = False
        campaign.MAP[(0, 0)].may_boss = True

        with self.assertRaisesRegex(SemanticGateClosed, "enemy violates"):
            synchronize_alas_campaign_map(campaign, make_state())

        self.assertEqual(campaign.map_data_init_calls, 0)
        self.assertFalse(hasattr(campaign, "semantic_map_projection"))

    def test_rolls_back_campaign_if_alas_initializer_fails(self):
        campaign = FakeCampaign()
        original_map = campaign.map

        def fail_after_mutation(map_):
            campaign.map = copy.deepcopy(map_)
            campaign.config.POOR_MAP_DATA = False
            raise RuntimeError("initializer failed")

        campaign.map_data_init = fail_after_mutation
        with self.assertRaisesRegex(RuntimeError, "initializer failed"):
            synchronize_alas_campaign_map(campaign, make_state())

        self.assertIs(campaign.map, original_map)
        self.assertTrue(campaign.config.POOR_MAP_DATA)
        self.assertFalse(hasattr(campaign, "semantic_map_projection"))


class AlasCampaignDecisionPreviewTests(unittest.TestCase):
    def test_runs_original_branch_and_captures_first_goto_without_input(self):
        campaign = FakeCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())
        source_map_dict = campaign.MAP.__dict__
        source_grid_dicts = {
            location: grid.__dict__
            for location, grid in campaign.MAP.grids.items()
        }
        original_config = copy.deepcopy(campaign.config.__dict__)

        decision = preview_alas_campaign_decision(campaign, projection)

        self.assertEqual(decision.branch_name, "battle_function")
        self.assertEqual(decision.fleet_index, 1)
        self.assertEqual(decision.fleet_marker, "alpha")
        self.assertEqual(decision.origin_node, "A2")
        self.assertEqual(decision.target_node, "A1")
        self.assertEqual(decision.target_kind, "enemy")
        self.assertEqual(decision.expected, "combat")
        self.assertEqual(decision.route_nodes, ("A2", "A1"))
        self.assertEqual(decision.goto_nodes, ("A2", "A1"))
        self.assertFalse(decision.step_optimize)
        self.assertFalse(decision.turning_optimize)
        self.assertIs(campaign.MAP.__dict__, source_map_dict)
        for location, grid_dict in source_grid_dicts.items():
            self.assertIs(campaign.MAP[location].__dict__, grid_dict)
        self.assertTrue(all(grid.cost == 9999 for grid in campaign.map))
        self.assertEqual(campaign.config.__dict__, original_config)

    def test_rejects_forbidden_boundary_before_goto(self):
        class SwitchingCampaign(FakeCampaign):
            def battle_function(self):
                self.fleet_set(index=2)

        campaign = SwitchingCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())

        with self.assertRaisesRegex(SemanticGateClosed, "fleet_set"):
            preview_alas_campaign_decision(campaign, projection)

    def test_rejects_branch_that_returns_without_goto(self):
        class NoDecisionCampaign(FakeCampaign):
            def battle_function(self):
                return False

        campaign = NoDecisionCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())

        with self.assertRaisesRegex(SemanticGateClosed, "returned without goto"):
            preview_alas_campaign_decision(campaign, projection)

    def test_rejects_target_outside_semantic_dynamic_input(self):
        class SeaTargetCampaign(FakeCampaign):
            def battle_function(self):
                self.goto(self.map[(1, 1)])

        campaign = SeaTargetCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())

        with self.assertRaisesRegex(SemanticGateClosed, "outside semantic"):
            preview_alas_campaign_decision(campaign, projection)

    def test_rejects_device_access_before_goto(self):
        class DeviceCampaign(FakeCampaign):
            def battle_function(self):
                self.device.screenshot()

        campaign = DeviceCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())

        with self.assertRaisesRegex(SemanticGateClosed, "Device access"):
            preview_alas_campaign_decision(campaign, projection)

    def test_accepts_canonical_string_target_from_original_branch(self):
        class StringTargetCampaign(FakeCampaign):
            def battle_function(self):
                self.goto("A1", expected="combat")

        campaign = StringTargetCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())

        decision = preview_alas_campaign_decision(campaign, projection)

        self.assertEqual(decision.target_node, "A1")
        self.assertEqual(decision.route_nodes, ("A2", "A1"))

    def test_rejects_timed_emotion_path_before_goto(self):
        class EmotionCampaign(FakeCampaign):
            def battle_function(self):
                if self.emotion.is_calculate:
                    self.emotion.wait(fleet_index=self.fleet_current_index)
                self.goto(self.map[(0, 0)], expected="combat")

        campaign = EmotionCampaign()
        campaign.config.Emotion_Mode = "calculate"
        projection = synchronize_alas_campaign_map(campaign, make_state())

        with self.assertRaisesRegex(SemanticGateClosed, "emotion wait"):
            preview_alas_campaign_decision(campaign, projection)

    def test_rejects_stale_projection_object(self):
        campaign = FakeCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())
        campaign.semantic_map_projection = replace(projection, generation=21)

        with self.assertRaisesRegex(SemanticGateClosed, "not current"):
            preview_alas_campaign_decision(campaign, projection)

    def test_rejects_route_that_disagrees_with_projection(self):
        campaign = FakeCampaign()
        projection = synchronize_alas_campaign_map(campaign, make_state())
        first_fleet = projection.fleets[0]
        wrong_route = replace(
            first_fleet.enemy_routes[0],
            nodes=("A2", "B2", "A1"),
        )
        bad_projection = replace(
            projection,
            fleets=(
                replace(first_fleet, enemy_routes=(wrong_route,)),
                projection.fleets[1],
            ),
        )
        campaign.semantic_map_projection = bad_projection

        with self.assertRaisesRegex(SemanticGateClosed, "route disagrees"):
            preview_alas_campaign_decision(campaign, bad_projection)


class AlasCampaignGotoInputPreviewTests(unittest.TestCase):
    @staticmethod
    def prepare(campaign=None):
        campaign = campaign or FakeGotoCampaign()
        state = make_zero_distance_state()
        projection = synchronize_alas_campaign_map(campaign, state)
        decision = preview_alas_campaign_decision(campaign, projection)
        admission = prepare_alas_campaign_combat_admission(
            decision, state, input_generation=state.generation
        )
        return campaign, state, projection, decision, admission

    def test_runs_original_goto_prefix_and_captures_exact_click_without_input(self):
        campaign, state, projection, decision, admission = self.prepare()
        source_map_dict = campaign.MAP.__dict__
        source_grid_dicts = {
            location: grid.__dict__
            for location, grid in campaign.MAP.grids.items()
        }
        campaign_snapshot = campaign.__dict__.copy()
        config_snapshot = campaign.config.__dict__.copy()

        preview = preview_alas_campaign_goto_input(
            campaign, projection, decision, admission, state
        )

        self.assertEqual(preview.target_node, "A1")
        self.assertEqual(preview.expected, "combat")
        self.assertEqual(preview.fleet_index, 1)
        self.assertEqual(preview.fleet_marker, "alpha")
        self.assertFalse(preview.retreat_triggered)
        self.assertEqual(preview.sight, (-3, 0, 3, 2))
        self.assertEqual(preview.camera_node, "A1")
        self.assertEqual(preview.local_location, (3, 2))
        self.assertEqual(preview.cell_path, admission.cell_path)
        self.assertEqual(preview.point, admission.point)
        self.assertEqual(preview.bounds, admission.bounds)
        self.assertEqual(
            preview.call_order,
            (
                "hp_retreat_triggered",
                "fleet_set",
                "in_sight",
                "focus_to_grid_center",
                "convert_global_to_local",
                "ambush_color_initial",
                "enemy_searching_color_initial",
                "device.click",
            ),
        )
        self.assertEqual(campaign.__dict__, campaign_snapshot)
        self.assertEqual(campaign.config.__dict__, config_snapshot)
        self.assertIs(campaign.MAP.__dict__, source_map_dict)
        for location, grid_dict in source_grid_dicts.items():
            self.assertIs(campaign.MAP[location].__dict__, grid_dict)

    def test_rejects_stale_map_state_before_goto(self):
        campaign, state, projection, decision, admission = self.prepare()
        stale = replace(state, generation=state.generation + 1)

        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            preview_alas_campaign_goto_input(
                campaign, projection, decision, admission, stale
            )

    def test_rejects_changed_decision_before_goto(self):
        campaign, state, projection, decision, admission = self.prepare()
        changed = replace(decision, expected="combat_boss")

        with self.assertRaisesRegex(SemanticGateClosed, "decision changed"):
            preview_alas_campaign_goto_input(
                campaign, projection, changed, admission, state
            )

    def test_rejects_fleet_index_drift_before_goto(self):
        campaign, state, projection, decision, admission = self.prepare()
        campaign.fleet_show_index = 2

        with self.assertRaisesRegex(SemanticGateClosed, "fleet indexes changed"):
            preview_alas_campaign_goto_input(
                campaign, projection, decision, admission, state
            )

    def test_rejects_low_hp_retreat_path_before_device_input(self):
        campaign = FakeGotoCampaign()
        campaign.config.HpControl_UseLowHpRetreat = True
        campaign.hp = (0.1,)
        campaign, state, projection, decision, admission = self.prepare(campaign)

        with self.assertRaisesRegex(SemanticGateClosed, "withdraw"):
            preview_alas_campaign_goto_input(
                campaign, projection, decision, admission, state
            )

    def test_rejects_device_access_before_captured_click(self):
        class ScreenshotCampaign(FakeGotoCampaign):
            def before_grid_click(self):
                self.device.screenshot()

        campaign, state, projection, decision, admission = self.prepare(
            ScreenshotCampaign()
        )

        with self.assertRaisesRegex(SemanticGateClosed, "Device access"):
            preview_alas_campaign_goto_input(
                campaign, projection, decision, admission, state
            )

    def test_rejects_changed_global_grid_annotation(self):
        class WrongAnnotationCampaign(FakeGotoCampaign):
            def grid_annotation(self, location):
                del location
                return 1, 1

        campaign, state, projection, decision, admission = self.prepare(
            WrongAnnotationCampaign()
        )

        with self.assertRaisesRegex(SemanticGateClosed, "annotation changed"):
            preview_alas_campaign_goto_input(
                campaign, projection, decision, admission, state
            )

    def test_rejects_native_target_state_drift(self):
        campaign, state, projection, decision, admission = self.prepare()
        campaign.map[(0, 0)].is_current_fleet = False

        with self.assertRaisesRegex(SemanticGateClosed, "native target state"):
            preview_alas_campaign_goto_input(
                campaign, projection, decision, admission, state
            )

if __name__ == "__main__":
    unittest.main()
