"""Build or verify a non-applying G29 rare-surface evidence record."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    ALAS_COMBAT_RARE_SURFACE_PROFILES,
    ALAS_COMBAT_RESULT_SURFACE_PROFILES,
    analyze_alas_combat_rare_surface_evidence,
    analyze_alas_combat_result_surface_evidence,
    analyze_alas_combat_surface_multiplex_evidence,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
    verify_alas_combat_rare_surface_evidence,
    verify_alas_combat_result_surface_evidence,
    verify_alas_combat_surface_multiplex_evidence,
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
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--profile", required=True, choices=PROFILE_IDS)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument("--minimum-consecutive-frames", type=int, default=3)
    parser.add_argument("--context-frames", type=int, default=2)
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    manifest = load_alas_combat_observer_manifest(args.manifest)
    trace = load_alas_combat_observer_trace(args.trace, manifest)
    digest = hashlib.sha256(args.trace.read_bytes()).hexdigest()
    if args.verify:
        record = json.loads(args.output.read_text(encoding="utf-8"))
        identity = record.get("mode") if isinstance(record, dict) else None
        if args.profile != "all":
            identity = record.get("profile_id") if isinstance(record, dict) else None
        if identity != args.profile:
            raise SystemExit("evidence profile does not match --profile")
    else:
        if args.profile == "all":
            record = analyze_alas_combat_surface_multiplex_evidence(
                manifest,
                trace,
                source_trace_sha256=digest,
                minimum_consecutive_frames=args.minimum_consecutive_frames,
                context_frames=args.context_frames,
            )
        else:
            analyzer = (
                analyze_alas_combat_result_surface_evidence
                if args.profile in RESULT_PROFILE_IDS
                else analyze_alas_combat_rare_surface_evidence
            )
            record = analyzer(
                manifest,
                trace,
                profile_id=args.profile,
                source_trace_sha256=digest,
                minimum_consecutive_frames=args.minimum_consecutive_frames,
                context_frames=args.context_frames,
            )
        write_json(args.output, record)
    if args.profile == "all":
        verifier = verify_alas_combat_surface_multiplex_evidence
    else:
        verifier = (
            verify_alas_combat_result_surface_evidence
            if args.profile in RESULT_PROFILE_IDS
            else verify_alas_combat_rare_surface_evidence
        )
    result = verifier(
        manifest,
        trace,
        record,
        source_trace_sha256=digest,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
