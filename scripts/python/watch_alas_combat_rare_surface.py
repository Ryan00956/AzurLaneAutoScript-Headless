"""Watch one rare combat surface without injecting Android input."""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    ALAS_COMBAT_RARE_SURFACE_PROFILES,
    ALAS_COMBAT_RESULT_SURFACE_PROFILES,
    AlasSemanticSession,
    ObserverTransportError,
    PINNED_CN_GAME_FINGERPRINT,
    SemanticGateClosed,
    alas_combat_surface_multiplex_candidate_present,
    analyze_alas_combat_rare_surface_evidence,
    analyze_alas_combat_result_surface_evidence,
    analyze_alas_combat_surface_multiplex_evidence,
    build_alas_combat_observer_trace,
    build_alas_combat_trace_frame,
    load_alas_combat_observer_manifest,
    parse_alas_combat_observer_trace,
    verify_alas_combat_rare_surface_evidence,
    verify_alas_combat_result_surface_evidence,
    verify_alas_combat_surface_multiplex_evidence,
    alas_package_process_lease_from_trace,
    load_alas_combat_observer_trace,
)


DIALOG_PROFILE_IDS = tuple(
    profile.profile_id for profile in ALAS_COMBAT_RARE_SURFACE_PROFILES
)
RESULT_PROFILE_IDS = tuple(
    profile.profile_id for profile in ALAS_COMBAT_RESULT_SURFACE_PROFILES
)
PROFILE_IDS = DIALOG_PROFILE_IDS + RESULT_PROFILE_IDS + ("all",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--profile", required=True, choices=PROFILE_IDS)
    parser.add_argument("--trace-output", required=True, type=Path)
    parser.add_argument("--evidence-output", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument("--duration-seconds", type=float, default=90.0)
    parser.add_argument("--interval-seconds", type=float, default=0.10)
    parser.add_argument("--max-samples", type=int, default=900)
    parser.add_argument("--minimum-consecutive-frames", type=int, default=3)
    parser.add_argument("--context-frames", type=int, default=2)
    parser.add_argument("--post-match-samples", type=int, default=2)
    parser.add_argument(
        "--continue-after-match",
        action="store_true",
        help="keep the read-only trace running after the first matched surface",
    )
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


def encode_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.025)


def validate_args(args: argparse.Namespace) -> None:
    if not 0.0 < args.duration_seconds <= 900.0:
        raise SystemExit("duration must be in (0, 900]")
    if not 0.02 <= args.interval_seconds <= 10.0:
        raise SystemExit("interval must be in [0.02, 10]")
    if not 3 <= args.minimum_consecutive_frames <= 20:
        raise SystemExit("minimum consecutive frames must be in [3, 20]")
    if not 0 <= args.context_frames <= 10:
        raise SystemExit("context frames must be in [0, 10]")
    if not 0 <= args.post_match_samples <= 20:
        raise SystemExit("post-match samples must be in [0, 20]")
    if not 3 <= args.max_samples <= 5000:
        raise SystemExit("max samples must be in [3, 5000]")
    if not 1 <= args.adb_command_timeout_seconds <= 120:
        raise SystemExit("ADB command timeout must be in [1, 120]")


def main() -> int:
    args = parse_args()
    validate_args(args)
    if args.profile == "all":
        verifier = verify_alas_combat_surface_multiplex_evidence
    else:
        verifier = (
            verify_alas_combat_result_surface_evidence
            if args.profile in RESULT_PROFILE_IDS
            else verify_alas_combat_rare_surface_evidence
        )
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
    fingerprint = ":".join(
        (
            game.version_name,
            str(game.version_code),
            game.primary_abi,
            game.base_apk_sha256,
            game.il2cpp_sha256,
        )
    )
    if manifest.game_fingerprint != fingerprint:
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
    matched_at_sample_count = None
    final_record = None
    final_digest = None
    try:
        session.open()
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
                    trace_json = build_alas_combat_observer_trace(manifest, samples)
                    trace_payload = encode_json(trace_json)
                    final_digest = hashlib.sha256(trace_payload).hexdigest()
                    write_bytes(args.trace_output, trace_payload)
                    trace = parse_alas_combat_observer_trace(trace_json, manifest)
                    should_analyze = args.profile != "all" or (
                        len(samples) >= args.minimum_consecutive_frames
                        and (
                            final_record is None
                            or alas_combat_surface_multiplex_candidate_present(typed)
                        )
                    )
                    if should_analyze:
                        if args.profile == "all":
                            final_record = analyze_alas_combat_surface_multiplex_evidence(
                                manifest,
                                trace,
                                source_trace_sha256=final_digest,
                                minimum_consecutive_frames=(
                                    args.minimum_consecutive_frames
                                ),
                                context_frames=args.context_frames,
                            )
                        else:
                            analyzer = (
                                analyze_alas_combat_result_surface_evidence
                                if args.profile in RESULT_PROFILE_IDS
                                else analyze_alas_combat_rare_surface_evidence
                            )
                            final_record = analyzer(
                                manifest,
                                trace,
                                profile_id=args.profile,
                                source_trace_sha256=final_digest,
                                minimum_consecutive_frames=(
                                    args.minimum_consecutive_frames
                                ),
                                context_frames=args.context_frames,
                            )
                        write_bytes(
                            args.evidence_output, encode_json(final_record)
                        )
                    candidate_complete = (
                        final_record is not None
                        and (
                            final_record["candidate_complete"]
                            if args.profile == "all"
                            else final_record["evidence_complete"]
                        )
                    )
                    if candidate_complete:
                        if matched_at_sample_count is None:
                            matched_at_sample_count = len(samples)
                        if (
                            not args.continue_after_match
                            and len(samples) - matched_at_sample_count
                            >= args.post_match_samples
                        ):
                            break
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

    if not samples or final_digest is None:
        raise SystemExit(
            "no coherent rare-surface samples were captured: "
            + json.dumps(rejection_reasons, ensure_ascii=False, sort_keys=True)
        )
    trace = parse_alas_combat_observer_trace(
        build_alas_combat_observer_trace(manifest, samples), manifest
    )
    if args.profile == "all":
        final_record = analyze_alas_combat_surface_multiplex_evidence(
            manifest,
            trace,
            source_trace_sha256=final_digest,
            minimum_consecutive_frames=args.minimum_consecutive_frames,
            context_frames=args.context_frames,
        )
        write_bytes(args.evidence_output, encode_json(final_record))
    if final_record is None:
        raise SystemExit("rare-surface evidence analysis did not complete")
    verification = verifier(
        manifest,
        trace,
        final_record,
        source_trace_sha256=final_digest,
    )
    print(
        json.dumps(
            {
                "schema": (
                    "alas-headless.g31-combat-surface-multiplex-watch-result/v1"
                    if args.profile == "all"
                    else (
                        "alas-headless.g30-combat-surface-watch-result/v2"
                        if args.profile in RESULT_PROFILE_IDS
                        else "alas-headless.g29-combat-rare-surface-watch-result/v1"
                    )
                ),
                "passed": True,
                "profile_id": args.profile,
                "evidence_complete": verification["evidence_complete"],
                "candidate_complete": (
                    verification.get("candidate_complete")
                    if args.profile == "all"
                    else verification["evidence_complete"]
                ),
                "matched_profile_ids": (
                    verification.get("matched_profile_ids", [])
                ),
                "ambiguous_match": verification.get("ambiguous_match", False),
                "sample_count": len(samples),
                "first_generation": trace.generations[0],
                "last_generation": trace.generations[-1],
                "selected_generations": final_record["selected_generations"],
                "ambiguous_generations": final_record["ambiguous_generations"],
                "rejected_endpoint_triples": rejected,
                "rejection_reasons": rejection_reasons,
                "duplicate_generations": duplicates,
                "trace_sha256": final_digest,
                "input_injected": False,
                "auto_promoted": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
