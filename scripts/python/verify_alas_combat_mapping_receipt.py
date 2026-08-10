"""Verify a versioned combat mapping receipt against its raw trace and manifest."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
    verify_alas_combat_mapping_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_alas_combat_observer_manifest(args.manifest)
    trace = load_alas_combat_observer_trace(args.trace, manifest)
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("cannot read mapping receipt") from exc
    result = verify_alas_combat_mapping_receipt(
        manifest,
        trace,
        receipt,
        source_trace_sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
