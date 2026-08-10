"""Report the fail-closed G20 live-combat mapping coverage baseline."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    ALAS_COMBAT_ACTION_TARGET_NAMES,
    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES,
    ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES,
    ALAS_COMBAT_REPLAY_RESOURCE_NAMES,
    audit_alas_combat_observer_manifest,
    load_alas_combat_observer_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return non-zero while any real combat mapping remains open",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_alas_combat_observer_manifest(args.manifest)
    coverage = audit_alas_combat_observer_manifest(manifest)
    print(
        json.dumps(
            {
                "schema": "alas-headless.g26-combat-observer-coverage/v2",
                "contract_valid": (
                    coverage.total_resources
                    == len(ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES)
                    and coverage.total_actions
                    == len(ALAS_COMBAT_ACTION_TARGET_NAMES)
                ),
                "production_ready": coverage.production_ready,
                "canonical_qualified_resources": (
                    coverage.canonical_qualified_resources
                ),
                "canonical_resources": coverage.canonical_resources,
                "qualified_resources": coverage.qualified_resources,
                "total_resources": coverage.total_resources,
                "unqualified_resources": coverage.unqualified_resources,
                "qualified_actions": coverage.qualified_actions,
                "total_actions": coverage.total_actions,
                "unqualified_actions": coverage.unqualified_actions,
                "branch_review_complete": coverage.branch_review_complete,
                "qualified_blockers": coverage.qualified_blockers,
                "total_blockers": coverage.total_blockers,
                "blocker_review_complete": coverage.blocker_review_complete,
                "blockers_qualified": coverage.blockers_qualified,
                "fleet_stats_qualified": coverage.fleet_stats_qualified,
                "phase_positive_resources": {
                    phase.value: resources
                    for phase, resources in ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES.items()
                },
                "canonical_resource_surface_exact": tuple(
                    sorted(ALAS_COMBAT_REPLAY_RESOURCE_NAMES)
                ),
                "defensive_resource_surface_exact": (
                    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES
                ),
                "action_target_surface_exact": ALAS_COMBAT_ACTION_TARGET_NAMES,
                "input_injected": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if args.require_ready and not coverage.production_ready:
        return 1
    return (
        0
        if coverage.total_resources == len(ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES)
        and coverage.total_actions == len(ALAS_COMBAT_ACTION_TARGET_NAMES)
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
