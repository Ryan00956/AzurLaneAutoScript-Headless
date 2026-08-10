"""Verify a G28 branch replay record against its pinned ALAS source files."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    ALAS_COMBAT_BRANCH_SOURCE_FILES,
    verify_alas_combat_branch_replay_record,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument(
        "--record",
        type=Path,
        default=(
            ROOT / "integration" / "alas" / "combat-defensive-branch-replay-g28.json"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    alas_root = args.alas_root.resolve()
    try:
        value = json.loads(args.record.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("cannot read combat branch replay record") from exc
    verified = dict(verify_alas_combat_branch_replay_record(value))
    commit = subprocess.run(
        ["git", "-C", str(alas_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != value["alas_commit"]:
        raise SystemExit("ALAS branch replay commit changed")
    observed_hashes = {
        name: hashlib.sha256((alas_root / Path(name)).read_bytes()).hexdigest()
        for name in ALAS_COMBAT_BRANCH_SOURCE_FILES
    }
    if observed_hashes != value["source_files_sha256"]:
        raise SystemExit("ALAS branch replay source files changed")
    verified["source_files_match"] = True
    print(json.dumps(verified, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
