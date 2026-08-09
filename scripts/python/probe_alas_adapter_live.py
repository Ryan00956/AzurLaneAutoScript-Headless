#!/usr/bin/env python3
"""Read-only live smoke for the pinned ALAS resource-name adapter."""

import argparse
import json
from pathlib import Path

from alas_headless import (
    AlasSemanticSession,
    AlasSemanticUnmapped,
    DEFAULT_ALAS_BUTTON_TARGETS,
    SemanticGateClosed,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--output")
    args = parser.parse_args()

    session = AlasSemanticSession(
        serial=args.serial,
        driver_revision=args.driver_revision,
        adb=args.adb,
    )
    try:
        adapter = session.open()
        aliases = {}
        for alas_name, expected_semantic_id in DEFAULT_ALAS_BUTTON_TARGETS.items():
            semantic_id = adapter.semantic_id_for(alas_name)
            if semantic_id != expected_semantic_id:
                raise SemanticGateClosed("ALAS alias resolved to an unexpected target")
            if not adapter.appear(alas_name):
                raise SemanticGateClosed(
                    "mapped ALAS resource is not safely visible: {0}".format(alas_name)
                )
            aliases[alas_name] = semantic_id

        unmapped_failed_closed = False
        try:
            adapter.semantic_id_for("BACK_ARROW")
        except AlasSemanticUnmapped:
            unmapped_failed_closed = True
        if not unmapped_failed_closed:
            raise SemanticGateClosed("generic BACK_ARROW unexpectedly resolved")

        raw_input_failed_closed = False
        try:
            adapter.reject_raw_input("live-smoke")
        except SemanticGateClosed:
            raw_input_failed_closed = True
        if not raw_input_failed_closed:
            raise SemanticGateClosed("raw input guard unexpectedly opened")

        state = adapter.oracle.read_state()
        result = {
            "schema": "alas-headless.alas-adapter-live-smoke/v1",
            "passed": True,
            "serial": args.serial,
            "package": session.package,
            "pid": session.bridge.pid,
            "driver_revision": args.driver_revision,
            "generation": state.generation,
            "scene_handle": state.scene_handle,
            "button_count": len(state.buttons),
            "alias_count": len(aliases),
            "aliases": aliases,
            "package_fingerprint_verified": True,
            "raycast_top_required": True,
            "unmapped_failed_closed": unmapped_failed_closed,
            "raw_input_failed_closed": raw_input_failed_closed,
            "input_injected": False,
        }
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text, end="")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
