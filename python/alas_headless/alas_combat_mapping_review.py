"""Evidence-bound promotion of raw Unity records into the combat manifest.

This module changes only the observer input contract.  It never imports ALAS,
assigns a combat phase, performs Android input, or enables the G18 live-combat
boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from typing import Any, Mapping, Optional, Sequence, Tuple

from .alas_combat_observer import (
    AlasCombatActionMapping,
    AlasCombatBlockerMapping,
    AlasCombatFleetStatsMapping,
    AlasCombatObserverCoverage,
    AlasCombatObserverManifest,
    AlasCombatResourceMapping,
    AlasCombatUnitySelector,
    alas_combat_fleet_stats,
    alas_combat_observer_manifest_to_json,
    alas_combat_unity_selector_present,
    alas_combat_unity_selector_to_json,
    audit_alas_combat_observer_manifest,
    parse_alas_combat_unity_selector,
    validate_alas_combat_observer_snapshot,
)
from .alas_combat_trace import (
    AlasCombatObserverTrace,
    AlasCombatObserverTraceSample,
)
from .semantic_oracle import SemanticGateClosed


ALAS_COMBAT_MAPPING_REVIEW_SCHEMA = "alas-headless.g26-combat-mapping-review/v2"
ALAS_COMBAT_MAPPING_RECEIPT_SCHEMA = "alas-headless.g26-combat-mapping-receipt/v2"
ALAS_COMBAT_MAPPING_EVIDENCE_SCHEMA = "alas-headless.g26-combat-mapping-evidence/v2"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_REVIEW_ID_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _coverage_json(coverage: AlasCombatObserverCoverage) -> Mapping[str, Any]:
    return {
        "production_ready": coverage.production_ready,
        "canonical_qualified_resources": coverage.canonical_qualified_resources,
        "canonical_resources": coverage.canonical_resources,
        "qualified_resources": coverage.qualified_resources,
        "total_resources": coverage.total_resources,
        "qualified_actions": coverage.qualified_actions,
        "total_actions": coverage.total_actions,
        "branch_review_complete": coverage.branch_review_complete,
        "qualified_blockers": coverage.qualified_blockers,
        "total_blockers": coverage.total_blockers,
        "blocker_review_complete": coverage.blocker_review_complete,
        "blockers_qualified": coverage.blockers_qualified,
        "fleet_stats_qualified": coverage.fleet_stats_qualified,
    }


def _review_entries(
    value: Any, *, entry_kind: str
) -> Tuple[Tuple[str, Tuple[AlasCombatUnitySelector, ...]], ...]:
    if not isinstance(value, list):
        raise SemanticGateClosed("combat mapping review entries are malformed")
    name_field = {
        "resource": "resource_name",
        "action": "action_name",
        "blocker": "blocker_name",
    }.get(entry_kind)
    if name_field is None:
        raise SemanticGateClosed("combat mapping review entry kind changed")
    parsed = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {name_field, "selectors"}:
            raise SemanticGateClosed(
                "combat mapping review {0} schema changed".format(entry_kind)
            )
        name = item[name_field]
        raw_selectors = item["selectors"]
        if not isinstance(name, str) or not name or not isinstance(raw_selectors, list):
            raise SemanticGateClosed(
                "combat mapping review {0} is malformed".format(entry_kind)
            )
        selectors = tuple(
            parse_alas_combat_unity_selector(selector) for selector in raw_selectors
        )
        if not selectors:
            raise SemanticGateClosed(
                "combat mapping review {0} has no selectors".format(entry_kind)
            )
        identities = tuple((selector.kind, selector.path) for selector in selectors)
        if len(identities) != len(set(identities)):
            raise SemanticGateClosed(
                "combat mapping review {0} has duplicate selectors".format(entry_kind)
            )
        parsed.append((name, selectors))
    names = tuple(name for name, _ in parsed)
    if len(names) != len(set(names)):
        raise SemanticGateClosed(
            "combat mapping review has duplicate {0} names".format(entry_kind)
        )
    return tuple(parsed)


def _select_review_samples(
    trace: AlasCombatObserverTrace, generations: Any
) -> Tuple[AlasCombatObserverTraceSample, ...]:
    if (
        not isinstance(generations, list)
        or len(generations) < 2
        or any(
            isinstance(generation, bool) or not isinstance(generation, int)
            for generation in generations
        )
        or any(right <= left for left, right in zip(generations, generations[1:]))
    ):
        raise SemanticGateClosed(
            "combat mapping review requires two increasing generations"
        )
    indexed = {sample.snapshot.generation: sample for sample in trace.samples}
    if len(indexed) != len(trace.samples):
        raise SemanticGateClosed("combat mapping trace generations are ambiguous")
    try:
        return tuple(indexed[generation] for generation in generations)
    except KeyError as exc:
        raise SemanticGateClosed("combat mapping review generation is absent") from exc


def _evidence_sha256(
    *,
    mapping_type: str,
    mapping_name: str,
    selectors: Sequence[AlasCombatUnitySelector],
    trace_sha256: str,
    selected: Sequence[AlasCombatObserverTraceSample],
) -> str:
    return _canonical_sha256(
        {
            "schema": ALAS_COMBAT_MAPPING_EVIDENCE_SCHEMA,
            "mapping_type": mapping_type,
            "mapping_name": mapping_name,
            "trace_sha256": trace_sha256,
            "frames": [
                {
                    "generation": sample.snapshot.generation,
                    "frame_sha256": sample.frame["sha256"],
                }
                for sample in selected
            ],
            "selectors": [
                alas_combat_unity_selector_to_json(
                    selector,
                    allow_dynamic_text=(
                        selector.kind.value == "text" and not selector.text
                    ),
                )
                for selector in selectors
            ],
        }
    )


def _review_fleet_stats(value: Any) -> Optional[AlasCombatFleetStatsMapping]:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "hp_images",
        "level_texts",
    }:
        raise SemanticGateClosed("combat mapping fleet stats schema changed")
    hp_images = value["hp_images"]
    level_texts = value["level_texts"]
    if not isinstance(hp_images, list) or not isinstance(level_texts, list):
        raise SemanticGateClosed("combat mapping fleet stats are malformed")
    mapping = AlasCombatFleetStatsMapping(
        hp_images=tuple(
            parse_alas_combat_unity_selector(item) for item in hp_images
        ),
        level_texts=tuple(
            parse_alas_combat_unity_selector(item, allow_dynamic_text=True)
            for item in level_texts
        ),
    )
    if len(mapping.hp_images) != 6 or len(mapping.level_texts) != 6:
        raise SemanticGateClosed("combat mapping fleet stats are incomplete")
    return mapping


def _prove_all_present(
    selected: Sequence[AlasCombatObserverTraceSample],
    selectors: Sequence[AlasCombatUnitySelector],
) -> None:
    for sample in selected:
        absent = tuple(
            selector.path
            for selector in selectors
            if not alas_combat_unity_selector_present(sample.snapshot, selector)
        )
        if absent:
            raise SemanticGateClosed(
                "combat mapping selector is absent at generation {0}: {1}".format(
                    sample.snapshot.generation, ", ".join(absent)
                )
            )


def promote_alas_combat_mapping_review(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    review: Any,
    *,
    source_trace_sha256: str,
) -> Tuple[AlasCombatObserverManifest, Mapping[str, Any]]:
    """Verify one review against raw frames and return a manifest plus receipt."""

    required_review_fields = {
        "schema",
        "review_id",
        "trace_sha256",
        "generations",
        "resources",
        "actions",
        "branch_review_complete",
        "blockers",
        "blocker_review_complete",
    }
    if (
        not isinstance(review, dict)
        or not required_review_fields.issubset(review)
        or not set(review).issubset(required_review_fields | {"fleet_stats"})
    ):
        raise SemanticGateClosed("combat mapping review schema changed")
    if review["schema"] != ALAS_COMBAT_MAPPING_REVIEW_SCHEMA:
        raise SemanticGateClosed("combat mapping review version changed")
    review_id = review["review_id"]
    if (
        not isinstance(review_id, str)
        or _REVIEW_ID_PATTERN.fullmatch(review_id) is None
    ):
        raise SemanticGateClosed("combat mapping review id is malformed")
    coverage_before = audit_alas_combat_observer_manifest(manifest)
    expected_trace_sha256 = review["trace_sha256"]
    if (
        not isinstance(expected_trace_sha256, str)
        or _SHA256_PATTERN.fullmatch(expected_trace_sha256) is None
        or expected_trace_sha256 != source_trace_sha256
    ):
        raise SemanticGateClosed("combat mapping review trace hash changed")
    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("combat mapping review trace is not typed")
    if (
        trace.package != manifest.package
        or trace.driver_revision != manifest.driver_revision
        or trace.game_fingerprint != manifest.game_fingerprint
    ):
        raise SemanticGateClosed("combat mapping review identity changed")
    selected = _select_review_samples(trace, review["generations"])
    for sample in selected:
        validate_alas_combat_observer_snapshot(sample.snapshot, manifest)
    resources = _review_entries(review["resources"], entry_kind="resource")
    actions = _review_entries(review["actions"], entry_kind="action")
    blockers = _review_entries(review["blockers"], entry_kind="blocker")
    reviewed_stats = _review_fleet_stats(review.get("fleet_stats"))
    if not resources and not actions and not blockers and reviewed_stats is None:
        raise SemanticGateClosed("combat mapping review has no promotions")
    branch_complete = review["branch_review_complete"]
    if not isinstance(branch_complete, bool):
        raise SemanticGateClosed("combat mapping branch review flag is malformed")
    if manifest.branch_review_complete and not branch_complete:
        raise SemanticGateClosed("combat mapping review cannot reopen branch coverage")
    complete = review["blocker_review_complete"]
    if not isinstance(complete, bool):
        raise SemanticGateClosed("combat mapping blocker review flag is malformed")
    if manifest.blocker_review_complete and not complete:
        raise SemanticGateClosed("combat mapping review cannot reopen blocker coverage")

    resource_index = {mapping.resource_name: mapping for mapping in manifest.resources}
    resource_promotions = []
    for name, selectors in resources:
        if name not in resource_index:
            raise SemanticGateClosed(
                "combat mapping review resource is unknown: " + name
            )
        _prove_all_present(selected, selectors)
        evidence = _evidence_sha256(
            mapping_type="resource",
            mapping_name=name,
            selectors=selectors,
            trace_sha256=source_trace_sha256,
            selected=selected,
        )
        reviewed_mapping = AlasCombatResourceMapping(name, selectors, evidence)
        existing_mapping = resource_index[name]
        if existing_mapping.qualified and existing_mapping != reviewed_mapping:
            raise SemanticGateClosed(
                "combat mapping review refuses to overwrite resource: " + name
            )
        resource_index[name] = reviewed_mapping
        resource_promotions.append(
            {
                "resource_name": name,
                "match": "all_of",
                "selectors": [
                    alas_combat_unity_selector_to_json(selector)
                    for selector in selectors
                ],
                "evidence_sha256": evidence,
                "present_in_all_samples": True,
            }
        )

    action_index = {mapping.action_name: mapping for mapping in manifest.actions}
    action_promotions = []
    for name, selectors in actions:
        if name not in action_index:
            raise SemanticGateClosed(
                "combat mapping review action is unknown: " + name
            )
        _prove_all_present(selected, selectors)
        evidence = _evidence_sha256(
            mapping_type="action",
            mapping_name=name,
            selectors=selectors,
            trace_sha256=source_trace_sha256,
            selected=selected,
        )
        reviewed_mapping = AlasCombatActionMapping(name, selectors, evidence)
        existing_mapping = action_index[name]
        if existing_mapping.qualified and existing_mapping != reviewed_mapping:
            raise SemanticGateClosed(
                "combat mapping review refuses to overwrite action: " + name
            )
        action_index[name] = reviewed_mapping
        action_promotions.append(
            {
                "action_name": name,
                "match": "exactly_one",
                "selectors": [
                    alas_combat_unity_selector_to_json(selector)
                    for selector in selectors
                ],
                "evidence_sha256": evidence,
                "present_in_all_samples": True,
            }
        )

    blocker_index = {mapping.blocker_name: mapping for mapping in manifest.blockers}
    blocker_promotions = []
    for name, selectors in blockers:
        _prove_all_present(selected, selectors)
        evidence = _evidence_sha256(
            mapping_type="blocker",
            mapping_name=name,
            selectors=selectors,
            trace_sha256=source_trace_sha256,
            selected=selected,
        )
        reviewed_mapping = AlasCombatBlockerMapping(name, selectors, evidence)
        existing_mapping = blocker_index.get(name)
        if existing_mapping is not None and existing_mapping != reviewed_mapping:
            raise SemanticGateClosed(
                "combat mapping review refuses to overwrite blocker: " + name
            )
        blocker_index[name] = reviewed_mapping
        blocker_promotions.append(
            {
                "blocker_name": name,
                "match": "all_of",
                "selectors": [
                    alas_combat_unity_selector_to_json(selector)
                    for selector in selectors
                ],
                "evidence_sha256": evidence,
                "present_in_all_samples": True,
            }
        )

    fleet_stats_promotion = None
    promoted_stats = manifest.fleet_stats
    if reviewed_stats is not None:
        observed_values = []
        for sample in selected:
            hp, levels = alas_combat_fleet_stats(sample.snapshot, reviewed_stats)
            observed_values.append(
                {
                    "generation": sample.snapshot.generation,
                    "hp": list(hp),
                    "levels": list(levels),
                }
            )
        selectors = reviewed_stats.hp_images + reviewed_stats.level_texts
        evidence = _evidence_sha256(
            mapping_type="fleet_stats",
            mapping_name="fleet_stats",
            selectors=selectors,
            trace_sha256=source_trace_sha256,
            selected=selected,
        )
        promoted_stats = AlasCombatFleetStatsMapping(
            hp_images=reviewed_stats.hp_images,
            level_texts=reviewed_stats.level_texts,
            evidence_sha256=evidence,
        )
        if manifest.fleet_stats.qualified and manifest.fleet_stats != promoted_stats:
            raise SemanticGateClosed(
                "combat mapping review refuses to overwrite fleet stats"
            )
        fleet_stats_promotion = {
            "match": "six_ordered",
            "hp_images": [
                alas_combat_unity_selector_to_json(item)
                for item in reviewed_stats.hp_images
            ],
            "level_texts": [
                alas_combat_unity_selector_to_json(
                    item, allow_dynamic_text=True
                )
                for item in reviewed_stats.level_texts
            ],
            "evidence_sha256": evidence,
            "values": observed_values,
        }

    promoted = replace(
        manifest,
        resources=tuple(
            resource_index[mapping.resource_name] for mapping in manifest.resources
        ),
        actions=tuple(
            action_index[mapping.action_name] for mapping in manifest.actions
        ),
        branch_review_complete=branch_complete,
        blockers=tuple(blocker_index[name] for name in sorted(blocker_index)),
        blocker_review_complete=complete,
        fleet_stats=promoted_stats,
    )
    coverage_after = audit_alas_combat_observer_manifest(promoted)
    before_json = alas_combat_observer_manifest_to_json(manifest)
    after_json = alas_combat_observer_manifest_to_json(promoted)
    receipt = {
        "schema": ALAS_COMBAT_MAPPING_RECEIPT_SCHEMA,
        "review_id": review_id,
        "source_trace_sha256": source_trace_sha256,
        "source_frames": [
            {
                "sequence": sample.sequence,
                "captured_at_utc": sample.captured_at_utc,
                "generation": sample.snapshot.generation,
                "frame_sha256": sample.frame["sha256"],
            }
            for sample in selected
        ],
        "manifest_before_sha256": _canonical_sha256(before_json),
        "manifest_after_sha256": _canonical_sha256(after_json),
        "resource_promotions": resource_promotions,
        "action_promotions": action_promotions,
        "branch_review_complete": branch_complete,
        "blocker_promotions": blocker_promotions,
        "blocker_review_complete": complete,
        "coverage_before": _coverage_json(coverage_before),
        "coverage_after": _coverage_json(coverage_after),
        "input_injected": False,
    }
    if fleet_stats_promotion is not None:
        receipt["fleet_stats_promotion"] = fleet_stats_promotion
    return promoted, receipt


def verify_alas_combat_mapping_receipt(
    manifest: AlasCombatObserverManifest,
    trace: AlasCombatObserverTrace,
    receipt: Any,
    *,
    source_trace_sha256: str,
) -> Mapping[str, Any]:
    """Re-prove a committed receipt against its raw trace and live manifest."""

    required_receipt_fields = {
        "schema",
        "review_id",
        "source_trace_sha256",
        "source_frames",
        "manifest_before_sha256",
        "manifest_after_sha256",
        "resource_promotions",
        "action_promotions",
        "branch_review_complete",
        "blocker_promotions",
        "blocker_review_complete",
        "coverage_before",
        "coverage_after",
        "input_injected",
    }
    if (
        not isinstance(receipt, dict)
        or not required_receipt_fields.issubset(receipt)
        or not set(receipt).issubset(
            required_receipt_fields | {"fleet_stats_promotion"}
        )
    ):
        raise SemanticGateClosed("combat mapping receipt schema changed")
    if receipt["schema"] != ALAS_COMBAT_MAPPING_RECEIPT_SCHEMA:
        raise SemanticGateClosed("combat mapping receipt version changed")
    if (
        not isinstance(receipt["review_id"], str)
        or _REVIEW_ID_PATTERN.fullmatch(receipt["review_id"]) is None
    ):
        raise SemanticGateClosed("combat mapping receipt id is malformed")
    if receipt["input_injected"] is not False:
        raise SemanticGateClosed("combat mapping receipt claims input")
    if (
        not isinstance(source_trace_sha256, str)
        or receipt["source_trace_sha256"] != source_trace_sha256
        or _SHA256_PATTERN.fullmatch(source_trace_sha256) is None
    ):
        raise SemanticGateClosed("combat mapping receipt trace hash changed")
    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("combat mapping receipt trace is not typed")
    if (
        trace.package != manifest.package
        or trace.driver_revision != manifest.driver_revision
        or trace.game_fingerprint != manifest.game_fingerprint
    ):
        raise SemanticGateClosed("combat mapping receipt identity changed")
    raw_frames = receipt["source_frames"]
    if not isinstance(raw_frames, list) or len(raw_frames) < 2:
        raise SemanticGateClosed("combat mapping receipt frames are malformed")
    generations = []
    for raw in raw_frames:
        if not isinstance(raw, dict) or set(raw) != {
            "sequence",
            "captured_at_utc",
            "generation",
            "frame_sha256",
        }:
            raise SemanticGateClosed("combat mapping receipt frame schema changed")
        generations.append(raw["generation"])
    selected = _select_review_samples(trace, generations)
    for sample in selected:
        validate_alas_combat_observer_snapshot(sample.snapshot, manifest)
    for raw, sample in zip(raw_frames, selected):
        if raw != {
            "sequence": sample.sequence,
            "captured_at_utc": sample.captured_at_utc,
            "generation": sample.snapshot.generation,
            "frame_sha256": sample.frame["sha256"],
        }:
            raise SemanticGateClosed("combat mapping receipt frame identity changed")

    manifest_json = alas_combat_observer_manifest_to_json(manifest)
    manifest_sha256 = _canonical_sha256(manifest_json)
    if receipt["manifest_after_sha256"] != manifest_sha256:
        raise SemanticGateClosed("combat mapping receipt manifest hash changed")
    if (
        not isinstance(receipt["manifest_before_sha256"], str)
        or _SHA256_PATTERN.fullmatch(receipt["manifest_before_sha256"]) is None
    ):
        raise SemanticGateClosed("combat mapping receipt prior hash is malformed")
    coverage = _coverage_json(audit_alas_combat_observer_manifest(manifest))
    if receipt["coverage_after"] != coverage:
        raise SemanticGateClosed("combat mapping receipt coverage changed")
    if (
        not isinstance(receipt["coverage_before"], dict)
        or set(receipt["coverage_before"]) != set(coverage)
        or any(
            not isinstance(value, (bool, int))
            for value in receipt["coverage_before"].values()
        )
    ):
        raise SemanticGateClosed("combat mapping receipt prior coverage is malformed")
    if receipt["blocker_review_complete"] != manifest.blocker_review_complete:
        raise SemanticGateClosed("combat mapping receipt blocker review changed")
    if receipt["branch_review_complete"] != manifest.branch_review_complete:
        raise SemanticGateClosed("combat mapping receipt branch review changed")

    resource_index = {mapping.resource_name: mapping for mapping in manifest.resources}
    action_index = {mapping.action_name: mapping for mapping in manifest.actions}
    blocker_index = {mapping.blocker_name: mapping for mapping in manifest.blockers}

    def verify_entries(raw_entries: Any, *, mapping_type: str) -> int:
        if not isinstance(raw_entries, list):
            raise SemanticGateClosed("combat mapping receipt entries are malformed")
        name_field = {
            "resource": "resource_name",
            "action": "action_name",
            "blocker": "blocker_name",
        }.get(mapping_type)
        expected_index = {
            "resource": resource_index,
            "action": action_index,
            "blocker": blocker_index,
        }.get(mapping_type)
        if name_field is None or expected_index is None:
            raise SemanticGateClosed("combat mapping receipt entry kind changed")
        names = []
        for raw in raw_entries:
            if not isinstance(raw, dict) or set(raw) != {
                name_field,
                "match",
                "selectors",
                "evidence_sha256",
                "present_in_all_samples",
            }:
                raise SemanticGateClosed("combat mapping receipt entry schema changed")
            name = raw[name_field]
            if (
                not isinstance(name, str)
                or raw["match"]
                != ("exactly_one" if mapping_type == "action" else "all_of")
                or raw["present_in_all_samples"] is not True
                or name not in expected_index
            ):
                raise SemanticGateClosed("combat mapping receipt entry is malformed")
            selectors = tuple(
                parse_alas_combat_unity_selector(item) for item in raw["selectors"]
            )
            _prove_all_present(selected, selectors)
            evidence = _evidence_sha256(
                mapping_type=mapping_type,
                mapping_name=name,
                selectors=selectors,
                trace_sha256=source_trace_sha256,
                selected=selected,
            )
            mapping = expected_index[name]
            if (
                mapping.selectors != selectors
                or mapping.evidence_sha256 != evidence
                or raw["evidence_sha256"] != evidence
            ):
                raise SemanticGateClosed("combat mapping receipt evidence changed")
            names.append(name)
        if len(names) != len(set(names)):
            raise SemanticGateClosed("combat mapping receipt has duplicate entries")
        return len(names)

    resource_count = verify_entries(
        receipt["resource_promotions"], mapping_type="resource"
    )
    action_count = verify_entries(
        receipt["action_promotions"], mapping_type="action"
    )
    blocker_count = verify_entries(
        receipt["blocker_promotions"], mapping_type="blocker"
    )
    fleet_stats_verified = False
    raw_stats = receipt.get("fleet_stats_promotion")
    if raw_stats is not None:
        if not isinstance(raw_stats, dict) or set(raw_stats) != {
            "match",
            "hp_images",
            "level_texts",
            "evidence_sha256",
            "values",
        }:
            raise SemanticGateClosed(
                "combat mapping receipt fleet stats schema changed"
            )
        if raw_stats["match"] != "six_ordered":
            raise SemanticGateClosed(
                "combat mapping receipt fleet stats match changed"
            )
        reviewed_stats = _review_fleet_stats(
            {
                "hp_images": raw_stats["hp_images"],
                "level_texts": raw_stats["level_texts"],
            }
        )
        assert reviewed_stats is not None
        values = []
        for sample in selected:
            hp, levels = alas_combat_fleet_stats(sample.snapshot, reviewed_stats)
            values.append(
                {
                    "generation": sample.snapshot.generation,
                    "hp": list(hp),
                    "levels": list(levels),
                }
            )
        selectors = reviewed_stats.hp_images + reviewed_stats.level_texts
        evidence = _evidence_sha256(
            mapping_type="fleet_stats",
            mapping_name="fleet_stats",
            selectors=selectors,
            trace_sha256=source_trace_sha256,
            selected=selected,
        )
        expected_stats = AlasCombatFleetStatsMapping(
            hp_images=reviewed_stats.hp_images,
            level_texts=reviewed_stats.level_texts,
            evidence_sha256=evidence,
        )
        if (
            manifest.fleet_stats != expected_stats
            or raw_stats["evidence_sha256"] != evidence
            or raw_stats["values"] != values
        ):
            raise SemanticGateClosed(
                "combat mapping receipt fleet stats evidence changed"
            )
        fleet_stats_verified = True
    if (
        resource_count + action_count + blocker_count == 0
        and not fleet_stats_verified
    ):
        raise SemanticGateClosed("combat mapping receipt has no verified entries")
    return {
        "schema": "alas-headless.g26-combat-mapping-verification/v2",
        "passed": True,
        "review_id": receipt["review_id"],
        "source_frames": len(selected),
        "verified_resources": resource_count,
        "verified_actions": action_count,
        "verified_blockers": blocker_count,
        "verified_fleet_stats": fleet_stats_verified,
        "manifest_sha256": manifest_sha256,
        "production_ready": coverage["production_ready"],
        "input_injected": False,
    }
