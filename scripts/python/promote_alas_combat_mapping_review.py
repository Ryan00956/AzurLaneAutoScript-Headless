"""Promote exact reviewed trace records into a candidate combat manifest."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    alas_combat_observer_manifest_to_json,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
    promote_alas_combat_mapping_review,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    return parser.parse_args()


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("cannot read JSON: {0}".format(path)) from exc


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    manifest = load_alas_combat_observer_manifest(args.manifest)
    trace = load_alas_combat_observer_trace(args.trace, manifest)
    promoted, receipt = promote_alas_combat_mapping_review(
        manifest,
        trace,
        _read_json(args.review),
        source_trace_sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),
    )
    _write_json(
        args.output_manifest,
        alas_combat_observer_manifest_to_json(promoted),
    )
    _write_json(args.receipt, receipt)
    print(
        json.dumps(
            {
                "schema": "alas-headless.g22-combat-mapping-promotion-result/v1",
                "passed": True,
                "manifest": str(args.output_manifest.resolve()),
                "receipt": str(args.receipt.resolve()),
                "qualified_resources": receipt["coverage_after"]["qualified_resources"],
                "total_resources": receipt["coverage_after"]["total_resources"],
                "qualified_blockers": receipt["coverage_after"]["qualified_blockers"],
                "blocker_review_complete": receipt["blocker_review_complete"],
                "production_ready": receipt["coverage_after"]["production_ready"],
                "input_injected": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
