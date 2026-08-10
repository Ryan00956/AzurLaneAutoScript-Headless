"""Evidence contract for one qualification-only original-ALAS live battle.

This module does not drive the game.  It binds the already separate grid and
resource-action receipts to one read-only multiplex trace, re-proves the
checked S-grade controls, and verifies the semantic map transition afterwards.
ALAS owns branch selection and its original pre-click ``_goto()`` prefix; this
qualification harness still sequences post-click evidence actions explicitly,
so it must not be reported as live ownership by ALAS's full combat state machine.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence, Tuple

from .alas_combat_observer import (
    AlasCombatObserverManifest,
    audit_alas_combat_observer_manifest,
)
from .alas_combat_result_evidence import (
    analyze_alas_combat_result_control_evidence,
    verify_alas_combat_result_control_evidence,
)
from .alas_combat_state_replay import ALAS_COMBAT_RESOURCE_ACTION_TARGETS
from .alas_combat_surface_multiplex import (
    verify_alas_combat_surface_multiplex_evidence,
)
from .alas_combat_trace import AlasCombatObserverTrace
from .semantic_oracle import CampaignMapState, SemanticGateClosed


ALAS_COMBAT_MAP_CHECKPOINT_SCHEMA = (
    "alas-headless.g32-combat-map-checkpoint/v1"
)
ALAS_COMBAT_CONTROLLED_EPISODE_SCHEMA = (
    "alas-headless.g32-controlled-combat-episode/v1"
)
ALAS_COMBAT_CONTROLLED_EPISODE_VERIFICATION_SCHEMA = (
    "alas-headless.g32-controlled-combat-episode-verification/v1"
)
ALAS_COMBAT_ACQUISITION_SCHEMA = "alas-headless.g32-combat-acquisition/v2"
_ACTION_COMMIT_SCHEMA = "alas-headless.g27-combat-resource-action-commit/v3"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_NODE_PATTERN = re.compile(r"([A-Z])([1-9][0-9]*)")


def alas_campaign_combat_map_state_to_json(
    state: CampaignMapState,
) -> Mapping[str, Any]:
    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed("combat map checkpoint state is not typed")
    return {
        "generation": state.generation,
        "stage_code": state.stage_code,
        "rows": state.rows,
        "columns": state.columns,
        "land_nodes": list(state.land_nodes),
        "expected_fleet_count": len(state.fleets),
        "fleets": [
            {
                "marker": fleet.marker,
                "node": fleet.node,
                "ammo": fleet.ammo,
                "ammo_capacity": fleet.ammo_capacity,
            }
            for fleet in state.fleets
        ],
        "enemies": [
            {
                "node": enemy.node,
                "object_id": enemy.object_id,
                "fighting": enemy.fighting,
            }
            for enemy in state.enemies
        ],
        "displayed_fleet_index": state.displayed_fleet_index,
        "current_fleet_marker": state.current_fleet_marker,
    }


def build_alas_combat_map_checkpoint(
    manifest: AlasCombatObserverManifest,
    *,
    pid: int,
    state: CampaignMapState,
) -> Mapping[str, Any]:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise SemanticGateClosed("combat map checkpoint PID is malformed")
    return {
        "schema": ALAS_COMBAT_MAP_CHECKPOINT_SCHEMA,
        "package": manifest.package,
        "driver_revision": manifest.driver_revision,
        "game_fingerprint": manifest.game_fingerprint,
        "pid": pid,
        "input_injected": False,
        "map": alas_campaign_combat_map_state_to_json(state),
    }


def alas_campaign_land_nodes_to_cells(
    land_nodes: Sequence[str], *, columns: int, rows: int
) -> Tuple[Tuple[int, int], ...]:
    cells = []
    for node in land_nodes:
        match = _NODE_PATTERN.fullmatch(node) if isinstance(node, str) else None
        if match is None:
            raise SemanticGateClosed("combat map land node is not canonical")
        column = ord(match.group(1)) - ord("A")
        row = int(match.group(2)) - 1
        if not 0 <= column < columns or not 0 <= row < rows:
            raise SemanticGateClosed("combat map land node is outside its shape")
        cells.append((column, row))
    if len(cells) != len(set(cells)):
        raise SemanticGateClosed("combat map land nodes are duplicated")
    return tuple(cells)


def _map_value(value: Any, label: str) -> Mapping[str, Any]:
    required = {
        "generation",
        "stage_code",
        "rows",
        "columns",
        "land_nodes",
        "expected_fleet_count",
        "fleets",
        "enemies",
        "displayed_fleet_index",
        "current_fleet_marker",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise SemanticGateClosed(label + " map schema changed")
    if any(
        isinstance(value[name], bool) or not isinstance(value[name], int)
        for name in (
            "generation",
            "rows",
            "columns",
            "expected_fleet_count",
            "displayed_fleet_index",
        )
    ):
        raise SemanticGateClosed(label + " map integers are malformed")
    if (
        value["generation"] < 0
        or value["rows"] < 1
        or not 1 <= value["columns"] <= 26
        or value["expected_fleet_count"] not in (1, 2)
        or value["displayed_fleet_index"] not in (1, 2)
        or not isinstance(value["stage_code"], str)
        or not value["stage_code"]
        or not isinstance(value["current_fleet_marker"], str)
        or not value["current_fleet_marker"]
    ):
        raise SemanticGateClosed(label + " stage code is malformed")
    if not isinstance(value["land_nodes"], list):
        raise SemanticGateClosed(label + " land nodes are malformed")
    alas_campaign_land_nodes_to_cells(
        value["land_nodes"], columns=value["columns"], rows=value["rows"]
    )
    if (
        not isinstance(value["fleets"], list)
        or len(value["fleets"]) != value["expected_fleet_count"]
        or not isinstance(value["enemies"], list)
    ):
        raise SemanticGateClosed(label + " map actors are malformed")
    fleet_markers = []
    fleet_nodes = []
    for fleet in value["fleets"]:
        if not isinstance(fleet, dict) or set(fleet) != {
            "marker",
            "node",
            "ammo",
            "ammo_capacity",
        }:
            raise SemanticGateClosed(label + " fleet schema changed")
        if (
            not isinstance(fleet["marker"], str)
            or not fleet["marker"]
            or isinstance(fleet["ammo"], bool)
            or not isinstance(fleet["ammo"], int)
            or isinstance(fleet["ammo_capacity"], bool)
            or not isinstance(fleet["ammo_capacity"], int)
            or not 0 <= fleet["ammo"] <= fleet["ammo_capacity"]
        ):
            raise SemanticGateClosed(label + " fleet values are malformed")
        alas_campaign_land_nodes_to_cells(
            (fleet["node"],), columns=value["columns"], rows=value["rows"]
        )
        fleet_markers.append(fleet["marker"])
        fleet_nodes.append(fleet["node"])
    if (
        len(fleet_markers) != len(set(fleet_markers))
        or len(fleet_nodes) != len(set(fleet_nodes))
        or value["current_fleet_marker"] not in fleet_markers
    ):
        raise SemanticGateClosed(label + " fleet identity is ambiguous")
    enemy_nodes = []
    enemy_ids = []
    for enemy in value["enemies"]:
        if not isinstance(enemy, dict) or set(enemy) != {
            "node",
            "object_id",
            "fighting",
        }:
            raise SemanticGateClosed(label + " enemy schema changed")
        if (
            isinstance(enemy["object_id"], bool)
            or not isinstance(enemy["object_id"], int)
            or enemy["object_id"] <= 0
            or not isinstance(enemy["fighting"], bool)
        ):
            raise SemanticGateClosed(label + " enemy values are malformed")
        alas_campaign_land_nodes_to_cells(
            (enemy["node"],), columns=value["columns"], rows=value["rows"]
        )
        enemy_nodes.append(enemy["node"])
        enemy_ids.append(enemy["object_id"])
    if (
        len(enemy_nodes) != len(set(enemy_nodes))
        or len(enemy_ids) != len(set(enemy_ids))
    ):
        raise SemanticGateClosed(label + " enemy identity is ambiguous")
    return value


def _combat_input_value(
    value: Any, before: Mapping[str, Any]
) -> Mapping[str, Any]:
    required = {
        "stage_code",
        "battle_count",
        "branch_name",
        "fleet_index",
        "fleet_marker",
        "enemy_object_id",
        "ammo_before",
        "origin_node",
        "target_node",
        "route_nodes",
        "expected",
        "cell_path",
        "point",
        "bounds",
        "admission_generation",
        "preflight_generation",
        "receipt_generation",
        "receipt_semantic_id",
        "call_order",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise SemanticGateClosed("controlled combat acquisition input schema changed")
    integer_names = (
        "battle_count",
        "fleet_index",
        "enemy_object_id",
        "ammo_before",
        "admission_generation",
        "preflight_generation",
        "receipt_generation",
    )
    if any(
        isinstance(value[name], bool) or not isinstance(value[name], int)
        for name in integer_names
    ):
        raise SemanticGateClosed("controlled combat acquisition integers changed")
    route = value["route_nodes"]
    if (
        value["stage_code"] != before["stage_code"]
        or value["expected"] != "combat"
        or not isinstance(value["branch_name"], str)
        or not value["branch_name"]
        or value["fleet_index"] not in (1, 2)
        or not isinstance(value["fleet_marker"], str)
        or not value["fleet_marker"]
        or not isinstance(value["cell_path"], str)
        or not value["cell_path"]
        or not isinstance(route, list)
        or not route
        or route[0] != value["origin_node"]
        or route[-1] != value["target_node"]
        or len(route) != len(set(route))
        or value["receipt_semantic_id"]
        != "campaign/map/grid/" + str(value["target_node"])
        or value["admission_generation"] != before["generation"]
        or not value["admission_generation"]
        <= value["preflight_generation"]
        <= value["receipt_generation"]
    ):
        raise SemanticGateClosed("controlled combat acquisition identity changed")
    for node in route:
        alas_campaign_land_nodes_to_cells(
            (node,), columns=before["columns"], rows=before["rows"]
        )
    point = value["point"]
    bounds = value["bounds"]
    if (
        not isinstance(point, dict)
        or set(point) != {"x", "y"}
        or not isinstance(bounds, dict)
        or set(bounds) != {"left", "top", "right", "bottom"}
    ):
        raise SemanticGateClosed("controlled combat acquisition geometry changed")
    numbers = (*point.values(), *bounds.values())
    if any(
        isinstance(number, bool) or not isinstance(number, (int, float))
        or not math.isfinite(float(number))
        for number in numbers
    ) or not (
        bounds["left"] <= point["x"] <= bounds["right"]
        and bounds["top"] <= point["y"] <= bounds["bottom"]
    ):
        raise SemanticGateClosed("controlled combat acquisition point is invalid")
    expected_order = [
        "hp_retreat_triggered",
        "fleet_set",
        "in_sight",
        "focus_to_grid_center",
        "convert_global_to_local",
        "ambush_color_initial",
        "enemy_searching_color_initial",
        "device.click",
    ]
    if value["call_order"] != expected_order:
        raise SemanticGateClosed("controlled combat ALAS goto prefix changed")
    return value


def _checkpoint_value(
    value: Any,
    manifest: AlasCombatObserverManifest,
    *,
    pid: int,
) -> Mapping[str, Any]:
    required = {
        "schema",
        "package",
        "driver_revision",
        "game_fingerprint",
        "pid",
        "input_injected",
        "map",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise SemanticGateClosed("combat map checkpoint schema changed")
    if value["schema"] != ALAS_COMBAT_MAP_CHECKPOINT_SCHEMA:
        raise SemanticGateClosed("combat map checkpoint version changed")
    if (
        value["package"] != manifest.package
        or value["driver_revision"] != manifest.driver_revision
        or value["game_fingerprint"] != manifest.game_fingerprint
        or value["pid"] != pid
        or value["input_injected"] is not False
    ):
        raise SemanticGateClosed("combat map checkpoint identity changed")
    return _map_value(value["map"], "post-combat")


def _action_sequences() -> Tuple[Tuple[str, ...], ...]:
    sequences = []
    for automation_confirm in (False, True):
        for automation_switch in (False, True):
            for get_items in (False, True):
                for get_mission in (False, True):
                    resources = []
                    if automation_confirm:
                        resources.append("AUTOMATION_CONFIRM")
                    if automation_switch:
                        resources.append("AUTOMATION_OFF")
                    resources.extend(("BATTLE_PREPARATION", "BATTLE_STATUS_S"))
                    if get_items:
                        resources.append("GET_ITEMS_1")
                    resources.append("EXP_INFO_S")
                    if get_mission:
                        resources.append("GET_MISSION")
                    sequences.append(tuple(resources))
    return tuple(sequences)


_ALLOWED_ACTION_SEQUENCES = _action_sequences()


def _validate_action_commits(
    manifest: AlasCombatObserverManifest,
    commits: Sequence[Any],
    *,
    pid: int,
    minimum_generation: int,
) -> Mapping[str, Any]:
    if not isinstance(commits, (tuple, list)) or not commits:
        raise SemanticGateClosed("controlled combat has no resource actions")
    resources = {item.resource_name: item for item in manifest.resources}
    actions = {item.action_name: item for item in manifest.actions}
    names = []
    generations = []
    previous = minimum_generation
    for raw in commits:
        if not isinstance(raw, dict) or raw.get("schema") != _ACTION_COMMIT_SCHEMA:
            raise SemanticGateClosed("controlled combat action receipt changed")
        resource_name = raw.get("resource_name")
        action_name = raw.get("action_name")
        if (
            raw.get("pid") != pid
            or raw.get("controlled_input_injected") is not True
            or raw.get("outcome_verified") is not False
            or raw.get("semantic_id") != "combat/resource/" + str(resource_name)
            or not isinstance(raw.get("first_frame_sha256"), str)
            or _SHA256_PATTERN.fullmatch(raw["first_frame_sha256"]) is None
            or not isinstance(raw.get("commit_frame_sha256"), str)
            or _SHA256_PATTERN.fullmatch(raw["commit_frame_sha256"]) is None
        ):
            raise SemanticGateClosed("controlled combat action identity changed")
        first = raw.get("first_generation")
        commit = raw.get("commit_generation")
        if (
            isinstance(first, bool)
            or not isinstance(first, int)
            or isinstance(commit, bool)
            or not isinstance(commit, int)
            or not previous < first < commit
        ):
            raise SemanticGateClosed("controlled combat actions are not increasing")
        resource = resources.get(resource_name)
        action = actions.get(action_name)
        allowed = ALAS_COMBAT_RESOURCE_ACTION_TARGETS.get(resource_name, ())
        if (
            resource is None
            or not resource.qualified
            or raw.get("resource_evidence_sha256") != resource.evidence_sha256
            or action is None
            or not action.qualified
            or action_name not in allowed
        ):
            raise SemanticGateClosed("controlled combat action is not qualified")
        variants = tuple(
            item
            for item in action.resolved_variants
            if item.variant_id == raw.get("action_variant_id")
            and item.evidence_sha256 == raw.get("action_evidence_sha256")
        )
        if len(variants) != 1 or not any(
            selector.require_top_raycast and selector.path == raw.get("path")
            for selector in variants[0].selectors
        ):
            raise SemanticGateClosed("controlled combat action variant changed")
        point = raw.get("point")
        bounds = raw.get("bounds")
        if (
            not isinstance(point, dict)
            or set(point) != {"x", "y"}
            or not isinstance(bounds, dict)
            or set(bounds) != {"left", "top", "right", "bottom"}
        ):
            raise SemanticGateClosed("controlled combat action geometry is malformed")
        if any(
            isinstance(number, bool) or not isinstance(number, (int, float))
            or not math.isfinite(float(number))
            for number in (*point.values(), *bounds.values())
        ):
            raise SemanticGateClosed("controlled combat action geometry is malformed")
        try:
            inside = (
                bounds["left"] <= point["x"] <= bounds["right"]
                and bounds["top"] <= point["y"] <= bounds["bottom"]
            )
        except (KeyError, TypeError):
            inside = False
        if not inside:
            raise SemanticGateClosed("controlled combat action point left its bounds")
        names.append(resource_name)
        generations.append(commit)
        previous = commit
    if tuple(names) not in _ALLOWED_ACTION_SEQUENCES:
        raise SemanticGateClosed("controlled combat action sequence changed")
    return {
        "resource_sequence": names,
        "commit_generations": generations,
        "last_generation": generations[-1],
    }


def _validate_map_transition(
    acquisition: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    manifest: AlasCombatObserverManifest,
    *,
    last_action_generation: int,
) -> Mapping[str, Any]:
    pid = acquisition["pid"]
    before = _map_value(acquisition.get("map_before"), "pre-combat")
    after = _checkpoint_value(checkpoint, manifest, pid=pid)
    identity_fields = (
        "stage_code",
        "rows",
        "columns",
        "land_nodes",
        "expected_fleet_count",
    )
    if any(before[name] != after[name] for name in identity_fields):
        raise SemanticGateClosed("controlled combat map contract changed")
    combat_input = acquisition["input"]
    target = combat_input["target_node"]
    origin = combat_input["origin_node"]
    route = combat_input["route_nodes"]
    marker = combat_input["fleet_marker"]
    enemy_object_id = combat_input["enemy_object_id"]
    if (
        not isinstance(route, list)
        or not route
        or route[0] != origin
        or route[-1] != target
        or len(route) != len(set(route))
    ):
        raise SemanticGateClosed("controlled combat route changed")
    same_cell = origin == target
    before_fleets = tuple(
        item for item in before["fleets"]
        if item.get("marker") == marker and item.get("node") == origin
    )
    after_fleets = tuple(
        item for item in after["fleets"]
        if item.get("marker") == marker and item.get("node") == target
    )
    before_enemies = tuple(
        item for item in before["enemies"]
        if item.get("node") == target
        and item.get("object_id") == enemy_object_id
        and item.get("fighting") is same_cell
    )
    if len(before_fleets) != 1 or len(before_enemies) != 1:
        raise SemanticGateClosed("controlled combat pre-input actors changed")
    if len(after_fleets) != 1 or any(
        item.get("node") == target for item in after["enemies"]
    ):
        raise SemanticGateClosed("controlled combat target did not clear")
    ammo_before = combat_input["ammo_before"]
    if (
        before_fleets[0].get("ammo") != ammo_before
        or after_fleets[0].get("ammo") != ammo_before - 1
    ):
        raise SemanticGateClosed("controlled combat ammunition did not decrement once")
    if (
        after["generation"] <= last_action_generation
        or after["current_fleet_marker"] != marker
    ):
        raise SemanticGateClosed("controlled combat stable map proof is stale")
    return {
        "stage_code": before["stage_code"],
        "origin_node": origin,
        "target_node": target,
        "route_nodes": route,
        "fleet_marker": marker,
        "ammo_before": ammo_before,
        "ammo_after": after_fleets[0]["ammo"],
        "pre_generation": before["generation"],
        "post_generation": after["generation"],
        "target_enemy_cleared": True,
        "target_fleet_retained": True,
    }


def analyze_alas_combat_controlled_episode(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    multiplex_evidence: Mapping[str, Any],
    acquisition: Mapping[str, Any],
    action_commits: Sequence[Mapping[str, Any]],
    post_map_checkpoint: Mapping[str, Any],
    *,
    source_trace_sha256: str,
    minimum_control_frames: int = 3,
) -> Mapping[str, Any]:
    """Build one deterministic G32 episode record; never inject input."""

    if (
        not isinstance(source_trace_sha256, str)
        or _SHA256_PATTERN.fullmatch(source_trace_sha256) is None
    ):
        raise SemanticGateClosed("controlled combat trace hash is malformed")
    audit_alas_combat_observer_manifest(manifest)
    if not isinstance(acquisition, dict) or acquisition.get("schema") != ALAS_COMBAT_ACQUISITION_SCHEMA:
        raise SemanticGateClosed("controlled combat acquisition version changed")
    if (
        acquisition.get("package") != manifest.package
        or acquisition.get("driver_revision") != manifest.driver_revision
        or acquisition.get("game_fingerprint") != manifest.game_fingerprint
        or acquisition.get("controlled_input_injected") is not True
        or acquisition.get("trace_recorder_input_injected") is not False
        or acquisition.get("pid") != trace.pid
        or acquisition.get("trace_sha256") != source_trace_sha256
        or acquisition.get("sample_count") != len(trace.samples)
        or acquisition.get("first_generation") != trace.generations[0]
        or acquisition.get("last_generation") != trace.generations[-1]
    ):
        raise SemanticGateClosed("controlled combat acquisition identity changed")
    before = _map_value(acquisition.get("map_before"), "pre-combat")
    combat_input = _combat_input_value(acquisition.get("input"), before)
    receipt_generation = combat_input.get("receipt_generation")
    if (
        isinstance(receipt_generation, bool)
        or not isinstance(receipt_generation, int)
        or not trace.generations[0] < receipt_generation < trace.generations[-1]
    ):
        raise SemanticGateClosed("controlled combat trace does not straddle grid input")

    multiplex = verify_alas_combat_surface_multiplex_evidence(
        manifest,
        trace,
        multiplex_evidence,
        source_trace_sha256=source_trace_sha256,
    )
    if multiplex.get("ambiguous_match"):
        raise SemanticGateClosed("controlled combat multiplex result is ambiguous")
    controls = []
    for profile_id in ("battle-status-s", "exp-info-s"):
        control = analyze_alas_combat_result_control_evidence(
            manifest,
            trace,
            profile_id=profile_id,
            source_trace_sha256=source_trace_sha256,
            minimum_consecutive_frames=minimum_control_frames,
        )
        verification = verify_alas_combat_result_control_evidence(
            manifest,
            trace,
            control,
            source_trace_sha256=source_trace_sha256,
        )
        if not verification["evidence_complete"]:
            raise SemanticGateClosed("controlled combat S positive control is incomplete")
        controls.append(control)

    actions = _validate_action_commits(
        manifest,
        action_commits,
        pid=trace.pid,
        minimum_generation=receipt_generation,
    )
    if trace.generations[-1] <= actions["last_generation"]:
        raise SemanticGateClosed("controlled combat trace does not cover result actions")
    transition = _validate_map_transition(
        acquisition,
        post_map_checkpoint,
        manifest,
        last_action_generation=actions["last_generation"],
    )
    return {
        "schema": ALAS_COMBAT_CONTROLLED_EPISODE_SCHEMA,
        "package": trace.package,
        "driver_revision": trace.driver_revision,
        "game_fingerprint": trace.game_fingerprint,
        "pid": trace.pid,
        "source_trace_sha256": source_trace_sha256,
        "sample_count": len(trace.samples),
        "first_generation": trace.generations[0],
        "last_generation": trace.generations[-1],
        "grid_receipt_generation": receipt_generation,
        "minimum_control_frames": minimum_control_frames,
        "multiplex": multiplex,
        "positive_controls": controls,
        "actions": actions,
        "map_transition": transition,
        "original_alas_decision_owner": True,
        "original_alas_goto_prefix_owner": True,
        "live_post_click_alas_state_machine_owner": False,
        "live_post_click_owner": "controlled-semantic-evidence-harness",
        "observer_input_only": True,
        "trace_recorder_input_injected": False,
        "auto_promoted": False,
        "production_enabled": False,
    }


def verify_alas_combat_controlled_episode(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    multiplex_evidence: Mapping[str, Any],
    acquisition: Mapping[str, Any],
    action_commits: Sequence[Mapping[str, Any]],
    post_map_checkpoint: Mapping[str, Any],
    record: Any,
    *,
    source_trace_sha256: str,
) -> Mapping[str, Any]:
    if not isinstance(record, dict):
        raise SemanticGateClosed("controlled combat episode record is malformed")
    expected = analyze_alas_combat_controlled_episode(
        manifest,
        trace,
        multiplex_evidence,
        acquisition,
        action_commits,
        post_map_checkpoint,
        source_trace_sha256=source_trace_sha256,
        minimum_control_frames=record.get("minimum_control_frames"),
    )
    if record != expected:
        raise SemanticGateClosed("controlled combat episode record changed")
    return {
        "schema": ALAS_COMBAT_CONTROLLED_EPISODE_VERIFICATION_SCHEMA,
        "passed": True,
        "pid": trace.pid,
        "sample_count": len(trace.samples),
        "action_count": len(action_commits),
        "positive_control_count": len(record["positive_controls"]),
        "target_enemy_cleared": True,
        "original_alas_decision_owner": True,
        "live_post_click_alas_state_machine_owner": False,
        "observer_input_only": True,
        "production_enabled": False,
    }
