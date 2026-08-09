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
    chapter_name: str
    stages: Tuple[CampaignStageState, ...]


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


DEFAULT_TARGETS: Tuple[SemanticTarget, ...] = (
    SemanticTarget(
        "login/enter",
        "LoginUI2(Clone)",
        "UICamera/Canvas/UIMain/LoginUI2(Clone)",
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
        "research-menu/page/back",
        "back",
        "SelectTechnologyUI(Clone)/blur_panel/adapt/top/back",
    ),
    SemanticTarget(
        "research-menu/research",
        "technology_btn",
        "SelectTechnologyUI(Clone)/frame/bg/technology_btn",
    ),
    SemanticTarget(
        "research-menu/shipyard",
        "blueprint_btn",
        "SelectTechnologyUI(Clone)/frame/bg/blueprint_btn",
    ),
    SemanticTarget(
        "research-menu/meta",
        "meta_btn",
        "SelectTechnologyUI(Clone)/frame/bg/meta_btn",
    ),
    SemanticTarget(
        "research/page/back",
        "back",
        "TechnologyUI(Clone)/blur_panel/adapt/top/back",
    ),
    SemanticTarget(
        "tactical/page/back",
        "btnBack",
        "NewNavalTacticsUI(Clone)/adpter/frame/btnBack",
    ),
    SemanticTarget(
        "tactical/continue/cancel",
        "custom_button_2(Clone)",
        "Msgbox(Clone)/window/button_container/custom_button_2(Clone)",
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
        "build/pool/light",
        "frame",
        "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
        "toggles/light/frame",
    ),
    SemanticToggleTarget(
        "build/pool/heavy",
        "frame",
        "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
        "toggles/heavy/frame",
    ),
    SemanticToggleTarget(
        "build/pool/special",
        "frame",
        "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
        "toggles/special/frame",
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
            "build/pool/light",
            "build/pool/heavy",
            "build/pool/special",
            "build/page/back",
        ),
    ),
    BlockerRule(
        "campaign-menu",
        "/LevelMainScene(Clone)/",
        (
            "campaign-menu/page/back",
            "campaign-menu/normal",
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
            "dorm/statistics/confirm",
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
        ),
    ),
    BlockerRule(
        "tactical-continue",
        "/Msgbox(Clone)/",
        ("tactical/continue/cancel",),
    ),
    BlockerRule(
        "tactical-page",
        "/NewNavalTacticsUI(Clone)/",
        (
            "tactical/page/back",
            "tactical/continue/cancel",
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
        self._last_generation: Optional[int] = None

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

        ui_state = self.read_ui_state()
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
        return tuple(rows)

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
            and item.bounds is not None
            and item.text.strip()
        )
        if len(chapter_titles) != 1:
            raise SemanticGateClosed("campaign chapter title is absent or ambiguous")

        prefix = "LevelMainScene(Clone)/float/levels/items/Chapter_"
        stage_buttons = []
        for button in button_state.buttons:
            marker = button.path.find(prefix)
            if marker < 0 or button.name != "Chapter_" + button.path.rsplit("Chapter_", 1)[-1]:
                continue
            suffix = button.path[marker + len(prefix) :]
            if not suffix.isdigit() or not button.path.endswith("Chapter_" + suffix):
                continue
            if (
                not button.active_in_hierarchy
                or not button.active_and_enabled
                or button.bounds is None
            ):
                continue
            stage_buttons.append((int(suffix), button))
        stage_buttons.sort(key=lambda item: item[0])
        if not stage_buttons or len({item[0] for item in stage_buttons}) != len(
            stage_buttons
        ):
            raise SemanticGateClosed("campaign stage buttons are absent or ambiguous")

        stages = []
        for stage_id, button in stage_buttons:
            root = button.path + "/main/info/bk/title_form/"
            fields: Dict[str, TextState] = {}
            for field in ("title_index", "title"):
                matches = tuple(
                    item
                    for item in ui_state.texts
                    if item.path == root + field
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.bounds is not None
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
            chapter_name=chapter_titles[0].text.strip(),
            stages=tuple(stages),
        )

    def campaign_page_is_normal(self) -> bool:
        if self.campaign_menu_is_entry():
            return False
        try:
            self.campaign_page_state()
        except SemanticTargetMissing:
            return False
        return True

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
        if len(matches) != 1 or not matches[0].actionable:
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
        return tuple(
            rule
            for rule in self._blockers
            if semantic_id not in rule.allowed_target_ids
            and any(rule.path_fragment in button.path for button in state.buttons)
        )

    def _tactical_continue_prompt_text(
        self, state: OracleState
    ) -> Optional[str]:
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("tactical prompt snapshots are not coherent")

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
                raise SemanticGateClosed("tactical prompt text is ambiguous")
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
        plain = re.sub(r"<[^>]*>", "", content).strip()
        if (
            re.fullmatch(
                r"「[^」]+」学习完成，「[^」]+」技能获得[1-9][0-9]*点经验"
                r"是否继续学习该技能？",
                plain,
            )
            and "".join(cancel.split()) == "取消"
            and "".join(confirm.split()) == "确定"
        ):
            return plain
        return None

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
        state = self.read_state()
        matches = self._matches(state, semantic_id)
        if semantic_id == "tactical/continue/cancel":
            return bool(matches and self._tactical_continue_prompt_matches(state))
        return bool(matches)

    def enabled(self, semantic_id: str) -> bool:
        state = self.read_state()
        matches = self._matches(state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed("semantic target mapping is ambiguous")
        if (
            semantic_id == "tactical/continue/cancel"
            and not self._tactical_continue_prompt_matches(state)
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
        if (
            semantic_id == "tactical/continue/cancel"
            and not self._tactical_continue_prompt_matches(state)
        ):
            raise SemanticGateClosed("tactical continue prompt identity is not proven")
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("semantic target is not actionable")
        if not (
            0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
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

        x = int(round(target.point.x))
        y = int(round(target.point.y))
        self._tap(x, y)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
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
