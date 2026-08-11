"""Qualification-only ALAS continuation after one typed camera gesture.

The harness calls ALAS's original ``focus_to()`` to create one camera gesture,
lets the patched original ``Camera.update()`` consume a typed Unity ``View``,
then enters the original ``_goto()`` and stops at its exact grid-click
statement.  The grid click is observed but never delegated to Android.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from types import MethodType
from typing import Any, Tuple

from .alas_camera_view import (
    AlasCampaignCameraViewObservation,
    AlasSemanticCampaignGrid,
    build_alas_campaign_camera_view,
)
from .alas_combat_admission import AlasCampaignCombatAdmission
from .alas_decision_preview import (
    AlasCampaignDecisionPreview,
    _DECISION_LOCK,
    _copy_config,
    _location_tuple,
    _native_map_overlay,
)
from .alas_goto_input_preview import _validate_inputs
from .alas_map_sync import AlasCampaignMapProjection
from .semantic_oracle import (
    CampaignMapState,
    CampaignMapViewportSwipeProof,
    SemanticGateClosed,
)


@dataclass(frozen=True)
class AlasCampaignViewportContinuation:
    stage_code: str
    battle_count: int
    target_node: str
    initial_generation: int
    viewport_post_generation: int
    camera_state_generation: int
    recheck_generation: int
    camera_before_node: str
    camera_after_node: str
    camera_before_offset: Tuple[float, float]
    camera_after_offset: Tuple[float, float]
    requested_grid_vector: Tuple[int, int]
    target_path: str
    target_local_location: Tuple[int, int]
    call_order: Tuple[str, ...]
    original_camera_update_owner: bool
    original_alas_goto_recheck_owner: bool
    grid_input_injected: bool
    production_enabled: bool


class _ViewportGridCaptured(Exception):
    pass


class _ViewportContinuationDevice:
    def __init__(
        self,
        real_device: Any,
        *,
        target_location: Tuple[int, int],
        target_path: str,
        target_point: Any,
        target_bounds: Any,
        call_order: list[str],
    ) -> None:
        self._real_device = real_device
        self._target_location = target_location
        self._target_path = target_path
        self._target_point = target_point
        self._target_bounds = target_bounds
        self._call_order = call_order
        self.captured_grid = None
        self.swipe_vector_count = 0

    def swipe_vector(self, *args: Any, **kwargs: Any) -> Any:
        self.swipe_vector_count += 1
        self._call_order.append("device.swipe_vector")
        return self._real_device.swipe_vector(*args, **kwargs)

    def click(self, button: Any) -> None:
        if self.captured_grid is not None:
            raise SemanticGateClosed(
                "ALAS viewport continuation attempted more than one grid click"
            )
        if not isinstance(button, AlasSemanticCampaignGrid):
            raise SemanticGateClosed(
                "ALAS viewport continuation changed the typed grid"
            )
        if getattr(button, "__str__", None) != self._target_location:
            raise SemanticGateClosed(
                "ALAS viewport continuation changed the global target"
            )
        if (
            button.semantic_path != self._target_path
            or button.semantic_point != self._target_point
            or button.semantic_bounds != self._target_bounds
        ):
            raise SemanticGateClosed(
                "ALAS viewport continuation changed target geometry"
            )
        self._call_order.append("device.click")
        self.captured_grid = button
        raise _ViewportGridCaptured

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real_device, name)


def preview_alas_campaign_viewport_continuation(
    campaign: Any,
    projection: AlasCampaignMapProjection,
    decision: AlasCampaignDecisionPreview,
    admission: AlasCampaignCombatAdmission,
    state: CampaignMapState,
    *,
    semantic_session: Any,
) -> AlasCampaignViewportContinuation:
    """Run one original Camera update and `_goto()` recheck without grid input."""

    target_location = _validate_inputs(
        campaign, projection, decision, admission, state
    )
    required_session_methods = (
        "campaign_map_viewport_swipe_committed",
        "campaign_map_viewport_swipe_proof",
        "campaign_camera_state",
        "campaign_camera_target_node",
        "recheck_campaign_combat_target_after_camera_view",
        "campaign_combat_committed",
    )
    if any(
        not callable(getattr(semantic_session, name, None))
        for name in required_session_methods
    ):
        raise SemanticGateClosed(
            "ALAS viewport continuation semantic session is incomplete"
        )
    required_campaign_methods = (
        "focus_to",
        "map_swipe",
        "_map_swipe",
        "update",
        "_update_view",
        "_update_view_data",
        "_goto",
        "hp_retreat_triggered",
        "fleet_ensure",
        "in_sight",
        "focus_to_grid_center",
        "convert_global_to_local",
    )
    if any(not callable(getattr(campaign, name, None)) for name in required_campaign_methods):
        raise SemanticGateClosed(
            "ALAS viewport continuation campaign interface is incomplete"
        )

    initial_view = build_alas_campaign_camera_view(
        state,
        screen_center=campaign.config.SCREEN_CENTER,
        target_node=admission.target_node,
    )
    initial_observation = initial_view.semantic_observation
    if (
        initial_observation.target_path != admission.cell_path
        or initial_observation.target_point != admission.point
        or initial_observation.target_bounds != admission.bounds
    ):
        raise SemanticGateClosed(
            "ALAS viewport continuation initial target changed"
        )
    requested_grid_vector = tuple(
        target_location[index] - initial_observation.camera_location[index]
        for index in range(2)
    )
    if (
        requested_grid_vector == (0, 0)
        or abs(requested_grid_vector[0]) > 4
        or abs(requested_grid_vector[1]) > 3
    ):
        raise SemanticGateClosed(
            "ALAS viewport continuation needs one bounded focus gesture"
        )

    sandbox = copy.copy(campaign)
    sandbox.__dict__ = campaign.__dict__.copy()
    sandbox.config = _copy_config(campaign.config)
    sandbox.camera = initial_observation.camera_location
    sandbox.view = initial_view
    sandbox.fleet_submarine_location = getattr(
        campaign, "fleet_submarine_location", ()
    )
    call_order: list[str] = []
    camera_observations: list[AlasCampaignCameraViewObservation] = []

    originals = {
        name: getattr(sandbox, name)
        for name in (
            "map_swipe",
            "_map_swipe",
            "update",
            "_update_view",
            "_update_view_data",
            "hp_retreat_triggered",
            "in_sight",
            "focus_to_grid_center",
            "convert_global_to_local",
        )
    }

    def wrap(name: str):
        original = originals[name]

        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            del self
            call_order.append(name)
            result = original(*args, **kwargs)
            if name == "_update_view":
                observation = getattr(
                    sandbox, "semantic_camera_view_observation", None
                )
                if not isinstance(
                    observation, AlasCampaignCameraViewObservation
                ):
                    raise SemanticGateClosed(
                        "original ALAS camera update did not consume typed View"
                    )
                camera_observations.append(observation)
            return result

        return wrapped

    for name in (
        "map_swipe",
        "_map_swipe",
        "update",
        "_update_view",
        "_update_view_data",
    ):
        setattr(sandbox, name, MethodType(wrap(name), sandbox))

    def hp_retreat_triggered(self: Any) -> bool:
        del self
        call_order.append("hp_retreat_triggered")
        return bool(originals["hp_retreat_triggered"]())

    def fleet_set(
        self: Any, index: Any = None, skip_first_screenshot: bool = True
    ) -> bool:
        del self, skip_first_screenshot
        call_order.append("fleet_set")
        if index != admission.fleet_index:
            raise SemanticGateClosed(
                "ALAS viewport continuation requested another fleet"
            )
        return False

    def in_sight(self: Any, location: Any, sight: Any = None) -> Any:
        del self
        call_order.append("in_sight")
        if _location_tuple(location) != target_location:
            raise SemanticGateClosed(
                "ALAS viewport continuation visibility target changed"
            )
        return originals["in_sight"](location, sight=sight)

    def focus_to_grid_center(self: Any, tolerance: Any = None) -> Any:
        del self
        call_order.append("focus_to_grid_center")
        return originals["focus_to_grid_center"](tolerance=tolerance)

    def convert_global_to_local(self: Any, location: Any) -> Any:
        del self
        call_order.append("convert_global_to_local")
        if _location_tuple(location) != target_location:
            raise SemanticGateClosed(
                "ALAS viewport continuation conversion target changed"
            )
        return originals["convert_global_to_local"](location)

    def ambush_color_initial(self: Any) -> None:
        del self
        call_order.append("ambush_color_initial")

    def enemy_searching_color_initial(self: Any) -> None:
        del self
        call_order.append("enemy_searching_color_initial")

    sandbox.hp_retreat_triggered = MethodType(hp_retreat_triggered, sandbox)
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

    projected_map = copy.deepcopy(campaign.map)
    with _DECISION_LOCK, _native_map_overlay(
        campaign.MAP, projected_map
    ) as native_map:
        sandbox.map = native_map
        # The patched original `_update_view` obtains the current semantic
        # session through the campaign device.  Only the final grid click is
        # replaced by this proxy.
        device = _ViewportContinuationDevice(
            campaign.device,
            target_location=target_location,
            target_path=admission.cell_path,
            target_point=admission.point,
            target_bounds=admission.bounds,
            call_order=call_order,
        )
        sandbox.device = device
        call_order.append("focus_to")
        sandbox.focus_to(target_location)

        if (
            device.swipe_vector_count != 1
            or not semantic_session.campaign_map_viewport_swipe_committed()
            or len(camera_observations) != 1
        ):
            raise SemanticGateClosed(
                "ALAS viewport continuation did not prove one camera update"
            )
        viewport = semantic_session.campaign_map_viewport_swipe_proof()
        if not isinstance(viewport, CampaignMapViewportSwipeProof):
            raise SemanticGateClosed(
                "ALAS viewport continuation lost typed swipe proof"
            )
        after_observation = camera_observations[0]
        if (
            viewport.grid_vector != requested_grid_vector
            or tuple(sandbox.camera) != after_observation.camera_location
            or after_observation.camera_location != target_location
            or viewport.post_generation > after_observation.generation
        ):
            raise SemanticGateClosed(
                "original ALAS camera update disagrees with typed movement"
            )

        current_state = sandbox.view.semantic_state
        call_order.append("target_recheck")
        recheck = semantic_session.recheck_campaign_combat_target_after_camera_view(
            current_state
        )
        device._target_path = recheck.path
        device._target_point = recheck.point
        device._target_bounds = recheck.bounds

        call_order.append("_goto")
        try:
            sandbox._goto(target_location, expected=decision.expected)
        except _ViewportGridCaptured:
            pass
        except SemanticGateClosed:
            raise
        except Exception as exc:
            raise SemanticGateClosed(
                "ALAS viewport continuation failed before grid capture: "
                + type(exc).__name__
                + ": "
                + str(exc)
            ) from exc
        else:
            raise SemanticGateClosed(
                "ALAS viewport continuation returned without grid capture"
            )

    if semantic_session.campaign_combat_committed():
        raise SemanticGateClosed(
            "ALAS viewport continuation unexpectedly injected grid input"
        )
    required_order = (
        "focus_to",
        "device.swipe_vector",
        "update",
        "_update_view",
        "_update_view_data",
        "target_recheck",
        "_goto",
        "hp_retreat_triggered",
        "fleet_set",
        "in_sight",
        "focus_to_grid_center",
        "convert_global_to_local",
        "ambush_color_initial",
        "enemy_searching_color_initial",
        "device.click",
    )
    cursor = 0
    for name in call_order:
        if cursor < len(required_order) and name == required_order[cursor]:
            cursor += 1
    if cursor != len(required_order):
        raise SemanticGateClosed(
            "ALAS viewport continuation call order changed: "
            + repr(call_order)
        )

    target_local = getattr(device.captured_grid, "location", None)
    if target_local != target_location:
        raise SemanticGateClosed(
            "ALAS viewport continuation local target changed"
        )
    return AlasCampaignViewportContinuation(
        stage_code=state.stage_code,
        battle_count=admission.battle_count,
        target_node=admission.target_node,
        initial_generation=state.generation,
        viewport_post_generation=viewport.post_generation,
        camera_state_generation=after_observation.generation,
        recheck_generation=recheck.recheck_generation,
        camera_before_node=initial_observation.camera_node,
        camera_after_node=after_observation.camera_node,
        camera_before_offset=initial_observation.center_offset,
        camera_after_offset=after_observation.center_offset,
        requested_grid_vector=requested_grid_vector,
        target_path=recheck.path,
        target_local_location=target_local,
        call_order=tuple(call_order),
        original_camera_update_owner=True,
        original_alas_goto_recheck_owner=True,
        grid_input_injected=False,
        production_enabled=False,
    )
