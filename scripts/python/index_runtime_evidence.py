#!/usr/bin/env python3
"""Build an offline runtime evidence index from explicit roots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.runtime_evidence import (
    index_runtime_evidence,
    runtime_evidence_markdown,
)


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    arguments = parser.parse_args(list(argv) if argv else None)
    index = index_runtime_evidence(arguments.root)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if arguments.markdown is not None:
        arguments.markdown.parent.mkdir(parents=True, exist_ok=True)
        arguments.markdown.write_text(
            runtime_evidence_markdown(index), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
