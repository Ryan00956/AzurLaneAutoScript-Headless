"""Replay rare combat branches against a real ALAS checkout without input."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    ALAS_COMBAT_BRANCH_SOURCE_FILES,
    alas_combat_branch_replay_to_json,
    replay_alas_combat_defensive_branches,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--config", default="semantic_e2e")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    alas_root = args.alas_root.resolve()
    output = args.output.resolve() if args.output is not None else None
    if not (alas_root / "campaign" / "campaign_main" / "campaign_12_4.py").is_file():
        raise SystemExit("ALAS checkout is missing pinned campaign_12_4.py")
    sys.path.insert(0, str(alas_root))
    os.chdir(alas_root)

    from campaign.campaign_main.campaign_12_4 import Campaign
    from module.config.config import AzurLaneConfig

    campaign = Campaign(
        AzurLaneConfig(args.config, task="Campaign"),
        device=SimpleNamespace(semantic_adapter=True),
    )
    result = replay_alas_combat_defensive_branches(campaign)
    commit = subprocess.run(
        ["git", "-C", str(alas_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    value = {
        **alas_combat_branch_replay_to_json(result),
        "alas_commit": commit,
        "config": args.config,
        "source_files_sha256": {
            name: _sha256(alas_root / Path(name))
            for name in ALAS_COMBAT_BRANCH_SOURCE_FILES
        },
    }
    if output is not None:
        _write_json(output, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
