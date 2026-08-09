"""Capture a read-only, package-pinned semantic UI observer snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from alas_headless import (
    AdbObserverBridge,
    OracleFingerprint,
    PINNED_CN_GAME_FINGERPRINT,
    SemanticOracle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--angle-apk", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("evidence"))
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument(
        "--component",
        default="com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if not args.angle_apk.is_file():
        raise SystemExit("ANGLE APK does not exist: {0}".format(args.angle_apk))
    revision = Path("ANGLE_REVISION").read_text(encoding="utf-8").strip()
    captured_at = datetime.now(timezone.utc)
    safe_serial = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in args.serial
    )
    output = args.output_root / (
        "g6-semantic-ui-{0}-{1}".format(
            captured_at.strftime("%Y%m%dT%H%M%SZ"), safe_serial
        )
    )
    output.mkdir(parents=True, exist_ok=False)

    with AdbObserverBridge(args.serial, args.package) as bridge:
        installed = bridge.require_package_fingerprint(PINNED_CN_GAME_FINGERPRINT)
        oracle = SemanticOracle(
            bridge.request,
            bridge.foreground_component,
            bridge.tap,
            OracleFingerprint(
                package=args.package,
                component=args.component,
                driver_revision=revision,
                expected_pid=bridge.pid,
            ),
        )
        button_state = oracle.read_state()
        ui_state = oracle.read_ui_state()
        snapshot = bridge.request("GET /v1/snapshot\n")
        buttons = bridge.request("GET /v1/buttons\n")
        ui = bridge.request("GET /v1/ui\n")

        write_json(output / "snapshot.json", snapshot)
        write_json(output / "buttons.json", buttons)
        write_json(output / "ui.json", ui)
        write_json(
            output / "manifest.json",
            {
                "schema": "alas-headless.g6-semantic-ui/v1",
                "captured_at_utc": captured_at.isoformat(),
                "serial": args.serial,
                "package": args.package,
                "component": args.component,
                "pid": bridge.pid,
                "driver_revision": revision,
                "angle_apk_sha256": sha256(args.angle_apk),
                "installed_fingerprint": installed.__dict__,
                "button_generation": button_state.generation,
                "ui_generation": ui_state.generation,
                "ui_method_mask": ui_state.method_mask,
                "ui_skipped_count": ui_state.skipped_count,
                "button_count": len(button_state.buttons),
                "toggle_count": len(ui_state.toggles),
                "text_count": len(ui_state.texts),
                "image_count": len(ui_state.images),
                "image_truncated": ui_state.image_truncated,
                "passed": True,
                "input_injected": False,
            },
        )
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
