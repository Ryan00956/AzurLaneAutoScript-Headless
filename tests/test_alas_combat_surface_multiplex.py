import copy
import unittest
from unittest import mock

from alas_headless import (
    ALAS_COMBAT_SURFACE_MULTIPLEX_PROFILE_IDS,
    AlasCombatObserverSnapshot,
    AlasCombatObserverTrace,
    Bounds,
    ButtonState,
    ImageState,
    OracleState,
    Point,
    SemanticGateClosed,
    UiState,
    alas_combat_surface_multiplex_candidate_present,
    analyze_alas_combat_surface_multiplex_evidence,
    verify_alas_combat_surface_multiplex_evidence,
)


TRACE_SHA256 = "a" * 64


def button(path, name, bounds):
    point = Point(
        (bounds.left + bounds.right) / 2.0,
        (bounds.top + bounds.bottom) / 2.0,
    )
    return ButtonState(
        name=name,
        path=path,
        active_in_hierarchy=True,
        active_and_enabled=True,
        interactable=True,
        raycast_top=True,
        point=point,
        bounds=bounds,
        raw={},
    )


def snapshot(*, buttons=(), sprite=""):
    images = ()
    if sprite:
        images = (
            ImageState(
                name="icon",
                path="Result/grade/icon",
                sprite=sprite,
                active_in_hierarchy=True,
                active_and_enabled=True,
                raycast_target=False,
                raycast_top=None,
                color=(1.0, 1.0, 1.0, 1.0),
                fill_amount=1.0,
                truncated=False,
                bounds=Bounds(10.0, 10.0, 20.0, 20.0),
                raw={},
            ),
        )
    return AlasCombatObserverSnapshot(
        capture_sha256=TRACE_SHA256,
        game_fingerprint="game",
        oracle_state=OracleState(1, 1, {}, {}, tuple(buttons)),
        ui_state=UiState(1, 15, 0, False, {}, (), (), images),
    )


def child_record(profile_id, *, complete=False, generations=None):
    if generations is None:
        generations = [11, 12, 13] if complete else []
    return {
        "schema": "child/" + profile_id,
        "evidence_complete": complete,
        "selected_generations": generations,
        "ambiguous_generations": [],
        "review_draft": (
            {"review_id": "review-" + profile_id} if complete else None
        ),
    }


class AlasCombatSurfaceMultiplexTests(unittest.TestCase):
    def setUp(self):
        self.trace = AlasCombatObserverTrace(
            package="com.bilibili.azurlane",
            driver_revision="driver",
            game_fingerprint="game",
            pid=4242,
            samples=(),
        )
        self.manifest = object()

    def analyzers(self, matches=()):
        def analyze(_manifest, _trace, *, profile_id, **_kwargs):
            return child_record(profile_id, complete=profile_id in matches)

        return mock.patch.multiple(
            "alas_headless.alas_combat_surface_multiplex",
            analyze_alas_combat_rare_surface_evidence=mock.Mock(
                side_effect=analyze
            ),
            analyze_alas_combat_result_surface_evidence=mock.Mock(
                side_effect=analyze
            ),
        )

    def test_profile_union_is_exact_and_ordered(self):
        self.assertEqual(
            ALAS_COMBAT_SURFACE_MULTIPLEX_PROFILE_IDS,
            (
                "guild-popup",
                "mission-popup",
                "battle-status-a",
                "battle-status-b",
                "battle-status-c",
                "battle-status-d",
                "exp-info-a",
                "exp-info-b",
            ),
        )

    def test_candidate_prefilter_handles_negative_result_and_mission_pair(self):
        self.assertFalse(alas_combat_surface_multiplex_candidate_present(snapshot()))
        self.assertTrue(
            alas_combat_surface_multiplex_candidate_present(
                snapshot(sprite="letter_A")
            )
        )
        mission = (
            button("Mission/frame/ack", "ack", Bounds(432, 493, 543, 533)),
            button("Mission/frame/go", "go", Bounds(719, 493, 861, 534)),
        )
        self.assertTrue(
            alas_combat_surface_multiplex_candidate_present(
                snapshot(buttons=mission)
            )
        )

    def test_no_match_keeps_aggregate_incomplete(self):
        with self.analyzers():
            record = analyze_alas_combat_surface_multiplex_evidence(
                self.manifest,
                self.trace,
                source_trace_sha256=TRACE_SHA256,
            )
        self.assertEqual(record["profile_count"], 8)
        self.assertFalse(record["candidate_complete"])
        self.assertFalse(record["evidence_complete"])
        self.assertEqual(record["matched_profile_ids"], [])
        self.assertEqual(record["review_drafts"], [])

    def test_one_match_emits_only_that_review_draft(self):
        with self.analyzers(("exp-info-b",)):
            record = analyze_alas_combat_surface_multiplex_evidence(
                self.manifest,
                self.trace,
                source_trace_sha256=TRACE_SHA256,
            )
        self.assertTrue(record["candidate_complete"])
        self.assertTrue(record["evidence_complete"])
        self.assertFalse(record["ambiguous_match"])
        self.assertEqual(record["matched_profile_ids"], ["exp-info-b"])
        self.assertEqual(record["selected_generations"], [11, 12, 13])
        self.assertEqual(record["review_drafts"][0]["profile_id"], "exp-info-b")

    def test_multiple_matches_are_ambiguous_and_export_no_draft(self):
        matches = ("guild-popup", "mission-popup")
        with self.analyzers(matches):
            record = analyze_alas_combat_surface_multiplex_evidence(
                self.manifest,
                self.trace,
                source_trace_sha256=TRACE_SHA256,
            )
        self.assertTrue(record["candidate_complete"])
        self.assertFalse(record["evidence_complete"])
        self.assertTrue(record["ambiguous_match"])
        self.assertEqual(record["matched_profile_ids"], list(matches))
        self.assertEqual(record["ambiguous_generations"], [11, 12, 13])
        self.assertEqual(record["review_drafts"], [])
        self.assertTrue(
            all("review_draft" not in item for item in record["profile_results"])
        )

    def test_verifier_recomputes_and_rejects_tampering(self):
        with self.analyzers(("battle-status-a",)):
            record = analyze_alas_combat_surface_multiplex_evidence(
                self.manifest,
                self.trace,
                source_trace_sha256=TRACE_SHA256,
            )
            verified = verify_alas_combat_surface_multiplex_evidence(
                self.manifest,
                self.trace,
                record,
                source_trace_sha256=TRACE_SHA256,
            )
        self.assertTrue(verified["passed"])
        self.assertEqual(verified["profile_count"], 8)

        tampered = copy.deepcopy(record)
        tampered["matched_profile_ids"] = []
        with self.analyzers(("battle-status-a",)):
            with self.assertRaisesRegex(SemanticGateClosed, "record changed"):
                verify_alas_combat_surface_multiplex_evidence(
                    self.manifest,
                    self.trace,
                    tampered,
                    source_trace_sha256=TRACE_SHA256,
                )


if __name__ == "__main__":
    unittest.main()
