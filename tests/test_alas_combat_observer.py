import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from alas_headless import (
    ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA,
    ALAS_COMBAT_MAPPING_RECEIPT_SCHEMA,
    ALAS_COMBAT_OBSERVER_TRACE_SCHEMA,
    ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES,
    ALAS_COMBAT_REPLAY_PHASES,
    ALAS_COMBAT_REPLAY_RESOURCE_NAMES,
    AlasCampaignCombatAdmission,
    AlasCombatBlockerMapping,
    AlasCombatFleetStatsMapping,
    AlasCombatObserverManifest,
    AlasCombatResourceMapping,
    AlasCombatUnityRecordKind,
    AlasCombatUnitySelector,
    AlasCombatReplayPhase,
    Bounds,
    Point,
    SemanticGateClosed,
    audit_alas_combat_observer_manifest,
    analyze_alas_combat_observer_candidates,
    alas_combat_unity_selector_present,
    alas_combat_replay_phase_sequence,
    build_alas_combat_observer_trace,
    build_alas_combat_trace_frame,
    build_alas_campaign_combat_replay_from_observer,
    commit_alas_combat_resource_action_for_evidence,
    compile_alas_combat_observer_fixture,
    load_alas_combat_observer_fixture,
    load_alas_combat_observer_manifest,
    merge_alas_combat_observer_traces,
    parse_alas_combat_observer_fixture_frame,
    parse_alas_combat_observer_trace,
    prepare_alas_combat_resource_action,
    promote_alas_combat_mapping_review,
    select_alas_combat_observer_trace_samples,
    unqualified_alas_combat_observer_manifest,
    verify_alas_combat_mapping_receipt,
)


PACKAGE = "com.bilibili.azurlane"
DRIVER = "b" * 40
GAME = "pinned-test-game"
EVIDENCE = "a" * 64
ACTION_RESOURCES = {
    "AUTOMATION_CONFIRM",
    "BATTLE_PREPARATION",
    "BATTLE_STATUS_S",
    "EXP_INFO_S",
    "GET_ITEMS_1",
    "GET_MISSION",
}


def selector_for(name):
    if name in ACTION_RESOURCES:
        return AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.BUTTON,
            "Combat/Button/" + name,
            name,
            require_top_raycast=True,
        )
    return AlasCombatUnitySelector(
        AlasCombatUnityRecordKind.IMAGE,
        "Combat/Image/" + name,
        name,
        sprite="sprite_" + name.lower(),
    )


def qualified_manifest(blockers=None):
    hp = tuple(
        AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.IMAGE,
            "Combat/Fleet/HP/{0}".format(index),
            "hp_{0}".format(index),
            sprite="hp_fill",
        )
        for index in range(6)
    )
    levels = tuple(
        AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.TEXT,
            "Combat/Fleet/Level/{0}".format(index),
            "level_{0}".format(index),
        )
        for index in range(6)
    )
    if blockers is None:
        blockers = (
            AlasCombatUnitySelector(
                AlasCombatUnityRecordKind.IMAGE,
                "Combat/Blocker/NetworkDown",
                "NetworkDown",
                sprite="network_down",
            ),
        )
    return AlasCombatObserverManifest(
        package=PACKAGE,
        driver_revision=DRIVER,
        game_fingerprint=GAME,
        resources=tuple(
            AlasCombatResourceMapping(name, (selector_for(name),), EVIDENCE)
            for name in ALAS_COMBAT_REPLAY_RESOURCE_NAMES
        ),
        blockers=(
            AlasCombatBlockerMapping(
                "test_blocker",
                tuple(blockers),
                EVIDENCE,
            ),
        ),
        blocker_review_complete=True,
        fleet_stats=AlasCombatFleetStatsMapping(hp, levels, EVIDENCE),
    )


def admission():
    return AlasCampaignCombatAdmission(
        generation=10,
        input_generation=10,
        stage_code="12-4",
        battle_count=0,
        branch_name="battle_0",
        fleet_index=1,
        fleet_marker="cell_fleet_test",
        origin_node="D6",
        target_node="D6",
        route_nodes=("D6",),
        enemy_object_id=1204090,
        enemy_sprite="hm1",
        enemy_level=113,
        ammo_before=5,
        cell_path="LevelGrid/chapter_cell_quad_6_4",
        point=Point(160.0, 240.0),
        bounds=Bounds(140.0, 220.0, 180.0, 260.0),
        decision_signature=("decision",),
        map_signature=("map",),
    )


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


def button_record(name, *, raycast_top=True):
    return {
        "name": name,
        "path": "Combat/Button/" + name,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "interactable": True,
        "raycast_top": raycast_top,
        "adb_point": {"x": 100.0, "y": 100.0},
        "adb_bounds": {
            "left": 90.0,
            "top": 90.0,
            "right": 110.0,
            "bottom": 110.0,
        },
    }


def image_record(name, path=None, sprite=None, fill=1.0):
    return {
        "kind": "image",
        "name": name,
        "path": path or "Combat/Image/" + name,
        "sprite": sprite or "sprite_" + name.lower(),
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "raycast_target": False,
        "raycast_top": None,
        "color": {"red": 1.0, "green": 1.0, "blue": 1.0, "alpha": 1.0},
        "fill_amount": fill,
        "flags": 0,
        "adb_bounds": {
            "left": 10.0,
            "top": 10.0,
            "right": 20.0,
            "bottom": 20.0,
        },
    }


def toggle_record(name, *, checked):
    return {
        "name": name,
        "path": "Combat/Toggle/" + name,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "interactable": True,
        "checked": checked,
        "raycast_top": None,
        "adb_point": None,
        "adb_bounds": None,
    }


def text_record(index):
    return {
        "kind": "ugui-text",
        "name": "level_{0}".format(index),
        "path": "Combat/Fleet/Level/{0}".format(index),
        "text": str(120 + index),
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "flags": 0,
        "adb_bounds": {
            "left": 10.0,
            "top": 10.0,
            "right": 20.0,
            "bottom": 20.0,
        },
    }


def campaign_map(generation, stable):
    cells = []
    for row in range(1, 9):
        for column in range(1, 12):
            node = chr(ord("A") + column - 1) + str(row)
            left = float(column * 40 - 20)
            top = float(row * 40 - 20)
            cells.append(
                {
                    "row": row,
                    "column": column,
                    "node": node,
                    "button_path": "LevelGrid/chapter_cell_quad_{0}_{1}".format(
                        row, column
                    ),
                    "point": {"x": left + 20.0, "y": top + 20.0},
                    "bounds": {
                        "left": left,
                        "top": top,
                        "right": left + 40.0,
                        "bottom": top + 40.0,
                    },
                }
            )
    return {
        "generation": generation,
        "stage_code": "12-4",
        "rows": 8,
        "columns": 11,
        "cells": cells,
        "land_nodes": [],
        "fleets": [
            {
                "marker": "cell_fleet_test",
                "node": "D6",
                "ammo": 4 if stable else 5,
                "ammo_capacity": 5,
            }
        ],
        "enemies": []
        if stable
        else [
            {
                "row": 6,
                "column": 4,
                "node": "D6",
                "object_id": 1204090,
                "sprite": "hm1",
                "scale": 1,
                "genre": "Carrier",
                "level": 113,
                "fighting": True,
            }
        ],
        "pickups": [],
        "displayed_fleet_index": 1,
        "current_fleet_marker": "cell_fleet_test",
        "current_fleet_roster_sprites": [
            "ship_1",
            "ship_2",
            "ship_3",
            "ship_4",
            "ship_5",
            "test",
        ],
    }


def frame(generation, resources, map_value=None, *, raycast_top=True):
    buttons = [
        button_record(name, raycast_top=raycast_top)
        for name in resources
        if name in ACTION_RESOURCES
    ]
    images = [
        image_record(name)
        for name in resources
        if name not in ACTION_RESOURCES
    ]
    texts = []
    if map_value is not None and not map_value["enemies"]:
        images.extend(
            image_record(
                "hp_{0}".format(index),
                path="Combat/Fleet/HP/{0}".format(index),
                sprite="hp_fill",
                fill=1.0 - index / 10.0,
            )
            for index in range(6)
        )
        texts.extend(text_record(index) for index in range(6))
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
    payload = {
        "snapshot": snapshot,
        "buttons": button_payload,
        "ui": ui,
        "campaign_map": map_value,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {**payload, "sha256": digest}


def fixture_value(phases=ALAS_COMBAT_REPLAY_PHASES):
    phases = tuple(phases)
    frames = []
    for offset, phase in enumerate(phases, start=1):
        map_value = None
        if phase.value == "map_enemy_searching":
            map_value = campaign_map(10 + offset, False)
        elif phase.value == "map_stable":
            map_value = campaign_map(10 + offset, True)
        frames.append(
            frame(
                10 + offset,
                ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES[phase],
                map_value,
            )
        )
    return {
        "schema": ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA,
        "game_fingerprint": GAME,
        "frames": frames,
    }


class AlasCombatObserverContractTests(unittest.TestCase):
    def write_fixture(self, value):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "combat.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_unqualified_manifest_is_honestly_zero_of_41(self):
        coverage = audit_alas_combat_observer_manifest(
            unqualified_alas_combat_observer_manifest(
                driver_revision=DRIVER, game_fingerprint=GAME
            )
        )

        self.assertEqual(coverage.total_resources, 41)
        self.assertEqual(coverage.qualified_resources, 0)
        self.assertFalse(coverage.production_ready)
        self.assertEqual(
            set(coverage.unqualified_resources),
            set(ALAS_COMBAT_REPLAY_RESOURCE_NAMES),
        )

    def test_complete_raw_fixture_infers_six_frames_without_phase_tokens(self):
        manifest = qualified_manifest()
        snapshots = load_alas_combat_observer_fixture(
            self.write_fixture(fixture_value()), manifest
        )

        replay = build_alas_campaign_combat_replay_from_observer(
            admission(), snapshots, manifest
        )

        self.assertEqual(len(replay.frames), 6)
        self.assertEqual(replay.frames[0].generation, 11)
        self.assertEqual(replay.frames[-1].generation, 16)
        self.assertEqual(replay.frames[-1].hp, (1.0, 0.9, 0.8, 0.7, 0.6, 0.5))
        self.assertEqual(replay.frames[-1].levels, (120, 121, 122, 123, 124, 125))
        self.assertTrue(replay.frames[-1].fleet_on_target)

    def test_optional_reward_and_mission_frames_are_inferred_from_resources(self):
        manifest = qualified_manifest()
        phases = alas_combat_replay_phase_sequence(
            include_get_items=True,
            include_get_mission=True,
        )
        snapshots = load_alas_combat_observer_fixture(
            self.write_fixture(fixture_value(phases)), manifest
        )

        replay = build_alas_campaign_combat_replay_from_observer(
            admission(), snapshots, manifest
        )

        self.assertEqual(tuple(frame.phase for frame in replay.frames), phases)
        self.assertEqual(replay.frames[3].phase, AlasCombatReplayPhase.GET_ITEMS)
        self.assertEqual(replay.frames[5].phase, AlasCombatReplayPhase.GET_MISSION)
        self.assertEqual(len(replay.frames), 8)

    def test_optional_automation_confirmation_is_inferred_before_preparation(self):
        manifest = qualified_manifest()
        phases = alas_combat_replay_phase_sequence(
            include_automation_confirm=True,
            include_get_items=True,
            include_get_mission=True,
        )
        snapshots = load_alas_combat_observer_fixture(
            self.write_fixture(fixture_value(phases)), manifest
        )

        replay = build_alas_campaign_combat_replay_from_observer(
            admission(), snapshots, manifest
        )

        self.assertEqual(tuple(frame.phase for frame in replay.frames), phases)
        self.assertEqual(replay.frames[0].phase, AlasCombatReplayPhase.AUTOMATION_CONFIRM)
        self.assertEqual(replay.frames[1].phase, AlasCombatReplayPhase.BATTLE_PREPARATION)
        self.assertEqual(len(replay.frames), 9)

    def test_toggle_state_selector_distinguishes_automation_on_from_off(self):
        manifest = qualified_manifest()
        toggle_selector = AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.TOGGLE_ON,
            "Combat/Toggle/AUTOMATION_ON",
            "AUTOMATION_ON",
        )
        manifest = replace(
            manifest,
            resources=tuple(
                AlasCombatResourceMapping(name, (toggle_selector,), EVIDENCE)
                if name == "AUTOMATION_ON"
                else mapping
                for name, mapping in (
                    (item.resource_name, item) for item in manifest.resources
                )
            ),
        )
        value = fixture_value()
        preparation = value["frames"][0]
        preparation["ui"]["images"] = [
            item
            for item in preparation["ui"]["images"]
            if item["name"] != "AUTOMATION_ON"
        ]
        preparation["ui"]["image_count"] -= 1
        preparation["ui"]["toggles"] = [
            toggle_record("AUTOMATION_ON", checked=True)
        ]
        preparation["ui"]["toggle_count"] = 1
        payload = {
            key: preparation[key]
            for key in ("snapshot", "buttons", "ui", "campaign_map")
        }
        preparation["sha256"] = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        snapshots = load_alas_combat_observer_fixture(
            self.write_fixture(value), manifest
        )
        replay = build_alas_campaign_combat_replay_from_observer(
            admission(), snapshots, manifest
        )

        self.assertEqual(replay.frames[0].phase, AlasCombatReplayPhase.BATTLE_PREPARATION)
        off_selector = replace(
            toggle_selector, kind=AlasCombatUnityRecordKind.TOGGLE_OFF
        )
        self.assertFalse(
            alas_combat_unity_selector_present(snapshots[0], off_selector)
        )

    def test_unqualified_manifest_cannot_build_replay(self):
        manifest = unqualified_alas_combat_observer_manifest(
            driver_revision=DRIVER, game_fingerprint=GAME
        )
        with self.assertRaisesRegex(SemanticGateClosed, "0/41"):
            build_alas_campaign_combat_replay_from_observer(
                admission(), (), manifest
            )

    def test_fixture_rejects_synthetic_phase_labels(self):
        value = fixture_value()
        value["frames"][0]["phase"] = "battle_preparation"
        with self.assertRaisesRegex(SemanticGateClosed, "must not provide phase"):
            load_alas_combat_observer_fixture(
                self.write_fixture(value), qualified_manifest()
            )

    def test_fixture_rejects_tampered_record_hash(self):
        value = fixture_value()
        value["frames"][0]["buttons"]["buttons"][0]["name"] = "tampered"
        with self.assertRaisesRegex(SemanticGateClosed, "frame hash changed"):
            load_alas_combat_observer_fixture(
                self.write_fixture(value), qualified_manifest()
            )

    def test_action_requires_top_raycast(self):
        value = fixture_value()
        first = value["frames"][0]
        first["buttons"]["buttons"][0]["raycast_top"] = False
        payload = {key: first[key] for key in ("snapshot", "buttons", "ui", "campaign_map")}
        first["sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        snapshots = load_alas_combat_observer_fixture(
            self.write_fixture(value), qualified_manifest()
        )
        with self.assertRaisesRegex(SemanticGateClosed, "top-raycast"):
            build_alas_campaign_combat_replay_from_observer(
                admission(), snapshots, qualified_manifest()
            )

    def test_reviewed_action_resolves_one_exact_button_without_input(self):
        manifest = qualified_manifest()
        snapshot = parse_alas_combat_observer_fixture_frame(
            frame(20, ("BATTLE_STATUS_S",)), manifest
        )

        receipt = prepare_alas_combat_resource_action(
            snapshot, manifest, "BATTLE_STATUS_S"
        )

        self.assertEqual(receipt.semantic_id, "combat/resource/BATTLE_STATUS_S")
        self.assertEqual(receipt.generation, 20)
        self.assertEqual(receipt.path, "Combat/Button/BATTLE_STATUS_S")
        self.assertEqual(receipt.point, Point(100.0, 100.0))

    def test_reviewed_action_rejects_active_blocker_and_competing_action(self):
        blocked_manifest = qualified_manifest(
            blockers=(selector_for("BATTLE_STATUS_S"),)
        )
        blocked = parse_alas_combat_observer_fixture_frame(
            frame(20, ("BATTLE_STATUS_S",)), blocked_manifest
        )
        with self.assertRaisesRegex(SemanticGateClosed, "blocked by"):
            prepare_alas_combat_resource_action(
                blocked, blocked_manifest, "BATTLE_STATUS_S"
            )

        manifest = qualified_manifest()
        ambiguous = parse_alas_combat_observer_fixture_frame(
            frame(21, ("BATTLE_STATUS_S", "EXP_INFO_S")), manifest
        )
        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous with"):
            prepare_alas_combat_resource_action(
                ambiguous, manifest, "BATTLE_STATUS_S"
            )

    def test_live_evidence_action_requires_two_stable_generations_then_taps_once(self):
        manifest = qualified_manifest()
        frames = (
            frame(20, ("BATTLE_STATUS_S",)),
            frame(21, ("BATTLE_STATUS_S",)),
        )

        class Bridge:
            pid = 4242

            def __init__(self):
                self.request_count = 0
                self.taps = []

            def foreground_component(self):
                return "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"

            def request(self, request):
                index = min(self.request_count // 3, 1)
                endpoint = request.strip().split("/")[-1]
                self.request_count += 1
                return frames[index][
                    {
                        "snapshot": "snapshot",
                        "buttons": "buttons",
                        "ui": "ui",
                    }[endpoint]
                ]

            def tap(self, x, y):
                self.taps.append((x, y))

        bridge = Bridge()
        session = mock.Mock()
        session.package = PACKAGE
        session.driver_revision = DRIVER
        session.component = (
            "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
        )
        session.bridge = bridge

        commit = commit_alas_combat_resource_action_for_evidence(
            session,
            manifest,
            "BATTLE_STATUS_S",
            expected_pid=4242,
            minimum_generation=19,
            action_budget=1,
            settle_interval_seconds=0.01,
            sleep=lambda _: None,
        )

        session.open.assert_called_once_with()
        self.assertEqual(bridge.taps, [(100, 100)])
        self.assertEqual(commit.first_generation, 20)
        self.assertEqual(commit.commit_generation, 21)
        self.assertEqual(commit.receipt.semantic_id, "combat/resource/BATTLE_STATUS_S")

    def test_live_evidence_action_rejects_wrong_pid_before_read_or_tap(self):
        manifest = qualified_manifest()
        session = mock.Mock()
        session.package = PACKAGE
        session.driver_revision = DRIVER
        session.component = (
            "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
        )
        session.bridge.pid = 4243

        with self.assertRaisesRegex(SemanticGateClosed, "process changed"):
            commit_alas_combat_resource_action_for_evidence(
                session,
                manifest,
                "BATTLE_STATUS_S",
                expected_pid=4242,
                minimum_generation=19,
                action_budget=1,
                sleep=lambda _: None,
            )
        session.bridge.request.assert_not_called()
        session.bridge.tap.assert_not_called()

    def test_live_evidence_action_rejects_endpoint_pid_drift(self):
        manifest = qualified_manifest()
        frames = [
            frame(20, ("BATTLE_STATUS_S",)),
            frame(21, ("BATTLE_STATUS_S",)),
        ]
        for payload in (
            frames[1]["snapshot"],
            frames[1]["buttons"],
            frames[1]["ui"],
        ):
            payload["pid"] = 4243
        frame_payload = {
            key: frames[1][key]
            for key in ("snapshot", "buttons", "ui", "campaign_map")
        }
        frames[1]["sha256"] = hashlib.sha256(
            json.dumps(
                frame_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        class Bridge:
            pid = 4242

            def __init__(self):
                self.request_count = 0
                self.taps = []

            def foreground_component(self):
                return "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"

            def request(self, request):
                index = min(self.request_count // 3, 1)
                endpoint = request.strip().split("/")[-1]
                self.request_count += 1
                return frames[index][
                    {"snapshot": "snapshot", "buttons": "buttons", "ui": "ui"}[
                        endpoint
                    ]
                ]

            def tap(self, x, y):
                self.taps.append((x, y))

        session = mock.Mock()
        session.package = PACKAGE
        session.driver_revision = DRIVER
        session.component = (
            "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
        )
        session.bridge = Bridge()

        with self.assertRaisesRegex(SemanticGateClosed, "snapshot process changed"):
            commit_alas_combat_resource_action_for_evidence(
                session,
                manifest,
                "BATTLE_STATUS_S",
                expected_pid=4242,
                minimum_generation=19,
                action_budget=1,
                settle_interval_seconds=0.01,
                sleep=lambda _: None,
            )
        self.assertEqual(session.bridge.taps, [])

    def test_active_reviewed_blocker_closes_replay(self):
        blocker = AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.IMAGE,
            "Combat/Image/AUTOMATION_ON",
            "AUTOMATION_ON",
            sprite="sprite_automation_on",
        )
        manifest = qualified_manifest((blocker,))
        snapshots = load_alas_combat_observer_fixture(
            self.write_fixture(fixture_value()), manifest
        )
        with self.assertRaisesRegex(SemanticGateClosed, "blocker is active"):
            build_alas_campaign_combat_replay_from_observer(
                admission(), snapshots, manifest
            )

    def test_compound_blocker_requires_every_exact_selector(self):
        active = AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.IMAGE,
            "Combat/Image/AUTOMATION_ON",
            "AUTOMATION_ON",
            sprite="sprite_automation_on",
        )
        absent = AlasCombatUnitySelector(
            AlasCombatUnityRecordKind.TEXT,
            "Combat/Blocker/NetworkDown/content",
            "content",
            text="[NetworkDown]",
        )
        manifest = qualified_manifest()
        manifest = replace(
            manifest,
            blockers=(
                AlasCombatBlockerMapping(
                    "network_down",
                    (active, absent),
                    EVIDENCE,
                ),
            ),
        )
        snapshots = load_alas_combat_observer_fixture(
            self.write_fixture(fixture_value()), manifest
        )

        replay = build_alas_campaign_combat_replay_from_observer(
            admission(), snapshots, manifest
        )

        self.assertEqual(len(replay.frames), 6)

    def test_removed_resource_mapping_is_surface_drift(self):
        manifest = qualified_manifest()
        with self.assertRaisesRegex(SemanticGateClosed, "surface changed"):
            audit_alas_combat_observer_manifest(
                replace(manifest, resources=manifest.resources[:-1])
            )

    def test_versioned_json_manifest_preserves_partial_fail_closed_coverage(self):
        root = Path(__file__).resolve().parents[1]
        manifest = load_alas_combat_observer_manifest(
            root / "integration" / "alas" / "combat-observer-manifest.json"
        )
        coverage = audit_alas_combat_observer_manifest(manifest)

        self.assertEqual(coverage.total_resources, 41)
        self.assertEqual(coverage.qualified_resources, 10)
        self.assertEqual(coverage.qualified_blockers, 1)
        self.assertFalse(coverage.blocker_review_complete)
        self.assertFalse(coverage.blockers_qualified)
        self.assertFalse(coverage.production_ready)

    @staticmethod
    def trace_frames(phases=ALAS_COMBAT_REPLAY_PHASES):
        manifest = qualified_manifest()
        fixture = fixture_value(phases)
        frames = []
        typed_maps = []
        for source in fixture["frames"]:
            typed_maps.append(
                parse_alas_combat_observer_fixture_frame(source, manifest).campaign_map
            )
            frame_value = json.loads(json.dumps(source))
            frame_value["campaign_map"] = None
            payload = {
                key: frame_value[key]
                for key in ("snapshot", "buttons", "ui", "campaign_map")
            }
            frame_value["sha256"] = hashlib.sha256(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            rebuilt, typed = build_alas_combat_trace_frame(
                frame_value["snapshot"],
                frame_value["buttons"],
                frame_value["ui"],
                manifest,
            )
            self_hash = rebuilt["sha256"]
            if self_hash != frame_value["sha256"] or typed.campaign_map is not None:
                raise AssertionError("test trace frame did not round-trip")
            frames.append(rebuilt)
        return manifest, tuple(frames), tuple(typed_maps)

    def test_optional_trace_analysis_and_compiler_use_only_final_map_phases(self):
        phases = alas_combat_replay_phase_sequence(
            include_get_items=True,
            include_get_mission=True,
        )
        manifest, frames, typed_maps = self.trace_frames(phases)
        trace = parse_alas_combat_observer_trace(
            build_alas_combat_observer_trace(
                manifest,
                tuple(
                    ("2026-08-10T06:03:{0:02d}Z".format(index), frame_value)
                    for index, frame_value in enumerate(frames, start=1)
                ),
            ),
            manifest,
        )
        selected = select_alas_combat_observer_trace_samples(
            trace, trace.generations
        )
        report = analyze_alas_combat_observer_candidates(
            selected, phase_sequence=phases
        )
        with mock.patch(
            "alas_headless.alas_combat_trace._offline_campaign_map",
            side_effect=(typed_maps[-2], typed_maps[-1]),
        ) as offline:
            compiled = compile_alas_combat_observer_fixture(
                selected,
                manifest,
                stage_code="12-4",
                columns=11,
                rows=8,
                land_cells=((0, 0),),
                expected_fleet_count=2,
                phase_sequence=phases,
            )

        self.assertEqual(
            tuple(item["phase"] for item in report["phases"]),
            tuple(phase.value for phase in phases),
        )
        self.assertEqual(offline.call_count, 2)
        self.assertTrue(
            all(frame["campaign_map"] is None for frame in compiled["frames"][:-2])
        )
        self.assertIsNotNone(compiled["frames"][-2]["campaign_map"])
        self.assertIsNotNone(compiled["frames"][-1]["campaign_map"])

    def test_raw_trace_round_trip_selects_generations_and_reports_candidates(self):
        manifest, frames, _ = self.trace_frames()
        samples = tuple(
            ("2026-08-10T06:00:{0:02d}Z".format(index), frame_value)
            for index, frame_value in enumerate(frames, start=1)
        )
        value = build_alas_combat_observer_trace(manifest, samples)

        trace = parse_alas_combat_observer_trace(value, manifest)
        selected = select_alas_combat_observer_trace_samples(
            trace, trace.generations
        )
        report = analyze_alas_combat_observer_candidates(selected)

        self.assertEqual(value["schema"], ALAS_COMBAT_OBSERVER_TRACE_SCHEMA)
        self.assertFalse(value["input_injected"])
        self.assertEqual(trace.generations, (11, 12, 13, 14, 15, 16))
        self.assertEqual(len(report["phases"]), 6)
        self.assertEqual(report["phases"][0]["phase"], "battle_preparation")
        self.assertTrue(report["phases"][0]["actionable_buttons"])

    def test_adjacent_trace_merge_requires_one_identity_and_increasing_generations(self):
        manifest, frames, _ = self.trace_frames()
        first = parse_alas_combat_observer_trace(
            build_alas_combat_observer_trace(
                manifest,
                tuple(
                    ("2026-08-10T06:10:{0:02d}Z".format(index), frame)
                    for index, frame in enumerate(frames[:3], start=1)
                ),
            ),
            manifest,
        )
        second = parse_alas_combat_observer_trace(
            build_alas_combat_observer_trace(
                manifest,
                tuple(
                    ("2026-08-10T06:11:{0:02d}Z".format(index), frame)
                    for index, frame in enumerate(frames[3:], start=1)
                ),
            ),
            manifest,
        )

        merged = merge_alas_combat_observer_traces((first, second))

        self.assertEqual(merged.generations, tuple(range(11, 17)))
        self.assertEqual(
            tuple(sample.sequence for sample in merged.samples), tuple(range(1, 7))
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not increasing"):
            merge_alas_combat_observer_traces((second, first))

    def test_trace_rejects_input_claim_and_phase_token(self):
        manifest, frames, _ = self.trace_frames()
        samples = tuple(
            ("2026-08-10T06:01:{0:02d}Z".format(index), frame_value)
            for index, frame_value in enumerate(frames, start=1)
        )
        value = build_alas_combat_observer_trace(manifest, samples)
        value["input_injected"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "not read-only"):
            parse_alas_combat_observer_trace(value, manifest)

        value["input_injected"] = False
        value["samples"][0]["frame"]["phase"] = "battle_preparation"
        with self.assertRaisesRegex(SemanticGateClosed, "frame is malformed"):
            parse_alas_combat_observer_trace(value, manifest)

    def test_trace_compiler_adds_only_derived_map_projections(self):
        manifest, frames, typed_maps = self.trace_frames()
        samples = tuple(
            ("2026-08-10T06:02:{0:02d}Z".format(index), frame_value)
            for index, frame_value in enumerate(frames, start=1)
        )
        trace = parse_alas_combat_observer_trace(
            build_alas_combat_observer_trace(manifest, samples), manifest
        )
        selected = select_alas_combat_observer_trace_samples(
            trace, trace.generations
        )
        with mock.patch(
            "alas_headless.alas_combat_trace._offline_campaign_map",
            side_effect=(typed_maps[4], typed_maps[5]),
        ):
            compiled = compile_alas_combat_observer_fixture(
                selected,
                manifest,
                stage_code="12-4",
                columns=11,
                rows=8,
                land_cells=((0, 0),),
                expected_fleet_count=2,
            )

        self.assertEqual(compiled["schema"], ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA)
        self.assertTrue(all("phase" not in frame_value for frame_value in compiled["frames"]))
        self.assertIsNone(compiled["frames"][3]["campaign_map"])
        self.assertIsNotNone(compiled["frames"][4]["campaign_map"])
        self.assertEqual(compiled["frames"][5]["campaign_map"]["stage_code"], "12-4")

    def test_mapping_review_promotes_only_records_present_in_every_frame(self):
        qualified, frames, _ = self.trace_frames()
        baseline = replace(
            qualified,
            resources=tuple(
                (
                    AlasCombatResourceMapping(mapping.resource_name)
                    if mapping.resource_name == "IN_MAP"
                    else mapping
                )
                for mapping in qualified.resources
            ),
            blockers=(),
            blocker_review_complete=False,
        )
        trace = parse_alas_combat_observer_trace(
            build_alas_combat_observer_trace(
                baseline,
                tuple(
                    ("2026-08-10T07:00:{0:02d}Z".format(index), frame)
                    for index, frame in enumerate(frames, start=1)
                ),
            ),
            baseline,
        )
        selector = selector_for("IN_MAP")
        selector_json = {
            "kind": selector.kind.value,
            "path": selector.path,
            "name": selector.name,
            "sprite": selector.sprite,
            "text": selector.text,
            "require_top_raycast": selector.require_top_raycast,
        }
        review = {
            "schema": "alas-headless.g22-combat-mapping-review/v1",
            "review_id": "unit-in-map",
            "trace_sha256": EVIDENCE,
            "generations": [15, 16],
            "resources": [{"resource_name": "IN_MAP", "selectors": [selector_json]}],
            "blockers": [{"blocker_name": "map_overlay", "selectors": [selector_json]}],
            "blocker_review_complete": False,
        }

        promoted, receipt = promote_alas_combat_mapping_review(
            baseline,
            trace,
            review,
            source_trace_sha256=EVIDENCE,
        )
        coverage = audit_alas_combat_observer_manifest(promoted)

        self.assertEqual(receipt["schema"], ALAS_COMBAT_MAPPING_RECEIPT_SCHEMA)
        self.assertEqual(coverage.qualified_resources, 41)
        self.assertEqual(coverage.qualified_blockers, 1)
        self.assertFalse(coverage.blockers_qualified)
        self.assertFalse(coverage.production_ready)
        self.assertFalse(receipt["input_injected"])
        verified = verify_alas_combat_mapping_receipt(
            promoted,
            trace,
            receipt,
            source_trace_sha256=EVIDENCE,
        )
        self.assertTrue(verified["passed"])
        self.assertEqual(verified["verified_resources"], 1)
        self.assertEqual(verified["verified_blockers"], 1)
        idempotent, _ = promote_alas_combat_mapping_review(
            promoted,
            trace,
            review,
            source_trace_sha256=EVIDENCE,
        )
        self.assertEqual(idempotent, promoted)

        tampered_receipt = json.loads(json.dumps(receipt))
        tampered_receipt["source_frames"][0]["frame_sha256"] = "0" * 64
        with self.assertRaisesRegex(SemanticGateClosed, "frame identity changed"):
            verify_alas_combat_mapping_receipt(
                promoted,
                trace,
                tampered_receipt,
                source_trace_sha256=EVIDENCE,
            )

        changed = json.loads(json.dumps(review))
        changed["resources"][0]["selectors"][0]["sprite"] = "drifted"
        with self.assertRaisesRegex(SemanticGateClosed, "selector is absent"):
            promote_alas_combat_mapping_review(
                baseline,
                trace,
                changed,
                source_trace_sha256=EVIDENCE,
            )


if __name__ == "__main__":
    unittest.main()
