#!/usr/bin/env python3
"""Plan or execute one exact-lock runtime qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from alas_headless.runtime_artifacts import RuntimeLock
from alas_headless.runtime_backends import backend_from_config
from alas_headless.runtime_command import (
    RuntimeCommandExecutor,
    RuntimeExecutionPolicy,
)
from alas_headless.runtime_qualification import RuntimeQualificationRunner
from alas_headless.runtime_qualification import RUNTIME_RECOVERY_KINDS


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime input must be a JSON object")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-runtime-mutation", action="store_true")
    parser.add_argument("--recovery", choices=RUNTIME_RECOVERY_KINDS)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(list(argv) if argv else None)

    runtime_lock = RuntimeLock.from_mapping(_load_json(arguments.lock))
    config = _load_json(arguments.config)
    if config.get("backend") != arguments.backend:
        parser.error("--backend does not match the runtime config")
    if runtime_lock.document["android"]["backend"] != arguments.backend:
        parser.error("--backend does not match the runtime lock")
    if arguments.allow_runtime_mutation and not arguments.execute:
        parser.error("--allow-runtime-mutation requires --execute")
    if arguments.execute and not arguments.allow_runtime_mutation:
        parser.error("--execute requires --allow-runtime-mutation")
    if arguments.execute and arguments.output is None:
        parser.error("--execute requires --output")
    if not arguments.execute and arguments.output is not None:
        parser.error("--output requires --execute; use --plan-output for plans")
    if arguments.execute and arguments.plan_output is not None:
        parser.error("--plan-output cannot be combined with --execute")

    executor = RuntimeCommandExecutor(
        RuntimeExecutionPolicy(
            allow_read_only=True,
            allow_runtime_mutation=arguments.allow_runtime_mutation,
        )
    )
    backend = backend_from_config(config, executor)
    configured_package = getattr(backend, "package", None)
    if (
        configured_package is not None
        and configured_package != runtime_lock.document["game"]["package"]
    ):
        parser.error("runtime config package does not match the runtime lock")
    plan = dict(backend.qualification_plan(runtime_lock))
    plan["runtime_lock_sha256"] = runtime_lock.sha256
    plan.setdefault("executable", True)
    if arguments.recovery is not None:
        plan["gate"] = "runtime-recovery-{0}".format(arguments.recovery)
        plan["recovery"] = arguments.recovery
        if not backend.supports_recovery(arguments.recovery):
            plan["executable"] = False
            plan["reason"] = "{0}-recovery-not-enabled".format(
                arguments.recovery
            )
        else:
            phases = list(plan.get("phases", ()))
            if phases and phases[-1] == "stop":
                phases.pop()
            if arguments.recovery == "game":
                phases.extend(
                    (
                        "restart-game",
                        "game-recovered",
                        "observer-recovered",
                        "fingerprint-recovered",
                    )
                )
                plan.setdefault("state_changes", []).append("restart-game-process")
            else:
                phases.extend(
                    (
                        "restart-android",
                        "adb-offline",
                        "adb-recovered",
                        "android-recovered",
                        "game-recovered",
                        "observer-recovered",
                        "fingerprint-recovered",
                    )
                )
                plan.setdefault("state_changes", []).append("restart-android")
            phases.append("stop")
            plan["phases"] = phases
    if not arguments.execute:
        if arguments.plan_output is not None:
            _write_json_atomic(arguments.plan_output, plan)
        print(json.dumps(plan, sort_keys=True))
        return 0

    assert arguments.output is not None
    if plan["executable"] is not True:
        parser.error(
            "backend is plan-only: {0}".format(
                plan.get("reason", "adapter-not-executable")
            )
        )
    manifest = RuntimeQualificationRunner(
        backend, runtime_lock, arguments.output
    ).qualify(arguments.recovery)
    print(str((arguments.output / "manifest.json").resolve()))
    return 0 if manifest["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
