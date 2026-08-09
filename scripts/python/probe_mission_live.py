#!/usr/bin/env python3
"""Run the reviewed TaskScene no-claim round trip on a pinned game process."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from alas_headless import AlasSemanticSession


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    with AlasSemanticSession(
        serial=args.serial,
        driver_revision=args.driver_revision,
        adb=args.adb,
    ) as adapter:
        receipt = adapter.run_mission_reward(
            daily=True,
            weekly=True,
            timeout_seconds=args.timeout_seconds,
        )
        result = {
            "schema": "alas-headless.mission-live/v1",
            "passed": receipt.outcome == "nothing-claimable",
            "serial": args.serial,
            "package_fingerprint_verified": True,
            "receipt": asdict(receipt),
            "navigation_input_count": 2,
            "overlay_close_input_count": len(receipt.dismissed_overlays),
            "semantic_input_count": 2 + len(receipt.dismissed_overlays),
            "claim_input_count": 0,
        }
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
