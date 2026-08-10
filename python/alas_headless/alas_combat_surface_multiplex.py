"""One read-only evidence pass across every G29/G30 combat surface profile."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Tuple

from .alas_combat_observer import AlasCombatObserverManifest, AlasCombatObserverSnapshot
from .alas_combat_rare_evidence import (
    ALAS_COMBAT_RARE_SURFACE_PROFILES,
    analyze_alas_combat_rare_surface_evidence,
)
from .alas_combat_result_evidence import (
    ALAS_COMBAT_RESULT_SURFACE_PROFILES,
    analyze_alas_combat_result_surface_evidence,
)
from .alas_combat_trace import AlasCombatObserverTrace
from .semantic_oracle import Bounds, SemanticGateClosed


ALAS_COMBAT_SURFACE_MULTIPLEX_EVIDENCE_SCHEMA = (
    "alas-headless.g31-combat-surface-multiplex-evidence/v1"
)
ALAS_COMBAT_SURFACE_MULTIPLEX_VERIFICATION_SCHEMA = (
    "alas-headless.g31-combat-surface-multiplex-verification/v1"
)
ALAS_COMBAT_SURFACE_MULTIPLEX_PROFILE_IDS = tuple(
    profile.profile_id for profile in ALAS_COMBAT_RARE_SURFACE_PROFILES
) + tuple(profile.profile_id for profile in ALAS_COMBAT_RESULT_SURFACE_PROFILES)
_DIALOG_PROFILE_IDS = frozenset(
    profile.profile_id for profile in ALAS_COMBAT_RARE_SURFACE_PROFILES
)
_RESULT_SPRITES = frozenset(
    prefix + grade
    for prefix in ("letter_", "label_")
    for grade in ("A", "B", "C", "D")
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def alas_combat_surface_multiplex_candidate_present(
    snapshot: AlasCombatObserverSnapshot,
) -> bool:
    """Cheap prefilter; false skips repeated full-trace analysis, not capture."""

    if not isinstance(snapshot, AlasCombatObserverSnapshot):
        raise SemanticGateClosed("combat surface multiplex snapshot is not typed")
    if any(
        image.active_in_hierarchy
        and image.active_and_enabled
        and not image.truncated
        and image.sprite in _RESULT_SPRITES
        for image in snapshot.ui_state.images
    ):
        return True
    actionable = tuple(
        button for button in snapshot.oracle_state.buttons if button.actionable
    )
    guild = next(
        profile
        for profile in ALAS_COMBAT_RARE_SURFACE_PROFILES
        if profile.profile_id == "guild-popup"
    )
    if all(
        any(
            button.path == control.exact_path
            and button.name == control.exact_name
            for button in actionable
        )
        for control in guild.controls
    ):
        return True
    mission = next(
        profile
        for profile in ALAS_COMBAT_RARE_SURFACE_PROFILES
        if profile.profile_id == "mission-popup"
    )
    return all(
        any(
            button.bounds is not None
            and _reference_coverage(button.bounds, control.reference_bounds) >= 0.65
            for button in actionable
        )
        for control in mission.controls
    )


def analyze_alas_combat_surface_multiplex_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    *,
    source_trace_sha256: str,
    minimum_consecutive_frames: int = 3,
    context_frames: int = 2,
) -> Mapping[str, Any]:
    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("combat surface multiplex trace is not typed")
    if (
        not isinstance(source_trace_sha256, str)
        or _SHA256_PATTERN.fullmatch(source_trace_sha256) is None
    ):
        raise SemanticGateClosed("combat surface multiplex trace hash is malformed")
    results = []
    drafts = {}
    for profile_id in ALAS_COMBAT_SURFACE_MULTIPLEX_PROFILE_IDS:
        analyzer = (
            analyze_alas_combat_rare_surface_evidence
            if profile_id in _DIALOG_PROFILE_IDS
            else analyze_alas_combat_result_surface_evidence
        )
        record = analyzer(
            manifest,
            trace,
            profile_id=profile_id,
            source_trace_sha256=source_trace_sha256,
            minimum_consecutive_frames=minimum_consecutive_frames,
            context_frames=context_frames,
        )
        if record["review_draft"] is not None:
            drafts[profile_id] = record["review_draft"]
        results.append(
            {
                "profile_id": profile_id,
                "profile_kind": (
                    "dialog" if profile_id in _DIALOG_PROFILE_IDS else "result"
                ),
                "evidence_schema": record["schema"],
                "evidence_complete": record["evidence_complete"],
                "selected_generations": record["selected_generations"],
                "ambiguous_generations": record["ambiguous_generations"],
                "review_draft_present": record["review_draft"] is not None,
                "record_sha256": _canonical_sha256(record),
            }
        )
    matched = tuple(
        item for item in results if item["evidence_complete"]
    )
    ambiguous_match = len(matched) > 1
    selected_generations = sorted(
        {
            generation
            for item in matched
            for generation in item["selected_generations"]
        }
    )
    ambiguous_generations = {
        generation
        for item in results
        for generation in item["ambiguous_generations"]
    }
    if ambiguous_match:
        ambiguous_generations.update(selected_generations)
    review_drafts = (
        [
            {
                "profile_id": matched[0]["profile_id"],
                "review_draft": drafts[matched[0]["profile_id"]],
            }
        ]
        if len(matched) == 1
        else []
    )
    return {
        "schema": ALAS_COMBAT_SURFACE_MULTIPLEX_EVIDENCE_SCHEMA,
        "mode": "all",
        "package": trace.package,
        "driver_revision": trace.driver_revision,
        "game_fingerprint": trace.game_fingerprint,
        "pid": trace.pid,
        "source_trace_sha256": source_trace_sha256,
        "minimum_consecutive_frames": minimum_consecutive_frames,
        "context_frames": context_frames,
        "profile_count": len(results),
        "profile_results": results,
        "matched_profile_ids": [item["profile_id"] for item in matched],
        "candidate_complete": bool(matched),
        "evidence_complete": len(matched) == 1,
        "ambiguous_match": ambiguous_match,
        "selected_generations": selected_generations,
        "ambiguous_generations": sorted(ambiguous_generations),
        "review_drafts": review_drafts,
        "review_required": True,
        "input_injected": False,
        "auto_promoted": False,
    }


def verify_alas_combat_surface_multiplex_evidence(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    record: Any,
    *,
    source_trace_sha256: str,
) -> Mapping[str, Any]:
    if not isinstance(record, dict):
        raise SemanticGateClosed("combat surface multiplex evidence is malformed")
    required = {
        "schema",
        "mode",
        "package",
        "driver_revision",
        "game_fingerprint",
        "pid",
        "source_trace_sha256",
        "minimum_consecutive_frames",
        "context_frames",
        "profile_count",
        "profile_results",
        "matched_profile_ids",
        "candidate_complete",
        "evidence_complete",
        "ambiguous_match",
        "selected_generations",
        "ambiguous_generations",
        "review_drafts",
        "review_required",
        "input_injected",
        "auto_promoted",
    }
    if set(record) != required:
        raise SemanticGateClosed("combat surface multiplex evidence schema changed")
    if record["schema"] != ALAS_COMBAT_SURFACE_MULTIPLEX_EVIDENCE_SCHEMA:
        raise SemanticGateClosed("combat surface multiplex evidence version changed")
    if record["mode"] != "all":
        raise SemanticGateClosed("combat surface multiplex mode changed")
    if record["source_trace_sha256"] != source_trace_sha256:
        raise SemanticGateClosed("combat surface multiplex trace hash changed")
    expected = analyze_alas_combat_surface_multiplex_evidence(
        manifest,
        trace,
        source_trace_sha256=source_trace_sha256,
        minimum_consecutive_frames=record["minimum_consecutive_frames"],
        context_frames=record["context_frames"],
    )
    if record != expected:
        raise SemanticGateClosed("combat surface multiplex evidence record changed")
    return {
        "schema": ALAS_COMBAT_SURFACE_MULTIPLEX_VERIFICATION_SCHEMA,
        "passed": True,
        "profile_count": record["profile_count"],
        "matched_profile_ids": record["matched_profile_ids"],
        "candidate_complete": record["candidate_complete"],
        "evidence_complete": record["evidence_complete"],
        "ambiguous_match": record["ambiguous_match"],
        "input_injected": False,
        "auto_promoted": False,
    }
