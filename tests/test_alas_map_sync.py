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
    preview_alas_campaign_decision,
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

if __name__ == "__main__":
    unittest.main()
