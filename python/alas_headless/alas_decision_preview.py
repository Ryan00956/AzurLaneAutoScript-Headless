"""Decision-only execution of an ALAS campaign branch.

The semantic layer supplies native map state, then ALAS keeps ownership of
path initialization, battle-branch dispatch, target selection, and route
construction.  The first public ``goto()`` call is recorded and interrupted;
no device or campaign mutation is admitted.
"""

import copy
import inspect
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from types import MethodType
from typing import Any, Dict, Iterable, Iterator, Tuple

from .alas_map_sync import AlasCampaignMapProjection, AlasCampaignRoutePlan
from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasCampaignDecisionPreview:
    generation: int
    stage_code: str
    battle_count: int
    branch_name: str
    fleet_index: int
    fleet_marker: str
    origin_node: str
    target_node: str
    target_kind: str
    expected: str
    cost: int
    weight: float
    route_nodes: Tuple[str, ...]
    goto_nodes: Tuple[str, ...]
    step_optimize: bool
    turning_optimize: bool

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.generation,
            self.stage_code,
            self.battle_count,
            self.branch_name,
            self.fleet_index,
            self.fleet_marker,
            self.origin_node,
            self.target_node,
            self.target_kind,
            self.expected,
            self.cost,
            self.weight,
            self.route_nodes,
            self.goto_nodes,
            self.step_optimize,
            self.turning_optimize,
        )


class _DecisionCaptured(Exception):
    def __init__(self, preview: AlasCampaignDecisionPreview):
        super().__init__(preview.target_node)
        self.preview = preview


class _NoDecisionInput:
    def __getattr__(self, name: str) -> Any:
        raise SemanticGateClosed(
            "ALAS decision preview attempted Device access: " + name
        )


class _DecisionEmotion:
    def __init__(self, config: Any):
        self._config = config

    @property
    def is_calculate(self) -> bool:
        return "calculate" in str(getattr(self._config, "Emotion_Mode", ""))

    def wait(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise SemanticGateClosed(
            "ALAS decision preview cannot execute an emotion wait"
        )


_DECISION_LOCK = threading.RLock()
_NUMERIC_BATTLE_BRANCH = re.compile(r"battle_[0-9]+$")
_NODE_PATTERN = re.compile(r"([A-Z])([1-9][0-9]*)$")
_BLOCKED_METHODS = (
    "_goto",
    "fleet_set",
    "fleet_ensure",
    "withdraw",
    "combat",
    "map_control_init",
    "update",
    "full_scan",
    "click",
    "appear_then_click",
)


def _location_to_node(location: Iterable[int]) -> str:
    column, row = tuple(location)
    return chr(ord("A") + int(column)) + str(int(row) + 1)


def _location_tuple(location: Any) -> Tuple[int, int]:
    location = getattr(location, "location", location)
    if isinstance(location, str):
        match = _NODE_PATTERN.fullmatch(location)
        if match is None:
            raise SemanticGateClosed("ALAS decision goto node is not canonical")
        return ord(match.group(1)) - ord("A"), int(match.group(2)) - 1
    try:
        result = tuple(int(item) for item in location)
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed("ALAS decision goto location is invalid") from exc
    if len(result) != 2:
        raise SemanticGateClosed("ALAS decision goto location is invalid")
    return result


def _grid_index(campaign_map: Any) -> Dict[Tuple[int, int], Any]:
    result = {tuple(grid.location): grid for grid in campaign_map}
    if len(result) != sum(1 for _ in campaign_map):
        raise SemanticGateClosed("ALAS decision map has duplicate locations")
    return result


@contextmanager
def _native_map_overlay(
    source_map: Any, projected_map: Any
) -> Iterator[Any]:
    """Temporarily make class-level ALAS road references see projected state.

    Campaign files keep ``RoadGrids`` and individual grid constants pointing
    at their class-level ``MAP`` objects.  Swapping only ``campaign.map`` would
    therefore bypass the original roadblock logic.  This transaction keeps all
    grid identities, replaces their attribute dictionaries for the duration of
    the preview, and restores the exact original dictionaries in ``finally``.
    """

    source = _grid_index(source_map)
    projected = _grid_index(projected_map)
    if source.keys() != projected.keys():
        raise SemanticGateClosed("ALAS decision map topology changed")
    if not hasattr(source_map, "__dict__"):
        raise SemanticGateClosed("ALAS decision source map is not transactional")

    original_map_dict = source_map.__dict__
    original_grid_dicts = {
        location: grid.__dict__ for location, grid in source.items()
    }
    overlay_map_dict = projected_map.__dict__.copy()
    overlay_map_dict["grids"] = original_map_dict["grids"]
    try:
        source_map.__dict__ = overlay_map_dict
        for location, grid in source.items():
            grid.__dict__ = projected[location].__dict__.copy()
        yield source_map
    finally:
        for location, grid in source.items():
            grid.__dict__ = original_grid_dicts[location]
        source_map.__dict__ = original_map_dict


def _branch_name() -> str:
    fallback = "battle_function"
    for frame in inspect.stack(context=0):
        name = frame.function
        if _NUMERIC_BATTLE_BRANCH.fullmatch(name):
            return name
        if name in ("battle_default", "battle_boss"):
            fallback = name
    return fallback


def _matching_route(
    projection: AlasCampaignMapProjection,
    fleet_index: int,
    target_node: str,
) -> Tuple[Any, AlasCampaignRoutePlan]:
    fleet = next(
        (item for item in projection.fleets if item.fleet_index == fleet_index),
        None,
    )
    if fleet is None:
        raise SemanticGateClosed("ALAS decision fleet is absent from projection")
    if target_node in projection.enemy_nodes:
        kind = "enemy"
        routes = fleet.enemy_routes
    elif target_node in projection.pickup_nodes:
        kind = "ammo"
        routes = fleet.pickup_routes
    else:
        raise SemanticGateClosed(
            "ALAS decision target is outside semantic enemy/pickup input"
        )
    route = next(
        (
            item
            for item in routes
            if item.target_node == target_node and item.target_kind == kind
        ),
        None,
    )
    if route is None:
        raise SemanticGateClosed("ALAS decision target has no projected route")
    return fleet, route


def _blocked_method(name: str):
    def blocked(self: Any, *args: Any, **kwargs: Any) -> None:
        del self, args, kwargs
        raise SemanticGateClosed(
            "ALAS decision preview crossed forbidden boundary: " + name
        )

    return blocked


def _copy_config(config: Any) -> Any:
    cloned = copy.copy(config)
    if hasattr(config, "__dict__"):
        cloned.__dict__.clear()
        cloned.__dict__.update(config.__dict__)
        for name, value in config.__dict__.items():
            if isinstance(value, (dict, list, set)):
                cloned.__dict__[name] = copy.deepcopy(value)
    if hasattr(cloned, "auto_update"):
        cloned.auto_update = False
    return cloned


def _decision_emotion(sandbox: Any) -> Any:
    sandbox.__dict__.pop("emotion", None)
    try:
        emotion = sandbox.emotion
    except AttributeError:
        emotion = _DecisionEmotion(sandbox.config)
    sandbox.emotion = emotion
    return emotion


@contextmanager
def _reject_emotion_sleep(emotion: Any) -> Iterator[None]:
    module = inspect.getmodule(type(emotion))
    if module is None or not hasattr(module, "sleep"):
        yield
        return
    original_sleep = module.sleep

    def blocked_sleep(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise SemanticGateClosed(
            "ALAS decision preview requires a timed emotion wait"
        )

    try:
        module.sleep = blocked_sleep
        yield
    finally:
        module.sleep = original_sleep


def preview_alas_campaign_decision(
    campaign: Any,
    projection: AlasCampaignMapProjection,
) -> AlasCampaignDecisionPreview:
    """Run ALAS's original battle branch until its first public ``goto``.

    ``synchronize_alas_campaign_map()`` must have populated ``campaign.map``
    and attached the exact projection first.  The preview uses a shallow
    campaign shell, copied config, transactionally overlaid native map grids,
    and hard guards on every known input boundary.  It never invokes ALAS's
    public ``goto`` implementation or any lower-level movement method.
    """

    if not isinstance(projection, AlasCampaignMapProjection):
        raise SemanticGateClosed("ALAS decision preview requires a projection")
    if getattr(campaign, "semantic_map_projection", None) is not projection:
        raise SemanticGateClosed("ALAS decision projection is not current")
    if (
        not callable(getattr(campaign, "battle_function", None))
        or not callable(getattr(campaign, "find_path_initial", None))
        or not hasattr(campaign, "map")
        or not hasattr(campaign, "MAP")
        or not hasattr(campaign, "config")
    ):
        raise SemanticGateClosed("ALAS decision campaign interface is incomplete")
    battle_count = getattr(campaign, "battle_count", None)
    if (
        isinstance(battle_count, bool)
        or not isinstance(battle_count, int)
        or battle_count < 0
    ):
        raise SemanticGateClosed("ALAS decision battle count is invalid")

    sandbox = copy.copy(campaign)
    sandbox.__dict__ = campaign.__dict__.copy()
    sandbox.config = _copy_config(campaign.config)
    sandbox.device = _NoDecisionInput()
    emotion = _decision_emotion(sandbox)
    for name in _BLOCKED_METHODS:
        setattr(sandbox, name, MethodType(_blocked_method(name), sandbox))

    projected_map = copy.deepcopy(campaign.map)
    with _DECISION_LOCK, _native_map_overlay(campaign.MAP, projected_map) as native_map:
        sandbox.map = native_map
        try:
            sandbox.find_path_initial()
        except SemanticGateClosed:
            raise
        except Exception as exc:
            raise SemanticGateClosed(
                "ALAS decision path initialization failed: "
                + type(exc).__name__
                + ": "
                + str(exc)
            ) from exc

        def capture_goto(
            location: Any,
            expected: str = "",
            step_optimize: Any = None,
            turning_optimize: Any = None,
        ) -> None:
            target_location = _location_tuple(location)
            try:
                target = native_map[target_location]
            except Exception as exc:
                raise SemanticGateClosed(
                    "ALAS decision goto target is outside the native map"
                ) from exc
            target_node = _location_to_node(target.location)
            fleet_index = sandbox.fleet_current_index
            fleet, projected_route = _matching_route(
                projection, fleet_index, target_node
            )
            route = native_map._find_path(target.location)
            if not route:
                raise SemanticGateClosed("ALAS decision target is unreachable")
            route_nodes = tuple(_location_to_node(item) for item in route)
            if (
                route_nodes != projected_route.nodes
                or int(target.cost) != projected_route.cost
                or float(target.weight) != projected_route.weight
                or route_nodes[0] != fleet.origin_node
                or route_nodes[-1] != target_node
            ):
                raise SemanticGateClosed(
                    "ALAS decision route disagrees with semantic projection"
                )

            use_step = (
                bool(getattr(sandbox.config, "MAP_HAS_FLEET_STEP", False))
                if step_optimize is None
                else bool(step_optimize)
            )
            if step_optimize is None and (
                bool(getattr(sandbox.config, "MAP_HAS_PORTAL", False))
                or bool(getattr(sandbox.config, "MAP_HAS_MAZE", False))
            ):
                use_step = True
            use_turning = (
                bool(getattr(sandbox.config, "MAP_HAS_AMBUSH", False))
                if turning_optimize is None
                else bool(turning_optimize)
            )
            step = sandbox.fleet_step if use_step else 0
            goto_route = native_map.find_path(
                target.location,
                step=step,
                turning_optimize=use_turning,
            )
            goto_nodes = tuple(_location_to_node(item) for item in goto_route)
            if not goto_nodes or goto_nodes[-1] != target_node:
                raise SemanticGateClosed("ALAS decision goto route is incomplete")

            raise _DecisionCaptured(
                AlasCampaignDecisionPreview(
                    generation=projection.generation,
                    stage_code=projection.stage_code,
                    battle_count=battle_count,
                    branch_name=_branch_name(),
                    fleet_index=fleet_index,
                    fleet_marker=fleet.marker,
                    origin_node=fleet.origin_node,
                    target_node=target_node,
                    target_kind=projected_route.target_kind,
                    expected=str(expected),
                    cost=projected_route.cost,
                    weight=projected_route.weight,
                    route_nodes=route_nodes,
                    goto_nodes=goto_nodes,
                    step_optimize=use_step,
                    turning_optimize=use_turning,
                )
            )

        sandbox.goto = capture_goto
        with _reject_emotion_sleep(emotion):
            try:
                sandbox.battle_function()
            except _DecisionCaptured as captured:
                return captured.preview
            except SemanticGateClosed:
                raise
            except Exception as exc:
                raise SemanticGateClosed(
                    "ALAS decision branch failed before goto: "
                    + type(exc).__name__
                    + ": "
                    + str(exc)
                ) from exc

    raise SemanticGateClosed("ALAS decision branch returned without goto")
