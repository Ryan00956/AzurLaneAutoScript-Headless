"""Device-free replay of original-ALAS defensive combat branches.

The ordinary G19 replay proves the common combat loop.  This module exercises
the source methods behind rare result grades, contextual popups, retirement,
story, and ambush handling on isolated object copies.  It records ALAS's own
query and click order without importing a replacement state machine or using
Android input.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from types import MethodType
from typing import Any, Mapping, Tuple

from .alas_combat_state_replay import (
    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES,
    ALAS_COMBAT_RESOURCE_ACTION_TARGETS,
)
from .alas_decision_preview import _copy_config
from .semantic_oracle import SemanticGateClosed


ALAS_COMBAT_BRANCH_REPLAY_SCHEMA = (
    "alas-headless.g28-combat-defensive-branch-replay/v1"
)
ALAS_COMBAT_BRANCH_REPLAY_VERIFICATION_SCHEMA = (
    "alas-headless.g28-combat-defensive-branch-replay-verification/v1"
)
ALAS_COMBAT_BRANCH_SOURCE_FILES = (
    "module/combat/combat.py",
    "module/handler/info_handler.py",
    "module/handler/ambush.py",
    "module/retire/retirement.py",
)
_SOURCE_METHODS = {
    "handle_battle_status": "module.combat.combat.Combat.handle_battle_status",
    "handle_exp_info": "module.combat.combat.Combat.handle_exp_info",
    "handle_guild_popup_confirm": (
        "module.handler.info_handler.InfoHandler.handle_guild_popup_confirm"
    ),
    "handle_guild_popup_cancel": (
        "module.handler.info_handler.InfoHandler.handle_guild_popup_cancel"
    ),
    "handle_mission_popup_go": (
        "module.handler.info_handler.InfoHandler.handle_mission_popup_go"
    ),
    "handle_mission_popup_ack": (
        "module.handler.info_handler.InfoHandler.handle_mission_popup_ack"
    ),
    "handle_retirement": "module.retire.retirement.Retirement.handle_retirement",
    "story_skip": "module.handler.info_handler.InfoHandler.story_skip",
    "handle_ambush": "module.handler.ambush.AmbushHandler.handle_ambush",
}


@dataclass(frozen=True)
class AlasCombatBranchReplayScenario:
    name: str
    source_method: str
    returned: bool
    resource_queries: Tuple[str, ...]
    virtual_actions: Tuple[str, ...]
    virtual_sleeps: Tuple[str, ...]
    call_order: Tuple[str, ...]


@dataclass(frozen=True)
class AlasCombatBranchReplayResult:
    scenarios: Tuple[AlasCombatBranchReplayScenario, ...]
    source_restored: bool
    input_injected: bool = False

    @property
    def passed(self) -> bool:
        return bool(self.scenarios) and self.source_restored and not self.input_injected


@dataclass(frozen=True)
class _ScenarioSpec:
    name: str
    method: str
    visible_resources: Tuple[str, ...]
    expected_queries: Tuple[str, ...]
    expected_actions: Tuple[str, ...]
    expected_sleeps: Tuple[str, ...] = ()
    expected_return: bool = True
    setup: str = "common"


_SCENARIOS = (
    _ScenarioSpec(
        "battle-status-a",
        "handle_battle_status",
        ("BATTLE_STATUS_A",),
        ("PAUSE", "BATTLE_STATUS_S", "BATTLE_STATUS_A"),
        ("BATTLE_STATUS_A",),
        ("(0.25, 0.5)",),
    ),
    _ScenarioSpec(
        "battle-status-b",
        "handle_battle_status",
        ("BATTLE_STATUS_B",),
        ("PAUSE", "BATTLE_STATUS_S", "BATTLE_STATUS_A", "BATTLE_STATUS_B"),
        ("BATTLE_STATUS_B",),
        ("(0.25, 0.5)",),
    ),
    _ScenarioSpec(
        "battle-status-c",
        "handle_battle_status",
        ("BATTLE_STATUS_C",),
        (
            "PAUSE",
            "BATTLE_STATUS_S",
            "BATTLE_STATUS_A",
            "BATTLE_STATUS_B",
            "BATTLE_STATUS_C",
        ),
        ("BATTLE_STATUS_C",),
        ("(0.25, 0.5)",),
    ),
    _ScenarioSpec(
        "battle-status-d",
        "handle_battle_status",
        ("BATTLE_STATUS_D",),
        (
            "PAUSE",
            "BATTLE_STATUS_S",
            "BATTLE_STATUS_A",
            "BATTLE_STATUS_B",
            "BATTLE_STATUS_C",
            "BATTLE_STATUS_D",
        ),
        ("BATTLE_STATUS_D",),
        ("(0.25, 0.5)",),
    ),
    _ScenarioSpec(
        "exp-info-a",
        "handle_exp_info",
        ("EXP_INFO_A",),
        ("PAUSE", "EXP_INFO_S", "EXP_INFO_A"),
        ("EXP_INFO_A",),
        ("(0.25, 0.5)",),
    ),
    _ScenarioSpec(
        "exp-info-b",
        "handle_exp_info",
        ("EXP_INFO_B",),
        ("PAUSE", "EXP_INFO_S", "EXP_INFO_A", "EXP_INFO_B"),
        ("EXP_INFO_B",),
        ("(0.25, 0.5)",),
    ),
    _ScenarioSpec(
        "guild-popup-confirm",
        "handle_guild_popup_confirm",
        ("GUILD_POPUP_CANCEL", "GUILD_POPUP_CONFIRM"),
        ("GUILD_POPUP_CANCEL", "GUILD_POPUP_CONFIRM"),
        ("GUILD_POPUP_CONFIRM",),
    ),
    _ScenarioSpec(
        "guild-popup-cancel",
        "handle_guild_popup_cancel",
        ("GUILD_POPUP_CANCEL", "GUILD_POPUP_CONFIRM"),
        ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"),
        ("GUILD_POPUP_CANCEL",),
    ),
    _ScenarioSpec(
        "mission-popup-go",
        "handle_mission_popup_go",
        ("MISSION_POPUP_ACK", "MISSION_POPUP_GO"),
        ("MISSION_POPUP_ACK", "MISSION_POPUP_GO"),
        ("MISSION_POPUP_GO",),
    ),
    _ScenarioSpec(
        "mission-popup-ack",
        "handle_mission_popup_ack",
        ("MISSION_POPUP_ACK", "MISSION_POPUP_GO"),
        ("MISSION_POPUP_GO", "MISSION_POPUP_ACK"),
        ("MISSION_POPUP_ACK",),
    ),
    _ScenarioSpec(
        "retirement-entry",
        "handle_retirement",
        ("RETIRE_APPEAR_1",),
        ("RETIRE_APPEAR_1",),
        ("RETIRE_APPEAR_1",),
        expected_return=False,
        setup="retirement",
    ),
    _ScenarioSpec(
        "retirement-dispatch",
        "handle_retirement",
        ("IN_RETIREMENT_CHECK",),
        ("RETIRE_APPEAR_1", "IN_RETIREMENT_CHECK"),
        (),
        setup="retirement",
    ),
    _ScenarioSpec(
        "story-letters-only",
        "story_skip",
        ("STORY_LETTERS_ONLY",),
        ("STORY_LETTERS_ONLY",),
        ("STORY_LETTERS_ONLY",),
        setup="story-black",
    ),
    _ScenarioSpec(
        "story-skip",
        "story_skip",
        ("STORY_SKIP_3",),
        ("STORY_SKIP_3",),
        ("STORY_SKIP",),
        setup="story",
    ),
    _ScenarioSpec(
        "story-close",
        "story_skip",
        ("STORY_CLOSE",),
        ("STORY_SKIP_3", "STORY_CLOSE"),
        ("STORY_CLOSE",),
        setup="story",
    ),
    _ScenarioSpec(
        "ambush-evade-success",
        "handle_ambush",
        ("MAP_AMBUSH_EVADE",),
        (
            "MAP_AMBUSH_EVADE",
            "MAP_AMBUSH_EVADE",
            "MAP_AMBUSH_EVADE",
        ),
        ("MAP_AMBUSH_EVADE",),
        expected_return=False,
        setup="ambush",
    ),
)


def _button_name(button: Any) -> str:
    name = getattr(button, "name", None)
    if not isinstance(name, str) or not name:
        raise SemanticGateClosed("combat branch replay received unnamed input")
    return name


class _VirtualTimer:
    def __init__(self, *, reached: bool = False, started: bool = False) -> None:
        self._reached = reached
        self._started = started

    def reached(self) -> bool:
        return self._reached

    def started(self) -> bool:
        return self._started

    def reset(self) -> "_VirtualTimer":
        self._started = True
        return self

    def clear(self) -> "_VirtualTimer":
        self._started = False
        return self


class _BranchDriver:
    def __init__(self, spec: _ScenarioSpec) -> None:
        self.spec = spec
        self.visible = frozenset(spec.visible_resources)
        self.resource_queries: list[str] = []
        self.virtual_actions: list[str] = []
        self.virtual_sleeps: list[str] = []
        self.call_order: list[str] = []
        self.info_bar_counts = iter((0, 1))

    def query(self, name: str) -> bool:
        if name not in ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES:
            raise SemanticGateClosed(
                "combat branch replay queried outside defensive surface: " + name
            )
        self.resource_queries.append(name)
        self.call_order.append("query:" + name)
        return name in self.visible

    def click(self, button: Any) -> None:
        name = _button_name(button)
        index = len(self.virtual_actions)
        if index >= len(self.spec.expected_actions):
            raise SemanticGateClosed(
                "combat branch replay attempted extra action: " + name
            )
        expected = self.spec.expected_actions[index]
        if name != expected:
            raise SemanticGateClosed(
                "combat branch replay action changed: expected={0}; actual={1}".format(
                    expected, name
                )
            )
        owners = tuple(
            resource
            for resource, actions in ALAS_COMBAT_RESOURCE_ACTION_TARGETS.items()
            if name in actions
        )
        if not owners:
            raise SemanticGateClosed(
                "combat branch replay action has no original-ALAS owner: " + name
            )
        if not set(owners).intersection(self.resource_queries):
            raise SemanticGateClosed(
                "combat branch replay action owner was not queried: " + name
            )
        self.virtual_actions.append(name)
        self.call_order.append("device.click(" + name + ")")

    def sleep(self, duration: Any) -> None:
        value = str(duration)
        self.virtual_sleeps.append(value)
        self.call_order.append("device.sleep(" + value + ")")

    def validate(self, returned: Any) -> None:
        if bool(returned) is not self.spec.expected_return:
            raise SemanticGateClosed(
                "combat branch replay return changed: " + self.spec.name
            )
        if tuple(self.resource_queries) != self.spec.expected_queries:
            raise SemanticGateClosed(
                "combat branch replay query order changed: " + self.spec.name
            )
        if tuple(self.virtual_actions) != self.spec.expected_actions:
            raise SemanticGateClosed(
                "combat branch replay action order changed: " + self.spec.name
            )
        if tuple(self.virtual_sleeps) != self.spec.expected_sleeps:
            raise SemanticGateClosed(
                "combat branch replay sleep order changed: " + self.spec.name
            )


class _BranchDevice:
    semantic_adapter = None

    def __init__(self, driver: _BranchDriver) -> None:
        self._driver = driver
        self.image = object()

    def click(self, button: Any) -> None:
        self._driver.click(button)

    def sleep(self, duration: Any) -> None:
        self._driver.sleep(duration)

    def screenshot(self) -> None:
        self._driver.call_order.append("device.screenshot")

    def __getattr__(self, name: str) -> Any:
        raise SemanticGateClosed(
            "combat branch replay attempted unsupported Device access: " + name
        )


def _source_method_identity(campaign: Any, name: str) -> str:
    method = getattr(campaign, name, None)
    function = getattr(method, "__func__", None)
    module = getattr(function, "__module__", None)
    qualname = getattr(function, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(qualname, str):
        raise SemanticGateClosed(
            "combat branch replay source method is unavailable: " + name
        )
    return module + "." + qualname


def _bind_common(sandbox: Any, driver: _BranchDriver) -> None:
    def appear(self: Any, button: Any, *args: Any, **kwargs: Any) -> bool:
        del self, args, kwargs
        return driver.query(_button_name(button))

    def appear_then_click(
        self: Any, button: Any, *args: Any, **kwargs: Any
    ) -> bool:
        del self, args, kwargs
        if not driver.query(_button_name(button)):
            return False
        driver.click(button)
        return True

    def is_combat_executing(self: Any) -> bool:
        del self
        driver.query("PAUSE")
        return False

    def interval_clear(self: Any, buttons: Any, *args: Any, **kwargs: Any) -> None:
        del self, args, kwargs
        driver.call_order.append("interval_clear:" + _names(buttons))

    def interval_reset(self: Any, buttons: Any, *args: Any, **kwargs: Any) -> None:
        del self, args, kwargs
        driver.call_order.append("interval_reset:" + _names(buttons))

    sandbox.appear = MethodType(appear, sandbox)
    sandbox.appear_then_click = MethodType(appear_then_click, sandbox)
    sandbox.is_combat_executing = MethodType(is_combat_executing, sandbox)
    sandbox.interval_clear = MethodType(interval_clear, sandbox)
    sandbox.interval_reset = MethodType(interval_reset, sandbox)


def _names(buttons: Any) -> str:
    if isinstance(buttons, (list, tuple)):
        return ",".join(_button_name(item) for item in buttons)
    return _button_name(buttons)


def _setup_retirement(sandbox: Any, driver: _BranchDriver) -> None:
    sandbox._unable_to_enhance = False
    sandbox.map_cat_attack_timer = _VirtualTimer()

    def handle_game_tips(self: Any) -> bool:
        del self
        driver.call_order.append("handle_game_tips:false")
        return False

    def retire_handler(self: Any, mode: Any = None) -> int:
        del self
        driver.call_order.append("retire_handler:" + str(mode))
        return 1

    sandbox.handle_game_tips = MethodType(handle_game_tips, sandbox)
    sandbox._retire_handler = MethodType(retire_handler, sandbox)


def _setup_story(sandbox: Any, driver: _BranchDriver, *, black: bool) -> None:
    sandbox.story_popup_timeout = _VirtualTimer(started=False)
    sandbox._story_option_timer = _VirtualTimer(reached=False)
    sandbox._story_confirm = _VirtualTimer(reached=True)
    sandbox._story_option_confirm = _VirtualTimer(reached=True)
    sandbox._story_option_record = 0

    def is_story_black(self: Any) -> bool:
        del self
        driver.call_order.append("story_black:" + str(black).lower())
        return black

    def no_options(self: Any) -> list[Any]:
        del self
        raise SemanticGateClosed("combat branch replay entered story option OCR")

    sandbox._is_story_black = MethodType(is_story_black, sandbox)
    sandbox._story_option_buttons_2 = MethodType(no_options, sandbox)


class _TemplateMatch:
    def __init__(self, value: bool) -> None:
        self.value = value

    def match(self, image: Any) -> bool:
        del image
        return self.value


def _run_ambush(sandbox: Any, driver: _BranchDriver) -> Any:
    sandbox.config.MAP_HAS_AMBUSH = True
    sandbox.config.Campaign_AmbushEvade = True

    def false_overlay(self: Any) -> bool:
        del self
        return False

    def wait_until_appear(
        self: Any, button: Any, *args: Any, **kwargs: Any
    ) -> None:
        del self, args, kwargs
        name = _button_name(button)
        if not driver.query(name):
            raise SemanticGateClosed("combat branch replay wait target is absent")
        driver.call_order.append("wait_until_appear:" + name)

    def handle_info_bar(self: Any) -> None:
        del self
        driver.call_order.append("handle_info_bar")

    def info_bar_count(self: Any) -> int:
        del self
        value = next(driver.info_bar_counts)
        driver.call_order.append("info_bar_count:" + str(value))
        return value

    def image_crop(self: Any, *args: Any, **kwargs: Any) -> object:
        del self, args, kwargs
        driver.call_order.append("image_crop:info_bar")
        return object()

    def blocked_combat(self: Any, *args: Any, **kwargs: Any) -> None:
        del self, args, kwargs
        raise SemanticGateClosed("combat branch replay unexpectedly entered combat")

    sandbox._air_raid_appear = MethodType(false_overlay, sandbox)
    sandbox._ambush_appear = MethodType(false_overlay, sandbox)
    sandbox.wait_until_appear = MethodType(wait_until_appear, sandbox)
    sandbox.handle_info_bar = MethodType(handle_info_bar, sandbox)
    sandbox.info_bar_count = MethodType(info_bar_count, sandbox)
    sandbox.image_crop = MethodType(image_crop, sandbox)
    sandbox.combat = MethodType(blocked_combat, sandbox)

    method = getattr(sandbox, "_handle_ambush_evade")
    function = getattr(method, "__func__", None)
    globals_value = getattr(function, "__globals__", None)
    names = (
        "info_letter_preprocess",
        "TEMPLATE_AMBUSH_EVADE_SUCCESS",
        "TEMPLATE_AMBUSH_EVADE_FAILED",
    )
    if not isinstance(globals_value, dict) or any(
        name not in globals_value for name in names
    ):
        raise SemanticGateClosed("combat branch replay ambush globals changed")
    previous = {name: globals_value[name] for name in names}
    globals_value["info_letter_preprocess"] = lambda image: image
    globals_value["TEMPLATE_AMBUSH_EVADE_SUCCESS"] = _TemplateMatch(True)
    globals_value["TEMPLATE_AMBUSH_EVADE_FAILED"] = _TemplateMatch(False)
    try:
        return sandbox.handle_ambush()
    finally:
        globals_value.update(previous)


def _run_scenario(campaign: Any, spec: _ScenarioSpec) -> AlasCombatBranchReplayScenario:
    source_method = _source_method_identity(campaign, spec.method)
    expected_source_method = _SOURCE_METHODS.get(spec.method)
    if expected_source_method is not None and source_method != expected_source_method:
        raise SemanticGateClosed(
            "combat branch replay source owner changed: " + spec.method
        )
    sandbox = copy.copy(campaign)
    sandbox.__dict__ = campaign.__dict__.copy()
    sandbox.config = _copy_config(campaign.config)
    sandbox.interval_timer = {}
    driver = _BranchDriver(spec)
    sandbox.device = _BranchDevice(driver)
    _bind_common(sandbox, driver)

    if spec.setup == "retirement":
        _setup_retirement(sandbox, driver)
    elif spec.setup == "story":
        _setup_story(sandbox, driver, black=False)
    elif spec.setup == "story-black":
        _setup_story(sandbox, driver, black=True)
    elif spec.setup not in ("common", "ambush"):
        raise SemanticGateClosed("combat branch replay setup changed")

    try:
        if spec.setup == "ambush":
            returned = _run_ambush(sandbox, driver)
        else:
            returned = getattr(sandbox, spec.method)()
    except SemanticGateClosed:
        raise
    except Exception as exc:
        raise SemanticGateClosed(
            "original ALAS defensive branch failed: {0}: {1}: {2}".format(
                spec.name, type(exc).__name__, str(exc)
            )
        ) from exc
    driver.validate(returned)
    return AlasCombatBranchReplayScenario(
        name=spec.name,
        source_method=source_method,
        returned=bool(returned),
        resource_queries=tuple(driver.resource_queries),
        virtual_actions=tuple(driver.virtual_actions),
        virtual_sleeps=tuple(driver.virtual_sleeps),
        call_order=tuple(driver.call_order),
    )


def replay_alas_combat_defensive_branches(
    campaign: Any,
) -> AlasCombatBranchReplayResult:
    """Replay pinned rare branches through original ALAS methods without input."""

    if campaign is None or not hasattr(campaign, "__dict__"):
        raise SemanticGateClosed("combat branch replay requires a campaign")
    source_dict = campaign.__dict__
    source_values: Mapping[str, Any] = source_dict.copy()
    scenarios = tuple(_run_scenario(campaign, spec) for spec in _SCENARIOS)
    source_restored = (
        campaign.__dict__ is source_dict
        and tuple(campaign.__dict__) == tuple(source_values)
        and all(campaign.__dict__[name] is value for name, value in source_values.items())
    )
    if not source_restored:
        raise SemanticGateClosed("combat branch replay mutated source campaign")
    return AlasCombatBranchReplayResult(
        scenarios=scenarios,
        source_restored=True,
        input_injected=False,
    )


def alas_combat_branch_replay_to_json(
    result: AlasCombatBranchReplayResult,
) -> Mapping[str, Any]:
    if not isinstance(result, AlasCombatBranchReplayResult):
        raise SemanticGateClosed("combat branch replay result is not typed")
    return {
        "schema": ALAS_COMBAT_BRANCH_REPLAY_SCHEMA,
        "passed": result.passed,
        "source_restored": result.source_restored,
        "input_injected": result.input_injected,
        "scenario_count": len(result.scenarios),
        "scenarios": [
            {
                "name": scenario.name,
                "source_method": scenario.source_method,
                "returned": scenario.returned,
                "resource_queries": list(scenario.resource_queries),
                "virtual_actions": list(scenario.virtual_actions),
                "virtual_sleeps": list(scenario.virtual_sleeps),
                "call_order": list(scenario.call_order),
            }
            for scenario in result.scenarios
        ],
    }


def verify_alas_combat_branch_replay_record(
    value: Any,
) -> Mapping[str, Any]:
    """Verify a checked-in real-ALAS branch replay record without rerunning it."""

    required = {
        "schema",
        "passed",
        "source_restored",
        "input_injected",
        "scenario_count",
        "scenarios",
        "alas_commit",
        "config",
        "source_files_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise SemanticGateClosed("combat branch replay record schema changed")
    if (
        value["schema"] != ALAS_COMBAT_BRANCH_REPLAY_SCHEMA
        or value["passed"] is not True
        or value["source_restored"] is not True
        or value["input_injected"] is not False
        or value["config"] != "semantic_e2e"
        or re.fullmatch(r"[0-9a-f]{40}", str(value["alas_commit"])) is None
    ):
        raise SemanticGateClosed("combat branch replay record identity changed")
    source_files = value["source_files_sha256"]
    if (
        not isinstance(source_files, dict)
        or set(source_files) != set(ALAS_COMBAT_BRANCH_SOURCE_FILES)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None
            for digest in source_files.values()
        )
    ):
        raise SemanticGateClosed("combat branch replay source hashes changed")
    scenarios = value["scenarios"]
    if (
        not isinstance(scenarios, list)
        or value["scenario_count"] != len(_SCENARIOS)
        or len(scenarios) != len(_SCENARIOS)
    ):
        raise SemanticGateClosed("combat branch replay scenario count changed")
    scenario_fields = {
        "name",
        "source_method",
        "returned",
        "resource_queries",
        "virtual_actions",
        "virtual_sleeps",
        "call_order",
    }
    for raw, spec in zip(scenarios, _SCENARIOS):
        if not isinstance(raw, dict) or set(raw) != scenario_fields:
            raise SemanticGateClosed("combat branch replay scenario schema changed")
        if (
            raw["name"] != spec.name
            or raw["source_method"] != _SOURCE_METHODS[spec.method]
            or raw["returned"] is not spec.expected_return
            or tuple(raw["resource_queries"]) != spec.expected_queries
            or tuple(raw["virtual_actions"]) != spec.expected_actions
            or tuple(raw["virtual_sleeps"]) != spec.expected_sleeps
            or not isinstance(raw["call_order"], list)
            or any(not isinstance(item, str) for item in raw["call_order"])
        ):
            raise SemanticGateClosed("combat branch replay scenario changed: " + spec.name)
    return {
        "schema": ALAS_COMBAT_BRANCH_REPLAY_VERIFICATION_SCHEMA,
        "passed": True,
        "scenario_count": len(scenarios),
        "alas_commit": value["alas_commit"],
        "input_injected": False,
        "live_mapping_promoted": False,
    }
