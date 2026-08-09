"""Narrow, opt-in bridge from ALAS Button names to semantic targets.

This module deliberately maps only resource names whose meaning was confirmed in
the pinned upstream ALAS tree and whose Unity target was observed in the pinned
Chinese game build.  Semantic mode must never fall back to image coordinates.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple, Union

from .semantic_oracle import (
    ActionReceipt,
    AdbObserverBridge,
    AndroidPackageFingerprint,
    Bounds,
    MissionPageState,
    MissionDisposition,
    SemanticGateClosed,
    SemanticOracle,
    OracleFingerprint,
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
    "MAIN_GOTO_DOCK": "main/dock",
    "MAIN_GOTO_DOCK_WHITE": "main/dock",
    "MAIN_GOTO_MISSION": "main/task",
    "MAIN_GOTO_MISSION_WHITE": "main/task",
    "MAIN_GOTO_SHOP": "main/shop",
    "MAIN_GOTO_SHOP_WHITE": "main/shop",
    "MAIL_ENTER": "main/mail",
    "MAIL_ENTER_WHITE": "main/mail",
    "MISSION_CHECK": "task/page/back",
    "LOGIN_ANNOUNCE": "overlay/bulletin/close",
    "LOGIN_ANNOUNCE_2": "overlay/bulletin/close",
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
MISSION_NAVBAR_TARGETS = (
    "task/nav/all",
    "task/nav/main",
    "task/nav/side",
    "task/nav/daily",
    "task/nav/weekly",
    "task/nav/event",
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
    entry_clicked: bool = False
    last_signature: Optional[Tuple[Any, ...]] = None
    last_generation: int = -1
    stable_generations: int = 0
    stable_state: Optional[MissionPageState] = None


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
        self._mission_context: Optional[_MissionFlowContext] = None

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
            or MISSION_NAVBAR_PATTERN.fullmatch(name)
        )

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        """Open one ALAS-owned mission state-machine invocation."""

        self._package_gate()
        if self._mission_context is not None:
            raise SemanticGateClosed("nested ALAS mission flow is not allowed")
        self._mission_context = _MissionFlowContext(
            daily=bool(daily),
            weekly=bool(weekly),
            claim_budget=(1 if self._allow_mission_claim_once else 0),
        )

    def end_mission_reward(self) -> None:
        """Close the ALAS-owned mission invocation and discard all cached state."""

        self._mission_context = None

    def _require_mission_context(self) -> _MissionFlowContext:
        if self._mission_context is None:
            raise SemanticGateClosed("mission resource used outside ALAS mission flow")
        return self._mission_context

    def _known_mission_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/task",
                "task/page/back",
                "reward/award-info/close",
                "reward/award-info1/close",
                "overlay/bulletin/close",
                "overlay/guild-message/close",
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
            # Absence of row Buttons is not a reviewed empty-page marker.
            return False
        raise AlasSemanticUnmapped(
            "ALAS mission resource is not semantically mapped: {0}".format(name)
        )

    def appear(self, button: Any) -> bool:
        name = self._button_name(button)
        semantic_id = self._mappings.get(name)
        if semantic_id is None and name not in MISSION_VIRTUAL_RESOURCES:
            if self._mission_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                )
            self._package_gate()
            if self._known_mission_surface_exists():
                # ALAS scans many page/popup assets.  An independently proven
                # mission surface lets unknown presence checks be safely false;
                # unknown clicks remain forbidden.
                return False
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(name)
            )
        self._package_gate()
        if semantic_id is None:
            return self._mission_resource_appears(name)
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

    def click(self, button: Any) -> ActionReceipt:
        name = self._button_name(button)
        semantic_id = self._mappings.get(name)
        navbar_match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        if (
            semantic_id is None
            and name not in MISSION_CLICK_RESOURCES
            and navbar_match is None
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        self._package_gate()
        if semantic_id is not None:
            receipt = self.oracle.click(semantic_id)
            if semantic_id == "main/task" and self._mission_context is not None:
                self._mission_context.entry_clicked = True
            return receipt

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
        if page.disposition != MissionDisposition.UNFINISHED:
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
        self.bridge = AdbObserverBridge(serial, package, adb=adb)
        self.adapter: Optional[AlasSemanticAdapter] = None

    @classmethod
    def from_environment(cls, serial: str) -> "AlasSemanticSession":
        if os.environ.get("ALAS_SEMANTIC_MODE") != "1":
            raise SemanticGateClosed("ALAS semantic mode is not explicitly enabled")
        revision = os.environ.get("ALAS_SEMANTIC_DRIVER_REVISION", "").lower()
        adb = os.environ.get("ALAS_SEMANTIC_ADB", "adb")
        return cls(
            serial=serial,
            driver_revision=revision,
            adb=adb,
            allow_mission_claim_once=(
                os.environ.get("ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE") == "1"
            ),
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
            )
            self.adapter = AlasSemanticAdapter(
                oracle,
                package_gate,
                allow_mission_claim_once=self.allow_mission_claim_once,
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

    def click(self, button: Any) -> ActionReceipt:
        name = AlasSemanticAdapter._button_name(button)
        if (
            name not in DEFAULT_ALAS_BUTTON_TARGETS
            and name not in MISSION_CLICK_RESOURCES
            and MISSION_NAVBAR_PATTERN.fullmatch(name) is None
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
