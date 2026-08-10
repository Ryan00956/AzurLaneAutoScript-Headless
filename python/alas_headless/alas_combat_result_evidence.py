"""Repeated raw-Unity evidence for passive alternate combat result pages.

The qualified S-grade mappings provide structural hypotheses for A-D battle
grades and A/B statistics pages.  A hypothesis becomes a review draft only
after every exact selector is present in at least three adjacent raw samples.
This module never applies the draft and never performs input.
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
    alas_combat_unity_selector_present,
    alas_combat_unity_selector_to_json,
    validate_alas_combat_observer_snapshot,
)
from .alas_combat_trace import AlasCombatObserverTrace, AlasCombatObserverTraceSample
from .semantic_oracle import Bounds, ButtonState, SemanticGateClosed


ALAS_COMBAT_RESULT_SURFACE_EVIDENCE_SCHEMA = (
    "alas-headless.g30-combat-result-surface-evidence/v1"
)
ALAS_COMBAT_RESULT_SURFACE_VERIFICATION_SCHEMA = (
    "alas-headless.g30-combat-result-surface-verification/v1"
)
ALAS_COMBAT_RESULT_CONTROL_EVIDENCE_SCHEMA = (
    "alas-headless.g32-combat-result-control-evidence/v1"
)
ALAS_COMBAT_RESULT_CONTROL_VERIFICATION_SCHEMA = (
    "alas-headless.g32-combat-result-control-verification/v1"
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class AlasCombatResultSurfaceProfile:
    profile_id: str
    resource_name: str
    action_name: str
    reference_resource_name: str
    selectors: Tuple[AlasCombatUnitySelector, ...]
    action_selector: AlasCombatUnitySelector


_RESULT_ROOT = "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
_GRADE_PAGE = _RESULT_ROOT + "NewBattleResultGradePage(Clone)"
_STATS_PAGE = _RESULT_ROOT + "NewBattleResultStatisticsPage(Clone)"


def _button(path: str, name: str) -> AlasCombatUnitySelector:
    return AlasCombatUnitySelector(
        AlasCombatUnityRecordKind.BUTTON,
        path,
        name,
        require_top_raycast=True,
    )


def _image(path: str, name: str, sprite: str) -> AlasCombatUnitySelector:
    return AlasCombatUnitySelector(
        AlasCombatUnityRecordKind.IMAGE,
        path,
        name,
        sprite=sprite,
    )


def _text(path: str, name: str, text: str) -> AlasCombatUnitySelector:
    return AlasCombatUnitySelector(
        AlasCombatUnityRecordKind.TEXT,
        path,
        name,
        text=text,
    )


_BATTLE_ACTION = _button(_GRADE_PAGE, "NewBattleResultGradePage(Clone)")
_EXP_ACTION = _button(_STATS_PAGE + "/bottom/confirmBtn", "confirmBtn")


def _battle_profile(grade: str) -> AlasCombatResultSurfaceProfile:
    name = "BATTLE_STATUS_" + grade
    return AlasCombatResultSurfaceProfile(
        "battle-status-" + grade.lower(),
        name,
        name,
        "BATTLE_STATUS_S",
        (
            _BATTLE_ACTION,
            _image(_GRADE_PAGE + "/bg/grade/icon", "icon", "letter_" + grade),
            _image(_GRADE_PAGE + "/bg/grade/Text", "Text", "label_" + grade),
            _text(
                _GRADE_PAGE + "/bg/ResultEffect/Tips/dianjijixu/bg20",
                "bg20",
                "点击继续",
            ),
        ),
        _BATTLE_ACTION,
    )


def _exp_profile(grade: str) -> AlasCombatResultSurfaceProfile:
    name = "EXP_INFO_" + grade
    return AlasCombatResultSurfaceProfile(
        "exp-info-" + grade.lower(),
        name,
        name,
        "EXP_INFO_S",
        (
            _EXP_ACTION,
            _image(
                _STATS_PAGE + "/bottom/confirmBtn",
                "confirmBtn",
                "btn_big_yellow",
            ),
            _image(_STATS_PAGE + "/top/grade/icon", "icon", "letter_" + grade),
            _image(_STATS_PAGE + "/top/grade/Text", "Text", "label_" + grade),
            _text(
                _STATS_PAGE + "/bottom/confirmBtn/Text",
                "Text",
                "确 定",
            ),
        ),
        _EXP_ACTION,
    )


ALAS_COMBAT_RESULT_SURFACE_PROFILES = tuple(
    _battle_profile(grade) for grade in ("A", "B", "C", "D")
) + tuple(_exp_profile(grade) for grade in ("A", "B"))

ALAS_COMBAT_RESULT_CONTROL_PROFILES = (
    _battle_profile("S"),
    _exp_profile("S"),
)


def _profile(profile_id: str) -> AlasCombatResultSurfaceProfile:
    matches = tuple(
        profile
        for profile in ALAS_COMBAT_RESULT_SURFACE_PROFILES
        if profile.profile_id == profile_id
    )
    if len(matches) != 1:
        raise SemanticGateClosed("combat result surface profile is unknown")
    return matches[0]


def _validate_reference_contract(
    manifest: AlasCombatObserverManifest,
    profile: AlasCombatResultSurfaceProfile,
) -> None:
    expected = (
        _battle_profile("S")
        if profile.reference_resource_name == "BATTLE_STATUS_S"
        else _exp_profile("S")
    )
    resources = tuple(
        mapping
        for mapping in manifest.resources
        if mapping.resource_name == profile.reference_resource_name
    )
    actions = tuple(
        mapping
        for mapping in manifest.actions
        if mapping.action_name == profile.reference_resource_name
    )
    if (
        len(resources) != 1
        or not resources[0].qualified
        or not all(
            selector in resources[0].selectors for selector in expected.selectors
        )
        or len(actions) != 1
        or not actions[0].qualified
        or len(actions[0].resolved_variants) != 1
        or actions[0].resolved_variants[0].selectors
        != (expected.action_selector,)
    ):
        raise SemanticGateClosed(
            "combat result reference S mapping changed or is unqualified"
        )


def _profile_visible(
    sample: AlasCombatObserverTraceSample,
    profile: AlasCombatResultSurfaceProfile,
) -> bool:
    action = _action_button(sample, profile.action_selector)
    if action is None or not action.actionable:
        return False
    return all(
        alas_combat_unity_selector_present(sample.snapshot, selector)
        for selector in profile.selectors
        if selector != profile.action_selector
    )


def _action_button(
    sample: AlasCombatObserverTraceSample,
    selector: AlasCombatUnitySelector,
) -> Optional[ButtonState]:
    matches = tuple(
        button
        for button in sample.snapshot.oracle_state.buttons
        if button.path == selector.path and button.name == selector.name
    )
    if len(matches) > 1:
        raise SemanticGateClosed("combat result action Button is ambiguous")
    if not matches:
        return None
    return matches[0]


def _action_geometry_stable(
    selected: Sequence[AlasCombatObserverTraceSample],
    selector: AlasCombatUnitySelector,
    *,
    tolerance: float = 2.0,
) -> bool:
    buttons = tuple(_action_button(sample, selector) for sample in selected)
    if any(button is None or button.bounds is None for button in buttons):
        return False
    bounds = tuple(
        button.bounds
        for button in buttons
        if button is not None and button.bounds is not None
    )
    for field in ("left", "top", "right", "bottom"):
        values = tuple(getattr(item, field) for item in bounds)
        if max(values) - min(values) > tolerance:
            return False
    return True


def _bounds_json(bounds: Bounds) -> Mapping[str, float]:
    return {
        "left": bounds.left,
        "top": bounds.top,
        "right": bounds.right,
        "bottom": bounds.bottom,
    }


def analyze_alas_combat_result_surface_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    *,
    profile_id: str,
    source_trace_sha256: str,
    minimum_consecutive_frames: int = 3,
    context_frames: int = 2,
) -> Mapping[str, Any]:
    """Emit one deterministic, non-applying review draft if evidence exists."""

    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("combat result surface trace is not typed")
    if (
        trace.package != manifest.package
        or trace.driver_revision != manifest.driver_revision
        or trace.game_fingerprint != manifest.game_fingerprint
    ):
        raise SemanticGateClosed("combat result surface identity changed")
    if (
        not isinstance(source_trace_sha256, str)
        or _SHA256_PATTERN.fullmatch(source_trace_sha256) is None
    ):
        raise SemanticGateClosed("combat result surface trace hash is malformed")
    if (
        isinstance(minimum_consecutive_frames, bool)
        or not isinstance(minimum_consecutive_frames, int)
        or not 3 <= minimum_consecutive_frames <= 20
    ):
        raise SemanticGateClosed("combat result frame threshold is malformed")
    if (
        isinstance(context_frames, bool)
        or not isinstance(context_frames, int)
        or not 0 <= context_frames <= 10
    ):
        raise SemanticGateClosed("combat result context threshold is malformed")
    profile = _profile(profile_id)
    _validate_reference_contract(manifest, profile)
    for sample in trace.samples:
        validate_alas_combat_observer_snapshot(sample.snapshot, manifest)

    visible = tuple(
        not alas_combat_active_blocker_names(sample.snapshot, manifest)
        and _profile_visible(sample, profile)
        for sample in trace.samples
    )
    ambiguous_generations = []
    for sample, target_visible in zip(trace.samples, visible):
        if not target_visible:
            continue
        competing = tuple(
            candidate.profile_id
            for candidate in ALAS_COMBAT_RESULT_SURFACE_PROFILES
            if candidate.profile_id != profile.profile_id
            and _profile_visible(sample, candidate)
        )
        if competing:
            ambiguous_generations.append(sample.snapshot.generation)

    selected_index = None
    for start in range(len(trace.samples) - minimum_consecutive_frames + 1):
        selected = trace.samples[
            start : start + minimum_consecutive_frames
        ]
        if not all(visible[start : start + minimum_consecutive_frames]):
            continue
        if any(
            sample.snapshot.generation in ambiguous_generations
            for sample in selected
        ):
            continue
        if not _action_geometry_stable(selected, profile.action_selector):
            continue
        selected_index = start
        break

    selected: Tuple[AlasCombatObserverTraceSample, ...] = ()
    if selected_index is not None:
        selected = trace.samples[
            selected_index : selected_index + minimum_consecutive_frames
        ]
    before = ()
    after = ()
    if selected_index is not None:
        before = trace.samples[max(0, selected_index - context_frames) : selected_index]
        after_start = selected_index + minimum_consecutive_frames
        after = trace.samples[after_start : after_start + context_frames]

    action_bounds = None
    if selected:
        action = _action_button(selected[0], profile.action_selector)
        assert action is not None and action.bounds is not None
        action_bounds = _bounds_json(action.bounds)
    review_draft = None
    if selected:
        review_draft = {
            "schema": ALAS_COMBAT_MAPPING_REVIEW_SCHEMA,
            "review_id": "g30-" + profile.profile_id,
            "trace_sha256": source_trace_sha256,
            "generations": [sample.snapshot.generation for sample in selected],
            "resources": [
                {
                    "resource_name": profile.resource_name,
                    "selectors": [
                        alas_combat_unity_selector_to_json(selector)
                        for selector in profile.selectors
                    ],
                }
            ],
            "actions": [
                {
                    "action_name": profile.action_name,
                    "variant_id": "default",
                    "selectors": [
                        alas_combat_unity_selector_to_json(
                            profile.action_selector
                        )
                    ],
                }
            ],
            "branch_review_complete": False,
            "blockers": [],
            "blocker_review_complete": False,
        }

    return {
        "schema": ALAS_COMBAT_RESULT_SURFACE_EVIDENCE_SCHEMA,
        "profile_id": profile.profile_id,
        "resource_name": profile.resource_name,
        "action_name": profile.action_name,
        "reference_resource_name": profile.reference_resource_name,
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
        "selectors": [
            alas_combat_unity_selector_to_json(selector)
            for selector in profile.selectors
        ],
        "action_bounds": action_bounds,
        "review_required": True,
        "review_draft": review_draft,
    }


def verify_alas_combat_result_surface_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    record: Any,
    *,
    source_trace_sha256: str,
) -> Mapping[str, Any]:
    if not isinstance(record, dict):
        raise SemanticGateClosed("combat result surface evidence is malformed")
    required = {
        "schema",
        "profile_id",
        "resource_name",
        "action_name",
        "reference_resource_name",
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
        "selectors",
        "action_bounds",
        "review_required",
        "review_draft",
    }
    if set(record) != required:
        raise SemanticGateClosed("combat result surface evidence schema changed")
    if record["schema"] != ALAS_COMBAT_RESULT_SURFACE_EVIDENCE_SCHEMA:
        raise SemanticGateClosed("combat result surface evidence version changed")
    if record["source_trace_sha256"] != source_trace_sha256:
        raise SemanticGateClosed("combat result surface evidence trace hash changed")
    expected = analyze_alas_combat_result_surface_evidence(
        manifest,
        trace,
        profile_id=record["profile_id"],
        source_trace_sha256=source_trace_sha256,
        minimum_consecutive_frames=record["minimum_consecutive_frames"],
        context_frames=record["context_frames"],
    )
    if record != expected:
        raise SemanticGateClosed("combat result surface evidence record changed")
    return {
        "schema": ALAS_COMBAT_RESULT_SURFACE_VERIFICATION_SCHEMA,
        "passed": True,
        "profile_id": record["profile_id"],
        "evidence_complete": record["evidence_complete"],
        "selected_frame_count": len(record["selected_generations"]),
        "input_injected": False,
        "auto_promoted": False,
    }


def _control_profile(profile_id: str) -> AlasCombatResultSurfaceProfile:
    matches = tuple(
        profile
        for profile in ALAS_COMBAT_RESULT_CONTROL_PROFILES
        if profile.profile_id == profile_id
    )
    if len(matches) != 1:
        raise SemanticGateClosed("combat result control profile is unknown")
    return matches[0]


def analyze_alas_combat_result_control_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    *,
    profile_id: str,
    source_trace_sha256: str,
    minimum_consecutive_frames: int = 3,
) -> Mapping[str, Any]:
    """Re-prove an already-qualified S page in one read-only live trace.

    Unlike the G30 alternate-grade analyzer, this emits no mapping draft.  It
    is a positive control binding a controlled episode to the checked-in S
    selectors and their stable action geometry.
    """

    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("combat result control trace is not typed")
    if (
        trace.package != manifest.package
        or trace.driver_revision != manifest.driver_revision
        or trace.game_fingerprint != manifest.game_fingerprint
    ):
        raise SemanticGateClosed("combat result control identity changed")
    if (
        not isinstance(source_trace_sha256, str)
        or _SHA256_PATTERN.fullmatch(source_trace_sha256) is None
    ):
        raise SemanticGateClosed("combat result control trace hash is malformed")
    if (
        isinstance(minimum_consecutive_frames, bool)
        or not isinstance(minimum_consecutive_frames, int)
        or not 3 <= minimum_consecutive_frames <= 20
    ):
        raise SemanticGateClosed("combat result control frame threshold is malformed")
    profile = _control_profile(profile_id)
    _validate_reference_contract(manifest, profile)
    for sample in trace.samples:
        validate_alas_combat_observer_snapshot(sample.snapshot, manifest)

    visible = tuple(
        not alas_combat_active_blocker_names(sample.snapshot, manifest)
        and _profile_visible(sample, profile)
        for sample in trace.samples
    )
    selected: Tuple[AlasCombatObserverTraceSample, ...] = ()
    for start in range(len(trace.samples) - minimum_consecutive_frames + 1):
        candidate = trace.samples[start : start + minimum_consecutive_frames]
        if not all(visible[start : start + minimum_consecutive_frames]):
            continue
        if any(
            _profile_visible(sample, alternate)
            for sample in candidate
            for alternate in ALAS_COMBAT_RESULT_SURFACE_PROFILES
        ):
            continue
        if not _action_geometry_stable(candidate, profile.action_selector):
            continue
        selected = candidate
        break

    action_bounds = None
    if selected:
        action = _action_button(selected[0], profile.action_selector)
        assert action is not None and action.bounds is not None
        action_bounds = _bounds_json(action.bounds)
    return {
        "schema": ALAS_COMBAT_RESULT_CONTROL_EVIDENCE_SCHEMA,
        "profile_id": profile.profile_id,
        "resource_name": profile.resource_name,
        "action_name": profile.action_name,
        "package": trace.package,
        "driver_revision": trace.driver_revision,
        "game_fingerprint": trace.game_fingerprint,
        "pid": trace.pid,
        "source_trace_sha256": source_trace_sha256,
        "minimum_consecutive_frames": minimum_consecutive_frames,
        "input_injected": False,
        "already_qualified": True,
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
        "action_bounds": action_bounds,
        "review_draft": None,
        "auto_promoted": False,
    }


def verify_alas_combat_result_control_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    record: Any,
    *,
    source_trace_sha256: str,
) -> Mapping[str, Any]:
    if not isinstance(record, dict):
        raise SemanticGateClosed("combat result control evidence is malformed")
    if record.get("schema") != ALAS_COMBAT_RESULT_CONTROL_EVIDENCE_SCHEMA:
        raise SemanticGateClosed("combat result control evidence version changed")
    expected = analyze_alas_combat_result_control_evidence(
        manifest,
        trace,
        profile_id=record.get("profile_id"),
        source_trace_sha256=source_trace_sha256,
        minimum_consecutive_frames=record.get("minimum_consecutive_frames"),
    )
    if record != expected:
        raise SemanticGateClosed("combat result control evidence record changed")
    return {
        "schema": ALAS_COMBAT_RESULT_CONTROL_VERIFICATION_SCHEMA,
        "passed": True,
        "profile_id": record["profile_id"],
        "evidence_complete": record["evidence_complete"],
        "selected_frame_count": len(record["selected_generations"]),
        "input_injected": False,
        "auto_promoted": False,
    }


def audit_alas_combat_result_surface_mappings(
    manifest: AlasCombatObserverManifest,
) -> Mapping[str, bool]:
    resources = {item.resource_name: item.qualified for item in manifest.resources}
    actions = {item.action_name: item.qualified for item in manifest.actions}
    result: Dict[str, bool] = {}
    for profile in ALAS_COMBAT_RESULT_SURFACE_PROFILES:
        result[profile.profile_id] = resources.get(
            profile.resource_name, False
        ) and actions.get(profile.action_name, False)
    return result
