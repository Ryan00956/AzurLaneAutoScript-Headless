import copy
import unittest
from dataclasses import replace

from alas_headless import (
    ALAS_COMBAT_RESULT_CONTROL_PROFILES,
    ALAS_COMBAT_RESULT_SURFACE_PROFILES,
    AlasCombatActionMapping,
    AlasCombatResourceMapping,
    AlasCombatUnityRecordKind,
    SemanticGateClosed,
    analyze_alas_combat_result_control_evidence,
    analyze_alas_combat_result_surface_evidence,
    audit_alas_combat_result_surface_mappings,
    build_alas_combat_observer_trace,
    build_alas_combat_trace_frame,
    parse_alas_combat_observer_trace,
    unqualified_alas_combat_observer_manifest,
    verify_alas_combat_result_surface_evidence,
    verify_alas_combat_result_control_evidence,
)


PACKAGE = "com.bilibili.azurlane"
DRIVER = "b" * 40
GAME = "pinned-test-game"
TRACE_SHA256 = "a" * 64


def meta(semantic_schema=None):
    value = {
        "protocol_schema": "alas-headless.observer/v1",
        "status": "ok",
        "package": PACKAGE,
        "driver_revision": DRIVER,
        "peer_uid": 2000,
        "age_ms": 0,
        "pid": 4242,
    }
    if semantic_schema is not None:
        value["semantic_schema"] = semantic_schema
    return value


def profile(profile_id):
    return next(
        item
        for item in ALAS_COMBAT_RESULT_SURFACE_PROFILES
        if item.profile_id == profile_id
    )


def s_selectors(item):
    return tuple(
        replace(
            selector,
            sprite=(
                selector.sprite[:-1] + "S"
                if selector.sprite in {
                    "letter_A",
                    "letter_B",
                    "letter_C",
                    "letter_D",
                    "label_A",
                    "label_B",
                    "label_C",
                    "label_D",
                }
                else selector.sprite
            ),
        )
        for selector in item.selectors
    )


def records_for_profile(item, *, raycast_top=True, geometry_offset=0.0):
    buttons = []
    images = []
    texts = []
    for selector in item.selectors:
        if selector.kind is AlasCombatUnityRecordKind.BUTTON:
            buttons.append(
                {
                    "name": selector.name,
                    "path": selector.path,
                    "active_in_hierarchy": True,
                    "active_and_enabled": True,
                    "interactable": True,
                    "raycast_top": raycast_top,
                    "adb_point": {"x": 640.0 + geometry_offset, "y": 360.0},
                    "adb_bounds": {
                        "left": 600.0 + geometry_offset,
                        "top": 330.0,
                        "right": 680.0 + geometry_offset,
                        "bottom": 390.0,
                    },
                }
            )
        elif selector.kind is AlasCombatUnityRecordKind.IMAGE:
            images.append(
                {
                    "kind": "image",
                    "name": selector.name,
                    "path": selector.path,
                    "sprite": selector.sprite,
                    "active_in_hierarchy": True,
                    "active_and_enabled": True,
                    "raycast_target": False,
                    "raycast_top": None,
                    "color": {
                        "red": 1.0,
                        "green": 1.0,
                        "blue": 1.0,
                        "alpha": 1.0,
                    },
                    "fill_amount": 1.0,
                    "flags": 0,
                    "adb_point": None,
                    "adb_bounds": {
                        "left": 300.0,
                        "top": 100.0,
                        "right": 400.0,
                        "bottom": 200.0,
                    },
                }
            )
        elif selector.kind is AlasCombatUnityRecordKind.TEXT:
            texts.append(
                {
                    "kind": "ugui-text",
                    "name": selector.name,
                    "path": selector.path,
                    "text": selector.text,
                    "active_in_hierarchy": True,
                    "active_and_enabled": True,
                    "flags": 0,
                    "adb_bounds": {
                        "left": 400.0,
                        "top": 200.0,
                        "right": 800.0,
                        "bottom": 300.0,
                    },
                }
            )
    return buttons, images, texts


def raw_frame(generation, item=None, *, raycast_top=True, geometry_offset=0.0):
    buttons = []
    images = []
    texts = []
    if item is not None:
        buttons, images, texts = records_for_profile(
            item,
            raycast_top=raycast_top,
            geometry_offset=geometry_offset,
        )
    snapshot = {
        **meta(),
        "snapshot_schema": 1,
        "main_thread": True,
        "flags": 15,
        "ui_stage": 100,
        "ui_method_mask": 15,
        "width": 1280,
        "height": 720,
        "generation": generation,
        "scene_handle": generation,
    }
    button_payload = {
        **meta("alas-headless.buttons/v1"),
        "schema": 1,
        "generation": generation,
        "truncated": False,
        "error_count": 0,
        "button_count": len(buttons),
        "buttons": buttons,
    }
    ui = {
        **meta("alas-headless.ui/v1"),
        "schema": 1,
        "generation": generation,
        "method_mask": 15,
        "skipped_count": 0,
        "toggle_truncated": False,
        "text_truncated": False,
        "image_truncated": False,
        "error_count": 0,
        "toggle_count": 0,
        "text_count": len(texts),
        "image_count": len(images),
        "toggles": [],
        "texts": texts,
        "images": images,
    }
    return snapshot, button_payload, ui


class AlasCombatResultEvidenceTests(unittest.TestCase):
    def setUp(self):
        manifest = unqualified_alas_combat_observer_manifest(
            package=PACKAGE,
            driver_revision=DRIVER,
            game_fingerprint=GAME,
        )
        battle = profile("battle-status-a")
        exp = profile("exp-info-a")
        references = {
            "BATTLE_STATUS_S": (s_selectors(battle), battle.action_selector),
            "EXP_INFO_S": (s_selectors(exp), exp.action_selector),
        }
        self.manifest = replace(
            manifest,
            resources=tuple(
                AlasCombatResourceMapping(
                    mapping.resource_name,
                    references[mapping.resource_name][0],
                    TRACE_SHA256,
                )
                if mapping.resource_name in references
                else mapping
                for mapping in manifest.resources
            ),
            actions=tuple(
                AlasCombatActionMapping(
                    mapping.action_name,
                    (references[mapping.action_name][1],),
                    TRACE_SHA256,
                )
                if mapping.action_name in references
                else mapping
                for mapping in manifest.actions
            ),
        )

    def trace(self, frames):
        built = []
        for generation, item, raycast_top, geometry_offset in frames:
            snapshot, buttons, ui = raw_frame(
                generation,
                item,
                raycast_top=raycast_top,
                geometry_offset=geometry_offset,
            )
            frame, _ = build_alas_combat_trace_frame(
                snapshot, buttons, ui, self.manifest
            )
            built.append(frame)
        value = build_alas_combat_observer_trace(
            self.manifest,
            tuple(
                (
                    "2026-08-10T13:00:{0:02d}Z".format(index),
                    frame,
                )
                for index, frame in enumerate(built, start=1)
            ),
        )
        return parse_alas_combat_observer_trace(value, self.manifest)

    def target_trace(self, item):
        return self.trace(
            (
                (10, None, True, 0.0),
                (11, item, True, 0.0),
                (12, item, True, 0.5),
                (13, item, True, 1.0),
                (14, None, True, 0.0),
            )
        )

    def test_all_six_profiles_emit_exact_non_applying_drafts(self):
        self.assertEqual(len(ALAS_COMBAT_RESULT_SURFACE_PROFILES), 6)
        for item in ALAS_COMBAT_RESULT_SURFACE_PROFILES:
            with self.subTest(profile=item.profile_id):
                record = analyze_alas_combat_result_surface_evidence(
                    self.manifest,
                    self.target_trace(item),
                    profile_id=item.profile_id,
                    source_trace_sha256=TRACE_SHA256,
                )
                self.assertTrue(record["evidence_complete"])
                self.assertFalse(record["input_injected"])
                self.assertFalse(record["auto_promoted"])
                self.assertEqual(record["selected_generations"], [11, 12, 13])
                self.assertEqual(record["context_before_generations"], [10])
                self.assertEqual(record["context_after_generations"], [14])
                self.assertEqual(
                    record["review_draft"]["resources"][0]["resource_name"],
                    item.resource_name,
                )
                self.assertEqual(
                    record["review_draft"]["actions"][0]["action_name"],
                    item.action_name,
                )

    def test_grade_identity_does_not_alias_a_sibling_profile(self):
        trace = self.target_trace(profile("battle-status-a"))
        record = analyze_alas_combat_result_surface_evidence(
            self.manifest,
            trace,
            profile_id="battle-status-b",
            source_trace_sha256=TRACE_SHA256,
        )
        self.assertFalse(record["evidence_complete"])
        self.assertIsNone(record["review_draft"])

    def test_non_actionable_and_geometry_drift_fail_closed(self):
        item = profile("exp-info-a")
        non_actionable = self.trace(
            tuple((generation, item, False, 0.0) for generation in (21, 22, 23))
        )
        self.assertFalse(
            analyze_alas_combat_result_surface_evidence(
                self.manifest,
                non_actionable,
                profile_id=item.profile_id,
                source_trace_sha256=TRACE_SHA256,
            )["evidence_complete"]
        )

        drifting = self.trace(
            (
                (31, item, True, 0.0),
                (32, item, True, 0.0),
                (33, item, True, 4.0),
            )
        )
        self.assertFalse(
            analyze_alas_combat_result_surface_evidence(
                self.manifest,
                drifting,
                profile_id=item.profile_id,
                source_trace_sha256=TRACE_SHA256,
            )["evidence_complete"]
        )

    def test_verifier_recomputes_and_rejects_tampering(self):
        item = profile("battle-status-d")
        trace = self.target_trace(item)
        record = analyze_alas_combat_result_surface_evidence(
            self.manifest,
            trace,
            profile_id=item.profile_id,
            source_trace_sha256=TRACE_SHA256,
        )
        result = verify_alas_combat_result_surface_evidence(
            self.manifest,
            trace,
            record,
            source_trace_sha256=TRACE_SHA256,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["selected_frame_count"], 3)

        tampered = copy.deepcopy(record)
        tampered["selectors"][1]["sprite"] = "letter_S"
        with self.assertRaisesRegex(SemanticGateClosed, "record changed"):
            verify_alas_combat_result_surface_evidence(
                self.manifest,
                trace,
                tampered,
                source_trace_sha256=TRACE_SHA256,
            )

    def test_checked_manifest_keeps_all_alternate_results_closed(self):
        self.assertEqual(
            audit_alas_combat_result_surface_mappings(self.manifest),
            {
                "battle-status-a": False,
                "battle-status-b": False,
                "battle-status-c": False,
                "battle-status-d": False,
                "exp-info-a": False,
                "exp-info-b": False,
            },
        )

    def test_reference_s_mapping_drift_is_rejected(self):
        item = profile("battle-status-a")
        drifted = replace(
            self.manifest,
            resources=tuple(
                AlasCombatResourceMapping(mapping.resource_name)
                if mapping.resource_name == "BATTLE_STATUS_S"
                else mapping
                for mapping in self.manifest.resources
            ),
        )
        with self.assertRaisesRegex(SemanticGateClosed, "reference S mapping"):
            analyze_alas_combat_result_surface_evidence(
                drifted,
                self.target_trace(item),
                profile_id=item.profile_id,
                source_trace_sha256=TRACE_SHA256,
            )

    def test_s_controls_reprove_checked_mapping_without_review_draft(self):
        self.assertEqual(
            tuple(item.profile_id for item in ALAS_COMBAT_RESULT_CONTROL_PROFILES),
            ("battle-status-s", "exp-info-s"),
        )
        for item in ALAS_COMBAT_RESULT_CONTROL_PROFILES:
            with self.subTest(profile=item.profile_id):
                record = analyze_alas_combat_result_control_evidence(
                    self.manifest,
                    self.target_trace(item),
                    profile_id=item.profile_id,
                    source_trace_sha256=TRACE_SHA256,
                )
                self.assertTrue(record["evidence_complete"])
                self.assertTrue(record["already_qualified"])
                self.assertEqual(record["selected_generations"], [11, 12, 13])
                self.assertIsNone(record["review_draft"])
                self.assertFalse(record["auto_promoted"])
                verified = verify_alas_combat_result_control_evidence(
                    self.manifest,
                    self.target_trace(item),
                    record,
                    source_trace_sha256=TRACE_SHA256,
                )
                self.assertTrue(verified["passed"])

    def test_s_control_rejects_geometry_drift_and_tampering(self):
        item = ALAS_COMBAT_RESULT_CONTROL_PROFILES[0]
        trace = self.trace(
            (
                (41, item, True, 0.0),
                (42, item, True, 0.0),
                (43, item, True, 4.0),
            )
        )
        record = analyze_alas_combat_result_control_evidence(
            self.manifest,
            trace,
            profile_id=item.profile_id,
            source_trace_sha256=TRACE_SHA256,
        )
        self.assertFalse(record["evidence_complete"])
        tampered = copy.deepcopy(record)
        tampered["evidence_complete"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "record changed"):
            verify_alas_combat_result_control_evidence(
                self.manifest,
                trace,
                tampered,
                source_trace_sha256=TRACE_SHA256,
            )


if __name__ == "__main__":
    unittest.main()
