"""Bounded, zero-input replay of ALAS's original campaign combat chain.

This module qualifies control-flow ownership, not live combat.  A complete,
typed sequence of post-click combat observations drives the original ALAS
``_goto()``, ``combat()``, ``combat_preparation()``, ``combat_execute()``, and
``combat_status()`` methods on an isolated shell.  Every intended click is
recorded as a virtual action and no semantic adapter or Android input is used.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType, MethodType
from typing import Any, Mapping, Tuple

from .alas_combat_admission import AlasCampaignCombatAdmission
from .alas_decision_preview import (
    AlasCampaignDecisionPreview,
    _DECISION_LOCK,
    _copy_config,
    _decision_emotion,
    _location_tuple,
    _native_map_overlay,
    _reject_emotion_sleep,
)
from .alas_goto_input_preview import (
    _SemanticGotoGrid,
    _SemanticGotoView,
    _blocked_method,
    _validate_inputs,
)
from .alas_map_sync import AlasCampaignMapProjection
from .semantic_oracle import CampaignMapState, SemanticGateClosed


class AlasCombatReplayPhase(str, Enum):
    AUTOMATION_CONFIRM = "automation_confirm"
    BATTLE_PREPARATION_AUTOMATION_OFF = "battle_preparation_automation_off"
    BATTLE_PREPARATION = "battle_preparation"
    COMBAT_EXECUTING = "combat_executing"
    BATTLE_STATUS = "battle_status_s"
    GET_ITEMS = "get_items_1"
    EXP_INFO = "exp_info_s"
    GET_MISSION = "get_mission"
    MAP_SEARCHING = "map_enemy_searching"
    MAP_STABLE = "map_stable"


@dataclass(frozen=True)
class AlasCombatReplayFrame:
    generation: int
    phase: AlasCombatReplayPhase
    visible_resources: Tuple[str, ...]
    in_map: bool
    combat_loading: bool
    combat_executing: bool
    enemy_searching: bool
    fleet_on_target: bool
    current_fleet_on_target: bool
    hp: Tuple[float, ...] = ()
    levels: Tuple[int, ...] = ()


@dataclass(frozen=True)
class AlasCampaignCombatReplay:
    stage_code: str
    target_node: str
    input_generation: int
    frames: Tuple[AlasCombatReplayFrame, ...]

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.stage_code,
            self.target_node,
            self.input_generation,
            tuple(
                (
                    frame.generation,
                    frame.phase.value,
                    frame.visible_resources,
                    frame.in_map,
                    frame.combat_loading,
                    frame.combat_executing,
                    frame.enemy_searching,
                    frame.fleet_on_target,
                    frame.current_fleet_on_target,
                    frame.hp,
                    frame.levels,
                )
                for frame in self.frames
            ),
        )


@dataclass(frozen=True)
class AlasCampaignCombatStateReplayResult:
    stage_code: str
    target_node: str
    fleet_index: int
    fleet_marker: str
    battle_count_before: int
    battle_count_after: int
    ammo_before: int
    ammo_after: int
    expected_end: str
    auto_mode: str
    submarine_mode: str
    phases: Tuple[str, ...]
    virtual_actions: Tuple[str, ...]
    virtual_sleeps: Tuple[str, ...]
    call_order: Tuple[str, ...]
    resource_queries: Tuple[str, ...]
    hp_after: Tuple[float, ...]
    levels_after: Tuple[int, ...]
    target_enemy_cleared: bool
    target_fleet_present: bool
    projected_map_unchanged: bool


ALAS_COMBAT_REPLAY_PHASES = (
    AlasCombatReplayPhase.BATTLE_PREPARATION,
    AlasCombatReplayPhase.COMBAT_EXECUTING,
    AlasCombatReplayPhase.BATTLE_STATUS,
    AlasCombatReplayPhase.EXP_INFO,
    AlasCombatReplayPhase.MAP_SEARCHING,
    AlasCombatReplayPhase.MAP_STABLE,
)


def alas_combat_replay_phase_sequence(
    *,
    include_automation_confirm: bool = False,
    include_automation_switch: bool = False,
    include_get_items: bool = False,
    include_get_mission: bool = False,
) -> Tuple[AlasCombatReplayPhase, ...]:
    """Return one bounded original-ALAS post-battle input sequence."""

    if (
        not isinstance(include_automation_confirm, bool)
        or not isinstance(include_automation_switch, bool)
        or not isinstance(include_get_items, bool)
        or not isinstance(include_get_mission, bool)
    ):
        raise SemanticGateClosed("combat replay optional phase flags are invalid")
    phases = []
    if include_automation_confirm:
        phases.append(AlasCombatReplayPhase.AUTOMATION_CONFIRM)
    if include_automation_switch:
        phases.append(
            AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF
        )
    phases.extend([
        AlasCombatReplayPhase.BATTLE_PREPARATION,
        AlasCombatReplayPhase.COMBAT_EXECUTING,
        AlasCombatReplayPhase.BATTLE_STATUS,
    ])
    if include_get_items:
        phases.append(AlasCombatReplayPhase.GET_ITEMS)
    phases.append(AlasCombatReplayPhase.EXP_INFO)
    if include_get_mission:
        phases.append(AlasCombatReplayPhase.GET_MISSION)
    phases.extend(
        (
            AlasCombatReplayPhase.MAP_SEARCHING,
            AlasCombatReplayPhase.MAP_STABLE,
        )
    )
    return tuple(phases)


ALAS_COMBAT_REPLAY_PHASE_SEQUENCES = tuple(
    alas_combat_replay_phase_sequence(
        include_automation_confirm=include_automation_confirm,
        include_automation_switch=include_automation_switch,
        include_get_items=include_get_items,
        include_get_mission=include_get_mission,
    )
    for include_automation_confirm in (False, True)
    for include_automation_switch in (False, True)
    for include_get_items in (False, True)
    for include_get_mission in (False, True)
)

ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES: Mapping[
    AlasCombatReplayPhase, Tuple[str, ...]
] = MappingProxyType({
    AlasCombatReplayPhase.AUTOMATION_CONFIRM: (
        "AUTOMATION_CONFIRM",
        "AUTOMATION_CONFIRM_CHECK",
    ),
    AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF: (
        "AUTOMATION_OFF",
        "BATTLE_PREPARATION",
    ),
    AlasCombatReplayPhase.BATTLE_PREPARATION: (
        "AUTOMATION_ON",
        "BATTLE_PREPARATION",
    ),
    AlasCombatReplayPhase.COMBAT_EXECUTING: ("PAUSE",),
    AlasCombatReplayPhase.BATTLE_STATUS: ("BATTLE_STATUS_S",),
    AlasCombatReplayPhase.GET_ITEMS: ("GET_ITEMS_1",),
    AlasCombatReplayPhase.EXP_INFO: ("EXP_INFO_S",),
    AlasCombatReplayPhase.GET_MISSION: ("GET_MISSION",),
    AlasCombatReplayPhase.MAP_SEARCHING: (
        "IN_MAP",
        "MAP_ENEMY_SEARCHING",
    ),
    AlasCombatReplayPhase.MAP_STABLE: ("IN_MAP",),
})

# Exact resource surface reached by the pinned original ALAS ordinary-combat
# chain.  This is intentionally narrower than the defensive allowlist below:
# adding *or removing* a query is upstream control-flow drift that must be
# reviewed before a live Unity mapping can be considered complete.
ALAS_COMBAT_REPLAY_RESOURCE_NAMES = (
    "AUTOMATION_CONFIRM",
    "AUTOMATION_CONFIRM_CHECK",
    "AUTOMATION_OFF",
    "AUTOMATION_ON",
    "AUTO_SEARCH_MENU_EXIT",
    "BATTLE_PREPARATION",
    "BATTLE_STATUS_A",
    "BATTLE_STATUS_B",
    "BATTLE_STATUS_C",
    "BATTLE_STATUS_D",
    "BATTLE_STATUS_S",
    "CAMPAIGN_CHECK",
    "EVENT_CHECK",
    "EXP_INFO_A",
    "EXP_INFO_B",
    "EXP_INFO_S",
    "FLEET_PREPARATION",
    "GAME_TIPS",
    "GAME_TIPS3",
    "GAME_TIPS4",
    "GET_ITEMS_1",
    "GET_ITEMS_2",
    "GET_ITEMS_3",
    "GET_MISSION",
    "GET_SHIP",
    "GUILD_POPUP_CONFIRM",
    "IN_MAP",
    "IN_RETIREMENT_CHECK",
    "MAP_AMBUSH_EVADE",
    "MAP_CAT_ATTACK",
    "MAP_CAT_ATTACK_MIRROR",
    "MAP_ENEMY_SEARCHING",
    "MAP_PREPARATION",
    "MISSION_POPUP_GO",
    "PAUSE",
    "POPUP_CANCEL",
    "POPUP_CONFIRM_WHITE",
    "RETIRE_APPEAR_1",
    "SP_CHECK",
    "STORY_CLOSE",
    "STORY_SKIP_3",
)

# This is a pinned replay allowlist, not a generic false fallback.  Every
# original ALAS presence query made by the qualified chain must be listed.
# A new upstream query closes the replay at final validation.
_PINNED_RESOURCE_QUERY_ALLOWLIST = frozenset(
    {
        "AUTOMATION_CONFIRM",
        "AUTOMATION_CONFIRM_CHECK",
        "AUTOMATION_OFF",
        "AUTOMATION_ON",
        "AUTO_SEARCH_MENU_EXIT",
        "BACK_ARROW",
        "BATTLE_PREPARATION",
        "BATTLE_PREPARATION_WITH_OVERLAY",
        "BATTLE_STATUS_A",
        "BATTLE_STATUS_B",
        "BATTLE_STATUS_C",
        "BATTLE_STATUS_D",
        "BATTLE_STATUS_S",
        "CAMPAIGN_CHECK",
        "DAILY_CHECK",
        "EMERGENCY_REPAIR_CONFIRM",
        "EVENT_CHECK",
        "EXP_INFO_A",
        "EXP_INFO_B",
        "EXP_INFO_S",
        "FLEET_PREPARATION",
        "GAME_TIPS",
        "GAME_TIPS3",
        "GAME_TIPS4",
        "GET_AMMO",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "GET_SHIP",
        "GET_ITEMS_SHIP_1",
        "GET_MISSION",
        "GUILD_POPUP_CANCEL",
        "GUILD_POPUP_CONFIRM",
        "IN_MAP",
        "IN_RETIREMENT_CHECK",
        "MAP_CAT_ATTACK",
        "MAP_CAT_ATTACK_MIRROR",
        "MAP_AMBUSH_EVADE",
        "MAP_ENEMY_SEARCHING",
        "MAP_PREPARATION",
        "MISSION_POPUP_ACK",
        "MISSION_POPUP_GO",
        "MUNITIONS_CHECK",
        "NEW_SHIP",
        "PAUSE",
        "POPUP_CANCEL",
        "POPUP_CONFIRM",
        "POPUP_CONFIRM_WHITE",
        "RETIRE_APPEAR_1",
        "SP_CHECK",
        "STORY_CLOSE",
        "STORY_SKIP_3",
    }
)

_MUTABLE_TIMER_FIELDS = (
    "_automation_set_timer",
    "_get_ammo_log_timer",
    "_story_confirm",
    "_story_option_confirm",
    "_story_option_timer",
    "auto_click_interval_timer",
    "auto_mode_click_timer",
    "auto_skip_timer",
    "in_stage_timer",
    "map_cat_attack_timer",
    "story_popup_timeout",
    "submarine_call_click_timer",
    "submarine_call_timer",
)


def _expected_resource_query_names(
    replay: AlasCampaignCombatReplay,
) -> frozenset[str]:
    expected = set(ALAS_COMBAT_REPLAY_RESOURCE_NAMES)
    if not any(
        frame.phase is AlasCombatReplayPhase.AUTOMATION_CONFIRM
        for frame in replay.frames
    ):
        expected.discard("AUTOMATION_CONFIRM")
    if not any(
        frame.phase is AlasCombatReplayPhase.GET_MISSION
        for frame in replay.frames
    ):
        # These fallbacks are short-circuited by EXP_INFO_S on the base path.
        expected.difference_update(("EXP_INFO_A", "EXP_INFO_B"))
    return frozenset(expected)


def canonical_alas_campaign_combat_replay(
    admission: AlasCampaignCombatAdmission,
    *,
    include_automation_confirm: bool = False,
    include_automation_switch: bool = False,
    include_get_items: bool = False,
    include_get_mission: bool = False,
) -> AlasCampaignCombatReplay:
    """Build one of the sixteen bounded ordinary-combat replay sequences."""

    if not isinstance(admission, AlasCampaignCombatAdmission):
        raise SemanticGateClosed("combat replay requires an admission")
    base = admission.input_generation
    phases = alas_combat_replay_phase_sequence(
        include_automation_confirm=include_automation_confirm,
        include_automation_switch=include_automation_switch,
        include_get_items=include_get_items,
        include_get_mission=include_get_mission,
    )
    frames = tuple(
        AlasCombatReplayFrame(
            generation=base + offset,
            phase=phase,
            visible_resources=ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES[phase],
            in_map=phase
            in (
                AlasCombatReplayPhase.MAP_SEARCHING,
                AlasCombatReplayPhase.MAP_STABLE,
            ),
            combat_loading=phase
            in (
                AlasCombatReplayPhase.AUTOMATION_CONFIRM,
                AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF,
                AlasCombatReplayPhase.BATTLE_PREPARATION,
            ),
            combat_executing=phase
            is AlasCombatReplayPhase.COMBAT_EXECUTING,
            enemy_searching=phase is AlasCombatReplayPhase.MAP_SEARCHING,
            fleet_on_target=phase
            in (
                AlasCombatReplayPhase.MAP_SEARCHING,
                AlasCombatReplayPhase.MAP_STABLE,
            ),
            current_fleet_on_target=phase
            in (
                AlasCombatReplayPhase.MAP_SEARCHING,
                AlasCombatReplayPhase.MAP_STABLE,
            ),
            hp=(1.0,) * 6
            if phase is AlasCombatReplayPhase.MAP_STABLE
            else (),
            levels=(-1,) * 6
            if phase is AlasCombatReplayPhase.MAP_STABLE
            else (),
        )
        for offset, phase in enumerate(phases, start=1)
    )
    return AlasCampaignCombatReplay(
        stage_code=admission.stage_code,
        target_node=admission.target_node,
        input_generation=admission.input_generation,
        frames=frames,
    )


def _validate_replay(
    replay: AlasCampaignCombatReplay,
    admission: AlasCampaignCombatAdmission,
) -> None:
    if not isinstance(replay, AlasCampaignCombatReplay):
        raise SemanticGateClosed("combat replay input is not typed")
    if (
        replay.stage_code != admission.stage_code
        or replay.target_node != admission.target_node
        or replay.input_generation != admission.input_generation
    ):
        raise SemanticGateClosed("combat replay identity changed")
    phase_order = tuple(frame.phase for frame in replay.frames)
    if phase_order not in ALAS_COMBAT_REPLAY_PHASE_SEQUENCES:
        raise SemanticGateClosed("combat replay phase order changed")
    generations = tuple(frame.generation for frame in replay.frames)
    if (
        any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in generations
        )
        or generations[0] <= admission.input_generation
        or any(right <= left for left, right in zip(generations, generations[1:]))
    ):
        raise SemanticGateClosed("combat replay generations are not increasing")
    for frame in replay.frames:
        if (
            tuple(sorted(frame.visible_resources))
            != tuple(sorted(ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES[frame.phase]))
        ):
            raise SemanticGateClosed("combat replay visible resources changed")
        expected_flags = {
            AlasCombatReplayPhase.AUTOMATION_CONFIRM: (
                False,
                True,
                False,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF: (
                False,
                True,
                False,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.BATTLE_PREPARATION: (
                False,
                True,
                False,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.COMBAT_EXECUTING: (
                False,
                False,
                True,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.BATTLE_STATUS: (
                False,
                False,
                False,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.GET_ITEMS: (
                False,
                False,
                False,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.EXP_INFO: (
                False,
                False,
                False,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.GET_MISSION: (
                False,
                False,
                False,
                False,
                False,
                False,
            ),
            AlasCombatReplayPhase.MAP_SEARCHING: (
                True,
                False,
                False,
                True,
                True,
                True,
            ),
            AlasCombatReplayPhase.MAP_STABLE: (
                True,
                False,
                False,
                False,
                True,
                True,
            ),
        }[frame.phase]
        actual_flags = (
            frame.in_map,
            frame.combat_loading,
            frame.combat_executing,
            frame.enemy_searching,
            frame.fleet_on_target,
            frame.current_fleet_on_target,
        )
        if actual_flags != expected_flags:
            raise SemanticGateClosed("combat replay phase flags changed")
        if frame.phase is not AlasCombatReplayPhase.MAP_STABLE and (
            frame.hp or frame.levels
        ):
            raise SemanticGateClosed("combat replay stats appeared too early")
    final = replay.frames[-1]
    if (
        len(final.hp) != 6
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0.0 <= float(value) <= 1.0
            for value in final.hp
        )
        or len(final.levels) != 6
        or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in final.levels
        )
    ):
        raise SemanticGateClosed("combat replay final fleet stats are invalid")


class _ReplayImage:
    pass


class _ReplayDriver:
    def __init__(
        self,
        replay: AlasCampaignCombatReplay,
        admission: AlasCampaignCombatAdmission,
        grid: _SemanticGotoGrid,
        target_location: Tuple[int, int],
    ) -> None:
        self.replay = replay
        self.admission = admission
        self.grid = grid
        self.target_location = target_location
        self.index = -1
        self.section = "goto"
        self.searching_screenshots = 0
        self.image = _ReplayImage()
        self.virtual_actions: list[str] = []
        self.call_order: list[str] = []
        self.resource_queries: list[str] = []
        self.sleep_calls: list[str] = []

    @property
    def frame(self) -> AlasCombatReplayFrame:
        if not 0 <= self.index < len(self.replay.frames):
            raise SemanticGateClosed("combat replay has no current frame")
        return self.replay.frames[self.index]

    def advance(self, expected: AlasCombatReplayPhase) -> None:
        next_index = self.index + 1
        if next_index >= len(self.replay.frames):
            raise SemanticGateClosed("combat replay advanced past its final frame")
        if self.replay.frames[next_index].phase is not expected:
            raise SemanticGateClosed("combat replay transition changed")
        self.index = next_index

    def next_phase(self) -> AlasCombatReplayPhase:
        next_index = self.index + 1
        if next_index >= len(self.replay.frames):
            raise SemanticGateClosed("combat replay has no next phase")
        return self.replay.frames[next_index].phase

    def query(self, name: str) -> bool:
        self.resource_queries.append(name)
        return name in self.frame.visible_resources

    def click(self, button: Any) -> None:
        annotation = getattr(button, "__str__", None)
        if button is self.grid and annotation == self.target_location:
            if self.index != -1:
                raise SemanticGateClosed(
                    "combat replay repeated the campaign grid input"
                )
            if (
                getattr(button, "semantic_path", None)
                != self.admission.cell_path
                or getattr(button, "semantic_point", None)
                != self.admission.point
                or getattr(button, "semantic_bounds", None)
                != self.admission.bounds
            ):
                raise SemanticGateClosed(
                    "combat replay campaign grid geometry changed"
                )
            self.virtual_actions.append("campaign_grid:" + self.admission.target_node)
            self.call_order.append("device.click(grid)")
            self.advance(self.replay.frames[0].phase)
            return
        name = getattr(button, "name", None)
        transitions = {
            AlasCombatReplayPhase.AUTOMATION_CONFIRM: "AUTOMATION_CONFIRM",
            AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF: (
                "AUTOMATION_SWITCH"
            ),
            AlasCombatReplayPhase.BATTLE_PREPARATION: "BATTLE_PREPARATION",
            AlasCombatReplayPhase.BATTLE_STATUS: "BATTLE_STATUS_S",
            AlasCombatReplayPhase.GET_ITEMS: "GET_ITEMS_1",
            AlasCombatReplayPhase.EXP_INFO: "EXP_INFO_S",
            AlasCombatReplayPhase.GET_MISSION: "GET_MISSION",
        }
        transition = transitions.get(self.frame.phase)
        visible_action_state = (
            "AUTOMATION_OFF"
            if self.frame.phase
            is AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF
            else name
        )
        if (
            transition is None
            or name != transition
            or visible_action_state not in self.frame.visible_resources
        ):
            raise SemanticGateClosed(
                "combat replay attempted an unexpected virtual input: "
                + str(name)
            )
        self.virtual_actions.append(name)
        self.call_order.append("device.click(" + name + ")")
        self.advance(self.next_phase())

    def screenshot(self) -> None:
        self.call_order.append("device.screenshot:" + self.section)
        if (
            self.section == "combat_execute"
            and self.frame.phase is AlasCombatReplayPhase.COMBAT_EXECUTING
        ):
            self.advance(AlasCombatReplayPhase.BATTLE_STATUS)
            return
        if (
            self.section == "combat_status"
            and self.frame.phase is AlasCombatReplayPhase.MAP_SEARCHING
        ):
            self.searching_screenshots += 1
            if self.searching_screenshots >= 3:
                self.advance(AlasCombatReplayPhase.MAP_STABLE)

    def sleep(self, duration: Any) -> None:
        self.sleep_calls.append(str(duration))

    def validate_complete(self) -> None:
        if self.frame.phase is not AlasCombatReplayPhase.MAP_STABLE:
            raise SemanticGateClosed("combat replay did not reach the stable map")
        action_by_phase = {
            AlasCombatReplayPhase.AUTOMATION_CONFIRM: "AUTOMATION_CONFIRM",
            AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF: (
                "AUTOMATION_SWITCH"
            ),
            AlasCombatReplayPhase.BATTLE_PREPARATION: "BATTLE_PREPARATION",
            AlasCombatReplayPhase.BATTLE_STATUS: "BATTLE_STATUS_S",
            AlasCombatReplayPhase.GET_ITEMS: "GET_ITEMS_1",
            AlasCombatReplayPhase.EXP_INFO: "EXP_INFO_S",
            AlasCombatReplayPhase.GET_MISSION: "GET_MISSION",
        }
        expected_actions = (
            "campaign_grid:" + self.admission.target_node,
            *(
                action_by_phase[frame.phase]
                for frame in self.replay.frames
                if frame.phase in action_by_phase
            ),
        )
        if tuple(self.virtual_actions) != expected_actions:
            raise SemanticGateClosed("combat replay virtual action order changed")
        expected_sleeps = (
            (("1",) if any(
                frame.phase
                is AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF
                for frame in self.replay.frames
            ) else ())
            + ("(0.25, 0.5)", "(0.25, 0.5)", "1.2", "0.3")
        )
        if tuple(self.sleep_calls) != expected_sleeps:
            raise SemanticGateClosed("combat replay virtual sleep order changed")
        unknown = set(self.resource_queries) - _PINNED_RESOURCE_QUERY_ALLOWLIST
        if unknown:
            raise SemanticGateClosed(
                "combat replay queried unmapped resources: "
                + ", ".join(sorted(unknown))
            )
        observed = set(self.resource_queries)
        expected = set(_expected_resource_query_names(self.replay))
        if observed != expected:
            raise SemanticGateClosed(
                "combat replay resource query surface changed; missing={0}; "
                "unexpected={1}".format(
                    ",".join(sorted(expected - observed)),
                    ",".join(sorted(observed - expected)),
                )
            )


class _ReplayDevice:
    semantic_adapter = None

    def __init__(self, driver: _ReplayDriver) -> None:
        self._driver = driver

    @property
    def image(self) -> _ReplayImage:
        return self._driver.image

    def click(self, button: Any) -> None:
        self._driver.click(button)

    def screenshot(self) -> None:
        self._driver.screenshot()

    def sleep(self, duration: Any) -> None:
        self._driver.sleep(duration)

    def stuck_record_clear(self) -> None:
        pass

    def click_record_clear(self) -> None:
        pass

    def screenshot_interval_set(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def __getattr__(self, name: str) -> Any:
        raise SemanticGateClosed(
            "combat replay attempted unsupported Device access: " + name
        )


class _ReplayView(_SemanticGotoView):
    def __init__(self, grid: _SemanticGotoGrid, driver: _ReplayDriver) -> None:
        super().__init__(grid)
        self._driver = driver

    def update(self, image: Any) -> None:
        if image is not self._driver.image:
            raise SemanticGateClosed("combat replay view image changed")


class _NullDropContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        del exc_type, exc, traceback
        return False


class _NullStat:
    def new(self, *args: Any, **kwargs: Any) -> _NullDropContext:
        del args, kwargs
        return _NullDropContext()


def _config_gate(campaign: Any) -> None:
    config = campaign.config
    required = {
        "Campaign_UseFleetLock": True,
        "Emotion_Mode": "calculate",
        "HpControl_UseHpBalance": False,
        "MAP_HAS_FLEET_STEP": False,
        "MAP_HAS_LAND_BASED": False,
        "MAP_HAS_MAZE": False,
        "MAP_HAS_MOVABLE_ENEMY": False,
        "MAP_MYSTERY_HAS_CARRIER": False,
        "MAP_FOCUS_ENEMY_AFTER_BATTLE": False,
        "STOP_IF_REACH_LV32": False,
        "StopCondition_ReachLevel": 0,
        "Submarine_Fleet": 0,
        "Submarine_Mode": "do_not_use",
    }
    for name, expected in required.items():
        if getattr(config, name, None) != expected:
            raise SemanticGateClosed(
                "combat replay configuration is outside pinned slice: " + name
            )
    if getattr(config, "Fleet_Fleet1Mode", None) != "combat_auto":
        raise SemanticGateClosed("combat replay requires fleet 1 combat auto")


def replay_alas_campaign_combat_state_machine(
    campaign: Any,
    projection: AlasCampaignMapProjection,
    decision: AlasCampaignDecisionPreview,
    admission: AlasCampaignCombatAdmission,
    state: CampaignMapState,
    replay: AlasCampaignCombatReplay,
) -> AlasCampaignCombatStateReplayResult:
    """Run the pinned original ALAS combat chain with virtual typed inputs."""

    target_location = _validate_inputs(
        campaign, projection, decision, admission, state
    )
    _validate_replay(replay, admission)
    _config_gate(campaign)
    required = (
        "_goto",
        "combat",
        "combat_preparation",
        "combat_execute",
        "combat_status",
        "combat_appear",
        "hp_retreat_triggered",
        "fleet_ensure",
        "in_sight",
        "focus_to_grid_center",
        "convert_global_to_local",
        "ambush_color_initial",
        "enemy_searching_color_initial",
        "find_path_initial",
    )
    if any(not callable(getattr(campaign, name, None)) for name in required):
        raise SemanticGateClosed("combat replay campaign interface is incomplete")

    sandbox = copy.copy(campaign)
    sandbox.__dict__ = campaign.__dict__.copy()
    sandbox.config = _copy_config(campaign.config)
    sandbox.interval_timer = {}
    timer_snapshots = {}
    for name in _MUTABLE_TIMER_FIELDS:
        value = getattr(campaign, name, None)
        if value is not None:
            timer_snapshots[name] = copy.deepcopy(getattr(value, "__dict__", {}))
            setattr(sandbox, name, copy.deepcopy(value))
    sandbox.camera = target_location
    sandbox.fleet_submarine_location = getattr(
        campaign, "fleet_submarine_location", ()
    )
    sandbox.fleet_ammo = admission.ammo_before
    sandbox.stat = _NullStat()
    emotion = _decision_emotion(sandbox)

    grid = _SemanticGotoGrid(
        location=(3, 2),
        path=admission.cell_path,
        point=admission.point,
        bounds=admission.bounds,
    )
    grid.may_boss = False
    driver = _ReplayDriver(replay, admission, grid, target_location)
    grid.predict_fleet = lambda: driver.frame.fleet_on_target
    grid.predict_current_fleet = lambda: driver.frame.current_fleet_on_target
    sandbox.view = _ReplayView(grid, driver)
    sandbox.device = _ReplayDevice(driver)

    original_hp_retreat = sandbox.hp_retreat_triggered
    original_in_sight = sandbox.in_sight
    original_focus_center = sandbox.focus_to_grid_center
    original_convert = sandbox.convert_global_to_local
    original_enemy_searching = sandbox.enemy_searching_color_initial
    original_combat_appear = sandbox.combat_appear
    original_combat = sandbox.combat
    original_combat_preparation = sandbox.combat_preparation
    original_combat_execute = sandbox.combat_execute
    original_combat_status = sandbox.combat_status
    original_find_path_initial = sandbox.find_path_initial

    def hp_retreat(self: Any) -> bool:
        del self
        driver.call_order.append("hp_retreat_triggered")
        return bool(original_hp_retreat())

    def fleet_set(
        self: Any, index: Any = None, skip_first_screenshot: bool = True
    ) -> bool:
        del self, skip_first_screenshot
        driver.call_order.append("fleet_set")
        if index != admission.fleet_index:
            raise SemanticGateClosed("combat replay requested another fleet")
        return False

    expected_sight = tuple(int(value) for value in sandbox._walk_sight)

    def in_sight(self: Any, location: Any, sight: Any = None) -> Any:
        del self
        driver.call_order.append("in_sight")
        if (
            _location_tuple(location) != target_location
            or tuple(int(value) for value in sight) != expected_sight
        ):
            raise SemanticGateClosed("combat replay visibility input changed")
        result = original_in_sight(location, sight=sight)
        if _location_tuple(sandbox.camera) != target_location:
            raise SemanticGateClosed("combat replay attempted a camera move")
        return result

    def focus_to_grid_center(self: Any, tolerance: Any = None) -> Any:
        del self
        driver.call_order.append("focus_to_grid_center")
        result = original_focus_center(tolerance=tolerance)
        if result not in (False, None):
            raise SemanticGateClosed("combat replay attempted a centering swipe")
        return result

    def convert_global_to_local(self: Any, location: Any) -> Any:
        del self
        driver.call_order.append("convert_global_to_local")
        if _location_tuple(location) != target_location:
            raise SemanticGateClosed("combat replay conversion target changed")
        result = original_convert(location)
        if result is not grid:
            raise SemanticGateClosed("combat replay local grid changed")
        return result

    def ambush_color_initial(self: Any) -> None:
        del self
        driver.call_order.append("ambush_color_initial")

    def enemy_searching_color_initial(self: Any) -> Any:
        del self
        driver.call_order.append("enemy_searching_color_initial")
        return original_enemy_searching()

    def appear(self: Any, button: Any, *args: Any, **kwargs: Any) -> bool:
        del self, args, kwargs
        name = getattr(button, "name", None)
        if not isinstance(name, str):
            raise SemanticGateClosed("combat replay queried an unnamed resource")
        return driver.query(name)

    def is_in_map(self: Any) -> bool:
        del self
        driver.call_order.append("is_in_map:" + driver.frame.phase.value)
        driver.resource_queries.append("IN_MAP")
        return driver.frame.in_map

    def is_combat_loading(self: Any) -> bool:
        del self
        driver.call_order.append("is_combat_loading")
        return driver.frame.combat_loading

    def is_combat_executing(self: Any) -> Any:
        del self
        driver.call_order.append("is_combat_executing")
        driver.resource_queries.append("PAUSE")
        return "PAUSE" if driver.frame.combat_executing else False

    def enemy_searching_appear(self: Any) -> bool:
        del self
        driver.call_order.append("enemy_searching_appear")
        driver.resource_queries.append("MAP_ENEMY_SEARCHING")
        return driver.frame.enemy_searching

    def combat_appear(self: Any) -> bool:
        del self
        driver.call_order.append("combat_appear")
        return bool(original_combat_appear())

    def combat(self: Any, *args: Any, **kwargs: Any) -> Any:
        del self
        driver.call_order.append("combat")
        if args or (
            kwargs.get("expected_end") != "with_searching"
            or kwargs.get("fleet_index") != admission.fleet_index
            or kwargs.get("submarine_mode") is not None
        ):
            raise SemanticGateClosed("combat replay dispatch arguments changed")
        driver.section = "combat"
        return original_combat(*args, **kwargs)

    def combat_preparation(self: Any, *args: Any, **kwargs: Any) -> Any:
        del self
        driver.call_order.append("combat_preparation")
        if args or kwargs != {
            "balance_hp": False,
            "emotion_reduce": True,
            "auto": "combat_auto",
            "fleet_index": admission.fleet_index,
        }:
            raise SemanticGateClosed(
                "combat replay preparation arguments changed"
            )
        driver.section = "combat_preparation"
        return original_combat_preparation(*args, **kwargs)

    def combat_execute(self: Any, *args: Any, **kwargs: Any) -> Any:
        del self
        driver.call_order.append("combat_execute")
        if args or kwargs != {
            "auto": "combat_auto",
            "submarine": "do_not_use",
            "drop": None,
        }:
            raise SemanticGateClosed("combat replay execute arguments changed")
        driver.section = "combat_execute"
        return original_combat_execute(*args, **kwargs)

    def combat_status(self: Any, *args: Any, **kwargs: Any) -> Any:
        del self
        driver.call_order.append("combat_status")
        if args or kwargs != {"drop": None, "expected_end": "with_searching"}:
            raise SemanticGateClosed("combat replay status arguments changed")
        driver.section = "combat_status"
        return original_combat_status(*args, **kwargs)

    def hp_get(self: Any) -> list[float]:
        del self
        driver.call_order.append("hp_get")
        hp = [float(value) for value in driver.frame.hp]
        sandbox.hp = hp
        return hp

    def lv_get(self: Any, after_battle: bool = False) -> list[int]:
        del self
        driver.call_order.append("lv_get:" + str(bool(after_battle)))
        levels = [int(value) for value in driver.frame.levels]
        sandbox.lv = levels
        return levels

    def image_color_count(
        self: Any, button: Any, *args: Any, **kwargs: Any
    ) -> bool:
        del self, args, kwargs
        name = getattr(button, "name", None)
        if not isinstance(name, str):
            raise SemanticGateClosed("combat replay color query is unnamed")
        driver.resource_queries.append(name)
        return False

    def false_air_raid(self: Any) -> bool:
        del self
        driver.call_order.append("air_raid_appear:false")
        return False

    def false_ambush(self: Any) -> bool:
        del self
        driver.call_order.append("ambush_appear:false")
        return False

    def info_bar_count(self: Any) -> int:
        del self
        driver.call_order.append("info_bar_count:0")
        return 0

    def is_story_black(self: Any) -> bool:
        del self
        driver.call_order.append("story_black:false")
        return False

    def predict(self: Any) -> None:
        del self
        driver.call_order.append("predict:semantic_map_stable")

    def find_path_initial(self: Any) -> Any:
        del self
        driver.call_order.append("find_path_initial")
        return original_find_path_initial()

    sandbox.hp_retreat_triggered = MethodType(hp_retreat, sandbox)
    sandbox.fleet_set = MethodType(fleet_set, sandbox)
    sandbox.in_sight = MethodType(in_sight, sandbox)
    sandbox.focus_to_grid_center = MethodType(focus_to_grid_center, sandbox)
    sandbox.convert_global_to_local = MethodType(
        convert_global_to_local, sandbox
    )
    sandbox.ambush_color_initial = MethodType(ambush_color_initial, sandbox)
    sandbox.enemy_searching_color_initial = MethodType(
        enemy_searching_color_initial, sandbox
    )
    sandbox.appear = MethodType(appear, sandbox)
    sandbox.is_in_map = MethodType(is_in_map, sandbox)
    sandbox.is_combat_loading = MethodType(is_combat_loading, sandbox)
    sandbox.is_combat_executing = MethodType(is_combat_executing, sandbox)
    sandbox.enemy_searching_appear = MethodType(
        enemy_searching_appear, sandbox
    )
    sandbox.combat_appear = MethodType(combat_appear, sandbox)
    sandbox.combat = MethodType(combat, sandbox)
    sandbox.combat_preparation = MethodType(combat_preparation, sandbox)
    sandbox.combat_execute = MethodType(combat_execute, sandbox)
    sandbox.combat_status = MethodType(combat_status, sandbox)
    sandbox.hp_get = MethodType(hp_get, sandbox)
    sandbox.lv_get = MethodType(lv_get, sandbox)
    sandbox.image_color_count = MethodType(image_color_count, sandbox)
    sandbox._air_raid_appear = MethodType(false_air_raid, sandbox)
    sandbox._ambush_appear = MethodType(false_ambush, sandbox)
    sandbox.info_bar_count = MethodType(info_bar_count, sandbox)
    sandbox._is_story_black = MethodType(is_story_black, sandbox)
    sandbox.predict = MethodType(predict, sandbox)
    sandbox.find_path_initial = MethodType(find_path_initial, sandbox)
    sandbox.withdraw = MethodType(_blocked_method("withdraw"), sandbox)

    projected_before = tuple(
        (tuple(grid_info.location), grid_info.__dict__.copy())
        for grid_info in campaign.map
    )
    projected_map = copy.deepcopy(campaign.map)
    with _DECISION_LOCK, _native_map_overlay(
        campaign.MAP, projected_map
    ) as native_map, _reject_emotion_sleep(emotion):
        sandbox.map = native_map
        try:
            sandbox._goto(target_location, expected=decision.expected)
        except SemanticGateClosed:
            raise
        except Exception as exc:
            raise SemanticGateClosed(
                "original ALAS combat replay failed: "
                + type(exc).__name__
                + ": "
                + str(exc)
            ) from exc

        driver.validate_complete()
        target = native_map[target_location]
        if (
            sandbox.battle_count != admission.battle_count + 1
            or sandbox.fleet_ammo != admission.ammo_before - 1
            or tuple(sandbox.fleet_current) != target_location
            or bool(target.is_enemy)
            or not bool(target.is_fleet)
        ):
            raise SemanticGateClosed(
                "original ALAS combat replay post-state changed"
            )
        unknown = set(driver.resource_queries) - _PINNED_RESOURCE_QUERY_ALLOWLIST
        if unknown:
            raise SemanticGateClosed(
                "combat replay queried unmapped resources: "
                + ", ".join(sorted(unknown))
            )
        observed = set(driver.resource_queries)
        expected = set(_expected_resource_query_names(replay))
        if observed != expected:
            raise SemanticGateClosed(
                "combat replay resource query surface changed; missing={0}; "
                "unexpected={1}".format(
                    ",".join(sorted(expected - observed)),
                    ",".join(sorted(observed - expected)),
                )
            )
        expected_end = sandbox._expected_end(decision.expected)
        auto_mode = sandbox.config.Fleet_Fleet1Mode
        submarine_mode = "do_not_use"
        result = AlasCampaignCombatStateReplayResult(
            stage_code=admission.stage_code,
            target_node=admission.target_node,
            fleet_index=admission.fleet_index,
            fleet_marker=admission.fleet_marker,
            battle_count_before=admission.battle_count,
            battle_count_after=sandbox.battle_count,
            ammo_before=admission.ammo_before,
            ammo_after=sandbox.fleet_ammo,
            expected_end=str(expected_end),
            auto_mode=str(auto_mode),
            submarine_mode=submarine_mode,
            phases=tuple(frame.phase.value for frame in replay.frames),
            virtual_actions=tuple(driver.virtual_actions),
            virtual_sleeps=tuple(driver.sleep_calls),
            call_order=tuple(driver.call_order),
            resource_queries=tuple(driver.resource_queries),
            hp_after=tuple(float(value) for value in sandbox.hp),
            levels_after=tuple(int(value) for value in sandbox.lv),
            target_enemy_cleared=not bool(target.is_enemy),
            target_fleet_present=bool(target.is_fleet),
            projected_map_unchanged=(
                projected_before
                == tuple(
                    (tuple(grid_info.location), grid_info.__dict__.copy())
                    for grid_info in campaign.map
                )
            ),
        )
    for name, snapshot in timer_snapshots.items():
        if getattr(getattr(campaign, name), "__dict__", {}) != snapshot:
            raise SemanticGateClosed(
                "combat replay mutated shared timer state: " + name
            )
    return result
