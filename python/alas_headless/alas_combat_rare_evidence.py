"""Read-only repeated evidence for rare original-ALAS combat branches.

G28 proves branch ownership with virtual observations.  This module handles the
next boundary: finding one stable pair of real Unity controls in a raw observer
trace.  It emits a review draft, but it never changes the combat manifest,
imports ALAS, or performs Android input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .alas_combat_mapping_review import ALAS_COMBAT_MAPPING_REVIEW_SCHEMA
from .alas_combat_observer import (
    AlasCombatObserverManifest,
    AlasCombatUnityRecordKind,
    AlasCombatUnitySelector,
    alas_combat_active_blocker_names,
    alas_combat_unity_selector_to_json,
    validate_alas_combat_observer_snapshot,
)
from .alas_combat_trace import AlasCombatObserverTrace, AlasCombatObserverTraceSample
from .semantic_oracle import Bounds, ButtonState, SemanticGateClosed


ALAS_COMBAT_RARE_SURFACE_EVIDENCE_SCHEMA = (
    "alas-headless.g29-combat-rare-surface-evidence/v1"
)
ALAS_COMBAT_RARE_SURFACE_VERIFICATION_SCHEMA = (
    "alas-headless.g29-combat-rare-surface-verification/v1"
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class AlasCombatRareControlSpec:
    role: str
    resource_name: str
    action_name: str
    reference_bounds: Bounds
    exact_path: str = ""
    exact_name: str = ""


@dataclass(frozen=True)
class AlasCombatRareSurfaceProfile:
    profile_id: str
    controls: Tuple[AlasCombatRareControlSpec, AlasCombatRareControlSpec]


_GUILD_ROOT = "OverlayCamera/Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/"
ALAS_COMBAT_RARE_SURFACE_PROFILES = (
    AlasCombatRareSurfaceProfile(
        "guild-popup",
        (
            AlasCombatRareControlSpec(
                "cancel",
                "GUILD_POPUP_CANCEL",
                "GUILD_POPUP_CANCEL",
                Bounds(422.0, 449.0, 623.0, 486.0),
                _GUILD_ROOT + "cancel_btn",
                "cancel_btn",
            ),
            AlasCombatRareControlSpec(
                "confirm",
                "GUILD_POPUP_CONFIRM",
                "GUILD_POPUP_CONFIRM",
                Bounds(655.0, 450.0, 856.0, 487.0),
                _GUILD_ROOT + "confirm_btn",
                "confirm_btn",
            ),
        ),
    ),
    AlasCombatRareSurfaceProfile(
        "mission-popup",
        (
            AlasCombatRareControlSpec(
                "acknowledge",
                "MISSION_POPUP_ACK",
                "MISSION_POPUP_ACK",
                Bounds(432.0, 493.0, 543.0, 533.0),
            ),
            AlasCombatRareControlSpec(
                "go",
                "MISSION_POPUP_GO",
                "MISSION_POPUP_GO",
                Bounds(719.0, 493.0, 861.0, 534.0),
            ),
        ),
    ),
)


def _profile(profile_id: str) -> AlasCombatRareSurfaceProfile:
    matches = tuple(
        profile
        for profile in ALAS_COMBAT_RARE_SURFACE_PROFILES
        if profile.profile_id == profile_id
    )
    if len(matches) != 1:
        raise SemanticGateClosed("rare combat surface profile is unknown")
    return matches[0]


def _area(bounds: Bounds) -> float:
    return max(0.0, bounds.right - bounds.left) * max(
        0.0, bounds.bottom - bounds.top
    )


def _reference_coverage(observed: Bounds, reference: Bounds) -> float:
    intersection = Bounds(
        max(observed.left, reference.left),
        max(observed.top, reference.top),
        min(observed.right, reference.right),
        min(observed.bottom, reference.bottom),
    )
    denominator = _area(reference)
    return _area(intersection) / denominator if denominator else 0.0


def _common_ancestor(left: str, right: str) -> str:
    common = []
    for left_part, right_part in zip(left.split("/"), right.split("/")):
        if left_part != right_part:
            break
        common.append(left_part)
    return "/".join(common)


def _control_candidates(
    sample: AlasCombatObserverTraceSample,
    spec: AlasCombatRareControlSpec,
) -> Tuple[ButtonState, ...]:
    candidates = []
    for button in sample.snapshot.oracle_state.buttons:
        if not button.actionable or button.bounds is None:
            continue
        if spec.exact_path:
            if button.path != spec.exact_path or button.name != spec.exact_name:
                continue
            minimum_coverage = 0.50
        else:
            minimum_coverage = 0.65
        if _reference_coverage(button.bounds, spec.reference_bounds) < minimum_coverage:
            continue
        candidates.append(button)
    return tuple(candidates)


def _frame_controls(
    sample: AlasCombatObserverTraceSample,
    profile: AlasCombatRareSurfaceProfile,
) -> Tuple[Optional[Tuple[ButtonState, ButtonState]], bool]:
    per_control = tuple(
        _control_candidates(sample, spec) for spec in profile.controls
    )
    ambiguous = any(len(items) > 1 for items in per_control)
    if ambiguous or any(len(items) != 1 for items in per_control):
        return None, ambiguous
    left, right = per_control[0][0], per_control[1][0]
    if left.path == right.path:
        return None, True
    ancestor = _common_ancestor(left.path, right.path)
    if len(ancestor.split("/")) < 4:
        return None, True
    return (left, right), False


def _identity(controls: Sequence[ButtonState]) -> Tuple[Tuple[str, str], ...]:
    return tuple((control.path, control.name) for control in controls)


def _geometry_stable(
    controls: Sequence[Sequence[ButtonState]], *, tolerance: float = 2.0
) -> bool:
    for position in range(2):
        bounds = tuple(items[position].bounds for items in controls)
        if any(item is None for item in bounds):
            return False
        assert all(item is not None for item in bounds)
        for field in ("left", "top", "right", "bottom"):
            values = tuple(getattr(item, field) for item in bounds if item is not None)
            if max(values) - min(values) > tolerance:
                return False
    return True


def _selector(button: ButtonState) -> AlasCombatUnitySelector:
    return AlasCombatUnitySelector(
        AlasCombatUnityRecordKind.BUTTON,
        button.path,
        button.name,
        require_top_raycast=True,
    )


def _bounds_json(bounds: Bounds) -> Mapping[str, float]:
    return {
        "left": bounds.left,
        "top": bounds.top,
        "right": bounds.right,
        "bottom": bounds.bottom,
    }


def analyze_alas_combat_rare_surface_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    *,
    profile_id: str,
    source_trace_sha256: str,
    minimum_consecutive_frames: int = 3,
    context_frames: int = 2,
) -> Mapping[str, Any]:
    """Find one stable control pair and emit a non-applying review draft."""

    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("rare combat surface trace is not typed")
    if (
        trace.package != manifest.package
        or trace.driver_revision != manifest.driver_revision
        or trace.game_fingerprint != manifest.game_fingerprint
    ):
        raise SemanticGateClosed("rare combat surface identity changed")
    if (
        not isinstance(source_trace_sha256, str)
        or _SHA256_PATTERN.fullmatch(source_trace_sha256) is None
    ):
        raise SemanticGateClosed("rare combat surface trace hash is malformed")
    if (
        isinstance(minimum_consecutive_frames, bool)
        or not isinstance(minimum_consecutive_frames, int)
        or not 3 <= minimum_consecutive_frames <= 20
    ):
        raise SemanticGateClosed("rare combat surface frame threshold is malformed")
    if (
        isinstance(context_frames, bool)
        or not isinstance(context_frames, int)
        or not 0 <= context_frames <= 10
    ):
        raise SemanticGateClosed("rare combat surface context threshold is malformed")
    profile = _profile(profile_id)
    for sample in trace.samples:
        validate_alas_combat_observer_snapshot(sample.snapshot, manifest)

    matched = []
    ambiguous_generations = []
    for sample in trace.samples:
        if alas_combat_active_blocker_names(sample.snapshot, manifest):
            controls, ambiguous = None, False
        else:
            controls, ambiguous = _frame_controls(sample, profile)
        matched.append(controls)
        if ambiguous:
            ambiguous_generations.append(sample.snapshot.generation)

    selected_index = None
    for start in range(len(trace.samples) - minimum_consecutive_frames + 1):
        window = matched[start : start + minimum_consecutive_frames]
        if any(items is None for items in window):
            continue
        typed_window = tuple(items for items in window if items is not None)
        identities = tuple(_identity(items) for items in typed_window)
        if len(set(identities)) != 1 or not _geometry_stable(typed_window):
            continue
        selected_index = start
        break

    selected: Tuple[AlasCombatObserverTraceSample, ...] = ()
    selected_controls: Tuple[Tuple[ButtonState, ButtonState], ...] = ()
    if selected_index is not None:
        selected = trace.samples[
            selected_index : selected_index + minimum_consecutive_frames
        ]
        selected_controls = tuple(
            items
            for items in matched[
                selected_index : selected_index + minimum_consecutive_frames
            ]
            if items is not None
        )

    controls_json = []
    review_draft = None
    if selected:
        first_controls = selected_controls[0]
        selectors = tuple(_selector(control) for control in first_controls)
        for spec, selector, control in zip(
            profile.controls, selectors, first_controls
        ):
            assert control.bounds is not None
            controls_json.append(
                {
                    "role": spec.role,
                    "resource_name": spec.resource_name,
                    "action_name": spec.action_name,
                    "selector": alas_combat_unity_selector_to_json(selector),
                    "reference_bounds": _bounds_json(spec.reference_bounds),
                    "observed_bounds": _bounds_json(control.bounds),
                    "identity_was_pinned_before_capture": bool(spec.exact_path),
                }
            )
        generations = [sample.snapshot.generation for sample in selected]
        review_draft = {
            "schema": ALAS_COMBAT_MAPPING_REVIEW_SCHEMA,
            "review_id": "g29-" + profile.profile_id,
            "trace_sha256": source_trace_sha256,
            "generations": generations,
            "resources": [
                {
                    "resource_name": spec.resource_name,
                    "selectors": [alas_combat_unity_selector_to_json(selector)],
                }
                for spec, selector in zip(profile.controls, selectors)
            ],
            "actions": [
                {
                    "action_name": spec.action_name,
                    "variant_id": "default",
                    "selectors": [alas_combat_unity_selector_to_json(selector)],
                }
                for spec, selector in zip(profile.controls, selectors)
            ],
            "branch_review_complete": False,
            "blockers": [],
            "blocker_review_complete": False,
        }

    before = ()
    after = ()
    if selected_index is not None:
        before = trace.samples[max(0, selected_index - context_frames) : selected_index]
        after_start = selected_index + minimum_consecutive_frames
        after = trace.samples[after_start : after_start + context_frames]
    return {
        "schema": ALAS_COMBAT_RARE_SURFACE_EVIDENCE_SCHEMA,
        "profile_id": profile.profile_id,
        "package": trace.package,
        "driver_revision": trace.driver_revision,
        "game_fingerprint": trace.game_fingerprint,
        "pid": trace.pid,
        "source_trace_sha256": source_trace_sha256,
        "minimum_consecutive_frames": minimum_consecutive_frames,
        "context_frames": context_frames,
        "input_injected": False,
        "auto_promoted": False,
        "evidence_complete": bool(selected),
        "selected_generations": [
            sample.snapshot.generation for sample in selected
        ],
        "source_frames": [
            {
                "sequence": sample.sequence,
                "generation": sample.snapshot.generation,
                "frame_sha256": sample.frame["sha256"],
            }
            for sample in selected
        ],
        "context_before_generations": [
            sample.snapshot.generation for sample in before
        ],
        "context_after_generations": [
            sample.snapshot.generation for sample in after
        ],
        "ambiguous_generations": ambiguous_generations,
        "controls": controls_json,
        "review_required": True,
        "review_draft": review_draft,
    }


def verify_alas_combat_rare_surface_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    record: Any,
    *,
    source_trace_sha256: str,
) -> Mapping[str, Any]:
    if not isinstance(record, dict):
        raise SemanticGateClosed("rare combat surface evidence is malformed")
    required = {
        "schema",
        "profile_id",
        "package",
        "driver_revision",
        "game_fingerprint",
        "pid",
        "source_trace_sha256",
        "minimum_consecutive_frames",
        "context_frames",
        "input_injected",
        "auto_promoted",
        "evidence_complete",
        "selected_generations",
        "source_frames",
        "context_before_generations",
        "context_after_generations",
        "ambiguous_generations",
        "controls",
        "review_required",
        "review_draft",
    }
    if set(record) != required:
        raise SemanticGateClosed("rare combat surface evidence schema changed")
    if record["schema"] != ALAS_COMBAT_RARE_SURFACE_EVIDENCE_SCHEMA:
        raise SemanticGateClosed("rare combat surface evidence version changed")
    if record["source_trace_sha256"] != source_trace_sha256:
        raise SemanticGateClosed("rare combat surface evidence trace hash changed")
    expected = analyze_alas_combat_rare_surface_evidence(
        manifest,
        trace,
        profile_id=record["profile_id"],
        source_trace_sha256=source_trace_sha256,
        minimum_consecutive_frames=record["minimum_consecutive_frames"],
        context_frames=record["context_frames"],
    )
    if record != expected:
        raise SemanticGateClosed("rare combat surface evidence record changed")
    return {
        "schema": ALAS_COMBAT_RARE_SURFACE_VERIFICATION_SCHEMA,
        "passed": True,
        "profile_id": record["profile_id"],
        "evidence_complete": record["evidence_complete"],
        "selected_frame_count": len(record["selected_generations"]),
        "input_injected": False,
        "auto_promoted": False,
    }


def audit_alas_combat_rare_surface_mappings(
    manifest: AlasCombatObserverManifest,
) -> Mapping[str, bool]:
    resources = {item.resource_name: item.qualified for item in manifest.resources}
    actions = {item.action_name: item.qualified for item in manifest.actions}
    result: Dict[str, bool] = {}
    for profile in ALAS_COMBAT_RARE_SURFACE_PROFILES:
        result[profile.profile_id] = all(
            resources.get(control.resource_name, False)
            and actions.get(control.action_name, False)
            for control in profile.controls
        )
    return result
