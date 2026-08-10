"""Qualification-only live input for reviewed combat observer resources.

The canonical ALAS patch does not import this module.  It exists only so a
reviewed G20 action resource can be advanced during evidence acquisition after
two fresh, coherent endpoint triples prove the same exact Button.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Tuple

from .alas_combat_observer import (
    AlasCombatObserverManifest,
    prepare_alas_combat_resource_action,
)
from .alas_combat_trace import build_alas_combat_trace_frame
from .semantic_oracle import ActionReceipt, SemanticGateClosed


ALAS_COMBAT_RESOURCE_ACTION_COMMIT_SCHEMA = (
    "alas-headless.g23-combat-resource-action-commit/v1"
)


@dataclass(frozen=True)
class AlasCombatResourceActionCommit:
    """Receipt for one controlled ADB tap, not proof of its outcome."""

    resource_name: str
    pid: int
    first_generation: int
    commit_generation: int
    first_frame_sha256: str
    commit_frame_sha256: str
    mapping_evidence_sha256: str
    receipt: ActionReceipt


def _mapping_evidence(
    manifest: AlasCombatObserverManifest, resource_name: str
) -> str:
    matches = tuple(
        mapping
        for mapping in manifest.resources
        if mapping.resource_name == resource_name
    )
    if len(matches) != 1 or not matches[0].qualified:
        raise SemanticGateClosed("combat action resource is not qualified")
    return matches[0].evidence_sha256


def _read_action(
    bridge: Any,
    manifest: AlasCombatObserverManifest,
    resource_name: str,
) -> Tuple[Mapping[str, Any], Any, ActionReceipt]:
    snapshot_payload = bridge.request("GET /v1/snapshot\n")
    button_payload = bridge.request("GET /v1/buttons\n")
    ui_payload = bridge.request("GET /v1/ui\n")
    frame, snapshot = build_alas_combat_trace_frame(
        snapshot_payload, button_payload, ui_payload, manifest
    )
    receipt = prepare_alas_combat_resource_action(
        snapshot, manifest, resource_name
    )
    return frame, snapshot, receipt


def commit_alas_combat_resource_action_for_evidence(
    session: Any,
    manifest: AlasCombatObserverManifest,
    resource_name: str,
    *,
    expected_pid: int,
    minimum_generation: int,
    action_budget: int,
    settle_attempts: int = 20,
    settle_interval_seconds: float = 0.05,
    sleep: Callable[[float], None] = time.sleep,
) -> AlasCombatResourceActionCommit:
    """Inject exactly one reviewed combat-resource action for evidence.

    The explicit PID and generation floor bind this action to the preceding
    trace.  Two increasing snapshots must resolve to the same point, bounds,
    and exact Unity path.  No post-click state is inferred here.
    """

    if (
        isinstance(action_budget, bool)
        or not isinstance(action_budget, int)
        or action_budget != 1
    ):
        raise SemanticGateClosed("combat evidence action requires budget 1")
    if (
        isinstance(expected_pid, bool)
        or not isinstance(expected_pid, int)
        or expected_pid <= 0
    ):
        raise SemanticGateClosed("combat evidence PID is malformed")
    if (
        isinstance(minimum_generation, bool)
        or not isinstance(minimum_generation, int)
        or minimum_generation < 0
    ):
        raise SemanticGateClosed("combat evidence generation floor is malformed")
    if not 2 <= settle_attempts <= 100:
        raise SemanticGateClosed("combat evidence settle attempts are invalid")
    if not 0.01 <= settle_interval_seconds <= 1.0:
        raise SemanticGateClosed("combat evidence settle interval is invalid")
    if (
        getattr(session, "package", None) != manifest.package
        or getattr(session, "driver_revision", None) != manifest.driver_revision
    ):
        raise SemanticGateClosed("combat evidence session identity changed")

    session.open()  # includes the independent pinned-package fingerprint gate
    bridge = getattr(session, "bridge", None)
    component = getattr(session, "component", None)
    if bridge is None or not component:
        raise SemanticGateClosed("combat evidence session is incomplete")
    if bridge.pid != expected_pid:
        raise SemanticGateClosed("combat evidence process changed")
    if bridge.foreground_component() != component:
        raise SemanticGateClosed("combat evidence game is not top-resumed")

    first_frame, first_snapshot, first_receipt = _read_action(
        bridge, manifest, resource_name
    )
    if first_snapshot.oracle_state.snapshot.get("pid") != expected_pid:
        raise SemanticGateClosed("combat evidence snapshot process changed")
    if first_snapshot.generation <= minimum_generation:
        raise SemanticGateClosed("combat evidence generation did not advance")
    second_frame: Optional[Mapping[str, Any]] = None
    second_snapshot = None
    second_receipt: Optional[ActionReceipt] = None
    last_error: Optional[SemanticGateClosed] = None
    for _ in range(settle_attempts):
        sleep(settle_interval_seconds)
        try:
            candidate_frame, candidate_snapshot, candidate_receipt = _read_action(
                bridge, manifest, resource_name
            )
        except SemanticGateClosed as exc:
            last_error = exc
            continue
        if candidate_snapshot.generation <= first_snapshot.generation:
            continue
        if candidate_snapshot.oracle_state.snapshot.get("pid") != expected_pid:
            raise SemanticGateClosed("combat evidence snapshot process changed")
        second_frame = candidate_frame
        second_snapshot = candidate_snapshot
        second_receipt = candidate_receipt
        break
    if second_frame is None or second_snapshot is None or second_receipt is None:
        if last_error is not None:
            raise SemanticGateClosed(
                "combat evidence action did not obtain a second stable snapshot"
            ) from last_error
        raise SemanticGateClosed(
            "combat evidence action did not obtain an increasing generation"
        )
    if (
        first_receipt.semantic_id != second_receipt.semantic_id
        or first_receipt.path != second_receipt.path
        or first_receipt.point != second_receipt.point
        or first_receipt.bounds != second_receipt.bounds
    ):
        raise SemanticGateClosed("combat evidence action geometry changed")
    point = second_receipt.point
    width = second_snapshot.oracle_state.snapshot.get("width")
    height = second_snapshot.oracle_state.snapshot.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or isinstance(height, bool)
        or not isinstance(height, int)
        or not 0 <= point.x < width
        or not 0 <= point.y < height
    ):
        raise SemanticGateClosed("combat evidence action point is outside screen")
    if bridge.pid != expected_pid:
        raise SemanticGateClosed("combat evidence process changed before input")
    if bridge.foreground_component() != component:
        raise SemanticGateClosed("combat evidence foreground changed before input")

    bridge.tap(int(round(point.x)), int(round(point.y)))
    return AlasCombatResourceActionCommit(
        resource_name=resource_name,
        pid=expected_pid,
        first_generation=first_snapshot.generation,
        commit_generation=second_snapshot.generation,
        first_frame_sha256=str(first_frame["sha256"]),
        commit_frame_sha256=str(second_frame["sha256"]),
        mapping_evidence_sha256=_mapping_evidence(manifest, resource_name),
        receipt=second_receipt,
    )


def alas_combat_resource_action_commit_to_json(
    commit: AlasCombatResourceActionCommit,
) -> Mapping[str, Any]:
    if not isinstance(commit, AlasCombatResourceActionCommit):
        raise SemanticGateClosed("combat evidence action commit is not typed")
    receipt = commit.receipt
    return {
        "schema": ALAS_COMBAT_RESOURCE_ACTION_COMMIT_SCHEMA,
        "resource_name": commit.resource_name,
        "pid": commit.pid,
        "first_generation": commit.first_generation,
        "commit_generation": commit.commit_generation,
        "first_frame_sha256": commit.first_frame_sha256,
        "commit_frame_sha256": commit.commit_frame_sha256,
        "mapping_evidence_sha256": commit.mapping_evidence_sha256,
        "semantic_id": receipt.semantic_id,
        "path": receipt.path,
        "point": {"x": receipt.point.x, "y": receipt.point.y},
        "bounds": {
            "left": receipt.bounds.left,
            "top": receipt.bounds.top,
            "right": receipt.bounds.right,
            "bottom": receipt.bounds.bottom,
        },
        "controlled_input_injected": True,
        "outcome_verified": False,
    }
