import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import alas_headless.alas_combat_branch_replay as branch_replay
from alas_headless import (
    ALAS_COMBAT_BRANCH_REPLAY_SCHEMA,
    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES,
    ALAS_COMBAT_RESOURCE_ACTION_TARGETS,
    AlasCombatBranchReplayResult,
    AlasCombatBranchReplayScenario,
    SemanticGateClosed,
    alas_combat_branch_replay_to_json,
    replay_alas_combat_defensive_branches,
    verify_alas_combat_branch_replay_record,
)


class AlasCombatBranchReplayTests(unittest.TestCase):
    def test_pinned_scenarios_cover_only_the_defensive_input_contract(self):
        scenarios = branch_replay._SCENARIOS
        names = tuple(spec.name for spec in scenarios)

        self.assertEqual(len(scenarios), 16)
        self.assertEqual(len(names), len(set(names)))
        for spec in scenarios:
            self.assertTrue(
                set(spec.expected_queries).issubset(
                    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES
                )
            )
            for action in spec.expected_actions:
                owners = tuple(
                    resource
                    for resource, actions in ALAS_COMBAT_RESOURCE_ACTION_TARGETS.items()
                    if action in actions
                )
                self.assertTrue(owners, action)

    def test_driver_enforces_exact_query_action_and_sleep_order(self):
        spec = next(
            item
            for item in branch_replay._SCENARIOS
            if item.name == "battle-status-b"
        )
        driver = branch_replay._BranchDriver(spec)

        for name in spec.expected_queries:
            driver.query(name)
        for duration in spec.expected_sleeps:
            driver.sleep(duration)
        for name in spec.expected_actions:
            driver.click(SimpleNamespace(name=name))

        driver.validate(spec.expected_return)
        with self.assertRaisesRegex(SemanticGateClosed, "extra action"):
            driver.click(SimpleNamespace(name="BATTLE_STATUS_B"))
        unqueried = branch_replay._BranchDriver(spec)
        with self.assertRaisesRegex(SemanticGateClosed, "owner was not queried"):
            unqueried.click(SimpleNamespace(name="BATTLE_STATUS_B"))

    def test_one_original_style_branch_runs_on_an_isolated_copy(self):
        cancel = SimpleNamespace(name="GUILD_POPUP_CANCEL")
        confirm = SimpleNamespace(name="GUILD_POPUP_CONFIRM")

        class Campaign:
            def __init__(self):
                self.config = SimpleNamespace()
                self.marker = object()

            def handle_guild_popup_confirm(self):
                if self.appear(cancel) and self.appear(confirm, interval=2):
                    self.device.click(confirm)
                    return True
                return False

        spec = branch_replay._ScenarioSpec(
            "guild-popup-confirm",
            "handle_guild_popup_confirm",
            ("GUILD_POPUP_CANCEL", "GUILD_POPUP_CONFIRM"),
            ("GUILD_POPUP_CANCEL", "GUILD_POPUP_CONFIRM"),
            ("GUILD_POPUP_CONFIRM",),
        )
        campaign = Campaign()
        source_dict = campaign.__dict__
        marker = campaign.marker

        with mock.patch.object(branch_replay, "_SCENARIOS", (spec,)), mock.patch.object(
            branch_replay, "_SOURCE_METHODS", {}
        ):
            result = replay_alas_combat_defensive_branches(campaign)

        self.assertTrue(result.passed)
        self.assertIs(campaign.__dict__, source_dict)
        self.assertIs(campaign.marker, marker)
        self.assertEqual(
            result.scenarios[0].virtual_actions, ("GUILD_POPUP_CONFIRM",)
        )

    def test_result_json_is_typed_and_read_only(self):
        scenario = AlasCombatBranchReplayScenario(
            name="unit",
            source_method="tests.Campaign.branch",
            returned=True,
            resource_queries=("PAUSE",),
            virtual_actions=(),
            virtual_sleeps=(),
            call_order=("query:PAUSE",),
        )
        value = alas_combat_branch_replay_to_json(
            AlasCombatBranchReplayResult(
                scenarios=(scenario,), source_restored=True
            )
        )

        self.assertEqual(value["schema"], ALAS_COMBAT_BRANCH_REPLAY_SCHEMA)
        self.assertTrue(value["passed"])
        self.assertFalse(value["input_injected"])

    def test_checked_in_real_alas_replay_covers_all_scenarios(self):
        root = Path(__file__).resolve().parents[1]
        value = json.loads(
            (
                root
                / "integration"
                / "alas"
                / "combat-defensive-branch-replay-g28.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(value["schema"], ALAS_COMBAT_BRANCH_REPLAY_SCHEMA)
        self.assertTrue(value["passed"])
        self.assertFalse(value["input_injected"])
        self.assertTrue(value["source_restored"])
        self.assertEqual(value["scenario_count"], 16)
        self.assertEqual(len(value["source_files_sha256"]), 4)
        self.assertEqual(
            tuple(item["name"] for item in value["scenarios"]),
            tuple(spec.name for spec in branch_replay._SCENARIOS),
        )
        verified = verify_alas_combat_branch_replay_record(value)
        self.assertTrue(verified["passed"])
        self.assertFalse(verified["live_mapping_promoted"])

        tampered = json.loads(json.dumps(value))
        tampered["scenarios"][0]["virtual_actions"] = []
        with self.assertRaisesRegex(SemanticGateClosed, "scenario changed"):
            verify_alas_combat_branch_replay_record(tampered)


if __name__ == "__main__":
    unittest.main()
