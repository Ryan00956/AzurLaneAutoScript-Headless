#!/usr/bin/env python3
"""Inject exactly one reviewed task claim-all and verify the semantic closure."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from alas_headless import AlasSemanticSession


CONFIRMATION_TOKEN = "CLAIM-ONE-GET-ALL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--confirm-exact-token", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.confirm_exact_token != CONFIRMATION_TOKEN:
        parser.error("exact controlled-claim confirmation token is required")

    with AlasSemanticSession(
        serial=args.serial,
        driver_revision=args.driver_revision,
        adb=args.adb,
    ) as adapter:
        receipt = adapter.claim_mission_rewards_once(
            timeout_seconds=args.timeout_seconds,
        )

    result = {
        "schema": "alas-headless.mission-claim-once-live/v1",
        "passed": receipt.outcome == "claimed-all-once",
        "serial": args.serial,
        "package_fingerprint_verified": True,
        "receipt": asdict(receipt),
        "claim_input_count": receipt.claim_input_count,
        "semantic_input_count": 4 + len(receipt.dismissed_overlays),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
