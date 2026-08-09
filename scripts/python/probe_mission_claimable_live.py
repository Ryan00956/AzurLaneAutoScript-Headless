#!/usr/bin/env python3
"""Capture a proven claimable TaskScene state without injecting a claim."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from alas_headless import AlasSemanticSession, MissionClaimableDetected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = {
        "schema": "alas-headless.mission-claimable-live/v1",
        "passed": False,
        "serial": args.serial,
        "package_fingerprint_verified": False,
        "claim_input_count": 0,
    }
    try:
        with AlasSemanticSession(
            serial=args.serial,
            driver_revision=args.driver_revision,
            adb=args.adb,
        ) as adapter:
            adapter.run_mission_reward(
                daily=True,
                weekly=True,
                timeout_seconds=args.timeout_seconds,
            )
    except MissionClaimableDetected as detected:
        result.update(
            {
                "passed": True,
                "package_fingerprint_verified": True,
                "disposition": detected.page.disposition.value,
                "page_generation": detected.page.generation,
                "entry": asdict(detected.entry),
                "exit": asdict(detected.exit_receipt),
                "claim_all": (
                    asdict(detected.page.claim_all)
                    if detected.page.claim_all is not None
                    else None
                ),
                "claim_rows": [
                    asdict(button) for button in detected.page.claim_rows
                ],
                "unfinished_rows": [
                    asdict(button) for button in detected.page.unfinished_rows
                ],
                "dismissed_overlays": list(detected.dismissed_overlays),
            }
        )

    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
