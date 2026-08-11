"""Typed Unity replacement for ALAS's campaign camera-detection input.

ALAS keeps ownership of ``Camera.update()``, its wait loop, swipe prediction,
camera-coordinate update, centering decision, and global-to-local conversion.
This module supplies only the ``View`` data that ALAS normally derives from a
screenshot: grid geometry, the grid containing ``SCREEN_CENTER``, fractional
center offset, and calibrated adjacent-cell distance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence, Tuple

import numpy as np

from .semantic_oracle import (
    Bounds,
    CampaignMapCellState,
    CampaignMapState,
    Point,
    SemanticGateClosed,
)


def _node(location: Tuple[int, int]) -> str:
    column, row = location
    if not (0 <= column < 26 and 0 <= row < 99):
        raise SemanticGateClosed("semantic ALAS camera location is outside bounds")
    return chr(ord("A") + column) + str(row + 1)


def _location(value: Iterable[Any], label: str) -> Tuple[int, int]:
    try:
        result = tuple(int(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed(label + " is malformed") from exc
    if len(result) != 2:
        raise SemanticGateClosed(label + " is malformed")
    return result


@dataclass(frozen=True)
class AlasCampaignCameraViewObservation:
    generation: int
    stage_code: str
    camera_location: Tuple[int, int]
    camera_node: str
    center_offset: Tuple[float, float]
    swipe_base: Tuple[float, float]
    cell_count: int
    projective_maximum_residual: float
    projective_rms_residual: float
    target_node: Optional[str]
    target_local_location: Optional[Tuple[int, int]]
    target_path: Optional[str]
    target_point: Optional[Point]
    target_bounds: Optional[Bounds]


class _ProjectiveCameraModel:
    def __init__(
        self,
        *,
        homography: np.ndarray,
        source_center: np.ndarray,
        source_scale: float,
        target_center: np.ndarray,
        target_scale: float,
    ) -> None:
        self.homography = homography
        self.source_center = source_center
        self.source_scale = source_scale
        self.target_center = target_center
        self.target_scale = target_scale

    def grid_to_screen(self, points: Any) -> np.ndarray:
        values = np.asarray(points, dtype=float)
        if values.ndim != 2 or values.shape[1] != 2:
            raise SemanticGateClosed(
                "semantic ALAS camera grid projection is malformed"
            )
        normalized = (values - self.source_center) / self.source_scale
        homogeneous = np.column_stack(
            (normalized, np.ones(len(normalized), dtype=float))
        )
        projected = homogeneous @ self.homography.T
        if np.any(~np.isfinite(projected)) or np.any(
            np.abs(projected[:, 2]) < 0.10
        ):
            raise SemanticGateClosed(
                "semantic ALAS camera grid projection crosses infinity"
            )
        return (
            projected[:, :2] / projected[:, 2, None] * self.target_scale
            + self.target_center
        )


class AlasSemanticCampaignGrid:
    """Native-shaped grid record backed by one exact Unity map-cell quad."""

    def __init__(
        self,
        cell: CampaignMapCellState,
        *,
        state: CampaignMapState,
        projector: _ProjectiveCameraModel,
    ) -> None:
        self.location = (cell.column - 1, cell.row - 1)
        self.corner = np.asarray(
            (
                (cell.bounds.left, cell.bounds.top),
                (cell.bounds.right, cell.bounds.top),
                (cell.bounds.left, cell.bounds.bottom),
                (cell.bounds.right, cell.bounds.bottom),
            ),
            dtype=float,
        )
        self.button = (
            cell.bounds.left,
            cell.bounds.top,
            cell.bounds.right,
            cell.bounds.bottom,
        )
        self.is_mechanism_trigger = False
        self.mechanism_wait = 0
        self.semantic_path = cell.button_path
        self.semantic_point = cell.point
        self.semantic_bounds = cell.bounds
        self._projector = projector
        enemy = next((item for item in state.enemies if item.node == cell.node), None)
        fleet = next((item for item in state.fleets if item.node == cell.node), None)
        pickup = next((item for item in state.pickups if item.node == cell.node), None)
        self.is_enemy = enemy is not None
        self.is_siren = bool(
            enemy is not None and "siren" in enemy.genre.lower()
        )
        self.is_boss = bool(
            enemy is not None and "boss" in enemy.genre.lower()
        )
        self.is_mystery = bool(
            pickup is not None and pickup.kind.lower() == "mystery"
        )
        self.is_fleet = fleet is not None
        self.is_current_fleet = bool(
            fleet is not None and fleet.marker == state.current_fleet_marker
        )
        self.outer = self.button

    def grid2screen(self, points: Any) -> np.ndarray:
        return self._projector.grid_to_screen(
            np.asarray(points, dtype=float) + np.asarray(self.location, dtype=float)
        )


class _AlasSemanticGridSelection:
    def __init__(self, grids: Iterable[AlasSemanticCampaignGrid]) -> None:
        self.grids = list(grids)

    def __iter__(self):
        return iter(self.grids)

    def add(self, other: Any) -> "_AlasSemanticGridSelection":
        if not isinstance(other, _AlasSemanticGridSelection):
            raise SemanticGateClosed("semantic ALAS camera selection is malformed")
        unique = list(self.grids)
        for grid in other.grids:
            if grid not in unique:
                unique.append(grid)
        return _AlasSemanticGridSelection(unique)


class AlasSemanticCampaignView:
    """Small ``View``-compatible typed observation consumed by ALAS Camera."""

    def __init__(
        self,
        *,
        state: CampaignMapState,
        observation: AlasCampaignCameraViewObservation,
        projector: _ProjectiveCameraModel,
    ) -> None:
        self.semantic_state = state
        self.semantic_observation = observation
        self.grids = {
            (cell.column - 1, cell.row - 1): AlasSemanticCampaignGrid(
                cell, state=state, projector=projector
            )
            for cell in state.cells
        }
        if len(self.grids) != len(state.cells):
            raise SemanticGateClosed("semantic ALAS camera view has duplicate cells")
        self.shape = np.asarray((state.columns - 1, state.rows - 1), dtype=int)
        self.center_loca = observation.camera_location
        self.center_offset = np.asarray(observation.center_offset, dtype=float)
        self.swipe_base = np.asarray(observation.swipe_base, dtype=float)
        # Edge correction needs the exact rendered map boundary, which the
        # current typed surface does not expose.  Internal views are qualified;
        # observations whose screen center reaches a map edge are rejected by
        # the builder instead of fabricating these flags.
        self.left_edge = False
        self.right_edge = False
        self.lower_edge = False
        self.upper_edge = False

    def __iter__(self):
        return iter(self.grids.values())

    def __contains__(self, item: Iterable[Any]) -> bool:
        return _location(item, "semantic ALAS camera lookup") in self.grids

    def __getitem__(self, item: Iterable[Any]) -> AlasSemanticCampaignGrid:
        key = _location(item, "semantic ALAS camera lookup")
        try:
            return self.grids[key]
        except KeyError as exc:
            raise SemanticGateClosed(
                "ALAS camera requested a cell outside the typed view"
            ) from exc

    def predict(self) -> None:
        # Enemy/fleet classification already entered ALAS through the typed map
        # projection.  Screenshot pixel prediction is intentionally absent.
        return None

    def show(self) -> None:
        return None

    def select(self, **kwargs: Any) -> _AlasSemanticGridSelection:
        return _AlasSemanticGridSelection(
            grid
            for grid in self
            if all(getattr(grid, name, None) == value for name, value in kwargs.items())
        )

    def predict_swipe(
        self,
        current: Any,
        *,
        with_current_fleet: bool = True,
        with_sea_grids: bool = True,
    ) -> Tuple[int, int]:
        del with_current_fleet, with_sea_grids
        if not isinstance(current, AlasSemanticCampaignView):
            raise SemanticGateClosed("ALAS camera swipe prediction lost typed view")
        before = self.semantic_observation
        after = current.semantic_observation
        if (
            self.semantic_state.signature != current.semantic_state.signature
            or after.generation <= before.generation
        ):
            raise SemanticGateClosed("ALAS camera swipe prediction changed map state")
        delta = tuple(
            after.camera_location[index] - before.camera_location[index]
            for index in range(2)
        )
        if delta == (0, 0) or abs(delta[0]) > 4 or abs(delta[1]) > 3:
            raise SemanticGateClosed("ALAS camera observed swipe is outside limits")
        return delta


def _fit_projective_camera(
    state: CampaignMapState,
    screen_center: Tuple[float, float],
) -> Tuple[Tuple[float, float], float, float, _ProjectiveCameraModel]:
    source = np.asarray(
        [(cell.column - 0.5, cell.row - 0.5) for cell in state.cells],
        dtype=float,
    )
    target = np.asarray(
        [(cell.point.x, cell.point.y) for cell in state.cells], dtype=float
    )
    if len(source) < 8:
        raise SemanticGateClosed("semantic ALAS camera needs at least eight cells")

    def normalize(points: np.ndarray):
        center = points.mean(axis=0)
        scale = float(np.sqrt(np.mean(np.sum((points - center) ** 2, axis=1))))
        if not math.isfinite(scale) or scale < 1.0:
            raise SemanticGateClosed("semantic ALAS camera cell spread is degenerate")
        return (points - center) / scale, center, scale

    normalized_source, source_center, source_scale = normalize(source)
    normalized_target, target_center, target_scale = normalize(target)
    rows = []
    outputs = []
    for (x, y), (u, v) in zip(normalized_source, normalized_target):
        rows.append((x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y))
        outputs.append(u)
        rows.append((0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y))
        outputs.append(v)
    matrix = np.asarray(rows, dtype=float)
    values = np.asarray(outputs, dtype=float)
    parameters, _, rank, singular_values = np.linalg.lstsq(
        matrix, values, rcond=None
    )
    if rank != 8 or len(singular_values) != 8:
        raise SemanticGateClosed("semantic ALAS camera projective model is singular")
    if singular_values[-1] <= 0.0 or singular_values[0] / singular_values[-1] > 1e8:
        raise SemanticGateClosed(
            "semantic ALAS camera projective model is ill-conditioned"
        )
    homography = np.append(parameters, 1.0).reshape(3, 3)
    determinant = float(np.linalg.det(homography))
    if not math.isfinite(determinant) or abs(determinant) < 1e-4:
        raise SemanticGateClosed("semantic ALAS camera projective model collapses")

    predicted = []
    for x, y in normalized_source:
        value = homography @ np.asarray((x, y, 1.0), dtype=float)
        if not np.all(np.isfinite(value)) or abs(value[2]) < 0.10:
            raise SemanticGateClosed(
                "semantic ALAS camera projective model crosses infinity"
            )
        predicted.append(value[:2] / value[2] * target_scale + target_center)
    residuals = np.linalg.norm(np.asarray(predicted) - target, axis=1)
    maximum_residual = float(np.max(residuals))
    rms_residual = float(np.sqrt(np.mean(residuals ** 2)))
    if maximum_residual > 2.0 or rms_residual > 1.0:
        raise SemanticGateClosed(
            "semantic ALAS camera projective geometry is incoherent"
        )

    normalized_screen = (
        np.asarray(screen_center, dtype=float) - target_center
    ) / target_scale
    inverse = np.linalg.inv(homography)
    continuous = inverse @ np.asarray(
        (normalized_screen[0], normalized_screen[1], 1.0), dtype=float
    )
    if not np.all(np.isfinite(continuous)) or abs(continuous[2]) < 0.10:
        raise SemanticGateClosed("semantic ALAS camera screen center is singular")
    continuous = continuous[:2] / continuous[2] * source_scale + source_center
    model = _ProjectiveCameraModel(
        homography=homography,
        source_center=source_center,
        source_scale=source_scale,
        target_center=target_center,
        target_scale=target_scale,
    )
    return (
        (float(continuous[0]), float(continuous[1])),
        maximum_residual,
        rms_residual,
        model,
    )


def build_alas_campaign_camera_view(
    state: CampaignMapState,
    *,
    screen_center: Sequence[float],
    target_node: Optional[str] = None,
) -> AlasSemanticCampaignView:
    """Convert one stable typed map into the screenshot-equivalent ALAS View."""

    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed("semantic ALAS camera requires a typed map state")
    try:
        exact_center = tuple(float(item) for item in screen_center)
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed("semantic ALAS camera screen center is malformed") from exc
    if (
        len(exact_center) != 2
        or any(not math.isfinite(item) for item in exact_center)
        or not (0.0 <= exact_center[0] < 1280.0)
        or not (0.0 <= exact_center[1] < 720.0)
    ):
        raise SemanticGateClosed("semantic ALAS camera screen center is malformed")

    continuous, maximum_residual, rms_residual, projector = _fit_projective_camera(
        state, exact_center
    )
    camera = (math.floor(continuous[0]), math.floor(continuous[1]))
    center_offset = (
        continuous[0] - camera[0],
        continuous[1] - camera[1],
    )
    if not (
        0 < camera[0] < state.columns - 1
        and 0 < camera[1] < state.rows - 1
        and all(0.0 <= value < 1.0 for value in center_offset)
    ):
        raise SemanticGateClosed(
            "semantic ALAS camera edge observation is not qualified"
        )

    indexed = {(cell.row, cell.column): cell for cell in state.cells}
    horizontal = []
    vertical = []
    for (row, column), cell in indexed.items():
        right = indexed.get((row, column + 1))
        below = indexed.get((row + 1, column))
        if right is not None:
            horizontal.append(
                math.hypot(
                    right.point.x - cell.point.x,
                    right.point.y - cell.point.y,
                )
            )
        if below is not None:
            vertical.append(
                math.hypot(
                    below.point.x - cell.point.x,
                    below.point.y - cell.point.y,
                )
            )
    if not horizontal or not vertical:
        raise SemanticGateClosed("semantic ALAS camera swipe base is incomplete")
    swipe_base = (
        float(np.median(np.asarray(horizontal, dtype=float))),
        float(np.median(np.asarray(vertical, dtype=float))),
    )
    if any(not 40.0 <= value <= 240.0 for value in swipe_base):
        raise SemanticGateClosed("semantic ALAS camera swipe base is outside limits")

    target = None
    if target_node is not None:
        matches = tuple(cell for cell in state.cells if cell.node == target_node)
        if len(matches) != 1:
            raise SemanticGateClosed("semantic ALAS camera target is absent")
        target = matches[0]
    observation = AlasCampaignCameraViewObservation(
        generation=state.generation,
        stage_code=state.stage_code,
        camera_location=camera,
        camera_node=_node(camera),
        center_offset=center_offset,
        swipe_base=swipe_base,
        cell_count=len(state.cells),
        projective_maximum_residual=maximum_residual,
        projective_rms_residual=rms_residual,
        target_node=target_node,
        target_local_location=(
            None if target is None else (target.column - 1, target.row - 1)
        ),
        target_path=None if target is None else target.button_path,
        target_point=None if target is None else target.point,
        target_bounds=None if target is None else target.bounds,
    )
    return AlasSemanticCampaignView(
        state=state, observation=observation, projector=projector
    )


def install_alas_campaign_camera_view(
    campaign: Any,
    state: CampaignMapState,
    *,
    target_node: Optional[str] = None,
) -> AlasCampaignCameraViewObservation:
    """Install one typed View at ALAS's existing ``_update_view`` boundary."""

    config = getattr(campaign, "config", None)
    if config is None or not hasattr(config, "SCREEN_CENTER"):
        raise SemanticGateClosed("ALAS campaign camera config is incomplete")
    view = build_alas_campaign_camera_view(
        state,
        screen_center=config.SCREEN_CENTER,
        target_node=target_node,
    )
    campaign.view = view
    campaign.semantic_camera_view_observation = view.semantic_observation
    return view.semantic_observation
