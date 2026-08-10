"""Build and immediately reverify one G32 controlled-combat episode."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    analyze_alas_combat_controlled_episode,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
    verify_alas_combat_controlled_episode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--multiplex-evidence", required=True, type=Path)
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument(
        "--action-receipt", required=True, action="append", type=Path
    )
    parser.add_argument("--post-map-checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-control-frames", type=int, default=3)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    return parser.parse_args()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("controlled episode input cannot be read: " + str(path)) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    if args.output.exists():
        raise SystemExit("controlled episode output already exists")
    manifest = load_alas_combat_observer_manifest(args.manifest.resolve())
    trace_path = args.trace.resolve()
    trace = load_alas_combat_observer_trace(trace_path, manifest)
    trace_sha256 = sha256_file(trace_path)
    multiplex = load_json(args.multiplex_evidence.resolve())
    acquisition = load_json(args.acquisition.resolve())
    actions = tuple(load_json(path.resolve()) for path in args.action_receipt)
    checkpoint = load_json(args.post_map_checkpoint.resolve())
    record = analyze_alas_combat_controlled_episode(
        manifest,
        trace,
        multiplex,
        acquisition,
        actions,
        checkpoint,
        source_trace_sha256=trace_sha256,
        minimum_control_frames=args.minimum_control_frames,
    )
    verification = verify_alas_combat_controlled_episode(
        manifest,
        trace,
        multiplex,
        acquisition,
        actions,
        checkpoint,
        record,
        source_trace_sha256=trace_sha256,
    )
    write_json(args.output.resolve(), record)
    print(json.dumps(verification, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
