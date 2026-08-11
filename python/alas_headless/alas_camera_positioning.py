"""Qualification-only empty-cell positioning through original ALAS Camera."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from types import MethodType
from typing import Any, Tuple

from .alas_adapter import CampaignCameraPositioningAdmission
from .alas_camera_view import (
    AlasCampaignCameraViewObservation,
    build_alas_campaign_camera_view,
)
from .alas_decision_preview import (
    _DECISION_LOCK,
    _copy_config,
    _native_map_overlay,
)
from .alas_map_sync import AlasCampaignMapProjection
from .semantic_oracle import (
    CampaignMapState,
    CampaignMapViewportSwipeProof,
    SemanticGateClosed,
)


@dataclass(frozen=True)
class AlasCampaignCameraPositioning:
    stage_code: str
    target_node: str
    initial_generation: int
    viewport_post_generation: int
    camera_state_generation: int
    camera_before_node: str
    camera_after_node: str
    camera_before_offset: Tuple[float, float]
    camera_after_offset: Tuple[float, float]
    requested_grid_vector: Tuple[int, int]
    gesture_grid_vectors: Tuple[Tuple[int, int], ...]
    gesture_count: int
    call_order: Tuple[str, ...]
    input_injected: bool
    qualification_only: bool
    production_enabled: bool


class _PositioningDevice:
    def __init__(self, real_device: Any, call_order: list[str]) -> None:
        self._real_device = real_device
        self._call_order = call_order
        self.swipe_vector_count = 0

    def swipe_vector(self, *args: Any, **kwargs: Any) -> Any:
        self.swipe_vector_count += 1
        if self.swipe_vector_count > 2:
            raise SemanticGateClosed(
                "ALAS camera positioning attempted more than two gestures"
            )
        self._call_order.append("device.swipe_vector")
        return self._real_device.swipe_vector(*args, **kwargs)

    def click(self, button: Any) -> None:
        del button
        raise SemanticGateClosed(
            "ALAS camera positioning attempted a non-camera click"
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real_device, name)


def position_alas_campaign_camera_for_qualification(
    campaign: Any,
    projection: AlasCampaignMapProjection,
    state: CampaignMapState,
    *,
    target_node: str,
    semantic_session: Any,
) -> AlasCampaignCameraPositioning:
    """Move the live camera once without choosing a fleet or combat target."""

    if not isinstance(projection, AlasCampaignMapProjection):
        raise SemanticGateClosed(
            "ALAS camera positioning requires a typed map projection"
        )
    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed(
            "ALAS camera positioning requires a typed map state"
        )
    if projection.generation != state.generation:
        raise SemanticGateClosed(
            "ALAS camera positioning projection is stale"
        )
    required_session_methods = (
        "authorize_campaign_camera_positioning",
        "campaign_camera_positioning_committed",
        "complete_campaign_camera_positioning",
        "campaign_camera_positioning_proof",
        "campaign_camera_positioning_proofs",
        "campaign_camera_state",
        "campaign_camera_target_node",
        "campaign_combat_committed",
    )
    if any(
        not callable(getattr(semantic_session, name, None))
        for name in required_session_methods
    ):
        raise SemanticGateClosed(
            "ALAS camera positioning semantic session is incomplete"
        )
    for name in (
        "focus_to",
        "map_swipe",
        "_map_swipe",
        "update",
        "_update_view",
        "_update_view_data",
    ):
        if not callable(getattr(campaign, name, None)):
            raise SemanticGateClosed(
                "ALAS camera positioning campaign interface is incomplete"
            )

    admission = semantic_session.authorize_campaign_camera_positioning(
        target_node, state
    )
    if not isinstance(admission, CampaignCameraPositioningAdmission):
        raise SemanticGateClosed(
            "ALAS camera positioning admission is not typed"
        )
    initial_view = build_alas_campaign_camera_view(
        state,
        screen_center=campaign.config.SCREEN_CENTER,
        target_node=target_node,
    )
    initial_observation = initial_view.semantic_observation
    if (
        initial_observation.target_path != admission.path
        or initial_observation.target_point != admission.point
        or initial_observation.target_bounds != admission.bounds
    ):
        raise SemanticGateClosed(
            "ALAS camera positioning initial target changed"
        )
    target_location = initial_observation.target_local_location
    if target_location is None:
        raise SemanticGateClosed(
            "ALAS camera positioning target location is absent"
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
            "ALAS camera positioning target needs one bounded gesture"
        )

    sandbox = copy.copy(campaign)
    sandbox.__dict__ = campaign.__dict__.copy()
    sandbox.config = _copy_config(campaign.config)
    sandbox.camera = initial_observation.camera_location
    sandbox.view = initial_view
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
                        "original ALAS camera positioning lost typed View"
                    )
                camera_observations.append(observation)
            return result

        return wrapped

    for name in originals:
        setattr(sandbox, name, MethodType(wrap(name), sandbox))

    projected_map = copy.deepcopy(campaign.map)
    with _DECISION_LOCK, _native_map_overlay(
        campaign.MAP, projected_map
    ) as native_map:
        sandbox.map = native_map
        device = _PositioningDevice(campaign.device, call_order)
        sandbox.device = device
        call_order.append("focus_to")
        sandbox.focus_to(target_location)

    completed_proofs = semantic_session.complete_campaign_camera_positioning(
        sandbox.view.semantic_state
    )
    if (
        not 1 <= device.swipe_vector_count <= 2
        or device.swipe_vector_count != len(camera_observations)
        or device.swipe_vector_count != len(completed_proofs)
        or not semantic_session.campaign_camera_positioning_committed()
        or semantic_session.campaign_combat_committed()
    ):
        raise SemanticGateClosed(
            "ALAS camera positioning did not prove one or two gestures"
        )
    proof = semantic_session.campaign_camera_positioning_proof()
    if not isinstance(proof, CampaignMapViewportSwipeProof):
        raise SemanticGateClosed(
            "ALAS camera positioning proof is not typed"
        )
    proofs = semantic_session.campaign_camera_positioning_proofs()
    if proofs != completed_proofs or proof is not proofs[-1]:
        raise SemanticGateClosed(
            "ALAS camera positioning proof sequence changed"
        )
    after_observation = camera_observations[-1]
    if (
        proof.target_node != target_node
        or proofs[0].grid_vector != requested_grid_vector
        or any(item.target_node != target_node for item in proofs)
        or tuple(sandbox.camera) != after_observation.camera_location
        or after_observation.camera_location != target_location
        or proof.post_generation > after_observation.generation
    ):
        raise SemanticGateClosed(
            "original ALAS camera positioning disagrees with typed movement"
        )
    required_order = (
        "focus_to",
        "map_swipe",
        "_map_swipe",
        "device.swipe_vector",
        "update",
        "_update_view",
        "_update_view_data",
    )
    cursor = 0
    for name in call_order:
        if cursor < len(required_order) and name == required_order[cursor]:
            cursor += 1
    if cursor != len(required_order):
        raise SemanticGateClosed(
            "ALAS camera positioning call order changed: " + repr(call_order)
        )
    return AlasCampaignCameraPositioning(
        stage_code=state.stage_code,
        target_node=target_node,
        initial_generation=state.generation,
        viewport_post_generation=proof.post_generation,
        camera_state_generation=after_observation.generation,
        camera_before_node=initial_observation.camera_node,
        camera_after_node=after_observation.camera_node,
        camera_before_offset=initial_observation.center_offset,
        camera_after_offset=after_observation.center_offset,
        requested_grid_vector=requested_grid_vector,
        gesture_grid_vectors=tuple(item.grid_vector for item in proofs),
        gesture_count=len(proofs),
        call_order=tuple(call_order),
        input_injected=True,
        qualification_only=True,
        production_enabled=False,
    )
