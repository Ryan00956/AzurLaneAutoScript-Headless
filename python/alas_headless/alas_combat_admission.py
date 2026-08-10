"""Decision-bound admission data for one ALAS-owned campaign combat.

This module does not execute movement or combat.  It validates that the first
state-changing grid input selected by ALAS still names either the exact
fighting enemy under the current fleet or one ordinary enemy reached through
at most three empty orthogonal cells.  The adapter owns the separate input
budget and the native ALAS state machine remains the only execution owner.
"""

import re
from dataclasses import dataclass
from typing import Any, Tuple

from .alas_decision_preview import AlasCampaignDecisionPreview
from .semantic_oracle import (
    Bounds,
    CampaignMapState,
    Point,
    SemanticGateClosed,
)


@dataclass(frozen=True)
class AlasCampaignCombatAdmission:
    generation: int
    input_generation: int
    stage_code: str
    battle_count: int
    branch_name: str
    fleet_index: int
    fleet_marker: str
    origin_node: str
    target_node: str
    route_nodes: Tuple[str, ...]
    enemy_object_id: int
    enemy_sprite: str
    enemy_level: int
    ammo_before: int
    cell_path: str
    point: Point
    bounds: Bounds
    decision_signature: Tuple[Any, ...]
    map_signature: Tuple[Any, ...]

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.generation,
            self.input_generation,
            self.stage_code,
            self.battle_count,
            self.branch_name,
            self.fleet_index,
            self.fleet_marker,
            self.origin_node,
            self.target_node,
            self.route_nodes,
            self.enemy_object_id,
            self.enemy_sprite,
            self.enemy_level,
            self.ammo_before,
            self.cell_path,
            self.point,
            self.bounds,
            self.decision_signature,
            self.map_signature,
        )


@dataclass(frozen=True)
class AlasCampaignCombatProof:
    stage_code: str
    battle_count_before: int
    battle_count_after: int
    fleet_index: int
    fleet_marker: str
    target_node: str
    enemy_object_id: int
    ammo_before: int
    ammo_after: int
    input_generation: int
    map_generation: int
    input_path: str


def prepare_alas_campaign_combat_admission(
    decision: AlasCampaignDecisionPreview,
    state: CampaignMapState,
    *,
    input_generation: int,
) -> AlasCampaignCombatAdmission:
    """Bind one same-cell or bounded-route decision to its exact map cell.

    G23 admits at most three orthogonal steps when every intermediate node is
    a typed passable cell with no enemy, fleet, or pickup.  Fleet switching,
    ammunition pickups, bosses, portals, diagonal routes, and longer movement
    remain outside this contract.
    """

    if not isinstance(decision, AlasCampaignDecisionPreview):
        raise SemanticGateClosed("campaign combat requires an ALAS decision")
    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed("campaign combat requires a typed map state")
    if (
        isinstance(input_generation, bool)
        or not isinstance(input_generation, int)
        or input_generation < state.generation
    ):
        raise SemanticGateClosed("campaign combat input generation is stale")
    if decision.generation != state.generation:
        raise SemanticGateClosed("campaign combat decision generation changed")
    if decision.stage_code != state.stage_code:
        raise SemanticGateClosed("campaign combat stage identity changed")
    if decision.target_kind != "enemy" or decision.expected != "combat":
        raise SemanticGateClosed("campaign combat target is not a normal enemy")
    if (
        isinstance(decision.cost, bool)
        or not isinstance(decision.cost, int)
        or not isinstance(decision.origin_node, str)
        or not isinstance(decision.target_node, str)
        or not isinstance(decision.route_nodes, tuple)
        or not decision.route_nodes
        or any(not isinstance(node, str) for node in decision.route_nodes)
    ):
        raise SemanticGateClosed("campaign combat route fields are malformed")
    node_pattern = re.compile(r"([A-Z])([1-9][0-9]*)")
    route_matches = tuple(node_pattern.fullmatch(node) for node in decision.route_nodes)
    same_cell = (
        decision.cost == 0
        and decision.origin_node == decision.target_node
        and decision.route_nodes == (decision.target_node,)
        and all(match is not None for match in route_matches)
    )
    bounded_route = (
        2 <= len(decision.route_nodes) <= 4
        and decision.cost > 0
        and decision.origin_node != decision.target_node
        and decision.route_nodes[0] == decision.origin_node
        and decision.route_nodes[-1] == decision.target_node
        and len(set(decision.route_nodes)) == len(decision.route_nodes)
        and all(match is not None for match in route_matches)
    )
    if bounded_route:
        coordinates = tuple(
            (ord(match.group(1)) - ord("A"), int(match.group(2)))
            for match in route_matches
            if match is not None
        )
        bounded_route = all(
            abs(left[0] - right[0]) + abs(left[1] - right[1]) == 1
            for left, right in zip(coordinates, coordinates[1:])
        )
    if not (same_cell or bounded_route) or decision.goto_nodes != (decision.target_node,):
        raise SemanticGateClosed(
            "campaign combat admission is limited to a same-cell or three-step route"
        )
    if decision.step_optimize:
        raise SemanticGateClosed("campaign combat fleet-step movement is not admitted")

    cells = tuple(cell for cell in state.cells if cell.node == decision.target_node)
    enemies = tuple(
        enemy for enemy in state.enemies if enemy.node == decision.target_node
    )
    fleets = tuple(
        fleet
        for fleet in state.fleets
        if fleet.marker == decision.fleet_marker
        and fleet.node == decision.origin_node
    )
    if len(cells) != 1:
        raise SemanticGateClosed("campaign combat target cell is absent or ambiguous")
    if len(enemies) != 1 or enemies[0].fighting != same_cell:
        raise SemanticGateClosed(
            "campaign combat target fighting state disagrees with the route"
        )
    if len(fleets) != 1 or state.current_fleet_marker != decision.fleet_marker:
        raise SemanticGateClosed("campaign combat current fleet identity changed")
    if fleets[0].ammo <= 0:
        raise SemanticGateClosed("campaign combat requires positive fleet ammunition")
    route_cells = tuple(
        cell for cell in state.cells if cell.node in decision.route_nodes
    )
    if len(route_cells) != len(decision.route_nodes):
        raise SemanticGateClosed("campaign combat route contains a non-passable cell")
    intermediate_nodes = frozenset(decision.route_nodes[1:-1])
    if any(
        item.node in intermediate_nodes
        for item in (*state.enemies, *state.fleets, *state.pickups)
    ):
        raise SemanticGateClosed("campaign combat route intermediate is occupied")
    if not same_cell and any(
        item.node == decision.target_node
        for item in (*state.fleets, *state.pickups)
    ):
        raise SemanticGateClosed("campaign combat target has a conflicting occupant")

    cell = cells[0]
    enemy = enemies[0]
    return AlasCampaignCombatAdmission(
        generation=state.generation,
        input_generation=input_generation,
        stage_code=state.stage_code,
        battle_count=decision.battle_count,
        branch_name=decision.branch_name,
        fleet_index=decision.fleet_index,
        fleet_marker=decision.fleet_marker,
        origin_node=decision.origin_node,
        target_node=decision.target_node,
        route_nodes=decision.route_nodes,
        enemy_object_id=enemy.object_id,
        enemy_sprite=enemy.sprite,
        enemy_level=enemy.level,
        ammo_before=fleets[0].ammo,
        cell_path=cell.button_path,
        point=cell.point,
        bounds=cell.bounds,
        decision_signature=decision.signature,
        map_signature=state.signature,
    )


def prove_alas_campaign_combat_transition(
    admission: AlasCampaignCombatAdmission,
    state: CampaignMapState,
    *,
    battle_count_after: int,
    input_path: str,
) -> AlasCampaignCombatProof:
    """Prove the independently observed post-battle map mutation."""

    if not isinstance(admission, AlasCampaignCombatAdmission):
        raise SemanticGateClosed("campaign combat admission is absent")
    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed("campaign combat post-state is absent")
    if (
        isinstance(battle_count_after, bool)
        or not isinstance(battle_count_after, int)
        or battle_count_after != admission.battle_count + 1
    ):
        raise SemanticGateClosed("ALAS battle count did not advance exactly once")
    if state.stage_code != admission.stage_code:
        raise SemanticGateClosed("campaign combat post-state stage changed")
    if state.generation <= admission.input_generation:
        raise SemanticGateClosed("campaign combat post-state predates input")
    if tuple((cell.node, cell.button_path) for cell in state.cells) != tuple(
        admission.map_signature[3]
    ):
        raise SemanticGateClosed("campaign combat map topology changed")
    if any(enemy.node == admission.target_node for enemy in state.enemies):
        raise SemanticGateClosed("campaign combat target enemy still exists")

    fleets = tuple(
        fleet
        for fleet in state.fleets
        if fleet.marker == admission.fleet_marker
        and fleet.node == admission.target_node
    )
    if len(fleets) != 1 or state.current_fleet_marker != admission.fleet_marker:
        raise SemanticGateClosed("campaign combat fleet did not remain on target")
    ammo_after = fleets[0].ammo
    if ammo_after != admission.ammo_before - 1:
        raise SemanticGateClosed("campaign combat ammunition did not decrease once")
    if input_path != admission.cell_path:
        raise SemanticGateClosed("campaign combat input path changed")

    return AlasCampaignCombatProof(
        stage_code=admission.stage_code,
        battle_count_before=admission.battle_count,
        battle_count_after=battle_count_after,
        fleet_index=admission.fleet_index,
        fleet_marker=admission.fleet_marker,
        target_node=admission.target_node,
        enemy_object_id=admission.enemy_object_id,
        ammo_before=admission.ammo_before,
        ammo_after=ammo_after,
        input_generation=admission.input_generation,
        map_generation=state.generation,
        input_path=input_path,
    )
