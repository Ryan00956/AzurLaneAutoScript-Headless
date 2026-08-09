#!/usr/bin/env python3
"""Read-only live smoke test for the controller-side SemanticOracle."""

import argparse
import json
from pathlib import Path

from alas_headless import (
    AdbObserverBridge,
    DEFAULT_BLOCKERS,
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
)


TARGETS = (
    "main/battle",
    "main/formation",
    "main/settings",
    "main/mail",
    "main/shop",
    "main/dock",
    "main/task",
    "main/build",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument(
        "--component",
        default="com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--output")
    args = parser.parse_args()

    with AdbObserverBridge(args.serial, args.package, adb=args.adb) as bridge:
        oracle = SemanticOracle(
            bridge.request,
            bridge.foreground_component,
            bridge.tap,
            OracleFingerprint(
                package=args.package,
                component=args.component,
                driver_revision=args.driver_revision,
                expected_pid=bridge.pid,
            ),
        )
        state = oracle.read_state()
        present_blockers = [
            rule.blocker_id
            for rule in DEFAULT_BLOCKERS
            if any(rule.path_fragment in button.path for button in state.buttons)
        ]
        if present_blockers:
            raise SemanticGateClosed(
                "live smoke requires an unobstructed main UI: {0}".format(
                    ", ".join(present_blockers)
                )
            )

        targets = {}
        for semantic_id in TARGETS:
            if not oracle.enabled(semantic_id):
                raise SemanticGateClosed(
                    "required main target is not enabled: {0}".format(semantic_id)
                )
            bounds = oracle.bounds(semantic_id)
            targets[semantic_id] = {
                "left": bounds.left,
                "top": bounds.top,
                "right": bounds.right,
                "bottom": bounds.bottom,
            }

        result = {
            "schema": "alas-headless.oracle-live-smoke/v1",
            "passed": True,
            "serial": args.serial,
            "package": args.package,
            "pid": bridge.pid,
            "generation": state.generation,
            "scene_handle": state.scene_handle,
            "button_count": len(state.buttons),
            "blockers": present_blockers,
            "targets": targets,
            "input_injected": False,
        }
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
