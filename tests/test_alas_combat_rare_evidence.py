import copy
import unittest
from dataclasses import replace

from alas_headless import (
    AlasCombatBlockerMapping,
    AlasCombatUnityRecordKind,
    AlasCombatUnitySelector,
    SemanticGateClosed,
    analyze_alas_combat_rare_surface_evidence,
    audit_alas_combat_rare_surface_mappings,
    build_alas_combat_observer_trace,
    build_alas_combat_trace_frame,
    parse_alas_combat_observer_trace,
    unqualified_alas_combat_observer_manifest,
    verify_alas_combat_rare_surface_evidence,
)


PACKAGE = "com.bilibili.azurlane"
DRIVER = "b" * 40
GAME = "pinned-test-game"
TRACE_SHA256 = "a" * 64
GUILD_ROOT = "OverlayCamera/Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/"
MISSION_ROOT = "OverlayCamera/Overlay/UIMain/MissionNotice(Clone)/frame/"


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


def button(path, name, bounds, *, raycast_top=True):
    left, top, right, bottom = bounds
    return {
        "name": name,
        "path": path,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "interactable": True,
        "raycast_top": raycast_top,
        "adb_point": {
            "x": (left + right) / 2.0,
            "y": (top + bottom) / 2.0,
        },
        "adb_bounds": {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        },
    }


def raw_frame(generation, buttons):
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
        "buttons": list(buttons),
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
        "text_count": 0,
        "image_count": 0,
        "toggles": [],
        "texts": [],
        "images": [],
    }
    return snapshot, button_payload, ui


def guild_buttons():
    return (
        button(
            GUILD_ROOT + "cancel_btn",
            "cancel_btn",
            (422.0, 449.0, 623.0, 486.0),
        ),
        button(
            GUILD_ROOT + "confirm_btn",
            "confirm_btn",
            (655.0, 450.0, 856.0, 487.0),
        ),
    )


def mission_buttons():
    return (
        button(
            MISSION_ROOT + "ack_btn",
            "ack_btn",
            (425.0, 487.0, 565.0, 538.0),
        ),
        button(
            MISSION_ROOT + "go_btn",
            "go_btn",
            (710.0, 486.0, 870.0, 540.0),
        ),
    )


class AlasCombatRareEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.manifest = unqualified_alas_combat_observer_manifest(
            package=PACKAGE,
            driver_revision=DRIVER,
            game_fingerprint=GAME,
        )

    def trace(self, controls_by_generation):
        frames = []
        for generation, controls in controls_by_generation:
            snapshot, buttons, ui = raw_frame(generation, controls)
            frame, _ = build_alas_combat_trace_frame(
                snapshot, buttons, ui, self.manifest
            )
            frames.append(frame)
        value = build_alas_combat_observer_trace(
            self.manifest,
            tuple(
                (
                    "2026-08-10T12:00:{0:02d}Z".format(index),
                    frame,
                )
                for index, frame in enumerate(frames, start=1)
            ),
        )
        return parse_alas_combat_observer_trace(value, self.manifest)

    def test_unqualified_manifest_keeps_both_rare_profiles_closed(self):
        self.assertEqual(
            audit_alas_combat_rare_surface_mappings(self.manifest),
            {"guild-popup": False, "mission-popup": False},
        )

    def test_guild_pair_emits_three_frame_non_applying_review_draft(self):
        trace = self.trace(
            (
                (10, ()),
                (11, guild_buttons()),
                (12, guild_buttons()),
                (13, guild_buttons()),
                (14, ()),
            )
        )
        record = analyze_alas_combat_rare_surface_evidence(
            self.manifest,
            trace,
            profile_id="guild-popup",
            source_trace_sha256=TRACE_SHA256,
        )

        self.assertTrue(record["evidence_complete"])
        self.assertFalse(record["input_injected"])
        self.assertFalse(record["auto_promoted"])
        self.assertEqual(record["selected_generations"], [11, 12, 13])
        self.assertEqual(record["context_before_generations"], [10])
        self.assertEqual(record["context_after_generations"], [14])
        self.assertEqual(
            [item["resource_name"] for item in record["controls"]],
            ["GUILD_POPUP_CANCEL", "GUILD_POPUP_CONFIRM"],
        )
        self.assertTrue(
            all(
                item["selector"]["require_top_raycast"]
                for item in record["controls"]
            )
        )
        self.assertEqual(len(record["review_draft"]["resources"]), 2)
        self.assertEqual(len(record["review_draft"]["actions"]), 2)

    def test_mission_pair_discovers_stable_exact_paths_from_asset_regions(self):
        trace = self.trace(
            tuple((generation, mission_buttons()) for generation in (21, 22, 23))
        )
        record = analyze_alas_combat_rare_surface_evidence(
            self.manifest,
            trace,
            profile_id="mission-popup",
            source_trace_sha256=TRACE_SHA256,
        )

        self.assertTrue(record["evidence_complete"])
        self.assertEqual(
            [item["selector"]["path"] for item in record["controls"]],
            [MISSION_ROOT + "ack_btn", MISSION_ROOT + "go_btn"],
        )
        self.assertTrue(
            all(
                not item["identity_was_pinned_before_capture"]
                for item in record["controls"]
            )
        )

    def test_qualified_blocker_suppresses_generic_two_button_false_positive(self):
        blocker_selectors = tuple(
            AlasCombatUnitySelector(
                AlasCombatUnityRecordKind.BUTTON,
                item["path"],
                item["name"],
                require_top_raycast=True,
            )
            for item in mission_buttons()
        )
        self.manifest = replace(
            self.manifest,
            blockers=(
                AlasCombatBlockerMapping(
                    "network_down", blocker_selectors, TRACE_SHA256
                ),
            ),
        )
        trace = self.trace(
            tuple((generation, mission_buttons()) for generation in (24, 25, 26))
        )
        record = analyze_alas_combat_rare_surface_evidence(
            self.manifest,
            trace,
            profile_id="mission-popup",
            source_trace_sha256=TRACE_SHA256,
        )
        self.assertFalse(record["evidence_complete"])
        self.assertIsNone(record["review_draft"])

    def test_two_frames_and_non_actionable_controls_remain_incomplete(self):
        controls = tuple(
            {**item, "raycast_top": False} for item in guild_buttons()
        )
        trace = self.trace(((31, guild_buttons()), (32, guild_buttons()), (33, controls)))
        record = analyze_alas_combat_rare_surface_evidence(
            self.manifest,
            trace,
            profile_id="guild-popup",
            source_trace_sha256=TRACE_SHA256,
        )

        self.assertFalse(record["evidence_complete"])
        self.assertIsNone(record["review_draft"])
        self.assertEqual(record["controls"], [])

    def test_ambiguous_region_fails_closed(self):
        ambiguous = mission_buttons() + (
            button(
                MISSION_ROOT + "ack_shadow",
                "ack_shadow",
                (430.0, 490.0, 560.0, 536.0),
            ),
        )
        trace = self.trace(tuple((generation, ambiguous) for generation in (41, 42, 43)))
        record = analyze_alas_combat_rare_surface_evidence(
            self.manifest,
            trace,
            profile_id="mission-popup",
            source_trace_sha256=TRACE_SHA256,
        )

        self.assertFalse(record["evidence_complete"])
        self.assertEqual(record["ambiguous_generations"], [41, 42, 43])

    def test_verifier_recomputes_record_and_rejects_tampering(self):
        trace = self.trace(
            tuple((generation, guild_buttons()) for generation in (51, 52, 53))
        )
        record = analyze_alas_combat_rare_surface_evidence(
            self.manifest,
            trace,
            profile_id="guild-popup",
            source_trace_sha256=TRACE_SHA256,
        )
        verification = verify_alas_combat_rare_surface_evidence(
            self.manifest,
            trace,
            record,
            source_trace_sha256=TRACE_SHA256,
        )
        self.assertTrue(verification["passed"])
        self.assertEqual(verification["selected_frame_count"], 3)

        tampered = copy.deepcopy(record)
        tampered["controls"][0]["selector"]["path"] = "changed"
        with self.assertRaisesRegex(SemanticGateClosed, "record changed"):
            verify_alas_combat_rare_surface_evidence(
                self.manifest,
                trace,
                tampered,
                source_trace_sha256=TRACE_SHA256,
            )
        with self.assertRaisesRegex(SemanticGateClosed, "trace hash changed"):
            verify_alas_combat_rare_surface_evidence(
                self.manifest,
                trace,
                record,
                source_trace_sha256="c" * 64,
            )


if __name__ == "__main__":
    unittest.main()
