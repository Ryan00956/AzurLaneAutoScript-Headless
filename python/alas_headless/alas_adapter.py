"""Narrow, opt-in bridge from ALAS Button names to semantic targets.

This module deliberately maps only resource names whose meaning was confirmed in
the pinned upstream ALAS tree and whose Unity target was observed in the pinned
Chinese game build.  Semantic mode must never fall back to image coordinates.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Mapping, Optional, Sequence, Set, Tuple, Union

from .semantic_oracle import (
    ActionReceipt,
    AdbObserverBridge,
    AndroidPackageFingerprint,
    Bounds,
    BuildCostState,
    BuildPool,
    BuildSubmitState,
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
CAMPAIGN_VIRTUAL_RESOURCES = frozenset(
    {
        "CAMPAIGN_CHECK",
        "CAMPAIGN_MENU_CHECK",
        "GOTO_MAIN",
    }
)
CAMPAIGN_CLICK_RESOURCES = frozenset(
    {
        "GOTO_MAIN",
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


@dataclass
class _ResearchFlowContext:
    start_budget: int = 0
    reward_budget: int = 0
    selected_slot: Optional[int] = None
    selected_code: Optional[str] = None
    start_receipt: Optional[ActionReceipt] = None
    start_confirm_receipt: Optional[ActionReceipt] = None
    pending_resource_id: Optional[str] = None
    pending_resource_required: Optional[int] = None
    reward_receipts: List[ActionReceipt] = field(default_factory=list)
    popup_close_receipts: List[ActionReceipt] = field(default_factory=list)


@dataclass
class _DormFlowContext:
    collect_budget: int = 0
    feed_budget: int = 0


@dataclass
class _BuildFlowContext:
    submit_budget: int = 0
    prep_opened: bool = False
    warning_confirmed: bool = False
    coins_owned: Optional[int] = None
    submit_receipt: Optional[ActionReceipt] = None


@dataclass
class PinnedPackageGate:
    """Cache one independent ADB verification of the installed package."""

    bridge: AdbObserverBridge
    expected: AndroidPackageFingerprint = PINNED_CN_GAME_FINGERPRINT
    _verified_pid: Optional[int] = None

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
        self._mission_context: Optional[_MissionFlowContext] = None
        self._mail_context: Optional[_MailFlowContext] = None
        self._commission_context: Optional[_CommissionFlowContext] = None
        self._research_context: Optional[_ResearchFlowContext] = None
        self._dorm_context: Optional[_DormFlowContext] = None
        self._build_context: Optional[_BuildFlowContext] = None
        self._observer_stale_since: Optional[float] = None

    @staticmethod
    def _button_name(button: Any) -> str:
        name = button if isinstance(button, str) else getattr(button, "name", None)
        if not isinstance(name, str) or not name:
            raise AlasSemanticUnmapped("ALAS resource has no stable name")
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
                self._research_context,
                self._dorm_context,
                self._build_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._mission_context = _MissionFlowContext(
            daily=bool(daily),
            weekly=bool(weekly),
            claim_budget=(1 if self._allow_mission_claim_once else 0),
        )

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
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._build_context is not None
            or self._commission_context is not None
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
            or self._mail_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._build_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._commission_context = _CommissionFlowContext(
            flow_kind="commission",
            reward_budget=self._commission_reward_budget,
            start_budget=self._commission_start_budget,
        )

    def begin_tactical(self) -> None:
        """Open the shared reward/tactical context without commission budgets."""

        self._package_gate()
        if (
            self._commission_context is not None
            or self._mail_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._build_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._commission_context = _CommissionFlowContext(
            flow_kind="tactical",
            rewards_allowed=self._allow_tactical_rewards,
            assign_budget=self._tactical_assign_budget,
        )

    def begin_research(self) -> None:
        self._package_gate()
        if any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._research_context = _ResearchFlowContext(
            start_budget=self._research_start_budget,
            reward_budget=self._research_reward_budget,
        )

    def end_research(self) -> None:
        self._research_context = None

    def begin_dorm(self) -> None:
        self._package_gate()
        if any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._dorm_context = _DormFlowContext(
            collect_budget=self._dorm_collect_budget,
            feed_budget=self._dorm_feed_budget,
        )

    def end_dorm(self) -> None:
        self._dorm_context = None

    def begin_build(self) -> None:
        self._package_gate()
        if any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._build_context = _BuildFlowContext(
            submit_budget=self._build_submit_budget
        )

    def end_build(self) -> None:
        self._build_context = None

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
        ):
            commission_context.passive_transition_until = time.monotonic() + 12.0
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
            if str(exc) != "observer snapshot is stale":
                raise
            now = time.monotonic()
            if self._observer_stale_since is None:
                self._observer_stale_since = now
            if now - self._observer_stale_since <= 5.0:
                return False
            raise
        self._observer_stale_since = None
        return result

    def _appear_once(self, button: Any) -> bool:
        name = self._button_name(button)
        semantic_id = self._mappings.get(name)
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
                and self._mail_context is None
                and self._commission_context is None
            ):
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                )
            self._package_gate()
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
                self._mission_context is not None
                and self._known_mission_surface_exists()
            ) or (
                self._mail_context is not None
                and self._known_mail_surface_exists()
            ) or (
                self._commission_context is not None
                and self._known_commission_surface_exists()
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
        if name in RESEARCH_VIRTUAL_RESOURCES and self._research_context is not None:
            if name == "QUEUE_CHECK":
                try:
                    self.oracle.research_queue_state()
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
            if name == "POPUP_CONFIRM":
                context = self._research_context
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
                    detail = self.oracle.research_detail_state()
                except SemanticGateClosed:
                    return False
                return not detail.can_start
            if name == "RESEARCH_STOP":
                try:
                    return self.oracle.research_detail_state().is_running
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_QUEUE_ADD":
                try:
                    return bool(
                        self._research_context.start_confirm_receipt is not None
                        and self.oracle.research_detail_state().can_queue
                    )
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_DETAIL_QUIT":
                return self.oracle.enabled("research/detail/root")
            if name == "QUEUE_CLAIM_REWARD":
                try:
                    queue = self.oracle.research_queue_state()
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
                    return True
                except SemanticGateClosed:
                    return False
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
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_ORDER"):
                if self.oracle.enabled("build/warning/confirm"):
                    return not self._build_context.warning_confirmed
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
            return self.oracle.campaign_menu_is_entry()
        if semantic_id is None and name == "CAMPAIGN_CHECK":
            return self.oracle.campaign_page_is_normal()
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
            if name in MAIL_VIRTUAL_RESOURCES and name not in MISSION_VIRTUAL_RESOURCES:
                raise AlasSemanticUnmapped(
                    "ALAS mail resource used outside mail flow: {0}".format(name)
                )
            if self._mission_context is not None:
                return self._mission_resource_appears(name)
            if name in MISSION_VIRTUAL_RESOURCES:
                # ALAS' generic popup loop probes a few mission-owned resource
                # names from reward flows as well.  A proven non-mission surface
                # makes those passive probes safely absent; the resources are
                # still not admitted to click() outside the mission context.
                if (
                    self._commission_context is not None
                    and self._known_commission_surface_exists()
                ) or (
                    self._mail_context is not None
                    and self._known_mail_surface_exists()
                ):
                    return False
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
        return self.oracle.research_projects()

    def research_detail_state(self) -> ResearchDetailState:
        self._package_gate()
        return self.oracle.research_detail_state()

    def research_queue_state(self) -> ResearchQueueState:
        self._package_gate()
        return self.oracle.research_queue_state()

    def research_queue_empty_slots(self) -> int:
        return self.research_queue_state().empty_slots

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
        return self.oracle.dorm_feed_state()

    def dorm_food_counts(self) -> Tuple[int, ...]:
        return tuple(item.count for item in self.dorm_feed_state().items)

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
            before = self.oracle.dorm_feed_state()
            item = before.items[item_index]
            if item.count <= 0 or before.food + item.value > before.capacity:
                raise SemanticGateClosed("dorm feed item is unavailable or would overflow")
            receipt = self.oracle.click_dorm_food(item.item_id)
            context.feed_budget -= 1
            receipts.append(receipt)
            deadline = time.monotonic() + 5.0
            while True:
                after = self.oracle.dorm_feed_state()
                after_item = after.items[item_index]
                if (
                    after_item.count == item.count - 1
                    and after.food == before.food + item.value
                ):
                    break
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed("dorm feed mutation was not proven")
                time.sleep(0.25)
        return tuple(receipts)

    def build_submit_state(self) -> BuildSubmitState:
        self._package_gate()
        return self.oracle.build_submit_state()

    def build_coins_owned(self) -> int:
        if self._build_context is None or self._build_context.coins_owned is None:
            raise SemanticGateClosed(
                "main coin count was not captured before Build entry"
            )
        return self._build_context.coins_owned

    def campaign_page_state(self) -> CampaignPageState:
        self._package_gate()
        return self.oracle.campaign_page_state()

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
        if (
            self._commission_context.flow_kind != "tactical"
            or not self._commission_context.rewards_allowed
        ):
            raise SemanticGateClosed(
                "tactical reward requires the separate explicit opt-in"
            )
        prompt = self.oracle.tactical_continue_prompt_text()
        if prompt is None or prompt in self._commission_context.cancelled_tactical_prompts:
            return False
        self.oracle.click("tactical/continue/cancel")
        self._commission_context.cancelled_tactical_prompts.add(prompt)
        return True

    def click(self, button: Any) -> ActionReceipt:
        name = self._button_name(button)
        semantic_id = self._mappings.get(name)
        navbar_match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        commission_row_match = COMMISSION_ROW_PATTERN.fullmatch(name)
        build_side_navbar_match = BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
        build_pool_navbar_match = BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
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
                if len(targets) != 1:
                    raise SemanticGateClosed("tactical back target is ambiguous")
                return self.oracle.click(targets[0])
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
                return self.oracle.click("research/queue/enter")
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
                return receipt
            if name == "RESEARCH_QUEUE_ADD":
                if context.start_confirm_receipt is None:
                    raise SemanticGateClosed(
                        "research queue add requires a confirmed budgeted start"
                    )
                return self.oracle.click("research/detail/queue")
            if name == "RESEARCH_STOP":
                raise SemanticGateClosed("semantic research cancellation is not enabled")
            if name == "QUEUE_CLAIM_REWARD":
                queue = self.oracle.research_queue_state()
                if not queue.reward_claimable or context.reward_budget <= 0:
                    raise SemanticGateClosed("research reward requires a positive budget")
                receipt = self.oracle.click("research/queue/claim")
                context.reward_budget -= 1
                context.reward_receipts.append(receipt)
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
                return self.oracle.click("research/page/back")

        if self._dorm_context is not None and name in DORM_VIRTUAL_RESOURCES:
            context = self._dorm_context
            if name == "DORM_QUICK_COLLECT":
                if context.collect_budget <= 0:
                    raise SemanticGateClosed("dorm collect requires a positive budget")
                receipt = self.oracle.click("dorm/collect")
                context.collect_budget -= 1
                return receipt
            if name == "DORM_FEED_ENTER":
                if self.oracle.enabled("dorm/feed/close"):
                    return self.oracle.click("dorm/feed/close")
                return self.oracle.click("dorm/feed")
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
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_ORDER"):
                if self.oracle.enabled("build/warning/confirm"):
                    if context.warning_confirmed:
                        raise SemanticGateClosed(
                            "construction warning was already confirmed once"
                        )
                    context.warning_confirmed = True
                    return self.oracle.click("build/warning/confirm")
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
            return self._record_mission_transition(self.oracle.click(target))
        if self._mail_context is not None and name == "MAIL_MANAGE":
            if self.oracle.enabled("mail/manage/back"):
                return self.oracle.click("mail/manage/back")
            return self.oracle.click("mail/manage")
        if semantic_id is not None:
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
                    self._research_context.start_receipt = None
                    self._research_context.start_confirm_receipt = None
                    self._research_context.pending_resource_id = None
                    self._research_context.pending_resource_required = None
                    return receipt
                receipt = self.oracle.click_research_project(slot)
                self._research_context.selected_slot = slot
                self._research_context.selected_code = project.code
                self._research_context.start_receipt = None
                self._research_context.start_confirm_receipt = None
                self._research_context.pending_resource_id = None
                self._research_context.pending_resource_required = None
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
            receipt = self.oracle.click(semantic_id)
            if semantic_id == "main/task" and self._mission_context is not None:
                self._mission_context.entry_clicked = True
                self._mission_context.entry_receipt = receipt
            if semantic_id == "main/more" and self._mission_context is not None:
                self._mission_context.summary_entry_clicked = True
                self._mission_context.summary_entry_receipt = receipt
            if semantic_id == "main/mail" and self._mail_context is not None:
                self._mail_context.entry_clicked = True
            return self._record_mission_transition(receipt)

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
    ) -> None:
        if not serial:
            raise ValueError("semantic ALAS mode requires an ADB serial")
        if not self._REVISION_PATTERN.fullmatch(driver_revision):
            raise ValueError("semantic ALAS mode requires a pinned ANGLE revision")
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
        self.bridge = AdbObserverBridge(serial, package, adb=adb)
        self.adapter: Optional[AlasSemanticAdapter] = None

    @classmethod
    def from_environment(cls, serial: str) -> "AlasSemanticSession":
        if os.environ.get("ALAS_SEMANTIC_MODE") != "1":
            raise SemanticGateClosed("ALAS semantic mode is not explicitly enabled")
        revision = os.environ.get("ALAS_SEMANTIC_DRIVER_REVISION", "").lower()
        adb = os.environ.get("ALAS_SEMANTIC_ADB", "adb")
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
        for label, value in (
            ("tactical assign", raw_tactical_assign_budget),
            ("commission reward", raw_reward_budget),
            ("commission start", raw_start_budget),
            ("research reward", raw_research_reward_budget),
            ("research start", raw_research_start_budget),
            ("dorm collect", raw_dorm_collect_budget),
            ("dorm feed", raw_dorm_feed_budget),
            ("build submit", raw_build_submit_budget),
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
        )

    def open(self) -> AlasSemanticAdapter:
        if self.adapter is not None:
            return self.adapter
        try:
            self.bridge.open()
            package_gate = PinnedPackageGate(self.bridge)
            package_gate()
            oracle = SemanticOracle(
                self.bridge.request,
                self.bridge.foreground_component,
                self.bridge.tap,
                OracleFingerprint(
                    package=self.package,
                    component=self.component,
                    driver_revision=self.driver_revision,
                    expected_pid=self.bridge.pid,
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

    def research_queue_state(self) -> ResearchQueueState:
        return self.open().research_queue_state()

    def research_queue_empty_slots(self) -> int:
        return self.open().research_queue_empty_slots()

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
        name = AlasSemanticAdapter._button_name(button)
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
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        return self.open().click(button)

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        self.open().begin_mission_reward(daily=daily, weekly=weekly)

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
