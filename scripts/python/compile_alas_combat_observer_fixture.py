"""Select a bounded trace sequence, report candidates, and compile a fixture."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    analyze_alas_combat_observer_candidates,
    alas_combat_replay_phase_sequence,
    compile_alas_combat_observer_fixture,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
    merge_alas_combat_observer_traces,
    select_alas_combat_observer_trace_samples,
)


PINNED_ALAS_SHA = "81ccf63b4540f00241628c82a58c02c7a2bb11af"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path, action="append")
    parser.add_argument("--generations", required=True)
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidates-output", type=Path)
    parser.add_argument("--include-automation-confirm", action="store_true")
    parser.add_argument("--include-get-items", action="store_true")
    parser.add_argument("--include-get-mission", action="store_true")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    return parser.parse_args()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    args.trace = [path.resolve() for path in args.trace]
    args.alas_root = args.alas_root.resolve()
    args.output = args.output.resolve()
    args.manifest = args.manifest.resolve()
    if args.candidates_output is not None:
        args.candidates_output = args.candidates_output.resolve()
    try:
        generations = tuple(int(item) for item in args.generations.split(","))
    except ValueError as exc:
        raise SystemExit("generations must be comma-separated integers") from exc
    phase_sequence = alas_combat_replay_phase_sequence(
        include_automation_confirm=args.include_automation_confirm,
        include_get_items=args.include_get_items,
        include_get_mission=args.include_get_mission,
    )
    if len(generations) != len(phase_sequence):
        raise SystemExit(
            "generation count does not match the selected combat phase sequence"
        )
    manifest = load_alas_combat_observer_manifest(args.manifest)
    trace = merge_alas_combat_observer_traces(
        tuple(load_alas_combat_observer_trace(path, manifest) for path in args.trace)
    )
    selected = select_alas_combat_observer_trace_samples(trace, generations)
    candidates = analyze_alas_combat_observer_candidates(
        selected, phase_sequence=phase_sequence
    )
    candidates_output = args.candidates_output or args.output.with_suffix(
        ".candidates.json"
    )
    write_json(candidates_output, candidates)

    alas_root = args.alas_root
    completed = subprocess.run(
        ["git", "-C", str(alas_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout.strip() != PINNED_ALAS_SHA:
        raise SystemExit("ALAS checkout is not at the pinned revision")
    campaign_file = alas_root / "campaign" / "campaign_main" / "campaign_12_4.py"
    if not campaign_file.is_file():
        raise SystemExit("pinned campaign_12_4.py is missing")
    sys.path.insert(0, str(alas_root))
    os.chdir(alas_root)
    from campaign.campaign_main.campaign_12_4 import MAP

    land = tuple(tuple(int(value) for value in grid.location) for grid in MAP if grid.is_land)
    fixture = compile_alas_combat_observer_fixture(
        selected,
        manifest,
        stage_code="12-4",
        columns=11,
        rows=8,
        land_cells=land,
        expected_fleet_count=2,
        phase_sequence=phase_sequence,
    )
    write_json(args.output, fixture)
    print(
        json.dumps(
            {
                "schema": "alas-headless.g21-combat-fixture-compile-result/v1",
                "passed": True,
                "traces": [str(path.resolve()) for path in args.trace],
                "fixture": str(args.output.resolve()),
                "candidates": str(candidates_output.resolve()),
                "generations": generations,
                "phases": [phase.value for phase in phase_sequence],
                "land_cells": len(land),
                "input_injected": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
