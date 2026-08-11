import unittest
from dataclasses import replace
from types import SimpleNamespace

from alas_headless import (
    Bounds,
    CampaignMapCellState,
    CampaignMapState,
    Point,
    SemanticGateClosed,
    build_alas_campaign_camera_view,
    install_alas_campaign_camera_view,
)


def make_state(*, generation=10, dx=0.0, dy=0.0, deform=False):
    cells = []
    for row in range(1, 6):
        for column in range(1, 6):
            x = 100.0 * (column - 0.5) + 100.0 + dx
            y = 80.0 * (row - 0.5) + 100.0 + dy
            if deform and row == 2 and column == 4:
                x += 30.0
                y -= 25.0
            cells.append(
                CampaignMapCellState(
                    row=row,
                    column=column,
                    node=chr(ord("A") + column - 1) + str(row),
                    button_path=(
                        "root/quads/chapter_cell_quad_{0}_{1}".format(
                            row, column
                        )
                    ),
                    point=Point(x, y),
                    bounds=Bounds(x - 40, y - 30, x + 40, y + 30),
                )
            )
    return CampaignMapState(
        generation=generation,
        stage_code="12-4",
        rows=5,
        columns=5,
        cells=tuple(cells),
        land_nodes=("A1",),
        fleets=(),
        enemies=(),
        pickups=(),
        displayed_fleet_index=1,
        current_fleet_marker="fleet",
        current_fleet_roster_sprites=("ship",),
    )


class AlasCampaignCameraViewTests(unittest.TestCase):
    def test_builds_exact_internal_camera_view_and_target_grid(self):
        state = make_state()
        view = build_alas_campaign_camera_view(
            state,
            screen_center=(350.0, 300.0),
            target_node="C3",
        )
        observation = view.semantic_observation

        self.assertEqual(observation.camera_location, (2, 2))
        self.assertEqual(observation.camera_node, "C3")
        self.assertAlmostEqual(observation.center_offset[0], 0.5)
        self.assertAlmostEqual(observation.center_offset[1], 0.5)
        self.assertEqual(observation.target_local_location, (2, 2))
        self.assertEqual(view[(2, 2)].semantic_path, observation.target_path)
        self.assertEqual(tuple(view.swipe_base), (100.0, 80.0))
        self.assertLess(observation.projective_maximum_residual, 1e-8)

    def test_predict_swipe_uses_observed_camera_delta(self):
        before = build_alas_campaign_camera_view(
            make_state(generation=10),
            screen_center=(350.0, 300.0),
        )
        # Moving rendered cells left by one column and down by one row moves
        # the camera coordinate right one and up one.
        after = build_alas_campaign_camera_view(
            make_state(generation=12, dx=-100.0, dy=80.0),
            screen_center=(350.0, 300.0),
        )

        self.assertEqual(before.predict_swipe(after), (1, -1))

    def test_rejects_incoherent_projection_and_unqualified_edge(self):
        with self.assertRaisesRegex(SemanticGateClosed, "incoherent"):
            build_alas_campaign_camera_view(
                make_state(deform=True),
                screen_center=(350.0, 300.0),
            )
        with self.assertRaisesRegex(SemanticGateClosed, "edge"):
            build_alas_campaign_camera_view(
                make_state(),
                screen_center=(160.0, 145.0),
            )

    def test_install_replaces_only_campaign_view_input(self):
        campaign = SimpleNamespace(
            config=SimpleNamespace(SCREEN_CENTER=(350.0, 300.0))
        )
        state = make_state()

        observation = install_alas_campaign_camera_view(
            campaign, state, target_node="C3"
        )

        self.assertIs(campaign.view.semantic_state, state)
        self.assertIs(campaign.semantic_camera_view_observation, observation)
        self.assertEqual(observation.target_node, "C3")

    def test_predict_swipe_rejects_logical_map_drift(self):
        before = build_alas_campaign_camera_view(
            make_state(generation=10), screen_center=(350.0, 300.0)
        )
        changed = replace(
            make_state(generation=12, dx=-100.0), stage_code="12-3"
        )
        after = build_alas_campaign_camera_view(
            changed, screen_center=(350.0, 300.0)
        )

        with self.assertRaisesRegex(SemanticGateClosed, "changed map"):
            before.predict_swipe(after)


if __name__ == "__main__":
    unittest.main()
