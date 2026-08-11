"""Narrow, opt-in bridge from ALAS Button names to semantic targets.

This module deliberately maps only resource names whose meaning was confirmed in
the pinned upstream ALAS tree and whose Unity target was observed in the pinned
Chinese game build.  Semantic mode must never fall back to image coordinates.
"""

from __future__ import annotations

import os
import math
import re
import time
from dataclasses import dataclass, field, replace
from numbers import Real
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from .alas_combat_admission import (
    AlasCampaignCombatAdmission,
    AlasCampaignCombatProof,
    prepare_alas_campaign_combat_admission,
    prove_alas_campaign_combat_transition,
)
from .alas_decision_preview import AlasCampaignDecisionPreview
from .alas_package_process_lease import AlasPackageProcessLease
from .semantic_oracle import (
    ActionReceipt,
    AdbObserverBridge,
    AndroidPackageFingerprint,
    Bounds,
    BuildCostState,
    BuildPool,
    BuildSubmitState,
    CampaignFleetRowState,
    CampaignFleetSelectionState,
    CampaignMapEntryState,
    CampaignMapState,
    CampaignMapViewportSwipeIntent,
    CampaignMapViewportSwipeProof,
    CampaignPageState,
    CommissionDetailState,
    CommissionRewardProof,
    CommissionRowState,
    CommissionScrollProof,
    CommissionScrollState,
    CommissionStartProof,
    DormState,
    DormFeedState,
    MissionPageState,
    MissionDisposition,
    Point,
    SemanticGateClosed,
    SemanticOracleError,
    SemanticOracle,
    OracleFingerprint,
    ResearchProjectState,
    ResearchProjectStatus,
    ResearchDetailState,
    ResearchQueueState,
    TacticalSlotState,
    TacticalCandidateShipState,
    TacticalBookState,
    TacticalSkillState,
)


PINNED_CN_GAME_FINGERPRINT = AndroidPackageFingerprint(
    version_name="9.7.10",
    version_code=9710,
    primary_abi="x86_64",
    base_apk_sha256="e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f",
    il2cpp_sha256="e3f1cfc442b67f1d4c9877fd9ceaedc3d68f2842ad677445241b9cc9c05d1c67",
)


# These aliases are intentionally asymmetric.  For example, BACK_ARROW is not
# mapped to settings/back because ALAS reuses that asset on many unrelated pages.
DEFAULT_ALAS_BUTTON_TARGETS: Mapping[str, str] = {
    "LOGIN_CHECK": "login/enter",
    "POPUP_CONFIRM_WHITE": "overlay/login-data-expired/confirm",
    "MAIN_GOTO_CAMPAIGN": "main/battle",
    "MAIN_GOTO_CAMPAIGN_WHITE": "main/battle",
    "MAIN_GOTO_FLEET": "main/formation",
    "MAIN_GOTO_FLEET_WHITE": "main/formation",
    "MAIN_GOTO_BUILD": "main/build",
    "MAIN_GOTO_BUILD_WHITE": "main/build",
    "MAIN_GOTO_DORMMENU": "main/live",
    "MAIN_GOTO_DORMMENU_WHITE": "main/live",
    "MAIN_GOTO_RESHMENU": "main/tech",
    "MAIN_GOTO_RESHMENU_WHITE": "main/tech",
    "DORMMENU_GOTO_ACADEMY": "dorm-menu/academy",
    "DORMMENU_GOTO_DORM": "dorm-menu/dorm",
    "DORMMENU_GOTO_MEOWFFICER": "dorm-menu/meowfficer",
    "DORMMENU_GOTO_PRIVATE_QUARTERS": "dorm-menu/private-quarters",
    "DORM_GOTO_MAIN": "dorm/page/back",
    "DORM_INFO": "dorm/statistics/confirm",
    "DORM_FEED_CANCEL": "dorm/empty-food/cancel",
    "CAMPAIGN_MENU_GOTO_CAMPAIGN": "campaign-menu/normal",
    "RESHMENU_GOTO_RESEARCH": "research-menu/research",
    "RESHMENU_GOTO_SHIPYARD": "research-menu/shipyard",
    "RESHMENU_GOTO_META": "research-menu/meta",
    "ENTRANCE_1": "research/project/1",
    "ENTRANCE_2": "research/project/2",
    "ENTRANCE_3": "research/project/3",
    "ENTRANCE_4": "research/project/4",
    "ENTRANCE_5": "research/project/5",
    "MAIN_GOTO_REWARD": "main/more",
    "MAIN_GOTO_REWARD_WHITE": "main/more",
    "MAIN_GOTO_DOCK": "main/dock",
    "MAIN_GOTO_DOCK_WHITE": "main/dock",
    "MAIN_GOTO_MISSION": "main/task",
    "MAIN_GOTO_MISSION_WHITE": "main/task",
    "MAIN_GOTO_SHOP": "main/shop",
    "MAIN_GOTO_SHOP_WHITE": "main/shop",
    "MAIL_ENTER": "main/mail",
    "MAIL_ENTER_WHITE": "main/mail",
    "MAIL_CHECK": "mail/page/back",
    "MAIL_MANAGE": "mail/manage",
    "MISSION_CHECK": "task/page/back",
    "COMMISSION_CHECK": "commission/page/back",
    "REWARD_CHECK": "reward/page/back",
    "REWARD_GOTO_MAIN": "reward/page/back",
    "REWARD_1": "reward/commission/finish",
    "REWARD_1_WHITE": "reward/commission/finish",
    "REWARD_GOTO_COMMISSION": "reward/commission/go",
    "REWARD_GOTO_COMMISSION_WHITE": "reward/commission/go",
    "REWARD_2": "reward/tactical/finish",
    "REWARD_2_WHITE": "reward/tactical/finish",
    "REWARD_GOTO_TACTICAL": "reward/tactical/go",
    "REWARD_GOTO_TACTICAL_WHITE": "reward/tactical/go",
    "LOGIN_ANNOUNCE": "overlay/bulletin/close",
    "LOGIN_ANNOUNCE_2": "overlay/bulletin/close",
    "AUTO_SEARCH_MENU_EXIT": "reward/campaign-total/exit",
    "POPUP_CANCEL": "overlay/network-reconnect/cancel",
    "POPUP_CONFIRM": "overlay/network-reconnect/confirm",
    "POPUP_CONFIRM_UI_ADDITIONAL": "overlay/network-reconnect/confirm",
}


MISSION_VIRTUAL_RESOURCES = frozenset(
    {
        "MISSION_NOTICE",
        "MISSION_NOTICE_WHITE",
        "MISSION_MULTI",
        "MISSION_SINGLE",
        "MISSION_EMPTY",
        "MISSION_UNFINISH",
        "MISSION_WEEKLY_RED_DOT",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_SHIP",
        "GUILD_POPUP_CONFIRM",
        "GUILD_POPUP_CANCEL",
    }
)
MISSION_CLICK_RESOURCES = frozenset(
    {
        "MISSION_MULTI",
        "MISSION_SINGLE",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GUILD_POPUP_CANCEL",
    }
)
MISSION_NAVBAR_PATTERN = re.compile(r"^REWARD_SIDE_NAVBAR_0_([0-5])$")
MISSION_NAVBAR_ACTIVE_COLOR = (247, 255, 173)
MISSION_NAVBAR_INACTIVE_COLOR = (140, 162, 181)
BUILD_SIDE_NAVBAR_PATTERN = re.compile(r"^GACHA_SIDE_NAVBAR_0_([0-4])$")
BUILD_POOL_NAVBAR_PATTERN = re.compile(r"^CONSTRUCT_BOTTOM_NAVBAR_([0-3])_0$")
BUILD_SIDE_NAVBAR_TARGETS = (
    "build/nav/pools",
    "build/nav/queue",
    "build/nav/support",
    "build/nav/unseam",
)
BUILD_POOL_NAVBAR_TARGETS = {
    1: "build/pool/light",
    2: "build/pool/heavy",
    3: "build/pool/special",
}
BUILD_SIDE_NAVBAR_ACTIVE_COLOR = (247, 255, 173)
BUILD_SIDE_NAVBAR_INACTIVE_COLOR = (140, 162, 181)
BUILD_POOL_NAVBAR_ACTIVE_COLOR = (247, 227, 148)
BUILD_POOL_NAVBAR_INACTIVE_COLOR = (189, 231, 247)
MISSION_NAVBAR_TARGETS = (
    "task/nav/all",
    "task/nav/main",
    "task/nav/side",
    "task/nav/daily",
    "task/nav/weekly",
    "task/nav/event",
)
MAIL_VIRTUAL_RESOURCES = frozenset(
    {
        "MAIL_BATCH_CLAIM",
        "MAIL_BATCH_DELETE",
        "MAIL_WHITE_EMPTY",
        "GOTO_MAIN_WHITE",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
    }
)
MAIL_CLICK_RESOURCES = frozenset(
    {
        "MAIL_BATCH_CLAIM",
        "MAIL_BATCH_DELETE",
        "MAIL_MANAGE",
        "MAIL_SELECT_ALL",
        "MAIL_SELECT_COINS",
        "MAIL_SELECT_CUBE",
        "MAIL_SELECT_GEMS",
        "MAIL_SELECT_MERIT",
        "MAIL_SELECT_OIL",
        "GOTO_MAIN_WHITE",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
    }
)
MAIL_TOGGLE_TARGETS: Mapping[str, str] = {
    "MAIL_SELECT_ALL": "mail/manage/all",
    "MAIL_SELECT_CUBE": "mail/manage/cube",
    "MAIL_SELECT_COINS": "mail/manage/coins",
    "MAIL_SELECT_OIL": "mail/manage/oil",
    "MAIL_SELECT_MERIT": "mail/manage/merit",
    "MAIL_SELECT_GEMS": "mail/manage/gems",
}
COMMISSION_VIRTUAL_RESOURCES = frozenset(
    {
        "COMMISSION_DAILY",
        "COMMISSION_URGENT",
        "COMMISSION_ADVICE",
        "COMMISSION_START",
        "EXP_INFO_S_REWARD",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "GET_SHIP",
    }
)
COMMISSION_CLICK_RESOURCES = frozenset(
    {
        "COMMISSION_DAILY",
        "COMMISSION_URGENT",
        "COMMISSION_ADVICE",
        "COMMISSION_START",
        "EXP_INFO_S_REWARD",
        "REWARD_SAVE_CLICK",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "BACK_ARROW",
    }
)
COMMISSION_TAB_TARGETS: Mapping[str, str] = {
    "COMMISSION_DAILY": "commission/nav/daily",
    "COMMISSION_URGENT": "commission/nav/urgent",
}
COMMISSION_ROW_PATTERN = re.compile(r"^COMMISSION_ROW_([0-9]+)$")
CAMPAIGN_FLEET_ROW_RESOURCES: Mapping[str, Tuple[str, str]] = {
    "FLEET_1_CHOOSE": ("fleet1", "select"),
    "FLEET_1_CLEAR": ("fleet1", "clear"),
    "FLEET_1_ADVICE": ("fleet1", "advice"),
    "FLEET_2_CHOOSE": ("fleet2", "select"),
    "FLEET_2_CLEAR": ("fleet2", "clear"),
    "FLEET_2_ADVICE": ("fleet2", "advice"),
    "SUBMARINE_CHOOSE": ("submarine", "select"),
    "SUBMARINE_CLEAR": ("submarine", "clear"),
    "SUBMARINE_ADVICE": ("submarine", "advice"),
}
CAMPAIGN_FLEET_BAR_PATTERN = re.compile(
    r"^(FLEET_1|FLEET_2|SUBMARINE)_BAR_INDEX_([1-6])$"
)
CAMPAIGN_AUTO_SEARCH_ON_RESOURCES = frozenset(
    {"AUTO_SEARCH_ON", "AUTO_SEARCH_ON2", "AUTO_SEARCH_ON3", "AUTO_SEARCH_ON4"}
)
CAMPAIGN_AUTO_SEARCH_OFF_RESOURCES = frozenset(
    {
        "AUTO_SEARCH_OFF",
        "AUTO_SEARCH_OFF2",
        "AUTO_SEARCH_OFF3",
        "AUTO_SEARCH_OFF4",
    }
)
CAMPAIGN_AUTO_SEARCH_RESOURCES = (
    CAMPAIGN_AUTO_SEARCH_ON_RESOURCES | CAMPAIGN_AUTO_SEARCH_OFF_RESOURCES
)
CAMPAIGN_VIRTUAL_RESOURCES = frozenset(
    {
        "CAMPAIGN_CHECK",
        "CAMPAIGN_MENU_CHECK",
        "EVENT_LIST_CHECK",
        "BACK_ARROW",
        "SWITCH_1_NORMAL",
        "SWITCH_1_HARD",
        "SWITCH_2_HARD",
        "SWITCH_2_EX",
        "GOTO_MAIN",
        "IN_MAP",
        "MAP_PREPARATION",
        "FLEET_PREPARATION",
        "MAP_PREPARATION_CANCEL",
        *CAMPAIGN_AUTO_SEARCH_RESOURCES,
        *CAMPAIGN_FLEET_ROW_RESOURCES.keys(),
    }
)
CAMPAIGN_CLICK_RESOURCES = frozenset(
    {
        "GOTO_MAIN",
        "BACK_ARROW",
        "MAP_PREPARATION",
        "MAP_PREPARATION_CANCEL",
        "FLEET_PREPARATION",
        *CAMPAIGN_AUTO_SEARCH_RESOURCES,
        "FLEET_1_CHOOSE",
        "FLEET_1_CLEAR",
        "FLEET_2_CHOOSE",
        "FLEET_2_CLEAR",
        "SUBMARINE_CHOOSE",
        "SUBMARINE_CLEAR",
    }
)
PAGE_VIRTUAL_RESOURCES = frozenset(
    {
        "BUILD_CHECK",
        "DORMMENU_CHECK",
        "DORM_CHECK",
        "RESHMENU_CHECK",
        "RESEARCH_CHECK",
        "TACTICAL_CHECK",
    }
)
RESEARCH_VIRTUAL_RESOURCES = frozenset(
    {
        "QUEUE_CHECK",
        "QUEUE_CLAIM_REWARD",
        "RESEARCH_COST_CHECKER",
        "RESEARCH_DETAIL_QUIT",
        "RESEARCH_GOTO_QUEUE",
        "RESEARCH_QUEUE_ADD",
        "RESEARCH_START",
        "RESEARCH_STOP",
        "RESEARCH_UNAVAILABLE",
        "DETAIL_NEXT",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "GET_ITEMS_RESEARCH_SAVE",
        "POPUP_CANCEL",
        "POPUP_CONFIRM",
        "BACK_ARROW",
    }
)
RESEARCH_CLICK_RESOURCES = frozenset(
    {
        "QUEUE_CLAIM_REWARD",
        "RESEARCH_DETAIL_QUIT",
        "RESEARCH_GOTO_QUEUE",
        "RESEARCH_QUEUE_ADD",
        "RESEARCH_START",
        "RESEARCH_STOP",
        "GET_ITEMS_RESEARCH_SAVE",
        "POPUP_CONFIRM",
        "BACK_ARROW",
    }
)
DORM_VIRTUAL_RESOURCES = frozenset(
    {
        "DORM_QUICK_COLLECT",
        "DORM_FEED_CHECK",
        "DORM_FEED_ENTER",
        "DORM_FEED_CANCEL",
        "POPUP_CANCEL",
    }
)
BUILD_VIRTUAL_RESOURCES = frozenset(
    {
        "BUILD_SUBMIT_ORDERS",
        "BUILD_SUBMIT_WW_ORDERS",
        "BUILD_QUEUE_EMPTY",
        "BUILD_FINISH_ORDERS",
        "BUILD_WW_CHECK",
        "SHOP_MEDAL_CHECK",
        "BUILD_MINUS",
        "BUILD_PLUS",
        "POPUP_CONFIRM",
        "POPUP_CONFIRM_GACHA_PREP",
        "POPUP_CONFIRM_GACHA_ORDER",
        "POPUP_CANCEL",
    }
)
TACTICAL_VIRTUAL_RESOURCES = frozenset(
    {
        "ADD_NEW_STUDENT",
        "DOCK_CHECK",
        "SKILL_CONFIRM",
        "TACTICAL_CLASS_START",
        "TACTICAL_CLASS_CANCEL",
        "POPUP_CONFIRM",
        "BACK_ARROW",
    }
)


class AlasSemanticUnmapped(SemanticGateClosed):
    """An ALAS resource has no reviewed semantic mapping."""


class MissionClaimableDetected(SemanticGateClosed):
    """A proven claim target was observed, but no claim input was injected."""

    def __init__(
        self,
        page: MissionPageState,
        entry: ActionReceipt,
        exit_receipt: ActionReceipt,
        dismissed_overlays: Tuple[str, ...],
    ) -> None:
        super().__init__(
            "claimable mission detected, but reward-popup contract is not validated"
        )
        self.page = page
        self.entry = entry
        self.exit_receipt = exit_receipt
        self.dismissed_overlays = dismissed_overlays


@dataclass(frozen=True)
class MissionRunReceipt:
    outcome: str
    page_generation: int
    entry_path: str
    exit_path: str
    claim_injected: bool = False
    claim_all_present: bool = False
    claim_row_count: int = 0
    unfinished_row_count: int = 0
    dismissed_overlays: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MissionClaimReceipt:
    outcome: str
    pre_claim_generation: int
    post_claim_generation: int
    entry_path: str
    claim_path: str
    popup_close_path: str
    exit_path: str
    pre_claim_row_count: int
    post_claim_row_count: int
    unfinished_row_count: int
    claim_input_count: int = 1
    dismissed_overlays: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CampaignPreSortieProof:
    stage_code: str
    chapter_name: str
    entry_generation: int
    preparation_kind: str
    cancel_generation: int
    restored_generation: int


@dataclass(frozen=True)
class CampaignFleetPreparationProof:
    stage_code: str
    initial_fleets: Tuple[int, int, int]
    requested_fleets: Tuple[int, int, int]
    prepared_fleets: Tuple[int, int, int]
    initial_generation: int
    prepared_generation: int
    mutation_semantic_ids: Tuple[str, ...]
    cancel_generation: int
    restored_generation: int


@dataclass(frozen=True)
class CampaignSortieProof:
    stage_code: str
    initial_fleets: Tuple[int, int, int]
    requested_fleets: Tuple[int, int, int]
    prepared_fleets: Tuple[int, int, int]
    mutation_semantic_ids: Tuple[str, ...]
    oil_before_sortie: int
    required_oil: int
    sortie_generation: int
    map_generation: int
    map_root_path: str


@dataclass
class _MissionFlowContext:
    daily: bool
    weekly: bool
    claim_budget: int
    summary_entry_clicked: bool = False
    entry_clicked: bool = False
    summary_entry_receipt: Optional[ActionReceipt] = None
    entry_receipt: Optional[ActionReceipt] = None
    passive_transition_until: float = 0.0
    last_signature: Optional[Tuple[Any, ...]] = None
    last_generation: int = -1
    stable_generations: int = 0
    stable_state: Optional[MissionPageState] = None


@dataclass
class _LoginFlowContext:
    passive_transition_until: float = 0.0
    entry_receipt: Optional[ActionReceipt] = None


@dataclass
class _MailFlowContext:
    entry_clicked: bool = False
    mutations_allowed: bool = False


@dataclass
class _CommissionFlowContext:
    flow_kind: str = "commission"
    rewards_allowed: bool = False
    reward_budget: int = 0
    reward_detected_count: Optional[int] = None
    reward_claim_receipt: Optional[ActionReceipt] = None
    reward_close_receipts: List[ActionReceipt] = field(default_factory=list)
    reward_proof: Optional[CommissionRewardProof] = None
    start_budget: int = 0
    selected_signature: Optional[Tuple[Union[int, str], ...]] = None
    selected_at: float = 0.0
    start_receipt: Optional[ActionReceipt] = None
    start_clicked_at: float = 0.0
    start_proof: Optional[CommissionStartProof] = None
    passive_transition_until: float = 0.0
    cancelled_tactical_prompts: Set[str] = field(default_factory=set)
    assign_budget: int = 0
    tactical_back_receipt: Optional[ActionReceipt] = None


@dataclass
class _ResearchFlowContext:
    start_budget: int = 0
    reward_budget: int = 0
    selected_slot: Optional[int] = None
    selected_code: Optional[str] = None
    selected_status: Optional[ResearchProjectStatus] = None
    start_receipt: Optional[ActionReceipt] = None
    start_confirm_receipt: Optional[ActionReceipt] = None
    pending_resource_id: Optional[str] = None
    pending_resource_required: Optional[int] = None
    reward_receipts: List[ActionReceipt] = field(default_factory=list)
    popup_close_receipts: List[ActionReceipt] = field(default_factory=list)
    passive_transition_until: float = 0.0
    navigation_receipts: Dict[str, ActionReceipt] = field(default_factory=dict)
    last_queue_state: Optional[ResearchQueueState] = None
    last_queue_observed_at: float = 0.0
    last_projects: Optional[Tuple[ResearchProjectState, ...]] = None
    last_projects_observed_at: float = 0.0
    queue_add_receipt: Optional[ActionReceipt] = None
    queue_confirm_receipt: Optional[ActionReceipt] = None
    queue_add_uses_start_budget: bool = False


@dataclass
class _DormFlowContext:
    collect_budget: int = 0
    feed_budget: int = 0
    passive_transition_until: float = 0.0
    navigation_receipts: Dict[str, ActionReceipt] = field(default_factory=dict)
    feed_entry_receipt: Optional[ActionReceipt] = None
    feed_panel_observed: bool = False


@dataclass
class _BuildFlowContext:
    submit_budget: int = 0
    prep_opened: bool = False
    warning_confirmed: bool = False
    coins_owned: Optional[int] = None
    submit_receipt: Optional[ActionReceipt] = None
    passive_transition_until: float = 0.0


@dataclass(frozen=True)
class CampaignMapTargetRecheckProof:
    """Read-only post-camera proof before ALAS reaches its grid click."""

    target_node: str
    viewport_post_generation: int
    camera_state_generation: int
    recheck_generation: int
    path: str
    point: Point
    bounds: Bounds


@dataclass
class _CampaignFlowContext:
    stage_code: str
    mode: str = "normal"
    entry_budget: int = 0
    fleet_mutation_budget: int = 0
    sortie_budget: int = 0
    menu_entry_receipt: Optional[ActionReceipt] = None
    entry_receipt: Optional[ActionReceipt] = None
    map_preparation_receipt: Optional[ActionReceipt] = None
    auto_search_toggle_receipt: Optional[ActionReceipt] = None
    preparation_kind: Optional[str] = None
    cancel_receipt: Optional[ActionReceipt] = None
    proof: Optional[CampaignPreSortieProof] = None
    initial_fleet_state: Optional[CampaignFleetSelectionState] = None
    prepared_fleet_state: Optional[CampaignFleetSelectionState] = None
    requested_fleets: Optional[Tuple[int, int, int]] = None
    required_fleet_mutations: int = 0
    expected_fleet_mutations: Tuple[str, ...] = ()
    fleet_mutation_receipts: List[ActionReceipt] = field(default_factory=list)
    fleet_dropdown_row: Optional[str] = None
    fleet_dropdown_previous_index: Optional[int] = None
    fleet_proof: Optional[CampaignFleetPreparationProof] = None
    oil_before_sortie: Optional[int] = None
    sortie_authorized: bool = False
    sortie_receipt: Optional[ActionReceipt] = None
    map_entry_state: Optional[CampaignMapEntryState] = None
    sortie_proof: Optional[CampaignSortieProof] = None
    combat_budget: int = 0
    viewport_swipe_budget: int = 0
    map_state: Optional[CampaignMapState] = None
    map_columns: Optional[int] = None
    map_rows: Optional[int] = None
    map_land_cells: Tuple[Tuple[int, int], ...] = ()
    map_expected_fleet_count: Optional[int] = None
    combat_admission: Optional[AlasCampaignCombatAdmission] = None
    viewport_swipe_required: bool = False
    viewport_swipe_intent: Optional[CampaignMapViewportSwipeIntent] = None
    viewport_swipe_proof: Optional[CampaignMapViewportSwipeProof] = None
    target_recheck_proof: Optional[CampaignMapTargetRecheckProof] = None
    combat_receipt: Optional[ActionReceipt] = None
    combat_proof: Optional[AlasCampaignCombatProof] = None
    passive_transition_until: float = 0.0


@dataclass
class PinnedPackageGate:
    """Cache one independent ADB verification of the installed package."""

    bridge: AdbObserverBridge
    expected: AndroidPackageFingerprint = PINNED_CN_GAME_FINGERPRINT
    _verified_pid: Optional[int] = None

    def accept_process_lease(self, lease: AlasPackageProcessLease) -> None:
        if not isinstance(lease, AlasPackageProcessLease):
            raise SemanticGateClosed("package process lease is not verified")
        if (
            self.bridge.pid is None
            or lease.pid != self.bridge.pid
            or lease.package != self.bridge.package
        ):
            raise SemanticGateClosed("package process lease PID changed")
        self._verified_pid = lease.pid

    def __call__(self) -> None:
        if self.bridge.pid is None:
            raise SemanticGateClosed("ADB observer bridge is not open")
        if self._verified_pid == self.bridge.pid:
            return
        self.bridge.require_package_fingerprint(self.expected)
        self._verified_pid = self.bridge.pid


class AlasSemanticAdapter:
    """Fail-closed replacement for ALAS image presence and coordinate clicks."""

    def __init__(
        self,
        oracle: SemanticOracle,
        package_gate: Callable[[], None],
        mappings: Mapping[str, str] = DEFAULT_ALAS_BUTTON_TARGETS,
        allow_mission_claim_once: bool = False,
        allow_mail_mutations: bool = False,
        allow_tactical_rewards: bool = False,
        tactical_assign_budget: int = 0,
        commission_reward_budget: int = 0,
        commission_start_budget: int = 0,
        research_reward_budget: int = 0,
        research_start_budget: int = 0,
        dorm_collect_budget: int = 0,
        dorm_feed_budget: int = 0,
        build_submit_budget: int = 0,
        campaign_stage_entry_budget: int = 0,
        campaign_fleet_mutation_budget: int = 0,
        campaign_sortie_budget: int = 0,
        campaign_combat_budget: int = 0,
        campaign_viewport_swipe_budget: int = 0,
    ) -> None:
        if package_gate is None:
            raise ValueError("semantic ALAS mode requires a package identity gate")
        self.oracle = oracle
        self._package_gate = package_gate
        self._mappings = dict(mappings)
        if not self._mappings or any(
            not name or not semantic_id
            for name, semantic_id in self._mappings.items()
        ):
            raise ValueError("ALAS semantic mappings must be non-empty")
        self._allow_mission_claim_once = bool(allow_mission_claim_once)
        self._allow_mail_mutations = bool(allow_mail_mutations)
        self._allow_tactical_rewards = bool(allow_tactical_rewards)
        for label, budget in (
            ("tactical assign", tactical_assign_budget),
            ("commission reward", commission_reward_budget),
            ("commission start", commission_start_budget),
            ("research reward", research_reward_budget),
            ("research start", research_start_budget),
            ("dorm collect", dorm_collect_budget),
            ("dorm feed", dorm_feed_budget),
            ("build submit", build_submit_budget),
            ("campaign stage entry", campaign_stage_entry_budget),
            ("campaign fleet mutation", campaign_fleet_mutation_budget),
            ("campaign sortie", campaign_sortie_budget),
            ("campaign combat", campaign_combat_budget),
            ("campaign viewport swipe", campaign_viewport_swipe_budget),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or budget < 0
            ):
                raise ValueError(
                    "{0} budget must be a non-negative integer".format(label)
                )
        self._commission_reward_budget = commission_reward_budget
        self._tactical_assign_budget = tactical_assign_budget
        self._commission_start_budget = commission_start_budget
        self._research_reward_budget = research_reward_budget
        self._research_start_budget = research_start_budget
        self._dorm_collect_budget = dorm_collect_budget
        self._dorm_feed_budget = dorm_feed_budget
        self._build_submit_budget = build_submit_budget
        self._campaign_stage_entry_budget = campaign_stage_entry_budget
        self._campaign_fleet_mutation_budget = campaign_fleet_mutation_budget
        self._campaign_sortie_budget = campaign_sortie_budget
        self._campaign_combat_budget = campaign_combat_budget
        self._campaign_viewport_swipe_budget = campaign_viewport_swipe_budget
        self._mission_context: Optional[_MissionFlowContext] = None
        self._login_context: Optional[_LoginFlowContext] = None
        self._mail_context: Optional[_MailFlowContext] = None
        self._commission_context: Optional[_CommissionFlowContext] = None
        self._research_context: Optional[_ResearchFlowContext] = None
        self._dorm_context: Optional[_DormFlowContext] = None
        self._build_context: Optional[_BuildFlowContext] = None
        self._campaign_context: Optional[_CampaignFlowContext] = None
        self._observer_stale_since: Optional[float] = None

    @staticmethod
    def _button_name(button: Any) -> str:
        name = button if isinstance(button, str) else getattr(button, "name", None)
        if not isinstance(name, str) or not name:
            raise AlasSemanticUnmapped("ALAS resource has no stable name")
        # InfoHandler temporarily annotates this reviewed shared asset between
        # its presence probe and click.  Normalize only the proven Research
        # suffix; broad prefix stripping could admit unrelated popup inputs.
        if name in (
            "POPUP_CONFIRM_RESEARCH_START",
            "POPUP_CONFIRM_RESEARCH_QUEUE",
            "POPUP_CONFIRM_LOGIN",
            "POPUP_CONFIRM_WHITE_LOGIN",
        ):
            return (
                "POPUP_CONFIRM_WHITE"
                if name == "POPUP_CONFIRM_WHITE_LOGIN"
                else "POPUP_CONFIRM"
            )
        return name

    def semantic_id_for(self, button: Any) -> str:
        name = self._button_name(button)
        try:
            return self._mappings[name]
        except KeyError as exc:
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(name)
            ) from exc

    def supports(self, button: Any) -> bool:
        try:
            name = self._button_name(button)
        except AlasSemanticUnmapped:
            return False
        return bool(
            name in self._mappings
            or name in MISSION_VIRTUAL_RESOURCES
            or name in MAIL_VIRTUAL_RESOURCES
            or name in MAIL_CLICK_RESOURCES
            or name in COMMISSION_VIRTUAL_RESOURCES
            or name in COMMISSION_CLICK_RESOURCES
            or name in CAMPAIGN_VIRTUAL_RESOURCES
            or name in CAMPAIGN_CLICK_RESOURCES
            or name in PAGE_VIRTUAL_RESOURCES
            or name in RESEARCH_VIRTUAL_RESOURCES
            or name in DORM_VIRTUAL_RESOURCES
            or name in BUILD_VIRTUAL_RESOURCES
            or name in TACTICAL_VIRTUAL_RESOURCES
            or CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name)
            or MISSION_NAVBAR_PATTERN.fullmatch(name)
            or COMMISSION_ROW_PATTERN.fullmatch(name)
            or BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
            or BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        )

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        """Open one ALAS-owned mission state-machine invocation."""

        self._package_gate()
        if self._mission_context is not None:
            raise SemanticGateClosed("nested ALAS mission flow is not allowed")
        if any(
            context is not None
            for context in (
                self._login_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._mission_context = _MissionFlowContext(
            daily=bool(daily),
            weekly=bool(weekly),
            claim_budget=(1 if self._allow_mission_claim_once else 0),
        )

    def begin_login(self) -> None:
        """Open one original ALAS LoginHandler invocation."""

        self._package_gate()
        if any(
            context is not None
            for context in (
                self._login_context,
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._login_context = _LoginFlowContext(
            passive_transition_until=time.monotonic() + 20.0
        )

    def end_login(self) -> None:
        self._login_context = None

    def end_mission_reward(self) -> None:
        """Close the ALAS-owned mission invocation and discard all cached state."""

        self._mission_context = None

    def mission_reward_active(self) -> bool:
        """Return whether ALAS currently owns the mission/reward flow."""

        return self._mission_context is not None

    def mission_claim_allowed(self) -> bool:
        """Expose the remaining input budget without weakening the click gate."""

        context = self._require_mission_context()
        return context.claim_budget > 0

    def begin_mail(self) -> None:
        """Open one ALAS-owned mail state-machine invocation."""

        self._package_gate()
        if (
            self._mail_context is not None
            or self._login_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._build_context is not None
            or self._commission_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._mail_context = _MailFlowContext(
            mutations_allowed=self._allow_mail_mutations
        )

    def end_mail(self) -> None:
        self._mail_context = None

    def begin_commission(self) -> None:
        """Open one ALAS-owned commission state-machine invocation."""

        self._package_gate()
        if (
            self._commission_context is not None
            or self._login_context is not None
            or self._mail_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._build_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._commission_context = _CommissionFlowContext(
            flow_kind="commission",
            reward_budget=self._commission_reward_budget,
            start_budget=self._commission_start_budget,
            passive_transition_until=time.monotonic() + 20.0,
        )

    def begin_tactical(self) -> None:
        """Open the shared reward/tactical context without commission budgets."""

        self._package_gate()
        if (
            self._commission_context is not None
            or self._login_context is not None
            or self._mail_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._build_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._commission_context = _CommissionFlowContext(
            flow_kind="tactical",
            rewards_allowed=self._allow_tactical_rewards,
            assign_budget=self._tactical_assign_budget,
            passive_transition_until=time.monotonic() + 20.0,
        )

    def begin_research(self) -> None:
        self._package_gate()
        if any(
            context is not None
            for context in (
                self._login_context,
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._research_context = _ResearchFlowContext(
            start_budget=self._research_start_budget,
            reward_budget=self._research_reward_budget,
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_research(self) -> None:
        self._research_context = None

    def begin_dorm(self) -> None:
        self._package_gate()
        if any(
            context is not None
            for context in (
                self._login_context,
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._dorm_context = _DormFlowContext(
            collect_budget=self._dorm_collect_budget,
            feed_budget=self._dorm_feed_budget,
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_dorm(self) -> None:
        self._dorm_context = None

    def begin_build(self) -> None:
        self._package_gate()
        if any(
            context is not None
            for context in (
                self._login_context,
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._build_context = _BuildFlowContext(
            submit_budget=self._build_submit_budget,
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_build(self) -> None:
        self._build_context = None

    def begin_campaign_pre_sortie(
        self, stage_code: str, mode: str = "normal"
    ) -> None:
        """Open one ALAS-owned bounded campaign entry invocation."""

        self._package_gate()
        if re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", stage_code) is None:
            raise SemanticGateClosed("campaign stage code is not canonical")
        if mode not in ("normal", "hard"):
            raise SemanticGateClosed("campaign mode is not reviewed")
        if any(
            context is not None
            for context in (
                self._login_context,
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._campaign_context = _CampaignFlowContext(
            stage_code=stage_code,
            mode=mode,
            entry_budget=self._campaign_stage_entry_budget,
            fleet_mutation_budget=self._campaign_fleet_mutation_budget,
            sortie_budget=self._campaign_sortie_budget,
            combat_budget=self._campaign_combat_budget,
            viewport_swipe_budget=self._campaign_viewport_swipe_budget,
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_campaign_pre_sortie(self) -> None:
        self._campaign_context = None

    def campaign_pre_sortie_active(self) -> bool:
        return self._campaign_context is not None

    def campaign_stage_entry_allowed(self) -> bool:
        context = self._require_campaign_context()
        return context.entry_budget > 0 and context.entry_receipt is None

    def campaign_map_preparation_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.map_preparation_receipt is not None

    def campaign_sortie_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.sortie_receipt is not None

    @staticmethod
    def _campaign_fleet_tuple(
        state: CampaignFleetSelectionState,
    ) -> Tuple[int, int, int]:
        rows = {row.row_key: row for row in state.rows}
        if set(rows) != {"fleet1", "fleet2", "submarine"}:
            raise SemanticGateClosed("campaign fleet rows are incomplete")
        return tuple(
            int(rows[key].selected_fleet or 0)
            for key in ("fleet1", "fleet2", "submarine")
        )

    def _campaign_fleet_row(self, row_key: str) -> CampaignFleetRowState:
        context = self._require_campaign_context()
        state = self.oracle.campaign_fleet_selection_state(context.stage_code)
        matches = tuple(row for row in state.rows if row.row_key == row_key)
        if len(matches) != 1:
            raise SemanticGateClosed("campaign fleet row is absent or ambiguous")
        return matches[0]

    def authorize_campaign_fleet_preparation(
        self, fleet1: int, fleet2: int, submarine: int
    ) -> bool:
        """Preflight the exact mutations ALAS will request before any input."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.mode != "normal":
            raise SemanticGateClosed(
                "typed campaign fleet preparation is qualified only for normal mode"
            )
        if fleet1 not in range(1, 7) or fleet2 not in range(0, 7) or submarine not in range(0, 7):
            raise SemanticGateClosed("campaign fleet configuration is outside 1 through 6")
        if context.initial_fleet_state is not None:
            raise SemanticGateClosed("campaign fleet preparation was already authorized")
        initial = self.oracle.campaign_fleet_selection_state(context.stage_code)
        context.initial_fleet_state = initial
        context.requested_fleets = (fleet1, fleet2, submarine)
        if context.fleet_mutation_budget == 0:
            return False

        values = dict(
            zip(("fleet1", "fleet2", "submarine"), self._campaign_fleet_tuple(initial))
        )
        operations: List[str] = []

        def clear(row_key: str) -> None:
            if values[row_key] == 0:
                return
            operations.append(
                "campaign/fleet-preparation/{0}/clear".format(
                    "submarine/1" if row_key == "submarine" else row_key.replace("fleet", "fleet/")
                )
            )
            values[row_key] = 0

        def ensure(row_key: str, index: int) -> None:
            if values[row_key] == index:
                return
            operations.append(
                "campaign/fleet-preparation/option/{0}".format(index)
            )
            values[row_key] = index

        map_allows_submarine = initial.submarine_fleets[1] == 1
        if submarine and not map_allows_submarine:
            raise SemanticGateClosed(
                "campaign submarine selection is not available on the proven panel"
            )
        if map_allows_submarine:
            if submarine:
                clear("fleet2")
                ensure("submarine", submarine)
            else:
                clear("fleet2")
                clear("submarine")
        if fleet2:
            clear("fleet2")
            ensure("fleet1", fleet1)
            ensure("fleet2", fleet2)
        else:
            clear("fleet2")
            ensure("fleet1", fleet1)
        if map_allows_submarine and not submarine:
            clear("submarine")
        if tuple(values[key] for key in ("fleet1", "fleet2", "submarine")) != (
            fleet1,
            fleet2,
            submarine,
        ):
            raise SemanticGateClosed("campaign fleet preflight did not reach the request")
        context.required_fleet_mutations = len(operations)
        context.expected_fleet_mutations = tuple(operations)
        if context.fleet_mutation_budget < len(operations):
            raise SemanticGateClosed(
                "campaign fleet mutation budget is below the preflight requirement: "
                "{0} < {1}".format(context.fleet_mutation_budget, len(operations))
            )
        return True

    def campaign_fleet_row_allowed(self, row_key: str) -> bool:
        # ALAS FleetOperator.clear() exits only when the row remains available
        # while in_use() becomes false.  The typed state proves all three exact
        # row controls independently of whether a fleet is currently assigned.
        self._campaign_fleet_row(row_key)
        return True

    def campaign_fleet_operator_is_hard(self, row_key: str) -> bool:
        self._campaign_fleet_row(row_key)
        return self._require_campaign_context().mode == "hard"

    def campaign_fleet_operator_hard_satisfied(
        self, row_key: str
    ) -> Optional[bool]:
        if not self.campaign_fleet_operator_is_hard(row_key):
            return None
        raise SemanticGateClosed(
            "hard-mode campaign fleet restrictions are not typed"
        )

    def campaign_fleet_operator_in_use(self, row_key: str) -> bool:
        return self._campaign_fleet_row(row_key).in_use

    def campaign_fleet_dropdown_opened(self) -> bool:
        return self.oracle.campaign_fleet_dropdown_state() is not None

    def campaign_fleet_selected_indices(self, row_key: str) -> List[int]:
        context = self._require_campaign_context()
        if context.fleet_dropdown_row != row_key:
            raise SemanticGateClosed("campaign fleet dropdown row identity changed")
        state = self.oracle.campaign_fleet_dropdown_state()
        if state is None:
            raise SemanticGateClosed("campaign fleet dropdown is not open")
        return list(state.active_indices)

    def confirm_campaign_fleet_selection(self) -> CampaignFleetSelectionState:
        context = self._require_campaign_context()
        if context.initial_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed("campaign fleet preparation was not authorized")
        if context.fleet_dropdown_row is not None:
            raise SemanticGateClosed("campaign fleet dropdown remains open")
        prepared = self.oracle.campaign_fleet_selection_state(context.stage_code)
        if self._campaign_fleet_tuple(prepared) != context.requested_fleets:
            raise SemanticGateClosed("campaign fleet selection did not match the request")
        if len(context.fleet_mutation_receipts) != context.required_fleet_mutations:
            raise SemanticGateClosed("campaign fleet mutation count changed")
        if tuple(
            receipt.semantic_id for receipt in context.fleet_mutation_receipts
        ) != context.expected_fleet_mutations:
            raise SemanticGateClosed("campaign fleet mutation sequence changed")
        if (
            context.required_fleet_mutations > 0
            and prepared.generation <= context.initial_fleet_state.generation
        ):
            raise SemanticGateClosed("campaign fleet selection generation did not advance")
        context.prepared_fleet_state = prepared
        return prepared

    def authorize_campaign_sortie(
        self,
        *,
        use_auto_search: bool,
        use_2x_book: bool,
        submarine_mode: str,
        fleet_order: str,
    ) -> bool:
        """Preflight the separately budgeted exact sortie before any input."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.sortie_receipt is not None or context.sortie_authorized:
            raise SemanticGateClosed("campaign sortie was already authorized")
        if context.sortie_budget == 0:
            return False
        if context.sortie_budget != 1:
            raise SemanticGateClosed(
                "campaign sortie is qualified only with an exact budget of one"
            )
        if context.mode != "normal":
            raise SemanticGateClosed("campaign sortie is qualified only in normal mode")
        if context.prepared_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed("campaign fleet selection was not proven")
        if context.requested_fleets != (1, 2, 0):
            raise SemanticGateClosed(
                "campaign sortie is qualified only for fleets (1, 2, 0)"
            )
        if use_auto_search is not False or use_2x_book is not False:
            raise SemanticGateClosed(
                "campaign sortie requires auto search and 2x book disabled"
            )
        if submarine_mode != "do_not_use":
            raise SemanticGateClosed(
                "campaign sortie requires submarine mode do_not_use"
            )
        if fleet_order != "fleet1_mob_fleet2_boss":
            raise SemanticGateClosed("campaign sortie fleet order is not reviewed")

        prepared = context.prepared_fleet_state
        rows = {row.row_key: row for row in prepared.rows}
        if (
            set(rows) != {"fleet1", "fleet2", "submarine"}
            or not rows["fleet1"].ship_levels
            or not rows["fleet2"].ship_levels
            or rows["submarine"].ship_levels
            or prepared.surface_fleets != (2, 2)
            or prepared.submarine_fleets != (0, 1)
        ):
            raise SemanticGateClosed("campaign sortie fleet validity is not proven")
        if context.oil_before_sortie is None:
            raise SemanticGateClosed("campaign oil was not captured before stage input")
        required_oil = prepared.mob_oil_cost + prepared.boss_oil_cost
        if required_oil <= 0 or context.oil_before_sortie < required_oil:
            raise SemanticGateClosed("campaign sortie oil precondition failed")
        if not prepared.sortie_button.actionable:
            raise SemanticGateClosed("campaign sortie target is not actionable")
        context.sortie_authorized = True
        return True

    def confirm_campaign_sortie(self) -> CampaignSortieProof:
        """Prove one exact sortie input reached the read-only map-scene root."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.sortie_proof is not None:
            return context.sortie_proof
        if (
            not context.sortie_authorized
            or context.sortie_receipt is None
            or context.sortie_budget != 0
            or context.initial_fleet_state is None
            or context.prepared_fleet_state is None
            or context.requested_fleets is None
            or context.oil_before_sortie is None
        ):
            raise SemanticGateClosed("campaign sortie input proof is incomplete")
        entered = self.oracle.campaign_map_entry_state()
        if entered.generation <= context.sortie_receipt.generation:
            raise SemanticGateClosed("campaign map entry did not advance generation")
        context.map_entry_state = entered
        required_oil = (
            context.prepared_fleet_state.mob_oil_cost
            + context.prepared_fleet_state.boss_oil_cost
        )
        context.sortie_proof = CampaignSortieProof(
            stage_code=context.stage_code,
            initial_fleets=self._campaign_fleet_tuple(context.initial_fleet_state),
            requested_fleets=context.requested_fleets,
            prepared_fleets=self._campaign_fleet_tuple(context.prepared_fleet_state),
            mutation_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.fleet_mutation_receipts
            ),
            oil_before_sortie=context.oil_before_sortie,
            required_oil=required_oil,
            sortie_generation=context.sortie_receipt.generation,
            map_generation=entered.generation,
            map_root_path=entered.root_path,
        )
        return context.sortie_proof

    def close_campaign_fleet_dropdown_for_rollback(self) -> None:
        context = self._require_campaign_context()
        state = self.oracle.campaign_fleet_dropdown_state()
        if state is None:
            context.fleet_dropdown_row = None
            context.fleet_dropdown_previous_index = None
            return
        close_index = context.fleet_dropdown_previous_index
        if close_index not in state.active_indices:
            close_index = state.active_indices[0] if state.active_indices else None
        if context.fleet_dropdown_row is None or close_index not in range(1, 7):
            raise SemanticGateClosed(
                "campaign fleet dropdown rollback identity is absent"
            )
        self.oracle.click_campaign_fleet_option(close_index)
        context.fleet_dropdown_row = None
        context.fleet_dropdown_previous_index = None
        context.passive_transition_until = time.monotonic() + 20.0

    def confirm_campaign_fleet_preparation(
        self,
    ) -> CampaignFleetPreparationProof:
        context = self._require_campaign_context()
        if context.fleet_proof is not None:
            return context.fleet_proof
        if (
            context.initial_fleet_state is None
            or context.prepared_fleet_state is None
            or context.requested_fleets is None
        ):
            raise SemanticGateClosed("campaign fleet selection proof is incomplete")
        pre_sortie = self.confirm_campaign_pre_sortie()
        context.fleet_proof = CampaignFleetPreparationProof(
            stage_code=context.stage_code,
            initial_fleets=self._campaign_fleet_tuple(context.initial_fleet_state),
            requested_fleets=context.requested_fleets,
            prepared_fleets=self._campaign_fleet_tuple(context.prepared_fleet_state),
            initial_generation=context.initial_fleet_state.generation,
            prepared_generation=context.prepared_fleet_state.generation,
            mutation_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.fleet_mutation_receipts
            ),
            cancel_generation=pre_sortie.cancel_generation,
            restored_generation=pre_sortie.restored_generation,
        )
        return context.fleet_proof

    def _campaign_preparation_kind(self) -> Optional[str]:
        context = self._require_campaign_context()
        try:
            state = self.oracle.campaign_preparation_state(context.stage_code)
        except SemanticGateClosed:
            if (
                (
                    context.entry_receipt is not None
                    or context.map_preparation_receipt is not None
                    or context.cancel_receipt is not None
                    or context.sortie_receipt is not None
                )
                and time.monotonic() <= context.passive_transition_until
            ):
                return None
            raise
        if state is None:
            return None
        if state.kind not in ("map", "fleet"):
            raise SemanticGateClosed("campaign preparation kind is invalid")
        context.preparation_kind = state.kind
        return state.kind

    def confirm_campaign_pre_sortie(self) -> CampaignPreSortieProof:
        """Prove entry, fleet-preparation cancel, and exact stage restoration."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.proof is not None:
            return context.proof
        if context.entry_receipt is None:
            raise SemanticGateClosed("campaign stage entry was not proven")
        if context.map_preparation_receipt is None:
            raise SemanticGateClosed(
                "campaign map-preparation transition was not proven"
            )
        if context.preparation_kind != "fleet":
            raise SemanticGateClosed(
                "campaign fleet preparation was not proven"
            )
        if context.cancel_receipt is None:
            raise SemanticGateClosed("campaign preparation cancel was not proven")
        restored = self.oracle.campaign_page_state()
        matching = tuple(
            stage
            for stage in restored.stages
            if stage.stage_code == context.stage_code and stage.button.actionable
        )
        if len(matching) != 1:
            raise SemanticGateClosed(
                "campaign stage restoration is absent or ambiguous"
            )
        if restored.generation <= context.cancel_receipt.generation:
            raise SemanticGateClosed(
                "campaign stage restoration did not advance generation"
            )
        context.proof = CampaignPreSortieProof(
            stage_code=context.stage_code,
            chapter_name=restored.chapter_name,
            entry_generation=context.entry_receipt.generation,
            preparation_kind=context.preparation_kind,
            cancel_generation=context.cancel_receipt.generation,
            restored_generation=restored.generation,
        )
        return context.proof

    def end_commission(self) -> None:
        self._commission_context = None

    def _require_mission_context(self) -> _MissionFlowContext:
        if self._mission_context is None:
            raise SemanticGateClosed("mission resource used outside ALAS mission flow")
        return self._mission_context

    def _require_commission_context(self) -> _CommissionFlowContext:
        if self._commission_context is None:
            raise SemanticGateClosed(
                "commission resource used outside ALAS commission flow"
            )
        return self._commission_context

    def _require_campaign_context(self) -> _CampaignFlowContext:
        if self._campaign_context is None:
            raise SemanticGateClosed(
                "campaign resource used outside ALAS pre-sortie flow"
            )
        return self._campaign_context

    def _known_mission_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/task",
                "main/more",
                "reward/page/back",
                "task/page/back",
                "reward/award-info/close",
                "reward/award-info1/close",
                "overlay/bulletin/close",
                "overlay/guild-message/close",
            )
        )

    def _known_login_surface_exists(self) -> bool:
        try:
            # False is still a reviewed login/main/campaign startup surface.
            self.oracle.campaign_is_in_map()
        except SemanticGateClosed:
            return any(
                self.oracle.enabled(target)
                for target in (
                    "overlay/bulletin/close",
                    "overlay/network-reconnect/confirm",
                    "overlay/login-data-expired/confirm",
                )
            )
        return True

    def _login_popup_target(self) -> Optional[str]:
        targets = tuple(
            semantic_id
            for semantic_id in (
                "overlay/login-data-expired/confirm",
                "overlay/network-reconnect/confirm",
            )
            if self.oracle.enabled(semantic_id)
        )
        if len(targets) > 1:
            raise SemanticGateClosed("login popup target is ambiguous")
        return targets[0] if targets else None

    def _record_mission_transition(self, receipt: ActionReceipt) -> ActionReceipt:
        context = self._mission_context
        if context is not None and receipt.semantic_id in (
            "main/more",
            "reward/page/back",
            "main/task",
            "task/page/back",
        ):
            context.passive_transition_until = time.monotonic() + 12.0
        commission_context = self._commission_context
        if commission_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "reward/commission/finish",
            "reward/commission/go",
            "reward/ship-exp/close",
            "reward/award-info/close",
            "reward/award-info1/close",
            "commission/page/back",
            "commission/detail/back",
            "build/page/back",
            "tactical/page/back",
        ):
            commission_context.passive_transition_until = time.monotonic() + 12.0
        research_context = self._research_context
        if research_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/tech",
            "research-menu/research",
            "research-menu/page/back",
            "research/page/back",
            "research/queue/enter",
            "research/detail/queue",
        ):
            research_context.passive_transition_until = time.monotonic() + 12.0
        dorm_context = self._dorm_context
        if dorm_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/live",
            "dorm-menu/dorm",
            "dorm/page/back",
            "dorm/feed",
            "dorm/feed/close",
        ):
            dorm_context.passive_transition_until = time.monotonic() + 12.0
        build_context = self._build_context
        if build_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/build",
            "build/page/back",
        ):
            build_context.passive_transition_until = time.monotonic() + 12.0
        return receipt

    def _known_mail_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/mail",
                "mail/page/back",
                "mail/manage",
                "mail/manage/back",
                "mail/manage/claim",
                "mail/manage/delete",
                "reward/award-info/close",
                "reward/award-info1/close",
            )
        )

    def _known_commission_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/more",
                "reward/page/back",
                "reward/commission/finish",
                "reward/commission/go",
                "commission/page/back",
                "commission/detail/back",
                "commission/detail/recommend",
                "commission/detail/start",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "reward/award-info1/close",
                "tactical/page/back",
                "tactical/continue/cancel",
            )
        )

    def _known_research_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/tech",
                "research-menu/page/back",
                "research-menu/research",
                "research/page/back",
                "research/queue/enter",
                "research/detail/root",
            )
        )

    def _known_dorm_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/live",
                "dorm-menu/page/root",
                "dorm-menu/dorm",
                "dorm/page/back",
                "dorm/page/manage",
                "dorm/feed",
                "dorm/feed/close",
            )
        )

    def _known_build_surface_exists(self) -> bool:
        if any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/build",
                "build/page/start",
                "build/page/back",
                "build/prep/confirm",
            )
        ):
            return True
        try:
            self.oracle.build_queue_timers()
        except SemanticGateClosed:
            return False
        return True

    def _known_campaign_surface_exists(self) -> bool:
        if self._campaign_context is not None:
            try:
                if self._campaign_preparation_kind() is not None:
                    return True
            except SemanticGateClosed:
                pass
        try:
            # Either result is a positive proof that the observer recognizes
            # the current campaign surface.  ``True`` means the exact map
            # root is present; ``False`` means one of the reviewed non-map
            # startup surfaces is present.  Only an exception is unknown.
            self.oracle.campaign_is_in_map()
        except SemanticGateClosed:
            return False
        return True

    def _active_flow_allows_passive_probe(self) -> bool:
        now = time.monotonic()
        if (
            self._login_context is not None
            and (
                now <= self._login_context.passive_transition_until
                or self._known_login_surface_exists()
            )
        ):
            return True
        if (
            self._mission_context is not None
            and (
                now <= self._mission_context.passive_transition_until
                or self._known_mission_surface_exists()
            )
        ):
            return True
        if self._mail_context is not None and self._known_mail_surface_exists():
            return True
        if (
            self._commission_context is not None
            and (
                now <= self._commission_context.passive_transition_until
                or self._known_commission_surface_exists()
            )
        ):
            return True
        if (
            self._research_context is not None
            and (
                now <= self._research_context.passive_transition_until
                or self._known_research_surface_exists()
            )
        ):
            return True
        if (
            self._dorm_context is not None
            and (
                now <= self._dorm_context.passive_transition_until
                or self._known_dorm_surface_exists()
            )
        ):
            return True
        if (
            self._build_context is not None
            and (
                now <= self._build_context.passive_transition_until
                or self._known_build_surface_exists()
            )
        ):
            return True
        if (
            self._campaign_context is not None
            and (
                now <= self._campaign_context.passive_transition_until
                or self._known_campaign_surface_exists()
            )
        ):
            return True
        return False

    def _stable_mission_state(self) -> Optional[MissionPageState]:
        context = self._require_mission_context()
        candidate = self.oracle.mission_page_state()

        if candidate.disposition == MissionDisposition.UNKNOWN:
            context.last_signature = None
            context.last_generation = -1
            context.stable_generations = 0
            context.stable_state = None
            return None

        if candidate.signature != context.last_signature:
            context.last_signature = candidate.signature
            context.last_generation = candidate.generation
            context.stable_generations = 1
            context.stable_state = None
            return None

        if candidate.generation > context.last_generation:
            context.last_generation = candidate.generation
            context.stable_generations += 1
            if context.stable_generations >= 2:
                context.stable_state = candidate
        return context.stable_state

    def _mission_notice_appears(self) -> bool:
        context = self._require_mission_context()
        # The current typed observer does not expose the red-dot Image.  A
        # scheduled daily mission run may safely inspect the proven main task
        # entry instead.  Weekly-only runs stay closed until tab evidence exists.
        return bool(context.daily and self.oracle.exists("main/task"))

    def _award_close_target(self) -> Optional[str]:
        targets = tuple(
            semantic_id
            for semantic_id in (
                "reward/award-info/close",
                "reward/award-info1/close",
            )
            if self.oracle.enabled(semantic_id)
        )
        if len(targets) > 1:
            raise SemanticGateClosed("reward popup close target is ambiguous")
        return targets[0] if targets else None

    def _goto_main_target(self) -> Optional[str]:
        targets = []
        if self.oracle.campaign_menu_is_entry() and self.oracle.enabled(
            "campaign-menu/page/back"
        ):
            targets.append("campaign-menu/page/back")
        try:
            self.oracle.build_queue_timers()
        except SemanticGateClosed:
            pass
        else:
            if self.oracle.enabled("build/page/back"):
                targets.append("build/page/back")
        for identity, target in (
            ("task/page/back", "task/page/back"),
            ("build/page/start", "build/page/back"),
            ("research-menu/page/back", "research-menu/page/back"),
            ("research/page/back", "research/page/back"),
        ):
            if self.oracle.exists(identity) and self.oracle.enabled(target):
                targets.append(target)
        unique = tuple(dict.fromkeys(targets))
        if len(unique) > 1:
            raise SemanticGateClosed("GOTO_MAIN target is ambiguous")
        return unique[0] if unique else None

    def _mission_resource_appears(self, name: str) -> bool:
        self._require_mission_context()
        if name in ("MISSION_NOTICE", "MISSION_NOTICE_WHITE"):
            return self._mission_notice_appears()
        if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
            return self._award_close_target() is not None
        if name in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"):
            return self.oracle.enabled("overlay/guild-message/close")
        if name == "GET_SHIP":
            # Ship-reward handling has no reviewed semantic contract in this
            # slice.  The validated AwardInfo popup is handled before this test.
            return False
        if name == "MISSION_WEEKLY_RED_DOT":
            return False

        state = self._stable_mission_state()
        if state is None:
            return False
        if name == "MISSION_MULTI":
            return state.disposition == MissionDisposition.CLAIMABLE_ALL
        if name == "MISSION_SINGLE":
            return state.disposition == MissionDisposition.CLAIMABLE_ROW
        if name == "MISSION_UNFINISH":
            return state.disposition == MissionDisposition.UNFINISHED
        if name == "MISSION_EMPTY":
            return state.disposition == MissionDisposition.EMPTY
        raise AlasSemanticUnmapped(
            "ALAS mission resource is not semantically mapped: {0}".format(name)
        )

    def appear(self, button: Any) -> bool:
        """Run one presence probe with a bounded render-transition grace."""

        try:
            result = self._appear_once(button)
        except SemanticGateClosed as exc:
            message = str(exc)
            transient = message in (
                "observer snapshot is stale",
                "observer endpoints are not generation-coherent",
                "Msgbox snapshots are not coherent",
            )
            if (
                message == "game activity is not top-resumed"
                and self._login_context is not None
            ):
                transient = True
            if not transient:
                raise
            now = time.monotonic()
            if self._observer_stale_since is None:
                self._observer_stale_since = now
            if (
                self._login_context is not None
                and now <= self._login_context.passive_transition_until
            ):
                return False
            if now - self._observer_stale_since <= 5.0:
                return False
            raise
        self._observer_stale_since = None
        return result

    def _appear_once(self, button: Any) -> bool:
        name = self._button_name(button)
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        if campaign_stage_code is not None:
            self._package_gate()
            context = self._require_campaign_context()
            if (
                not isinstance(campaign_stage_code, str)
                or campaign_stage_code != context.stage_code
                or name != campaign_stage_code
            ):
                raise SemanticGateClosed("campaign stage identity changed")
            try:
                return self.oracle.campaign_stage_actionable(campaign_stage_code)
            except SemanticGateClosed:
                if (
                    context.entry_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return False
                raise
        semantic_id = self._mappings.get(name)
        if self._login_context is not None and name == "POPUP_CONFIRM":
            return self._login_popup_target() is not None
        if (
            self._login_context is not None
            and semantic_id == "login/enter"
            and self._login_context.entry_receipt is not None
            and time.monotonic() <= self._login_context.passive_transition_until
        ):
            return False
        if (
            semantic_id is None
            and name not in MISSION_VIRTUAL_RESOURCES
            and name not in MAIL_VIRTUAL_RESOURCES
            and name not in COMMISSION_VIRTUAL_RESOURCES
            and name not in CAMPAIGN_VIRTUAL_RESOURCES
            and name not in PAGE_VIRTUAL_RESOURCES
            and name not in RESEARCH_VIRTUAL_RESOURCES
            and name not in DORM_VIRTUAL_RESOURCES
            and name not in BUILD_VIRTUAL_RESOURCES
            and name not in TACTICAL_VIRTUAL_RESOURCES
        ):
            if (
                self._mission_context is None
                and self._login_context is None
                and self._mail_context is None
                and self._commission_context is None
                and self._research_context is None
                and self._dorm_context is None
                and self._build_context is None
                and self._campaign_context is None
            ):
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                )
            self._package_gate()
            if (
                self._login_context is not None
                and time.monotonic()
                <= self._login_context.passive_transition_until
            ):
                return False
            if (
                self._mission_context is not None
                and time.monotonic()
                <= self._mission_context.passive_transition_until
            ):
                return False
            if (
                self._commission_context is not None
                and time.monotonic()
                <= self._commission_context.passive_transition_until
            ):
                return False
            if (
                self._research_context is not None
                and time.monotonic()
                <= self._research_context.passive_transition_until
            ):
                return False
            if (
                self._dorm_context is not None
                and time.monotonic()
                <= self._dorm_context.passive_transition_until
            ):
                return False
            if (
                self._build_context is not None
                and time.monotonic()
                <= self._build_context.passive_transition_until
            ):
                return False
            if (
                self._campaign_context is not None
                and time.monotonic()
                <= self._campaign_context.passive_transition_until
            ):
                return False
            if (
                self._login_context is not None
                and self._known_login_surface_exists()
            ) or (
                self._mission_context is not None
                and self._known_mission_surface_exists()
            ) or (
                self._mail_context is not None
                and self._known_mail_surface_exists()
            ) or (
                self._commission_context is not None
                and self._known_commission_surface_exists()
            ) or (
                self._research_context is not None
                and self._known_research_surface_exists()
            ) or (
                self._dorm_context is not None
                and self._known_dorm_surface_exists()
            ) or (
                self._build_context is not None
                and self._known_build_surface_exists()
            ) or (
                self._campaign_context is not None
                and self._known_campaign_surface_exists()
            ):
                # ALAS scans many page/popup assets.  An independently proven
                # mission surface lets unknown presence checks be safely false;
                # unknown clicks remain forbidden.
                return False
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(name)
            )
        self._package_gate()
        if self._mission_context is not None:
            if (
                semantic_id == "main/more"
                and self._mission_context.summary_entry_clicked
            ):
                return False
            if semantic_id == "main/task" and self._mission_context.entry_clicked:
                return False
        if name in PAGE_VIRTUAL_RESOURCES:
            if (
                name == "DORM_CHECK"
                and self._dorm_context is not None
                and (
                    self.oracle.dorm_empty_food_cancel_available()
                    or self.oracle.enabled("dorm/feed/close")
                )
            ):
                # Do not report the CourtYard page through its modal empty-food
                # prompt.  This lets ALAS reach ui_additional() and invoke its
                # own dedicated DORM_FEED_CANCEL branch.
                return False
            if name == "RESEARCH_CHECK" and self._research_context is not None:
                try:
                    return len(self.oracle.research_projects()) == 5
                except SemanticGateClosed:
                    return False
            target = {
                "BUILD_CHECK": "build/page/start",
                "DORMMENU_CHECK": "dorm-menu/page/root",
                "DORM_CHECK": "dorm/page/manage",
                "RESHMENU_CHECK": "research-menu/page/back",
                "RESEARCH_CHECK": "research/page/back",
                "TACTICAL_CHECK": "tactical/page/back",
            }[name]
            return self.oracle.exists(target)
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_FLEET_ROW_RESOURCES
        ):
            row_key, action = CAMPAIGN_FLEET_ROW_RESOURCES[name]
            if action == "advice":
                return self.campaign_fleet_operator_is_hard(row_key)
            if action == "clear":
                return self.campaign_fleet_row_allowed(row_key)
            return not self.campaign_fleet_dropdown_opened()
        if self._campaign_context is not None and name == "EVENT_LIST_CHECK":
            return self.oracle.exists("event-list/page/back")
        if self._campaign_context is not None and name == "BACK_ARROW":
            return self.oracle.enabled("event-list/page/back")
        if self._campaign_context is not None and name in (
            "SWITCH_1_NORMAL",
            "SWITCH_1_HARD",
        ):
            expected = "normal" if name == "SWITCH_1_NORMAL" else "hard"
            return self.oracle.campaign_mode_switch_state() == expected
        if self._campaign_context is not None and name in (
            "SWITCH_2_HARD",
            "SWITCH_2_EX",
        ):
            # Main campaign chapters expose only the normal/hard switch.  The
            # second switch belongs to event EX pages and is presence-only in
            # ALAS' generic ModeSwitch probe.
            return False
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_AUTO_SEARCH_RESOURCES
        ):
            context = self._require_campaign_context()
            if context.map_preparation_receipt is not None:
                return False
            if self._campaign_preparation_kind() != "map":
                return False
            selected = self.oracle.toggle_selected(
                "campaign/map-preparation/auto-search"
            )
            return (
                selected
                if name in CAMPAIGN_AUTO_SEARCH_ON_RESOURCES
                else not selected
            )
        if self._campaign_context is not None and name in (
            "MAP_PREPARATION",
            "FLEET_PREPARATION",
            "MAP_PREPARATION_CANCEL",
        ):
            if (
                name == "MAP_PREPARATION"
                and self._campaign_context.map_preparation_receipt is not None
            ):
                return False
            kind = self._campaign_preparation_kind()
            if name == "MAP_PREPARATION":
                return kind == "map"
            if name == "FLEET_PREPARATION":
                if kind != "fleet":
                    return False
                if self._campaign_context.map_preparation_receipt is None:
                    raise SemanticGateClosed(
                        "campaign fleet preparation appeared without map transition"
                    )
                return True
            return kind in ("map", "fleet")
        if name in RESEARCH_VIRTUAL_RESOURCES and self._research_context is not None:
            if name == "QUEUE_CHECK":
                try:
                    self.research_queue_state()
                    return True
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_GOTO_QUEUE":
                return self.oracle.enabled("research/queue/enter")
            if name in ("DETAIL_NEXT", "RESEARCH_COST_CHECKER"):
                try:
                    self.oracle.research_detail_state()
                    return True
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_START":
                try:
                    detail = self.oracle.research_detail_state()
                except SemanticGateClosed:
                    return False
                return (
                    detail.can_start
                    and self._research_context.start_budget > 0
                    and self._research_context.start_receipt is None
                )
            if name in ("POPUP_CANCEL", "POPUP_CONFIRM"):
                context = self._research_context
                if context.queue_add_receipt is not None:
                    target = (
                        "research/queue/cancel"
                        if name == "POPUP_CANCEL"
                        else "research/queue/confirm"
                    )
                    return bool(
                        context.queue_confirm_receipt is None
                        and self.oracle.enabled(target)
                    )
                cost = self.oracle.research_start_prompt_cost()
                return bool(
                    context.start_receipt is not None
                    and context.start_confirm_receipt is None
                    and context.start_budget > 0
                    and cost is not None
                    and cost
                    == (context.pending_resource_id, context.pending_resource_required)
                )
            if name == "RESEARCH_UNAVAILABLE":
                try:
                    self.oracle.research_detail_state()
                except SemanticGateClosed:
                    return False
                return not self.research_detail_available()
            if name == "RESEARCH_STOP":
                return self.research_detail_is_running()
            if name == "RESEARCH_QUEUE_ADD":
                return self.research_detail_can_queue()
            if name == "RESEARCH_DETAIL_QUIT":
                return self.oracle.enabled("research/detail/root")
            if name == "QUEUE_CLAIM_REWARD":
                try:
                    queue = self.research_queue_state()
                except SemanticGateClosed:
                    return False
                return queue.reward_claimable and self._research_context.reward_budget > 0
            if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3", "GET_ITEMS_RESEARCH_SAVE"):
                return bool(
                    self._research_context.reward_receipts
                    and self._award_close_target() is not None
                )
            if name == "BACK_ARROW":
                return self.oracle.enabled("research/page/back")
        research_entrance = re.fullmatch(r"ENTRANCE_([1-5])", name)
        if research_entrance is not None and self._research_context is not None:
            slot = int(research_entrance.group(1))
            try:
                return any(
                    project.slot == slot and project.button.actionable
                    for project in self.oracle.research_projects()
                )
            except SemanticGateClosed:
                return False
        if name in DORM_VIRTUAL_RESOURCES and self._dorm_context is not None:
            if name == "DORM_QUICK_COLLECT":
                return (
                    self._dorm_context.collect_budget > 0
                    and self.oracle.enabled("dorm/collect")
                )
            if name == "DORM_FEED_ENTER":
                if self.oracle.enabled("dorm/feed/close"):
                    return True
                return self.oracle.enabled("dorm/feed")
            if name == "DORM_FEED_CHECK":
                try:
                    self.oracle.dorm_feed_state()
                    self._dorm_context.feed_panel_observed = True
                    return True
                except SemanticGateClosed:
                    return False
            if name == "DORM_FEED_CANCEL":
                if self.oracle.dorm_empty_food_cancel_available():
                    return True
                if not self.oracle.enabled("dorm/feed/close"):
                    return False
                context = self._dorm_context
                return not (
                    context.feed_entry_receipt is not None
                    and not context.feed_panel_observed
                    and time.monotonic() <= context.passive_transition_until
                )
            if name == "POPUP_CANCEL":
                return self.oracle.enabled("dorm/feed/shop/cancel")
        if name in BUILD_VIRTUAL_RESOURCES and self._build_context is not None:
            if name == "BUILD_SUBMIT_ORDERS":
                return self.oracle.enabled("build/page/start")
            if name in ("BUILD_SUBMIT_WW_ORDERS", "BUILD_WW_CHECK", "SHOP_MEDAL_CHECK"):
                return False
            if name == "BUILD_QUEUE_EMPTY":
                empty = self.oracle.build_queue_empty()
                if not empty and self._build_context.submit_receipt is None:
                    raise SemanticGateClosed(
                        "construction queue must be empty before a bounded submit"
                    )
                return empty
            if name == "BUILD_FINISH_ORDERS":
                try:
                    self.oracle.build_queue_timers()
                    return True
                except SemanticGateClosed:
                    return False
            if name == "BUILD_MINUS":
                return self.oracle.enabled("build/prep/minus")
            if name == "BUILD_PLUS":
                return self.oracle.enabled("build/prep/add")
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_PREP"):
                if self.oracle.enabled("build/warning/confirm"):
                    return not self._build_context.warning_confirmed
                return False
            if name == "POPUP_CONFIRM_GACHA_ORDER":
                return bool(
                    self.oracle.enabled("build/prep/confirm")
                    and self._build_context.submit_receipt is None
                )
            if name == "POPUP_CANCEL":
                return bool(
                    self.oracle.enabled("build/warning/cancel")
                    or self.oracle.enabled("build/prep/cancel")
                )
        if (
            name in TACTICAL_VIRTUAL_RESOURCES
            and self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
        ):
            if name == "ADD_NEW_STUDENT":
                try:
                    return len(self.oracle.tactical_slots()) < 4
                except SemanticGateClosed:
                    return False
            if name == "DOCK_CHECK":
                try:
                    return bool(self.oracle.tactical_candidate_ships())
                except SemanticGateClosed:
                    return False
            if name == "SKILL_CONFIRM":
                try:
                    return bool(self.oracle.tactical_skills())
                except SemanticGateClosed:
                    return False
            if name == "BACK_ARROW":
                return any(
                    self.oracle.enabled(target)
                    for target in (
                        "tactical/dock/back",
                        "tactical/page/back",
                    )
                )
            if name in ("TACTICAL_CLASS_START", "TACTICAL_CLASS_CANCEL"):
                target = (
                    "tactical/book/start"
                    if name == "TACTICAL_CLASS_START"
                    else "tactical/book/cancel"
                )
                return self.oracle.enabled(target)
            if name == "POPUP_CONFIRM":
                return (
                    self._commission_context.assign_budget > 0
                    and self.oracle.enabled("tactical/course/confirm")
                )
        if semantic_id is None and name == "CAMPAIGN_MENU_CHECK":
            if self.oracle.campaign_menu_is_entry():
                return True
            # MAIN_GOTO_CAMPAIGN resumes an unfinished sortie directly into
            # LevelGrid.  Treat that exact map root as completion of the UI
            # graph's campaign-menu hop; CampaignRun immediately performs its
            # own IN_MAP branch and retains state-machine ownership.
            return self.oracle.campaign_is_in_map()
        if semantic_id is None and name == "CAMPAIGN_CHECK":
            if self._campaign_context is not None:
                if self._campaign_preparation_kind() is not None:
                    return False
                if (
                    self._campaign_context.map_preparation_receipt is not None
                    and self._campaign_context.cancel_receipt is None
                    and time.monotonic()
                    <= self._campaign_context.passive_transition_until
                ):
                    return False
                try:
                    return self.oracle.campaign_page_is_normal()
                except SemanticGateClosed:
                    if (
                        time.monotonic()
                        <= self._campaign_context.passive_transition_until
                    ):
                        return False
                    raise
            return self.oracle.campaign_page_is_normal()
        if semantic_id is None and name == "IN_MAP":
            if self._campaign_context is not None:
                if self._campaign_context.sortie_receipt is not None:
                    try:
                        return self.oracle.campaign_is_in_map()
                    except SemanticGateClosed:
                        if (
                            time.monotonic()
                            <= self._campaign_context.passive_transition_until
                        ):
                            return False
                        raise
                if self._campaign_preparation_kind() is not None:
                    return False
                if (
                    self._campaign_context.map_preparation_receipt is not None
                    and time.monotonic()
                    <= self._campaign_context.passive_transition_until
                ):
                    return False
            return self.oracle.campaign_is_in_map()
        if semantic_id is None and name == "GOTO_MAIN":
            return self._goto_main_target() is not None
        if self._mail_context is not None and name == "MAIL_MANAGE":
            return self.oracle.enabled("mail/manage")
        if semantic_id is None:
            if (
                self._commission_context is not None
                and name in COMMISSION_VIRTUAL_RESOURCES
            ):
                tab_target = COMMISSION_TAB_TARGETS.get(name)
                if tab_target is not None:
                    return self.oracle.image_selected(tab_target)
                if name in ("COMMISSION_ADVICE", "COMMISSION_START"):
                    context = self._commission_context
                    if context.selected_signature is None:
                        return False
                    try:
                        detail = self.oracle.commission_detail_state()
                    except SemanticGateClosed:
                        if time.monotonic() - context.selected_at <= 12.0:
                            return False
                        raise
                    expected = context.selected_signature
                    if detail.signature != (expected[1], expected[2], expected[3]):
                        raise SemanticGateClosed(
                            "selected commission detail identity changed"
                        )
                    if name == "COMMISSION_ADVICE":
                        return detail.selected_ship_count < 3
                    return (
                        detail.selected_ship_count >= 3
                        and detail.oil_cost == 0
                        and context.start_budget > 0
                        and context.start_receipt is None
                    )
                if name == "EXP_INFO_S_REWARD":
                    return self.oracle.enabled("reward/ship-exp/close")
                if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                    return self._award_close_target() is not None
                if name == "GET_SHIP":
                    return False
            if self._mail_context is not None and name in MAIL_VIRTUAL_RESOURCES:
                if name == "GOTO_MAIN_WHITE":
                    return self.oracle.enabled("mail/page/back")
                if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                    return self._award_close_target() is not None
                if name == "MAIL_BATCH_CLAIM":
                    return self.oracle.enabled("mail/manage/claim")
                if name == "MAIL_BATCH_DELETE":
                    return self.oracle.enabled("mail/manage/delete")
                if name == "MAIL_WHITE_EMPTY":
                    return self.oracle.mail_is_empty()
                return False
            if (
                self._mission_context is not None
                and name in MISSION_VIRTUAL_RESOURCES
            ):
                return self._mission_resource_appears(name)
            if self._active_flow_allows_passive_probe():
                # ALAS' generic page and popup loops probe resources owned by
                # unrelated modules.  On an independently proven active-flow
                # surface, those presence-only probes are safely absent; the
                # same resources remain forbidden to click().
                return False
            if name in MAIL_VIRTUAL_RESOURCES and name not in MISSION_VIRTUAL_RESOURCES:
                raise AlasSemanticUnmapped(
                    "ALAS mail resource used outside mail flow: {0}".format(name)
                )
            if name in MISSION_VIRTUAL_RESOURCES:
                raise AlasSemanticUnmapped(
                    "ALAS mission resource used outside mission flow: {0}".format(name)
                )
            raise AlasSemanticUnmapped(
                "ALAS virtual resource has no active semantic flow: {0}".format(name)
            )
        # enabled() includes active/interactable/bounds and blocker checks.  A
        # Unity object hidden behind an overlay must not count as visible to ALAS.
        return self.oracle.enabled(semantic_id)

    def bounds(self, button: Any) -> Bounds:
        semantic_id = self.semantic_id_for(button)
        self._package_gate()
        return self.oracle.bounds(semantic_id)

    @staticmethod
    def _ocr_bounds(areas: Sequence[Any]) -> Tuple[Bounds, ...]:
        result = []
        for area in areas:
            if not isinstance(area, (tuple, list)) or len(area) != 4:
                raise SemanticGateClosed("semantic OCR area is malformed")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in area):
                raise SemanticGateClosed("semantic OCR area is not numeric")
            left, top, right, bottom = (float(value) for value in area)
            if not (0 <= left < right <= 1280 and 0 <= top < bottom <= 720):
                raise SemanticGateClosed("semantic OCR area is outside the logical screen")
            result.append(Bounds(left, top, right, bottom))
        if not result:
            raise SemanticGateClosed("semantic OCR requires at least one reviewed area")
        return tuple(result)

    @staticmethod
    def _normalize_typed_text(value: str) -> str:
        # Unity Text/TMP expose source text, which can contain rich-text tags
        # that an image OCR engine would never see.
        value = re.sub(r"<[^<>]{1,128}>", "", value)
        value = value.replace("\u00a0", " ").replace("\u3000", " ")
        return "".join(value.split())

    def ocr_text(
        self,
        areas: Sequence[Any],
        alphabet: Optional[str] = None,
    ) -> Union[str, List[str]]:
        """Return typed Unity text for ALAS OCR rectangles.

        The bridge requires an observed Text/TMP component substantially inside
        every OCR rectangle.  Missing, overlapping, truncated, or out-of-
        alphabet records close the gate instead of falling back to pixels.
        """

        self._package_gate()
        bounds = self._ocr_bounds(areas)
        groups = self.oracle.text_groups_in_bounds(bounds)
        values: List[str] = []
        for group in groups:
            observed = []
            seen = set()
            for text_state in group:
                if text_state.bounds is None:
                    continue
                if text_state.truncated:
                    raise SemanticGateClosed(
                        "semantic OCR target text is truncated"
                    )
                value = self._normalize_typed_text(text_state.text)
                identity = (
                    value,
                    round(text_state.bounds.left, 1),
                    round(text_state.bounds.top, 1),
                    round(text_state.bounds.right, 1),
                    round(text_state.bounds.bottom, 1),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                observed.append((text_state, value))
            if not observed:
                raise SemanticGateClosed("semantic OCR area has no typed text")

            for index, (left_state, _) in enumerate(observed):
                for right_state, _ in observed[index + 1 :]:
                    if left_state.bounds is None or right_state.bounds is None:
                        raise SemanticGateClosed("semantic OCR text has no bounds")
                    overlap = self.oracle._bounds_overlap(
                        left_state.bounds, right_state.bounds
                    )
                    left_area = (
                        left_state.bounds.right - left_state.bounds.left
                    ) * (left_state.bounds.bottom - left_state.bounds.top)
                    right_area = (
                        right_state.bounds.right - right_state.bounds.left
                    ) * (right_state.bounds.bottom - right_state.bounds.top)
                    if overlap > 0.1 * min(left_area, right_area):
                        raise SemanticGateClosed(
                            "semantic OCR area contains overlapping text records"
                        )
            value = "".join(item[1] for item in observed)
            if alphabet is not None and any(
                character not in alphabet for character in value
            ):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            values.append(value)
        return values[0] if len(values) == 1 else values

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research projects used outside ALAS research flow")
        try:
            projects = self.oracle.research_projects()
        except SemanticGateClosed:
            if (
                self._research_context.last_projects is None
                or time.monotonic()
                - self._research_context.last_projects_observed_at
                > 5.0
            ):
                raise
            return self._research_context.last_projects
        self._research_context.last_projects = projects
        self._research_context.last_projects_observed_at = time.monotonic()
        return projects

    def research_detail_state(self) -> ResearchDetailState:
        self._package_gate()
        return self.oracle.research_detail_state()

    def research_detail_available(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        try:
            detail = self.oracle.research_detail_state()
            return bool(
                detail.can_start
                and self._research_context.start_budget > 0
                and self._research_context.start_receipt is None
            )
        except SemanticGateClosed:
            if self._active_flow_allows_passive_probe():
                return False
            raise

    def research_detail_is_running(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        return self.oracle.enabled("research/detail/stop")

    def research_detail_can_queue(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        return self.oracle.research_queue_add_available()

    def research_queue_state(self) -> ResearchQueueState:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research queue used outside ALAS research flow")
        try:
            state = self.oracle.research_queue_state()
        except SemanticGateClosed:
            if (
                self._research_context.last_queue_state is None
                or time.monotonic()
                - self._research_context.last_queue_observed_at
                > 30.0
            ):
                raise
            return self._research_context.last_queue_state
        self._research_context.last_queue_state = state
        self._research_context.last_queue_observed_at = time.monotonic()
        return state

    def research_queue_empty_slots(self) -> int:
        return self.research_queue_state().empty_slots

    def research_queue_fill_slots(self) -> int:
        """Return the slots ALAS may fill under this run's mutation budget."""

        if self._research_context is None:
            raise SemanticGateClosed("research queue used outside ALAS research flow")
        if self._research_context.start_budget <= 0:
            return 0
        return self.research_queue_empty_slots()

    def research_queue_remaining_seconds(self) -> int:
        return self.research_queue_state().first_remaining_seconds

    def build_selected_pool(self) -> BuildPool:
        self._package_gate()
        return self.oracle.build_selected_pool()

    def build_costs(self) -> BuildCostState:
        self._package_gate()
        return self.oracle.build_costs()

    def dorm_state(self) -> DormState:
        self._package_gate()
        return self.oracle.dorm_state()

    def dorm_feed_state(self) -> DormFeedState:
        self._package_gate()
        # BackYardFeedUI rebuilds its typed hierarchy while food counters tick.
        # ALAS polls this panel repeatedly during one feed pass, so wait for one
        # complete snapshot while still failing closed if none stabilizes.
        return self._stable_dorm_feed_state()

    def dorm_food_counts(self) -> Tuple[int, ...]:
        return tuple(item.count for item in self.dorm_feed_state().items)

    def _stable_dorm_feed_state(self, timeout_seconds: float = 5.0) -> DormFeedState:
        deadline = time.monotonic() + timeout_seconds
        last_error: Optional[SemanticOracleError] = None
        while True:
            try:
                return self.oracle.dorm_feed_state()
            except SemanticOracleError as exc:
                last_error = exc
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "stable dorm feed-state wait timed out"
                ) from last_error
            time.sleep(0.25)

    def dorm_feed_food(self, item_index: int, count: int) -> Tuple[ActionReceipt, ...]:
        """Apply ALAS' chosen food/count through exact per-item Buttons."""

        if item_index not in range(6):
            raise ValueError("dorm food index must be 0 through 5")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("dorm feed count must be a non-negative integer")
        if self._dorm_context is None:
            raise SemanticGateClosed("dorm feed used outside ALAS dorm flow")
        context = self._dorm_context
        if count > context.feed_budget:
            raise SemanticGateClosed("dorm feed count exceeds the remaining budget")
        receipts = []
        for _ in range(count):
            before = self._stable_dorm_feed_state()
            item = before.items[item_index]
            if item.count <= 0 or before.food + item.value > before.capacity:
                raise SemanticGateClosed("dorm feed item is unavailable or would overflow")
            receipt = self.oracle.click_dorm_food(item.item_id)
            clicked_at = time.monotonic()
            context.feed_budget -= 1
            receipts.append(receipt)
            deadline = time.monotonic() + 5.0
            last_error: Optional[SemanticOracleError] = None
            while True:
                try:
                    after = self.oracle.dorm_feed_state()
                    after_item = after.items[item_index]
                    # Up to six ships consume at most 18 food per 15-second
                    # tick.  A tick can straddle either snapshot boundary, so
                    # admit only the bounded concurrent decrease while the
                    # independent inventory counter must still be exactly -1.
                    elapsed = max(0.0, time.monotonic() - clicked_at)
                    max_consumption = 18 * (int(elapsed // 15.0) + 2)
                    minimum_food = before.food + item.value - max_consumption
                    if (
                        after_item.count == item.count - 1
                        and minimum_food <= after.food <= before.food + item.value
                    ):
                        break
                    last_error = None
                except SemanticOracleError as exc:
                    # Food-card images briefly leave the hierarchy during the
                    # consume animation.  The input has already happened, so
                    # wait for the same postcondition without replaying it.
                    last_error = exc
                if time.monotonic() >= deadline:
                    error = SemanticGateClosed("dorm feed mutation was not proven")
                    if last_error is not None:
                        raise error from last_error
                    raise error
                time.sleep(0.25)
        return tuple(receipts)

    def build_submit_state(self) -> BuildSubmitState:
        self._package_gate()
        return self.oracle.build_submit_state()

    def build_coins_owned(self) -> int:
        if self._build_context is None:
            raise SemanticGateClosed(
                "construction coin count used outside ALAS build flow"
            )
        if self._build_context.coins_owned is None:
            # A task may legitimately start while ALAS is already on page_build,
            # so MAIN_GOTO_BUILD is not guaranteed to run.  The proven Build
            # resource panel supplies the same owned-coin value in that case.
            self._build_context.coins_owned = self.oracle.build_coins_owned()
        return self._build_context.coins_owned

    def campaign_page_state(self) -> CampaignPageState:
        self._package_gate()
        last_error = None
        for _ in range(4):
            try:
                state = self.oracle.campaign_page_state()
                if self._campaign_context is not None:
                    self._campaign_context.passive_transition_until = (
                        time.monotonic() + 20.0
                    )
                return state
            except SemanticGateClosed as exc:
                if str(exc) not in (
                    "observer endpoints are not generation-coherent",
                    "campaign snapshots are not coherent",
                ):
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    def campaign_oil(self) -> int:
        self._package_gate()
        self._require_campaign_context()
        return self.oracle.campaign_oil()

    def campaign_map_state(
        self,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        """Supply one read-only typed map input to the ALAS campaign flow."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.mode != "normal":
            raise SemanticGateClosed(
                "campaign map model is qualified only in normal mode"
            )
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=columns,
            rows=rows,
            land_cells=land_cells,
            expected_fleet_count=expected_fleet_count,
        )

        context.map_state = state
        context.map_columns = columns
        context.map_rows = rows
        context.map_land_cells = tuple(tuple(item) for item in land_cells)
        context.map_expected_fleet_count = expected_fleet_count
        return state

    def authorize_campaign_combat(
        self,
        decision: AlasCampaignDecisionPreview,
        state: CampaignMapState,
    ) -> Optional[AlasCampaignCombatAdmission]:
        """Prepare one exact combat grid input without consuming its budget."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.combat_budget == 0:
            return None
        if context.combat_budget != 1:
            raise SemanticGateClosed(
                "campaign combat requires exactly one remaining budget unit"
            )
        if (
            context.combat_admission is not None
            or context.combat_receipt is not None
            or context.combat_proof is not None
        ):
            raise SemanticGateClosed("campaign combat admission is single-use")
        if context.map_state is not state:
            raise SemanticGateClosed("campaign combat map state is not current")
        target = self.oracle.campaign_map_cell_viewport_target(
            state, decision.target_node
        )
        # A one-unit viewport budget explicitly arms one ALAS-owned camera
        # move for this admitted target.  This is independent of whether the
        # cell is already top-raycast: original ALAS may still center a
        # visible target before its grid click.  A covered target remains
        # forbidden unless that separate capability was granted.
        viewport_required = context.viewport_swipe_budget == 1
        if target.raycast_top is not True and not viewport_required:
            raise SemanticGateClosed(
                "campaign combat covered target requires one viewport swipe budget"
            )
        admission = prepare_alas_campaign_combat_admission(
            decision,
            state,
            input_generation=state.generation,
        )
        if (
            target.path != admission.cell_path
            or target.point != admission.point
            or target.bounds != admission.bounds
        ):
            raise SemanticGateClosed("campaign combat target changed during preflight")
        context.combat_admission = admission
        context.viewport_swipe_required = viewport_required
        return admission

    @staticmethod
    def _campaign_swipe_pair(value: Any, label: str) -> Tuple[float, float]:
        try:
            pair = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(pair) != 2 or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in pair
        ):
            raise SemanticGateClosed(label + " is malformed")
        return float(pair[0]), float(pair[1])

    @staticmethod
    def _campaign_swipe_box(
        value: Any, label: str
    ) -> Tuple[float, float, float, float]:
        try:
            area = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(area) != 4 or any(
            isinstance(item, bool)
            or not isinstance(item, Real)
            or not math.isfinite(float(item))
            for item in area
        ):
            raise SemanticGateClosed(label + " is malformed")
        result = tuple(float(item) for item in area)
        if result[0] >= result[2] or result[1] >= result[3]:
            raise SemanticGateClosed(label + " is empty")
        return result

    @classmethod
    def _campaign_swipe_areas(
        cls, value: Any, label: str
    ) -> Tuple[Tuple[float, float, float, float], ...]:
        if value is None:
            return ()
        try:
            areas = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(areas) > 128:
            raise SemanticGateClosed(label + " is too large")
        return tuple(cls._campaign_swipe_box(area, label) for area in areas)

    def begin_campaign_map_swipe_vector(
        self,
        vector: Any,
        *,
        box: Any,
        random_range: Any,
        padding: Any,
        duration: Any,
        whitelist_area: Any,
        blacklist_area: Any,
        name: Any,
        distance_check: Any,
    ) -> CampaignMapViewportSwipeIntent:
        """Authorize ALAS's complete map-swipe selection, but no raw input."""

        self._package_gate()
        context = self._require_campaign_context()
        if (
            not context.viewport_swipe_required
            or context.viewport_swipe_budget != 1
            or context.combat_admission is None
            or context.map_state is None
            or context.viewport_swipe_intent is not None
            or context.viewport_swipe_proof is not None
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed("campaign map viewport swipe is not authorized")
        if not isinstance(name, str):
            raise SemanticGateClosed("campaign map viewport swipe name is malformed")
        match = re.fullmatch(r"MAP_SWIPE_(-?[0-9]+)_(-?[0-9]+)", name)
        if match is None:
            raise SemanticGateClosed("campaign map viewport swipe name is not canonical")
        grid_vector = tuple(int(item) for item in match.groups())
        if (
            abs(grid_vector[0]) > 4
            or abs(grid_vector[1]) > 3
            or grid_vector == (0, 0)
        ):
            raise SemanticGateClosed("campaign map viewport grid vector is outside ALAS limits")
        pixel_vector = self._campaign_swipe_pair(
            vector, "campaign map viewport pixel vector"
        )
        if not 10.0 <= math.hypot(*pixel_vector) <= 1200.0:
            raise SemanticGateClosed("campaign map viewport pixel vector is outside limits")
        for grid, pixel in zip(grid_vector, pixel_vector):
            # map_swipe() adds ALAS's fractional center correction before
            # `_map_swipe()` rounds the semantic name.  A rounded zero axis may
            # therefore retain less than half a calibrated grid of pixels.
            if (grid == 0 and abs(pixel) > 120.0) or (
                grid != 0 and grid * pixel >= 0.0
            ):
                raise SemanticGateClosed(
                    "campaign map viewport pixel vector disagrees with ALAS"
                )
        exact_box = self._campaign_swipe_box(box, "campaign map viewport box")
        if exact_box != (123.0, 159.0, 1175.0, 628.0):
            raise SemanticGateClosed("campaign map viewport box changed")
        try:
            exact_random_values = tuple(random_range)
        except TypeError as exc:
            raise SemanticGateClosed(
                "campaign map viewport random range is malformed"
            ) from exc
        if len(exact_random_values) != 4 or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in exact_random_values
        ):
            raise SemanticGateClosed(
                "campaign map viewport random range is malformed"
            )
        exact_random = tuple(float(item) for item in exact_random_values)
        if exact_random != (0.0, 0.0, 0.0, 0.0):
            raise SemanticGateClosed("campaign map viewport random range changed")
        if isinstance(padding, bool) or not isinstance(padding, int) or padding != 15:
            raise SemanticGateClosed("campaign map viewport padding changed")
        duration_range = self._campaign_swipe_pair(
            duration, "campaign map viewport duration"
        )
        if duration_range != (0.1, 0.2):
            raise SemanticGateClosed("campaign map viewport duration changed")
        if distance_check is not True:
            raise SemanticGateClosed("campaign map viewport distance check is disabled")
        intent = CampaignMapViewportSwipeIntent(
            name=name,
            grid_vector=grid_vector,
            pixel_vector=pixel_vector,
            box=tuple(int(item) for item in exact_box),
            random_range=tuple(int(item) for item in exact_random),
            padding=padding,
            duration_range=duration_range,
            whitelist_areas=self._campaign_swipe_areas(
                whitelist_area, "campaign map viewport whitelist"
            ),
            blacklist_areas=self._campaign_swipe_areas(
                blacklist_area, "campaign map viewport blacklist"
            ),
            distance_check=True,
        )
        context.viewport_swipe_intent = intent
        return intent

    def end_campaign_map_swipe_vector(
        self, intent: CampaignMapViewportSwipeIntent
    ) -> None:
        context = self._require_campaign_context()
        if context.viewport_swipe_intent is not intent:
            raise SemanticGateClosed("campaign map viewport swipe token changed")
        context.viewport_swipe_intent = None

    @staticmethod
    def _campaign_point_in_area(
        point: Tuple[int, int], area: Tuple[float, float, float, float]
    ) -> bool:
        return area[0] <= point[0] <= area[2] and area[1] <= point[1] <= area[3]

    @staticmethod
    def _campaign_swipe_endpoint_area(
        intent: CampaignMapViewportSwipeIntent,
    ) -> Tuple[float, float, float, float]:
        """Reproduce ALAS's padded end-point domain before random selection."""

        half = tuple(int(round(value / 2.0)) for value in intent.pixel_vector)
        left, top, right, bottom = intent.box
        pad_x = abs(half[0]) + intent.padding
        pad_y = abs(half[1]) + intent.padding
        return (
            left + pad_x + half[0],
            top + pad_y + half[1],
            right - pad_x + half[0],
            bottom - pad_y + half[1],
        )

    def swipe(
        self,
        p1: Any,
        p2: Any,
        *,
        duration: Any,
        name: Any,
        distance_check: Any,
    ) -> CampaignMapViewportSwipeProof:
        """Replace only the final dispatch of one armed ALAS map swipe."""

        self._package_gate()
        context = self._require_campaign_context()
        intent = context.viewport_swipe_intent
        if intent is None:
            self.reject_raw_input("swipe")
        assert intent is not None
        if name != intent.name or distance_check is not True:
            raise SemanticGateClosed("campaign map viewport final input changed")
        start_pair = self._campaign_swipe_pair(p1, "campaign map viewport start")
        end_pair = self._campaign_swipe_pair(p2, "campaign map viewport end")
        if any(not float(item).is_integer() for item in (*start_pair, *end_pair)):
            raise SemanticGateClosed("campaign map viewport endpoints are not integral")
        start = tuple(int(item) for item in start_pair)
        end = tuple(int(item) for item in end_pair)
        left, top, right, bottom = intent.box
        if any(
            not (left <= point[0] <= right and top <= point[1] <= bottom)
            for point in (start, end)
        ):
            raise SemanticGateClosed("campaign map viewport endpoint left its box")
        expected_delta = tuple(int(round(value)) for value in intent.pixel_vector)
        if (end[0] - start[0], end[1] - start[1]) != expected_delta:
            raise SemanticGateClosed("campaign map viewport selected vector changed")
        # ``random_rectangle_vector_opted`` treats whitelist areas as preferred
        # candidates, not as a mandatory final constraint: if no clipped area
        # produces a blacklist-safe point it deliberately falls back to the
        # padded box.  Validate that exact ALAS fallback domain here, then keep
        # the original segment-wise blacklist check below.
        endpoint_area = self._campaign_swipe_endpoint_area(intent)
        if (
            endpoint_area[0] > endpoint_area[2]
            or endpoint_area[1] > endpoint_area[3]
            or not self._campaign_point_in_area(end, endpoint_area)
        ):
            raise SemanticGateClosed(
                "campaign map viewport endpoint left ALAS selection domain"
            )
        segment_count = int(math.hypot(*expected_delta) // 70) + 1
        for index in range(segment_count + 1):
            point = (
                int(round(end[0] - expected_delta[0] * index / segment_count)),
                int(round(end[1] - expected_delta[1] * index / segment_count)),
            )
            if any(
                self._campaign_point_in_area(point, area)
                for area in intent.blacklist_areas
            ):
                raise SemanticGateClosed("campaign map viewport path entered its blacklist")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or not 0.20 <= float(duration) <= 0.60
        ):
            raise SemanticGateClosed("campaign map viewport final duration changed")
        if (
            context.viewport_swipe_budget != 1
            or context.map_state is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
            or context.combat_admission is None
        ):
            raise SemanticGateClosed("campaign map viewport lease is incomplete")

        context.viewport_swipe_budget -= 1
        proof = self.oracle.campaign_map_viewport_swipe(
            context.map_state,
            context.combat_admission.target_node,
            intent,
            start=start,
            end=end,
            duration_ms=int(round(float(duration) * 1000.0)),
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        context.viewport_swipe_proof = proof
        context.viewport_swipe_required = False
        context.map_state = proof.post_state
        context.combat_admission = replace(
            context.combat_admission,
            input_generation=proof.post_generation,
            point=proof.target_after_point,
            bounds=proof.target_after_bounds,
        )
        return proof

    def campaign_map_viewport_swipe_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.viewport_swipe_proof is not None

    def campaign_map_viewport_swipe_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        context = self._require_campaign_context()
        proof = context.viewport_swipe_proof
        if proof is None:
            raise SemanticGateClosed("campaign map viewport swipe is not proven")
        return proof

    def campaign_camera_state(self) -> CampaignMapState:
        """Return one fresh map observation to ALAS's original Camera.update."""

        self._package_gate()
        context = self._require_campaign_context()
        if (
            context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
            or context.map_state is None
        ):
            raise SemanticGateClosed("campaign camera map topology is incomplete")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        if state.signature != context.map_state.signature:
            raise SemanticGateClosed(
                "campaign camera observation changed logical map state"
            )
        admission = context.combat_admission
        if admission is not None and state.signature != admission.map_signature:
            raise SemanticGateClosed(
                "campaign camera observation changed admitted map state"
            )
        context.map_state = state
        return state

    def campaign_camera_target_node(self) -> Optional[str]:
        context = self._require_campaign_context()
        admission = context.combat_admission
        return None if admission is None else admission.target_node

    def recheck_campaign_combat_target_after_camera_view(
        self, state: CampaignMapState
    ) -> CampaignMapTargetRecheckProof:
        """Bind ALAS's fresh typed View to the exact eventual target cell."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.target_recheck_proof is not None:
            if (
                context.map_state is not state
                or state.generation
                != context.target_recheck_proof.camera_state_generation
            ):
                raise SemanticGateClosed(
                    "campaign target recheck token changed"
                )
            return context.target_recheck_proof
        admission = context.combat_admission
        viewport = context.viewport_swipe_proof
        if (
            admission is None
            or viewport is None
            or context.map_state is not state
            or context.viewport_swipe_required
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed(
                "campaign target recheck requires a proven camera view"
            )
        if (
            state.signature != admission.map_signature
            or state.generation < viewport.post_generation
            or viewport.target_node != admission.target_node
            or viewport.target_path != admission.cell_path
        ):
            raise SemanticGateClosed(
                "campaign target recheck changed viewport identity"
            )
        target = self.oracle.campaign_map_cell_input(
            state, admission.target_node
        )
        if target.path != admission.cell_path:
            raise SemanticGateClosed("campaign target recheck changed cell path")
        assert target.point is not None and target.bounds is not None
        context.combat_admission = replace(
            admission,
            input_generation=max(admission.input_generation, state.generation),
            point=target.point,
            bounds=target.bounds,
        )
        proof = CampaignMapTargetRecheckProof(
            target_node=admission.target_node,
            viewport_post_generation=viewport.post_generation,
            camera_state_generation=state.generation,
            recheck_generation=state.generation,
            path=target.path,
            point=target.point,
            bounds=target.bounds,
        )
        context.target_recheck_proof = proof
        return proof

    @staticmethod
    def _campaign_grid_location(button: Any) -> Optional[Tuple[int, int]]:
        """Read ALAS `_goto()`'s explicit global-location annotation only."""

        location = getattr(button, "__str__", None)
        if callable(location) or not isinstance(location, (tuple, list)):
            return None
        if len(location) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in location
        ):
            return None
        if not (
            hasattr(button, "corner")
            and hasattr(button, "button")
            and hasattr(button, "location")
        ):
            return None
        return tuple(location)

    @staticmethod
    def _campaign_node(location: Tuple[int, int]) -> str:
        column, row = location
        if not (0 <= column < 26 and 0 <= row < 99):
            raise SemanticGateClosed("campaign combat grid location is outside bounds")
        return chr(ord("A") + column) + str(row + 1)

    def click_campaign_combat_grid(self, button: Any) -> ActionReceipt:
        """Consume the one budget only at ALAS's original `device.click(grid)`."""

        self._package_gate()
        context = self._require_campaign_context()
        admission = context.combat_admission
        location = self._campaign_grid_location(button)
        if admission is None or location is None or context.map_state is None:
            raise SemanticGateClosed("campaign combat grid input is not authorized")
        if context.viewport_swipe_required:
            raise SemanticGateClosed(
                "campaign combat grid input requires proven viewport movement"
            )
        if (
            context.viewport_swipe_proof is not None
            and context.target_recheck_proof is None
        ):
            raise SemanticGateClosed(
                "campaign combat grid input requires post-camera target recheck"
            )
        node = self._campaign_node(location)
        if node != admission.target_node:
            raise SemanticGateClosed("campaign combat grid target changed")
        if context.combat_budget != 1 or context.combat_receipt is not None:
            raise SemanticGateClosed(
                "campaign combat grid requires one remaining budget unit"
            )
        receipt = self.oracle.click_campaign_map_cell(context.map_state, node)
        # The ADB tap has happened.  Consume and record the lease before any
        # subsequent assertion so an anomalous receipt can never be replayed.
        context.combat_budget -= 1
        context.combat_admission = replace(
            admission, input_generation=receipt.generation
        )
        context.combat_receipt = receipt
        if (
            receipt.path != admission.cell_path
            or receipt.point != admission.point
            or receipt.bounds != admission.bounds
            or receipt.generation < admission.input_generation
        ):
            raise SemanticGateClosed("campaign combat input receipt changed")
        return receipt

    def campaign_combat_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.combat_receipt is not None

    def confirm_campaign_combat(
        self,
        battle_count_after: int,
    ) -> AlasCampaignCombatProof:
        """Validate ALAS's completed combat against a stable semantic map."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.combat_proof is not None:
            return context.combat_proof
        if (
            context.combat_admission is None
            or context.combat_receipt is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed("campaign combat input is not committed")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        proof = prove_alas_campaign_combat_transition(
            context.combat_admission,
            state,
            battle_count_after=battle_count_after,
            input_path=context.combat_receipt.path,
        )
        context.map_state = state
        context.combat_proof = proof
        return proof

    def research_series(self) -> List[int]:
        return [project.series for project in self.research_projects()]

    def research_statuses(self) -> List[str]:
        return [project.status.value for project in self.research_projects()]

    def research_finished_index(self) -> Optional[int]:
        finished = [
            project.slot - 1
            for project in self.research_projects()
            if project.status == ResearchProjectStatus.FINISHED
        ]
        if len(finished) > 1:
            raise SemanticGateClosed("multiple finished research projects are ambiguous")
        return finished[0] if finished else None

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        self._package_gate()
        return self.oracle.tactical_slots()

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        self._package_gate()
        return self.oracle.tactical_remaining_seconds()

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        self._package_gate()
        return self.oracle.tactical_candidate_ships()

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        self._package_gate()
        return self.oracle.tactical_skills()

    def tactical_select_suitable_ship(
        self, min_level: int, start_index: int
    ) -> bool:
        context = self._require_commission_context()
        if context.flow_kind != "tactical" or context.assign_budget <= 0:
            raise SemanticGateClosed("tactical assignment requires a positive budget")
        if min_level < 1 or start_index < 0:
            raise ValueError("tactical ship selection bounds are invalid")
        candidates = self.oracle.tactical_candidate_ships()
        selected = next(
            (
                candidate
                for candidate in candidates[start_index:]
                if candidate.level >= min_level
            ),
            None,
        )
        if selected is None:
            return False
        receipt = self.oracle.click_tactical_ship(selected.ship_id)
        self.oracle.wait_for(
            "tactical/dock/confirm",
            timeout_seconds=5.0,
            minimum_generation=receipt.generation,
        )
        confirm = self.oracle.click("tactical/dock/confirm")
        self.oracle.wait_for(
            "tactical/skill/confirm",
            timeout_seconds=8.0,
            minimum_generation=confirm.generation,
        )
        return True

    def tactical_select_first_trainable_skill(self) -> bool:
        context = self._require_commission_context()
        if context.flow_kind != "tactical" or context.assign_budget <= 0:
            raise SemanticGateClosed("tactical assignment requires a positive budget")
        skill = next(
            (skill for skill in self.oracle.tactical_skills() if not skill.max_level),
            None,
        )
        if skill is None:
            return False
        receipt = self.oracle.click_tactical_skill(skill.position)
        self.oracle.wait_for(
            "tactical/skill/confirm",
            timeout_seconds=5.0,
            minimum_generation=receipt.generation,
        )
        self.oracle.click("tactical/skill/confirm")
        return True

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        context = self._require_commission_context()
        if context.flow_kind != "tactical":
            raise SemanticGateClosed("tactical books require the tactical flow")
        return self.oracle.tactical_books()

    def tactical_select_book(self, position: int) -> ActionReceipt:
        context = self._require_commission_context()
        if context.flow_kind != "tactical" or context.assign_budget <= 0:
            raise SemanticGateClosed("tactical assignment requires a positive budget")
        before = self.oracle.tactical_books()
        matches = tuple(book for book in before if book.position == position)
        if len(matches) != 1 or matches[0].count <= 0:
            raise SemanticGateClosed("selected tactical book is unavailable")
        if matches[0].selected:
            image = matches[0].image
            assert image.bounds is not None
            return ActionReceipt(
                semantic_id="tactical/book/{0}".format(position),
                generation=self.oracle.read_state().generation,
                point=Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                ),
                bounds=image.bounds,
                path=image.path,
            )
        receipt = self.oracle.click_tactical_book(position)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                current = self.oracle.tactical_books()
            except SemanticGateClosed:
                time.sleep(0.1)
                continue
            if any(book.position == position and book.selected for book in current):
                return receipt
            time.sleep(0.1)
        raise SemanticGateClosed("tactical book selection was not observed")

    def tactical_book_selected(self, position: int) -> bool:
        return any(
            book.position == position and book.selected
            for book in self.tactical_books()
        )

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_rows()

    def commission_is_empty(self) -> bool:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_is_empty()

    def commission_scroll_state(self) -> CommissionScrollState:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_scroll_state()

    def commission_scroll_next(self) -> Optional[CommissionScrollProof]:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_scroll_next()

    def commission_scroll_to_top(self) -> Optional[CommissionScrollProof]:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_scroll_to_top()

    def commission_reward_pending(self) -> bool:
        """Detect a finished commission only from the typed reward summary."""

        context = self._require_commission_context()
        if context.flow_kind != "commission":
            raise SemanticGateClosed(
                "commission reward state used outside commission flow"
            )
        self._package_gate()
        if not self.oracle.exists("reward/commission/finish"):
            context.reward_detected_count = None
            return False
        if not self.oracle.enabled("reward/commission/finish"):
            raise SemanticGateClosed("commission reward finish input is blocked")
        count = self.oracle.reward_summary_count("commission", "finished")
        if count <= 0:
            raise SemanticGateClosed(
                "commission reward button contradicts the finished counter"
            )
        context.reward_detected_count = count
        return True

    def commission_reward_allowed(self) -> bool:
        context = self._require_commission_context()
        return (
            context.flow_kind == "commission"
            and context.reward_budget > 0
            and context.reward_detected_count == 1
            and context.reward_claim_receipt is None
        )

    def commission_reward_claimed(self) -> bool:
        context = self._require_commission_context()
        return context.reward_claim_receipt is not None

    def confirm_commission_reward(self) -> CommissionRewardProof:
        """Prove one finish input drained the exact finished counter to zero."""

        context = self._require_commission_context()
        if context.flow_kind != "commission":
            raise SemanticGateClosed(
                "commission reward proof used outside commission flow"
            )
        if context.reward_proof is not None:
            return context.reward_proof
        if context.reward_claim_receipt is None:
            raise SemanticGateClosed("commission reward input was not recorded")
        if context.reward_detected_count != 1:
            raise SemanticGateClosed(
                "controlled commission reward requires exactly one finished row"
            )
        if not context.reward_close_receipts:
            raise SemanticGateClosed(
                "commission reward popup chain has no reviewed close input"
            )
        self._package_gate()
        if not self.oracle.enabled("commission/page/back"):
            raise SemanticGateClosed(
                "commission page is absent after reward popup closure"
            )
        back = self.oracle.click("commission/page/back")
        context.passive_transition_until = time.monotonic() + 12.0
        self.oracle.wait_for(
            "reward/page/back",
            timeout_seconds=12.0,
            minimum_generation=back.generation,
        )
        after = self.oracle.reward_summary_count("commission", "finished")
        if after != 0:
            raise SemanticGateClosed(
                "commission reward finished counter did not reach zero"
            )
        generation = self.oracle.read_state().generation
        context.reward_proof = CommissionRewardProof(
            before_finished_count=context.reward_detected_count,
            after_finished_count=after,
            claim_generation=context.reward_claim_receipt.generation,
            close_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.reward_close_receipts
            ),
            generation=generation,
        )
        return context.reward_proof

    def commission_start_allowed(self) -> bool:
        return self._require_commission_context().start_budget > 0

    def commission_detail_state(self) -> CommissionDetailState:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_detail_state()

    def commission_start_confirmed(self) -> bool:
        context = self._require_commission_context()
        if context.start_receipt is None or context.selected_signature is None:
            return False
        if context.start_proof is not None:
            return True
        try:
            context.start_proof = self.oracle.commission_start_transition(
                context.selected_signature
            )
        except SemanticGateClosed:
            if time.monotonic() - context.start_clicked_at <= 15.0:
                return False
            raise
        return True

    def commission_start_proof(self) -> CommissionStartProof:
        """Return the cached typed proof after the exact row entered running state."""

        context = self._require_commission_context()
        if not self.commission_start_confirmed() or context.start_proof is None:
            raise SemanticGateClosed("commission start transition is not proven")
        return context.start_proof

    def close_started_commission_detail(self) -> ActionReceipt:
        """Leave the proven running detail without touching its cancel action."""

        context = self._require_commission_context()
        if context.start_proof is None:
            raise SemanticGateClosed(
                "commission running detail cannot close before start proof"
            )
        self._package_gate()
        if not self.oracle.enabled("commission/detail/back"):
            raise SemanticGateClosed("proven commission detail back is absent")
        receipt = self.oracle.click("commission/detail/back")
        context.passive_transition_until = time.monotonic() + 12.0
        self.oracle.wait_for(
            "reward/page/back",
            timeout_seconds=12.0,
            minimum_generation=receipt.generation,
        )
        return receipt

    def cancel_tactical_continue_if_present(self) -> bool:
        self._package_gate()
        if self._commission_context is None:
            raise SemanticGateClosed("tactical popup used outside ALAS tactical flow")
        prompt = self.oracle.tactical_continue_prompt_text()
        if prompt is None:
            return False
        if (
            self._commission_context.flow_kind != "tactical"
            or not self._commission_context.rewards_allowed
        ):
            raise SemanticGateClosed(
                "tactical reward requires the separate explicit opt-in"
            )
        if prompt in self._commission_context.cancelled_tactical_prompts:
            return False
        self.oracle.click("tactical/continue/cancel")
        self._commission_context.cancelled_tactical_prompts.add(prompt)
        return True

    def click(self, button: Any) -> ActionReceipt:
        if self._campaign_grid_location(button) is not None:
            return self.click_campaign_combat_grid(button)
        name = self._button_name(button)
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        semantic_id = self._mappings.get(name)
        if self._login_context is not None and name == "POPUP_CONFIRM":
            semantic_id = self._login_popup_target()
            if semantic_id is None:
                raise SemanticGateClosed("login popup identity is not proven")
        navbar_match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        commission_row_match = COMMISSION_ROW_PATTERN.fullmatch(name)
        build_side_navbar_match = BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
        build_pool_navbar_match = BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        campaign_fleet_bar_match = CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name)
        if name == "BACK_ARROW" and all(
            context is None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: BACK_ARROW"
            )
        if (
            semantic_id is None
            and name not in MISSION_CLICK_RESOURCES
            and name not in MAIL_CLICK_RESOURCES
            and name not in CAMPAIGN_CLICK_RESOURCES
            and not (
                self._research_context is not None
                and name in RESEARCH_CLICK_RESOURCES
            )
            and not (
                self._dorm_context is not None
                and name in DORM_VIRTUAL_RESOURCES
            )
            and not (
                self._build_context is not None
                and name in BUILD_VIRTUAL_RESOURCES
            )
            and not (
                self._commission_context is not None
                and self._commission_context.flow_kind == "tactical"
                and name in TACTICAL_VIRTUAL_RESOURCES
            )
            and not (
                self._commission_context is not None
                and name in COMMISSION_CLICK_RESOURCES
            )
            and campaign_stage_code is None
            and CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name) is None
            and navbar_match is None
            and commission_row_match is None
            and not (
                self._build_context is not None
                and (
                    build_side_navbar_match is not None
                    or build_pool_navbar_match is not None
                )
            )
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        self._package_gate()
        if campaign_stage_code is not None:
            context = self._require_campaign_context()
            if (
                not isinstance(campaign_stage_code, str)
                or campaign_stage_code != context.stage_code
                or name != campaign_stage_code
            ):
                raise SemanticGateClosed("campaign stage identity changed")
            if context.entry_budget <= 0 or context.entry_receipt is not None:
                raise SemanticGateClosed(
                    "campaign stage entry requires one remaining budget unit"
                )
            context.oil_before_sortie = self.oracle.campaign_oil()
            receipt = self.oracle.click_campaign_stage(campaign_stage_code)
            context.entry_budget -= 1
            context.entry_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._campaign_context is not None and name == "FLEET_PREPARATION":
            context = self._require_campaign_context()
            if (
                not context.sortie_authorized
                or context.sortie_budget != 1
                or context.sortie_receipt is not None
                or context.prepared_fleet_state is None
            ):
                raise SemanticGateClosed(
                    "campaign sortie requires one authorized budget unit"
                )
            receipt = self.oracle.click_campaign_sortie(context.stage_code)
            if receipt.generation < context.prepared_fleet_state.generation:
                raise SemanticGateClosed(
                    "campaign sortie target predates prepared fleet state"
                )
            context.sortie_budget -= 1
            context.sortie_receipt = receipt
            context.passive_transition_until = time.monotonic() + 30.0
            return receipt
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_FLEET_ROW_RESOURCES
        ):
            context = self._require_campaign_context()
            row_key, action = CAMPAIGN_FLEET_ROW_RESOURCES[name]
            if action == "advice":
                raise SemanticGateClosed(
                    "campaign fleet advice is observation-only"
                )
            if action == "select":
                if (
                    context.initial_fleet_state is None
                    or context.requested_fleets is None
                ):
                    raise SemanticGateClosed(
                        "campaign fleet selection was not preflight-authorized"
                    )
                dropdown = self.oracle.campaign_fleet_dropdown_state()
                if dropdown is None:
                    row = self._campaign_fleet_row(row_key)
                    receipt = self.oracle.click_campaign_fleet_row(
                        row_key, "select"
                    )
                    context.fleet_dropdown_row = row_key
                    context.fleet_dropdown_previous_index = row.selected_fleet
                else:
                    close_index = context.fleet_dropdown_previous_index
                    if close_index not in dropdown.active_indices:
                        close_index = (
                            dropdown.active_indices[0]
                            if dropdown.active_indices
                            else None
                        )
                    if (
                        context.fleet_dropdown_row != row_key
                        or close_index not in range(1, 7)
                    ):
                        raise SemanticGateClosed(
                            "campaign fleet dropdown close identity changed"
                        )
                    receipt = self.oracle.click_campaign_fleet_option(
                        close_index
                    )
                    context.fleet_dropdown_row = None
                    context.fleet_dropdown_previous_index = None
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if (
                context.initial_fleet_state is None
                or context.requested_fleets is None
            ):
                raise SemanticGateClosed(
                    "campaign fleet clear was not preflight-authorized"
                )
            row = self._campaign_fleet_row(row_key)
            if not row.in_use:
                observed = self.oracle.campaign_fleet_selection_state(
                    context.stage_code
                )
                matches = tuple(
                    candidate
                    for candidate in observed.rows
                    if candidate.row_key == row_key
                )
                if len(matches) != 1 or matches[0].in_use:
                    raise SemanticGateClosed(
                        "campaign fleet empty-row identity changed"
                    )
                row = matches[0]
                clear_button = row.clear_button
                if clear_button.point is None or clear_button.bounds is None:
                    raise SemanticGateClosed(
                        "campaign fleet empty-row clear identity is incomplete"
                    )
                # ALAS sometimes emits an idempotent clear while reconciling
                # partially prepared rows. Preserve that state-machine edge as
                # an observation-only success: no ADB input and no mutation
                # budget are consumed.
                return ActionReceipt(
                    semantic_id={
                        "fleet1": "campaign/fleet-preparation/fleet/1/clear",
                        "fleet2": "campaign/fleet-preparation/fleet/2/clear",
                        "submarine": (
                            "campaign/fleet-preparation/submarine/1/clear"
                        ),
                    }[row_key],
                    generation=observed.generation,
                    point=clear_button.point,
                    bounds=clear_button.bounds,
                    path=clear_button.path,
                )
            if (
                context.fleet_mutation_budget <= 0
                or len(context.fleet_mutation_receipts)
                >= context.required_fleet_mutations
            ):
                raise SemanticGateClosed(
                    "campaign fleet clear requires a remaining mutation budget"
                )
            receipt = self.oracle.click_campaign_fleet_row(row_key, "clear")
            context.fleet_mutation_budget -= 1
            context.fleet_mutation_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if (
            self._campaign_context is not None
            and campaign_fleet_bar_match is not None
        ):
            context = self._require_campaign_context()
            row_key = {
                "FLEET_1": "fleet1",
                "FLEET_2": "fleet2",
                "SUBMARINE": "submarine",
            }[campaign_fleet_bar_match.group(1)]
            index = int(campaign_fleet_bar_match.group(2))
            dropdown = self.oracle.campaign_fleet_dropdown_state()
            if (
                dropdown is None
                or context.fleet_dropdown_row != row_key
                or index in dropdown.active_indices
            ):
                raise SemanticGateClosed(
                    "campaign fleet option is absent or already selected"
                )
            if (
                context.fleet_mutation_budget <= 0
                or len(context.fleet_mutation_receipts)
                >= context.required_fleet_mutations
            ):
                raise SemanticGateClosed(
                    "campaign fleet selection requires a remaining mutation budget"
                )
            receipt = self.oracle.click_campaign_fleet_option(index)
            context.fleet_mutation_budget -= 1
            context.fleet_mutation_receipts.append(receipt)
            context.fleet_dropdown_row = None
            context.fleet_dropdown_previous_index = None
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_AUTO_SEARCH_RESOURCES
        ):
            context = self._require_campaign_context()
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle requires proven stage entry"
                )
            if context.map_preparation_receipt is not None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle is only valid before map preparation"
                )
            if context.auto_search_toggle_receipt is not None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle transition is single-use"
                )
            if self._campaign_preparation_kind() != "map":
                raise SemanticGateClosed(
                    "campaign auto-search toggle requires the map-preparation layer"
                )
            selected = self.oracle.toggle_selected(
                "campaign/map-preparation/auto-search"
            )
            if selected != (name in CAMPAIGN_AUTO_SEARCH_ON_RESOURCES):
                raise SemanticGateClosed(
                    "campaign auto-search resource state changed before input"
                )
            receipt = self.oracle.click_toggle(
                "campaign/map-preparation/auto-search"
            )
            context.auto_search_toggle_receipt = receipt
            context.passive_transition_until = time.monotonic() + 5.0
            return receipt
        if self._campaign_context is not None and name == "MAP_PREPARATION":
            context = self._require_campaign_context()
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign map preparation requires proven stage entry"
                )
            if context.map_preparation_receipt is not None:
                raise SemanticGateClosed(
                    "campaign map-preparation transition is single-use"
                )
            preparation_kind = self._campaign_preparation_kind()
            if preparation_kind not in (None, "map"):
                raise SemanticGateClosed(
                    "campaign map preparation is not the active layer"
                )
            # `appear(MAP_PREPARATION)` and this input call are separate ALAS
            # operations.  During the bounded post-entry transition the
            # adapter may get one incoherent read here and report no kind.
            # The oracle action below performs a fresh, exact page/stage/
            # raycast proof immediately before input, so let that final proof
            # decide rather than failing on the advisory pre-read.
            receipt = self.oracle.click_campaign_map_preparation(
                context.stage_code
            )
            context.map_preparation_receipt = receipt
            context.passive_transition_until = time.monotonic() + 60.0
            return receipt
        if (
            self._campaign_context is not None
            and name == "MAP_PREPARATION_CANCEL"
        ):
            context = self._require_campaign_context()
            if context.entry_receipt is None or context.cancel_receipt is not None:
                raise SemanticGateClosed(
                    "campaign preparation cancel is not currently allowed"
                )
            kind = self._campaign_preparation_kind()
            if kind == "fleet":
                if context.map_preparation_receipt is None:
                    raise SemanticGateClosed(
                        "campaign fleet cancel requires proven map transition"
                    )
                receipt = self.oracle.cancel_campaign_fleet_preparation(
                    context.stage_code
                )
            elif kind == "map":
                receipt = self.oracle.cancel_campaign_map_preparation(
                    context.stage_code
                )
            else:
                raise SemanticGateClosed(
                    "campaign preparation cancel layer is absent"
                )
            context.preparation_kind = kind
            context.cancel_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._campaign_context is not None and name == "BACK_ARROW":
            receipt = self.oracle.click("event-list/page/back")
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 20.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and semantic_id == "campaign-menu/normal"
        ):
            context = self._require_campaign_context()
            if (
                context.menu_entry_receipt is not None
                and time.monotonic() <= context.passive_transition_until
            ):
                return context.menu_entry_receipt
            receipt = self.oracle.click(semantic_id)
            context.menu_entry_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._build_context is not None and build_side_navbar_match is not None:
            index = int(build_side_navbar_match.group(1))
            if index not in (0, 1):
                raise SemanticGateClosed(
                    "construction side navigation input is outside build/queue"
                )
            return self.oracle.click_toggle(BUILD_SIDE_NAVBAR_TARGETS[index])
        if self._build_context is not None and build_pool_navbar_match is not None:
            index = int(build_pool_navbar_match.group(1))
            target = BUILD_POOL_NAVBAR_TARGETS.get(index)
            if target is None:
                raise SemanticGateClosed("event construction pool is not qualified")
            return self.oracle.click_toggle(target)
        if (
            self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
            and name in TACTICAL_VIRTUAL_RESOURCES
        ):
            context = self._commission_context
            if name == "ADD_NEW_STUDENT":
                if context.assign_budget <= 0:
                    raise SemanticGateClosed(
                        "tactical assignment requires a positive budget"
                    )
                occupied = {slot.slot for slot in self.oracle.tactical_slots()}
                empty = next((slot for slot in range(1, 5) if slot not in occupied), None)
                if empty is None:
                    raise SemanticGateClosed("tactical class has no empty slot")
                return self.oracle.click_tactical_empty_slot(empty)
            if name == "BACK_ARROW":
                targets = tuple(
                    target
                    for target in ("tactical/dock/back", "tactical/page/back")
                    if self.oracle.enabled(target)
                )
                if (
                    not targets
                    and context.tactical_back_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.tactical_back_receipt
                if len(targets) != 1:
                    raise SemanticGateClosed("tactical back target is ambiguous")
                receipt = self._record_mission_transition(
                    self.oracle.click(targets[0])
                )
                if receipt.semantic_id == "tactical/page/back":
                    context.tactical_back_receipt = receipt
                return receipt
            if name == "TACTICAL_CLASS_START":
                if context.assign_budget <= 0:
                    raise SemanticGateClosed(
                        "tactical course start requires a positive budget"
                    )
                books = self.oracle.tactical_books()
                selected = tuple(book for book in books if book.selected)
                if len(selected) != 1 or selected[0].count <= 0:
                    raise SemanticGateClosed(
                        "tactical course start requires one available selected book"
                    )
                receipt = self.oracle.click("tactical/book/start")
                return receipt
            if name == "TACTICAL_CLASS_CANCEL":
                return self.oracle.click("tactical/book/cancel")
            if name == "POPUP_CONFIRM":
                if context.assign_budget <= 0:
                    raise SemanticGateClosed(
                        "tactical course confirmation requires a positive budget"
                    )
                receipt = self.oracle.click("tactical/course/confirm")
                context.assign_budget -= 1
                return receipt
            raise AlasSemanticUnmapped(
                "tactical resource requires a typed workflow helper: {0}".format(name)
            )
        if self._research_context is not None and name in RESEARCH_CLICK_RESOURCES:
            context = self._research_context
            if name == "RESEARCH_GOTO_QUEUE":
                target = "research/queue/enter"
                cached = context.navigation_receipts.get(target)
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                receipt = self._record_mission_transition(self.oracle.click(target))
                context.navigation_receipts[target] = receipt
                return receipt
            if name == "RESEARCH_DETAIL_QUIT":
                return self.oracle.click("research/detail/root")
            if name == "RESEARCH_START":
                detail = self.oracle.research_detail_state()
                if (
                    context.start_budget <= 0
                    or context.start_receipt is not None
                    or not detail.can_start
                ):
                    raise SemanticGateClosed(
                        "research start requires sufficient resources and a positive budget"
                    )
                if context.selected_code is not None and detail.code != context.selected_code:
                    raise SemanticGateClosed("selected research project identity changed")
                receipt = self.oracle.click("research/detail/start")
                context.start_receipt = receipt
                context.start_confirm_receipt = None
                context.pending_resource_id = detail.resource_id
                context.pending_resource_required = detail.resource_required
                return receipt
            if name == "POPUP_CONFIRM":
                if context.queue_add_receipt is not None:
                    if context.queue_confirm_receipt is not None:
                        return context.queue_confirm_receipt
                    if (
                        context.queue_add_uses_start_budget
                        and context.start_budget <= 0
                    ):
                        raise SemanticGateClosed(
                            "research queue confirmation requires a positive budget"
                        )
                    receipt = self.oracle.click("research/queue/confirm")
                    if context.queue_add_uses_start_budget:
                        context.start_budget -= 1
                    context.queue_confirm_receipt = receipt
                    context.last_queue_state = None
                    context.last_projects = None
                    return receipt
                expected = (
                    context.pending_resource_id,
                    context.pending_resource_required,
                )
                if (
                    context.start_receipt is None
                    or context.start_confirm_receipt is not None
                    or context.start_budget <= 0
                    or self.oracle.research_start_prompt_cost() != expected
                ):
                    raise SemanticGateClosed(
                        "research start confirmation does not match the budgeted project"
                    )
                receipt = self.oracle.click("research/start/confirm")
                context.start_budget -= 1
                context.start_confirm_receipt = receipt
                context.last_queue_state = None
                context.last_projects = None
                return receipt
            if name == "RESEARCH_QUEUE_ADD":
                if (
                    context.queue_add_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.queue_add_receipt
                confirmed_start = context.start_confirm_receipt is not None
                existing_running = (
                    context.selected_status == ResearchProjectStatus.RUNNING
                    and context.start_budget > 0
                    and self.research_detail_is_running()
                    and self.research_detail_can_queue()
                )
                if not confirmed_start and not existing_running:
                    raise SemanticGateClosed(
                        "research queue add requires a confirmed start or one budgeted running project"
                    )
                receipt = self.oracle.click_research_queue_add()
                context.queue_add_receipt = receipt
                context.queue_confirm_receipt = None
                context.queue_add_uses_start_budget = existing_running
                context.last_queue_state = None
                context.last_projects = None
                return self._record_mission_transition(receipt)
            if name == "RESEARCH_STOP":
                raise SemanticGateClosed("semantic research cancellation is not enabled")
            if name == "QUEUE_CLAIM_REWARD":
                queue = self.oracle.research_queue_state()
                if not queue.reward_claimable or context.reward_budget <= 0:
                    raise SemanticGateClosed("research reward requires a positive budget")
                receipt = self.oracle.click("research/queue/claim")
                context.reward_budget -= 1
                context.reward_receipts.append(receipt)
                context.last_queue_state = None
                context.last_projects = None
                return receipt
            if name in (
                "GET_ITEMS_1",
                "GET_ITEMS_2",
                "GET_ITEMS_3",
                "GET_ITEMS_RESEARCH_SAVE",
            ):
                if not context.reward_receipts:
                    raise SemanticGateClosed(
                        "research reward popup requires a budgeted queue claim"
                    )
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("reviewed research reward popup is absent")
                receipt = self.oracle.click(target)
                context.popup_close_receipts.append(receipt)
                return receipt
            if name == "BACK_ARROW":
                cached = context.navigation_receipts.get("research/page/back")
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                receipt = self._record_mission_transition(
                    self.oracle.click("research/page/back")
                )
                context.navigation_receipts["research/page/back"] = receipt
                return receipt

        if self._dorm_context is not None and name in DORM_VIRTUAL_RESOURCES:
            context = self._dorm_context
            if name == "DORM_QUICK_COLLECT":
                if context.collect_budget <= 0:
                    raise SemanticGateClosed("dorm collect requires a positive budget")
                receipt = self.oracle.click("dorm/collect")
                context.collect_budget -= 1
                return receipt
            if name == "DORM_FEED_ENTER":
                if (
                    context.feed_entry_receipt is not None
                    and not context.feed_panel_observed
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.feed_entry_receipt
                if self.oracle.enabled("dorm/feed/close"):
                    receipt = self._record_mission_transition(
                        self.oracle.click("dorm/feed/close")
                    )
                    context.feed_panel_observed = False
                    return receipt
                receipt = self._record_mission_transition(
                    self.oracle.click("dorm/feed")
                )
                context.feed_entry_receipt = receipt
                context.feed_panel_observed = False
                # CourtYardUI can take more than twenty seconds to materialize
                # either BackYardFeedUI or CourtYardEmptyFoodUI on a contended
                # emulator.  Suppress only duplicate entry clicks while ALAS
                # keeps polling; either exact destination still ends the wait.
                context.passive_transition_until = time.monotonic() + 45.0
                return receipt
            if name == "DORM_FEED_CANCEL":
                if self.oracle.dorm_empty_food_cancel_available():
                    receipt = self.oracle.click("dorm/empty-food/cancel")
                    context.feed_entry_receipt = None
                    context.feed_panel_observed = False
                    return receipt
                receipt = self._record_mission_transition(
                    self.oracle.click("dorm/feed/close")
                )
                context.feed_panel_observed = False
                return receipt
            if name == "POPUP_CANCEL":
                return self.oracle.click("dorm/feed/shop/cancel")
            raise AlasSemanticUnmapped(
                "ALAS dorm resource is observation-only: {0}".format(name)
            )

        if self._build_context is not None and name in BUILD_VIRTUAL_RESOURCES:
            context = self._build_context
            if name == "BUILD_SUBMIT_ORDERS":
                receipt = self.oracle.click("build/page/start")
                context.prep_opened = True
                return receipt
            if name == "BUILD_MINUS":
                return self.oracle.click("build/prep/minus")
            if name == "BUILD_PLUS":
                return self.oracle.click("build/prep/add")
            if name in (
                "BUILD_QUEUE_EMPTY",
                "BUILD_FINISH_ORDERS",
                "BUILD_SUBMIT_WW_ORDERS",
                "BUILD_WW_CHECK",
                "SHOP_MEDAL_CHECK",
            ):
                raise SemanticGateClosed(
                    "construction observation resource is not an admitted input"
                )
            if name == "POPUP_CANCEL":
                target = (
                    "build/warning/cancel"
                    if self.oracle.enabled("build/warning/cancel")
                    else "build/prep/cancel"
                )
                return self.oracle.click(target)
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_PREP"):
                if (
                    not self.oracle.enabled("build/warning/confirm")
                    or context.warning_confirmed
                ):
                    raise SemanticGateClosed(
                        "construction preparation alias requires the exact warning"
                    )
                context.warning_confirmed = True
                return self.oracle.click("build/warning/confirm")
            if name == "POPUP_CONFIRM_GACHA_ORDER":
                if self.oracle.enabled("build/warning/confirm"):
                    raise SemanticGateClosed(
                        "construction order alias cannot confirm a warning"
                    )
                submit = self.oracle.build_submit_state()
                if (
                    context.submit_budget <= 0
                    or submit.count != 1
                    or submit.cubes_owned < submit.cubes_required
                    or context.coins_owned is None
                    or context.coins_owned < submit.coins_required
                    or context.submit_receipt is not None
                ):
                    raise SemanticGateClosed(
                        "construction submit requires one build, sufficient resources, and a positive budget"
                    )
                receipt = self.oracle.click("build/prep/confirm")
                context.submit_budget -= 1
                context.submit_receipt = receipt
                return receipt
        if semantic_id is None and name == "GOTO_MAIN":
            target = self._goto_main_target()
            if target is None:
                raise SemanticGateClosed("GOTO_MAIN has no reviewed page target")
            if (
                self._research_context is not None
                and target in ("research/page/back", "research-menu/page/back")
            ):
                context = self._research_context
                cached = context.navigation_receipts.get(target)
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                receipt = self._record_mission_transition(self.oracle.click(target))
                context.navigation_receipts[target] = receipt
                return receipt
            return self._record_mission_transition(self.oracle.click(target))
        if self._mail_context is not None and name == "MAIL_MANAGE":
            if self.oracle.enabled("mail/manage/back"):
                return self.oracle.click("mail/manage/back")
            return self.oracle.click("mail/manage")
        if semantic_id is not None:
            if (
                self._dorm_context is not None
                and semantic_id in ("main/live", "dorm-menu/dorm", "dorm/page/back")
            ):
                cached = self._dorm_context.navigation_receipts.get(semantic_id)
                if (
                    cached is not None
                    and time.monotonic()
                    <= self._dorm_context.passive_transition_until
                ):
                    return cached
            if self._build_context is not None and semantic_id == "main/build":
                self._build_context.coins_owned = self.oracle.main_gold()
            if (
                self._research_context is not None
                and semantic_id.startswith("research/project/")
            ):
                slot = int(semantic_id.rsplit("/", 1)[1])
                projects = self.oracle.research_projects()
                matches = tuple(project for project in projects if project.slot == slot)
                if len(matches) != 1:
                    raise SemanticGateClosed("research project slot identity is ambiguous")
                project = matches[0]
                if project.status == ResearchProjectStatus.FINISHED:
                    if self._research_context.reward_budget <= 0:
                        raise SemanticGateClosed(
                            "finished research claim requires a positive budget"
                        )
                    receipt = self.oracle.click_research_project(slot)
                    self._research_context.reward_budget -= 1
                    self._research_context.reward_receipts.append(receipt)
                    self._research_context.selected_slot = None
                    self._research_context.selected_code = None
                    self._research_context.selected_status = None
                    self._research_context.start_receipt = None
                    self._research_context.start_confirm_receipt = None
                    self._research_context.pending_resource_id = None
                    self._research_context.pending_resource_required = None
                    self._research_context.last_queue_state = None
                    self._research_context.last_projects = None
                    self._research_context.queue_add_receipt = None
                    self._research_context.queue_confirm_receipt = None
                    self._research_context.queue_add_uses_start_budget = False
                    return receipt
                receipt = self.oracle.click_research_project(slot)
                self._research_context.selected_slot = slot
                self._research_context.selected_code = project.code
                self._research_context.selected_status = project.status
                self._research_context.start_receipt = None
                self._research_context.start_confirm_receipt = None
                self._research_context.pending_resource_id = None
                self._research_context.pending_resource_required = None
                self._research_context.queue_add_receipt = None
                self._research_context.queue_confirm_receipt = None
                self._research_context.queue_add_uses_start_budget = False
                return receipt
            if self._mission_context is not None:
                if (
                    semantic_id == "main/more"
                    and self._mission_context.summary_entry_receipt is not None
                ):
                    return self._mission_context.summary_entry_receipt
                if (
                    semantic_id == "main/task"
                    and self._mission_context.entry_receipt is not None
                ):
                    return self._mission_context.entry_receipt
            if self._commission_context is not None and semantic_id in (
                "reward/commission/finish",
                "reward/tactical/finish",
            ):
                context = self._commission_context
                if semantic_id == "reward/commission/finish":
                    if context.flow_kind != "commission":
                        raise SemanticGateClosed(
                            "commission reward input used outside commission flow"
                        )
                    if context.reward_claim_receipt is not None:
                        return context.reward_claim_receipt
                    # Re-read the finished counter immediately before input so
                    # a second commission completing after the preflight cannot
                    # turn a one-item budget into a multi-claim action.
                    self.commission_reward_pending()
                    if not self.commission_reward_allowed():
                        raise SemanticGateClosed(
                            "commission reward requires one finished row and a positive budget"
                        )
                    receipt = self.oracle.click(semantic_id)
                    context.reward_budget -= 1
                    context.reward_claim_receipt = receipt
                    return self._record_mission_transition(receipt)
                if context.flow_kind != "tactical" or not context.rewards_allowed:
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
            if (
                self._research_context is not None
                and semantic_id in (
                    "main/tech",
                    "research-menu/research",
                    "research-menu/page/back",
                    "research/page/back",
                )
            ):
                cached = self._research_context.navigation_receipts.get(semantic_id)
                if (
                    cached is not None
                    and time.monotonic()
                    <= self._research_context.passive_transition_until
                ):
                    return cached
            receipt = self.oracle.click(semantic_id)
            if semantic_id == "main/task" and self._mission_context is not None:
                self._mission_context.entry_clicked = True
                self._mission_context.entry_receipt = receipt
            if semantic_id == "main/more" and self._mission_context is not None:
                self._mission_context.summary_entry_clicked = True
                self._mission_context.summary_entry_receipt = receipt
            if (
                self._login_context is not None
                and semantic_id in (
                    "login/enter",
                    "overlay/bulletin/close",
                    "reward/award-info/close",
                    "reward/award-info1/close",
                    "overlay/login-data-expired/confirm",
                )
            ):
                if semantic_id == "login/enter":
                    self._login_context.entry_receipt = receipt
                self._login_context.passive_transition_until = (
                    time.monotonic() + 60.0
                )
            if semantic_id == "main/mail" and self._mail_context is not None:
                self._mail_context.entry_clicked = True
            receipt = self._record_mission_transition(receipt)
            if (
                self._research_context is not None
                and semantic_id in (
                    "main/tech",
                    "research-menu/research",
                    "research-menu/page/back",
                    "research/page/back",
                )
            ):
                self._research_context.navigation_receipts[semantic_id] = receipt
            if (
                self._dorm_context is not None
                and semantic_id in ("main/live", "dorm-menu/dorm", "dorm/page/back")
            ):
                self._dorm_context.navigation_receipts[semantic_id] = receipt
            return receipt

        if (
            self._commission_context is not None
            and name in COMMISSION_CLICK_RESOURCES
        ):
            tab_target = COMMISSION_TAB_TARGETS.get(name)
            if tab_target is not None:
                return self.oracle.click_image(tab_target)
            if name in ("COMMISSION_ADVICE", "COMMISSION_START"):
                context = self._commission_context
                if context.selected_signature is None:
                    raise SemanticGateClosed("commission row selection is not proven")
                if name == "COMMISSION_ADVICE":
                    return self.oracle.click_commission_recommend(
                        context.selected_signature
                    )
                if context.start_receipt is not None:
                    return context.start_receipt
                if context.start_budget <= 0:
                    raise SemanticGateClosed(
                        "commission start input requires a positive independent budget"
                    )
                detail = self.oracle.commission_detail_state()
                expected = context.selected_signature
                if detail.signature != (expected[1], expected[2], expected[3]):
                    raise SemanticGateClosed(
                        "selected commission detail identity changed"
                    )
                if detail.selected_ship_count < 3:
                    raise SemanticGateClosed(
                        "commission start requires at least three assigned ships"
                    )
                if detail.oil_cost != 0:
                    raise SemanticGateClosed(
                        "semantic commission start is limited to zero-oil rows"
                    )
                receipt = self.oracle.click_commission_start(
                    context.selected_signature
                )
                context.start_budget -= 1
                context.start_receipt = receipt
                context.start_clicked_at = time.monotonic()
                return receipt
            if name == "BACK_ARROW":
                targets = tuple(
                    semantic_id
                    for semantic_id in (
                        "tactical/page/back",
                        "commission/page/back",
                    )
                    if self.oracle.enabled(semantic_id)
                )
                if len(targets) != 1:
                    raise SemanticGateClosed(
                        "contextual ALAS back target is absent or ambiguous"
                    )
                return self.oracle.click(targets[0])
            if name in ("EXP_INFO_S_REWARD", "REWARD_SAVE_CLICK"):
                context = self._commission_context
                if context.flow_kind == "commission":
                    if context.reward_claim_receipt is None:
                        raise SemanticGateClosed(
                            "commission reward popup requires a budgeted finish input"
                        )
                    for recorded in context.reward_close_receipts:
                        if recorded.semantic_id == "reward/ship-exp/close":
                            return recorded
                elif not context.rewards_allowed:
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                receipt = self.oracle.click("reward/ship-exp/close")
                if context.flow_kind == "commission":
                    context.reward_close_receipts.append(receipt)
                return self._record_mission_transition(receipt)
            if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                context = self._commission_context
                if context.flow_kind == "commission":
                    if context.reward_claim_receipt is None:
                        raise SemanticGateClosed(
                            "commission reward popup requires a budgeted finish input"
                        )
                elif not context.rewards_allowed:
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                target = self._award_close_target()
                if target is None:
                    if context.flow_kind == "commission":
                        recorded_awards = tuple(
                            recorded
                            for recorded in context.reward_close_receipts
                            if recorded.semantic_id in (
                                "reward/award-info/close",
                                "reward/award-info1/close",
                            )
                        )
                        if recorded_awards:
                            # ALAS can decide a cached popup asset still appears
                            # immediately after the Unity object has gone away.
                            # Reuse the last exact receipt instead of turning
                            # that observation race into another ADB input.
                            return recorded_awards[-1]
                    raise SemanticGateClosed("reviewed commission reward popup is absent")
                if context.flow_kind == "commission":
                    for recorded in context.reward_close_receipts:
                        if recorded.semantic_id == target:
                            return recorded
                receipt = self.oracle.click(target)
                if context.flow_kind == "commission":
                    context.reward_close_receipts.append(receipt)
                return self._record_mission_transition(receipt)

        if self._commission_context is not None and commission_row_match is not None:
            signature = getattr(button, "semantic_commission_signature", None)
            if not isinstance(signature, tuple) or len(signature) != 6:
                raise SemanticGateClosed("ALAS commission row identity is malformed")
            receipt = self.oracle.click_commission_row(signature)
            context = self._commission_context
            context.selected_signature = signature
            context.selected_at = time.monotonic()
            context.start_receipt = None
            context.start_clicked_at = 0.0
            context.start_proof = None
            return receipt

        if self._mail_context is not None and name in MAIL_CLICK_RESOURCES:
            toggle_target = MAIL_TOGGLE_TARGETS.get(name)
            if toggle_target is not None:
                return self.oracle.click_toggle(toggle_target)
            if name in ("MAIL_BATCH_CLAIM", "MAIL_BATCH_DELETE"):
                if not self._mail_context.mutations_allowed:
                    raise SemanticGateClosed(
                        "mail mutation requires the separate explicit opt-in"
                    )
                target = (
                    "mail/manage/claim"
                    if name == "MAIL_BATCH_CLAIM"
                    else "mail/manage/delete"
                )
                return self.oracle.click(target)
            if name == "GOTO_MAIN_WHITE":
                if not self._mail_context.entry_clicked:
                    raise SemanticGateClosed("mail entry identity is not proven")
                return self.oracle.click("mail/page/back")
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("reviewed mail reward popup is absent")
                return self.oracle.click(target)

        if navbar_match is not None:
            context = self._require_mission_context()
            if not context.entry_clicked or not self.oracle.enabled("task/page/back"):
                raise SemanticGateClosed("mission navbar page identity is not proven")
            return self.oracle.click_image(
                MISSION_NAVBAR_TARGETS[int(navbar_match.group(1))]
            )

        context = self._require_mission_context()
        if name == "MISSION_MULTI":
            state = self._stable_mission_state()
            if (
                state is None
                or state.disposition != MissionDisposition.CLAIMABLE_ALL
                or state.claim_all is None
            ):
                raise SemanticGateClosed("stable mission claim-all is absent")
            if context.claim_budget <= 0:
                raise SemanticGateClosed(
                    "mission claim input requires the separate one-claim opt-in"
                )
            context.claim_budget -= 1
            return self.oracle.click("task/claim/all")
        if name == "MISSION_SINGLE":
            raise SemanticGateClosed("numeric-row mission claiming is not validated")
        if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
            target = self._award_close_target()
            if target is None:
                raise SemanticGateClosed("reviewed reward popup close is absent")
            return self.oracle.click(target)
        if name == "GUILD_POPUP_CANCEL":
            if not self.oracle.enabled("overlay/guild-message/close"):
                raise SemanticGateClosed("reviewed guild-message close is absent")
            return self.oracle.click("overlay/guild-message/close")
        raise AlasSemanticUnmapped(
            "ALAS resource is not semantically mapped for input: {0}".format(name)
        )

    def match_template_color(self, button: Any) -> bool:
        return self.appear(button)

    def image_color_count(
        self,
        button: Any,
        color: Tuple[int, int, int],
        threshold: int,
        count: int,
    ) -> bool:
        del threshold, count
        name = self._button_name(button)
        self._package_gate()
        if name in ("MISSION_NOTICE_WHITE", "MISSION_WEEKLY_RED_DOT"):
            return self._mission_resource_appears(name)

        mail_toggle = MAIL_TOGGLE_TARGETS.get(name)
        if mail_toggle is not None:
            if self._mail_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS mail option used outside mail flow: {0}".format(name)
                )
            return self.oracle.toggle_selected(mail_toggle)

        build_side_match = BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
        if build_side_match is not None:
            if self._build_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS construction navbar used outside build flow"
                )
            index = int(build_side_match.group(1))
            if index >= len(BUILD_SIDE_NAVBAR_TARGETS):
                return False
            selected = self.oracle.toggle_selected(
                BUILD_SIDE_NAVBAR_TARGETS[index]
            )
            normalized_color = tuple(color)
            if normalized_color == BUILD_SIDE_NAVBAR_ACTIVE_COLOR:
                return selected
            if normalized_color == BUILD_SIDE_NAVBAR_INACTIVE_COLOR:
                return not selected
            raise SemanticGateClosed(
                "unexpected construction side-navbar color contract"
            )

        build_pool_match = BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        if build_pool_match is not None:
            if self._build_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS construction pool navbar used outside build flow"
                )
            index = int(build_pool_match.group(1))
            target = BUILD_POOL_NAVBAR_TARGETS.get(index)
            if target is None:
                return False
            selected = self.oracle.toggle_selected(target)
            normalized_color = tuple(color)
            if normalized_color == BUILD_POOL_NAVBAR_ACTIVE_COLOR:
                return selected
            if normalized_color == BUILD_POOL_NAVBAR_INACTIVE_COLOR:
                return not selected
            raise SemanticGateClosed(
                "unexpected construction pool-navbar color contract"
            )

        match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        if match is None:
            raise AlasSemanticUnmapped(
                "ALAS color resource is not semantically mapped: {0}".format(name)
            )
        context = self._require_mission_context()
        if not context.entry_clicked or not self.oracle.enabled("task/page/back"):
            raise SemanticGateClosed("default mission tab identity is not proven")
        index = int(match.group(1))
        selected = self.oracle.image_selected(MISSION_NAVBAR_TARGETS[index])
        normalized_color = tuple(color)
        if normalized_color == MISSION_NAVBAR_ACTIVE_COLOR:
            return selected
        if normalized_color == MISSION_NAVBAR_INACTIVE_COLOR:
            return not selected
        raise SemanticGateClosed("unexpected mission navbar color contract")

    def _enter_mission_page(
        self, timeout_seconds: float
    ) -> Tuple[ActionReceipt, MissionPageState, Tuple[str, ...]]:
        dismissed_overlays = []
        deadline = time.monotonic() + timeout_seconds
        while not self.oracle.enabled("main/task"):
            dismissed = False
            for semantic_id in (
                "overlay/bulletin/close",
                "overlay/guild-message/close",
            ):
                if self.oracle.enabled(semantic_id):
                    self.oracle.click(semantic_id)
                    dismissed_overlays.append(semantic_id)
                    dismissed = True
                    time.sleep(0.75)
                    break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("unobstructed main task target did not appear")
            if not dismissed:
                time.sleep(0.5)

        entry = self.oracle.click("main/task")
        self.oracle.wait_for(
            "task/page/back",
            timeout_seconds,
            minimum_generation=entry.generation,
        )
        page = self.oracle.wait_for_mission_state(timeout_seconds)
        return entry, page, tuple(dismissed_overlays)

    def _return_from_mission(self, timeout_seconds: float) -> ActionReceipt:
        exit_receipt = self.oracle.click("task/page/back")
        self.oracle.wait_for(
            "main/task",
            timeout_seconds,
            minimum_generation=exit_receipt.generation,
        )
        return exit_receipt

    def run_mission_reward(
        self,
        daily: bool = True,
        weekly: bool = True,
        timeout_seconds: float = 30.0,
        allow_claim_once: bool = False,
    ) -> Union[MissionRunReceipt, MissionClaimReceipt]:
        """Run the reviewed no-claim TaskScene branch.

        Claim Buttons are detected, but deliberately not clicked until their
        reward-popup and post-claim contracts have separate live evidence.
        """

        self._package_gate()
        if not daily and not weekly:
            return MissionRunReceipt("disabled", 0, "", "")

        entry, page, dismissed_overlays = self._enter_mission_page(timeout_seconds)

        if page.disposition in (
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.CLAIMABLE_ROW,
        ):
            if allow_claim_once and page.disposition == MissionDisposition.CLAIMABLE_ALL:
                return self._claim_open_mission(
                    entry,
                    page,
                    dismissed_overlays,
                    timeout_seconds,
                )
            exit_receipt = self._return_from_mission(timeout_seconds)
            raise MissionClaimableDetected(
                page=page,
                entry=entry,
                exit_receipt=exit_receipt,
                dismissed_overlays=tuple(dismissed_overlays),
            )
        if page.disposition not in (
            MissionDisposition.UNFINISHED,
            MissionDisposition.EMPTY,
        ):
            self._return_from_mission(timeout_seconds)
            raise SemanticGateClosed("mission state is not proven")
        exit_receipt = self._return_from_mission(timeout_seconds)
        return MissionRunReceipt(
            outcome="nothing-claimable",
            page_generation=page.generation,
            entry_path=entry.path,
            exit_path=exit_receipt.path,
            claim_injected=False,
            claim_all_present=page.claim_all is not None,
            claim_row_count=len(page.claim_rows),
            unfinished_row_count=len(page.unfinished_rows),
            dismissed_overlays=tuple(dismissed_overlays),
        )

    def _claim_open_mission(
        self,
        entry: ActionReceipt,
        page: MissionPageState,
        dismissed_overlays: Tuple[str, ...],
        timeout_seconds: float,
    ) -> MissionClaimReceipt:
        if (
            page.disposition != MissionDisposition.CLAIMABLE_ALL
            or page.claim_all is None
        ):
            raise SemanticGateClosed("unique actionable mission claim-all is absent")

        claim_receipt = self.oracle.click("task/claim/all")
        popup_semantic_id, _ = self.oracle.wait_for_any(
            (
                "reward/award-info/close",
                "reward/award-info1/close",
            ),
            timeout_seconds,
            minimum_generation=claim_receipt.generation,
        )
        popup_close_receipt = self.oracle.click(popup_semantic_id)
        self.oracle.wait_for(
            "task/page/back",
            timeout_seconds,
            minimum_generation=popup_close_receipt.generation,
        )
        post_page = self.oracle.wait_for_mission_state(timeout_seconds)
        if post_page.disposition != MissionDisposition.UNFINISHED:
            raise SemanticGateClosed("post-claim mission state is not proven unfinished")
        exit_receipt = self._return_from_mission(timeout_seconds)
        return MissionClaimReceipt(
            outcome="claimed-all-once",
            pre_claim_generation=page.generation,
            post_claim_generation=post_page.generation,
            entry_path=entry.path,
            claim_path=claim_receipt.path,
            popup_close_path=popup_close_receipt.path,
            exit_path=exit_receipt.path,
            pre_claim_row_count=len(page.claim_rows),
            post_claim_row_count=len(post_page.claim_rows),
            unfinished_row_count=len(post_page.unfinished_rows),
            claim_input_count=1,
            dismissed_overlays=dismissed_overlays,
        )

    def claim_mission_rewards_once(
        self,
        timeout_seconds: float = 30.0,
    ) -> MissionClaimReceipt:
        """Inject one reviewed GetAllButton claim and prove its full closure."""

        self._package_gate()
        entry, page, dismissed_overlays = self._enter_mission_page(timeout_seconds)
        if (
            page.disposition != MissionDisposition.CLAIMABLE_ALL
            or page.claim_all is None
        ):
            self._return_from_mission(timeout_seconds)
            raise SemanticGateClosed("unique actionable mission claim-all is absent")
        return self._claim_open_mission(
            entry,
            page,
            dismissed_overlays,
            timeout_seconds,
        )

    @staticmethod
    def reject_raw_input(operation: str) -> None:
        raise SemanticGateClosed(
            "raw ALAS input is disabled in semantic mode: {0}".format(operation)
        )


class AlasSemanticSession:
    """Own a lazy ADB bridge and adapter for one pinned ALAS device."""

    _REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")

    def __init__(
        self,
        serial: str,
        driver_revision: str,
        adb: str = "adb",
        package: str = "com.bilibili.azurlane",
        component: str = (
            "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
        ),
        allow_mission_claim_once: bool = False,
        allow_mail_mutations: bool = False,
        allow_tactical_rewards: bool = False,
        tactical_assign_budget: int = 0,
        commission_reward_budget: int = 0,
        commission_start_budget: int = 0,
        research_reward_budget: int = 0,
        research_start_budget: int = 0,
        dorm_collect_budget: int = 0,
        dorm_feed_budget: int = 0,
        build_submit_budget: int = 0,
        campaign_stage_entry_budget: int = 0,
        campaign_fleet_mutation_budget: int = 0,
        campaign_sortie_budget: int = 0,
        campaign_combat_budget: int = 0,
        campaign_viewport_swipe_budget: int = 0,
        adb_command_timeout_seconds: int = 10,
        observer_max_age_ms: int = 2500,
        package_process_lease: Optional[AlasPackageProcessLease] = None,
    ) -> None:
        if not serial:
            raise ValueError("semantic ALAS mode requires an ADB serial")
        if not self._REVISION_PATTERN.fullmatch(driver_revision):
            raise ValueError("semantic ALAS mode requires a pinned ANGLE revision")
        if (
            isinstance(adb_command_timeout_seconds, bool)
            or not isinstance(adb_command_timeout_seconds, int)
            or not 1 <= adb_command_timeout_seconds <= 120
        ):
            raise ValueError("semantic ALAS ADB timeout must be in [1, 120]")
        if (
            isinstance(observer_max_age_ms, bool)
            or not isinstance(observer_max_age_ms, int)
            or not 1 <= observer_max_age_ms <= 300000
        ):
            raise ValueError("semantic ALAS observer max age must be in [1, 300000]")
        if package_process_lease is not None and not isinstance(
            package_process_lease, AlasPackageProcessLease
        ):
            raise ValueError("semantic ALAS package lease is not verified")
        self.serial = serial
        self.driver_revision = driver_revision
        self.package = package
        self.component = component
        self.allow_mission_claim_once = bool(allow_mission_claim_once)
        self.allow_mail_mutations = bool(allow_mail_mutations)
        self.allow_tactical_rewards = bool(allow_tactical_rewards)
        for label, budget in (
            ("tactical assign", tactical_assign_budget),
            ("commission reward", commission_reward_budget),
            ("commission start", commission_start_budget),
            ("research reward", research_reward_budget),
            ("research start", research_start_budget),
            ("dorm collect", dorm_collect_budget),
            ("dorm feed", dorm_feed_budget),
            ("build submit", build_submit_budget),
            ("campaign stage entry", campaign_stage_entry_budget),
            ("campaign fleet mutation", campaign_fleet_mutation_budget),
            ("campaign sortie", campaign_sortie_budget),
            ("campaign combat", campaign_combat_budget),
            ("campaign viewport swipe", campaign_viewport_swipe_budget),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or budget < 0
            ):
                raise ValueError(
                    "{0} budget must be a non-negative integer".format(label)
                )
        self.commission_reward_budget = commission_reward_budget
        self.tactical_assign_budget = tactical_assign_budget
        self.commission_start_budget = commission_start_budget
        self.research_reward_budget = research_reward_budget
        self.research_start_budget = research_start_budget
        self.dorm_collect_budget = dorm_collect_budget
        self.dorm_feed_budget = dorm_feed_budget
        self.build_submit_budget = build_submit_budget
        self.campaign_stage_entry_budget = campaign_stage_entry_budget
        self.campaign_fleet_mutation_budget = campaign_fleet_mutation_budget
        self.campaign_sortie_budget = campaign_sortie_budget
        self.campaign_combat_budget = campaign_combat_budget
        self.campaign_viewport_swipe_budget = campaign_viewport_swipe_budget
        self.package_process_lease = package_process_lease
        self.observer_max_age_ms = observer_max_age_ms
        self.bridge = AdbObserverBridge(
            serial,
            package,
            adb=adb,
            command_timeout_seconds=float(adb_command_timeout_seconds),
        )
        self.adapter: Optional[AlasSemanticAdapter] = None

    @classmethod
    def from_environment(cls, serial: str) -> "AlasSemanticSession":
        if os.environ.get("ALAS_SEMANTIC_MODE") != "1":
            raise SemanticGateClosed("ALAS semantic mode is not explicitly enabled")
        revision = os.environ.get("ALAS_SEMANTIC_DRIVER_REVISION", "").lower()
        adb = os.environ.get("ALAS_SEMANTIC_ADB", "adb")
        raw_adb_timeout = os.environ.get(
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS", "10"
        )
        raw_start_budget = os.environ.get(
            "ALAS_SEMANTIC_COMMISSION_START_BUDGET", "0"
        )
        raw_reward_budget = os.environ.get(
            "ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET", "0"
        )
        raw_tactical_assign_budget = os.environ.get(
            "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET", "0"
        )
        raw_research_reward_budget = os.environ.get(
            "ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET", "0"
        )
        raw_research_start_budget = os.environ.get(
            "ALAS_SEMANTIC_RESEARCH_START_BUDGET", "0"
        )
        raw_dorm_collect_budget = os.environ.get(
            "ALAS_SEMANTIC_DORM_COLLECT_BUDGET", "0"
        )
        raw_dorm_feed_budget = os.environ.get(
            "ALAS_SEMANTIC_DORM_FEED_BUDGET", "0"
        )
        raw_build_submit_budget = os.environ.get(
            "ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET", "0"
        )
        raw_campaign_stage_entry_budget = os.environ.get(
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET", "0"
        )
        raw_campaign_fleet_mutation_budget = os.environ.get(
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET", "0"
        )
        raw_campaign_sortie_budget = os.environ.get(
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET", "0"
        )
        raw_campaign_combat_budget = os.environ.get(
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET", "0"
        )
        raw_campaign_viewport_swipe_budget = os.environ.get(
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET", "0"
        )
        for label, value in (
            ("ADB command timeout", raw_adb_timeout),
            ("tactical assign", raw_tactical_assign_budget),
            ("commission reward", raw_reward_budget),
            ("commission start", raw_start_budget),
            ("research reward", raw_research_reward_budget),
            ("research start", raw_research_start_budget),
            ("dorm collect", raw_dorm_collect_budget),
            ("dorm feed", raw_dorm_feed_budget),
            ("build submit", raw_build_submit_budget),
            ("campaign stage entry", raw_campaign_stage_entry_budget),
            ("campaign fleet mutation", raw_campaign_fleet_mutation_budget),
            ("campaign sortie", raw_campaign_sortie_budget),
            ("campaign combat", raw_campaign_combat_budget),
            ("campaign viewport swipe", raw_campaign_viewport_swipe_budget),
        ):
            if re.fullmatch(r"0|[1-9][0-9]*", value) is None:
                raise SemanticGateClosed(
                    "{0} budget must be a canonical non-negative integer".format(
                        label
                    )
                )
        if "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS" in os.environ:
            raise SemanticGateClosed(
                "boolean commission reward opt-in was removed; use the integer budget"
            )
        return cls(
            serial=serial,
            driver_revision=revision,
            adb=adb,
            allow_mission_claim_once=(
                os.environ.get("ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE") == "1"
            ),
            allow_mail_mutations=(
                os.environ.get("ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS") == "1"
            ),
            allow_tactical_rewards=(
                os.environ.get("ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS") == "1"
            ),
            tactical_assign_budget=int(raw_tactical_assign_budget),
            commission_reward_budget=int(raw_reward_budget),
            commission_start_budget=int(raw_start_budget),
            research_reward_budget=int(raw_research_reward_budget),
            research_start_budget=int(raw_research_start_budget),
            dorm_collect_budget=int(raw_dorm_collect_budget),
            dorm_feed_budget=int(raw_dorm_feed_budget),
            build_submit_budget=int(raw_build_submit_budget),
            campaign_stage_entry_budget=int(raw_campaign_stage_entry_budget),
            campaign_fleet_mutation_budget=int(
                raw_campaign_fleet_mutation_budget
            ),
            campaign_sortie_budget=int(raw_campaign_sortie_budget),
            campaign_combat_budget=int(raw_campaign_combat_budget),
            campaign_viewport_swipe_budget=int(
                raw_campaign_viewport_swipe_budget
            ),
            adb_command_timeout_seconds=int(raw_adb_timeout),
        )

    def open(self) -> AlasSemanticAdapter:
        if self.adapter is not None:
            return self.adapter
        try:
            self.bridge.open()
            package_gate = PinnedPackageGate(self.bridge)
            if self.package_process_lease is None:
                package_gate()
            else:
                if (
                    self.package_process_lease.driver_revision
                    != self.driver_revision
                ):
                    raise SemanticGateClosed(
                        "package process lease driver revision changed"
                    )
                package_gate.accept_process_lease(self.package_process_lease)
            oracle = SemanticOracle(
                self.bridge.request,
                self.bridge.foreground_component,
                self.bridge.tap,
                OracleFingerprint(
                    package=self.package,
                    component=self.component,
                    driver_revision=self.driver_revision,
                    expected_pid=self.bridge.pid,
                    max_age_ms=self.observer_max_age_ms,
                ),
                swipe=self.bridge.swipe,
            )
            self.adapter = AlasSemanticAdapter(
                oracle,
                package_gate,
                allow_mission_claim_once=self.allow_mission_claim_once,
                allow_mail_mutations=self.allow_mail_mutations,
                allow_tactical_rewards=self.allow_tactical_rewards,
                tactical_assign_budget=self.tactical_assign_budget,
                commission_reward_budget=self.commission_reward_budget,
                commission_start_budget=self.commission_start_budget,
                research_reward_budget=self.research_reward_budget,
                research_start_budget=self.research_start_budget,
                dorm_collect_budget=self.dorm_collect_budget,
                dorm_feed_budget=self.dorm_feed_budget,
                build_submit_budget=self.build_submit_budget,
                campaign_stage_entry_budget=self.campaign_stage_entry_budget,
                campaign_fleet_mutation_budget=(
                    self.campaign_fleet_mutation_budget
                ),
                campaign_sortie_budget=self.campaign_sortie_budget,
                campaign_combat_budget=self.campaign_combat_budget,
                campaign_viewport_swipe_budget=(
                    self.campaign_viewport_swipe_budget
                ),
            )
            return self.adapter
        except Exception:
            self.bridge.close()
            raise

    def close(self) -> None:
        self.adapter = None
        self.bridge.close()

    def __enter__(self) -> AlasSemanticAdapter:
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def semantic_id_for(self, button: Any) -> str:
        # Name validation is cheap and happens before the bridge is opened, so
        # unmapped ALAS calls fail without touching ADB or the game.
        if self.adapter is None:
            name = AlasSemanticAdapter._button_name(button)
            try:
                return DEFAULT_ALAS_BUTTON_TARGETS[name]
            except KeyError as exc:
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                ) from exc
        return self.adapter.semantic_id_for(button)

    def appear(self, button: Any) -> bool:
        return self.open().appear(button)

    def match_template_color(self, button: Any) -> bool:
        return self.open().match_template_color(button)

    def image_color_count(
        self,
        button: Any,
        color: Tuple[int, int, int],
        threshold: int,
        count: int,
    ) -> bool:
        return self.open().image_color_count(button, color, threshold, count)

    def bounds(self, button: Any) -> Bounds:
        self.semantic_id_for(button)
        return self.open().bounds(button)

    def ocr_text(
        self,
        areas: Sequence[Any],
        alphabet: Optional[str] = None,
    ) -> Union[str, List[str]]:
        return self.open().ocr_text(areas, alphabet=alphabet)

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        return self.open().research_projects()

    def research_detail_state(self) -> ResearchDetailState:
        return self.open().research_detail_state()

    def research_detail_available(self) -> bool:
        return self.open().research_detail_available()

    def research_detail_is_running(self) -> bool:
        return self.open().research_detail_is_running()

    def research_detail_can_queue(self) -> bool:
        return self.open().research_detail_can_queue()

    def research_queue_state(self) -> ResearchQueueState:
        return self.open().research_queue_state()

    def research_queue_empty_slots(self) -> int:
        return self.open().research_queue_empty_slots()

    def research_queue_fill_slots(self) -> int:
        return self.open().research_queue_fill_slots()

    def research_queue_remaining_seconds(self) -> int:
        return self.open().research_queue_remaining_seconds()

    def build_selected_pool(self) -> BuildPool:
        return self.open().build_selected_pool()

    def build_costs(self) -> BuildCostState:
        return self.open().build_costs()

    def dorm_state(self) -> DormState:
        return self.open().dorm_state()

    def dorm_feed_state(self) -> DormFeedState:
        return self.open().dorm_feed_state()

    def dorm_food_counts(self) -> Tuple[int, ...]:
        return self.open().dorm_food_counts()

    def dorm_feed_food(self, item_index: int, count: int) -> Tuple[ActionReceipt, ...]:
        return self.open().dorm_feed_food(item_index, count)

    def build_submit_state(self) -> BuildSubmitState:
        return self.open().build_submit_state()

    def build_coins_owned(self) -> int:
        return self.open().build_coins_owned()

    def campaign_page_state(self) -> CampaignPageState:
        return self.open().campaign_page_state()

    def campaign_oil(self) -> int:
        return self.open().campaign_oil()

    def campaign_map_state(
        self,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        return self.open().campaign_map_state(
            columns=columns,
            rows=rows,
            land_cells=land_cells,
            expected_fleet_count=expected_fleet_count,
        )

    def authorize_campaign_combat(
        self,
        decision: AlasCampaignDecisionPreview,
        state: CampaignMapState,
    ) -> Optional[AlasCampaignCombatAdmission]:
        return self.open().authorize_campaign_combat(decision, state)

    def campaign_combat_committed(self) -> bool:
        return self.open().campaign_combat_committed()

    def confirm_campaign_combat(
        self,
        battle_count_after: int,
    ) -> AlasCampaignCombatProof:
        return self.open().confirm_campaign_combat(battle_count_after)

    def begin_campaign_map_swipe_vector(
        self, vector: Any, **kwargs: Any
    ) -> CampaignMapViewportSwipeIntent:
        return self.open().begin_campaign_map_swipe_vector(vector, **kwargs)

    def end_campaign_map_swipe_vector(
        self, intent: CampaignMapViewportSwipeIntent
    ) -> None:
        self.open().end_campaign_map_swipe_vector(intent)

    def swipe(
        self,
        p1: Any,
        p2: Any,
        *,
        duration: Any,
        name: Any,
        distance_check: Any,
    ) -> CampaignMapViewportSwipeProof:
        return self.open().swipe(
            p1,
            p2,
            duration=duration,
            name=name,
            distance_check=distance_check,
        )

    def campaign_map_viewport_swipe_committed(self) -> bool:
        return self.open().campaign_map_viewport_swipe_committed()

    def campaign_map_viewport_swipe_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        return self.open().campaign_map_viewport_swipe_proof()

    def campaign_camera_state(self) -> CampaignMapState:
        return self.open().campaign_camera_state()

    def campaign_camera_target_node(self) -> Optional[str]:
        return self.open().campaign_camera_target_node()

    def recheck_campaign_combat_target_after_camera_view(
        self, state: CampaignMapState
    ) -> CampaignMapTargetRecheckProof:
        return self.open().recheck_campaign_combat_target_after_camera_view(
            state
        )

    def campaign_stage_entry_allowed(self) -> bool:
        return self.open().campaign_stage_entry_allowed()

    def campaign_map_preparation_committed(self) -> bool:
        return self.open().campaign_map_preparation_committed()

    def confirm_campaign_pre_sortie(self) -> CampaignPreSortieProof:
        return self.open().confirm_campaign_pre_sortie()

    def authorize_campaign_fleet_preparation(
        self, fleet1: int, fleet2: int, submarine: int
    ) -> bool:
        return self.open().authorize_campaign_fleet_preparation(
            fleet1, fleet2, submarine
        )

    def campaign_fleet_row_allowed(self, row_key: str) -> bool:
        return self.open().campaign_fleet_row_allowed(row_key)

    def campaign_fleet_operator_is_hard(self, row_key: str) -> bool:
        return self.open().campaign_fleet_operator_is_hard(row_key)

    def campaign_fleet_operator_hard_satisfied(
        self, row_key: str
    ) -> Optional[bool]:
        return self.open().campaign_fleet_operator_hard_satisfied(row_key)

    def campaign_fleet_operator_in_use(self, row_key: str) -> bool:
        return self.open().campaign_fleet_operator_in_use(row_key)

    def campaign_fleet_dropdown_opened(self) -> bool:
        return self.open().campaign_fleet_dropdown_opened()

    def campaign_fleet_selected_indices(self, row_key: str) -> List[int]:
        return self.open().campaign_fleet_selected_indices(row_key)

    def confirm_campaign_fleet_selection(self) -> CampaignFleetSelectionState:
        return self.open().confirm_campaign_fleet_selection()

    def close_campaign_fleet_dropdown_for_rollback(self) -> None:
        self.open().close_campaign_fleet_dropdown_for_rollback()

    def confirm_campaign_fleet_preparation(
        self,
    ) -> CampaignFleetPreparationProof:
        return self.open().confirm_campaign_fleet_preparation()

    def authorize_campaign_sortie(
        self,
        *,
        use_auto_search: bool,
        use_2x_book: bool,
        submarine_mode: str,
        fleet_order: str,
    ) -> bool:
        return self.open().authorize_campaign_sortie(
            use_auto_search=use_auto_search,
            use_2x_book=use_2x_book,
            submarine_mode=submarine_mode,
            fleet_order=fleet_order,
        )

    def campaign_sortie_committed(self) -> bool:
        return self.open().campaign_sortie_committed()

    def confirm_campaign_sortie(self) -> CampaignSortieProof:
        return self.open().confirm_campaign_sortie()

    def research_series(self) -> List[int]:
        return self.open().research_series()

    def research_statuses(self) -> List[str]:
        return self.open().research_statuses()

    def research_finished_index(self) -> Optional[int]:
        return self.open().research_finished_index()

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        return self.open().tactical_slots()

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        return self.open().tactical_remaining_seconds()

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        return self.open().tactical_candidate_ships()

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        return self.open().tactical_skills()

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        return self.open().tactical_books()

    def tactical_select_book(self, position: int) -> ActionReceipt:
        return self.open().tactical_select_book(position)

    def tactical_book_selected(self, position: int) -> bool:
        return self.open().tactical_book_selected(position)

    def tactical_select_suitable_ship(self, min_level: int, start_index: int) -> bool:
        return self.open().tactical_select_suitable_ship(min_level, start_index)

    def tactical_select_first_trainable_skill(self) -> bool:
        return self.open().tactical_select_first_trainable_skill()

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        return self.open().commission_rows()

    def commission_is_empty(self) -> bool:
        return self.open().commission_is_empty()

    def commission_scroll_state(self) -> CommissionScrollState:
        return self.open().commission_scroll_state()

    def commission_scroll_next(self) -> Optional[CommissionScrollProof]:
        return self.open().commission_scroll_next()

    def commission_scroll_to_top(self) -> Optional[CommissionScrollProof]:
        return self.open().commission_scroll_to_top()

    def commission_reward_pending(self) -> bool:
        return self.open().commission_reward_pending()

    def commission_reward_allowed(self) -> bool:
        return self.open().commission_reward_allowed()

    def commission_reward_claimed(self) -> bool:
        return self.open().commission_reward_claimed()

    def confirm_commission_reward(self) -> CommissionRewardProof:
        return self.open().confirm_commission_reward()

    def commission_start_allowed(self) -> bool:
        return self.open().commission_start_allowed()

    def commission_detail_state(self) -> CommissionDetailState:
        return self.open().commission_detail_state()

    def commission_start_confirmed(self) -> bool:
        return self.open().commission_start_confirmed()

    def commission_start_proof(self) -> CommissionStartProof:
        return self.open().commission_start_proof()

    def close_started_commission_detail(self) -> ActionReceipt:
        return self.open().close_started_commission_detail()

    def cancel_tactical_continue_if_present(self) -> bool:
        return self.open().cancel_tactical_continue_if_present()

    def click(self, button: Any) -> ActionReceipt:
        if AlasSemanticAdapter._campaign_grid_location(button) is not None:
            return self.open().click_campaign_combat_grid(button)
        name = AlasSemanticAdapter._button_name(button)
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        if (
            name not in DEFAULT_ALAS_BUTTON_TARGETS
            and name not in MISSION_CLICK_RESOURCES
            and name not in MAIL_CLICK_RESOURCES
            and name not in CAMPAIGN_CLICK_RESOURCES
            and not (
                self.adapter is not None
                and name in RESEARCH_CLICK_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in DORM_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in BUILD_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in TACTICAL_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in COMMISSION_CLICK_RESOURCES
            )
            and MISSION_NAVBAR_PATTERN.fullmatch(name) is None
            and COMMISSION_ROW_PATTERN.fullmatch(name) is None
            and BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name) is None
            and BUILD_POOL_NAVBAR_PATTERN.fullmatch(name) is None
            and CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name) is None
            and campaign_stage_code is None
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        return self.open().click(button)

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        self.open().begin_mission_reward(daily=daily, weekly=weekly)

    def begin_login(self) -> None:
        self.open().begin_login()

    def end_login(self) -> None:
        if self.adapter is not None:
            self.adapter.end_login()

    def end_mission_reward(self) -> None:
        if self.adapter is not None:
            self.adapter.end_mission_reward()

    def mission_reward_active(self) -> bool:
        return bool(
            self.adapter is not None and self.adapter.mission_reward_active()
        )

    def mission_claim_allowed(self) -> bool:
        return self.open().mission_claim_allowed()

    def begin_mail(self) -> None:
        self.open().begin_mail()

    def end_mail(self) -> None:
        if self.adapter is not None:
            self.adapter.end_mail()

    def begin_commission(self) -> None:
        self.open().begin_commission()

    def end_commission(self) -> None:
        if self.adapter is not None:
            self.adapter.end_commission()

    def begin_tactical(self) -> None:
        self.open().begin_tactical()

    def end_tactical(self) -> None:
        if self.adapter is not None:
            self.adapter.end_commission()

    def begin_research(self) -> None:
        self.open().begin_research()

    def end_research(self) -> None:
        if self.adapter is not None:
            self.adapter.end_research()

    def begin_dorm(self) -> None:
        self.open().begin_dorm()

    def end_dorm(self) -> None:
        if self.adapter is not None:
            self.adapter.end_dorm()

    def begin_build(self) -> None:
        self.open().begin_build()

    def end_build(self) -> None:
        if self.adapter is not None:
            self.adapter.end_build()

    def begin_campaign_pre_sortie(
        self, stage_code: str, mode: str = "normal"
    ) -> None:
        self.open().begin_campaign_pre_sortie(stage_code, mode=mode)

    def end_campaign_pre_sortie(self) -> None:
        if self.adapter is not None:
            self.adapter.end_campaign_pre_sortie()

    def campaign_pre_sortie_active(self) -> bool:
        return bool(
            self.adapter is not None
            and self.adapter.campaign_pre_sortie_active()
        )

    def run_mission_reward(
        self,
        daily: bool = True,
        weekly: bool = True,
        timeout_seconds: float = 30.0,
        allow_claim_once: bool = False,
    ) -> Union[MissionRunReceipt, MissionClaimReceipt]:
        return self.open().run_mission_reward(
            daily=daily,
            weekly=weekly,
            timeout_seconds=timeout_seconds,
            allow_claim_once=allow_claim_once,
        )

    def claim_mission_rewards_once(
        self,
        timeout_seconds: float = 30.0,
    ) -> MissionClaimReceipt:
        return self.open().claim_mission_rewards_once(
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def reject_raw_input(operation: str) -> None:
        AlasSemanticAdapter.reject_raw_input(operation)
