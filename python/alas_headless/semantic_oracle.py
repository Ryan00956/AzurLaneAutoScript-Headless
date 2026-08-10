"""Fail-closed client for the in-process ALAS headless semantic observer.

The observer is intentionally read-only.  This module performs input through an
independent ADB backend only after package, foreground, freshness, generation,
mapping, bounds, and known-blocker gates have all passed.
"""

from __future__ import annotations

import json
import math
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


OBSERVER_SCHEMA = "alas-headless.observer/v1"
BUTTON_SCHEMA = "alas-headless.buttons/v1"
UI_SCHEMA = "alas-headless.ui/v1"


class SemanticOracleError(RuntimeError):
    """Base error for semantic observation and action failures."""


class SemanticGateClosed(SemanticOracleError):
    """The requested action was refused because a safety gate is not proven."""


class SemanticTargetMissing(SemanticGateClosed):
    """A mapped semantic target is not present in the current valid snapshot."""


class ObserverTransportError(SemanticOracleError):
    """The local observer transport failed or returned malformed data."""


@dataclass(frozen=True)
class OracleFingerprint:
    package: str
    component: str
    driver_revision: str
    width: int = 1280
    height: int = 720
    max_age_ms: int = 2500
    peer_uid: int = 2000
    expected_pid: Optional[int] = None


@dataclass(frozen=True)
class AndroidPackageFingerprint:
    version_name: str
    version_code: int
    primary_abi: str
    base_apk_sha256: str
    il2cpp_sha256: str


@dataclass(frozen=True)
class SemanticTarget:
    semantic_id: str
    name: str
    path_suffix: str


@dataclass(frozen=True)
class SemanticImageTarget:
    semantic_id: str
    path_parent_suffix: str
    selected_sprite: str
    inactive_sprite: str


@dataclass(frozen=True)
class SemanticToggleTarget:
    semantic_id: str
    name: str
    path_suffix: str
    expected_child_sprite: Optional[str] = None


@dataclass(frozen=True)
class SemanticTextTarget:
    semantic_id: str
    path_suffix: str
    expected_texts: Tuple[str, ...]


@dataclass(frozen=True)
class BlockerRule:
    blocker_id: str
    path_fragment: str
    allowed_target_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, point: Point) -> bool:
        return (
            self.left <= point.x <= self.right
            and self.top <= point.y <= self.bottom
        )


@dataclass(frozen=True)
class ButtonState:
    name: str
    path: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    interactable: bool
    raycast_top: Optional[bool]
    point: Optional[Point]
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]

    @property
    def actionable(self) -> bool:
        return (
            self.active_in_hierarchy
            and self.active_and_enabled
            and self.interactable
            and self.raycast_top is True
            and self.point is not None
            and self.bounds is not None
            and self.bounds.contains(self.point)
        )


@dataclass(frozen=True)
class ToggleState:
    name: str
    path: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    interactable: bool
    checked: bool
    raycast_top: Optional[bool]
    point: Optional[Point]
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]

    @property
    def actionable(self) -> bool:
        return (
            self.active_in_hierarchy
            and self.active_and_enabled
            and self.interactable
            and self.raycast_top is True
            and self.point is not None
            and self.bounds is not None
            and self.bounds.contains(self.point)
        )


@dataclass(frozen=True)
class TextState:
    kind: str
    name: str
    path: str
    text: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    truncated: bool
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ImageState:
    name: str
    path: str
    sprite: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    raycast_target: bool
    raycast_top: Optional[bool]
    color: Tuple[float, float, float, float]
    fill_amount: float
    truncated: bool
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class UiState:
    generation: int
    method_mask: int
    skipped_count: int
    image_truncated: bool
    snapshot: Mapping[str, Any]
    toggles: Tuple[ToggleState, ...]
    texts: Tuple[TextState, ...]
    images: Tuple[ImageState, ...]


@dataclass(frozen=True)
class IndexedTextGroup:
    index: int
    path: str
    texts: Tuple[TextState, ...]


@dataclass(frozen=True)
class OracleState:
    generation: int
    scene_handle: int
    snapshot: Mapping[str, Any]
    buttons_snapshot: Mapping[str, Any]
    buttons: Tuple[ButtonState, ...]


@dataclass(frozen=True)
class ActionReceipt:
    semantic_id: str
    generation: int
    point: Point
    bounds: Bounds
    path: str


class MissionDisposition(str, Enum):
    """Observed task-page state proven only from reviewed Unity Buttons."""

    CLAIMABLE_ALL = "claimable-all"
    CLAIMABLE_ROW = "claimable-row"
    UNFINISHED = "unfinished"
    EMPTY = "empty"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MissionPageState:
    disposition: MissionDisposition
    generation: int
    back: ButtonState
    claim_all: Optional[ButtonState]
    claim_rows: Tuple[ButtonState, ...]
    unfinished_rows: Tuple[ButtonState, ...]

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.disposition,
            self.claim_all.path if self.claim_all is not None else None,
            tuple(button.path for button in self.claim_rows),
            tuple(button.path for button in self.unfinished_rows),
        )


class CommissionStatus(str, Enum):
    """Commission row status proven from an exact typed Unity sprite."""

    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"


@dataclass(frozen=True)
class CommissionRowState:
    index: int
    name: str
    level: int
    duration_seconds: int
    status: CommissionStatus
    type_sprite: str
    button: ButtonState

    @property
    def signature(self) -> Tuple[Union[int, str], ...]:
        return (
            self.index,
            self.name,
            self.level,
            self.duration_seconds,
            self.status.value,
            self.type_sprite,
        )


@dataclass(frozen=True)
class CommissionDetailState:
    name: str
    level: int
    duration_seconds: int
    oil_cost: int
    selected_ship_count: int
    empty_ship_count: int

    @property
    def signature(self) -> Tuple[Union[int, str], ...]:
        return (self.name, self.level, self.duration_seconds)


@dataclass(frozen=True)
class CommissionStartProof:
    index: int
    name: str
    level: int
    type_sprite: str
    before_duration_seconds: int
    after_duration_seconds: int
    before_status_sprite: str
    after_status_sprite: str
    generation: int


@dataclass(frozen=True)
class CommissionRewardProof:
    before_finished_count: int
    after_finished_count: int
    claim_generation: int
    close_semantic_ids: Tuple[str, ...]
    generation: int


@dataclass(frozen=True)
class CommissionScrollState:
    generation: int
    position: float
    page_fraction: float
    track_bounds: Bounds
    handle_bounds: Bounds
    handle_path: str
    handle_raycast_top: Optional[bool]

    @property
    def scrollable(self) -> bool:
        return self.page_fraction < 0.98

    @property
    def at_top(self) -> bool:
        return not self.scrollable or self.position <= 0.05

    @property
    def at_bottom(self) -> bool:
        return not self.scrollable or self.position >= 0.95


@dataclass(frozen=True)
class CommissionScrollProof:
    direction: str
    before_position: float
    after_position: float
    before_generation: int
    after_generation: int
    before_row_signatures: Tuple[Tuple[Union[int, str], ...], ...]
    after_row_signatures: Tuple[Tuple[Union[int, str], ...], ...]


class BuildPool(str, Enum):
    LIGHT = "light"
    HEAVY = "heavy"
    SPECIAL = "special"


@dataclass(frozen=True)
class BuildCostState:
    cubes_owned: int
    cubes_per_build: int
    coins_per_build: int


@dataclass(frozen=True)
class DormState:
    occupied_slots: int
    total_slots: int
    food: int
    food_capacity: int
    comfort: int
    floor: int
    food_countdown_seconds: Optional[int]


@dataclass(frozen=True)
class CampaignStageState:
    stage_id: int
    stage_code: str
    title: str
    button: ButtonState


@dataclass(frozen=True)
class CampaignPageState:
    generation: int
    chapter_name: str
    stages: Tuple[CampaignStageState, ...]


@dataclass(frozen=True)
class CampaignPreparationState:
    generation: int
    kind: str
    stage_code: str
    title: str
    proceed_button: ButtonState
    cancel_button: ButtonState


@dataclass(frozen=True)
class CampaignFleetRowState:
    row_key: str
    selected_fleet: Optional[int]
    ship_levels: Tuple[int, ...]
    select_button: ButtonState
    clear_button: ButtonState

    @property
    def in_use(self) -> bool:
        return bool(self.ship_levels)


@dataclass(frozen=True)
class CampaignFleetSelectionState:
    generation: int
    stage_code: str
    title: str
    surface_fleets: Tuple[int, int]
    submarine_fleets: Tuple[int, int]
    mob_oil_cost: int
    boss_oil_cost: int
    submarine_oil_cost: int
    rows: Tuple[CampaignFleetRowState, ...]
    sortie_button: ButtonState


@dataclass(frozen=True)
class CampaignFleetDropdownState:
    generation: int
    active_indices: Tuple[int, ...]
    options: Tuple[ToggleState, ...]


@dataclass(frozen=True)
class CampaignMapEntryState:
    generation: int
    root_path: str
    button_paths: Tuple[str, ...]
    image_paths: Tuple[str, ...]


@dataclass(frozen=True)
class CampaignMapCellState:
    row: int
    column: int
    node: str
    button_path: str
    point: Point
    bounds: Bounds


@dataclass(frozen=True)
class CampaignMapEnemyState:
    row: int
    column: int
    node: str
    object_id: int
    sprite: str
    scale: int
    genre: str
    level: int
    fighting: bool


@dataclass(frozen=True)
class CampaignMapPickupState:
    row: int
    column: int
    node: str
    kind: str
    sprite: str


@dataclass(frozen=True)
class CampaignMapFleetState:
    marker: str
    node: str
    ammo: int
    ammo_capacity: int


@dataclass(frozen=True)
class CampaignMapState:
    generation: int
    stage_code: str
    rows: int
    columns: int
    cells: Tuple[CampaignMapCellState, ...]
    land_nodes: Tuple[str, ...]
    fleets: Tuple[CampaignMapFleetState, ...]
    enemies: Tuple[CampaignMapEnemyState, ...]
    pickups: Tuple[CampaignMapPickupState, ...]
    displayed_fleet_index: int
    current_fleet_marker: str
    current_fleet_roster_sprites: Tuple[str, ...]

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.stage_code,
            self.rows,
            self.columns,
            tuple((cell.node, cell.button_path) for cell in self.cells),
            self.land_nodes,
            tuple(
                (fleet.marker, fleet.node, fleet.ammo, fleet.ammo_capacity)
                for fleet in self.fleets
            ),
            tuple(
                (
                    enemy.node,
                    enemy.object_id,
                    enemy.sprite,
                    enemy.scale,
                    enemy.genre,
                    enemy.level,
                    enemy.fighting,
                )
                for enemy in self.enemies
            ),
            tuple((pickup.node, pickup.kind, pickup.sprite) for pickup in self.pickups),
            self.displayed_fleet_index,
            self.current_fleet_marker,
            self.current_fleet_roster_sprites,
        )


class ResearchProjectStatus(str, Enum):
    DETAIL = "detail"
    RUNNING = "running"
    WAITING = "waiting"
    FINISHED = "finished"


@dataclass(frozen=True)
class ResearchProjectState:
    slot: int
    unity_index: int
    code: str
    subtitle: str
    series: int
    status: ResearchProjectStatus
    duration_seconds: int
    button: ButtonState


@dataclass(frozen=True)
class ResearchDetailState:
    code: str
    subtitle: str
    duration_seconds: int
    resource_id: str
    resource_owned: int
    resource_required: int
    requirement: str
    can_start: bool
    can_queue: bool
    is_running: bool
    is_finished: bool


@dataclass(frozen=True)
class ResearchQueueEntryState:
    slot: int
    code: str
    series: int
    status: ResearchProjectStatus
    remaining_seconds: int


@dataclass(frozen=True)
class ResearchQueueState:
    entries: Tuple[ResearchQueueEntryState, ...]
    reward_claimable: bool

    @property
    def empty_slots(self) -> int:
        return 5 - len(self.entries)

    @property
    def finished_count(self) -> int:
        return sum(
            entry.status == ResearchProjectStatus.FINISHED
            for entry in self.entries
        )

    @property
    def first_remaining_seconds(self) -> int:
        for entry in self.entries:
            if entry.status == ResearchProjectStatus.RUNNING:
                return entry.remaining_seconds
        return 0


@dataclass(frozen=True)
class DormFoodState:
    item_id: int
    value: int
    count: int
    button: ButtonState


@dataclass(frozen=True)
class DormFeedState:
    food: int
    capacity: int
    items: Tuple[DormFoodState, ...]


@dataclass(frozen=True)
class BuildSubmitState:
    count: int
    cubes_owned: int
    cubes_required: int
    coins_required: int
    confirm: ButtonState


class TacticalSlotStatus(str, Enum):
    RUNNING = "running"
    FINISHED = "finished"


@dataclass(frozen=True)
class TacticalSlotState:
    slot: int
    ship_id: int
    ship_name: str
    ship_level: int
    skill_name: str
    skill_level: int
    exp_current: int
    exp_total: int
    status: TacticalSlotStatus
    remaining_seconds: Optional[int]
    button: ButtonState


@dataclass(frozen=True)
class TacticalCandidateShipState:
    position: int
    ship_id: int
    ship_name: str
    level: int
    button: ButtonState


@dataclass(frozen=True)
class TacticalSkillState:
    position: int
    name: str
    level_text: str
    max_level: bool
    button: ButtonState


@dataclass(frozen=True)
class TacticalBookState:
    position: int
    item_id: str
    genre: int
    tier: int
    exp_bonus: bool
    count: int
    selected: bool
    image: ImageState


DEFAULT_TARGETS: Tuple[SemanticTarget, ...] = (
    SemanticTarget(
        "login/enter",
        "LoginUI2(Clone)",
        "UICamera/Canvas/UIMain/LoginUI2(Clone)",
    ),
    SemanticTarget(
        "event-list/page/back",
        "back_btn",
        "ActivityMainUI(Clone)/adapt/blur_panel/adapt/top/back_btn",
    ),
    SemanticTarget("main/battle", "battle", "frame/right/1/battle"),
    SemanticTarget("main/formation", "formation", "frame/right/1/formation"),
    SemanticTarget("main/settings", "settings", "frame/top/btns/settings"),
    SemanticTarget("main/mail", "mail", "frame/top/btns/mail"),
    SemanticTarget("main/shop", "shop", "frame/bottom/frame/shop"),
    SemanticTarget("main/dock", "dock", "frame/bottom/frame/dock"),
    SemanticTarget("main/task", "task", "frame/bottom/frame/task"),
    SemanticTarget("main/build", "build", "frame/bottom/frame/build"),
    SemanticTarget("main/live", "live", "frame/bottom/frame/live"),
    SemanticTarget("main/tech", "tech", "frame/bottom/frame/tech"),
    SemanticTarget(
        "dorm-menu/page/root",
        "MainLiveAreaUI(Clone)",
        "Overlay/UIMain/MainLiveAreaUI(Clone)",
    ),
    SemanticTarget(
        "dorm-menu/academy",
        "school_btn",
        "MainLiveAreaUI(Clone)/school_btn",
    ),
    SemanticTarget(
        "dorm-menu/dorm",
        "backyard_btn",
        "MainLiveAreaUI(Clone)/backyard_btn",
    ),
    SemanticTarget(
        "dorm-menu/meowfficer",
        "commander_btn",
        "MainLiveAreaUI(Clone)/commander_btn",
    ),
    SemanticTarget(
        "dorm-menu/private-quarters",
        "dorm_btn",
        "MainLiveAreaUI(Clone)/dorm_btn",
    ),
    SemanticTarget(
        "dorm/page/back",
        "return",
        "CourtYardUI(Clone)/main/topPanel/btns/topleft/return",
    ),
    SemanticTarget(
        "dorm/page/manage",
        "decorate_btn",
        "CourtYardUI(Clone)/main/bottomPanel/bottomright/decorate_btn",
    ),
    SemanticTarget(
        "dorm/train",
        "train_btn",
        "CourtYardUI(Clone)/main/bottomPanel/bottomleft/train_btn",
    ),
    SemanticTarget(
        "dorm/feed",
        "feed_btn",
        "CourtYardUI(Clone)/main/bottomPanel/bottomleft/feed_btn",
    ),
    SemanticTarget(
        "dorm/collect",
        "onekey",
        "CourtYardUI(Clone)/main/rightPanel/onekey",
    ),
    SemanticTarget(
        "dorm/feed/close",
        "close",
        "BackYardFeedUI(Clone)/close",
    ),
    SemanticTarget(
        "dorm/feed/shop/cancel",
        "cancel_btn",
        "BackYardFeedUI(Clone)/BackYardFeedShopPanel(Clone)/frame/cancel_btn",
    ),
    SemanticTarget(
        "dorm/empty-food/cancel",
        "cancel_btn",
        "CourtYardEmptyFoodUI(Clone)/frame/cancel_btn",
    ),
    SemanticTarget(
        "dorm/statistics/confirm",
        "confirm_btn",
        "BackYardStatisticsUI(Clone)/painting/confirm_btn",
    ),
    SemanticTarget(
        "build/page/start",
        "start_btn",
        "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/start_btn",
    ),
    SemanticTarget(
        "build/warning/cancel",
        "custom_button_2(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_2(Clone)",
    ),
    SemanticTarget(
        "build/warning/confirm",
        "custom_button_1(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
    ),
    SemanticTarget(
        "build/prep/confirm",
        "confirm_btn",
        "BuildShipMsgBoxUI(Clone)/window/btns/confirm_btn",
    ),
    SemanticTarget(
        "build/prep/cancel",
        "cancel_btn",
        "BuildShipMsgBoxUI(Clone)/window/btns/cancel_btn",
    ),
    SemanticTarget(
        "build/prep/close",
        "close_btn",
        "BuildShipMsgBoxUI(Clone)/window/close_btn",
    ),
    SemanticTarget(
        "build/prep/minus",
        "minus",
        "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/minus",
    ),
    SemanticTarget(
        "build/prep/add",
        "add",
        "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/add",
    ),
    SemanticTarget(
        "build/prep/max",
        "max",
        "BuildShipMsgBoxUI(Clone)/window/content/max",
    ),
    SemanticTarget(
        "build/page/back",
        "back_btn",
        "Overlay/UIMain/blur_panel/adapt/top/back_btn",
    ),
    SemanticTarget(
        "campaign-menu/page/back",
        "back_button",
        "LevelMainScene(Clone)/top/top_chapter/back_button",
    ),
    SemanticTarget(
        "campaign-menu/normal",
        "enter_main",
        "LevelMainScene(Clone)/entrance/enters/enter_main",
    ),
    SemanticTarget(
        "campaign/map-preparation/proceed",
        "start_button",
        "LevelStageInfoView(Clone)/panel/start_button",
    ),
    SemanticTarget(
        "campaign/map-preparation/cancel",
        "btnBack",
        "LevelStageInfoView(Clone)/panel/btnBack",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/cancel",
        "btnBack",
        "LevelFleetSelectView(Clone)/panel/Fixed/btnBack",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/sortie",
        "start_button",
        "LevelFleetSelectView(Clone)/panel/Fixed/start_button",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/fleet/1/select",
        "btn_select",
        "LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/btn_select",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/fleet/1/clear",
        "btn_clear",
        "LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/btn_clear",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/fleet/2/select",
        "btn_select",
        "LevelFleetSelectView(Clone)/panel/ShipList/fleet/2/btn_select",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/fleet/2/clear",
        "btn_clear",
        "LevelFleetSelectView(Clone)/panel/ShipList/fleet/2/btn_clear",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/submarine/1/select",
        "btn_select",
        "LevelFleetSelectView(Clone)/panel/ShipList/sub/1/btn_select",
    ),
    SemanticTarget(
        "campaign/fleet-preparation/submarine/1/clear",
        "btn_clear",
        "LevelFleetSelectView(Clone)/panel/ShipList/sub/1/btn_clear",
    ),
    SemanticTarget(
        "research-menu/page/back",
        "back",
        "/SelectTechnologyUI(Clone)/blur_panel/adapt/top/back",
    ),
    SemanticTarget(
        "research-menu/research",
        "technology_btn",
        "/SelectTechnologyUI(Clone)/frame/bg/technology_btn",
    ),
    SemanticTarget(
        "research-menu/shipyard",
        "blueprint_btn",
        "/SelectTechnologyUI(Clone)/frame/bg/blueprint_btn",
    ),
    SemanticTarget(
        "research-menu/meta",
        "meta_btn",
        "/SelectTechnologyUI(Clone)/frame/bg/meta_btn",
    ),
    SemanticTarget(
        "research/page/back",
        "back",
        "/TechnologyUI(Clone)/blur_panel/adapt/top/back",
    ),
    SemanticTarget(
        "research/queue/enter",
        "btn_queue",
        "/TechnologyUI(Clone)/blur_panel/adapt/left/btn_queue",
    ),
    SemanticTarget(
        "research/queue/claim",
        "btn_award",
        "/TechnologyUI(Clone)/blur_panel/adapt/right/btn_award",
    ),
    SemanticTarget(
        "research/detail/root",
        "selecte_panel",
        "/TechnologyUI(Clone)/main/base_page/selecte_panel",
    ),
    SemanticTarget(
        "research/detail/start",
        "start_btn",
        "/TechnologyUI(Clone)/main/base_page/selecte_panel/technology_card/frame/btns/start_btn",
    ),
    SemanticTarget(
        "research/detail/stop",
        "stop_btn",
        "/TechnologyUI(Clone)/main/base_page/selecte_panel/technology_card/frame/btns/stop_btn",
    ),
    SemanticTarget(
        "research/detail/finish",
        "finish_btn",
        "/TechnologyUI(Clone)/main/base_page/selecte_panel/technology_card/frame/btns/finish_btn",
    ),
    SemanticTarget(
        "research/detail/queue",
        "join_btn",
        "/TechnologyUI(Clone)/main/base_page/selecte_panel/technology_card/frame/btns/join_btn",
    ),
    SemanticTarget(
        "tactical/page/back",
        "btnBack",
        "NewNavalTacticsUI(Clone)/adpter/frame/btnBack",
    ),
    SemanticTarget(
        "tactical/dock/back",
        "back",
        "Overlay/UIMain/blur_panel/adapt/top/back",
    ),
    SemanticTarget(
        "tactical/dock/confirm",
        "confirm_button",
        "Overlay/UIMain/blur_panel/select_panel/confirm_button",
    ),
    SemanticTarget(
        "tactical/dock/cancel",
        "cancel_button",
        "Overlay/UIMain/blur_panel/select_panel/cancel_button",
    ),
    SemanticTarget(
        "tactical/skill/confirm",
        "confirm_btn",
        "NewNavalTacticsSkillsPage(Clone)/frame/confirm_btn",
    ),
    SemanticTarget(
        "tactical/book/start",
        "confirm_btn",
        "NewNavalTacticsLessonPage(Clone)/confirm_btn",
    ),
    SemanticTarget(
        "tactical/book/cancel",
        "cancel_btn",
        "NewNavalTacticsLessonPage(Clone)/cancel_btn",
    ),
    SemanticTarget(
        "tactical/continue/cancel",
        "custom_button_2(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_2(Clone)",
    ),
    SemanticTarget(
        "tactical/course/cancel",
        "custom_button_2(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_2(Clone)",
    ),
    SemanticTarget(
        "tactical/course/confirm",
        "custom_button_1(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
    ),
    SemanticTarget(
        "research/start/cancel",
        "custom_button_2(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_2(Clone)",
    ),
    SemanticTarget(
        "research/start/confirm",
        "custom_button_1(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
    ),
    SemanticTarget(
        "research/queue/cancel",
        "custom_button_2(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_2(Clone)",
    ),
    SemanticTarget(
        "research/queue/confirm",
        "custom_button_1(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
    ),
    SemanticTarget(
        "overlay/network-reconnect/cancel",
        "custom_button_2(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_2(Clone)",
    ),
    SemanticTarget(
        "overlay/network-reconnect/confirm",
        "custom_button_1(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
    ),
    *tuple(
        SemanticTarget(
            "research/project/" + str(slot),
            str(unity_index),
            "TechnologyUI(Clone)/main/base_page/srcoll_rect/content/"
            + str(unity_index),
        )
        for slot, unity_index in ((1, 2), (2, 1), (3, 5), (4, 4), (5, 3))
    ),
    SemanticTarget("main/more", "extend", "frame/left/extend"),
    SemanticTarget(
        "reward/page/back",
        "CommissionInfoUI4Mellow(Clone)",
        "Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
    ),
    SemanticTarget(
        "reward/commission",
        "finish_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/event/frame/finish_btn",
    ),
    SemanticTarget(
        "reward/commission/finish",
        "finish_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/event/frame/finish_btn",
    ),
    SemanticTarget(
        "reward/commission/go",
        "go_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/event/frame/go_btn",
    ),
    SemanticTarget(
        "reward/tactical",
        "finish_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/class/frame/finish_btn",
    ),
    SemanticTarget(
        "reward/tactical/finish",
        "finish_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/class/frame/finish_btn",
    ),
    SemanticTarget(
        "reward/tactical/go",
        "go_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/class/frame/go_btn",
    ),
    SemanticTarget(
        "reward/research",
        "finish_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/technology/frame/finish_btn",
    ),
    SemanticTarget(
        "reward/research/finish",
        "finish_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/technology/frame/finish_btn",
    ),
    SemanticTarget(
        "reward/research/go",
        "go_btn",
        "CommissionInfoUI4Mellow(Clone)/frame/main/content/technology/frame/go_btn",
    ),
    SemanticTarget(
        "overlay/bulletin/close",
        "close_btn",
        "NewBulletinBoardUI(Clone)/bg/close_btn",
    ),
    SemanticTarget(
        "overlay/guild-message/close",
        "close",
        "GuildMsgBoxUI(Clone)/frame/close",
    ),
    SemanticTarget(
        "settings/back",
        "back_btn",
        "NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn",
    ),
    SemanticTarget(
        "task/page/back",
        "back_btn",
        "TaskScene(Clone)/blur_panel/adapt/top/back_btn",
    ),
    SemanticTarget(
        "task/claim/all",
        "GetAllButton",
        "TaskScene(Clone)/blur_panel/adapt/top/GetAllButton",
    ),
    SemanticTarget(
        "commission/page/back",
        "back_btn",
        "EventUI(Clone)/blur_panel/adapt/top/back_btn",
    ),
    SemanticTarget(
        "commission/detail/back",
        "back_btn",
        "Overlay/UIMain/blur_panel/adapt/top/back_btn",
    ),
    SemanticTarget(
        "commission/detail/recommend",
        "btn_recommend",
        "Overlay/UIMain/blur_panel/scrollItem/maskDetail/detailPanel/btn_recommend",
    ),
    SemanticTarget(
        "commission/detail/start",
        "btn",
        "Overlay/UIMain/blur_panel/scrollItem/maskDetail/detailPanel/btn",
    ),
    SemanticTarget(
        "mail/page/back",
        "back_btn",
        "MailUI(Clone)/adapt/CommonTitleAndBack/back_btn",
    ),
    SemanticTarget(
        "mail/manage",
        "btn_managerMail",
        "MailUI(Clone)/adapt/main/content/left/left_content/bottom/btn_managerMail",
    ),
    SemanticTarget(
        "mail/manage/back",
        "btnBack",
        "MailMgrMsgboxUI(Clone)/window/top/btnBack",
    ),
    SemanticTarget(
        "mail/manage/claim",
        "btn_get",
        "MailMgrMsgboxUI(Clone)/window/button_container/btn_get",
    ),
    SemanticTarget(
        "mail/manage/delete",
        "btn_delete",
        "MailMgrMsgboxUI(Clone)/window/button_container/btn_delete",
    ),
    SemanticTarget(
        "reward/award-info/close",
        "close",
        "AwardInfoUI(Clone)/items/close",
    ),
    SemanticTarget(
        "reward/award-info1/close",
        "close",
        "AwardInfoUI1(Clone)/items/close",
    ),
    SemanticTarget(
        "reward/ship-exp/close",
        "skipLayer",
        "ShipExpUI(Clone)/skipLayer",
    ),
)


DEFAULT_IMAGE_TARGETS: Tuple[SemanticImageTarget, ...] = tuple(
    SemanticImageTarget(
        "task/nav/" + semantic_name,
        "TaskScene(Clone)/blur_panel/adapt/left_length/frame/tagRoot/" + unity_name,
        selected_sprite,
        inactive_sprite,
    )
    for semantic_name, unity_name, selected_sprite, inactive_sprite in (
        ("all", "all", "icon_all_sel", "icon_all_unsel"),
        ("main", "scenario", "icon_main_sel", "icon_main_unsel"),
        ("side", "branch", "icon_brach_sel", "icon_brach_unsel"),
        ("daily", "routine", "icon_daily_sel", "icon_daily_unsel"),
        ("weekly", "weekly", "icon_week_sel", "icon_week_unsel"),
        ("event", "activity", "icon_activity_sel", "icon_activity_unsel"),
    )
) + (
    SemanticImageTarget(
        "commission/nav/daily",
        "EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
        "tagRoot/daily_btn",
        "toggle_meiri_sel 1",
        "toggle_meiri_unsel 1",
    ),
    SemanticImageTarget(
        "commission/nav/urgent",
        "EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
        "tagRoot/urgency_btn",
        "toggle_jinji_sel 1",
        "toggle_jinji_unsel 1",
    ),
)


DEFAULT_TOGGLE_TARGETS: Tuple[SemanticToggleTarget, ...] = (
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/1",
        "item1",
        "LevelFleetSelectView(Clone)/mask/list/item1",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/2",
        "item2",
        "LevelFleetSelectView(Clone)/mask/list/item2",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/3",
        "item3",
        "LevelFleetSelectView(Clone)/mask/list/item3",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/4",
        "item4",
        "LevelFleetSelectView(Clone)/mask/list/item4",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/5",
        "item5",
        "LevelFleetSelectView(Clone)/mask/list/item5",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/6",
        "item6",
        "LevelFleetSelectView(Clone)/mask/list/item6",
    ),
    SemanticToggleTarget(
        "build/nav/pools",
        "build_btn",
        "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/build_btn",
    ),
    SemanticToggleTarget(
        "build/nav/queue",
        "queue_btn",
        "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/queue_btn",
    ),
    SemanticToggleTarget(
        "build/nav/support",
        "support_btn",
        "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/support_btn",
    ),
    SemanticToggleTarget(
        "build/nav/unseam",
        "unseam_btn",
        "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/unseam_btn",
    ),
    SemanticToggleTarget(
        "build/pool/light",
        "frame",
        "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
        "toggles/light(Clone)/frame",
    ),
    SemanticToggleTarget(
        "build/pool/heavy",
        "frame",
        "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
        "toggles/heavy(Clone)/frame",
    ),
    SemanticToggleTarget(
        "build/pool/special",
        "frame",
        "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
        "toggles/special(Clone)/frame",
    ),
    SemanticToggleTarget(
        "mail/manage/all",
        "all",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/all",
    ),
    SemanticToggleTarget(
        "mail/manage/filter",
        "filter",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter",
    ),
    SemanticToggleTarget(
        "mail/manage/cube",
        "toggle_tpl",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl",
        "20001",
    ),
    SemanticToggleTarget(
        "mail/manage/coins",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "gold",
    ),
    SemanticToggleTarget(
        "mail/manage/oil",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "oil",
    ),
    SemanticToggleTarget(
        "mail/manage/merit",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "exploit",
    ),
    SemanticToggleTarget(
        "mail/manage/gems",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "gem",
    ),
)
DEFAULT_TEXT_TARGETS: Tuple[SemanticTextTarget, ...] = ()

_CAMPAIGN_FLEET_INPUT_TARGETS = tuple(
    "campaign/fleet-preparation/{0}".format(suffix)
    for suffix in (
        "fleet/1/select",
        "fleet/1/clear",
        "fleet/2/select",
        "fleet/2/clear",
        "submarine/1/select",
        "submarine/1/clear",
        "sortie",
        "option/1",
        "option/2",
        "option/3",
        "option/4",
        "option/5",
        "option/6",
    )
)


DEFAULT_BLOCKERS: Tuple[BlockerRule, ...] = (
    BlockerRule("loading", "/UIOverlay/Loading(Clone)"),
    BlockerRule(
        "bulletin",
        "/NewBulletinBoardUI(Clone)/",
        ("overlay/bulletin/close",),
    ),
    BlockerRule(
        "guild-message",
        "/GuildMsgBoxUI(Clone)/",
        ("overlay/guild-message/close",),
    ),
    BlockerRule(
        "award-info",
        "/AwardInfoUI(Clone)/",
        ("reward/award-info/close",),
    ),
    BlockerRule(
        "award-info1",
        "/AwardInfoUI1(Clone)/",
        ("reward/award-info1/close",),
    ),
    BlockerRule(
        "ship-exp",
        "/ShipExpUI(Clone)/",
        ("reward/ship-exp/close",),
    ),
    BlockerRule(
        "mail-manager",
        "/MailMgrMsgboxUI(Clone)/",
        (
            "mail/manage/back",
            "mail/manage/claim",
            "mail/manage/delete",
            "mail/manage/all",
            "mail/manage/filter",
            "mail/manage/cube",
            "mail/manage/coins",
            "mail/manage/oil",
            "mail/manage/merit",
            "mail/manage/gems",
        ),
    ),
    BlockerRule(
        "reward-page",
        "/CommissionInfoUI4Mellow(Clone)/",
        (
            "reward/page/back",
            "reward/commission",
            "reward/commission/finish",
            "reward/commission/go",
            "reward/tactical",
            "reward/tactical/finish",
            "reward/tactical/go",
            "reward/research",
            "reward/research/finish",
            "reward/research/go",
            "reward/award-info/close",
            "reward/award-info1/close",
            "reward/ship-exp/close",
        ),
    ),
    BlockerRule(
        "task-page",
        "/TaskScene(Clone)/",
        (
            "task/page/back",
            "task/claim/all",
            "task/nav/all",
            "task/nav/main",
            "task/nav/side",
            "task/nav/daily",
            "task/nav/weekly",
            "task/nav/event",
            "reward/award-info/close",
            "reward/award-info1/close",
        ),
    ),
    BlockerRule(
        "commission-page",
        "/EventUI(Clone)/",
        (
            "commission/page/back",
            "commission/nav/daily",
            "commission/nav/urgent",
            "commission/detail/back",
            "commission/detail/recommend",
            "commission/detail/start",
            "commission/scroll",
        ),
    ),
    BlockerRule(
        "commission-detail",
        "/Overlay/UIMain/blur_panel/scrollItem/maskDetail/detailPanel/",
        (
            "commission/detail/back",
            "commission/detail/recommend",
            "commission/detail/start",
        ),
    ),
    BlockerRule(
        "build-page",
        "/BuildShipUI(Clone)/",
        (
            "build/nav/pools",
            "build/nav/queue",
            "build/nav/support",
            "build/nav/unseam",
            "build/pool/light",
            "build/pool/heavy",
            "build/pool/special",
            "build/page/back",
            "build/page/start",
            "build/warning/cancel",
            "build/warning/confirm",
            "build/prep/confirm",
            "build/prep/cancel",
            "build/prep/close",
            "build/prep/minus",
            "build/prep/add",
            "build/prep/max",
        ),
    ),
    BlockerRule(
        "campaign-menu",
        "/LevelMainScene(Clone)/",
        (
            "campaign-menu/page/back",
            "campaign-menu/normal",
            "campaign/map-preparation/proceed",
            "campaign/map-preparation/cancel",
            "campaign/fleet-preparation/cancel",
            *_CAMPAIGN_FLEET_INPUT_TARGETS,
        ),
    ),
    BlockerRule(
        "campaign-map-preparation",
        "/LevelStageInfoView(Clone)/",
        (
            "campaign/map-preparation/proceed",
            "campaign/map-preparation/cancel",
        ),
    ),
    BlockerRule(
        "campaign-fleet-preparation",
        "/LevelFleetSelectView(Clone)/",
        (
            "campaign/fleet-preparation/cancel",
            *_CAMPAIGN_FLEET_INPUT_TARGETS,
        ),
    ),
    BlockerRule(
        "build-prep",
        "/BuildShipMsgBoxUI(Clone)/",
        (
            "build/prep/confirm",
            "build/prep/cancel",
            "build/prep/close",
            "build/prep/minus",
            "build/prep/add",
            "build/prep/max",
        ),
    ),
    BlockerRule(
        "dorm-menu",
        "/MainLiveAreaUI(Clone)/",
        (
            "dorm-menu/academy",
            "dorm-menu/dorm",
            "dorm-menu/meowfficer",
            "dorm-menu/private-quarters",
        ),
    ),
    BlockerRule(
        "dorm-statistics",
        "/BackYardStatisticsUI(Clone)/",
        ("dorm/statistics/confirm",),
    ),
    BlockerRule(
        "dorm-page",
        "/CourtYardUI(Clone)/",
        (
            "dorm/page/back",
            "dorm/page/manage",
            "dorm/train",
            "dorm/feed",
            "dorm/collect",
            "dorm/statistics/confirm",
            "dorm/feed/close",
            "dorm/feed/item/50001",
            "dorm/feed/item/50002",
            "dorm/feed/item/50003",
            "dorm/feed/item/50004",
            "dorm/feed/item/50005",
            "dorm/feed/item/50006",
            "dorm/feed/shop/cancel",
            "dorm/empty-food/cancel",
        ),
    ),
    BlockerRule(
        "dorm-empty-food",
        "/CourtYardEmptyFoodUI(Clone)/",
        ("dorm/empty-food/cancel",),
    ),
    BlockerRule(
        "dorm-feed-shop",
        "/BackYardFeedShopPanel(Clone)/",
        ("dorm/feed/shop/cancel",),
    ),
    BlockerRule(
        "dorm-feed",
        "/BackYardFeedUI(Clone)/",
        (
            "dorm/feed/close",
            "dorm/feed/item/50001",
            "dorm/feed/item/50002",
            "dorm/feed/item/50003",
            "dorm/feed/item/50004",
            "dorm/feed/item/50005",
            "dorm/feed/item/50006",
        ),
    ),
    BlockerRule(
        "research-menu",
        "/SelectTechnologyUI(Clone)/",
        (
            "research-menu/page/back",
            "research-menu/research",
            "research-menu/shipyard",
            "research-menu/meta",
        ),
    ),
    BlockerRule(
        "research-page",
        "/TechnologyUI(Clone)/",
        (
            "research/page/back",
            "research/project/1",
            "research/project/2",
            "research/project/3",
            "research/project/4",
            "research/project/5",
            "research/queue/enter",
            "research/queue/claim",
            "research/detail/root",
            "research/detail/start",
            "research/detail/stop",
            "research/detail/finish",
            "research/detail/queue",
            "reward/award-info/close",
            "reward/award-info1/close",
            "research/start/cancel",
            "research/start/confirm",
            "research/queue/cancel",
            "research/queue/confirm",
        ),
    ),
    BlockerRule(
        "tactical-continue",
        "/Msgbox(Clone)/",
        (
            "tactical/continue/cancel",
            "tactical/course/cancel",
            "tactical/course/confirm",
            "research/start/cancel",
            "research/start/confirm",
            "research/queue/cancel",
            "research/queue/confirm",
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
            "build/warning/cancel",
            "build/warning/confirm",
        ),
    ),
    BlockerRule(
        "tactical-dock",
        "/DockyardUI(Clone)/",
        (
            "tactical/dock/back",
            "tactical/dock/confirm",
            "tactical/dock/cancel",
            "tactical/dock/ship",
            "tactical/skill/item",
            "tactical/skill/confirm",
        ),
    ),
    BlockerRule(
        "tactical-skill",
        "/NewNavalTacticsSkillsPage(Clone)/",
        (
            "tactical/skill/item",
            "tactical/skill/confirm",
        ),
    ),
    BlockerRule(
        "tactical-book",
        "/NewNavalTacticsLessonPage(Clone)/",
        (
            "tactical/book/item",
            "tactical/book/start",
            "tactical/book/cancel",
            "tactical/course/cancel",
            "tactical/course/confirm",
        ),
    ),
    BlockerRule(
        "tactical-page",
        "/NewNavalTacticsUI(Clone)/",
        (
            "tactical/page/back",
            "tactical/continue/cancel",
            "tactical/course/cancel",
            "tactical/course/confirm",
            "tactical/slot/1",
            "tactical/slot/2",
            "tactical/slot/3",
            "tactical/slot/4",
            "tactical/dock/back",
            "tactical/dock/confirm",
            "tactical/dock/cancel",
            "tactical/dock/ship",
            "tactical/skill/item",
            "tactical/skill/confirm",
            "tactical/book/item",
            "tactical/book/start",
            "tactical/book/cancel",
        ),
    ),
)


class TcpObserverTransport:
    """One-request-per-connection client for an ADB-forwarded observer socket."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 3.0,
        maximum_response_bytes: int = 1024 * 1024,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._maximum_response_bytes = maximum_response_bytes

    def request(self, request_line: str) -> Mapping[str, Any]:
        if request_line not in (
            "GET /v1/snapshot\n",
            "GET /v1/buttons\n",
            "GET /v1/ui\n",
        ):
            raise ObserverTransportError("client refused an unsupported observer request")
        try:
            with socket.create_connection(
                (self._host, self._port), self._timeout_seconds
            ) as client:
                client.settimeout(self._timeout_seconds)
                client.sendall(request_line.encode("ascii"))
                chunks = bytearray()
                while True:
                    chunk = client.recv(8192)
                    if not chunk:
                        break
                    chunks.extend(chunk)
                    if len(chunks) > self._maximum_response_bytes:
                        raise ObserverTransportError("observer response exceeded size limit")
                    if b"\n" in chunk:
                        break
        except (OSError, TimeoutError) as exc:
            raise ObserverTransportError("observer socket request failed") from exc

        line = bytes(chunks).split(b"\n", 1)[0]
        if not line:
            raise ObserverTransportError("observer returned an empty response")
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ObserverTransportError("observer returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ObserverTransportError("observer response is not a JSON object")
        return value


class AdbObserverBridge:
    """ADB forwarding, foreground inspection, and tap injection for one game PID."""

    _FOREGROUND_PATTERN = re.compile(
        r"topResumedActivity=.*?\bu\d+\s+([^\s}]+/[^\s}]+)"
    )
    _DEVICE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9_./:+@=~-]+$")
    _SHA256_PATTERN = re.compile(r"^([0-9a-fA-F]{64})(?:\s|$)")

    def __init__(
        self,
        serial: str,
        package: str,
        adb: str = "adb",
        command_timeout_seconds: float = 10.0,
    ) -> None:
        self.serial = serial
        self.package = package
        self.adb = adb
        self.command_timeout_seconds = command_timeout_seconds
        self.pid: Optional[int] = None
        self.port: Optional[int] = None
        self.transport: Optional[TcpObserverTransport] = None

    def _run(
        self,
        arguments: Sequence[str],
        timeout_seconds: Optional[float] = None,
    ) -> str:
        timeout = (
            self.command_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        try:
            completed = subprocess.run(
                [self.adb, "-s", self.serial, *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ObserverTransportError("ADB command failed") from exc
        return completed.stdout.strip()

    def open(self) -> "AdbObserverBridge":
        if self.transport is not None:
            return self
        if self._run(("get-state",)) != "device":
            raise ObserverTransportError("ADB device is not ready")
        pid_text = self._run(("shell", "pidof", self.package))
        if not pid_text.isdigit():
            raise ObserverTransportError("expected exactly one numeric game PID")
        self.pid = int(pid_text)
        port_text = self._run(
            (
                "forward",
                "tcp:0",
                "localabstract:alas.g3.{0}".format(self.pid),
            )
        )
        if not port_text.isdigit():
            raise ObserverTransportError("ADB did not return a forwarding port")
        self.port = int(port_text)
        self.transport = TcpObserverTransport("127.0.0.1", self.port)
        return self

    def close(self) -> None:
        if self.port is not None:
            try:
                self._run(("forward", "--remove", "tcp:{0}".format(self.port)))
            finally:
                self.transport = None
                self.port = None

    def __enter__(self) -> "AdbObserverBridge":
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def request(self, request_line: str) -> Mapping[str, Any]:
        if self.transport is None:
            raise ObserverTransportError("ADB observer bridge is not open")
        return self.transport.request(request_line)

    def foreground_component(self) -> str:
        output = self._run(("shell", "dumpsys", "activity", "activities"))
        match = self._FOREGROUND_PATTERN.search(output)
        return match.group(1) if match else ""

    def tap(self, x: int, y: int) -> None:
        self._run(("shell", "input", "tap", str(x), str(y)))

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int,
    ) -> None:
        self._run(
            (
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration_ms),
            )
        )

    @classmethod
    def _device_path(cls, value: str, field: str) -> str:
        path = value.strip()
        if not cls._DEVICE_PATH_PATTERN.fullmatch(path):
            raise SemanticGateClosed("unsafe or malformed device path: {0}".format(field))
        return path

    def _device_sha256(self, path: str) -> str:
        safe_path = self._device_path(path, "sha256 target")
        # The pinned base APK is large enough that hashing it on an emulator can
        # legitimately exceed the normal short ADB command timeout.
        output = self._run(("shell", "sha256sum", safe_path), timeout_seconds=120.0)
        match = self._SHA256_PATTERN.match(output)
        if match is None:
            raise SemanticGateClosed("device sha256 output is malformed")
        return match.group(1).lower()

    def package_fingerprint(self) -> AndroidPackageFingerprint:
        """Read the installed game identity without trusting observer output."""

        package_dump = self._run(("shell", "dumpsys", "package", self.package))
        version_code_match = re.search(r"\bversionCode=(\d+)", package_dump)
        version_name_match = re.search(r"\bversionName=([^\r\n]+)", package_dump)
        primary_abi_match = re.search(r"\bprimaryCpuAbi=([^\r\n]+)", package_dump)
        native_dir_match = re.search(
            r"\b(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\r\n]+)",
            package_dump,
        )
        if not all(
            (
                version_code_match,
                version_name_match,
                primary_abi_match,
                native_dir_match,
            )
        ):
            raise SemanticGateClosed("installed package identity is incomplete")

        base_output = self._run(("shell", "pm", "path", self.package))
        base_paths = [
            line[len("package:") :]
            for line in base_output.splitlines()
            if line.startswith("package:")
        ]
        if len(base_paths) != 1:
            raise SemanticGateClosed("expected exactly one base APK path")
        base_path = self._device_path(base_paths[0], "base APK")
        native_dir = self._device_path(native_dir_match.group(1), "nativeLibraryDir")
        il2cpp_output = self._run(
            (
                "shell",
                "find",
                native_dir,
                "-type",
                "f",
                "-name",
                "libil2cpp.so",
                "-print",
            )
        )
        il2cpp_paths = [line.strip() for line in il2cpp_output.splitlines() if line.strip()]
        if len(il2cpp_paths) != 1:
            raise SemanticGateClosed("expected exactly one libil2cpp.so")
        il2cpp_path = self._device_path(il2cpp_paths[0], "libil2cpp.so")

        return AndroidPackageFingerprint(
            version_name=version_name_match.group(1).strip(),
            version_code=int(version_code_match.group(1)),
            primary_abi=primary_abi_match.group(1).strip(),
            base_apk_sha256=self._device_sha256(base_path),
            il2cpp_sha256=self._device_sha256(il2cpp_path),
        )

    def require_package_fingerprint(
        self, expected: AndroidPackageFingerprint
    ) -> AndroidPackageFingerprint:
        actual = self.package_fingerprint()
        if actual != expected:
            raise SemanticGateClosed("installed package fingerprint is not allowlisted")
        return actual


class SemanticOracle:
    """Mapped semantic observation and input with fail-closed action gates."""

    def __init__(
        self,
        request: Callable[[str], Mapping[str, Any]],
        foreground_component: Callable[[], str],
        tap: Callable[[int, int], None],
        fingerprint: OracleFingerprint,
        targets: Iterable[SemanticTarget] = DEFAULT_TARGETS,
        image_targets: Iterable[SemanticImageTarget] = DEFAULT_IMAGE_TARGETS,
        toggle_targets: Iterable[SemanticToggleTarget] = DEFAULT_TOGGLE_TARGETS,
        text_targets: Iterable[SemanticTextTarget] = DEFAULT_TEXT_TARGETS,
        blockers: Iterable[BlockerRule] = DEFAULT_BLOCKERS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        swipe: Optional[Callable[[int, int, int, int, int], None]] = None,
    ) -> None:
        self._request = request
        self._foreground_component = foreground_component
        self._tap = tap
        self.fingerprint = fingerprint
        self._targets = self._index_targets(targets)
        self._image_targets = self._index_image_targets(image_targets)
        self._toggle_targets = self._index_toggle_targets(toggle_targets)
        self._text_targets = self._index_text_targets(text_targets)
        self._blockers = tuple(blockers)
        self._monotonic = monotonic
        self._sleep = sleep
        self._swipe = swipe
        self._last_generation: Optional[int] = None

    def _retry_transition_read(
        self,
        reader: Callable[[], Any],
        *,
        attempts: int = 4,
        interval_seconds: float = 0.25,
    ) -> Any:
        """Retry a read-only typed view while a Unity transition settles.

        A generation can briefly expose a newly active Button tree before all
        Images on that page have settled. Retrying the complete typed read does
        not relax a gate: the final attempt must still satisfy every original
        exactness check. The helper never injects input, and callers that act
        re-read the actionable Button immediately before the tap.
        """

        if attempts < 1:
            raise ValueError("transition read attempts must be positive")
        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(attempts):
            try:
                return reader()
            except SemanticGateClosed as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    self._sleep(interval_seconds)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _index_targets(
        targets: Iterable[SemanticTarget],
    ) -> Dict[str, SemanticTarget]:
        indexed: Dict[str, SemanticTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError("duplicate semantic target id: {0}".format(target.semantic_id))
            if not target.name or not target.path_suffix:
                raise ValueError("semantic target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _index_image_targets(
        targets: Iterable[SemanticImageTarget],
    ) -> Dict[str, SemanticImageTarget]:
        indexed: Dict[str, SemanticImageTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError(
                    "duplicate semantic image target id: {0}".format(
                        target.semantic_id
                    )
                )
            if (
                not target.path_parent_suffix
                or not target.selected_sprite
                or not target.inactive_sprite
            ):
                raise ValueError("semantic image target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _index_toggle_targets(
        targets: Iterable[SemanticToggleTarget],
    ) -> Dict[str, SemanticToggleTarget]:
        indexed: Dict[str, SemanticToggleTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError(
                    "duplicate semantic toggle target id: {0}".format(
                        target.semantic_id
                    )
                )
            if not target.semantic_id or not target.name or not target.path_suffix:
                raise ValueError("semantic toggle target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _index_text_targets(
        targets: Iterable[SemanticTextTarget],
    ) -> Dict[str, SemanticTextTarget]:
        indexed: Dict[str, SemanticTextTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError(
                    "duplicate semantic text target id: {0}".format(
                        target.semantic_id
                    )
                )
            if (
                not target.semantic_id
                or not target.path_suffix
                or not target.expected_texts
                or any(not value for value in target.expected_texts)
            ):
                raise ValueError("semantic text target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _integer(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SemanticGateClosed("invalid integer field: {0}".format(field))
        return value

    @staticmethod
    def _finite_number(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SemanticGateClosed("invalid numeric field: {0}".format(field))
        result = float(value)
        if not math.isfinite(result):
            raise SemanticGateClosed("non-finite numeric field: {0}".format(field))
        return result

    def _validate_identity(
        self,
        value: Mapping[str, Any],
        semantic_schema: Optional[str] = None,
    ) -> None:
        if value.get("protocol_schema") != OBSERVER_SCHEMA:
            raise SemanticGateClosed("observer protocol schema mismatch")
        if semantic_schema is not None and value.get("semantic_schema") != semantic_schema:
            raise SemanticGateClosed("semantic schema mismatch")
        if value.get("status") != "ok":
            raise SemanticGateClosed("observer status is not ok")
        if value.get("package") != self.fingerprint.package:
            raise SemanticGateClosed("observer package mismatch")
        if value.get("driver_revision") != self.fingerprint.driver_revision:
            raise SemanticGateClosed("observer driver revision mismatch")
        if self._integer(value.get("peer_uid"), "peer_uid") != self.fingerprint.peer_uid:
            raise SemanticGateClosed("observer peer credential mismatch")
        if self.fingerprint.expected_pid is not None and self._integer(
            value.get("pid"), "pid"
        ) != self.fingerprint.expected_pid:
            raise SemanticGateClosed("observer PID mismatch")
        if self._integer(value.get("age_ms"), "age_ms") > self.fingerprint.max_age_ms:
            raise SemanticGateClosed("observer snapshot is stale")

    def _parse_button(self, raw: Any) -> ButtonState:
        if not isinstance(raw, dict):
            raise SemanticGateClosed("button record is not an object")
        name = raw.get("name")
        path = raw.get("path")
        if not isinstance(name, str) or not isinstance(path, str) or not name or not path:
            raise SemanticGateClosed("button identity is incomplete")

        point_value = raw.get("adb_point")
        bounds_value = raw.get("adb_bounds")
        point = None
        bounds = None
        if point_value is not None:
            if not isinstance(point_value, dict):
                raise SemanticGateClosed("button point is malformed")
            point = Point(
                self._finite_number(point_value.get("x"), "adb_point.x"),
                self._finite_number(point_value.get("y"), "adb_point.y"),
            )
        if bounds_value is not None:
            if not isinstance(bounds_value, dict):
                raise SemanticGateClosed("button bounds are malformed")
            candidate_bounds = Bounds(
                self._finite_number(bounds_value.get("left"), "adb_bounds.left"),
                self._finite_number(bounds_value.get("top"), "adb_bounds.top"),
                self._finite_number(bounds_value.get("right"), "adb_bounds.right"),
                self._finite_number(bounds_value.get("bottom"), "adb_bounds.bottom"),
            )
            # Some active Unity Buttons are layout sentinels with a zero-area
            # RectTransform. They remain observable but are never actionable.
            if (
                candidate_bounds.left < candidate_bounds.right
                and candidate_bounds.top < candidate_bounds.bottom
            ):
                bounds = candidate_bounds
        raycast_top = raw.get("raycast_top")
        if raycast_top is not None and not isinstance(raycast_top, bool):
            raise SemanticGateClosed("button raycast state is malformed")
        return ButtonState(
            name=name,
            path=path,
            active_in_hierarchy=raw.get("active_in_hierarchy") is True,
            active_and_enabled=raw.get("active_and_enabled") is True,
            interactable=raw.get("interactable") is True,
            raycast_top=raycast_top,
            point=point,
            bounds=bounds,
            raw=raw,
        )

    def _parse_toggle(self, raw: Any) -> ToggleState:
        button = self._parse_button(raw)
        checked = raw.get("checked") if isinstance(raw, dict) else None
        if not isinstance(checked, bool):
            raise SemanticGateClosed("toggle state is malformed")
        return ToggleState(
            name=button.name,
            path=button.path,
            active_in_hierarchy=button.active_in_hierarchy,
            active_and_enabled=button.active_and_enabled,
            interactable=button.interactable,
            checked=checked,
            raycast_top=button.raycast_top,
            point=button.point,
            bounds=button.bounds,
            raw=raw,
        )

    def _parse_text(self, raw: Any) -> TextState:
        if not isinstance(raw, dict):
            raise SemanticGateClosed("text record is not an object")
        kind = raw.get("kind")
        name = raw.get("name")
        path = raw.get("path")
        value = raw.get("text")
        if kind not in ("ugui-text", "tmp-text"):
            raise SemanticGateClosed("text kind is not supported")
        if (
            not isinstance(name, str)
            or not isinstance(path, str)
            or not isinstance(value, str)
            or not name
            or not path
        ):
            raise SemanticGateClosed("text identity is incomplete")
        flags = self._integer(raw.get("flags"), "text flags")
        bounds_value = raw.get("adb_bounds")
        bounds = None
        if bounds_value is not None:
            if not isinstance(bounds_value, dict):
                raise SemanticGateClosed("text bounds are malformed")
            candidate = Bounds(
                self._finite_number(bounds_value.get("left"), "text bounds.left"),
                self._finite_number(bounds_value.get("top"), "text bounds.top"),
                self._finite_number(bounds_value.get("right"), "text bounds.right"),
                self._finite_number(bounds_value.get("bottom"), "text bounds.bottom"),
            )
            if candidate.left < candidate.right and candidate.top < candidate.bottom:
                bounds = candidate
        return TextState(
            kind=kind,
            name=name,
            path=path,
            text=value,
            active_in_hierarchy=raw.get("active_in_hierarchy") is True,
            active_and_enabled=raw.get("active_and_enabled") is True,
            truncated=bool(flags & 0x10),
            bounds=bounds,
            raw=raw,
        )

    def _parse_image(self, raw: Any) -> ImageState:
        if not isinstance(raw, dict) or raw.get("kind") != "image":
            raise SemanticGateClosed("image record is not supported")
        name = raw.get("name")
        path = raw.get("path")
        sprite = raw.get("sprite")
        if (
            not isinstance(name, str)
            or not isinstance(path, str)
            or not isinstance(sprite, str)
            or not name
            or not path
        ):
            raise SemanticGateClosed("image identity is incomplete")
        raycast_target = raw.get("raycast_target")
        raycast_top = raw.get("raycast_top")
        color_value = raw.get("color")
        if (
            not isinstance(raycast_target, bool)
            or (raycast_top is not None and not isinstance(raycast_top, bool))
            or not isinstance(color_value, dict)
        ):
            raise SemanticGateClosed("image state is malformed")
        color = tuple(
            self._finite_number(color_value.get(channel), "image color." + channel)
            for channel in ("red", "green", "blue", "alpha")
        )
        bounds_value = raw.get("adb_bounds")
        bounds = None
        if bounds_value is not None:
            if not isinstance(bounds_value, dict):
                raise SemanticGateClosed("image bounds are malformed")
            candidate = Bounds(
                self._finite_number(bounds_value.get("left"), "image bounds.left"),
                self._finite_number(bounds_value.get("top"), "image bounds.top"),
                self._finite_number(bounds_value.get("right"), "image bounds.right"),
                self._finite_number(bounds_value.get("bottom"), "image bounds.bottom"),
            )
            if candidate.left < candidate.right and candidate.top < candidate.bottom:
                bounds = candidate
        flags = self._integer(raw.get("flags"), "image flags")
        return ImageState(
            name=name,
            path=path,
            sprite=sprite,
            active_in_hierarchy=raw.get("active_in_hierarchy") is True,
            active_and_enabled=raw.get("active_and_enabled") is True,
            raycast_target=raycast_target,
            raycast_top=raycast_top,
            color=color,
            fill_amount=self._finite_number(raw.get("fill_amount"), "fill_amount"),
            truncated=bool(flags & 0x10),
            bounds=bounds,
            raw=raw,
        )

    def read_state(self) -> OracleState:
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity is not top-resumed")
        snapshot = self._request("GET /v1/snapshot\n")
        buttons_snapshot = self._request("GET /v1/buttons\n")
        if not isinstance(snapshot, dict) or not isinstance(buttons_snapshot, dict):
            raise ObserverTransportError("observer response is not a mapping")
        self._validate_identity(snapshot)
        self._validate_identity(buttons_snapshot, BUTTON_SCHEMA)

        if snapshot.get("snapshot_schema") != 1 or buttons_snapshot.get("schema") != 1:
            raise SemanticGateClosed("observer snapshot schema mismatch")
        if (
            snapshot.get("main_thread") is not True
            or self._integer(snapshot.get("flags"), "flags") != 15
            or self._integer(snapshot.get("ui_stage"), "ui_stage") != 100
            or self._integer(snapshot.get("ui_method_mask"), "ui_method_mask") != 15
        ):
            raise SemanticGateClosed("typed main-thread UI probe is incomplete")
        if (
            self._integer(snapshot.get("width"), "width") != self.fingerprint.width
            or self._integer(snapshot.get("height"), "height") != self.fingerprint.height
        ):
            raise SemanticGateClosed("logical screen size mismatch")
        if snapshot.get("pid") != buttons_snapshot.get("pid"):
            raise SemanticGateClosed("observer endpoints disagree on PID")

        generation = self._integer(snapshot.get("generation"), "generation")
        button_generation = self._integer(
            buttons_snapshot.get("generation"), "button generation"
        )
        if button_generation < generation or button_generation > generation + 2:
            raise SemanticGateClosed("observer endpoints are not generation-coherent")
        if self._last_generation is not None and generation < self._last_generation:
            raise SemanticGateClosed("observer generation moved backwards")
        self._last_generation = generation

        if buttons_snapshot.get("truncated") is not False:
            raise SemanticGateClosed("button snapshot is truncated")
        if self._integer(buttons_snapshot.get("error_count"), "error_count") != 0:
            raise SemanticGateClosed("button snapshot contains extraction errors")
        raw_buttons = buttons_snapshot.get("buttons")
        if not isinstance(raw_buttons, list):
            raise SemanticGateClosed("button list is malformed")
        if self._integer(buttons_snapshot.get("button_count"), "button_count") != len(
            raw_buttons
        ):
            raise SemanticGateClosed("button count does not match the record list")
        buttons = tuple(self._parse_button(raw) for raw in raw_buttons)
        return OracleState(
            generation=button_generation,
            scene_handle=self._integer(snapshot.get("scene_handle"), "scene_handle"),
            snapshot=snapshot,
            buttons_snapshot=buttons_snapshot,
            buttons=buttons,
        )

    def read_ui_state(self) -> UiState:
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity is not top-resumed")
        ui_snapshot = self._request("GET /v1/ui\n")
        if not isinstance(ui_snapshot, dict):
            raise ObserverTransportError("UI observer response is not a mapping")
        self._validate_identity(ui_snapshot, UI_SCHEMA)
        if ui_snapshot.get("schema") != 1:
            raise SemanticGateClosed("UI snapshot schema mismatch")
        if ui_snapshot.get("toggle_truncated") is not False:
            raise SemanticGateClosed("toggle snapshot is truncated")
        if ui_snapshot.get("text_truncated") is not False:
            raise SemanticGateClosed("text snapshot is truncated")
        if self._integer(ui_snapshot.get("error_count"), "UI error_count") != 0:
            raise SemanticGateClosed("UI snapshot contains extraction errors")

        image_truncated = ui_snapshot.get("image_truncated")
        if not isinstance(image_truncated, bool):
            raise SemanticGateClosed("image truncation state is malformed")
        raw_toggles = ui_snapshot.get("toggles")
        raw_texts = ui_snapshot.get("texts")
        raw_images = ui_snapshot.get("images")
        if (
            not isinstance(raw_toggles, list)
            or not isinstance(raw_texts, list)
            or not isinstance(raw_images, list)
        ):
            raise SemanticGateClosed("UI record lists are malformed")
        if self._integer(ui_snapshot.get("toggle_count"), "toggle_count") != len(
            raw_toggles
        ):
            raise SemanticGateClosed("toggle count does not match the record list")
        if self._integer(ui_snapshot.get("text_count"), "text_count") != len(raw_texts):
            raise SemanticGateClosed("text count does not match the record list")
        if self._integer(ui_snapshot.get("image_count"), "image_count") != len(
            raw_images
        ):
            raise SemanticGateClosed("image count does not match the record list")
        method_mask = self._integer(ui_snapshot.get("method_mask"), "UI method_mask")
        skipped_count = self._integer(
            ui_snapshot.get("skipped_count"), "UI skipped_count"
        )
        if skipped_count < 0:
            raise SemanticGateClosed("UI skipped_count is negative")
        if method_mask & 0x6 == 0:
            raise SemanticGateClosed("no typed Unity text accessor is available")
        generation = self._integer(ui_snapshot.get("generation"), "UI generation")
        if self._last_generation is not None and generation < self._last_generation:
            raise SemanticGateClosed("observer generation moved backwards")
        self._last_generation = generation
        return UiState(
            generation=generation,
            method_mask=method_mask,
            skipped_count=skipped_count,
            image_truncated=image_truncated,
            snapshot=ui_snapshot,
            toggles=tuple(self._parse_toggle(raw) for raw in raw_toggles),
            texts=tuple(self._parse_text(raw) for raw in raw_texts),
            images=tuple(self._parse_image(raw) for raw in raw_images),
        )

    def read_text_state(self) -> UiState:
        """Read a complete text slice while ignoring unrelated UI-type caps."""

        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity is not top-resumed")
        ui_snapshot = self._request("GET /v1/ui\n")
        if not isinstance(ui_snapshot, dict):
            raise ObserverTransportError("UI observer response is not a mapping")
        self._validate_identity(ui_snapshot, UI_SCHEMA)
        if ui_snapshot.get("schema") != 1:
            raise SemanticGateClosed("UI snapshot schema mismatch")
        if ui_snapshot.get("text_truncated") is not False:
            raise SemanticGateClosed("text snapshot is truncated")
        if self._integer(ui_snapshot.get("error_count"), "UI error_count") != 0:
            raise SemanticGateClosed("UI snapshot contains extraction errors")
        raw_texts = ui_snapshot.get("texts")
        if not isinstance(raw_texts, list) or self._integer(
            ui_snapshot.get("text_count"), "text_count"
        ) != len(raw_texts):
            raise SemanticGateClosed("text record list is malformed")
        method_mask = self._integer(ui_snapshot.get("method_mask"), "UI method_mask")
        if method_mask & 0x6 == 0:
            raise SemanticGateClosed("no typed Unity text accessor is available")
        generation = self._integer(ui_snapshot.get("generation"), "UI generation")
        if self._last_generation is not None and generation < self._last_generation:
            raise SemanticGateClosed("observer generation moved backwards")
        self._last_generation = generation
        skipped_count = self._integer(
            ui_snapshot.get("skipped_count"), "UI skipped_count"
        )
        if skipped_count < 0:
            raise SemanticGateClosed("UI skipped_count is negative")
        return UiState(
            generation=generation,
            method_mask=method_mask,
            skipped_count=skipped_count,
            image_truncated=bool(ui_snapshot.get("image_truncated")),
            snapshot=ui_snapshot,
            toggles=(),
            texts=tuple(self._parse_text(raw) for raw in raw_texts),
            images=(),
        )

    @staticmethod
    def _bounds_overlap(left: Bounds, right: Bounds) -> float:
        width = max(0.0, min(left.right, right.right) - max(left.left, right.left))
        height = max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
        return width * height

    def texts_in_bounds(
        self,
        bounds: Bounds,
        minimum_overlap_ratio: float = 0.5,
    ) -> Tuple[TextState, ...]:
        if not 0.0 < minimum_overlap_ratio <= 1.0:
            raise ValueError("text overlap ratio must be in (0, 1]")
        state = self.read_ui_state()
        return self._texts_in_state_bounds(state, bounds, minimum_overlap_ratio)

    def _texts_in_state_bounds(
        self,
        state: UiState,
        bounds: Bounds,
        minimum_overlap_ratio: float,
    ) -> Tuple[TextState, ...]:
        matches = []
        for text_state in state.texts:
            text_bounds = text_state.bounds
            if (
                not text_state.active_in_hierarchy
                or not text_state.active_and_enabled
                or text_bounds is None
            ):
                continue
            text_area = (text_bounds.right - text_bounds.left) * (
                text_bounds.bottom - text_bounds.top
            )
            if text_area <= 0:
                continue
            overlap = self._bounds_overlap(bounds, text_bounds)
            if overlap / text_area >= minimum_overlap_ratio:
                matches.append(text_state)
        matches.sort(
            key=lambda item: (
                item.bounds.top if item.bounds is not None else math.inf,
                item.bounds.left if item.bounds is not None else math.inf,
                item.path,
            )
        )
        return tuple(matches)

    def text_groups_in_bounds(
        self,
        bounds: Iterable[Bounds],
        minimum_overlap_ratio: float = 0.5,
    ) -> Tuple[Tuple[TextState, ...], ...]:
        if not 0.0 < minimum_overlap_ratio <= 1.0:
            raise ValueError("text overlap ratio must be in (0, 1]")
        state = self.read_ui_state()
        return tuple(
            self._texts_in_state_bounds(state, area, minimum_overlap_ratio)
            for area in bounds
        )

    def text_state(self, semantic_id: str) -> TextState:
        try:
            target = self._text_targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic text target is not mapped: {0}".format(semantic_id)
            ) from exc
        state = self.read_ui_state()
        matches = tuple(
            item
            for item in state.texts
            if item.path.endswith(target.path_suffix)
            and item.text in target.expected_texts
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic text target is absent or ambiguous: {0}".format(
                    semantic_id
                )
            )
        item = matches[0]
        if (
            item.truncated
            or not item.active_in_hierarchy
            or not item.active_and_enabled
            or item.bounds is None
        ):
            raise SemanticGateClosed("semantic text target is incomplete")
        return item

    def text_exists(self, semantic_id: str) -> bool:
        try:
            self.text_state(semantic_id)
        except SemanticGateClosed:
            return False
        return True

    def indexed_text_groups(self, path_prefix: str) -> Tuple[IndexedTextGroup, ...]:
        """Group live text below exact ``path_prefix/<numeric-index>`` nodes."""

        if not path_prefix or path_prefix.endswith("/"):
            raise ValueError("indexed text path prefix must be non-empty and normalized")
        state = self.read_ui_state()
        pattern = re.compile(
            r"(?:^|/)" + re.escape(path_prefix) + r"/([0-9]+)(?:/|$)"
        )
        groups: Dict[int, List[TextState]] = {}
        roots: Dict[int, str] = {}
        for item in state.texts:
            if (
                item.truncated
                or not item.active_in_hierarchy
                or not item.active_and_enabled
                or item.bounds is None
            ):
                continue
            match = pattern.search(item.path)
            if match is None:
                continue
            index = int(match.group(1))
            root_end = match.end(1)
            root = item.path[:root_end]
            if index in roots and roots[index] != root:
                raise SemanticGateClosed(
                    "indexed text group root is ambiguous: {0}".format(index)
                )
            roots[index] = root
            groups.setdefault(index, []).append(item)
        result = []
        for index in sorted(groups):
            values = sorted(
                groups[index],
                key=lambda item: (
                    item.bounds.top if item.bounds is not None else math.inf,
                    item.bounds.left if item.bounds is not None else math.inf,
                    item.path,
                ),
            )
            result.append(IndexedTextGroup(index, roots[index], tuple(values)))
        return tuple(result)

    @staticmethod
    def parse_countdown_seconds(value: str) -> int:
        """Parse a strict ``MM:SS`` or ``HH:MM:SS`` typed Unity countdown."""

        if not isinstance(value, str):
            raise SemanticGateClosed("countdown text is not a string")
        match = re.fullmatch(r"(?:(\d{1,3}):)?([0-5]\d):([0-5]\d)", value.strip())
        if match is None:
            raise SemanticGateClosed("typed countdown has an unsupported format")
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        return hours * 3600 + minutes * 60 + seconds

    def mail_count(self) -> Tuple[int, int]:
        """Return the explicit ``used/capacity`` marker from the pinned mail page."""

        button_state = self.read_state()
        page_back = self._unique(button_state, "mail/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "mail/page/back"
        ):
            raise SemanticGateClosed("mail page identity is not safely actionable")

        ui_state = self.read_text_state()
        suffix = (
            "MailUI(Clone)/adapt/main/content/left/left_content/top/count"
        )
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.name == "count"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("mail count marker is absent or ambiguous")
        plain = re.sub(r"<[^>]*>", "", matches[0].text).strip()
        count_match = re.fullmatch(r"(\d{1,3})/(\d{1,3})", plain)
        if count_match is None:
            raise SemanticGateClosed("mail count marker is malformed")
        used = int(count_match.group(1))
        capacity = int(count_match.group(2))
        if capacity <= 0 or used > capacity:
            raise SemanticGateClosed("mail count marker is inconsistent")
        return used, capacity

    def mail_is_empty(self) -> bool:
        """Classify empty mail only from the explicit typed counter."""

        used, _ = self.mail_count()
        return used == 0

    def main_mail_unread_count(self) -> int:
        """Read the exact numeric badge attached to the pinned main mail Button."""

        button_state = self.read_state()
        mail = self._unique(button_state, "main/mail")
        if not mail.actionable or self._blocking_rules(button_state, "main/mail"):
            raise SemanticGateClosed("main mail identity is not safely actionable")
        ui_state = self.read_ui_state()
        suffix = "NewMainMellowTheme(Clone)/frame/top/btns/mail/Text"
        matches = tuple(
            item
            for item in ui_state.texts
            if item.name == "Text"
            and item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if not matches:
            return 0
        if len(matches) != 1 or re.fullmatch(r"[1-9]\d{0,2}", matches[0].text) is None:
            raise SemanticGateClosed("main mail unread badge is malformed or ambiguous")
        return int(matches[0].text)

    def main_gold(self) -> int:
        """Read the exact main-screen coin counter before entering Build."""

        button_state = self.read_state()
        build = self._unique(button_state, "main/build")
        if not build.actionable or self._blocking_rules(button_state, "main/build"):
            raise SemanticGateClosed("main build entry identity is not proven")
        ui_state = self.read_ui_state()
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(
                "NewMainMellowTheme(Clone)/frame/top/res/gold/Text"
            )
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1 or re.fullmatch(r"[0-9]+", matches[0].text.strip()) is None:
            raise SemanticGateClosed("main coin counter is absent or malformed")
        return int(matches[0].text.strip())

    def main_red_dot(self, semantic_id: str) -> bool:
        """Read a reviewed main-menu ``reddot`` marker without using pixels."""

        suffixes = {
            "main/task": "NewMainMellowTheme(Clone)/frame/bottom/frame/task/tip",
            "main/build": "NewMainMellowTheme(Clone)/frame/bottom/frame/build/tip",
            "main/live": "NewMainMellowTheme(Clone)/frame/bottom/frame/live/tip",
        }
        try:
            suffix = suffixes[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed("main red-dot target is not mapped") from exc
        button_state = self.read_state()
        if not self._matches(button_state, semantic_id):
            raise SemanticGateClosed("main red-dot parent identity is absent")
        ui_state = self.read_ui_state()
        matches = tuple(
            image
            for image in ui_state.images
            if image.name == "tip"
            and image.path.endswith(suffix)
            and image.sprite == "reddot"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(matches) > 1:
            raise SemanticGateClosed("main red-dot marker is ambiguous")
        return bool(matches)

    def reward_summary_count(self, section: str, counter: str) -> int:
        """Read one exact non-negative counter from the reward side panel."""

        return self._retry_transition_read(
            lambda: self._reward_summary_count_once(section, counter)
        )

    def _reward_summary_count_once(self, section: str, counter: str) -> int:
        """Read one exact reward-summary generation."""

        section_names = {
            "commission": "event",
            "tactical": "class",
            "research": "technology",
        }
        if section not in section_names:
            raise SemanticGateClosed("reward summary section is not mapped")
        if counter not in ("finished", "ongoing", "leisure"):
            raise SemanticGateClosed("reward summary counter is not mapped")

        button_state = self.read_state()
        page = self._unique(button_state, "reward/page/back")
        if not page.actionable or self._blocking_rules(button_state, "reward/page/back"):
            raise SemanticGateClosed("reward summary page identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("reward summary snapshots are not coherent")
        suffix = (
            "CommissionInfoUI4Mellow(Clone)/frame/main/content/"
            + section_names[section]
            + "/frame/counter/"
            + counter
            + "/Text"
        )
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) > 1:
            raise SemanticGateClosed("reward summary counter is ambiguous")
        if matches:
            if re.fullmatch(r"[0-9]+", matches[0].text) is None:
                raise SemanticGateClosed("reward summary counter is malformed")
            return int(matches[0].text)

        # The pinned page omits both the label Image and Text for zero-valued
        # counters.  Treat that closed-world omission as zero only after the
        # exact section frame and a complete Image snapshot are proven.
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed reward Image snapshot is incomplete")
        section_path = (
            "CommissionInfoUI4Mellow(Clone)/frame/main/content/"
            + section_names[section]
            + "/frame"
        )
        frame_sprites = {
            "commission": "frame_event",
            "tactical": "frame_class",
            "research": "frame_tech",
        }
        frames = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(section_path)
            and image.sprite == frame_sprites[section]
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        label_sprites = {
            "finished": "label_finish",
            "ongoing": "label_ongoing",
            "leisure": "label_freedom",
        }
        labels = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(suffix[: -len("/Text")])
            and image.sprite == label_sprites[counter]
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(frames) != 1 or labels:
            raise SemanticGateClosed("reward summary zero counter is not proven")
        return 0

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        """Read visible commission rows without inferring hidden or unknown state.

        This deliberately exposes only rows whose exact row Button is currently
        top-raycastable on screen.  It is therefore a viewport read, not a claim
        that the scrollable commission list has been exhausted.
        """

        return self._retry_transition_read(self._commission_rows_once)

    def _commission_rows_once(self) -> Tuple[CommissionRowState, ...]:
        """Read one exact commission-list generation."""

        button_state = self.read_state()
        page_back = self._unique(button_state, "commission/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/page/back"
        ):
            raise SemanticGateClosed("commission page identity is not proven")

        row_pattern = re.compile(
            r"(?:^|/)EventUI\(Clone\)/scrollRect\$/content/([0-9]+)/bgNormal\$$"
        )
        indexed_buttons: Dict[int, ButtonState] = {}
        row_roots: Dict[int, str] = {}
        for button in button_state.buttons:
            if button.name != "bgNormal$":
                continue
            match = row_pattern.search(button.path)
            if match is None or not button.active_in_hierarchy:
                continue
            index = int(match.group(1))
            if index in indexed_buttons:
                raise SemanticGateClosed(
                    "commission row Button index is ambiguous: {0}".format(index)
                )
            indexed_buttons[index] = button
            row_roots[index] = button.path[: -len("/bgNormal$")]

        if not indexed_buttons:
            if self.commission_is_empty():
                return ()
            raise SemanticGateClosed(
                "commission page has neither indexed rows nor the exact empty marker"
            )

        ui_state = self.read_ui_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed commission Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission snapshots are not coherent")

        def exact_text(path: str) -> TextState:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path == path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "commission row text is absent or ambiguous: " + path
                )
            return matches[0]

        def exact_image(path: str) -> ImageState:
            matches = tuple(
                item
                for item in ui_state.images
                if item.path == path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "commission row image is absent or ambiguous: " + path
                )
            return matches[0]

        status_sprites = {
            # These are the exact pending/running row markers observed and
            # exercised on the pinned CN 9.7.10 build. New sprites remain closed.
            "kongxian_bg": CommissionStatus.PENDING,
            "tag_ongoing": CommissionStatus.RUNNING,
        }
        rows = []
        for index in sorted(indexed_buttons):
            button = indexed_buttons[index]
            if (
                not button.actionable
                or button.point is None
                or not 0 <= button.point.x < self.fingerprint.width
                or not 0 <= button.point.y < self.fingerprint.height
            ):
                continue
            root = row_roots[index]
            name = exact_text(root + "/labelName$").text.strip()
            level_text = exact_text(root + "/level/labelLv$").text.strip()
            duration_text = exact_text(root + "/labelTime$/Text").text.strip()
            status_matches = tuple(
                item
                for item in ui_state.images
                if item.path in (
                    root + "/iconState$/0",
                    root + "/iconState$/1",
                )
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(status_matches) != 1:
                raise SemanticGateClosed(
                    "commission row status image is absent or ambiguous: " + root
                )
            status_image = status_matches[0]
            type_image = exact_image(root + "/iconType$")
            if not name or re.fullmatch(r"[0-9]{1,3}", level_text) is None:
                raise SemanticGateClosed("commission row identity is malformed")
            level = int(level_text)
            if level <= 0:
                raise SemanticGateClosed("commission row level is invalid")
            try:
                status = status_sprites[status_image.sprite]
            except KeyError as exc:
                raise SemanticGateClosed(
                    "commission row status sprite is not reviewed: "
                    + status_image.sprite
                ) from exc
            if not type_image.sprite:
                raise SemanticGateClosed("commission row type sprite is empty")
            rows.append(
                CommissionRowState(
                    index=index,
                    name=name,
                    level=level,
                    duration_seconds=self.parse_countdown_seconds(duration_text),
                    status=status,
                    type_sprite=type_image.sprite,
                    button=button,
                )
            )
        if not rows:
            raise SemanticGateClosed("commission viewport has no actionable typed rows")
        return tuple(rows)

    def commission_scroll_state(self) -> CommissionScrollState:
        """Read the exact commission scrollbar geometry from typed Images."""

        return self._retry_transition_read(self._commission_scroll_state_once)

    def _commission_scroll_state_once(self) -> CommissionScrollState:
        button_state = self.read_state()
        page_back = self._unique(button_state, "commission/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/scroll"
        ):
            raise SemanticGateClosed("commission scroll page identity is not proven")
        ui_state = self.read_ui_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed commission scroll Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission scroll snapshots are not coherent")

        track_suffix = "EventUI(Clone)/blur_panel/adapt/scroll_bar"
        handle_suffix = track_suffix + "/Image"
        tracks = tuple(
            image
            for image in ui_state.images
            if image.name == "scroll_bar"
            and image.path.endswith(track_suffix)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        handles = tuple(
            image
            for image in ui_state.images
            if image.name == "Image"
            and image.path.endswith(handle_suffix)
            and image.sprite == "scroll_bar"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if not tracks and not handles:
            # Lists that fit in one viewport do not instantiate this optional
            # scrollbar at all.  A complete Image snapshot proves that exact
            # absence; a partial track/handle pair remains invalid below.
            empty_bounds = Bounds(0.0, 0.0, 0.0, 0.0)
            return CommissionScrollState(
                generation=ui_state.generation,
                position=0.0,
                page_fraction=1.0,
                track_bounds=empty_bounds,
                handle_bounds=empty_bounds,
                handle_path="",
                handle_raycast_top=None,
            )
        if len(tracks) != 1 or len(handles) != 1:
            raise SemanticGateClosed(
                "commission scrollbar track or handle is absent or ambiguous"
            )
        track = tracks[0]
        handle = handles[0]
        assert track.bounds is not None
        assert handle.bounds is not None
        track_height = track.bounds.bottom - track.bounds.top
        handle_height = handle.bounds.bottom - handle.bounds.top
        track_center_x = (track.bounds.left + track.bounds.right) / 2.0
        handle_center_x = (handle.bounds.left + handle.bounds.right) / 2.0
        if (
            track_height <= 0
            or handle_height <= 0
            or handle_height > track_height + 20.0
            or abs(track_center_x - handle_center_x) > 20.0
        ):
            raise SemanticGateClosed("commission scrollbar geometry is invalid")
        travel = max(0.0, track_height - handle_height)
        if travel <= 1.0:
            position = 0.0
        else:
            raw_position = (handle.bounds.top - track.bounds.top) / travel
            if raw_position < -0.15 or raw_position > 1.15:
                raise SemanticGateClosed("commission scrollbar position is invalid")
            position = min(1.0, max(0.0, raw_position))
        return CommissionScrollState(
            generation=ui_state.generation,
            position=position,
            page_fraction=min(1.0, handle_height / track_height),
            track_bounds=track.bounds,
            handle_bounds=handle.bounds,
            handle_path=handle.path,
            handle_raycast_top=handle.raycast_top,
        )

    @staticmethod
    def _commission_row_signatures(
        rows: Sequence[CommissionRowState],
    ) -> Tuple[Tuple[Union[int, str], ...], ...]:
        # Countdown and lifecycle status can change independently of a
        # gesture.  Neither is evidence that a different row entered the
        # actionable viewport.
        return tuple(
            (
                row.index,
                row.name,
                row.level,
                row.type_sprite,
            )
            for row in rows
        )

    def _commission_scroll_to(
        self,
        target_position: float,
        direction: str,
        timeout_seconds: float = 12.0,
    ) -> Optional[CommissionScrollProof]:
        if direction not in ("top", "next"):
            raise ValueError("commission scroll direction is not supported")
        if not 0.0 <= target_position <= 1.0:
            raise ValueError("commission scroll target must be within [0, 1]")
        if self._swipe is None:
            raise SemanticGateClosed("semantic commission swipe backend is unavailable")
        before = self.commission_scroll_state()
        before_rows = self.commission_rows()
        before_signatures = self._commission_row_signatures(before_rows)
        if not before.scrollable:
            return None
        if direction == "top" and before.at_top:
            return None
        if direction == "next" and before.at_bottom:
            return None
        if before.handle_raycast_top is not True:
            raise SemanticGateClosed("commission scrollbar handle is not top-raycastable")

        handle_height = before.handle_bounds.bottom - before.handle_bounds.top
        track_height = before.track_bounds.bottom - before.track_bounds.top
        travel = track_height - handle_height
        if travel <= 1.0:
            return None
        start = Point(
            (before.handle_bounds.left + before.handle_bounds.right) / 2.0,
            (before.handle_bounds.top + before.handle_bounds.bottom) / 2.0,
        )
        end = Point(
            start.x,
            before.track_bounds.top + target_position * travel + handle_height / 2.0,
        )
        if not (
            0 <= start.x < self.fingerprint.width
            and 0 <= start.y < self.fingerprint.height
            and 0 <= end.x < self.fingerprint.width
            and 0 <= end.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("commission scrollbar gesture is outside the screen")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before commission scroll")
        self._swipe(
            int(round(start.x)),
            int(round(start.y)),
            int(round(end.x)),
            int(round(end.y)),
            500,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after commission scroll")

        deadline = self._monotonic() + timeout_seconds
        last_error: Optional[SemanticGateClosed] = None
        while self._monotonic() < deadline:
            self._sleep(0.25)
            try:
                after = self.commission_scroll_state()
                after_rows = self.commission_rows()
                after_signatures = self._commission_row_signatures(after_rows)
            except SemanticGateClosed as exc:
                last_error = exc
                continue
            moved = (
                after.position < before.position - 0.03
                if direction == "top"
                else after.position > before.position + 0.03
            )
            if after.generation > before.generation and moved:
                return CommissionScrollProof(
                    direction=direction,
                    before_position=before.position,
                    after_position=after.position,
                    before_generation=before.generation,
                    after_generation=after.generation,
                    before_row_signatures=before_signatures,
                    after_row_signatures=after_signatures,
                )
        if last_error is not None:
            raise last_error
        raise SemanticGateClosed("commission scrollbar transition was not proven")

    def commission_scroll_next(self) -> Optional[CommissionScrollProof]:
        state = self.commission_scroll_state()
        target = min(1.0, state.position + max(0.25, state.page_fraction * 0.8))
        proof = self._commission_scroll_to(target, "next")
        if (
            proof is not None
            and proof.before_row_signatures == proof.after_row_signatures
        ):
            # The exact handle moved, but no new stable row identity entered
            # the actionable viewport.  For ALAS list scanning this is list
            # exhaustion, not another page to process.
            return None
        return proof

    def commission_scroll_to_top(self) -> Optional[CommissionScrollProof]:
        before = self.commission_scroll_state()
        before_signatures = self._commission_row_signatures(self.commission_rows())
        if not before.scrollable or before.at_top:
            return None

        after = before
        after_signatures = before_signatures
        for _ in range(6):
            step = self._commission_scroll_to(0.0, "top")
            if step is None:
                break
            after = self.commission_scroll_state()
            after_signatures = self._commission_row_signatures(
                self.commission_rows()
            )
            if after.at_top:
                return CommissionScrollProof(
                    direction="top",
                    before_position=before.position,
                    after_position=after.position,
                    before_generation=before.generation,
                    after_generation=after.generation,
                    before_row_signatures=before_signatures,
                    after_row_signatures=after_signatures,
                )
        raise SemanticGateClosed("commission scrollbar did not reach the exact top")

    def commission_is_empty(self) -> bool:
        """Return true only for the pinned commission page's explicit empty text."""

        button_state = self.read_state()
        page_back = self._unique(button_state, "commission/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/page/back"
        ):
            raise SemanticGateClosed("commission page identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission empty snapshots are not coherent")
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith("EventUI(Clone)/empty/Text")
            and item.text == "暂无可以进行的委托"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.bounds.right > 0
            and item.bounds.bottom > 0
            and item.bounds.left < self.fingerprint.width
            and item.bounds.top < self.fingerprint.height
        )
        if len(matches) > 1:
            raise SemanticGateClosed("commission empty marker is ambiguous")
        if matches:
            row_pattern = re.compile(
                r"(?:^|/)EventUI\(Clone\)/scrollRect\$/content/([0-9]+)/"
                r"bgNormal\$$"
            )
            visible_rows = tuple(
                button
                for button in button_state.buttons
                if button.name == "bgNormal$"
                and row_pattern.search(button.path) is not None
                and button.actionable
                and button.point is not None
                and 0 <= button.point.x < self.fingerprint.width
                and 0 <= button.point.y < self.fingerprint.height
            )
            if visible_rows:
                raise SemanticGateClosed(
                    "commission page reports rows and empty together"
                )
        return bool(matches)

    def click_commission_row(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> ActionReceipt:
        """Select one exact visible pending row after re-reading typed state."""

        expected = tuple(expected_signature)
        if len(expected) != 6:
            raise SemanticGateClosed("commission row signature is malformed")
        rows = self.commission_rows()
        matches = tuple(row for row in rows if row.signature == expected)
        if len(matches) != 1:
            raise SemanticGateClosed("commission row identity is absent or ambiguous")
        row = matches[0]
        if row.status != CommissionStatus.PENDING:
            raise SemanticGateClosed("commission row is not pending")
        state = self.read_state()
        current = tuple(button for button in state.buttons if button.path == row.button.path)
        if len(current) != 1:
            raise SemanticGateClosed("commission row Button changed before input")
        button = current[0]
        if not button.actionable or button.point is None or button.bounds is None:
            raise SemanticGateClosed("commission row is not actionable")
        if self._blocking_rules(state, "commission/page/back"):
            raise SemanticGateClosed("commission row action is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before commission input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(
            semantic_id="commission/row/{0}".format(row.index),
            generation=state.generation,
            point=button.point,
            bounds=button.bounds,
            path=button.path,
        )

    def commission_detail_state(self) -> CommissionDetailState:
        """Read the exact selected commission and ship-assignment state."""

        button_state = self.read_state()
        back = self._unique(button_state, "commission/detail/back")
        recommend = self._unique(button_state, "commission/detail/recommend")
        start = self._unique(button_state, "commission/detail/start")
        if not back.actionable:
            raise SemanticGateClosed("commission detail page identity is not proven")
        for target in (recommend, start):
            if (
                not target.active_in_hierarchy
                or not target.active_and_enabled
                or not target.interactable
                or target.point is None
                or target.bounds is None
                or target.raycast_top is False
            ):
                raise SemanticGateClosed("commission detail input is not structurally valid")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission detail snapshots are not coherent")

        base = "Overlay/UIMain/blur_panel/scrollItem/"

        def exact_text(suffix: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(base + suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "commission detail text is absent or ambiguous: " + suffix
                )
            return re.sub(r"<[^<>]{1,128}>", "", matches[0].text).strip()

        name = exact_text("labelName$")
        level_text = exact_text("level/labelLv$")
        duration_text = exact_text("labelTime$/Text")
        oil_text = exact_text("maskDetail/detailPanel/consume/Text")
        if (
            not name
            or re.fullmatch(r"[0-9]{1,3}", level_text) is None
            or re.fullmatch(r"[0-9]+", oil_text) is None
        ):
            raise SemanticGateClosed("commission detail identity is malformed")

        empty_pattern = re.compile(
            r"(?:^|/)maskDetail/detailPanel/frame/ship_contain_(?:left|right)/"
            r"ship_[1-3]/emptytpl$"
        )
        empty_paths = {
            button.path
            for button in button_state.buttons
            if empty_pattern.search(button.path) is not None
            and button.active_in_hierarchy
            and button.active_and_enabled
        }
        if len(empty_paths) > 6:
            raise SemanticGateClosed("commission detail empty ship slots are malformed")
        empty_count = len(empty_paths)
        selected_count = 6 - empty_count
        return CommissionDetailState(
            name=name,
            level=int(level_text),
            duration_seconds=self.parse_countdown_seconds(duration_text),
            oil_cost=int(oil_text),
            selected_ship_count=selected_count,
            empty_ship_count=empty_count,
        )

    def _click_commission_detail(
        self,
        semantic_id: str,
        expected_signature: Sequence[Union[int, str]],
        require_assigned_ships: bool,
    ) -> ActionReceipt:
        expected = tuple(expected_signature)
        if len(expected) != 6:
            raise SemanticGateClosed("commission row signature is malformed")
        detail = self.commission_detail_state()
        if detail.signature != (expected[1], expected[2], expected[3]):
            raise SemanticGateClosed("selected commission detail identity changed")
        if require_assigned_ships and detail.selected_ship_count < 3:
            raise SemanticGateClosed("commission start requires at least three assigned ships")
        if require_assigned_ships and detail.oil_cost != 0:
            raise SemanticGateClosed(
                "semantic commission start is limited to zero-oil rows"
            )

        state = self.read_state()
        target = self._unique(state, semantic_id)
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or target.raycast_top is False
            or self._blocking_rules(state, semantic_id)
        ):
            raise SemanticGateClosed("commission detail action is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before commission detail input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_commission_recommend(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> ActionReceipt:
        return self._click_commission_detail(
            "commission/detail/recommend",
            expected_signature,
            require_assigned_ships=False,
        )

    def click_commission_start(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> ActionReceipt:
        return self._click_commission_detail(
            "commission/detail/start",
            expected_signature,
            require_assigned_ships=True,
        )

    def commission_start_transition(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> CommissionStartProof:
        """Prove that the exact pending row returned with a live countdown."""

        expected = tuple(expected_signature)
        if len(expected) != 6 or expected[4] != CommissionStatus.PENDING.value:
            raise SemanticGateClosed("commission start proof signature is malformed")
        index, name, level, before_duration, _, type_sprite = expected
        if not isinstance(index, int):
            raise SemanticGateClosed("commission start proof index is malformed")

        button_state = self.read_state()
        page_back_matches = self._matches(button_state, "commission/page/back")
        detail_back_matches = self._matches(button_state, "commission/detail/back")
        if not page_back_matches and len(detail_back_matches) == 1:
            detail_back = detail_back_matches[0]
            if not detail_back.actionable or self._blocking_rules(
                button_state, "commission/detail/back"
            ):
                raise SemanticGateClosed(
                    "running commission detail identity is not proven"
                )
            ui_state = self.read_ui_state()
            if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
                raise SemanticGateClosed(
                    "running commission detail Image snapshot is incomplete"
                )
            if (
                ui_state.generation < button_state.generation
                or ui_state.generation > button_state.generation + 2
            ):
                raise SemanticGateClosed(
                    "running commission detail snapshots are not coherent"
                )
            root = "Overlay/UIMain/blur_panel/scrollItem"

            def detail_text(suffix: str) -> str:
                matches = tuple(
                    item
                    for item in ui_state.texts
                    if item.path.endswith(root + suffix)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "running commission detail text is ambiguous"
                    )
                return re.sub(r"<[^<>]{1,128}>", "", matches[0].text).strip()

            def detail_image(suffix: str) -> ImageState:
                matches = tuple(
                    item
                    for item in ui_state.images
                    if item.path.endswith(root + suffix)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "running commission detail image is ambiguous"
                    )
                return matches[0]

            actual_name = detail_text("/labelName$")
            actual_level = detail_text("/level/labelLv$")
            after_duration = self.parse_countdown_seconds(
                detail_text("/labelTime$/Text")
            )
            cancel_label = detail_text(
                "/maskDetail/detailPanel/btn/giveup/text"
            )
            actual_type = detail_image("/iconType$").sprite
            after_status = detail_image("/iconState$/1").sprite
            if (
                actual_name != name
                or actual_level != str(level)
                or actual_type != type_sprite
                or cancel_label != "取消"
                or after_status != "tag_ongoing"
            ):
                raise SemanticGateClosed(
                    "running commission detail identity changed"
                )
            if not 0 < after_duration <= int(before_duration):
                raise SemanticGateClosed(
                    "running commission detail countdown is invalid"
                )
            return CommissionStartProof(
                index=index,
                name=actual_name,
                level=int(actual_level),
                type_sprite=actual_type,
                before_duration_seconds=int(before_duration),
                after_duration_seconds=after_duration,
                before_status_sprite="kongxian_bg",
                after_status_sprite=after_status,
                generation=button_state.generation,
            )
        if len(page_back_matches) != 1 or detail_back_matches:
            raise SemanticGateClosed(
                "commission start transition surface is absent or ambiguous"
            )
        page_back = page_back_matches[0]
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/page/back"
        ):
            raise SemanticGateClosed("commission page identity is not proven")
        root = "EventUI(Clone)/scrollRect$/content/{0}".format(index)
        row_buttons = tuple(
            button
            for button in button_state.buttons
            if button.name == "bgNormal$"
            and button.path.endswith(root + "/bgNormal$")
            and button.active_in_hierarchy
        )
        if len(row_buttons) != 1:
            raise SemanticGateClosed("started commission row is absent or ambiguous")

        ui_state = self.read_ui_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("commission start proof Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission start proof snapshots are not coherent")

        def exact_text(suffix: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(root + suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("commission start proof text is ambiguous")
            return item_text(matches[0])

        def item_text(item: TextState) -> str:
            return re.sub(r"<[^<>]{1,128}>", "", item.text).strip()

        def exact_image(suffix: str) -> ImageState:
            matches = tuple(
                item
                for item in ui_state.images
                if item.path.endswith(root + suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("commission start proof image is ambiguous")
            return matches[0]

        actual_name = exact_text("/labelName$")
        actual_level = exact_text("/level/labelLv$")
        after_duration = self.parse_countdown_seconds(
            exact_text("/labelTime$/Text")
        )
        after_status = exact_image("/iconState$/1").sprite
        actual_type = exact_image("/iconType$").sprite
        if (
            actual_name != name
            or actual_level != str(level)
            or actual_type != type_sprite
        ):
            raise SemanticGateClosed("started commission row identity changed")
        if not 0 < after_duration <= int(before_duration):
            raise SemanticGateClosed("started commission countdown is invalid")
        if after_status != "tag_ongoing":
            raise SemanticGateClosed("commission row did not leave pending state")
        return CommissionStartProof(
            index=index,
            name=actual_name,
            level=int(actual_level),
            type_sprite=actual_type,
            before_duration_seconds=int(before_duration),
            after_duration_seconds=after_duration,
            before_status_sprite="kongxian_bg",
            after_status_sprite=after_status,
            generation=button_state.generation,
        )

    def build_selected_pool(self) -> BuildPool:
        """Return the selected construction pool from exact Unity Toggles."""

        button_state = self.read_state()
        page_markers = tuple(
            button
            for button in button_state.buttons
            if button.name == "start_btn"
            and button.path.endswith(
                "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/start_btn"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(page_markers) != 1:
            raise SemanticGateClosed("construction page identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("construction snapshots are not coherent")
        selected = []
        for pool in BuildPool:
            matches = self._toggle_matches(ui_state, "build/pool/" + pool.value)
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "construction pool Toggle is absent or ambiguous: " + pool.value
                )
            if matches[0].checked:
                selected.append(pool)
        if len(selected) != 1:
            raise SemanticGateClosed("construction pool selection is inconsistent")
        return selected[0]

    def build_costs(self) -> BuildCostState:
        """Read owned cubes and per-build costs without enabling construction."""

        self.build_selected_pool()
        state = self.read_ui_state()
        base = "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/"
        suffixes = {
            "owned": base + "res_items/item/Text",
            "cubes": base + "item_bg/item/Text",
            "coins": base + "item_bg/gold/Text",
        }
        values: Dict[str, int] = {}
        for key, suffix in suffixes.items():
            matches = tuple(
                item
                for item in state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
                and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "construction resource text is absent or ambiguous: " + key
                )
            values[key] = int(matches[0].text.strip())
        if values["cubes"] <= 0 or values["coins"] <= 0:
            raise SemanticGateClosed("construction cost is invalid")
        return BuildCostState(
            cubes_owned=values["owned"],
            cubes_per_build=values["cubes"],
            coins_per_build=values["coins"],
        )

    def build_coins_owned(self) -> int:
        """Read the exact global coin counter while the pool page is proven."""

        self.build_selected_pool()
        state = self.read_ui_state()
        suffix = "Overlay/UIMain/ResPanel(Clone)/frame/gold/gold_value"
        matches = tuple(
            item
            for item in state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "construction coin counter is absent or ambiguous"
            )
        return int(matches[0].text.strip())

    def build_submit_state(self) -> BuildSubmitState:
        """Read and cross-check the open construction confirmation dialog."""

        button_state = self.read_state()
        confirm = self._unique(button_state, "build/prep/confirm")
        cancel = self._unique(button_state, "build/prep/cancel")
        if (
            not confirm.actionable
            or not cancel.actionable
            or self._blocking_rules(button_state, "build/prep/confirm")
        ):
            raise SemanticGateClosed("construction confirmation identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("construction confirmation snapshots are not coherent")

        def exact_text(path: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "construction confirmation text is absent or ambiguous"
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        count_text = exact_text(
            "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/Text"
        )
        message = exact_text("BuildShipMsgBoxUI(Clone)/window/content/Text")
        count_match = re.fullmatch(r"([1-9][0-9]?)", count_text)
        cost_match = re.fullmatch(
            r"建造「([1-9][0-9]?)艘」.+需要消耗:\s*"
            r"「([1-9][0-9]*)物资」和「([1-9][0-9]*)个心智魔方」",
            message,
        )
        if count_match is None or cost_match is None:
            raise SemanticGateClosed("construction confirmation cost is malformed")
        count = int(count_match.group(1))
        message_count, coins, cubes = map(int, cost_match.groups())
        if message_count != count:
            raise SemanticGateClosed("construction confirmation count is inconsistent")

        costs = self.build_costs()
        if (
            cubes != costs.cubes_per_build * count
            or coins != costs.coins_per_build * count
        ):
            raise SemanticGateClosed("construction confirmation cost changed unexpectedly")
        return BuildSubmitState(
            count=count,
            cubes_owned=costs.cubes_owned,
            cubes_required=cubes,
            coins_required=coins,
            confirm=confirm,
        )

    def build_queue_timers(self) -> Tuple[str, ...]:
        """Read the pinned two-slot construction queue without mutating it."""

        button_state = self.read_state()
        back = self._unique(button_state, "build/page/back")
        if not back.actionable or self._blocking_rules(
            button_state, "build/nav/queue"
        ):
            raise SemanticGateClosed("construction queue page identity is not proven")
        if not self.toggle_selected("build/nav/queue"):
            raise SemanticGateClosed("construction queue tab is not selected")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("construction queue snapshots are not coherent")
        capacity = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith("BuildShipDetailUI1(Clone)/title/value")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(capacity) != 1 or capacity[0].text.strip() != "2":
            raise SemanticGateClosed("construction queue capacity is unexpected")
        timer_patterns = {
            "single": re.compile(
                r"BuildShipDetailUI1\(Clone\)/list_single_line/content/"
                r"project_([12])/frame/buiding/timer/Text$"
            ),
            "multi": re.compile(
                r"BuildShipDetailUI1\(Clone\)/list_mult_line/content/"
                r"project_([123])/frame/buiding/timer/Text$"
            ),
        }
        timers_by_layout: Dict[str, Dict[int, str]] = {
            "single": {},
            "multi": {},
        }
        for item in ui_state.texts:
            layout_match = next(
                (
                    (layout, pattern.search(item.path))
                    for layout, pattern in timer_patterns.items()
                    if pattern.search(item.path) is not None
                ),
                None,
            )
            if layout_match is None:
                continue
            layout, match = layout_match
            assert match is not None
            if (
                not item.active_in_hierarchy
                or not item.active_and_enabled
                or item.truncated
                or item.bounds is None
            ):
                continue
            index = int(match.group(1))
            timers = timers_by_layout[layout]
            if index in timers:
                raise SemanticGateClosed("construction queue timer is ambiguous")
            value = item.text.strip()
            if value != "99:99:99" and re.fullmatch(
                r"[0-9]{2}:[0-5][0-9]:[0-5][0-9]", value
            ) is None:
                raise SemanticGateClosed("construction queue timer is malformed")
            timers[index] = value
        observed = tuple(
            (layout, timers)
            for layout, timers in timers_by_layout.items()
            if timers
        )
        if len(observed) != 1:
            raise SemanticGateClosed("construction queue timers are incomplete")
        layout, timers = observed[0]
        expected = (1, 2) if layout == "single" else (1, 2, 3)
        if tuple(sorted(timers)) != expected:
            raise SemanticGateClosed("construction queue timers are incomplete")
        return tuple(timers[index] for index in expected)

    def build_queue_empty(self) -> bool:
        return all(value == "99:99:99" for value in self.build_queue_timers())

    def campaign_menu_is_entry(self) -> bool:
        """Identify the campaign entrance without conflating the chapter page."""

        if not self.exists("campaign-menu/normal"):
            return False
        state = self.read_ui_state()
        chapter_titles = tuple(
            item
            for item in state.texts
            if item.path.endswith(
                "LevelMainScene(Clone)/top/top_chapter/title_chapter/name"
            )
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.bounds is not None
        )
        if chapter_titles:
            raise SemanticGateClosed(
                "campaign entrance and chapter title are visible together"
            )
        return True

    def campaign_map_entry_state(self) -> CampaignMapEntryState:
        """Read the exact map-scene root without exposing any map input."""

        return self._retry_transition_read(
            self._campaign_map_entry_state_once,
            attempts=12,
        )

    def _campaign_map_entry_state_once(self) -> CampaignMapEntryState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        return self._campaign_map_entry_state_from_snapshots(button_state, ui_state)

    @staticmethod
    def _campaign_map_entry_state_from_snapshots(
        button_state: OracleState,
        ui_state: UiState,
    ) -> CampaignMapEntryState:
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.method_mask & 0x8 == 0
        ):
            raise SemanticGateClosed("campaign map-entry snapshots are incomplete")

        grid_root = "LevelCamera/Canvas/UIMain/LevelGrid"
        grid_button = re.compile(
            re.escape(grid_root)
            + r"/DragLayer/plane/quads/chapter_cell_quad_[1-9][0-9]*_[1-9][0-9]*"
        )
        retreat_button_path = grid_root + "/DragLayer/op1/retreat"
        stage_root = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)"
        stage_back_button_path = stage_root + "/top_stage/back_button"
        required_images = {
            grid_root + "/DragLayer/op1/retreat/retreat": "reteat_popo",
            grid_root + "/DragLayer/plane/display/mask/sea": "sea_day",
            stage_root + "/top_stage/back_button/mask/Image": "back_btn",
        }
        preparation_markers = (
            "/LevelMainScene(Clone)/",
            "/LevelStageInfoView(Clone)/",
            "/LevelFleetSelectView(Clone)/",
        )
        active_buttons = tuple(
            button
            for button in button_state.buttons
            if button.active_in_hierarchy and button.active_and_enabled
        )
        grid_button_paths = tuple(
            sorted(
                button.path
                for button in active_buttons
                if grid_button.fullmatch(button.path)
            )
        )
        fixed_button_paths = tuple(
            path
            for path in (retreat_button_path, stage_back_button_path)
            if sum(button.path == path for button in active_buttons) == 1
        )
        active_images = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        required_image_paths = tuple(sorted(required_images))
        required_image_matches = tuple(
            (
                sprite,
                tuple(image for image in active_images if image.path == path),
            )
            for path, sprite in required_images.items()
        )
        if (
            len(fixed_button_paths) != 2
            or not grid_button_paths
            or any(
                len(matches) != 1 or matches[0].sprite != sprite
                for sprite, matches in required_image_matches
            )
        ):
            raise SemanticGateClosed("campaign map-scene identity is absent")
        if any(
            marker in item.path
            for marker in preparation_markers
            for item in (*button_state.buttons, *ui_state.texts)
            if item.active_in_hierarchy and item.active_and_enabled
        ):
            raise SemanticGateClosed(
                "campaign map and preparation identities overlap"
            )
        return CampaignMapEntryState(
            generation=button_state.generation,
            root_path=grid_root,
            button_paths=tuple(sorted((*fixed_button_paths, *grid_button_paths))),
            image_paths=required_image_paths,
        )

    @staticmethod
    def _campaign_map_node(row: int, column: int) -> str:
        if row < 1 or column < 1:
            raise SemanticGateClosed("campaign map coordinate is invalid")
        value = column
        letters = ""
        while value:
            value, remainder = divmod(value - 1, 26)
            letters = chr(ord("A") + remainder) + letters
        return letters + str(row)

    def campaign_map_state(
        self,
        stage_code: str,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        """Build a stable, complete, read-only map model from typed Unity state.

        ``land_cells`` uses ALAS's zero-based ``CampaignMap`` locations.  The
        complete Button topology is checked against that map definition, while
        all dynamic objects require a non-truncated Image/Text snapshot.  Two
        increasing generations must expose the same logical signature.
        """

        if re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", stage_code) is None:
            raise SemanticGateClosed("campaign map stage code is not canonical")
        if (
            isinstance(columns, bool)
            or not isinstance(columns, int)
            or isinstance(rows, bool)
            or not isinstance(rows, int)
            or columns < 1
            or rows < 1
            or columns > 26
            or rows > 99
        ):
            raise SemanticGateClosed("campaign map shape is invalid")
        if (
            isinstance(expected_fleet_count, bool)
            or not isinstance(expected_fleet_count, int)
            or expected_fleet_count not in (1, 2)
        ):
            raise SemanticGateClosed("campaign map fleet count is invalid")

        normalized_land = []
        for location in land_cells:
            if (
                not isinstance(location, (tuple, list))
                or len(location) != 2
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in location
                )
            ):
                raise SemanticGateClosed("campaign map land topology is malformed")
            column0, row0 = location
            if not (0 <= column0 < columns and 0 <= row0 < rows):
                raise SemanticGateClosed("campaign map land coordinate is outside its shape")
            normalized_land.append((row0 + 1, column0 + 1))
        land = tuple(sorted(set(normalized_land)))
        if len(land) != len(normalized_land):
            raise SemanticGateClosed("campaign map land topology contains duplicates")
        if not land or len(land) >= rows * columns:
            raise SemanticGateClosed("campaign map land topology is incomplete")

        reader = lambda: self._campaign_map_state_once(
            stage_code,
            columns=columns,
            rows=rows,
            land=land,
            expected_fleet_count=expected_fleet_count,
        )
        previous = self._retry_transition_read(reader, attempts=12)
        for _ in range(11):
            self._sleep(0.25)
            current = self._retry_transition_read(reader, attempts=1)
            if (
                current.generation > previous.generation
                and current.signature == previous.signature
            ):
                return current
            previous = current
        raise SemanticGateClosed("campaign map model did not stabilize")

    def campaign_map_cell_input(
        self,
        state: CampaignMapState,
        node: str,
    ) -> ButtonState:
        """Revalidate one exact actionable map cell without injecting input."""

        if not isinstance(state, CampaignMapState):
            raise SemanticGateClosed("campaign map-cell input requires a typed state")
        matches = tuple(cell for cell in state.cells if cell.node == node)
        if len(matches) != 1:
            raise SemanticGateClosed("campaign map-cell input is absent or ambiguous")
        cell = matches[0]
        observed = self.read_state()
        if observed.generation < state.generation:
            raise SemanticGateClosed("campaign map-cell input snapshot is stale")
        buttons = tuple(
            button for button in observed.buttons if button.path == cell.button_path
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("campaign map-cell Button identity changed")
        target = buttons[0]
        if (
            not target.actionable
            or target.point != cell.point
            or target.bounds != cell.bounds
        ):
            raise SemanticGateClosed("campaign map-cell geometry or actionability changed")
        if self._blocking_rules(observed, "campaign/map/grid"):
            raise SemanticGateClosed("campaign map-cell input is blocked")
        if not (
            0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("campaign map-cell point is outside the screen")
        return target

    def click_campaign_map_cell(
        self,
        state: CampaignMapState,
        node: str,
    ) -> ActionReceipt:
        """Inject one exact map-cell tap after a fresh typed revalidation."""

        target = self.campaign_map_cell_input(state, node)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/map/grid/" + node,
            generation=self._last_generation or state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _campaign_map_state_once(
        self,
        stage_code: str,
        *,
        columns: int,
        rows: int,
        land: Tuple[Tuple[int, int], ...],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        entry = self._campaign_map_entry_state_from_snapshots(button_state, ui_state)
        if ui_state.image_truncated:
            raise SemanticGateClosed("campaign map Image snapshot is truncated")

        grid_root = entry.root_path
        cell_pattern = re.compile(
            re.escape(grid_root)
            + r"/DragLayer/plane/quads/chapter_cell_quad_([1-9][0-9]*)_([1-9][0-9]*)$"
        )
        cells_by_coordinate: Dict[Tuple[int, int], CampaignMapCellState] = {}
        cell_world_positions: Dict[Tuple[int, int], Tuple[float, float, float]] = {}
        for button in button_state.buttons:
            match = cell_pattern.fullmatch(button.path)
            if match is None:
                continue
            row, column = (int(match.group(1)), int(match.group(2)))
            coordinate = (row, column)
            if (
                coordinate in cells_by_coordinate
                or row > rows
                or column > columns
                or not button.active_in_hierarchy
                or not button.active_and_enabled
                or not button.interactable
                or button.point is None
                or button.bounds is None
                or not button.bounds.contains(button.point)
            ):
                raise SemanticGateClosed("campaign map grid topology is invalid")
            world_value = button.raw.get("world_position")
            if not isinstance(world_value, dict):
                raise SemanticGateClosed("campaign map grid world position is absent")
            cell_world_positions[coordinate] = tuple(
                self._finite_number(
                    world_value.get(axis), "campaign map grid world position." + axis
                )
                for axis in ("x", "y", "z")
            )
            cells_by_coordinate[coordinate] = CampaignMapCellState(
                row=row,
                column=column,
                node=self._campaign_map_node(row, column),
                button_path=button.path,
                point=button.point,
                bounds=button.bounds,
            )
        expected_cells = {
            (row, column)
            for row in range(1, rows + 1)
            for column in range(1, columns + 1)
            if (row, column) not in land
        }
        if set(cells_by_coordinate) != expected_cells:
            raise SemanticGateClosed("campaign map grid topology disagrees with ALAS")

        active_images = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        active_texts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        cell_root = grid_root + "/DragLayer/plane/cells/"
        attachment_pattern = re.compile(
            re.escape(cell_root)
            + r"chapter_cell_([1-9][0-9]*)_([1-9][0-9]*)/attachment/([^/]+)"
        )
        attachment_roots = set()
        for item in (*active_images, *active_texts):
            match = attachment_pattern.match(item.path)
            if match is not None:
                attachment_roots.add(
                    (int(match.group(1)), int(match.group(2)), match.group(3))
                )

        enemy_icon_pattern = re.compile(
            re.escape(cell_root)
            + r"chapter_cell_([1-9][0-9]*)_([1-9][0-9]*)/attachment/"
            + r"enemy_([1-9][0-9]*)/icon$"
        )
        genre_names = {"qx": "Light", "zl": "Main", "hm": "Carrier"}
        enemies = []
        enemy_roots = set()
        for image in active_images:
            match = enemy_icon_pattern.fullmatch(image.path)
            if match is None:
                continue
            row, column, object_id = map(int, match.groups())
            coordinate = (row, column)
            root_name = "enemy_{0}".format(object_id)
            root = (
                cell_root
                + "chapter_cell_{0}_{1}/attachment/{2}".format(
                    row, column, root_name
                )
            )
            sprite_match = re.fullmatch(r"(qx|zl|hm)([123])", image.sprite)
            if (
                coordinate not in expected_cells
                or (row, column, root_name) in enemy_roots
                or sprite_match is None
                or image.bounds is None
            ):
                raise SemanticGateClosed("campaign map enemy identity is unsupported")
            level_matches = tuple(
                item for item in active_texts if item.path == root + "/lv/Text"
            )
            label_matches = tuple(
                item for item in active_texts if item.path == root + "/lv/lv_label"
            )
            fighting_images = tuple(
                item for item in active_images if item.path == root + "/fighting"
            )
            fighting_texts = tuple(
                item for item in active_texts if item.path == root + "/fighting/Text"
            )
            if (
                len(level_matches) != 1
                or re.fullmatch(r"[1-9][0-9]{0,2}", level_matches[0].text.strip()) is None
                or len(label_matches) != 1
                or label_matches[0].text.strip() != "Lv."
                or bool(fighting_images) != bool(fighting_texts)
                or (fighting_images and len(fighting_images) != 1)
                or (fighting_texts and len(fighting_texts) != 1)
                or (
                    fighting_images
                    and (
                        fighting_images[0].sprite != "xingdongzhong"
                        or fighting_texts[0].text.strip() != "行动中"
                    )
                )
            ):
                raise SemanticGateClosed("campaign map enemy details are incomplete")
            prefix, scale_text = sprite_match.groups()
            enemies.append(
                CampaignMapEnemyState(
                    row=row,
                    column=column,
                    node=self._campaign_map_node(row, column),
                    object_id=object_id,
                    sprite=image.sprite,
                    scale=int(scale_text),
                    genre=genre_names[prefix],
                    level=int(level_matches[0].text.strip()),
                    fighting=bool(fighting_images),
                )
            )
            enemy_roots.add((row, column, root_name))

        pickups = []
        supply_roots = set()
        supply_pattern = re.compile(
            re.escape(cell_root)
            + r"chapter_cell_([1-9][0-9]*)_([1-9][0-9]*)/attachment/"
            + r"supply/Tpl_Supply\(Clone\)/normal$"
        )
        for image in active_images:
            match = supply_pattern.fullmatch(image.path)
            if match is None:
                continue
            row, column = map(int, match.groups())
            if (
                (row, column) not in expected_cells
                or (row, column, "supply") in supply_roots
                or image.sprite != "event4"
                or image.bounds is None
            ):
                raise SemanticGateClosed("campaign map pickup identity is unsupported")
            pickups.append(
                CampaignMapPickupState(
                    row=row,
                    column=column,
                    node=self._campaign_map_node(row, column),
                    kind="ammo",
                    sprite=image.sprite,
                )
            )
            supply_roots.add((row, column, "supply"))
        if attachment_roots != enemy_roots | supply_roots:
            raise SemanticGateClosed("campaign map contains an unsupported attachment")

        fleet_marker_pattern = re.compile(
            re.escape(cell_root) + r"(cell_fleet_[A-Za-z0-9_]+)/"
        )
        fleet_markers = {
            match.group(1)
            for item in (*active_images, *active_texts)
            for match in (fleet_marker_pattern.match(item.path),)
            if match is not None
        }
        if len(fleet_markers) != expected_fleet_count:
            raise SemanticGateClosed("campaign map fleet count is unexpected")
        fleets = []
        occupied_nodes = set()
        for marker in sorted(fleet_markers):
            root = cell_root + marker
            ammo_matches = tuple(
                item for item in active_texts if item.path == root + "/ammo/text"
            )
            anchor_matches = tuple(
                image for image in active_images if image.path == root + "/ammo/bg"
            )
            if (
                len(ammo_matches) != 1
                or len(anchor_matches) != 1
                or anchor_matches[0].sprite != "danyao_bar"
            ):
                raise SemanticGateClosed("campaign map fleet details are incomplete")
            ammo_match = re.fullmatch(
                r"([0-9]+)/([1-9][0-9]*)", ammo_matches[0].text.strip()
            )
            if ammo_match is None:
                raise SemanticGateClosed("campaign map fleet ammo is malformed")
            ammo, capacity = map(int, ammo_match.groups())
            if ammo > capacity:
                raise SemanticGateClosed("campaign map fleet ammo exceeds capacity")
            anchor_value = anchor_matches[0].raw.get("anchor_world_position")
            if not isinstance(anchor_value, dict):
                raise SemanticGateClosed("campaign map fleet world anchor is absent")
            anchor = tuple(
                self._finite_number(
                    anchor_value.get(axis), "campaign map fleet world anchor." + axis
                )
                for axis in ("x", "y", "z")
            )
            distances = sorted(
                (
                    sum((anchor[index] - world[index]) ** 2 for index in range(3)),
                    coordinate,
                )
                for coordinate, world in cell_world_positions.items()
            )
            if not distances or distances[0][0] > 0.05 ** 2:
                raise SemanticGateClosed("campaign map fleet world anchor is unmatched")
            if (
                len(distances) > 1
                and abs(distances[1][0] - distances[0][0]) <= 0.05 ** 2
            ):
                raise SemanticGateClosed("campaign map fleet world anchor is ambiguous")
            matched_cell = cells_by_coordinate[distances[0][1]]
            if matched_cell.node in occupied_nodes:
                raise SemanticGateClosed("campaign map fleet location is ambiguous")
            fleets.append(
                CampaignMapFleetState(
                    marker=marker,
                    node=matched_cell.node,
                    ammo=ammo,
                    ammo_capacity=capacity,
                )
            )
            occupied_nodes.add(matched_cell.node)

        fleet_status_root = (
            "LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)"
        )
        fleet_number_path = (
            fleet_status_root + "/top_stage/msg_panel/fleet_info/number"
        )
        fleet_number_matches = tuple(
            item for item in active_texts if item.path == fleet_number_path
        )
        if (
            len(fleet_number_matches) != 1
            or re.fullmatch(
                r"[12]", fleet_number_matches[0].text.strip()
            ) is None
        ):
            raise SemanticGateClosed(
                "campaign map displayed fleet index is absent or ambiguous"
            )
        displayed_fleet_index = int(fleet_number_matches[0].text.strip())

        roster_icon_pattern = re.compile(
            re.escape(fleet_status_root)
            + r"/left_stage/fleet/(?:vanguard|main)/shiptpl\(Clone\)"
            + r"/icon_bg/icon$"
        )
        roster_icons = tuple(
            image
            for image in active_images
            if roster_icon_pattern.fullmatch(image.path) is not None
        )
        roster_sprites = tuple(sorted(image.sprite for image in roster_icons))
        if (
            not roster_sprites
            or len(roster_sprites) > 6
            or any(
                re.fullmatch(r"[A-Za-z0-9_]+", sprite) is None
                for sprite in roster_sprites
            )
        ):
            raise SemanticGateClosed(
                "campaign map displayed fleet roster is incomplete"
            )
        current_marker_candidates = []
        for marker in fleet_markers:
            marker_sprite = marker.removeprefix("cell_fleet_")
            matches = sum(sprite == marker_sprite for sprite in roster_sprites)
            if matches > 1:
                raise SemanticGateClosed(
                    "campaign map current fleet roster identity is ambiguous"
                )
            if matches == 1:
                current_marker_candidates.append(marker)
        if len(current_marker_candidates) != 1:
            raise SemanticGateClosed(
                "campaign map current fleet marker is absent or ambiguous"
            )
        current_fleet_marker = current_marker_candidates[0]
        current_fleet_node = next(
            fleet.node for fleet in fleets
            if fleet.marker == current_fleet_marker
        )
        fighting_nodes = tuple(
            enemy.node for enemy in enemies if enemy.fighting
        )
        if fighting_nodes and fighting_nodes != (current_fleet_node,):
            raise SemanticGateClosed(
                "campaign map fighting enemy disagrees with current fleet"
            )

        return CampaignMapState(
            generation=max(button_state.generation, ui_state.generation),
            stage_code=stage_code,
            rows=rows,
            columns=columns,
            cells=tuple(
                cells_by_coordinate[key] for key in sorted(cells_by_coordinate)
            ),
            land_nodes=tuple(
                self._campaign_map_node(row, column) for row, column in land
            ),
            fleets=tuple(sorted(fleets, key=lambda item: (item.node, item.marker))),
            enemies=tuple(
                sorted(enemies, key=lambda item: (item.row, item.column, item.object_id))
            ),
            pickups=tuple(
                sorted(pickups, key=lambda item: (item.row, item.column, item.kind))
            ),
            displayed_fleet_index=displayed_fleet_index,
            current_fleet_marker=current_fleet_marker,
            current_fleet_roster_sprites=roster_sprites,
        )

    def campaign_is_in_map(self) -> bool:
        """Prove an exact map root or one reviewed non-map startup surface."""

        try:
            self._campaign_map_entry_state_once()
        except SemanticGateClosed:
            pass
        else:
            return True

        state = self.read_state()
        non_map_targets = (
            "login/enter",
            "event-list/page/back",
            "main/battle",
            "campaign-menu/normal",
            "campaign-menu/page/back",
            "task/page/back",
            "reward/page/back",
            "commission/page/back",
            "mail/page/back",
            "build/page/start",
            "build/page/back",
            "dorm-menu/page/root",
            "dorm/page/back",
            "research-menu/page/back",
            "research/page/back",
            "tactical/page/back",
        )
        observed = tuple(
            semantic_id
            for semantic_id in non_map_targets
            if self._matches(state, semantic_id)
        )
        if observed:
            return False
        raise SemanticGateClosed("campaign startup surface is not reviewed")

    def campaign_page_state(self) -> CampaignPageState:
        """Read the visible chapter and stage labels without enabling a stage click."""

        button_state = self.read_state()
        back = self._unique(button_state, "campaign-menu/page/back")
        if not back.actionable or self._blocking_rules(
            button_state, "campaign-menu/page/back"
        ):
            raise SemanticGateClosed("campaign page identity is not proven")
        if self.exists("campaign-menu/normal"):
            raise SemanticGateClosed("campaign entrance is not a chapter page")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("campaign snapshots are not coherent")

        title_path = "LevelMainScene(Clone)/top/top_chapter/title_chapter/name"
        chapter_titles = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(title_path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        if len(chapter_titles) != 1:
            raise SemanticGateClosed("campaign chapter title is absent or ambiguous")

        prefix = "LevelMainScene(Clone)/float/levels/items/Chapter_"
        stage_control = re.compile(
            re.escape(prefix) + r"([1-9][0-9]*)/main$"
        )
        stage_buttons = []
        for button in button_state.buttons:
            match = stage_control.search(button.path)
            if match is None or button.name != "main":
                continue
            if (
                not button.active_in_hierarchy
                or not button.active_and_enabled
                or button.bounds is None
            ):
                continue
            stage_buttons.append((int(match.group(1)), button))
        stage_buttons.sort(key=lambda item: item[0])
        if not stage_buttons or len({item[0] for item in stage_buttons}) != len(
            stage_buttons
        ):
            raise SemanticGateClosed("campaign stage buttons are absent or ambiguous")

        stages = []
        for stage_id, button in stage_buttons:
            root = button.path + "/info/bk/title_form/"
            fields: Dict[str, TextState] = {}
            for field in ("title_index", "title"):
                matches = tuple(
                    item
                    for item in ui_state.texts
                    if item.path == root + field
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "campaign stage text is absent or ambiguous: " + field
                    )
                fields[field] = matches[0]
            code_match = re.fullmatch(
                r"([0-9]+)[\-–—]([0-9]+)", fields["title_index"].text.strip()
            )
            title = fields["title"].text.strip()
            if code_match is None or not title:
                raise SemanticGateClosed("campaign stage text is malformed")
            chapter, stage = map(int, code_match.groups())
            if stage_id != chapter * 100 + stage:
                raise SemanticGateClosed("campaign stage identity is inconsistent")
            stages.append(
                CampaignStageState(
                    stage_id=stage_id,
                    stage_code="{0}-{1}".format(chapter, stage),
                    title=title,
                    button=button,
                )
            )
        return CampaignPageState(
            generation=button_state.generation,
            chapter_name=chapter_titles[0].text.strip(),
            stages=tuple(stages),
        )

    def campaign_mode_switch_state(self) -> str:
        """Return the exact destination exposed by the normal/hard switch."""

        state = self.read_state()
        controls = {
            "hard": (
                "btn_elite",
                "LevelMainScene(Clone)/main/left_chapter/buttons/btn_elite",
            ),
            "normal": (
                "btn_normal",
                "LevelMainScene(Clone)/main/left_chapter/buttons/btn_normal",
            ),
        }
        observed = []
        for destination, (name, suffix) in controls.items():
            matches = tuple(
                button
                for button in state.buttons
                if button.name == name
                and button.path.endswith(suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("campaign mode switch is ambiguous")
            if matches:
                observed.append(destination)
        if len(observed) != 1:
            raise SemanticGateClosed("campaign mode switch is absent or ambiguous")
        return observed[0]

    def campaign_oil(self) -> int:
        """Read the exact global oil counter on a proven campaign page."""

        return self._retry_transition_read(self._campaign_oil_once)

    def _campaign_oil_once(self) -> int:
        """Read the oil counter from one fully proven campaign generation."""

        self.campaign_page_state()
        state = self.read_ui_state()
        suffix = "Overlay/UIMain/ResPanel(Clone)/frame/oil/oil_value"
        matches = tuple(
            item
            for item in state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign oil counter is absent or ambiguous")
        return int(matches[0].text.strip())

    def campaign_page_is_normal(self) -> bool:
        if self.campaign_menu_is_entry():
            return False
        try:
            self.campaign_page_state()
        except SemanticTargetMissing:
            return False
        return True

    def campaign_stage_state(self, stage_code: str) -> CampaignStageState:
        """Return one exact visible stage from the typed campaign page."""

        if re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", stage_code) is None:
            raise SemanticGateClosed("campaign stage code is not canonical")
        matches = tuple(
            stage
            for stage in self.campaign_page_state().stages
            if stage.stage_code == stage_code
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign stage is absent or ambiguous")
        return matches[0]

    def campaign_stage_actionable(self, stage_code: str) -> bool:
        return self.campaign_stage_state(stage_code).button.actionable

    def campaign_preparation_state(
        self, stage_code: str
    ) -> Optional[CampaignPreparationState]:
        """Return the one exact pre-sortie layer, or None before it appears."""

        state = self.read_state()
        map_present = any(
            button.name in ("start_button", "btnBack")
            and "LevelStageInfoView(Clone)/panel/" in button.path
            and button.active_in_hierarchy
            for button in state.buttons
        )
        fleet_present = any(
            "LevelFleetSelectView(Clone)/panel/Fixed/" in button.path
            and button.active_in_hierarchy
            for button in state.buttons
        )
        if map_present and fleet_present:
            raise SemanticGateClosed(
                "campaign preparation layers are simultaneously active"
            )
        if fleet_present:
            return self.campaign_fleet_preparation_state(stage_code)
        if map_present:
            return self.campaign_map_preparation_state(stage_code)
        return None

    def campaign_map_preparation_state(
        self, stage_code: str
    ) -> CampaignPreparationState:
        """Read one exact ALAS MAP_PREPARATION surface for the selected stage."""

        return self._retry_transition_read(
            lambda: self._campaign_map_preparation_state_once(stage_code)
        )

    def _campaign_map_preparation_state_once(
        self, stage_code: str
    ) -> CampaignPreparationState:
        if re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", stage_code) is None:
            raise SemanticGateClosed("campaign stage code is not canonical")
        button_state = self.read_state()
        proceed = self._unique(button_state, "campaign/map-preparation/proceed")
        cancel = self._unique(button_state, "campaign/map-preparation/cancel")
        for semantic_id, button in (
            ("campaign/map-preparation/proceed", proceed),
            ("campaign/map-preparation/cancel", cancel),
        ):
            if (
                not button.active_in_hierarchy
                or not button.active_and_enabled
                or not button.interactable
                or button.point is None
                or button.bounds is None
                or self._blocking_rules(button_state, semantic_id)
            ):
                raise SemanticGateClosed(
                    "campaign map-preparation controls are not proven"
                )

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "campaign map-preparation snapshots are not coherent"
            )
        root = "LevelStageInfoView(Clone)/panel/title_form/"
        title_indexes = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(root + "title_index")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        titles = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(root + "title")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        if len(title_indexes) != 1 or len(titles) != 1:
            raise SemanticGateClosed(
                "campaign map-preparation stage identity is absent or ambiguous"
            )
        match = re.fullmatch(
            r"([1-9][0-9]*)[\-–—]([1-9][0-9]*)\s*",
            title_indexes[0].text.strip(),
        )
        observed_stage = (
            "{0}-{1}".format(*match.groups()) if match is not None else None
        )
        if observed_stage != stage_code:
            raise SemanticGateClosed(
                "campaign map-preparation stage identity changed"
            )
        return CampaignPreparationState(
            generation=button_state.generation,
            kind="map",
            stage_code=stage_code,
            title=titles[0].text.strip(),
            proceed_button=proceed,
            cancel_button=cancel,
        )

    def click_campaign_map_preparation(self, stage_code: str) -> ActionReceipt:
        """Advance from stage details to fleet preparation, never to sortie."""

        observed = self.campaign_map_preparation_state(stage_code)
        target = observed.proceed_button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "campaign map-preparation proceed is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/map-preparation/proceed",
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def cancel_campaign_map_preparation(self, stage_code: str) -> ActionReceipt:
        """Close the exact stage-detail preparation without advancing."""

        observed = self.campaign_map_preparation_state(stage_code)
        target = observed.cancel_button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "campaign map-preparation cancel is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/map-preparation/cancel",
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_fleet_preparation_state(
        self, stage_code: str
    ) -> CampaignPreparationState:
        """Read exact fleet preparation, including its separately gated sortie."""

        return self._retry_transition_read(
            lambda: self._campaign_fleet_preparation_state_once(stage_code)
        )

    def _campaign_fleet_preparation_state_once(
        self, stage_code: str
    ) -> CampaignPreparationState:
        match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", stage_code)
        if match is None:
            raise SemanticGateClosed("campaign stage code is not canonical")
        stage_id = int(match.group(1)) * 100 + int(match.group(2))
        button_state = self.read_state()
        cancel = self._unique(
            button_state, "campaign/fleet-preparation/cancel"
        )
        if (
            not cancel.active_in_hierarchy
            or not cancel.active_and_enabled
            or not cancel.interactable
            or cancel.point is None
            or cancel.bounds is None
            or self._blocking_rules(
                button_state, "campaign/fleet-preparation/cancel"
            )
        ):
            raise SemanticGateClosed(
                "campaign fleet-preparation cancel is not proven"
            )
        sortie = self._unique(
            button_state, "campaign/fleet-preparation/sortie"
        )
        if (
            not sortie.actionable
            or self._blocking_rules(
                button_state, "campaign/fleet-preparation/sortie"
            )
        ):
            raise SemanticGateClosed(
                "campaign fleet-preparation sortie is not proven"
            )
        stage_path = (
            "LevelMainScene(Clone)/float/levels/items/Chapter_{0}/main".format(
                stage_id
            )
        )
        stage_buttons = tuple(
            button
            for button in button_state.buttons
            if button.name == "main"
            and button.path.endswith(stage_path)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if len(stage_buttons) != 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation stage underlay is absent or ambiguous"
            )

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "campaign fleet-preparation snapshots are not coherent"
            )
        fleet_titles = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(
                "LevelFleetSelectView(Clone)/panel/Fixed/title/Image/text"
            )
            and item.text.strip() == "舰队选择"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        title_root = stage_path + "/info/bk/title_form/"
        title_indexes = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(title_root + "title_index")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        titles = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(title_root + "title")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        if len(fleet_titles) != 1 or len(title_indexes) != 1 or len(titles) != 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation identity is absent or ambiguous"
            )
        observed = re.fullmatch(
            r"([1-9][0-9]*)[\-–—]([1-9][0-9]*)\s*",
            title_indexes[0].text.strip(),
        )
        observed_stage = (
            "{0}-{1}".format(*observed.groups())
            if observed is not None
            else None
        )
        if observed_stage != stage_code:
            raise SemanticGateClosed(
                "campaign fleet-preparation stage identity changed"
            )
        return CampaignPreparationState(
            generation=button_state.generation,
            kind="fleet",
            stage_code=stage_code,
            title=titles[0].text.strip(),
            proceed_button=sortie,
            cancel_button=cancel,
        )

    @staticmethod
    def _campaign_fleet_row_definition(
        row_key: str,
    ) -> Tuple[str, str, str]:
        definitions = {
            "fleet1": (
                "campaign/fleet-preparation/fleet/1",
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/1",
                "surface",
            ),
            "fleet2": (
                "campaign/fleet-preparation/fleet/2",
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/2",
                "surface",
            ),
            "submarine": (
                "campaign/fleet-preparation/submarine/1",
                "LevelFleetSelectView(Clone)/panel/ShipList/sub/1",
                "submarine",
            ),
        }
        try:
            return definitions[row_key]
        except KeyError as exc:
            raise SemanticGateClosed(
                "campaign fleet row is not reviewed: {0}".format(row_key)
            ) from exc

    def campaign_fleet_selection_state(
        self, stage_code: str
    ) -> CampaignFleetSelectionState:
        """Read the closed fleet-selection panel and its gated sortie target."""

        return self._retry_transition_read(
            lambda: self._campaign_fleet_selection_state_once(stage_code),
            attempts=12,
        )

    def _campaign_fleet_selection_state_once(
        self, stage_code: str
    ) -> CampaignFleetSelectionState:
        preparation = self._campaign_fleet_preparation_state_once(stage_code)
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.image_truncated
            or ui_state.method_mask & 0x8 == 0
        ):
            raise SemanticGateClosed(
                "campaign fleet-selection snapshots are incomplete"
            )
        visible_options = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.path.endswith(
                tuple(
                    "LevelFleetSelectView(Clone)/mask/list/item{0}".format(index)
                    for index in range(1, 7)
                )
            )
        )
        if visible_options:
            raise SemanticGateClosed(
                "campaign fleet-selection dropdown is still open"
            )

        numerals = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
        rows = []
        for row_key in ("fleet1", "fleet2", "submarine"):
            semantic_root, path_root, row_kind = self._campaign_fleet_row_definition(
                row_key
            )
            select_button = self._unique(button_state, semantic_root + "/select")
            clear_button = self._unique(button_state, semantic_root + "/clear")
            for semantic_id, button in (
                (semantic_root + "/select", select_button),
                (semantic_root + "/clear", clear_button),
            ):
                if not button.actionable or self._blocking_rules(
                    button_state, semantic_id
                ):
                    raise SemanticGateClosed(
                        "campaign fleet row input is not proven: " + row_key
                    )

            names = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(path_root + "/bg/name")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(names) > 1:
                raise SemanticGateClosed(
                    "campaign fleet row name is ambiguous: " + row_key
                )
            icons = tuple(
                image
                for image in ui_state.images
                if "/" + path_root + "/" in image.path
                and image.path.endswith("/icon_bg/icon")
                and image.name == "icon"
                and image.sprite
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
            )
            level_texts = tuple(
                text
                for text in ui_state.texts
                if "/" + path_root + "/" in text.path
                and text.path.endswith("/icon_bg/lv/Text")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
            )
            maximum_ships = 3 if row_kind == "submarine" else 6
            if (
                len(icons) != len(level_texts)
                or len(icons) > maximum_ships
            ):
                raise SemanticGateClosed(
                    "campaign fleet row ship identity is inconsistent: " + row_key
                )
            levels = tuple(sorted(int(text.text.strip()) for text in level_texts))
            if any(level < 1 or level > 125 for level in levels):
                raise SemanticGateClosed(
                    "campaign fleet row level is outside the pinned range"
                )

            selected_fleet = None
            if levels:
                if len(names) != 1:
                    raise SemanticGateClosed(
                        "campaign fleet row selection name is absent: " + row_key
                    )
                normalized = re.sub(r"\s+", "", names[0].text)
                pattern = (
                    r"潜艇编队([一二三四五六])"
                    if row_kind == "submarine"
                    else r"第([一二三四五六])舰队"
                )
                match = re.fullmatch(pattern, normalized)
                if match is None:
                    raise SemanticGateClosed(
                        "campaign fleet row selection name is malformed: " + row_key
                    )
                selected_fleet = numerals[match.group(1)]
            rows.append(
                CampaignFleetRowState(
                    row_key=row_key,
                    selected_fleet=selected_fleet,
                    ship_levels=levels,
                    select_button=select_button,
                    clear_button=clear_button,
                )
            )

        def exact_text(suffix: str, pattern: str) -> re.Match[str]:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "campaign fleet summary text is absent or ambiguous"
                )
            match = re.fullmatch(pattern, matches[0].text.strip())
            if match is None:
                raise SemanticGateClosed("campaign fleet summary text is malformed")
            return match

        surface = exact_text(
            "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/limit/number",
            r"([0-9]+)/([0-9]+)",
        )
        submarine = exact_text(
            "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/limit/number_sub",
            r"([0-9]+)/([0-9]+)",
        )
        mob = exact_text(
            "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/cost_limit/"
            "cost_noraml/Text",
            r"道中\(([0-9]+)\)",
        )
        boss = exact_text(
            "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/cost_limit/"
            "cost_boss/Text",
            r"旗舰\(([0-9]+)\)",
        )
        sub_cost = exact_text(
            "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/cost_limit/"
            "cost_sub/Text",
            r"潜艇\(([0-9]+)\)",
        )
        surface_counts = tuple(map(int, surface.groups()))
        submarine_counts = tuple(map(int, submarine.groups()))
        if (
            surface_counts[0] != sum(row.in_use for row in rows[:2])
            or submarine_counts[0] != int(rows[2].in_use)
            or not (0 <= surface_counts[0] <= surface_counts[1] <= 2)
            or not (0 <= submarine_counts[0] <= submarine_counts[1] <= 1)
        ):
            raise SemanticGateClosed(
                "campaign fleet counts do not match the typed rows"
            )
        return CampaignFleetSelectionState(
            generation=button_state.generation,
            stage_code=stage_code,
            title=preparation.title,
            surface_fleets=surface_counts,
            submarine_fleets=submarine_counts,
            mob_oil_cost=int(mob.group(1)),
            boss_oil_cost=int(boss.group(1)),
            submarine_oil_cost=int(sub_cost.group(1)),
            rows=tuple(rows),
            sortie_button=preparation.proceed_button,
        )

    def campaign_fleet_dropdown_state(
        self,
    ) -> Optional[CampaignFleetDropdownState]:
        """Read the exact six-option fleet dropdown, or return None if closed."""

        return self._retry_transition_read(
            self._campaign_fleet_dropdown_state_once,
            attempts=8,
        )

    def _campaign_fleet_dropdown_state_once(
        self,
    ) -> Optional[CampaignFleetDropdownState]:
        """Read one coherent Button/Toggle generation pair for the dropdown."""

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        option_matches = tuple(
            self._toggle_matches(
                ui_state, "campaign/fleet-preparation/option/{0}".format(index)
            )
            for index in range(1, 7)
        )
        if all(not matches for matches in option_matches):
            return None
        if any(len(matches) != 1 for matches in option_matches):
            raise SemanticGateClosed(
                "campaign fleet dropdown options are incomplete or ambiguous"
            )
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "campaign fleet dropdown snapshots are not coherent"
            )
        masks = tuple(
            button
            for button in button_state.buttons
            if button.name == "mask"
            and button.path.endswith("LevelFleetSelectView(Clone)/mask")
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(masks) != 1:
            raise SemanticGateClosed("campaign fleet dropdown mask is absent")
        options = tuple(matches[0] for matches in option_matches)
        for index, option in enumerate(options, 1):
            semantic_id = "campaign/fleet-preparation/option/{0}".format(index)
            if not option.actionable or self._blocking_rules(button_state, semantic_id):
                raise SemanticGateClosed(
                    "campaign fleet dropdown option is not actionable"
                )
        active_indices = []
        for index in range(1, 7):
            prefix = (
                "LevelFleetSelectView(Clone)/mask/list/item{0}/".format(index)
            )
            states = tuple(
                state
                for state in ("on", "off")
                if any(
                    text.path.endswith(prefix + state + "/mask/number")
                    and text.text.strip() == str(index)
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    for text in ui_state.texts
                )
            )
            if len(states) != 1:
                raise SemanticGateClosed(
                    "campaign fleet dropdown option state is ambiguous"
                )
            if states[0] == "on":
                active_indices.append(index)
        return CampaignFleetDropdownState(
            generation=ui_state.generation,
            active_indices=tuple(active_indices),
            options=options,
        )

    def click_campaign_fleet_row(self, row_key: str, action: str) -> ActionReceipt:
        if action not in ("select", "clear"):
            raise SemanticGateClosed("campaign fleet row action is not reviewed")
        semantic_root, _, _ = self._campaign_fleet_row_definition(row_key)
        return self.click(semantic_root + "/" + action)

    def click_campaign_fleet_option(self, index: int) -> ActionReceipt:
        if index not in range(1, 7):
            raise SemanticGateClosed("campaign fleet option is outside 1 through 6")
        if self.campaign_fleet_dropdown_state() is None:
            raise SemanticGateClosed("campaign fleet dropdown is not open")
        return self.click_toggle(
            "campaign/fleet-preparation/option/{0}".format(index)
        )

    def cancel_campaign_fleet_preparation(
        self, stage_code: str
    ) -> ActionReceipt:
        """Cancel fleet preparation without exposing or touching sortie."""

        observed = self.campaign_fleet_preparation_state(stage_code)
        target = observed.cancel_button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "campaign fleet-preparation cancel is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/fleet-preparation/cancel",
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_sortie(self, stage_code: str) -> ActionReceipt:
        """Inject the one exact fleet-preparation sortie after caller preflight."""

        observed = self.campaign_fleet_selection_state(stage_code)
        target = observed.sortie_button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("campaign sortie is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/fleet-preparation/sortie",
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_stage(self, stage_code: str) -> ActionReceipt:
        """Click one exact stage after revalidating its typed Unity identity."""

        observed = self.campaign_stage_state(stage_code)
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.name == observed.button.name
            and button.path == observed.button.path
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign stage changed before input")
        target = matches[0]
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("campaign stage is not actionable")
        if not (
            0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("campaign stage point is outside the screen")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/stage/" + stage_code,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def dorm_state(self) -> DormState:
        """Read the dorm summary without opening a mutating sub-page."""

        button_state = self.read_state()
        page = self._unique(button_state, "dorm/page/manage")
        if not page.actionable or self._blocking_rules(
            button_state, "dorm/page/manage"
        ):
            raise SemanticGateClosed("dorm page identity is not proven")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm snapshots are not coherent")

        root = "CourtYardUI(Clone)/main/"
        suffixes = {
            "slots": root + "bottomPanel/bottomleft/train_btn/Text",
            "food": root + "bottomPanel/bottomleft/feed_btn/Text",
            "comfort": root + "topPanel/btns/topright/comfortable/Text",
            "floor": root + "topPanel/btns/topright/switch/Text",
            "countdown": root + "bottomPanel/bottomleft/feed_btn/time",
        }
        values: Dict[str, str] = {}
        for key, suffix in suffixes.items():
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "dorm text is absent or ambiguous: " + key
                )
            values[key] = matches[0].text.strip()

        slots = re.fullmatch(r"([0-9]{1,2})/([1-9][0-9]?)", values["slots"])
        food = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", values["food"])
        floor = re.fullmatch(r"([1-9][0-9]*)F", values["floor"])
        if (
            slots is None
            or food is None
            or floor is None
            or re.fullmatch(r"[0-9]+", values["comfort"]) is None
        ):
            raise SemanticGateClosed("dorm summary is malformed")

        occupied_slots, total_slots = map(int, slots.groups())
        current_food, food_capacity = map(int, food.groups())
        if occupied_slots > total_slots or current_food > food_capacity:
            raise SemanticGateClosed("dorm summary is inconsistent")
        countdown = (
            None
            if not values["countdown"]
            else self.parse_countdown_seconds(values["countdown"])
        )
        return DormState(
            occupied_slots=occupied_slots,
            total_slots=total_slots,
            food=current_food,
            food_capacity=food_capacity,
            comfort=int(values["comfort"]),
            floor=int(floor.group(1)),
            food_countdown_seconds=countdown,
        )

    def dorm_feed_state(self) -> DormFeedState:
        """Read the open dorm feed panel without changing inventory."""

        button_state = self.read_state()
        close = self._unique(button_state, "dorm/feed/close")
        if not close.actionable or self._blocking_rules(
            button_state, "dorm/feed/close"
        ):
            raise SemanticGateClosed("dorm feed panel identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm feed snapshots are not coherent")

        def exact_text(path: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "dorm feed text is absent or ambiguous: " + path
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        fill = re.fullmatch(
            r"([0-9]+)/([1-9][0-9]*)",
            exact_text("BackYardFeedUI(Clone)/frame/Text"),
        )
        if fill is None:
            raise SemanticGateClosed("dorm feed capacity is malformed")
        food, capacity = map(int, fill.groups())
        if food > capacity:
            raise SemanticGateClosed("dorm feed capacity is inconsistent")

        items = []
        for item_id in range(50001, 50007):
            root = "BackYardFeedUI(Clone)/frame/food_{0}/".format(item_id)
            value_match = re.fullmatch(r"食物([1-9][0-9]*)", exact_text(root + "Text"))
            count_text = exact_text(root + "icon_bg/count")
            if value_match is None or re.fullmatch(r"[0-9]+", count_text) is None:
                raise SemanticGateClosed("dorm feed inventory is malformed")
            semantic_id = "dorm/feed/item/{0}".format(item_id)
            images = tuple(
                image
                for image in ui_state.images
                if image.name == "icon_bg"
                and image.path.endswith(root + "icon_bg")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.raycast_target
                and image.raycast_top is True
                and not image.truncated
                and image.bounds is not None
            )
            if len(images) != 1:
                raise SemanticGateClosed("dorm feed item image is absent or ambiguous")
            image = images[0]
            if self._blocking_rules(button_state, semantic_id):
                raise SemanticGateClosed("dorm feed item is not safely actionable")
            assert image.bounds is not None
            button = ButtonState(
                name=image.name,
                path=image.path,
                active_in_hierarchy=image.active_in_hierarchy,
                active_and_enabled=image.active_and_enabled,
                interactable=True,
                raycast_top=image.raycast_top,
                point=Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                ),
                bounds=image.bounds,
                raw=image.raw,
            )
            items.append(
                DormFoodState(
                    item_id=item_id,
                    value=int(value_match.group(1)),
                    count=int(count_text),
                    button=button,
                )
            )
        return DormFeedState(food=food, capacity=capacity, items=tuple(items))

    def click_dorm_food(self, item_id: int) -> ActionReceipt:
        """Click one ALAS dorm food card after exact typed revalidation."""

        if item_id not in range(50001, 50007):
            raise ValueError("dorm food item id must be 50001 through 50006")
        feed = self._retry_transition_read(
            self.dorm_feed_state,
            attempts=20,
            interval_seconds=0.25,
        )
        matches = tuple(item for item in feed.items if item.item_id == item_id)
        if len(matches) != 1:
            raise SemanticGateClosed("dorm feed item identity is ambiguous")
        target = matches[0].button
        semantic_id = "dorm/feed/item/{0}".format(item_id)
        button_state = self.read_state()
        if (
            not target.actionable
            or target.point is None
            or target.bounds is None
            or self._blocking_rules(button_state, semantic_id)
        ):
            raise SemanticGateClosed("dorm feed item is not safely actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_tactical_empty_slot(self, slot: int) -> ActionReceipt:
        """Click one visually ordered empty tactical slot after exact revalidation."""

        if slot not in range(1, 5):
            raise ValueError("tactical slot must be 1 through 4")
        state = self.read_state()
        prefix = (
            "NewNavalTacticsUI(Clone)/adpter/"
            "NewNavalTacticsStudentsPage(Clone)/"
        )
        matches = tuple(
            button
            for button in state.buttons
            if button.name in ("add", "add(Clone)")
            and button.path.endswith(prefix + button.name)
            and button.actionable
            and button.point is not None
        )
        matches = tuple(sorted(matches, key=lambda button: button.point.x))
        if len(matches) != 4:
            raise SemanticGateClosed("tactical empty slots are incomplete")
        target = matches[slot - 1]
        if self._blocking_rules(state, "tactical/slot/{0}".format(slot)):
            raise SemanticGateClosed("tactical slot input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="tactical/slot/{0}".format(slot),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        """Read visible tactical Dock candidates in ALAS grid order."""

        button_state = self.read_state()
        back = self._unique(button_state, "tactical/dock/back")
        confirm = self._unique(button_state, "tactical/dock/confirm")
        if not back.active_and_enabled or not confirm.active_and_enabled:
            raise SemanticGateClosed("tactical Dock identity is not proven")
        prefix = "DockyardUI(Clone)/main/ship_container/ships/"
        buttons = tuple(
            button
            for button in button_state.buttons
            if re.fullmatch(r"[1-9][0-9]{5,7}", button.name) is not None
            and button.path.endswith(prefix + button.name)
            and button.bounds is not None
            and button.bounds.right > 0
            and button.bounds.bottom > 0
            and button.bounds.left < self.fingerprint.width
            and button.bounds.top < 500
        )
        if not buttons or len({button.name for button in buttons}) != len(buttons):
            raise SemanticGateClosed("tactical Dock candidates are absent or ambiguous")
        buttons = tuple(
            sorted(
                buttons,
                key=lambda button: (
                    round(button.bounds.top / 50.0),
                    button.bounds.left,
                ),
            )
        )
        ui_state = self.read_text_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical Dock snapshots are not coherent")

        candidates = []
        for position, button in enumerate(buttons):
            root = button.path + "/content/"

            def exact_text(suffix: str) -> str:
                matches = tuple(
                    text
                    for text in ui_state.texts
                    if text.path == root + suffix
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    and text.bounds is not None
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "tactical Dock text is absent or ambiguous: " + suffix
                    )
                return re.sub(r"<[^>]*>", "", matches[0].text).strip()

            name = exact_text("info/name_mask/name")
            level_text = exact_text("dockyard/lv/Text")
            if not name or re.fullmatch(r"[1-9][0-9]{0,2}", level_text) is None:
                raise SemanticGateClosed("tactical Dock candidate is malformed")
            candidates.append(
                TacticalCandidateShipState(
                    position=position,
                    ship_id=int(button.name),
                    ship_name=name,
                    level=int(level_text),
                    button=button,
                )
            )
        return tuple(candidates)

    def click_tactical_ship(self, ship_id: int) -> ActionReceipt:
        candidates = self.tactical_candidate_ships()
        matches = tuple(candidate for candidate in candidates if candidate.ship_id == ship_id)
        if len(matches) != 1:
            raise SemanticGateClosed("tactical Dock ship identity changed")
        target = matches[0].button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("tactical Dock ship is not safely actionable")
        state = self.read_state()
        current = tuple(button for button in state.buttons if button.path == target.path)
        if len(current) != 1 or not current[0].actionable:
            raise SemanticGateClosed("tactical Dock ship changed before input")
        target = current[0]
        assert target.point is not None and target.bounds is not None
        if self._blocking_rules(state, "tactical/dock/ship"):
            raise SemanticGateClosed("tactical Dock ship input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="tactical/dock/ship/{0}".format(ship_id),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        """Read visible skill rows in the tactical skill-selection dialog."""

        button_state = self.read_state()
        confirm = self._unique(button_state, "tactical/skill/confirm")
        if not confirm.active_and_enabled:
            raise SemanticGateClosed("tactical skill dialog identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical skill snapshots are not coherent")
        rows = tuple(
            image
            for image in ui_state.images
            if image.name in ("skill", "skill(Clone)")
            and image.path.endswith(
                "NewNavalTacticsSkillsPage(Clone)/frame/skill_container/content/"
                + image.name
            )
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and not image.truncated
            and image.bounds is not None
            and image.bounds.bottom > 0
            and image.bounds.top < self.fingerprint.height
        )
        rows = tuple(sorted(rows, key=lambda image: image.bounds.top))
        if not rows or len(rows) > 4:
            raise SemanticGateClosed("tactical skill rows are absent or ambiguous")

        result = []
        for position, row in enumerate(rows):
            assert row.bounds is not None

            def text_with_suffix(suffix: str) -> str:
                matches = tuple(
                    text
                    for text in ui_state.texts
                    if text.path.endswith(suffix)
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    and text.bounds is not None
                    and row.bounds.contains(
                        Point(
                            (text.bounds.left + text.bounds.right) / 2.0,
                            (text.bounds.top + text.bounds.bottom) / 2.0,
                        )
                    )
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "tactical skill text is absent or ambiguous: " + suffix
                    )
                return re.sub(r"<[^>]*>", "", matches[0].text).strip()

            name = text_with_suffix("/name/Text/subText")
            level = text_with_suffix("/name/level")
            next_value = text_with_suffix("/next")
            if not name or re.fullmatch(r"Lv\.[1-9][0-9]?", level) is None:
                raise SemanticGateClosed("tactical skill row is malformed")
            result.append(
                TacticalSkillState(
                    position=position,
                    name=name,
                    level_text=next_value,
                    max_level=next_value.upper() == "MAX",
                    button=ButtonState(
                        name=row.name,
                        path=row.path,
                        active_in_hierarchy=row.active_in_hierarchy,
                        active_and_enabled=row.active_and_enabled,
                        interactable=True,
                        raycast_top=row.raycast_top,
                        point=Point(
                            (row.bounds.left + row.bounds.right) / 2.0,
                            (row.bounds.top + row.bounds.bottom) / 2.0,
                        ),
                        bounds=row.bounds,
                        raw=row.raw,
                    ),
                )
            )
        return tuple(result)

    def click_tactical_skill(self, position: int) -> ActionReceipt:
        skills = self.tactical_skills()
        matches = tuple(skill for skill in skills if skill.position == position)
        if len(matches) != 1 or matches[0].max_level:
            raise SemanticGateClosed("tactical skill is absent or already maxed")
        target = matches[0].button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("tactical skill is not safely actionable")
        state = self.read_state()
        if self._blocking_rules(state, "tactical/skill/item"):
            raise SemanticGateClosed("tactical skill input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="tactical/skill/{0}".format(position),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        """Read visible tactical books in the same order as ALAS BOOKS_GRID."""

        button_state = self.read_state()
        start = self._unique(button_state, "tactical/book/start")
        cancel = self._unique(button_state, "tactical/book/cancel")
        if not start.active_and_enabled or not cancel.active_and_enabled:
            raise SemanticGateClosed("tactical book dialog identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical book snapshots are not coherent")

        root = "NewNavalTacticsLessonPage(Clone)/items/scorll/content/"
        items = tuple(
            image
            for image in ui_state.images
            if image.name in ("item", "item(Clone)")
            and image.path.endswith(root + image.name)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.raycast_top is True
            and not image.truncated
            and image.bounds is not None
            and image.bounds.right > 0
            and image.bounds.bottom > 0
            and image.bounds.left < self.fingerprint.width
            and image.bounds.top < self.fingerprint.height
        )
        items = tuple(
            sorted(
                items,
                key=lambda image: (
                    round(image.bounds.top / 50.0),
                    image.bounds.left,
                ),
            )
        )
        if not items or len(items) > 12:
            raise SemanticGateClosed("tactical book items are absent or ambiguous")

        def center(bounds: Bounds) -> Point:
            return Point(
                (bounds.left + bounds.right) / 2.0,
                (bounds.top + bounds.bottom) / 2.0,
            )

        books = []
        seen_ids = set()
        for position, item in enumerate(items):
            assert item.bounds is not None
            icon_matches = tuple(
                image
                for image in ui_state.images
                if image.name == "icon"
                and image.path.startswith(item.path + "/icon_bg/")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and item.bounds.contains(center(image.bounds))
                and re.fullmatch(r"160[012][1-4]", image.sprite) is not None
            )
            count_matches = tuple(
                text
                for text in ui_state.texts
                if text.name == "count"
                and text.path.startswith(item.path + "/icon_bg/")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and item.bounds.contains(center(text.bounds))
                and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
            )
            addition_matches = tuple(
                text
                for text in ui_state.texts
                if text.name == "addition"
                and text.path.startswith(item.path + "/")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and item.bounds.left <= center(text.bounds).x <= item.bounds.right
                and item.bounds.top - 10 <= center(text.bounds).y <= item.bounds.bottom
            )
            if (
                len(icon_matches) != 1
                or len(count_matches) != 1
                or len(addition_matches) != 1
            ):
                raise SemanticGateClosed(
                    "tactical book identity text is absent or ambiguous"
                )
            item_id = icon_matches[0].sprite
            if item_id in seen_ids:
                raise SemanticGateClosed("tactical book item ID is duplicated")
            seen_ids.add(item_id)
            addition = addition_matches[0].text.strip()
            if addition not in ("", "EXP150%", "EXP200%"):
                raise SemanticGateClosed("tactical book EXP bonus is malformed")
            selected = any(
                image.name == "selected"
                and image.path.startswith(item.path + "/selected")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and item.bounds.contains(center(image.bounds))
                for image in ui_state.images
            )
            books.append(
                TacticalBookState(
                    position=position,
                    item_id=item_id,
                    genre=int(item_id[-2]) + 1,
                    tier=int(item_id[-1]),
                    exp_bonus=bool(addition),
                    count=int(count_matches[0].text.strip()),
                    selected=selected,
                    image=item,
                )
            )
        if sum(book.selected for book in books) != 1:
            raise SemanticGateClosed("tactical selected book is absent or ambiguous")
        return tuple(books)

    def click_tactical_book(self, position: int) -> ActionReceipt:
        books = self.tactical_books()
        matches = tuple(book for book in books if book.position == position)
        if len(matches) != 1 or matches[0].count <= 0:
            raise SemanticGateClosed("tactical book is absent or exhausted")
        target = matches[0].image
        if target.raycast_top is not True or target.bounds is None:
            raise SemanticGateClosed("tactical book is not safely actionable")
        state = self.read_state()
        if self._blocking_rules(state, "tactical/book/item"):
            raise SemanticGateClosed("tactical book input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="tactical/book/{0}".format(position),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        """Read the five visible research cards from typed Unity state."""

        button_state = self.read_state()
        back = self._unique(button_state, "research/page/back")
        if not back.actionable or self._blocking_rules(
            button_state, "research/page/back"
        ):
            raise SemanticGateClosed("research page identity is not proven")
        indexed = []
        pattern = re.compile(
            r"(?:^|/)TechnologyUI\(Clone\)/main/base_page/srcoll_rect/"
            r"content/([1-5])$"
        )
        for button in button_state.buttons:
            match = pattern.search(button.path)
            if (
                match is not None
                and button.name == match.group(1)
                and button.actionable
                and button.point is not None
                and 0 <= button.point.x < self.fingerprint.width
                and 0 <= button.point.y < self.fingerprint.height
            ):
                indexed.append((int(match.group(1)), button))
        if len(indexed) != 5 or len({item[0] for item in indexed}) != 5:
            raise SemanticGateClosed("research project Buttons are incomplete")
        indexed.sort(key=lambda item: (item[1].point.x, item[0]))

        ui_state = self.read_ui_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed research Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("research snapshots are not coherent")

        def text_at(path: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path == path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "research project text is absent or ambiguous: " + path
                )
            return matches[0].text.strip()

        status_texts = {
            "查看详情": ResearchProjectStatus.DETAIL,
            "进行中": ResearchProjectStatus.RUNNING,
            "等待中": ResearchProjectStatus.WAITING,
            "研究完成": ResearchProjectStatus.FINISHED,
        }
        projects = []
        for slot, (unity_index, button) in enumerate(indexed, start=1):
            root = button.path + "/frame/"
            code = text_at(root + "name_bg/Text")
            subtitle = text_at(root + "sub_name")
            marker = re.sub(r"<[^>]*>", "", text_at(root + "marks/Text")).strip()
            try:
                status = status_texts[marker]
            except KeyError as exc:
                raise SemanticGateClosed(
                    "research project status is not reviewed: " + marker
                ) from exc
            duration = self.parse_countdown_seconds(text_at(root + "marks/time"))
            version_path = root + "top/label/version"
            versions = tuple(
                image
                for image in ui_state.images
                if image.path == version_path
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
            )
            if len(versions) != 1:
                raise SemanticGateClosed("research project series is ambiguous")
            version = re.fullmatch(r"version_([1-9][0-9]*)", versions[0].sprite)
            if version is None or not code:
                raise SemanticGateClosed("research project identity is malformed")
            projects.append(
                ResearchProjectState(
                    slot=slot,
                    unity_index=unity_index,
                    code=code,
                    subtitle=subtitle,
                    series=int(version.group(1)),
                    status=status,
                    duration_seconds=duration,
                    button=button,
                )
            )
        return tuple(projects)

    def click_research_project(self, slot: int) -> ActionReceipt:
        if slot not in range(1, 6):
            raise ValueError("research project slot must be 1 through 5")
        projects = self.research_projects()
        matches = tuple(project for project in projects if project.slot == slot)
        if len(matches) != 1:
            raise SemanticGateClosed("research project slot identity changed")
        expected = matches[0]
        state = self.read_state()
        current = tuple(
            button
            for button in state.buttons
            if button.path == expected.button.path
            and button.name == str(expected.unity_index)
        )
        if len(current) != 1 or not current[0].actionable:
            raise SemanticGateClosed("research project changed before input")
        target = current[0]
        if self._blocking_rules(state, "research/project/{0}".format(slot)):
            raise SemanticGateClosed("research project input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="research/project/{0}".format(slot),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _research_status_from_text(value: str) -> ResearchProjectStatus:
        plain = re.sub(r"<[^>]*>", "", value).strip()
        statuses = {
            "查看详情": ResearchProjectStatus.DETAIL,
            "进行中": ResearchProjectStatus.RUNNING,
            "等待中": ResearchProjectStatus.WAITING,
            "研究完成": ResearchProjectStatus.FINISHED,
        }
        try:
            return statuses[plain]
        except KeyError as exc:
            raise SemanticGateClosed(
                "research status is not reviewed: " + plain
            ) from exc

    def research_detail_state(self) -> ResearchDetailState:
        """Read the selected research detail and its exact action state."""

        button_state = self.read_state()
        root_button = self._unique(button_state, "research/detail/root")
        if not root_button.actionable or self._blocking_rules(
            button_state, "research/detail/root"
        ):
            raise SemanticGateClosed("research detail identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("research detail snapshots are incomplete")

        root = (
            "TechnologyUI(Clone)/main/base_page/selecte_panel/"
            "technology_card/frame/"
        )
        panel = "TechnologyUI(Clone)/main/base_page/selecte_panel/"

        def exact_text(suffix: str) -> str:
            path = root + suffix
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "research detail text is absent or ambiguous: " + suffix
                )
            return matches[0].text.strip()

        code = exact_text("name_bg/Text")
        subtitle = exact_text("sub_name")

        def panel_text(suffix: str) -> str:
            path = panel + suffix
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "research detail text is absent or ambiguous: " + suffix
                )
            return matches[0].text.strip()

        duration = self.parse_countdown_seconds(panel_text("timer/bg/Text"))
        resource = re.fullmatch(
            r"([0-9]+)/([1-9][0-9]*)",
            re.sub(r"<[^>]*>", "", panel_text("consume_panel/bg/container/item_tpl/icon_bg/count")),
        )
        if resource is None or not code:
            raise SemanticGateClosed("research detail resource state is malformed")
        owned, required = map(int, resource.groups())
        resource_path = panel + "consume_panel/bg/container/item_tpl/icon_bg/icon"
        icons = tuple(
            item
            for item in ui_state.images
            if item.path.endswith(resource_path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(icons) != 1 or re.fullmatch(r"[A-Za-z0-9_.-]+", icons[0].sprite) is None:
            raise SemanticGateClosed("research detail resource identity is ambiguous")

        action_ids = {
            "start": "research/detail/start",
            "stop": "research/detail/stop",
            "finish": "research/detail/finish",
            "queue": "research/detail/queue",
        }
        actions = {}
        for key, semantic_id in action_ids.items():
            matches = self._matches(button_state, semantic_id)
            if len(matches) > 1:
                raise SemanticGateClosed("research detail action is ambiguous: " + key)
            if key == "queue":
                actions[key] = self._research_queue_add_proven(
                    button_state, ui_state=ui_state
                )
            else:
                actions[key] = bool(matches and matches[0].actionable)
        return ResearchDetailState(
            code=code,
            subtitle=subtitle,
            duration_seconds=duration,
            resource_id=icons[0].sprite,
            resource_owned=owned,
            resource_required=required,
            requirement=re.sub(
                r"<[^>]*>", "", panel_text(
                    "consume_panel/bg/task_panel/slider/Text"
                )
            ).strip(),
            can_start=actions["start"] and owned >= required,
            can_queue=actions["queue"],
            is_running=actions["stop"],
            is_finished=actions["finish"],
        )

    def _research_queue_add_proven(
        self, state: OracleState, ui_state: Optional[UIState] = None
    ) -> bool:
        matches = self._matches(state, "research/detail/queue")
        if len(matches) > 1:
            raise SemanticGateClosed("research queue-add target is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, "research/detail/queue"):
            return False
        if target.actionable:
            return True
        if (
            target.raycast_top is not None
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False

        # The live 9.7.10 join_btn delegates raycasts to its same-path Image,
        # so the observer cannot assign a top-raycast result to the parent
        # Button.  Admit only this reviewed structure while a concurrently
        # actionable stop button proves that the selected project is running.
        stop = self._matches(state, "research/detail/stop")
        root = self._matches(state, "research/detail/root")
        if (
            len(stop) != 1
            or not stop[0].actionable
            or len(root) != 1
            or not root[0].actionable
        ):
            return False
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("research queue-add snapshots are incomplete")
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == "join_btn"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        if len(images) > 1:
            raise SemanticGateClosed("research queue-add image is ambiguous")
        return len(images) == 1

    def research_queue_add_available(self) -> bool:
        state = self.read_state()
        return self._research_queue_add_proven(state)

    def click_research_queue_add(self) -> ActionReceipt:
        state = self.read_state()
        target = self._unique(state, "research/detail/queue")
        if not self._research_queue_add_proven(state):
            raise SemanticGateClosed("research queue-add input is not proven")
        assert target.point is not None
        assert target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before research queue-add")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed after research queue-add")
        return ActionReceipt(
            semantic_id="research/detail/queue",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _dorm_back_delegated_raycast_proven(
        self, state: OracleState, ui_state: Optional[UiState] = None
    ) -> bool:
        matches = self._matches(state, "dorm/page/back")
        if len(matches) > 1:
            raise SemanticGateClosed("dorm back target is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, "dorm/page/back"):
            return False
        if target.actionable:
            return True
        if (
            target.raycast_top is not False
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False

        # CourtYardUI's reviewed return control delegates raycasts to the
        # decorative Images on the Button and its children.  Keep this escape
        # hatch local to the exact path and exact 9.7.10 sprite composition.
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("dorm back snapshots are incomplete")
        expected = {
            target.path: "back_btn_bg",
            target.path + "/Image": "return",
            target.path + "/s": "back_btn_s1",
        }
        proven = set()
        for image in ui_state.images:
            sprite = expected.get(image.path)
            if sprite is None or image.sprite != sprite:
                continue
            if (
                not image.active_in_hierarchy
                or not image.active_and_enabled
                or not image.raycast_target
                or image.truncated
                or image.bounds is None
                or not image.bounds.contains(target.point)
            ):
                return False
            if image.path in proven:
                raise SemanticGateClosed("dorm back image is ambiguous")
            proven.add(image.path)
        return proven == set(expected)

    def _dorm_empty_food_cancel_proven(
        self, state: OracleState, ui_state: Optional[UiState] = None
    ) -> bool:
        matches = self._matches(state, "dorm/empty-food/cancel")
        if len(matches) > 1:
            raise SemanticGateClosed("dorm empty-food cancel target is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, "dorm/empty-food/cancel"):
            return False
        if (
            target.raycast_top is not None
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("dorm empty-food snapshots are incomplete")
        root = target.path.rsplit("/frame/cancel_btn", 1)[0]
        expected = {
            target.path: "btn_yellow",
            root + "/frame/Image": "hungry",
            root + "/frame": "msg_bg",
        }
        proven = set()
        for image in ui_state.images:
            sprite = expected.get(image.path)
            if sprite is None or image.sprite != sprite:
                continue
            if (
                not image.active_in_hierarchy
                or not image.active_and_enabled
                or not image.raycast_target
                or image.truncated
                or image.bounds is None
            ):
                return False
            if image.path == target.path and not image.bounds.contains(target.point):
                return False
            if image.path in proven:
                raise SemanticGateClosed("dorm empty-food image is ambiguous")
            proven.add(image.path)
        return proven == set(expected)

    def dorm_empty_food_cancel_available(self) -> bool:
        state = self.read_state()
        return self._dorm_empty_food_cancel_proven(state)

    def _dorm_page_control_proven(
        self,
        state: OracleState,
        semantic_id: str,
        ui_state: Optional[UiState] = None,
    ) -> bool:
        if semantic_id not in ("dorm/feed", "dorm/collect"):
            raise ValueError("unsupported delegated dorm page control")
        matches = self._matches(state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed("dorm page control is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, semantic_id):
            return False
        if target.actionable:
            return True
        if (
            target.raycast_top is not False
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False
        page_back = self._matches(state, "dorm/page/back")
        manage = self._matches(state, "dorm/page/manage")
        if (
            len(page_back) != 1
            or not page_back[0].active_in_hierarchy
            or len(manage) != 1
            or not manage[0].active_in_hierarchy
        ):
            return False
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.snapshot.get("text_truncated") is not False
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("dorm page-control snapshots are incomplete")

        feed_root = target.path if semantic_id == "dorm/feed" else target.path.rsplit(
            "/rightPanel/onekey", 1
        )[0] + "/bottomPanel/bottomleft/feed_btn"
        labels = tuple(
            value
            for value in ui_state.texts
            if value.path in (feed_root + "/label", feed_root + "/Text")
            and value.active_in_hierarchy
            and value.active_and_enabled
            and not value.truncated
        )
        if len(labels) != 2:
            return False
        by_path = {value.path: value.text for value in labels}
        if by_path.get(feed_root + "/label") != "食量" or re.fullmatch(
            r"[0-9]+/[1-9][0-9]*", by_path.get(feed_root + "/Text", "")
        ) is None:
            return False

        if semantic_id == "dorm/feed":
            expected_images = {
                target.path + "/icon": "btn_feed",
                target.path + "/bg": "btn_72",
            }
            images = tuple(
                image
                for image in ui_state.images
                if image.path in expected_images
                and image.sprite == expected_images[image.path]
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and target.bounds.contains(
                    Point(
                        (image.bounds.left + image.bounds.right) / 2.0,
                        (image.bounds.top + image.bounds.bottom) / 2.0,
                    )
                )
            )
            return len(images) == len(expected_images) and len(
                {image.path for image in images}
            ) == len(expected_images)

        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == "onekey"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        if len(images) > 1:
            raise SemanticGateClosed("dorm collect image is ambiguous")
        return len(images) == 1

    def research_queue_state(self) -> ResearchQueueState:
        """Read all non-empty queue slots and the reviewed claim control."""

        button_state = self.read_state()
        back = self._unique(button_state, "research/page/back")
        ui_state = self.read_ui_state()
        queue_title = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(
                "TechnologyUI(Clone)/blur_panel/adapt/top/title_queue"
            )
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        if (
            not back.actionable
            or len(queue_title) != 1
            or ui_state.image_truncated
            or ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("research queue identity is not proven")

        def optional_text(path: str) -> Optional[str]:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("research queue text is ambiguous: " + path)
            return matches[0].text.strip() if matches else None

        entries = []
        for slot in range(1, 6):
            root = "TechnologyUI(Clone)/main/queue_page/queue_rect/content/{0}/frame/".format(slot)
            code = optional_text(root + "name_bg/Text")
            marker = optional_text(root + "marks/Text")
            remain = optional_text(root + "marks/time")
            version_path = root + "top/label/version"
            versions = tuple(
                image
                for image in ui_state.images
                if image.path.endswith(version_path)
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
            )
            if code is None and marker is None and remain is None and not versions:
                continue
            if code is None or marker is None or remain is None or len(versions) != 1:
                raise SemanticGateClosed("research queue slot is incomplete")
            version = re.fullmatch(r"version_([1-9][0-9]*)", versions[0].sprite)
            if version is None or not code:
                raise SemanticGateClosed("research queue identity is malformed")
            entries.append(
                ResearchQueueEntryState(
                    slot=slot,
                    code=code,
                    series=int(version.group(1)),
                    status=self._research_status_from_text(marker),
                    remaining_seconds=self.parse_countdown_seconds(remain),
                )
            )
        claim_matches = self._matches(button_state, "research/queue/claim")
        if len(claim_matches) > 1:
            raise SemanticGateClosed("research queue claim target is ambiguous")
        claimable = bool(claim_matches and claim_matches[0].actionable)
        if claimable and not any(
            entry.status == ResearchProjectStatus.FINISHED for entry in entries
        ):
            raise SemanticGateClosed("research queue claim state is inconsistent")
        return ResearchQueueState(tuple(entries), claimable)

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        """Read populated tactical-class slots from typed Unity controls."""

        button_state = self.read_state()
        page = self._unique(button_state, "tactical/page/back")
        if not page.active_in_hierarchy or not page.active_and_enabled:
            raise SemanticGateClosed("tactical page identity is not proven")

        prefix = (
            "NewNavalTacticsUI(Clone)/adpter/"
            "NewNavalTacticsStudentsPage(Clone)/"
        )
        ship_buttons = tuple(
            button
            for button in button_state.buttons
            if re.fullmatch(r"[1-9][0-9]{5}", button.name) is not None
            and prefix in button.path
            and button.path.endswith("/" + button.name)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
            and button.bounds.right > 0
            and button.bounds.bottom > 0
            and button.bounds.left < self.fingerprint.width
            and button.bounds.top < self.fingerprint.height
        )
        if len(ship_buttons) > 4 or len({button.name for button in ship_buttons}) != len(
            ship_buttons
        ):
            raise SemanticGateClosed("tactical slot identity is ambiguous")
        ship_buttons = tuple(sorted(ship_buttons, key=lambda button: button.bounds.left))

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical snapshots are not coherent")

        def text_in_slot(button: ButtonState, suffix: str) -> str:
            assert button.bounds is not None
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and prefix in text.path
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and button.bounds.left
                <= (text.bounds.left + text.bounds.right) / 2.0
                <= button.bounds.right
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "tactical slot text is absent or ambiguous: " + suffix
                )
            return matches[0].text.strip()

        slots = []
        for slot, button in enumerate(ship_buttons, start=1):
            ship_name = text_in_slot(button, "/content/info/name_mask/name")
            ship_level_text = text_in_slot(button, "/content/dockyard/lv/Text")
            skill_name = text_in_slot(button, "/skill/name_Text")
            skill_level_text = text_in_slot(button, "/skill/level")
            progress_text = text_in_slot(button, "/skill/next")
            timer_text = text_in_slot(button, "/timer_Text")
            progress = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", progress_text)
            if (
                not ship_name
                or not skill_name
                or re.fullmatch(r"[1-9][0-9]{0,2}", ship_level_text) is None
                or re.fullmatch(r"[1-9][0-9]?", skill_level_text) is None
                or progress is None
            ):
                raise SemanticGateClosed("tactical slot summary is malformed")
            exp_current, exp_total = map(int, progress.groups())
            if exp_current > exp_total:
                raise SemanticGateClosed("tactical skill progress is inconsistent")
            if timer_text:
                status = TacticalSlotStatus.RUNNING
                remaining_seconds: Optional[int] = self.parse_countdown_seconds(
                    timer_text
                )
            else:
                # On the reviewed page a populated slot retains its cancel
                # control and publishes an empty timer only after completion.
                cancel_buttons = tuple(
                    candidate
                    for candidate in button_state.buttons
                    if candidate.name == "cancel_btn"
                    and candidate.path.startswith(button.path.rsplit("/", 1)[0] + "/")
                    and candidate.active_in_hierarchy
                    and candidate.active_and_enabled
                    and candidate.bounds is not None
                    and button.bounds.left
                    <= (candidate.bounds.left + candidate.bounds.right) / 2.0
                    <= button.bounds.right
                )
                if len(cancel_buttons) != 1:
                    raise SemanticGateClosed(
                        "finished tactical slot marker is absent or ambiguous"
                    )
                status = TacticalSlotStatus.FINISHED
                remaining_seconds = None
            slots.append(
                TacticalSlotState(
                    slot=slot,
                    ship_id=int(button.name),
                    ship_name=ship_name,
                    ship_level=int(ship_level_text),
                    skill_name=skill_name,
                    skill_level=int(skill_level_text),
                    exp_current=exp_current,
                    exp_total=exp_total,
                    status=status,
                    remaining_seconds=remaining_seconds,
                    button=button,
                )
            )
        return tuple(slots)

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        return tuple(
            slot.remaining_seconds
            for slot in self.tactical_slots()
            if slot.status == TacticalSlotStatus.RUNNING
            and slot.remaining_seconds is not None
        )

    def _mapping(self, semantic_id: str) -> SemanticTarget:
        try:
            return self._targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic target is not mapped: {0}".format(semantic_id)
            ) from exc

    def _image_mapping(self, semantic_id: str) -> SemanticImageTarget:
        try:
            return self._image_targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic image target is not mapped: {0}".format(semantic_id)
            ) from exc

    def _toggle_mapping(self, semantic_id: str) -> SemanticToggleTarget:
        try:
            return self._toggle_targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic toggle target is not mapped: {0}".format(semantic_id)
            ) from exc

    def _toggle_matches(
        self, state: UiState, semantic_id: str
    ) -> Tuple[ToggleState, ...]:
        target = self._toggle_mapping(semantic_id)
        candidates = tuple(
            toggle
            for toggle in state.toggles
            if toggle.name == target.name
            and toggle.path.endswith(target.path_suffix)
        )
        if target.expected_child_sprite is None:
            return candidates

        matching = []
        for toggle in candidates:
            if toggle.bounds is None:
                continue
            child_images = tuple(
                image
                for image in state.images
                if not image.truncated
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
                and image.sprite == target.expected_child_sprite
                and image.path.startswith(toggle.path + "/")
                and toggle.bounds.contains(
                    Point(
                        (image.bounds.left + image.bounds.right) / 2.0,
                        (image.bounds.top + image.bounds.bottom) / 2.0,
                    )
                )
            )
            if len(child_images) == 1:
                matching.append(toggle)
            elif len(child_images) > 1:
                raise SemanticGateClosed(
                    "semantic toggle child sprite is ambiguous: {0}".format(
                        semantic_id
                    )
                )
        return tuple(matching)

    def toggle_state(self, semantic_id: str) -> ToggleState:
        state = self.read_ui_state()
        if state.method_mask & 0x1 == 0:
            raise SemanticGateClosed("typed Unity Toggle snapshot is incomplete")
        matches = self._toggle_matches(state, semantic_id)
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: {0}".format(
                    semantic_id
                )
            )
        return matches[0]

    def toggle_selected(self, semantic_id: str) -> bool:
        return self.toggle_state(semantic_id).checked

    def _build_pool_delegated_raycast_proven(
        self,
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
    ) -> bool:
        expected_sprites = {
            "build/pool/light": "light_unsel",
            "build/pool/heavy": "heavy_unsel",
            "build/pool/special": "spec_unsel",
        }
        expected_sprite = expected_sprites.get(semantic_id)
        if expected_sprite is None:
            return False
        matches = self._toggle_matches(ui_state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed("construction pool Toggle is ambiguous")
        if not matches:
            return False
        toggle = matches[0]
        if (
            toggle.checked
            or toggle.raycast_top is not None
            or not toggle.active_in_hierarchy
            or not toggle.active_and_enabled
            or not toggle.interactable
            or toggle.point is None
            or toggle.bounds is None
            or not toggle.bounds.contains(toggle.point)
            or self._blocking_rules(button_state, semantic_id)
        ):
            return False

        # The live 9.7.10 construction-pool Toggle delegates its raycast to
        # the same-path Image.  The observer consequently reports no top
        # result on either component.  Admit only an unchecked, exact pool
        # Toggle with its exact unselected sprite while the pool start Button
        # proves the surrounding page.
        page_markers = tuple(
            button
            for button in button_state.buttons
            if button.name == "start_btn"
            and button.path.endswith(
                "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/start_btn"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(page_markers) != 1:
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == toggle.path
            and image.name == "frame"
            and image.sprite == expected_sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.raycast_top is None
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(toggle.point)
        )
        if len(images) > 1:
            raise SemanticGateClosed("construction pool Image is ambiguous")
        return len(images) == 1

    def click_toggle(self, semantic_id: str) -> ActionReceipt:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if ui_state.method_mask & 0x1 == 0:
            raise SemanticGateClosed("typed Unity Toggle snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("button and toggle snapshots are not coherent")
        matches = self._toggle_matches(ui_state, semantic_id)
        delegated_build_pool = self._build_pool_delegated_raycast_proven(
            button_state, ui_state, semantic_id
        )
        if len(matches) != 1 or (
            not matches[0].actionable and not delegated_build_pool
        ):
            raise SemanticGateClosed("semantic toggle target is not actionable")
        toggle = matches[0]
        if self._blocking_rules(button_state, semantic_id):
            raise SemanticGateClosed("semantic toggle action is blocked")
        assert toggle.point is not None
        assert toggle.bounds is not None
        if not (
            0 <= toggle.point.x < self.fingerprint.width
            and 0 <= toggle.point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("semantic toggle target point is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before toggle input")
        self._tap(int(round(toggle.point.x)), int(round(toggle.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after toggle input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=ui_state.generation,
            point=toggle.point,
            bounds=toggle.bounds,
            path=toggle.path,
        )

    def _image_matches(
        self,
        state: UiState,
        semantic_id: str,
    ) -> Tuple[ImageState, ...]:
        target = self._image_mapping(semantic_id)
        direct_suffix = target.path_parent_suffix + "/Image"
        selected_suffix = target.path_parent_suffix + "/selected/Image"
        allowed_sprites = (target.selected_sprite, target.inactive_sprite)
        return tuple(
            image
            for image in state.images
            if image.name == "Image"
            and (
                image.path.endswith(direct_suffix)
                or image.path.endswith(selected_suffix)
            )
            and image.sprite in allowed_sprites
        )

    def image_state(self, semantic_id: str) -> ImageState:
        return self._retry_transition_read(
            lambda: self._image_state_once(semantic_id)
        )

    def _image_state_once(self, semantic_id: str) -> ImageState:
        state = self.read_ui_state()
        if state.image_truncated or state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed Unity Image snapshot is incomplete")
        matches = self._image_matches(state, semantic_id)
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic image target is absent or ambiguous: {0}".format(
                    semantic_id
                )
            )
        if matches[0].truncated:
            raise SemanticGateClosed("semantic image target identity is truncated")
        return matches[0]

    def image_selected(self, semantic_id: str) -> bool:
        target = self._image_mapping(semantic_id)
        image = self.image_state(semantic_id)
        if image.sprite == target.selected_sprite:
            return True
        if image.sprite == target.inactive_sprite:
            return False
        raise SemanticGateClosed("semantic image target sprite is unexpected")

    def click_image(self, semantic_id: str) -> ActionReceipt:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed Unity Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("button and image snapshots are not coherent")
        matches = self._image_matches(ui_state, semantic_id)
        if len(matches) != 1:
            raise SemanticGateClosed("semantic image target is absent or ambiguous")
        image = matches[0]
        if (
            image.truncated
            or not image.active_in_hierarchy
            or not image.active_and_enabled
            or not image.raycast_target
            or image.raycast_top is not True
            or image.bounds is None
        ):
            raise SemanticGateClosed("semantic image target is not actionable")
        if semantic_id.startswith("task/nav/"):
            page_semantic_id = "task/page/back"
            page_name = "mission"
        elif semantic_id.startswith("commission/nav/"):
            page_semantic_id = "commission/page/back"
            page_name = "commission"
        else:
            raise SemanticGateClosed("semantic image action has no page identity")
        page_back = self._unique(button_state, page_semantic_id)
        if (
            not page_back.actionable
            or self._blocking_rules(button_state, semantic_id)
        ):
            raise SemanticGateClosed(page_name + " page image action is blocked")
        point = Point(
            (image.bounds.left + image.bounds.right) / 2.0,
            (image.bounds.top + image.bounds.bottom) / 2.0,
        )
        if not image.bounds.contains(point) or not (
            0 <= point.x < self.fingerprint.width
            and 0 <= point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("semantic image target center is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before image input")
        self._tap(int(round(point.x)), int(round(point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after image input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=ui_state.generation,
            point=point,
            bounds=image.bounds,
            path=image.path,
        )

    def _matches(self, state: OracleState, semantic_id: str) -> Tuple[ButtonState, ...]:
        target = self._mapping(semantic_id)
        return tuple(
            button
            for button in state.buttons
            if button.name == target.name and button.path.endswith(target.path_suffix)
        )

    def _unique(self, state: OracleState, semantic_id: str) -> ButtonState:
        matches = self._matches(state, semantic_id)
        if not matches:
            raise SemanticTargetMissing("semantic target is absent: {0}".format(semantic_id))
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic target mapping is ambiguous: {0}".format(semantic_id)
            )
        return matches[0]

    def _blocking_rules(
        self, state: OracleState, semantic_id: str
    ) -> Tuple[BlockerRule, ...]:
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
        ):
            # A proven topmost NetworkDown Msgbox intentionally crosses page
            # ownership. Its exact text/labels and top raycast are still
            # required before either button can be considered actionable.
            return ()
        return tuple(
            rule
            for rule in self._blockers
            if semantic_id not in rule.allowed_target_ids
            and any(rule.path_fragment in button.path for button in state.buttons)
        )

    def _msgbox_prompt_parts(
        self, state: OracleState
    ) -> Optional[Tuple[str, str, str]]:
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("Msgbox snapshots are not coherent")

        def exact_text(suffix: str) -> Optional[str]:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("Msgbox text is ambiguous")
            return matches[0].text if matches else None

        content = exact_text("Msgbox(Clone)/window/msg_panel/content")
        cancel = exact_text(
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic"
        )
        confirm = exact_text(
            "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic"
        )
        if content is None or cancel is None or confirm is None:
            return None
        return (
            re.sub(r"<[^>]*>", "", content).strip(),
            "".join(cancel.split()),
            "".join(confirm.split()),
        )

    def _tactical_continue_prompt_text(
        self, state: OracleState
    ) -> Optional[str]:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return None
        plain, cancel, confirm = parts
        if (
            re.fullmatch(
                r"「[^」]+」学习完成，「[^」]+」技能获得[1-9][0-9]*点经验"
                r"是否继续学习该技能？",
                plain,
            )
            and cancel == "取消"
            and confirm == "确定"
        ):
            return plain
        return None

    def _network_reconnect_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            re.fullmatch(
                r"服务器连接失败，是否重新连接？\s*\[NetworkDown\]",
                plain,
            )
            and cancel == "取消"
            and confirm == "确定"
        )

    def _build_warning_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            plain
            == "常驻UR兑换点数已达上限，未兑换UR角色前继续建造不能获得点数，是否继续建造？"
            and cancel == "取消"
            and confirm == "确定"
        )

    def _tactical_course_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            re.fullmatch(
                r"是否消耗1本「舰艇(?:攻击|防御|辅助)教材T[1-4]」，"
                r"训练「[^」]+」的[^「」]+技能？",
                plain,
            )
            and cancel == "取消"
            and confirm == "确定"
        )

    def _research_start_prompt_cost(
        self, state: OracleState
    ) -> Optional[Tuple[str, int]]:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return None
        plain, cancel, confirm = parts
        match = re.fullmatch(
            r"开启该科研项目需要消耗\s*:\s*(物资|心智魔方)x([1-9][0-9]*)",
            plain,
        )
        if match is None or cancel != "取消" or confirm != "确定":
            return None
        resource_id = {"物资": "gold", "心智魔方": "20001"}[match.group(1)]
        return resource_id, int(match.group(2))

    def _research_queue_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            plain
            == "确定将该科研项目加入研究队列吗，加入队列的研究项目将顺序完成，不可取消"
            and cancel == "取消"
            and confirm == "确定"
        )

    def research_start_prompt_cost(self) -> Optional[Tuple[str, int]]:
        state = self.read_state()
        target = self._matches(state, "research/start/confirm")
        if len(target) > 1:
            raise SemanticGateClosed("research start prompt is ambiguous")
        if not target or not target[0].actionable:
            return None
        return self._research_start_prompt_cost(state)

    def _tactical_continue_prompt_matches(self, state: OracleState) -> bool:
        return self._tactical_continue_prompt_text(state) is not None

    def tactical_continue_prompt_text(self) -> Optional[str]:
        state = self.read_state()
        matches = self._matches(state, "tactical/continue/cancel")
        if len(matches) > 1:
            raise SemanticGateClosed("tactical prompt cancel target is ambiguous")
        if (
            not matches
            or not matches[0].actionable
            or self._blocking_rules(state, "tactical/continue/cancel")
        ):
            return None
        return self._tactical_continue_prompt_text(state)

    def exists(self, semantic_id: str) -> bool:
        return self._retry_transition_read(lambda: self._exists_once(semantic_id))

    def _exists_once(self, semantic_id: str) -> bool:
        state = self.read_state()
        matches = self._matches(state, semantic_id)
        if semantic_id == "tactical/continue/cancel":
            return bool(matches and self._tactical_continue_prompt_matches(state))
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
        ):
            return bool(matches and self._network_reconnect_prompt_matches(state))
        if semantic_id in ("build/warning/cancel", "build/warning/confirm"):
            return bool(matches and self._build_warning_prompt_matches(state))
        if semantic_id in ("tactical/course/cancel", "tactical/course/confirm"):
            return bool(matches and self._tactical_course_prompt_matches(state))
        if semantic_id in ("research/start/cancel", "research/start/confirm"):
            return bool(matches and self._research_start_prompt_cost(state) is not None)
        if semantic_id in ("research/queue/cancel", "research/queue/confirm"):
            return bool(matches and self._research_queue_prompt_matches(state))
        return bool(matches)

    def enabled(self, semantic_id: str) -> bool:
        return self._retry_transition_read(lambda: self._enabled_once(semantic_id))

    def _enabled_once(self, semantic_id: str) -> bool:
        state = self.read_state()
        matches = self._matches(state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed("semantic target mapping is ambiguous")
        if semantic_id == "dorm/empty-food/cancel":
            return self._dorm_empty_food_cancel_proven(state)
        if semantic_id in ("dorm/feed", "dorm/collect"):
            return self._dorm_page_control_proven(state, semantic_id)
        if (
            semantic_id == "tactical/continue/cancel"
            and not self._tactical_continue_prompt_matches(state)
        ):
            return False
        if (
            semantic_id in (
                "overlay/network-reconnect/cancel",
                "overlay/network-reconnect/confirm",
            )
            and not self._network_reconnect_prompt_matches(state)
        ):
            return False
        if (
            semantic_id in ("build/warning/cancel", "build/warning/confirm")
            and not self._build_warning_prompt_matches(state)
        ):
            return False
        if (
            semantic_id in ("tactical/course/cancel", "tactical/course/confirm")
            and not self._tactical_course_prompt_matches(state)
        ):
            return False
        if (
            semantic_id in ("research/start/cancel", "research/start/confirm")
            and self._research_start_prompt_cost(state) is None
        ):
            return False
        if (
            semantic_id in ("research/queue/cancel", "research/queue/confirm")
            and not self._research_queue_prompt_matches(state)
        ):
            return False
        return bool(
            matches
            and matches[0].actionable
            and not self._blocking_rules(state, semantic_id)
        )

    def bounds(self, semantic_id: str) -> Bounds:
        target = self._unique(self.read_state(), semantic_id)
        if target.bounds is None:
            raise SemanticGateClosed("semantic target has no screen bounds")
        return target.bounds

    def current_scene(self) -> int:
        return self.read_state().scene_handle

    @staticmethod
    def _mission_rows(
        state: OracleState, button_name: str
    ) -> Tuple[ButtonState, ...]:
        pattern = re.compile(
            r"(?:^|/)TaskScene\(Clone\)/pages/TaskListPage\(Clone\)/"
            r"right_panel/content/([0-9]+)/frame/"
            + re.escape(button_name)
            + r"$"
        )
        rows = []
        indexes = set()
        for button in state.buttons:
            if button.name != button_name:
                continue
            match = pattern.search(button.path)
            if match is None:
                continue
            index = int(match.group(1))
            if index in indexes:
                raise SemanticGateClosed(
                    "mission row Button index is ambiguous: {0}".format(index)
                )
            indexes.add(index)
            rows.append((index, button))
        rows.sort(key=lambda item: item[0])
        return tuple(button for _, button in rows)

    def mission_page_state(self) -> MissionPageState:
        """Classify the reviewed TaskScene without treating absence as empty."""

        state = self.read_state()
        back = self._unique(state, "task/page/back")
        if not back.actionable or self._blocking_rules(state, "task/page/back"):
            raise SemanticGateClosed("mission page identity is not safely actionable")

        claim_all_matches = self._matches(state, "task/claim/all")
        if len(claim_all_matches) > 1:
            raise SemanticGateClosed("mission claim-all target is ambiguous")
        claim_all = claim_all_matches[0] if claim_all_matches else None
        claim_rows = self._mission_rows(state, "get_btn")
        unfinished_rows = self._mission_rows(state, "go_btn")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("button and mission text snapshots are not coherent")
        empty_markers = tuple(
            item
            for item in ui_state.texts
            if item.name == "Text"
            and item.path.endswith(
                "TaskScene(Clone)/TaskEmptyListUI(Clone)/Text"
            )
            and item.text == "没有进行中的任务"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.bounds.right > 0
            and item.bounds.bottom > 0
            and item.bounds.left < self.fingerprint.width
            and item.bounds.top < self.fingerprint.height
        )
        if len(empty_markers) > 1:
            raise SemanticGateClosed("mission empty marker is ambiguous")

        actionable_claim_rows = tuple(
            button for button in claim_rows if button.actionable
        )
        actionable_unfinished_rows = tuple(
            button for button in unfinished_rows if button.actionable
        )
        if claim_all is not None and claim_all.actionable:
            disposition = MissionDisposition.CLAIMABLE_ALL
        elif actionable_claim_rows:
            disposition = MissionDisposition.CLAIMABLE_ROW
        elif claim_all is not None or claim_rows:
            # A claim object hidden by clipping or an overlay is not evidence of
            # a safe click, and it must not be misreported as no work.
            disposition = MissionDisposition.UNKNOWN
        elif actionable_unfinished_rows:
            disposition = MissionDisposition.UNFINISHED
        elif empty_markers:
            disposition = MissionDisposition.EMPTY
        else:
            # Never infer EMPTY from mere absence while a page may still load.
            disposition = MissionDisposition.UNKNOWN

        return MissionPageState(
            disposition=disposition,
            generation=state.generation,
            back=back,
            claim_all=claim_all,
            claim_rows=actionable_claim_rows,
            unfinished_rows=actionable_unfinished_rows,
        )

    def wait_for_mission_state(
        self,
        timeout_seconds: float,
        interval_seconds: float = 0.5,
        required_generations: int = 2,
    ) -> MissionPageState:
        if required_generations < 2:
            raise ValueError("mission state requires at least two generations")
        deadline = self._monotonic() + timeout_seconds
        last_state: Optional[MissionPageState] = None
        stable_generations = 0
        last_error: Optional[SemanticOracleError] = None
        while self._monotonic() < deadline:
            try:
                candidate = self.mission_page_state()
                if candidate.disposition == MissionDisposition.UNKNOWN:
                    last_state = None
                    stable_generations = 0
                elif last_state is None or candidate.signature != last_state.signature:
                    last_state = candidate
                    stable_generations = 1
                elif candidate.generation > last_state.generation:
                    last_state = candidate
                    stable_generations += 1
                if last_state is not None and stable_generations >= required_generations:
                    return last_state
            except SemanticOracleError as exc:
                last_error = exc
                last_state = None
                stable_generations = 0
            self._sleep(interval_seconds)
        if last_error is not None:
            raise SemanticGateClosed("stable mission-state wait timed out") from last_error
        raise SemanticGateClosed("stable mission-state wait timed out")

    def click(self, semantic_id: str) -> ActionReceipt:
        state = self.read_state()
        target = self._unique(state, semantic_id)
        dorm_back_delegated = (
            semantic_id == "dorm/page/back"
            and self._dorm_back_delegated_raycast_proven(state)
        )
        dorm_empty_food_cancel = (
            semantic_id == "dorm/empty-food/cancel"
            and self._dorm_empty_food_cancel_proven(state)
        )
        dorm_page_control = (
            semantic_id in ("dorm/feed", "dorm/collect")
            and self._dorm_page_control_proven(state, semantic_id)
        )
        if (
            semantic_id == "tactical/continue/cancel"
            and not self._tactical_continue_prompt_matches(state)
        ):
            raise SemanticGateClosed("tactical continue prompt identity is not proven")
        if (
            semantic_id in (
                "overlay/network-reconnect/cancel",
                "overlay/network-reconnect/confirm",
            )
            and not self._network_reconnect_prompt_matches(state)
        ):
            raise SemanticGateClosed("network reconnect prompt identity is not proven")
        if (
            semantic_id in ("build/warning/cancel", "build/warning/confirm")
            and not self._build_warning_prompt_matches(state)
        ):
            raise SemanticGateClosed("build warning prompt identity is not proven")
        if (
            semantic_id in ("tactical/course/cancel", "tactical/course/confirm")
            and not self._tactical_course_prompt_matches(state)
        ):
            raise SemanticGateClosed("tactical course prompt identity is not proven")
        if (
            semantic_id in ("research/start/cancel", "research/start/confirm")
            and self._research_start_prompt_cost(state) is None
        ):
            raise SemanticGateClosed("research start prompt identity is not proven")
        if (
            semantic_id in ("research/queue/cancel", "research/queue/confirm")
            and not self._research_queue_prompt_matches(state)
        ):
            raise SemanticGateClosed("research queue prompt identity is not proven")
        if semantic_id == "research/detail/root" and any(
            candidate.actionable
            for candidate in self._matches(state, "research/detail/finish")
        ):
            raise SemanticGateClosed(
                "research detail cannot close through the root while finish is actionable"
            )
        if (
            not target.actionable
            and not dorm_back_delegated
            and not dorm_empty_food_cancel
            and not dorm_page_control
        ) or target.point is None or target.bounds is None:
            raise SemanticGateClosed("semantic target is not actionable")
        point = target.point
        if dorm_page_control:
            ui_state = self.read_ui_state()
            if not self._dorm_page_control_proven(
                state, semantic_id, ui_state=ui_state
            ):
                raise SemanticGateClosed("dorm page control changed before input")
            image_path = (
                target.path + "/icon"
                if semantic_id == "dorm/feed"
                else target.path
            )
            image_sprite = "btn_feed" if semantic_id == "dorm/feed" else "onekey"
            click_images = tuple(
                image
                for image in ui_state.images
                if image.path == image_path
                and image.sprite == image_sprite
                and image.bounds is not None
            )
            if len(click_images) != 1:
                raise SemanticGateClosed("dorm page-control click image is ambiguous")
            click_bounds = click_images[0].bounds
            assert click_bounds is not None
            point = Point(
                (click_bounds.left + click_bounds.right) / 2.0,
                (click_bounds.top + click_bounds.bottom) / 2.0,
            )
            if not target.bounds.contains(point):
                raise SemanticGateClosed("dorm page-control click point is invalid")
        if (
            semantic_id == "research/queue/claim"
            and math.isclose(point.x, float(self.fingerprint.width), abs_tol=0.01)
            and math.isclose(
                target.bounds.right, float(self.fingerprint.width), abs_tol=0.01
            )
            and 0 <= target.bounds.left < target.bounds.right
            and 0 <= target.bounds.top < target.bounds.bottom <= self.fingerprint.height
        ):
            # This reviewed edge-docked Button reports its right-edge pivot as
            # the screen point.  Its complete visible bounds and top raycast
            # are proven, so use the centre of the visible in-screen rectangle.
            point = Point(
                (target.bounds.left + min(
                    target.bounds.right, self.fingerprint.width - 1.0
                )) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        if not (
            0 <= point.x < self.fingerprint.width
            and 0 <= point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("semantic target point is outside the screen")

        disallowed = tuple(
            rule.blocker_id for rule in self._blocking_rules(state, semantic_id)
        )
        if disallowed:
            raise SemanticGateClosed(
                "semantic input is blocked by: {0}".format(", ".join(disallowed))
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")

        x = int(round(point.x))
        y = int(round(point.y))
        self._tap(x, y)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def wait_for(
        self,
        semantic_id: str,
        timeout_seconds: float,
        minimum_generation: Optional[int] = None,
        interval_seconds: float = 0.5,
    ) -> ButtonState:
        deadline = self._monotonic() + timeout_seconds
        last_error: Optional[SemanticOracleError] = None
        while self._monotonic() < deadline:
            try:
                state = self.read_state()
                matches = self._matches(state, semantic_id)
                if len(matches) > 1:
                    raise SemanticGateClosed("semantic target mapping is ambiguous")
                if (
                    matches
                    and matches[0].actionable
                    and not self._blocking_rules(state, semantic_id)
                    and (
                        minimum_generation is None
                        or state.generation > minimum_generation
                    )
                ):
                    return matches[0]
            except SemanticOracleError as exc:
                last_error = exc
            self._sleep(interval_seconds)
        if last_error is not None:
            raise SemanticGateClosed("semantic wait timed out") from last_error
        raise SemanticGateClosed("semantic wait timed out")

    def wait_for_any(
        self,
        semantic_ids: Tuple[str, ...],
        timeout_seconds: float,
        minimum_generation: Optional[int] = None,
        interval_seconds: float = 0.5,
    ) -> Tuple[str, ButtonState]:
        if not semantic_ids or len(set(semantic_ids)) != len(semantic_ids):
            raise ValueError("semantic wait set must contain unique targets")
        deadline = self._monotonic() + timeout_seconds
        last_error: Optional[SemanticOracleError] = None
        while self._monotonic() < deadline:
            try:
                state = self.read_state()
                actionable = []
                for semantic_id in semantic_ids:
                    matches = self._matches(state, semantic_id)
                    if len(matches) > 1:
                        raise SemanticGateClosed(
                            "semantic target mapping is ambiguous"
                        )
                    if (
                        matches
                        and matches[0].actionable
                        and not self._blocking_rules(state, semantic_id)
                    ):
                        actionable.append((semantic_id, matches[0]))
                if len(actionable) > 1:
                    raise SemanticGateClosed("semantic wait set is ambiguous")
                if (
                    len(actionable) == 1
                    and (
                        minimum_generation is None
                        or state.generation > minimum_generation
                    )
                ):
                    return actionable[0]
            except SemanticOracleError as exc:
                last_error = exc
            self._sleep(interval_seconds)
        if last_error is not None:
            raise SemanticGateClosed("semantic wait timed out") from last_error
        raise SemanticGateClosed("semantic wait timed out")

    def click_and_wait(
        self,
        semantic_id: str,
        expected_semantic_id: str,
        timeout_seconds: float,
    ) -> ButtonState:
        receipt = self.click(semantic_id)
        return self.wait_for(
            expected_semantic_id,
            timeout_seconds,
            minimum_generation=receipt.generation,
        )
