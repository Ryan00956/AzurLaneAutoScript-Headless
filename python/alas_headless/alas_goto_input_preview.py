"""Zero-input execution of ALAS's original campaign ``_goto()`` prefix.

The semantic layer supplies one exact target-cell input for the already
admitted same-cell or bounded-route combat.  ALAS still owns the retreat check,
fleet ensure, visibility, centering, global-to-local conversion, color-baseline
ordering, and final ``device.click(grid)`` call.  The device boundary captures
that exact call and aborts before any Android input or post-click state runs.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from types import MethodType
from typing import Any, Iterable, Tuple

import numpy as np

from .alas_combat_admission import AlasCampaignCombatAdmission
from .alas_decision_preview import (
    AlasCampaignDecisionPreview,
    _DECISION_LOCK,
    _copy_config,
    _location_tuple,
    _native_map_overlay,
)
from .alas_map_sync import AlasCampaignMapProjection
from .semantic_oracle import (
    ActionReceipt,
    Bounds,
    CampaignMapState,
    Point,
    SemanticGateClosed,
)


@dataclass(frozen=True)
class AlasCampaignGotoInputPreview:
    generation: int
    input_generation: int
    stage_code: str
    battle_count: int
    branch_name: str
    fleet_index: int
    fleet_marker: str
    origin_node: str
    target_node: str
    route_nodes: Tuple[str, ...]
    expected: str
    retreat_triggered: bool
    sight: Tuple[int, int, int, int]
    camera_node: str
    local_location: Tuple[int, int]
    center_offset: Tuple[float, float]
    cell_path: str
    point: Point
    bounds: Bounds
    call_order: Tuple[str, ...]

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.generation,
            self.input_generation,
            self.stage_code,
            self.battle_count,
            self.branch_name,
            self.fleet_index,
            self.fleet_marker,
            self.origin_node,
            self.target_node,
            self.route_nodes,
            self.expected,
            self.retreat_triggered,
            self.sight,
            self.camera_node,
            self.local_location,
            self.center_offset,
            self.cell_path,
            self.point,
            self.bounds,
            self.call_order,
        )


@dataclass(frozen=True)
class AlasCampaignGotoInputCommit:
    """Qualification-only receipt from ALAS's exact grid-click statement."""

    preview: AlasCampaignGotoInputPreview
    receipt: ActionReceipt


class _GridInputCaptured(Exception):
    def __init__(self, preview: AlasCampaignGotoInputPreview):
        super().__init__(preview.target_node)
        self.preview = preview


class _GridInputCommitted(Exception):
    def __init__(self, commit: AlasCampaignGotoInputCommit):
        super().__init__(commit.preview.target_node)
        self.commit = commit


class _SemanticGotoGrid:
    """Smallest native-shaped grid input needed by ``device.click(grid)``."""

    def __init__(
        self,
        *,
        location: Tuple[int, int],
        path: str,
        point: Point,
        bounds: Bounds,
    ) -> None:
        self.location = location
        self.corner = (
            (bounds.left, bounds.top),
            (bounds.right, bounds.top),
            (bounds.left, bounds.bottom),
            (bounds.right, bounds.bottom),
        )
        self.button = (
            bounds.left,
            bounds.top,
            bounds.right,
            bounds.bottom,
        )
        self.is_mechanism_trigger = False
        self.mechanism_wait = 0
        self.semantic_path = path
        self.semantic_point = point
        self.semantic_bounds = bounds


class _SemanticGotoView:
    """A centered, one-grid ALAS view derived from the typed cell input."""

    def __init__(self, grid: _SemanticGotoGrid) -> None:
        self.center_loca = grid.location
        self.center_offset = np.array((0.5, 0.5), dtype=float)
        self._grid = grid

    @staticmethod
    def _tuple(location: Iterable[Any]) -> Tuple[int, int]:
        try:
            result = tuple(int(value) for value in location)
        except (TypeError, ValueError) as exc:
            raise SemanticGateClosed(
                "ALAS goto local view received an invalid location"
            ) from exc
        if len(result) != 2:
            raise SemanticGateClosed(
                "ALAS goto local view received an invalid location"
            )
        return result

    def __contains__(self, location: Iterable[Any]) -> bool:
        return self._tuple(location) == self._grid.location

    def __getitem__(self, location: Iterable[Any]) -> _SemanticGotoGrid:
        if self._tuple(location) != self._grid.location:
            raise SemanticGateClosed(
                "ALAS goto requested a cell outside the semantic view"
            )
        return self._grid


class _GotoCaptureDevice:
    def __init__(
        self,
        *,
        grid: _SemanticGotoGrid,
        target_location: Tuple[int, int],
        admission: AlasCampaignCombatAdmission,
        decision: AlasCampaignDecisionPreview,
        sight: Tuple[int, int, int, int],
        call_order: list[str],
    ) -> None:
        self._grid = grid
        self._target_location = target_location
        self._admission = admission
        self._decision = decision
        self._sight = sight
        self._call_order = call_order
        self._captured = False

    def _capture(self, button: Any) -> AlasCampaignGotoInputPreview:
        if self._captured:
            raise SemanticGateClosed("ALAS goto attempted more than one grid input")
        if button is not self._grid:
            raise SemanticGateClosed("ALAS goto changed the semantic local grid")
        annotation = getattr(button, "__str__", None)
        if annotation != self._target_location:
            raise SemanticGateClosed("ALAS goto global grid annotation changed")
        if (
            getattr(button, "semantic_path", None) != self._admission.cell_path
            or getattr(button, "semantic_point", None) != self._admission.point
            or getattr(button, "semantic_bounds", None) != self._admission.bounds
        ):
            raise SemanticGateClosed("ALAS goto semantic grid geometry changed")
        self._call_order.append("device.click")
        expected_order = (
            "hp_retreat_triggered",
            "fleet_set",
            "in_sight",
            "focus_to_grid_center",
            "convert_global_to_local",
            "ambush_color_initial",
            "enemy_searching_color_initial",
            "device.click",
        )
        if tuple(self._call_order) != expected_order:
            raise SemanticGateClosed("ALAS goto pre-click call order changed")
        self._captured = True
        return AlasCampaignGotoInputPreview(
            generation=self._admission.generation,
            input_generation=self._admission.input_generation,
            stage_code=self._admission.stage_code,
            battle_count=self._admission.battle_count,
            branch_name=self._admission.branch_name,
            fleet_index=self._admission.fleet_index,
            fleet_marker=self._admission.fleet_marker,
            origin_node=self._admission.origin_node,
            target_node=self._admission.target_node,
            route_nodes=self._admission.route_nodes,
            expected=self._decision.expected,
            retreat_triggered=False,
            sight=self._sight,
            camera_node=self._admission.target_node,
            local_location=self._grid.location,
            center_offset=(0.5, 0.5),
            cell_path=self._admission.cell_path,
            point=self._admission.point,
            bounds=self._admission.bounds,
            call_order=tuple(self._call_order),
        )

    def click(self, button: Any) -> None:
        raise _GridInputCaptured(self._capture(button))

    def __getattr__(self, name: str) -> Any:
        raise SemanticGateClosed(
            "ALAS goto preview attempted Device access before input capture: "
            + name
        )


class _GotoCommitDevice(_GotoCaptureDevice):
    """Spend one already-admitted grid lease, then stop the ALAS sandbox."""

    def __init__(self, *, input_committer: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._input_committer = input_committer

    def click(self, button: Any) -> None:
        preview = self._capture(button)
        commit = getattr(self._input_committer, "click_campaign_combat_grid", None)
        if not callable(commit):
            # AlasSemanticSession intentionally exposes the adapter's dynamic
            # grid port through its single click proxy.
            commit = getattr(self._input_committer, "click", None)
        committed = getattr(self._input_committer, "campaign_combat_committed", None)
        if not callable(commit) or not callable(committed):
            raise SemanticGateClosed("campaign evidence input committer is incomplete")
        receipt = commit(button)
        if not isinstance(receipt, ActionReceipt):
            raise SemanticGateClosed("campaign evidence input receipt is not typed")
        if (
            receipt.semantic_id != "campaign/map/grid/" + preview.target_node
            or receipt.path != preview.cell_path
            or receipt.point != preview.point
            or receipt.bounds != preview.bounds
            or receipt.generation < preview.input_generation
        ):
            raise SemanticGateClosed("campaign evidence input receipt changed")
        if not committed():
            raise SemanticGateClosed("campaign evidence input lease was not committed")
        raise _GridInputCommitted(
            AlasCampaignGotoInputCommit(preview=preview, receipt=receipt)
        )


def _blocked_method(name: str):
    def blocked(self: Any, *args: Any, **kwargs: Any) -> None:
        del self, args, kwargs
        raise SemanticGateClosed(
            "ALAS goto preview crossed forbidden boundary: " + name
        )

    return blocked


def _validate_inputs(
    campaign: Any,
    projection: AlasCampaignMapProjection,
    decision: AlasCampaignDecisionPreview,
    admission: AlasCampaignCombatAdmission,
    state: CampaignMapState,
) -> Tuple[int, int]:
    if not isinstance(projection, AlasCampaignMapProjection):
        raise SemanticGateClosed("ALAS goto preview requires a projection")
    if not isinstance(decision, AlasCampaignDecisionPreview):
        raise SemanticGateClosed("ALAS goto preview requires a decision")
    if not isinstance(admission, AlasCampaignCombatAdmission):
        raise SemanticGateClosed("ALAS goto preview requires a combat admission")
    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed("ALAS goto preview requires a typed map state")
    if getattr(campaign, "semantic_map_projection", None) is not projection:
        raise SemanticGateClosed("ALAS goto projection is not current")
    if state.signature != admission.map_signature:
        raise SemanticGateClosed("ALAS goto map state changed after admission")
    if decision.signature != admission.decision_signature:
        raise SemanticGateClosed("ALAS goto decision changed after admission")
    if (
        projection.generation != admission.generation
        or decision.generation != admission.generation
        or state.generation != admission.generation
        or projection.stage_code != admission.stage_code
        or decision.stage_code != admission.stage_code
        or state.stage_code != admission.stage_code
    ):
        raise SemanticGateClosed("ALAS goto identity changed after admission")
    same_cell = len(admission.route_nodes) == 1
    if (
        decision.battle_count != admission.battle_count
        or decision.branch_name != admission.branch_name
        or decision.fleet_index != admission.fleet_index
        or decision.fleet_marker != admission.fleet_marker
        or decision.origin_node != admission.origin_node
        or decision.target_node != admission.target_node
        or decision.route_nodes != admission.route_nodes
        or decision.expected != "combat"
        or decision.goto_nodes != (admission.target_node,)
        or decision.step_optimize
    ):
        raise SemanticGateClosed("ALAS goto decision is outside the admitted slice")
    if not (
        (same_cell and admission.origin_node == admission.target_node)
        or (
            2 <= len(admission.route_nodes) <= 4
            and admission.origin_node != admission.target_node
        )
    ):
        raise SemanticGateClosed("ALAS goto decision route changed")
    if getattr(campaign, "battle_count", None) != admission.battle_count:
        raise SemanticGateClosed("ALAS goto campaign battle count changed")
    if (
        getattr(campaign, "fleet_show_index", None)
        != projection.displayed_fleet_index
        or getattr(campaign, "fleet_current_index", None)
        != admission.fleet_index
        or projection.current_fleet_index != admission.fleet_index
        or projection.current_fleet_marker != admission.fleet_marker
    ):
        raise SemanticGateClosed("ALAS goto fleet indexes changed")

    fleet_plans = tuple(
        fleet
        for fleet in projection.fleets
        if fleet.fleet_index == admission.fleet_index
        and fleet.marker == admission.fleet_marker
        and fleet.is_current
        and fleet.origin_node == decision.origin_node
        and fleet.ammo == admission.ammo_before
    )
    state_fleets = tuple(
        fleet
        for fleet in state.fleets
        if fleet.marker == admission.fleet_marker
        and fleet.node == decision.origin_node
        and fleet.ammo == admission.ammo_before
    )
    enemies = tuple(
        enemy
        for enemy in state.enemies
        if enemy.node == admission.target_node
        and enemy.object_id == admission.enemy_object_id
        and enemy.sprite == admission.enemy_sprite
        and enemy.level == admission.enemy_level
        and enemy.fighting == same_cell
    )
    cells = tuple(
        cell
        for cell in state.cells
        if cell.node == admission.target_node
        and cell.button_path == admission.cell_path
        and cell.point == admission.point
        and cell.bounds == admission.bounds
    )
    if not (
        len(fleet_plans) == len(state_fleets) == len(enemies) == len(cells) == 1
        and state.current_fleet_marker == admission.fleet_marker
    ):
        raise SemanticGateClosed("ALAS goto admitted cell state changed")

    target_location = _location_tuple(admission.target_node)
    try:
        target_grid = campaign.map[target_location]
    except Exception as exc:
        raise SemanticGateClosed(
            "ALAS goto target is absent from projected map"
        ) from exc
    if not (
        bool(getattr(target_grid, "is_enemy", False))
        and bool(getattr(target_grid, "is_fleet", False)) == same_cell
        and bool(getattr(target_grid, "is_current_fleet", False)) == same_cell
        and _location_tuple(getattr(campaign, "fleet_current", ()))
        == _location_tuple(decision.origin_node)
    ):
        raise SemanticGateClosed("ALAS goto native target state changed")
    return target_location


def _run_alas_campaign_goto_input(
    campaign: Any,
    projection: AlasCampaignMapProjection,
    decision: AlasCampaignDecisionPreview,
    admission: AlasCampaignCombatAdmission,
    state: CampaignMapState,
    *,
    input_committer: Any = None,
) -> Any:
    """Run the shared original ``_goto()`` prefix in an isolated shell."""

    target_location = _validate_inputs(
        campaign, projection, decision, admission, state
    )
    required = (
        "_goto",
        "hp_retreat_triggered",
        "fleet_ensure",
        "in_sight",
        "focus_to_grid_center",
        "convert_global_to_local",
        "ambush_color_initial",
        "enemy_searching_color_initial",
    )
    if any(not callable(getattr(campaign, name, None)) for name in required):
        raise SemanticGateClosed("ALAS goto campaign interface is incomplete")
    if not hasattr(campaign, "MAP") or not hasattr(campaign, "map"):
        raise SemanticGateClosed("ALAS goto campaign map interface is incomplete")

    sandbox = copy.copy(campaign)
    sandbox.__dict__ = campaign.__dict__.copy()
    sandbox.config = _copy_config(campaign.config)
    sandbox.camera = target_location
    sandbox.fleet_submarine_location = getattr(
        campaign, "fleet_submarine_location", ()
    )

    local_location = (3, 2)
    grid = _SemanticGotoGrid(
        location=local_location,
        path=admission.cell_path,
        point=admission.point,
        bounds=admission.bounds,
    )
    sandbox.view = _SemanticGotoView(grid)
    call_order: list[str] = []

    original_hp_retreat = sandbox.hp_retreat_triggered
    original_in_sight = sandbox.in_sight
    original_focus_center = sandbox.focus_to_grid_center
    original_convert = sandbox.convert_global_to_local
    original_enemy_searching = sandbox.enemy_searching_color_initial

    def hp_retreat(self: Any) -> bool:
        del self
        call_order.append("hp_retreat_triggered")
        return bool(original_hp_retreat())

    def fleet_set(
        self: Any, index: Any = None, skip_first_screenshot: bool = True
    ) -> bool:
        del self, skip_first_screenshot
        call_order.append("fleet_set")
        if index != admission.fleet_index:
            raise SemanticGateClosed("ALAS goto requested another fleet")
        return False

    expected_sight = tuple(int(value) for value in sandbox._walk_sight)
    if len(expected_sight) != 4:
        raise SemanticGateClosed("ALAS goto walk sight is invalid")

    def in_sight(self: Any, location: Any, sight: Any = None) -> Any:
        del self
        call_order.append("in_sight")
        if _location_tuple(location) != target_location:
            raise SemanticGateClosed("ALAS goto visibility target changed")
        if tuple(int(value) for value in sight) != expected_sight:
            raise SemanticGateClosed("ALAS goto visibility window changed")
        result = original_in_sight(location, sight=sight)
        if _location_tuple(sandbox.camera) != target_location:
            raise SemanticGateClosed("ALAS goto attempted a camera move")
        return result

    def focus_to_grid_center(self: Any, tolerance: Any = None) -> Any:
        del self
        call_order.append("focus_to_grid_center")
        result = original_focus_center(tolerance=tolerance)
        if result not in (False, None):
            raise SemanticGateClosed("ALAS goto attempted a centering swipe")
        return result

    def convert_global_to_local(self: Any, location: Any) -> Any:
        del self
        call_order.append("convert_global_to_local")
        if _location_tuple(location) != target_location:
            raise SemanticGateClosed("ALAS goto conversion target changed")
        result = original_convert(location)
        if result is not grid:
            raise SemanticGateClosed("ALAS goto conversion changed the local grid")
        return result

    def ambush_color_initial(self: Any) -> None:
        del self
        call_order.append("ambush_color_initial")
        # This replaces only the pixel color baseline.  Post-click ambush
        # recognition remains closed and is not reached by this preview.

    def enemy_searching_color_initial(self: Any) -> Any:
        del self
        call_order.append("enemy_searching_color_initial")
        return original_enemy_searching()

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
    sandbox.withdraw = MethodType(_blocked_method("withdraw"), sandbox)
    device_type = (
        _GotoCaptureDevice if input_committer is None else _GotoCommitDevice
    )
    device_kwargs = dict(
        grid=grid,
        target_location=target_location,
        admission=admission,
        decision=decision,
        sight=expected_sight,
        call_order=call_order,
    )
    if input_committer is not None:
        device_kwargs["input_committer"] = input_committer
    sandbox.device = device_type(**device_kwargs)

    projected_map = copy.deepcopy(campaign.map)
    with _DECISION_LOCK, _native_map_overlay(
        campaign.MAP, projected_map
    ) as native_map:
        sandbox.map = native_map
        try:
            sandbox._goto(target_location, expected=decision.expected)
        except _GridInputCaptured as captured:
            if input_committer is not None:
                raise SemanticGateClosed(
                    "campaign evidence input stopped before commit"
                )
            return captured.preview
        except _GridInputCommitted as committed:
            if input_committer is None:
                raise SemanticGateClosed(
                    "campaign preview unexpectedly committed input"
                )
            return committed.commit
        except SemanticGateClosed:
            raise
        except Exception as exc:
            raise SemanticGateClosed(
                "ALAS goto prefix failed before input capture: "
                + type(exc).__name__
                + ": "
                + str(exc)
            ) from exc

    raise SemanticGateClosed("ALAS goto returned without a grid input")


def preview_alas_campaign_goto_input(
    campaign: Any,
    projection: AlasCampaignMapProjection,
    decision: AlasCampaignDecisionPreview,
    admission: AlasCampaignCombatAdmission,
    state: CampaignMapState,
) -> AlasCampaignGotoInputPreview:
    """Capture ALAS's exact grid-click statement without performing input."""

    return _run_alas_campaign_goto_input(
        campaign, projection, decision, admission, state
    )


def commit_alas_campaign_goto_input_for_evidence(
    campaign: Any,
    projection: AlasCampaignMapProjection,
    decision: AlasCampaignDecisionPreview,
    admission: AlasCampaignCombatAdmission,
    state: CampaignMapState,
    *,
    input_committer: Any,
) -> AlasCampaignGotoInputCommit:
    """Spend one exact combat lease for a controlled evidence acquisition.

    This API is intentionally absent from the canonical ALAS patch.  It runs
    the same isolated original ``_goto()`` prefix as the zero-input preview,
    delegates only its final ``device.click(grid)`` statement to the current
    semantic adapter, and aborts before post-click ALAS state-machine logic.
    """

    result = _run_alas_campaign_goto_input(
        campaign,
        projection,
        decision,
        admission,
        state,
        input_committer=input_committer,
    )
    if not isinstance(result, AlasCampaignGotoInputCommit):
        raise SemanticGateClosed("campaign evidence input did not commit")
    return result
