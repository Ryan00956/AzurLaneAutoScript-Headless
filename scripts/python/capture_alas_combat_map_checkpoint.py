"""Capture one read-only semantic map checkpoint after a controlled battle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    ALAS_COMBAT_ACQUISITION_SCHEMA,
    AlasSemanticSession,
    alas_package_process_lease_from_trace,
    alas_campaign_land_nodes_to_cells,
    build_alas_combat_map_checkpoint,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-command-timeout-seconds", type=int, default=10)
    parser.add_argument("--verified-trace", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    return parser.parse_args()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("checkpoint input cannot be read") from exc


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def main() -> int:
    args = parse_args()
    args.acquisition = args.acquisition.resolve()
    args.output = args.output.resolve()
    if args.output.exists():
        raise SystemExit("checkpoint output already exists")
    acquisition = load_json(args.acquisition)
    if (
        not isinstance(acquisition, dict)
        or acquisition.get("schema") != ALAS_COMBAT_ACQUISITION_SCHEMA
        or acquisition.get("controlled_input_injected") is not True
    ):
        raise SystemExit("checkpoint requires one G32 controlled acquisition")
    before = acquisition.get("map_before")
    if not isinstance(before, dict):
        raise SystemExit("controlled acquisition has no pre-combat map")
    try:
        stage_code = before["stage_code"]
        columns = before["columns"]
        rows = before["rows"]
        expected_fleet_count = before["expected_fleet_count"]
        land_cells = alas_campaign_land_nodes_to_cells(
            before["land_nodes"], columns=columns, rows=rows
        )
    except (KeyError, TypeError) as exc:
        raise SystemExit("controlled acquisition map contract is incomplete") from exc

    manifest = load_alas_combat_observer_manifest(args.manifest.resolve())
    process_lease = None
    if args.verified_trace is not None:
        verified_trace = load_alas_combat_observer_trace(
            args.verified_trace.resolve(), manifest
        )
        process_lease = alas_package_process_lease_from_trace(
            verified_trace, manifest
        )
    session = AlasSemanticSession(
        serial=args.serial,
        driver_revision=manifest.driver_revision,
        adb=args.adb,
        package=manifest.package,
        adb_command_timeout_seconds=args.adb_command_timeout_seconds,
        package_process_lease=process_lease,
    )
    try:
        session.open()
        if session.bridge.pid != acquisition.get("pid"):
            raise SystemExit("game PID changed after controlled combat")
        session.begin_campaign_pre_sortie(stage_code, mode="normal")
        try:
            state = session.campaign_map_state(
                columns=columns,
                rows=rows,
                land_cells=land_cells,
                expected_fleet_count=expected_fleet_count,
            )
        finally:
            session.end_campaign_pre_sortie()
        value = build_alas_combat_map_checkpoint(
            manifest, pid=session.bridge.pid, state=state
        )
    finally:
        session.close()
    write_json(args.output, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
