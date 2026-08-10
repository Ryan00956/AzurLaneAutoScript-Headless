"""Spend one reviewed semantic network-reconnect input and write its receipt."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    AlasSemanticSession,
    ObserverTransportError,
    alas_combat_active_blocker_names,
    alas_package_process_lease_from_trace,
    load_alas_combat_observer_trace,
    load_alas_combat_observer_manifest,
)


class _NamedButton:
    name = "POPUP_CONFIRM"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorize-once", action="store_true")
    parser.add_argument("--verified-trace", required=True, type=Path)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-command-timeout-seconds", type=int, default=10)
    parser.add_argument(
        "--allow-stalled-prompt-seconds",
        type=int,
        default=0,
        help="qualification-only stale NetworkDown lease; 0 keeps the 2.5s default",
    )
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
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def main() -> int:
    args = parse_args()
    if not args.authorize_once:
        raise SystemExit("--authorize-once is required")
    if args.output.exists():
        raise SystemExit("network reconnect output already exists")
    if not 1 <= args.adb_command_timeout_seconds <= 120:
        raise SystemExit("ADB command timeout must be in [1, 120]")
    if (
        args.allow_stalled_prompt_seconds != 0
        and not 3 <= args.allow_stalled_prompt_seconds <= 300
    ):
        raise SystemExit("stalled prompt lease must be 0 or in [3, 300] seconds")
    manifest = load_alas_combat_observer_manifest(args.manifest.resolve())
    verified_trace = load_alas_combat_observer_trace(
        args.verified_trace.resolve(), manifest
    )
    if args.allow_stalled_prompt_seconds:
        if len(verified_trace.samples) < 2:
            raise SystemExit("stalled prompt lease requires two read-only samples")
        recent = verified_trace.samples[-2:]
        if any(
            alas_combat_active_blocker_names(sample.snapshot, manifest)
            != ("network_down",)
            for sample in recent
        ):
            raise SystemExit(
                "stalled prompt lease requires two exact network_down-only samples"
            )
        captured = datetime.fromisoformat(
            verified_trace.samples[-1].captured_at_utc.replace("Z", "+00:00")
        )
        age_seconds = (datetime.now(timezone.utc) - captured).total_seconds()
        if age_seconds < 0 or age_seconds > args.allow_stalled_prompt_seconds:
            raise SystemExit("stalled prompt trace is outside its short lease")
    process_lease = alas_package_process_lease_from_trace(
        verified_trace, manifest
    )
    session = AlasSemanticSession(
        serial=args.serial,
        driver_revision=manifest.driver_revision,
        adb=args.adb,
        package=manifest.package,
        adb_command_timeout_seconds=args.adb_command_timeout_seconds,
        observer_max_age_ms=(
            args.allow_stalled_prompt_seconds * 1000
            if args.allow_stalled_prompt_seconds
            else 2500
        ),
        package_process_lease=process_lease,
    )
    button = _NamedButton()
    try:
        if not session.appear(button):
            raise SystemExit("reviewed network reconnect prompt is absent")
        receipt = session.click(button)
        value = {
            "schema": "alas-headless.g32-network-reconnect-commit/v1",
            "package": manifest.package,
            "driver_revision": manifest.driver_revision,
            "game_fingerprint": manifest.game_fingerprint,
            "pid": session.bridge.pid,
            "semantic_id": receipt.semantic_id,
            "generation": receipt.generation,
            "path": receipt.path,
            "point": {"x": receipt.point.x, "y": receipt.point.y},
            "bounds": {
                "left": receipt.bounds.left,
                "top": receipt.bounds.top,
                "right": receipt.bounds.right,
                "bottom": receipt.bounds.bottom,
            },
            "controlled_input_injected": True,
            "stalled_prompt_lease_seconds": args.allow_stalled_prompt_seconds,
            "outcome_verified": False,
        }
        write_json(args.output.resolve(), value)
    finally:
        try:
            session.close()
        except ObserverTransportError:
            pass
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
