#!/usr/bin/env python3
"""Validate a runtime lock and optional local artifact files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Sequence

from alas_headless.runtime_artifacts import (
    RuntimeLock,
    RuntimeLockError,
    expected_artifact_hashes,
    verify_artifact_files,
)


def _artifact_arguments(values: Sequence[str]) -> Dict[str, Path]:
    artifacts = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            raise RuntimeLockError("artifact arguments must use name=path")
        if name in artifacts:
            raise RuntimeLockError("duplicate artifact argument: {0}".format(name))
        artifacts[name] = Path(raw_path)
    return artifacts


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--artifact", action="append", default=[])
    arguments = parser.parse_args(list(argv) if argv else None)
    value = json.loads(arguments.lock.read_text(encoding="utf-8"))
    runtime_lock = RuntimeLock.from_mapping(value)
    artifacts = _artifact_arguments(arguments.artifact)
    verified = {}
    if artifacts:
        expected = expected_artifact_hashes(runtime_lock)
        unknown = sorted(set(artifacts) - set(expected))
        if unknown:
            raise RuntimeLockError(
                "unknown artifact names: {0}".format(", ".join(unknown))
            )
        verified = verify_artifact_files(
            {name: expected[name] for name in artifacts}, artifacts
        )
    print(
        json.dumps(
            {
                "schema": "alas-headless.runtime-lock-validation/v1",
                "runtime_lock_sha256": runtime_lock.sha256,
                "verified_artifacts": verified,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
