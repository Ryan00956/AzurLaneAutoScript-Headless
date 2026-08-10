"""Read-only projection of semantic map state into ALAS-native map objects."""

import copy
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from .semantic_oracle import CampaignMapState, SemanticGateClosed


@dataclass(frozen=True)
class AlasCampaignRoutePlan:
    target_node: str
    target_kind: str
    cost: int
    weight: float
    nodes: Tuple[str, ...]


@dataclass(frozen=True)
class AlasCampaignFleetPlan:
    fleet_index: int
    is_current: bool
    marker: str
    origin_node: str
    ammo: int
    ammo_capacity: int
    enemy_routes: Tuple[AlasCampaignRoutePlan, ...]
    pickup_routes: Tuple[AlasCampaignRoutePlan, ...]
    recommended_enemy_node: Optional[str]
    recommended_pickup_node: Optional[str]


@dataclass(frozen=True)
class AlasCampaignMapProjection:
    generation: int
    stage_code: str
    rows: int
    columns: int
    land_nodes: Tuple[str, ...]
    enemy_nodes: Tuple[str, ...]
    pickup_nodes: Tuple[str, ...]
    displayed_fleet_index: int
    current_fleet_index: int
    current_fleet_marker: str
    fleets: Tuple[AlasCampaignFleetPlan, ...]

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.stage_code,
            self.rows,
            self.columns,
            self.land_nodes,
            self.enemy_nodes,
            self.pickup_nodes,
            self.displayed_fleet_index,
            self.current_fleet_index,
            self.current_fleet_marker,
            tuple(
                (
                    fleet.fleet_index,
                    fleet.is_current,
                    fleet.marker,
                    fleet.origin_node,
                    fleet.ammo,
                    fleet.ammo_capacity,
                    fleet.recommended_enemy_node,
                    fleet.recommended_pickup_node,
                    tuple(
                        (
                            route.target_kind,
                            route.target_node,
                            route.cost,
                            route.weight,
                            route.nodes,
                        )
                        for route in fleet.enemy_routes
                    ),
                    tuple(
                        (
                            route.target_kind,
                            route.target_node,
                            route.cost,
                            route.weight,
                            route.nodes,
                        )
                        for route in fleet.pickup_routes
                    ),
                )
                for fleet in self.fleets
            ),
        )


_NODE_PATTERN = re.compile(r"([A-Z])([1-9][0-9]*)")
_CAMPAIGN_STATE_FIELDS = (
    "map",
    "fleet_1_location",
    "fleet_2_location",
    "fleet_submarine_location",
    "fleet_show_index",
    "fleet_current_index",
    "battle_count",
    "mystery_count",
    "carrier_count",
    "siren_count",
    "ammo_count",
    "semantic_fleet_locations",
    "semantic_map_projection",
)
_CONFIG_STATE_FIELDS = ("POOR_MAP_DATA",)


def _node_to_location(node: str, *, columns: int, rows: int) -> Tuple[int, int]:
    if not isinstance(node, str):
        raise SemanticGateClosed("ALAS map projection node is not text")
    match = _NODE_PATTERN.fullmatch(node)
    if match is None:
        raise SemanticGateClosed("ALAS map projection node is not canonical")
    column = ord(match.group(1)) - ord("A")
    row = int(match.group(2)) - 1
    if not (0 <= column < columns and 0 <= row < rows):
        raise SemanticGateClosed("ALAS map projection node is outside its shape")
    return column, row


def _location_to_node(location: Iterable[int]) -> str:
    column, row = tuple(location)
    return chr(ord("A") + int(column)) + str(int(row) + 1)


def _require_unique_nodes(items: Iterable[Any], label: str) -> Tuple[str, ...]:
    nodes = tuple(item.node for item in items)
    if len(set(nodes)) != len(nodes):
        raise SemanticGateClosed("ALAS map projection has duplicate " + label)
    return nodes


def _snapshot_campaign(campaign: Any) -> Dict[str, Tuple[bool, Any]]:
    return {
        name: (hasattr(campaign, name), getattr(campaign, name, None))
        for name in _CAMPAIGN_STATE_FIELDS
    }


def _snapshot_config(config: Any) -> Dict[str, Tuple[bool, Any]]:
    return {
        name: (hasattr(config, name), getattr(config, name, None))
        for name in _CONFIG_STATE_FIELDS
    }


def _restore_campaign(
    campaign: Any, snapshot: Dict[str, Tuple[bool, Any]]
) -> None:
    for name, (present, value) in snapshot.items():
        if present:
            setattr(campaign, name, value)
        elif hasattr(campaign, name):
            delattr(campaign, name)


def _restore_config(
    config: Any, snapshot: Dict[str, Tuple[bool, Any]]
) -> None:
    for name, (present, value) in snapshot.items():
        if present:
            setattr(config, name, value)
        elif hasattr(config, name):
            delattr(config, name)


def _route_plan(
    campaign_map: Any,
    target_node: str,
    target_kind: str,
    *,
    columns: int,
    rows: int,
) -> Optional[AlasCampaignRoutePlan]:
    target_location = _node_to_location(
        target_node, columns=columns, rows=rows
    )
    route = campaign_map._find_path(target_location)
    if route is None:
        return None
    target = campaign_map[target_location]
    cost = target.cost
    weight = target.weight
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost >= 9999:
        return None
    if not isinstance(weight, (int, float)) or isinstance(weight, bool):
        raise SemanticGateClosed("ALAS map projection grid weight is invalid")
    return AlasCampaignRoutePlan(
        target_node=target_node,
        target_kind=target_kind,
        cost=int(cost),
        weight=float(weight),
        nodes=tuple(_location_to_node(location) for location in route),
    )


def _recommended(routes: Tuple[AlasCampaignRoutePlan, ...]) -> Optional[str]:
    if not routes:
        return None
    return min(
        routes,
        key=lambda route: (route.weight, route.cost, route.target_node),
    ).target_node


def synchronize_alas_campaign_map(
    campaign: Any,
    state: CampaignMapState,
) -> AlasCampaignMapProjection:
    """Populate a shadow ALAS ``CampaignMap`` and compute paths without input.

    The function delegates static initialization and path finding to ALAS's
    existing ``map_data_init()``, ``find_path_initial()``, and ``_find_path()``
    methods. It assigns fleet indexes only from the stable typed current-roster
    identity, and deliberately does not call ``map_control_init()`` or invoke
    any movement/battle method.
    """

    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed("ALAS map projection requires typed map state")
    if (
        not hasattr(campaign, "MAP")
        or not callable(getattr(campaign, "map_data_init", None))
        or not hasattr(campaign, "config")
    ):
        raise SemanticGateClosed("ALAS campaign map interface is incomplete")
    source_map = campaign.MAP
    if getattr(source_map, "name", None) != state.stage_code:
        raise SemanticGateClosed("ALAS map projection stage disagrees with ALAS")
    if getattr(source_map, "shape", None) != (state.columns - 1, state.rows - 1):
        raise SemanticGateClosed("ALAS map projection shape disagrees with ALAS")

    static_land = tuple(
        sorted(_location_to_node(grid.location) for grid in source_map if grid.is_land)
    )
    if tuple(sorted(state.land_nodes)) != static_land:
        raise SemanticGateClosed("ALAS map projection land topology disagrees")
    expected_cells = tuple(
        sorted(
            _location_to_node(grid.location)
            for grid in source_map
            if not grid.is_land
        )
    )
    if tuple(sorted(cell.node for cell in state.cells)) != expected_cells:
        raise SemanticGateClosed("ALAS map projection cell topology disagrees")
    for cell in state.cells:
        location = _node_to_location(
            cell.node, columns=state.columns, rows=state.rows
        )
        if location != (cell.column - 1, cell.row - 1):
            raise SemanticGateClosed(
                "ALAS map projection cell coordinates disagree"
            )

    fleet_nodes = _require_unique_nodes(state.fleets, "fleet nodes")
    enemy_nodes = _require_unique_nodes(state.enemies, "enemy nodes")
    pickup_nodes = _require_unique_nodes(state.pickups, "pickup nodes")
    if len(set(fleet.marker for fleet in state.fleets)) != len(state.fleets):
        raise SemanticGateClosed("ALAS map projection has duplicate fleet markers")
    if (
        isinstance(state.displayed_fleet_index, bool)
        or state.displayed_fleet_index not in (1, 2)
        or state.current_fleet_marker
        not in {fleet.marker for fleet in state.fleets}
    ):
        raise SemanticGateClosed("ALAS map projection fleet identity is invalid")
    roster_matches = []
    for fleet in state.fleets:
        marker_prefix = "cell_fleet_"
        marker_sprite = (
            fleet.marker[len(marker_prefix) :]
            if fleet.marker.startswith(marker_prefix)
            else fleet.marker
        )
        matches = sum(
            sprite == marker_sprite
            for sprite in state.current_fleet_roster_sprites
        )
        if matches > 1:
            raise SemanticGateClosed(
                "ALAS map projection fleet roster identity is ambiguous"
            )
        if matches == 1:
            roster_matches.append(fleet.marker)
    if roster_matches != [state.current_fleet_marker]:
        raise SemanticGateClosed(
            "ALAS map projection fleet roster identity disagrees"
        )
    if set(pickup_nodes).intersection(set(fleet_nodes) | set(enemy_nodes)):
        raise SemanticGateClosed(
            "ALAS map projection pickup overlaps a fleet or enemy"
        )

    for node in fleet_nodes:
        location = _node_to_location(node, columns=state.columns, rows=state.rows)
        if source_map[location].is_land:
            raise SemanticGateClosed("ALAS map projection places a fleet on land")
    for enemy in state.enemies:
        location = _node_to_location(
            enemy.node, columns=state.columns, rows=state.rows
        )
        if location != (enemy.column - 1, enemy.row - 1):
            raise SemanticGateClosed(
                "ALAS map projection enemy coordinates disagree"
            )
        grid = source_map[location]
        if grid.is_land or not grid.may_enemy:
            raise SemanticGateClosed("ALAS map projection enemy violates static map")
    for pickup in state.pickups:
        location = _node_to_location(
            pickup.node, columns=state.columns, rows=state.rows
        )
        if location != (pickup.column - 1, pickup.row - 1):
            raise SemanticGateClosed(
                "ALAS map projection pickup coordinates disagree"
            )
        if pickup.kind != "ammo" or not source_map[location].may_ammo:
            raise SemanticGateClosed("ALAS map projection pickup violates static map")

    current_fleet = next(
        fleet for fleet in state.fleets
        if fleet.marker == state.current_fleet_marker
    )
    fighting_nodes = tuple(
        enemy.node for enemy in state.enemies if enemy.fighting
    )
    if fighting_nodes and fighting_nodes != (current_fleet.node,):
        raise SemanticGateClosed(
            "ALAS map projection fighting enemy disagrees with current fleet"
        )

    fleets_reversed = bool(getattr(campaign, "fleets_reversed", False))
    current_fleet_index = (
        3 - state.displayed_fleet_index
        if fleets_reversed
        else state.displayed_fleet_index
    )
    if len(state.fleets) == 1:
        if current_fleet_index != 1:
            raise SemanticGateClosed(
                "ALAS map projection single fleet index is unsupported"
            )
        index_by_marker = {state.current_fleet_marker: 1}
    elif len(state.fleets) == 2:
        other_marker = next(
            fleet.marker for fleet in state.fleets
            if fleet.marker != state.current_fleet_marker
        )
        index_by_marker = {
            state.current_fleet_marker: current_fleet_index,
            other_marker: 3 - current_fleet_index,
        }
    else:
        raise SemanticGateClosed("ALAS map projection fleet count is unsupported")

    previous = _snapshot_campaign(campaign)
    previous_config = _snapshot_config(campaign.config)
    try:
        projected_map = copy.deepcopy(source_map)
        campaign.map_data_init(projected_map)

        marker_locations = {}
        for fleet in state.fleets:
            location = _node_to_location(
                fleet.node, columns=state.columns, rows=state.rows
            )
            campaign.map[location].is_fleet = True
            marker_locations[fleet.marker] = location
        current_location = marker_locations[state.current_fleet_marker]
        campaign.map[current_location].is_current_fleet = True
        campaign.fleet_show_index = state.displayed_fleet_index
        campaign.fleet_current_index = current_fleet_index
        campaign.fleet_1_location = next(
            marker_locations[marker]
            for marker, index in index_by_marker.items()
            if index == 1
        )
        campaign.fleet_2_location = next(
            (
                marker_locations[marker]
                for marker, index in index_by_marker.items()
                if index == 2
            ),
            (),
        )
        for enemy in state.enemies:
            location = _node_to_location(
                enemy.node, columns=state.columns, rows=state.rows
            )
            grid = campaign.map[location]
            grid.is_enemy = True
            grid.enemy_scale = enemy.scale
            grid.enemy_genre = enemy.genre
        for pickup in state.pickups:
            location = _node_to_location(
                pickup.node, columns=state.columns, rows=state.rows
            )
            campaign.map[location].is_ammo = True

        fleet_plans = []
        has_ambush = bool(getattr(campaign.config, "MAP_HAS_AMBUSH", False))
        for fleet in sorted(
            state.fleets, key=lambda item: index_by_marker[item.marker]
        ):
            origin = marker_locations[fleet.marker]
            campaign.map.find_path_initial(origin, has_ambush=has_ambush)
            enemy_routes = tuple(
                route
                for route in (
                    _route_plan(
                        campaign.map,
                        enemy.node,
                        "enemy",
                        columns=state.columns,
                        rows=state.rows,
                    )
                    for enemy in state.enemies
                )
                if route is not None
            )
            pickup_routes = tuple(
                route
                for route in (
                    _route_plan(
                        campaign.map,
                        pickup.node,
                        pickup.kind,
                        columns=state.columns,
                        rows=state.rows,
                    )
                    for pickup in state.pickups
                )
                if route is not None
            )
            fleet_plans.append(
                AlasCampaignFleetPlan(
                    fleet_index=index_by_marker[fleet.marker],
                    is_current=fleet.marker == state.current_fleet_marker,
                    marker=fleet.marker,
                    origin_node=fleet.node,
                    ammo=fleet.ammo,
                    ammo_capacity=fleet.ammo_capacity,
                    enemy_routes=tuple(
                        sorted(
                            enemy_routes,
                            key=lambda route: (
                                route.weight,
                                route.cost,
                                route.target_node,
                            ),
                        )
                    ),
                    pickup_routes=tuple(
                        sorted(
                            pickup_routes,
                            key=lambda route: (
                                route.weight,
                                route.cost,
                                route.target_node,
                            ),
                        )
                    ),
                    recommended_enemy_node=_recommended(enemy_routes),
                    recommended_pickup_node=_recommended(pickup_routes),
                )
            )

        for grid in campaign.map:
            grid.cost = 9999
            grid.cost_1 = 9999
            grid.cost_2 = 9999
            grid.connection = None

        projection = AlasCampaignMapProjection(
            generation=state.generation,
            stage_code=state.stage_code,
            rows=state.rows,
            columns=state.columns,
            land_nodes=tuple(sorted(state.land_nodes)),
            enemy_nodes=tuple(sorted(enemy_nodes)),
            pickup_nodes=tuple(sorted(pickup_nodes)),
            displayed_fleet_index=state.displayed_fleet_index,
            current_fleet_index=current_fleet_index,
            current_fleet_marker=state.current_fleet_marker,
            fleets=tuple(fleet_plans),
        )
        campaign.semantic_fleet_locations = dict(marker_locations)
        campaign.semantic_map_projection = projection
        return projection
    except Exception:
        _restore_campaign(campaign, previous)
        raise
    finally:
        _restore_config(campaign.config, previous_config)
