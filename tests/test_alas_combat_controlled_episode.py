import copy
import unittest
from dataclasses import replace

from alas_headless import (
    ALAS_COMBAT_ACQUISITION_SCHEMA,
    ALAS_COMBAT_MAP_CHECKPOINT_SCHEMA,
    ALAS_COMBAT_RESULT_CONTROL_PROFILES,
    AlasCombatActionMapping,
    AlasCombatResourceMapping,
    AlasCombatUnityRecordKind,
    AlasCombatUnitySelector,
    SemanticGateClosed,
    analyze_alas_combat_controlled_episode,
    analyze_alas_combat_surface_multiplex_evidence,
    build_alas_combat_observer_trace,
    build_alas_combat_trace_frame,
    parse_alas_combat_observer_trace,
    unqualified_alas_combat_observer_manifest,
    verify_alas_combat_controlled_episode,
)


PACKAGE = "com.bilibili.azurlane"
DRIVER = "b" * 40
GAME = "pinned-test-game"
EVIDENCE = "a" * 64
PID = 4242


def meta(semantic_schema=None):
    value = {
        "protocol_schema": "alas-headless.observer/v1",
        "status": "ok",
        "package": PACKAGE,
        "driver_revision": DRIVER,
        "peer_uid": 2000,
        "age_ms": 0,
        "pid": PID,
    }
    if semantic_schema is not None:
        value["semantic_schema"] = semantic_schema
    return value


def records_for_profile(profile):
    buttons = []
    images = []
    texts = []
    for selector in profile.selectors:
        if selector.kind is AlasCombatUnityRecordKind.BUTTON:
            buttons.append(
                {
                    "name": selector.name,
                    "path": selector.path,
                    "active_in_hierarchy": True,
                    "active_and_enabled": True,
                    "interactable": True,
                    "raycast_top": True,
                    "adb_point": {"x": 640.0, "y": 360.0},
                    "adb_bounds": {
                        "left": 600.0,
                        "top": 330.0,
                        "right": 680.0,
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


def raw_frame(generation, profile=None):
    buttons, images, texts = ([], [], [])
    if profile is not None:
        buttons, images, texts = records_for_profile(profile)
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


def map_value(generation, *, ammo, enemy, fleet_node):
    return {
        "generation": generation,
        "stage_code": "12-4",
        "rows": 8,
        "columns": 11,
        "land_nodes": ["A1"],
        "expected_fleet_count": 2,
        "fleets": [
            {
                "marker": "ying",
                "node": fleet_node,
                "ammo": ammo,
                "ammo_capacity": 5,
            },
            {
                "marker": "shengwang_younv",
                "node": "E8",
                "ammo": 5,
                "ammo_capacity": 5,
            },
        ],
        "enemies": (
            [{"node": "C3", "object_id": 1204050, "fighting": False}]
            if enemy
            else []
        ),
        "displayed_fleet_index": 1,
        "current_fleet_marker": "ying",
    }


class AlasCombatControlledEpisodeTests(unittest.TestCase):
    def setUp(self):
        manifest = unqualified_alas_combat_observer_manifest(
            package=PACKAGE,
            driver_revision=DRIVER,
            game_fingerprint=GAME,
        )
        battle, exp = ALAS_COMBAT_RESULT_CONTROL_PROFILES
        preparation = AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.BUTTON,
            "Overlay/ChapterPreCombatUI/start",
            "start",
            require_top_raycast=True,
        )
        resource_selectors = {
            "BATTLE_PREPARATION": (preparation,),
            "BATTLE_STATUS_S": battle.selectors,
            "EXP_INFO_S": exp.selectors,
        }
        action_selectors = {
            "BATTLE_PREPARATION": preparation,
            "BATTLE_STATUS_S": battle.action_selector,
            "EXP_INFO_S": exp.action_selector,
        }
        self.manifest = replace(
            manifest,
            resources=tuple(
                AlasCombatResourceMapping(
                    mapping.resource_name,
                    resource_selectors[mapping.resource_name],
                    EVIDENCE,
                )
                if mapping.resource_name in resource_selectors
                else mapping
                for mapping in manifest.resources
            ),
            actions=tuple(
                AlasCombatActionMapping(
                    mapping.action_name,
                    (action_selectors[mapping.action_name],),
                    EVIDENCE,
                )
                if mapping.action_name in action_selectors
                else mapping
                for mapping in manifest.actions
            ),
        )
        frames = []
        for generation, profile in (
            (10, None),
            (20, battle),
            (21, battle),
            (22, battle),
            (30, exp),
            (31, exp),
            (32, exp),
            (40, None),
        ):
            snapshot, buttons, ui = raw_frame(generation, profile)
            frame, _ = build_alas_combat_trace_frame(
                snapshot, buttons, ui, self.manifest
            )
            frames.append(frame)
        raw_trace = build_alas_combat_observer_trace(
            self.manifest,
            tuple(
                ("2026-08-10T13:00:{0:02d}Z".format(index), frame)
                for index, frame in enumerate(frames, start=1)
            ),
        )
        self.trace = parse_alas_combat_observer_trace(
            raw_trace, self.manifest
        )
        self.multiplex = analyze_alas_combat_surface_multiplex_evidence(
            self.manifest,
            self.trace,
            source_trace_sha256=EVIDENCE,
            minimum_consecutive_frames=3,
            context_frames=2,
        )
        self.acquisition = {
            "schema": ALAS_COMBAT_ACQUISITION_SCHEMA,
            "package": PACKAGE,
            "driver_revision": DRIVER,
            "game_fingerprint": GAME,
            "pid": PID,
            "controlled_input_injected": True,
            "trace_recorder_input_injected": False,
            "trace_sha256": EVIDENCE,
            "sample_count": len(self.trace.samples),
            "first_generation": self.trace.generations[0],
            "last_generation": self.trace.generations[-1],
            "map_before": map_value(
                14, ammo=5, enemy=True, fleet_node="A3"
            ),
            "input": {
                "stage_code": "12-4",
                "battle_count": 0,
                "branch_name": "battle_0",
                "fleet_index": 1,
                "origin_node": "A3",
                "target_node": "C3",
                "route_nodes": ["A3", "B3", "C3"],
                "fleet_marker": "ying",
                "enemy_object_id": 1204050,
                "ammo_before": 5,
                "expected": "combat",
                "cell_path": "LevelGrid/quads/chapter_cell_quad_3_3",
                "point": {"x": 640.0, "y": 360.0},
                "bounds": {
                    "left": 600.0,
                    "top": 330.0,
                    "right": 680.0,
                    "bottom": 390.0,
                },
                "admission_generation": 14,
                "preflight_generation": 15,
                "receipt_generation": 15,
                "receipt_semantic_id": "campaign/map/grid/C3",
                "call_order": [
                    "hp_retreat_triggered",
                    "fleet_set",
                    "in_sight",
                    "focus_to_grid_center",
                    "convert_global_to_local",
                    "ambush_color_initial",
                    "enemy_searching_color_initial",
                    "device.click",
                ],
            },
        }
        self.actions = tuple(
            self.action_receipt(resource, first, commit)
            for resource, first, commit in (
                ("BATTLE_PREPARATION", 16, 17),
                ("BATTLE_STATUS_S", 23, 24),
                ("EXP_INFO_S", 33, 34),
            )
        )
        self.checkpoint = {
            "schema": ALAS_COMBAT_MAP_CHECKPOINT_SCHEMA,
            "package": PACKAGE,
            "driver_revision": DRIVER,
            "game_fingerprint": GAME,
            "pid": PID,
            "input_injected": False,
            "map": map_value(
                39, ammo=4, enemy=False, fleet_node="C3"
            ),
        }

    def action_receipt(self, resource, first, commit):
        mapping = next(
            item for item in self.manifest.actions
            if item.action_name == resource
        )
        variant = mapping.resolved_variants[0]
        selector = next(
            item for item in variant.selectors if item.require_top_raycast
        )
        return {
            "schema": "alas-headless.g27-combat-resource-action-commit/v3",
            "resource_name": resource,
            "action_name": resource,
            "action_variant_id": variant.variant_id,
            "pid": PID,
            "first_generation": first,
            "commit_generation": commit,
            "first_frame_sha256": EVIDENCE,
            "commit_frame_sha256": EVIDENCE,
            "resource_evidence_sha256": EVIDENCE,
            "action_evidence_sha256": EVIDENCE,
            "semantic_id": "combat/resource/" + resource,
            "path": selector.path,
            "point": {"x": 640.0, "y": 360.0},
            "bounds": {
                "left": 600.0,
                "top": 330.0,
                "right": 680.0,
                "bottom": 390.0,
            },
            "controlled_input_injected": True,
            "outcome_verified": False,
        }

    def analyze(self, **overrides):
        values = {
            "multiplex_evidence": self.multiplex,
            "acquisition": self.acquisition,
            "action_commits": self.actions,
            "post_map_checkpoint": self.checkpoint,
        }
        values.update(overrides)
        return analyze_alas_combat_controlled_episode(
            self.manifest,
            self.trace,
            values["multiplex_evidence"],
            values["acquisition"],
            values["action_commits"],
            values["post_map_checkpoint"],
            source_trace_sha256=EVIDENCE,
        )

    def test_complete_episode_binds_controls_actions_and_map_transition(self):
        record = self.analyze()
        self.assertEqual(
            record["actions"]["resource_sequence"],
            ["BATTLE_PREPARATION", "BATTLE_STATUS_S", "EXP_INFO_S"],
        )
        self.assertEqual(
            [item["profile_id"] for item in record["positive_controls"]],
            ["battle-status-s", "exp-info-s"],
        )
        self.assertEqual(record["map_transition"]["ammo_after"], 4)
        self.assertTrue(record["map_transition"]["target_enemy_cleared"])
        self.assertTrue(record["original_alas_decision_owner"])
        self.assertTrue(record["original_alas_goto_prefix_owner"])
        self.assertFalse(record["live_post_click_alas_state_machine_owner"])
        self.assertFalse(record["auto_promoted"])
        self.assertFalse(record["production_enabled"])
        verified = verify_alas_combat_controlled_episode(
            self.manifest,
            self.trace,
            self.multiplex,
            self.acquisition,
            self.actions,
            self.checkpoint,
            record,
            source_trace_sha256=EVIDENCE,
        )
        self.assertTrue(verified["passed"])

    def test_map_or_action_drift_fails_closed(self):
        unchanged_ammo = copy.deepcopy(self.checkpoint)
        unchanged_ammo["map"]["fleets"][0]["ammo"] = 5
        with self.assertRaisesRegex(SemanticGateClosed, "ammunition"):
            self.analyze(post_map_checkpoint=unchanged_ammo)

        reordered = (self.actions[1], self.actions[0], self.actions[2])
        with self.assertRaisesRegex(SemanticGateClosed, "not increasing"):
            self.analyze(action_commits=reordered)

    def test_trace_and_record_tampering_fail_closed(self):
        acquisition = copy.deepcopy(self.acquisition)
        acquisition["input"]["receipt_generation"] = 50
        with self.assertRaisesRegex(SemanticGateClosed, "straddle"):
            self.analyze(acquisition=acquisition)

        record = self.analyze()
        record["production_enabled"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "record changed"):
            verify_alas_combat_controlled_episode(
                self.manifest,
                self.trace,
                self.multiplex,
                self.acquisition,
                self.actions,
                self.checkpoint,
                record,
                source_trace_sha256=EVIDENCE,
            )


if __name__ == "__main__":
    unittest.main()
