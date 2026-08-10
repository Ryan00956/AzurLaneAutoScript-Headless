"""Exact Unity-observer input contract for ALAS campaign combat replay.

G19 qualified ALAS's original state machine with synthetic phase frames.  This
module is the boundary that may replace those frames: every ALAS presence
query must have a reviewed exact Unity selector, every observer slice must be
complete and hash-bound, and the six phases are inferred from records rather
than accepted as fixture labels.  The checked-in manifest deliberately has no
live combat mappings yet, so production use fails closed until real captures
are reviewed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .alas_combat_admission import AlasCampaignCombatAdmission
from .alas_combat_state_replay import (
    ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES,
    ALAS_COMBAT_REPLAY_PHASES,
    ALAS_COMBAT_REPLAY_RESOURCE_NAMES,
    AlasCampaignCombatReplay,
    AlasCombatReplayFrame,
    AlasCombatReplayPhase,
)
from .semantic_oracle import (
    BUTTON_SCHEMA,
    OBSERVER_SCHEMA,
    UI_SCHEMA,
    Bounds,
    ButtonState,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapPickupState,
    CampaignMapState,
    ImageState,
    OracleFingerprint,
    OracleState,
    Point,
    SemanticGateClosed,
    SemanticOracle,
    TextState,
    UiState,
)


ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA = (
    "alas-headless.g20-combat-observer-fixture/v1"
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_ACTION_RESOURCES = frozenset(
    {"BATTLE_PREPARATION", "BATTLE_STATUS_S", "EXP_INFO_S"}
)


class AlasCombatUnityRecordKind(str, Enum):
    BUTTON = "button"
    IMAGE = "image"
    TEXT = "text"


@dataclass(frozen=True)
class AlasCombatUnitySelector:
    """One exact record identity; no suffix, regex, OCR, or coordinate match."""

    kind: AlasCombatUnityRecordKind
    path: str
    name: str
    sprite: str = ""
    text: str = ""
    require_top_raycast: bool = False


@dataclass(frozen=True)
class AlasCombatResourceMapping:
    resource_name: str
    selectors: Tuple[AlasCombatUnitySelector, ...] = ()
    evidence_sha256: str = ""

    @property
    def qualified(self) -> bool:
        return bool(self.selectors) and _is_sha256(self.evidence_sha256)


@dataclass(frozen=True)
class AlasCombatFleetStatsMapping:
    hp_images: Tuple[AlasCombatUnitySelector, ...] = ()
    level_texts: Tuple[AlasCombatUnitySelector, ...] = ()
    evidence_sha256: str = ""

    @property
    def qualified(self) -> bool:
        return (
            len(self.hp_images) == 6
            and len(self.level_texts) == 6
            and _is_sha256(self.evidence_sha256)
        )


@dataclass(frozen=True)
class AlasCombatObserverManifest:
    package: str
    driver_revision: str
    game_fingerprint: str
    resources: Tuple[AlasCombatResourceMapping, ...]
    blocker_selectors: Tuple[AlasCombatUnitySelector, ...] = ()
    blocker_evidence_sha256: str = ""
    fleet_stats: AlasCombatFleetStatsMapping = AlasCombatFleetStatsMapping()


@dataclass(frozen=True)
class AlasCombatObserverCoverage:
    total_resources: int
    qualified_resources: int
    unqualified_resources: Tuple[str, ...]
    blockers_qualified: bool
    fleet_stats_qualified: bool

    @property
    def production_ready(self) -> bool:
        return (
            self.qualified_resources == self.total_resources
            and self.blockers_qualified
            and self.fleet_stats_qualified
        )


@dataclass(frozen=True)
class AlasCombatObserverSnapshot:
    """One complete, coherent observer generation without a trusted phase."""

    capture_sha256: str
    game_fingerprint: str
    oracle_state: OracleState
    ui_state: UiState
    campaign_map: Optional[CampaignMapState] = None

    @property
    def generation(self) -> int:
        values = [self.oracle_state.generation, self.ui_state.generation]
        if self.campaign_map is not None:
            values.append(self.campaign_map.generation)
        return max(values)


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def unqualified_alas_combat_observer_manifest(
    *,
    package: str = "com.bilibili.azurlane",
    driver_revision: str = "UNQUALIFIED",
    game_fingerprint: str = "UNQUALIFIED",
) -> AlasCombatObserverManifest:
    """Return the honest checked-in G20 coverage baseline: 0/38 mapped."""

    return AlasCombatObserverManifest(
        package=package,
        driver_revision=driver_revision,
        game_fingerprint=game_fingerprint,
        resources=tuple(
            AlasCombatResourceMapping(name)
            for name in ALAS_COMBAT_REPLAY_RESOURCE_NAMES
        ),
    )


def audit_alas_combat_observer_manifest(
    manifest: AlasCombatObserverManifest,
) -> AlasCombatObserverCoverage:
    if not isinstance(manifest, AlasCombatObserverManifest):
        raise SemanticGateClosed("combat observer manifest is not typed")
    if not manifest.package or not manifest.driver_revision or not manifest.game_fingerprint:
        raise SemanticGateClosed("combat observer manifest identity is incomplete")
    names = tuple(mapping.resource_name for mapping in manifest.resources)
    if len(names) != len(set(names)):
        raise SemanticGateClosed("combat observer manifest has duplicate resources")
    if set(names) != set(ALAS_COMBAT_REPLAY_RESOURCE_NAMES):
        raise SemanticGateClosed("combat observer resource surface changed")
    for mapping in manifest.resources:
        _validate_mapping_shape(mapping)
    for selector in manifest.blocker_selectors:
        _validate_selector(selector)
    if manifest.blocker_evidence_sha256 and not _is_sha256(
        manifest.blocker_evidence_sha256
    ):
        raise SemanticGateClosed("combat blocker evidence hash is malformed")
    _validate_stats_shape(manifest.fleet_stats)
    unqualified = tuple(
        sorted(
            mapping.resource_name
            for mapping in manifest.resources
            if not mapping.qualified
        )
    )
    return AlasCombatObserverCoverage(
        total_resources=len(ALAS_COMBAT_REPLAY_RESOURCE_NAMES),
        qualified_resources=len(ALAS_COMBAT_REPLAY_RESOURCE_NAMES)
        - len(unqualified),
        unqualified_resources=unqualified,
        blockers_qualified=bool(manifest.blocker_selectors)
        and _is_sha256(manifest.blocker_evidence_sha256),
        fleet_stats_qualified=manifest.fleet_stats.qualified,
    )


def _validate_selector(
    selector: AlasCombatUnitySelector, *, allow_dynamic_text: bool = False
) -> None:
    if not isinstance(selector, AlasCombatUnitySelector):
        raise SemanticGateClosed("combat Unity selector is not typed")
    if (
        not selector.path
        or not selector.name
        or "/" not in selector.path
        or selector.path.startswith("*")
    ):
        raise SemanticGateClosed("combat Unity selector identity is incomplete")
    if "*" in selector.path or selector.path.endswith("/"):
        raise SemanticGateClosed("combat Unity selector path is not exact")
    if selector.kind is AlasCombatUnityRecordKind.IMAGE:
        if not selector.sprite or selector.text:
            raise SemanticGateClosed("combat image selector is incomplete")
    elif selector.kind is AlasCombatUnityRecordKind.TEXT:
        if (
            (not selector.text and not allow_dynamic_text)
            or selector.sprite
            or selector.require_top_raycast
        ):
            raise SemanticGateClosed("combat text selector is incomplete")
    elif selector.kind is AlasCombatUnityRecordKind.BUTTON:
        if selector.sprite or selector.text:
            raise SemanticGateClosed("combat button selector is malformed")
    else:
        raise SemanticGateClosed("combat Unity selector kind is unsupported")


def _validate_mapping_shape(mapping: AlasCombatResourceMapping) -> None:
    if not isinstance(mapping, AlasCombatResourceMapping) or not mapping.resource_name:
        raise SemanticGateClosed("combat resource mapping is malformed")
    for selector in mapping.selectors:
        _validate_selector(selector)
    identities = tuple((selector.kind, selector.path) for selector in mapping.selectors)
    if len(identities) != len(set(identities)):
        raise SemanticGateClosed("combat resource mapping has duplicate selectors")
    if mapping.evidence_sha256 and not _is_sha256(mapping.evidence_sha256):
        raise SemanticGateClosed("combat resource evidence hash is malformed")
    if mapping.resource_name in _ACTION_RESOURCES and mapping.qualified:
        if not any(
            selector.kind is AlasCombatUnityRecordKind.BUTTON
            and selector.require_top_raycast
            for selector in mapping.selectors
        ):
            raise SemanticGateClosed(
                "combat action mapping lacks an exact top-raycast Button"
            )


def _validate_stats_shape(mapping: AlasCombatFleetStatsMapping) -> None:
    if not isinstance(mapping, AlasCombatFleetStatsMapping):
        raise SemanticGateClosed("combat fleet stats mapping is not typed")
    for selector in mapping.hp_images:
        _validate_selector(selector)
        if selector.kind is not AlasCombatUnityRecordKind.IMAGE:
            raise SemanticGateClosed("combat HP mapping is not an Image")
    for selector in mapping.level_texts:
        _validate_selector(selector, allow_dynamic_text=True)
        if selector.kind is not AlasCombatUnityRecordKind.TEXT:
            raise SemanticGateClosed("combat level mapping is not Text")
    identities = tuple(
        (selector.kind, selector.path)
        for selector in mapping.hp_images + mapping.level_texts
    )
    if len(identities) != len(set(identities)):
        raise SemanticGateClosed("combat fleet stats mapping has duplicate selectors")
    if mapping.evidence_sha256 and not _is_sha256(mapping.evidence_sha256):
        raise SemanticGateClosed("combat fleet stats evidence hash is malformed")


def _validate_snapshot(
    snapshot: AlasCombatObserverSnapshot,
    manifest: AlasCombatObserverManifest,
) -> None:
    if not isinstance(snapshot, AlasCombatObserverSnapshot):
        raise SemanticGateClosed("combat observer snapshot is not typed")
    if not _is_sha256(snapshot.capture_sha256):
        raise SemanticGateClosed("combat observer capture hash is malformed")
    if snapshot.game_fingerprint != manifest.game_fingerprint:
        raise SemanticGateClosed("combat observer game fingerprint changed")
    oracle = snapshot.oracle_state
    ui = snapshot.ui_state
    if not isinstance(oracle, OracleState) or not isinstance(ui, UiState):
        raise SemanticGateClosed("combat observer endpoint state is not typed")
    payloads = (oracle.snapshot, oracle.buttons_snapshot, ui.snapshot)
    if any(payload.get("package") != manifest.package for payload in payloads):
        raise SemanticGateClosed("combat observer package changed")
    if any(
        payload.get("driver_revision") != manifest.driver_revision
        for payload in payloads
    ):
        raise SemanticGateClosed("combat observer driver revision changed")
    pids = tuple(payload.get("pid") for payload in payloads)
    if any(isinstance(pid, bool) or not isinstance(pid, int) for pid in pids):
        raise SemanticGateClosed("combat observer PID is malformed")
    if len(set(pids)) != 1:
        raise SemanticGateClosed("combat observer endpoints disagree on PID")
    if oracle.buttons_snapshot.get("truncated") is not False:
        raise SemanticGateClosed("combat Button snapshot is truncated")
    if ui.snapshot.get("toggle_truncated") is not False:
        raise SemanticGateClosed("combat Toggle snapshot is truncated")
    if ui.snapshot.get("text_truncated") is not False:
        raise SemanticGateClosed("combat Text snapshot is truncated")
    if ui.snapshot.get("image_truncated") is not False or ui.image_truncated:
        raise SemanticGateClosed("combat Image snapshot is truncated")
    if oracle.buttons_snapshot.get("error_count") != 0 or ui.snapshot.get(
        "error_count"
    ) != 0:
        raise SemanticGateClosed("combat observer snapshot has extraction errors")
    if ui.method_mask & 0xE != 0xE:
        raise SemanticGateClosed("combat observer typed UI methods are incomplete")
    generations = (oracle.generation, ui.generation)
    if generations[1] < generations[0] - 2 or generations[1] > generations[0] + 2:
        raise SemanticGateClosed("combat observer endpoints are generation-incoherent")
    if snapshot.campaign_map is not None:
        if not isinstance(snapshot.campaign_map, CampaignMapState):
            raise SemanticGateClosed("combat map observation is not typed")
        endpoint_generation = max(oracle.generation, ui.generation)
        if abs(snapshot.campaign_map.generation - endpoint_generation) > 2:
            raise SemanticGateClosed("combat map observation is generation-incoherent")


def _record_for_selector(
    snapshot: AlasCombatObserverSnapshot,
    selector: AlasCombatUnitySelector,
) -> Optional[Any]:
    if selector.kind is AlasCombatUnityRecordKind.BUTTON:
        records: Iterable[Any] = snapshot.oracle_state.buttons
    elif selector.kind is AlasCombatUnityRecordKind.IMAGE:
        records = snapshot.ui_state.images
    else:
        records = snapshot.ui_state.texts
    identities = [record for record in records if record.path == selector.path]
    if len(identities) > 1:
        raise SemanticGateClosed("combat Unity selector path is ambiguous")
    if not identities:
        return None
    record = identities[0]
    if record.name != selector.name:
        raise SemanticGateClosed("combat Unity selector name drifted")
    if selector.kind is AlasCombatUnityRecordKind.IMAGE:
        if record.truncated:
            raise SemanticGateClosed("combat Unity Image identity is truncated")
        if record.sprite != selector.sprite:
            return None
    elif selector.kind is AlasCombatUnityRecordKind.TEXT:
        if record.truncated:
            raise SemanticGateClosed("combat Unity Text identity is truncated")
        if selector.text and record.text != selector.text:
            return None
    return record


def _selector_present(
    snapshot: AlasCombatObserverSnapshot,
    selector: AlasCombatUnitySelector,
) -> bool:
    record = _record_for_selector(snapshot, selector)
    if record is None:
        return False
    if not record.active_in_hierarchy or not record.active_and_enabled:
        return False
    if selector.require_top_raycast:
        if not isinstance(record, ButtonState) or not record.actionable:
            raise SemanticGateClosed(
                "combat action Button is not exact top-raycast actionable"
            )
    return True


def _resource_visible(
    snapshot: AlasCombatObserverSnapshot,
    mapping: AlasCombatResourceMapping,
) -> bool:
    return all(_selector_present(snapshot, item) for item in mapping.selectors)


def _fleet_stats(
    snapshot: AlasCombatObserverSnapshot,
    mapping: AlasCombatFleetStatsMapping,
) -> Tuple[Tuple[float, ...], Tuple[int, ...]]:
    hp = []
    for selector in mapping.hp_images:
        record = _record_for_selector(snapshot, selector)
        if not isinstance(record, ImageState) or not _selector_present(
            snapshot, selector
        ):
            raise SemanticGateClosed("combat HP Image is absent")
        value = float(record.fill_amount)
        if not 0.0 <= value <= 1.0:
            raise SemanticGateClosed("combat HP fill is outside [0, 1]")
        hp.append(value)
    levels = []
    for selector in mapping.level_texts:
        record = _record_for_selector(snapshot, selector)
        if not isinstance(record, TextState) or not _selector_present(
            snapshot, selector
        ):
            raise SemanticGateClosed("combat level Text is absent")
        if re.fullmatch(r"(?:[1-9]|[1-9][0-9]|1[01][0-9]|12[0-5])", record.text) is None:
            raise SemanticGateClosed("combat fleet level is outside 1..125")
        levels.append(int(record.text))
    return tuple(hp), tuple(levels)


def _map_flags(
    phase: AlasCombatReplayPhase,
    state: Optional[CampaignMapState],
    admission: AlasCampaignCombatAdmission,
) -> Tuple[bool, bool, bool]:
    if phase not in (
        AlasCombatReplayPhase.MAP_SEARCHING,
        AlasCombatReplayPhase.MAP_STABLE,
    ):
        if state is not None:
            raise SemanticGateClosed("combat map observation appeared too early")
        return False, False, False
    if state is None:
        raise SemanticGateClosed("combat map observation is missing")
    if state.stage_code != admission.stage_code:
        raise SemanticGateClosed("combat map stage changed")
    target_cells = tuple(cell for cell in state.cells if cell.node == admission.target_node)
    if len(target_cells) != 1:
        raise SemanticGateClosed("combat target cell is absent or ambiguous")
    target_cell = target_cells[0]
    if (
        target_cell.button_path != admission.cell_path
        or target_cell.point != admission.point
        or target_cell.bounds != admission.bounds
    ):
        raise SemanticGateClosed("combat target cell geometry changed")
    target_fleets = tuple(fleet for fleet in state.fleets if fleet.node == admission.target_node)
    fleet_on_target = any(fleet.marker == admission.fleet_marker for fleet in target_fleets)
    current_on_target = (
        state.current_fleet_marker == admission.fleet_marker and fleet_on_target
    )
    if not fleet_on_target or not current_on_target:
        raise SemanticGateClosed("combat target fleet identity changed")
    if phase is AlasCombatReplayPhase.MAP_STABLE and any(
        enemy.node == admission.target_node for enemy in state.enemies
    ):
        raise SemanticGateClosed("combat target enemy remains on stable map")
    if phase is AlasCombatReplayPhase.MAP_STABLE:
        matching_fleet = next(
            fleet for fleet in target_fleets if fleet.marker == admission.fleet_marker
        )
        if matching_fleet.ammo != admission.ammo_before - 1:
            raise SemanticGateClosed("combat target fleet ammo did not decrement")
    return True, fleet_on_target, current_on_target


def build_alas_campaign_combat_replay_from_observer(
    admission: AlasCampaignCombatAdmission,
    snapshots: Sequence[AlasCombatObserverSnapshot],
    manifest: AlasCombatObserverManifest,
) -> AlasCampaignCombatReplay:
    """Infer the pinned six replay frames from complete exact Unity records."""

    if not isinstance(admission, AlasCampaignCombatAdmission):
        raise SemanticGateClosed("combat observer replay requires an admission")
    coverage = audit_alas_combat_observer_manifest(manifest)
    if not coverage.production_ready:
        raise SemanticGateClosed(
            "combat observer manifest is not production-ready: {0}/38 resources"
            .format(coverage.qualified_resources)
        )
    if len(snapshots) != len(ALAS_COMBAT_REPLAY_PHASES):
        raise SemanticGateClosed("combat observer replay requires six snapshots")
    mappings: Dict[str, AlasCombatResourceMapping] = {
        item.resource_name: item for item in manifest.resources
    }
    frames = []
    previous = admission.input_generation
    for phase, snapshot in zip(ALAS_COMBAT_REPLAY_PHASES, snapshots):
        _validate_snapshot(snapshot, manifest)
        if snapshot.generation <= previous:
            raise SemanticGateClosed(
                "combat observer generations are not strictly increasing"
            )
        previous = snapshot.generation
        active_blockers = tuple(
            selector.path
            for selector in manifest.blocker_selectors
            if _selector_present(snapshot, selector)
        )
        if active_blockers:
            raise SemanticGateClosed(
                "combat observer blocker is active: " + ", ".join(active_blockers)
            )
        visible = tuple(
            name
            for name in ALAS_COMBAT_REPLAY_RESOURCE_NAMES
            if _resource_visible(snapshot, mappings[name])
        )
        expected = ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES[phase]
        if set(visible) != set(expected):
            raise SemanticGateClosed(
                "combat observer records do not prove expected phase " + phase.value
            )
        in_map, fleet_on_target, current_on_target = _map_flags(
            phase, snapshot.campaign_map, admission
        )
        hp: Tuple[float, ...] = ()
        levels: Tuple[int, ...] = ()
        if phase is AlasCombatReplayPhase.MAP_STABLE:
            hp, levels = _fleet_stats(snapshot, manifest.fleet_stats)
        frames.append(
            AlasCombatReplayFrame(
                generation=snapshot.generation,
                phase=phase,
                visible_resources=tuple(sorted(visible)),
                in_map=in_map,
                combat_loading=phase is AlasCombatReplayPhase.BATTLE_PREPARATION,
                combat_executing=phase is AlasCombatReplayPhase.COMBAT_EXECUTING,
                enemy_searching=phase is AlasCombatReplayPhase.MAP_SEARCHING,
                fleet_on_target=fleet_on_target,
                current_fleet_on_target=current_on_target,
                hp=hp,
                levels=levels,
            )
        )
    return AlasCampaignCombatReplay(
        stage_code=admission.stage_code,
        target_node=admission.target_node,
        input_generation=admission.input_generation,
        frames=tuple(frames),
    )


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fixture_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticGateClosed("combat fixture integer is malformed: " + field)
    return value


def _fixture_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticGateClosed("combat fixture number is malformed: " + field)
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise SemanticGateClosed("combat fixture number is non-finite: " + field)
    return result


def _fixture_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SemanticGateClosed("combat fixture text is malformed: " + field)
    return value


def _fixture_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise SemanticGateClosed("combat fixture boolean is malformed: " + field)
    return value


def _parse_campaign_map(value: Any) -> Optional[CampaignMapState]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SemanticGateClosed("combat fixture map is malformed")
    try:
        cells = tuple(
            CampaignMapCellState(
                row=_fixture_int(item["row"], "cell.row"),
                column=_fixture_int(item["column"], "cell.column"),
                node=_fixture_text(item["node"], "cell.node"),
                button_path=_fixture_text(item["button_path"], "cell.button_path"),
                point=Point(
                    _fixture_number(item["point"]["x"], "cell.point.x"),
                    _fixture_number(item["point"]["y"], "cell.point.y"),
                ),
                bounds=Bounds(
                    _fixture_number(item["bounds"]["left"], "cell.bounds.left"),
                    _fixture_number(item["bounds"]["top"], "cell.bounds.top"),
                    _fixture_number(item["bounds"]["right"], "cell.bounds.right"),
                    _fixture_number(item["bounds"]["bottom"], "cell.bounds.bottom"),
                ),
            )
            for item in value["cells"]
        )
        fleets = tuple(
            CampaignMapFleetState(
                marker=_fixture_text(item["marker"], "fleet.marker"),
                node=_fixture_text(item["node"], "fleet.node"),
                ammo=_fixture_int(item["ammo"], "fleet.ammo"),
                ammo_capacity=_fixture_int(
                    item["ammo_capacity"], "fleet.ammo_capacity"
                ),
            )
            for item in value["fleets"]
        )
        enemies = tuple(
            CampaignMapEnemyState(
                row=_fixture_int(item["row"], "enemy.row"),
                column=_fixture_int(item["column"], "enemy.column"),
                node=_fixture_text(item["node"], "enemy.node"),
                object_id=_fixture_int(item["object_id"], "enemy.object_id"),
                sprite=_fixture_text(item["sprite"], "enemy.sprite"),
                scale=_fixture_int(item["scale"], "enemy.scale"),
                genre=_fixture_text(item["genre"], "enemy.genre"),
                level=_fixture_int(item["level"], "enemy.level"),
                fighting=_fixture_bool(item["fighting"], "enemy.fighting"),
            )
            for item in value["enemies"]
        )
        pickups = tuple(
            CampaignMapPickupState(
                row=_fixture_int(item["row"], "pickup.row"),
                column=_fixture_int(item["column"], "pickup.column"),
                node=_fixture_text(item["node"], "pickup.node"),
                kind=_fixture_text(item["kind"], "pickup.kind"),
                sprite=_fixture_text(item["sprite"], "pickup.sprite"),
            )
            for item in value["pickups"]
        )
        state = CampaignMapState(
            generation=_fixture_int(value["generation"], "map.generation"),
            stage_code=_fixture_text(value["stage_code"], "map.stage_code"),
            rows=_fixture_int(value["rows"], "map.rows"),
            columns=_fixture_int(value["columns"], "map.columns"),
            cells=cells,
            land_nodes=tuple(
                _fixture_text(item, "map.land_node") for item in value["land_nodes"]
            ),
            fleets=fleets,
            enemies=enemies,
            pickups=pickups,
            displayed_fleet_index=_fixture_int(
                value["displayed_fleet_index"], "map.displayed_fleet_index"
            ),
            current_fleet_marker=_fixture_text(
                value["current_fleet_marker"], "map.current_fleet_marker"
            ),
            current_fleet_roster_sprites=tuple(
                _fixture_text(item, "map.roster_sprite")
                for item in value["current_fleet_roster_sprites"]
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SemanticGateClosed("combat fixture map is incomplete") from exc
    observed_nodes = tuple(cell.node for cell in state.cells) + state.land_nodes
    if (
        not state.cells
        or not state.fleets
        or state.rows < 1
        or state.columns < 1
        or len(observed_nodes) != state.rows * state.columns
        or len(observed_nodes) != len(set(observed_nodes))
        or len(state.current_fleet_roster_sprites) not in range(1, 7)
    ):
        raise SemanticGateClosed("combat fixture map has no complete topology")
    return state


def _parse_fixture_frame(
    value: Any,
    manifest: AlasCombatObserverManifest,
) -> AlasCombatObserverSnapshot:
    if not isinstance(value, dict):
        raise SemanticGateClosed("combat fixture frame is not an object")
    payload = {
        "snapshot": value.get("snapshot"),
        "buttons": value.get("buttons"),
        "ui": value.get("ui"),
        "campaign_map": value.get("campaign_map"),
    }
    declared_hash = value.get("sha256")
    if declared_hash != _canonical_sha256(payload):
        raise SemanticGateClosed("combat fixture frame hash changed")
    snapshot_raw = payload["snapshot"]
    buttons_raw = payload["buttons"]
    ui_raw = payload["ui"]
    if not all(isinstance(item, dict) for item in (snapshot_raw, buttons_raw, ui_raw)):
        raise SemanticGateClosed("combat fixture endpoint payload is malformed")
    parser = SemanticOracle(
        request=lambda request: {},
        foreground_component=lambda: "",
        tap=lambda x, y: None,
        fingerprint=OracleFingerprint(
            package=manifest.package,
            component="fixture",
            driver_revision=manifest.driver_revision,
        ),
    )
    parser._validate_identity(snapshot_raw)  # exact live parser, offline transport
    parser._validate_identity(buttons_raw, BUTTON_SCHEMA)
    parser._validate_identity(ui_raw, UI_SCHEMA)
    if snapshot_raw.get("snapshot_schema") != 1:
        raise SemanticGateClosed("combat fixture snapshot schema mismatch")
    if (
        snapshot_raw.get("main_thread") is not True
        or snapshot_raw.get("flags") != 15
        or snapshot_raw.get("ui_stage") != 100
        or snapshot_raw.get("ui_method_mask") != 15
        or snapshot_raw.get("width") != 1280
        or snapshot_raw.get("height") != 720
    ):
        raise SemanticGateClosed("combat fixture main-thread probe is incomplete")
    raw_buttons = buttons_raw.get("buttons")
    raw_toggles = ui_raw.get("toggles")
    raw_texts = ui_raw.get("texts")
    raw_images = ui_raw.get("images")
    if not all(
        isinstance(item, list)
        for item in (raw_buttons, raw_toggles, raw_texts, raw_images)
    ):
        raise SemanticGateClosed("combat fixture record list is malformed")
    if (
        buttons_raw.get("schema") != 1
        or buttons_raw.get("truncated") is not False
        or buttons_raw.get("error_count") != 0
        or buttons_raw.get("button_count") != len(raw_buttons)
        or ui_raw.get("schema") != 1
        or ui_raw.get("toggle_truncated") is not False
        or ui_raw.get("text_truncated") is not False
        or ui_raw.get("image_truncated") is not False
        or ui_raw.get("error_count") != 0
        or ui_raw.get("toggle_count") != len(raw_toggles)
        or ui_raw.get("text_count") != len(raw_texts)
        or ui_raw.get("image_count") != len(raw_images)
        or ui_raw.get("method_mask") != 15
    ):
        raise SemanticGateClosed("combat fixture endpoint completeness changed")
    oracle_generation = parser._integer(
        buttons_raw.get("generation"), "fixture Button generation"
    )
    ui_generation = parser._integer(ui_raw.get("generation"), "fixture UI generation")
    snapshot_generation = parser._integer(
        snapshot_raw.get("generation"), "fixture snapshot generation"
    )
    if (
        oracle_generation < snapshot_generation
        or oracle_generation > snapshot_generation + 2
        or abs(ui_generation - oracle_generation) > 2
    ):
        raise SemanticGateClosed("combat fixture endpoint generations disagree")
    oracle_state = OracleState(
        generation=oracle_generation,
        scene_handle=parser._integer(snapshot_raw.get("scene_handle"), "scene_handle"),
        snapshot=snapshot_raw,
        buttons_snapshot=buttons_raw,
        buttons=tuple(parser._parse_button(item) for item in raw_buttons),
    )
    ui_state = UiState(
        generation=ui_generation,
        method_mask=15,
        skipped_count=parser._integer(ui_raw.get("skipped_count"), "skipped_count"),
        image_truncated=False,
        snapshot=ui_raw,
        toggles=tuple(parser._parse_toggle(item) for item in raw_toggles),
        texts=tuple(parser._parse_text(item) for item in raw_texts),
        images=tuple(parser._parse_image(item) for item in raw_images),
    )
    return AlasCombatObserverSnapshot(
        capture_sha256=declared_hash,
        game_fingerprint=manifest.game_fingerprint,
        oracle_state=oracle_state,
        ui_state=ui_state,
        campaign_map=_parse_campaign_map(payload["campaign_map"]),
    )


def load_alas_combat_observer_fixture(
    path: Path,
    manifest: AlasCombatObserverManifest,
) -> Tuple[AlasCombatObserverSnapshot, ...]:
    """Load hash-bound raw observer endpoint payloads for offline replay."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticGateClosed("combat observer fixture cannot be read") from exc
    if not isinstance(value, dict) or value.get("schema") != ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA:
        raise SemanticGateClosed("combat observer fixture schema mismatch")
    if value.get("game_fingerprint") != manifest.game_fingerprint:
        raise SemanticGateClosed("combat fixture game fingerprint changed")
    frames = value.get("frames")
    if not isinstance(frames, list) or len(frames) != 6:
        raise SemanticGateClosed("combat observer fixture requires six frames")
    if any("phase" in frame for frame in frames if isinstance(frame, dict)):
        raise SemanticGateClosed("combat fixture must not provide phase tokens")
    return tuple(_parse_fixture_frame(frame, manifest) for frame in frames)
