"""Spend one reviewed combat-resource action for live evidence acquisition."""

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    AlasSemanticSession,
    alas_combat_resource_action_commit_to_json,
    commit_alas_combat_resource_action_for_evidence,
    alas_package_process_lease_from_trace,
    load_alas_combat_observer_trace,
    load_alas_combat_observer_manifest,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--action-target")
    parser.add_argument("--expected-pid", required=True, type=int)
    parser.add_argument("--minimum-generation", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorize-once", action="store_true")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-command-timeout-seconds", type=int, default=10)
    parser.add_argument("--verified-trace", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    return parser.parse_args()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def main():
    args = parse_args()
    if not args.authorize_once:
        raise SystemExit("--authorize-once is required")
    manifest = load_alas_combat_observer_manifest(args.manifest)
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
        commit = commit_alas_combat_resource_action_for_evidence(
            session,
            manifest,
            args.resource,
            action_name=args.action_target,
            expected_pid=args.expected_pid,
            minimum_generation=args.minimum_generation,
            action_budget=1,
        )
    finally:
        session.close()
    value = alas_combat_resource_action_commit_to_json(commit)
    write_json(args.output, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
