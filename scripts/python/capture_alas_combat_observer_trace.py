"""Record a package-verified, input-free raw combat observer trace."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    AlasSemanticSession,
    ObserverTransportError,
    PINNED_CN_GAME_FINGERPRINT,
    SemanticGateClosed,
    build_alas_combat_observer_trace,
    build_alas_combat_trace_frame,
    alas_package_process_lease_from_trace,
    load_alas_combat_observer_trace,
    load_alas_combat_observer_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument("--duration-seconds", type=float, default=90.0)
    parser.add_argument("--interval-seconds", type=float, default=0.20)
    parser.add_argument("--max-samples", type=int, default=480)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-command-timeout-seconds", type=int, default=10)
    parser.add_argument("--verified-trace", type=Path)
    return parser.parse_args()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def write_trace(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            # Windows readers can briefly hold the destination across the
            # atomic replace.  Keep the capture fail-closed but tolerate the
            # bounded sharing violation instead of losing the live trace.
            time.sleep(0.025)


def main() -> int:
    args = parse_args()
    if not 0.0 < args.duration_seconds <= 900.0:
        raise SystemExit("duration must be in (0, 900]")
    if not 0.02 <= args.interval_seconds <= 10.0:
        raise SystemExit("interval must be in [0.02, 10]")
    if not 1 <= args.max_samples <= 5000:
        raise SystemExit("max samples must be in [1, 5000]")
    if not 1 <= args.adb_command_timeout_seconds <= 120:
        raise SystemExit("ADB command timeout must be in [1, 120]")
    manifest = load_alas_combat_observer_manifest(args.manifest)
    process_lease = None
    if args.verified_trace is not None:
        verified_trace = load_alas_combat_observer_trace(
            args.verified_trace.resolve(), manifest
        )
        process_lease = alas_package_process_lease_from_trace(
            verified_trace, manifest
        )
    game = PINNED_CN_GAME_FINGERPRINT
    expected_game_fingerprint = ":".join(
        (
            game.version_name,
            str(game.version_code),
            game.primary_abi,
            game.base_apk_sha256,
            game.il2cpp_sha256,
        )
    )
    if manifest.game_fingerprint != expected_game_fingerprint:
        raise SystemExit("manifest game fingerprint is not the pinned package")
    session = AlasSemanticSession(
        serial=args.serial,
        driver_revision=manifest.driver_revision,
        adb=args.adb,
        package=manifest.package,
        adb_command_timeout_seconds=args.adb_command_timeout_seconds,
        package_process_lease=process_lease,
    )
    samples = []
    rejected = 0
    rejection_reasons = {}
    duplicates = 0
    last_generation = -1
    try:
        session.open()  # includes the independent pinned package fingerprint gate
        deadline = time.monotonic() + args.duration_seconds
        while time.monotonic() < deadline and len(samples) < args.max_samples:
            started = time.monotonic()
            try:
                if session.bridge.foreground_component() != session.component:
                    raise SemanticGateClosed("game activity is not top-resumed")
                snapshot = session.bridge.request("GET /v1/snapshot\n")
                buttons = session.bridge.request("GET /v1/buttons\n")
                ui = session.bridge.request("GET /v1/ui\n")
                frame, typed = build_alas_combat_trace_frame(
                    snapshot, buttons, ui, manifest
                )
                if typed.generation <= last_generation:
                    duplicates += 1
                else:
                    samples.append((utc_now(), frame))
                    last_generation = typed.generation
                    trace = build_alas_combat_observer_trace(manifest, samples)
                    write_trace(args.output, trace)
            except (SemanticGateClosed, ObserverTransportError) as exc:
                rejected += 1
                reason = str(exc)
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            remaining = args.interval_seconds - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        try:
            session.close()
        except ObserverTransportError as exc:
            rejected += 1
            reason = "observer close failed: " + str(exc)
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    if not samples:
        raise SystemExit(
            "no coherent combat observer samples were captured: "
            + json.dumps(rejection_reasons, ensure_ascii=False, sort_keys=True)
        )
    trace = build_alas_combat_observer_trace(manifest, samples)
    generations = [
        max(
            sample[1]["buttons"]["generation"],
            sample[1]["ui"]["generation"],
        )
        for sample in samples
    ]
    print(
        json.dumps(
            {
                "schema": "alas-headless.g21-combat-trace-capture-result/v1",
                "passed": True,
                "output": str(args.output.resolve()),
                "pid": trace["pid"],
                "sample_count": len(samples),
                "first_generation": generations[0],
                "last_generation": generations[-1],
                "rejected_endpoint_triples": rejected,
                "rejection_reasons": rejection_reasons,
                "duplicate_generations": duplicates,
                "input_injected": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
