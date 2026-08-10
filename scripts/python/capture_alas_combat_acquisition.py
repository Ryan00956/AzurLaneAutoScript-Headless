"""Acquire one controlled ALAS combat input and a concurrent raw trace.

This qualification-only tool does not alter the canonical ALAS patch.  It
replaces the imported zero-input preview function in memory for this process,
runs the same isolated original ``_goto()`` prefix, and lets only its exact
``device.click(grid)`` statement spend the already-admitted one-use semantic
combat lease.  The normal runner still raises its existing G18 ``ScriptEnd``
immediately afterwards, while the independent G21 recorder remains read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import alas_headless  # noqa: E402
from alas_headless import (  # noqa: E402
    ALAS_COMBAT_ACQUISITION_SCHEMA,
    AlasCampaignGotoInputCommit,
    AlasSemanticSession,
    ObserverTransportError,
    PINNED_CN_GAME_FINGERPRINT,
    alas_campaign_combat_map_state_to_json,
    alas_package_process_lease_from_trace,
    commit_alas_campaign_goto_input_for_evidence,
    current_semantic_session,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt-output", required=True, type=Path)
    parser.add_argument("--config", default="semantic_e2e")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument("--duration-seconds", type=float, default=180.0)
    parser.add_argument("--interval-seconds", type=float, default=0.20)
    parser.add_argument("--max-samples", type=int, default=1200)
    parser.add_argument("--capture-python", default=sys.executable)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-command-timeout-seconds", type=int, default=10)
    parser.add_argument("--recorder-start-timeout-seconds", type=int, default=300)
    parser.add_argument("--state-machine-start-timeout-seconds", type=int, default=120)
    parser.add_argument("--verified-trace", type=Path)
    return parser.parse_args()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


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
    args.alas_root = args.alas_root.resolve()
    args.output = args.output.resolve()
    args.receipt_output = args.receipt_output.resolve()
    args.manifest = args.manifest.resolve()
    if not (args.alas_root / "alas.py").is_file():
        raise SystemExit("ALAS root does not contain alas.py")
    if args.output.exists() or args.receipt_output.exists():
        raise SystemExit("acquisition output already exists")
    if not 10.0 <= args.duration_seconds <= 900.0:
        raise SystemExit("duration must be in [10, 900]")
    if not 0.02 <= args.interval_seconds <= 10.0:
        raise SystemExit("interval must be in [0.02, 10]")
    if not 10 <= args.max_samples <= 5000:
        raise SystemExit("max samples must be in [10, 5000]")
    if not 1 <= args.adb_command_timeout_seconds <= 120:
        raise SystemExit("ADB command timeout must be in [1, 120]")
    if not 20 <= args.recorder_start_timeout_seconds <= 360:
        raise SystemExit("recorder start timeout must be in [20, 360]")
    if not 20 <= args.state_machine_start_timeout_seconds <= 360:
        raise SystemExit("state-machine start timeout must be in [20, 360]")

    manifest = load_alas_combat_observer_manifest(args.manifest)
    game = PINNED_CN_GAME_FINGERPRINT
    expected_game = ":".join(
        (
            game.version_name,
            str(game.version_code),
            game.primary_abi,
            game.base_apk_sha256,
            game.il2cpp_sha256,
        )
    )
    if manifest.game_fingerprint != expected_game:
        raise SystemExit("manifest game fingerprint is not pinned")

    capture_command = [
        args.capture_python,
        str(ROOT / "scripts" / "python" / "capture_alas_combat_observer_trace.py"),
        "--serial",
        args.serial,
        "--output",
        str(args.output),
        "--manifest",
        str(args.manifest),
        "--duration-seconds",
        str(args.duration_seconds),
        "--interval-seconds",
        str(args.interval_seconds),
        "--max-samples",
        str(args.max_samples),
        "--adb",
        args.adb,
        "--adb-command-timeout-seconds",
        str(args.adb_command_timeout_seconds),
    ]
    if args.verified_trace is not None:
        capture_command.extend(
            ("--verified-trace", str(args.verified_trace.resolve()))
        )
    capture = subprocess.Popen(
        capture_command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    try:
        deadline = time.monotonic() + args.recorder_start_timeout_seconds
        while not args.output.exists():
            if capture.poll() is not None:
                output, _ = capture.communicate()
                raise SystemExit("trace recorder stopped early: " + output.strip())
            if time.monotonic() >= deadline:
                raise SystemExit("trace recorder did not produce a pre-input sample")
            time.sleep(0.1)

        sys.path.insert(0, str(args.alas_root))
        from alas import AzurLaneAutoScript  # noqa: E402
        from module.exception import ScriptEnd  # noqa: E402

        committed = []
        admitted_context = []
        original_preview = alas_headless.preview_alas_campaign_goto_input
        lease_trace = load_alas_combat_observer_trace(args.output, manifest)
        process_lease = alas_package_process_lease_from_trace(
            lease_trace, manifest
        )
        semantic_session = AlasSemanticSession(
            serial=args.serial,
            driver_revision=manifest.driver_revision,
            adb=args.adb,
            package=manifest.package,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
            campaign_combat_budget=1,
            adb_command_timeout_seconds=args.adb_command_timeout_seconds,
            package_process_lease=process_lease,
        )
        original_session_factory = AlasSemanticSession.__dict__["from_environment"]

        def leased_session_factory(cls, serial):
            del cls
            if serial != args.serial:
                raise RuntimeError("G32 package-process lease serial changed")
            return semantic_session

        def evidence_preview(campaign, projection, decision, admission, state):
            if committed:
                raise RuntimeError("G23 acquisition attempted a second combat input")
            result = commit_alas_campaign_goto_input_for_evidence(
                campaign,
                projection,
                decision,
                admission,
                state,
                input_committer=current_semantic_session(),
            )
            committed.append(result)
            admitted_context.append((admission, state))
            return result.preview

        alas_headless.preview_alas_campaign_goto_input = evidence_preview
        AlasSemanticSession.from_environment = classmethod(
            leased_session_factory
        )
        os.environ["ALAS_SEMANTIC_MODE"] = "1"
        os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = manifest.driver_revision
        os.environ["ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS"] = str(
            args.adb_command_timeout_seconds
        )
        os.environ["ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET"] = "1"
        os.environ["ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET"] = "3"
        os.environ["ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET"] = "1"
        os.environ["ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET"] = "1"

        previous_cwd = Path.cwd()
        try:
            os.chdir(str(args.alas_root))
            alas = AzurLaneAutoScript(config_name=args.config)
            alas.config.bind("Main")
            alas.config.override(
                Emulator_Serial=args.serial,
                Emulator_ScreenshotMethod="ADB",
                Emulator_ControlMethod="ADB",
                Campaign_UseAutoSearch=False,
                Campaign_Use2xBook=False,
                Submarine_Mode="do_not_use",
            )
            # The null ANGLE backend intentionally makes ALAS's framebuffer
            # probes black.  Device construction can therefore take longer
            # than the observer's strict 2.5-second freshness window while a
            # static map publishes frames sparsely.  Wait read-only for the
            # next exact reviewed campaign surface *after* construction, then
            # enter the original state machine immediately without another
            # screenshot.  ``campaign_is_in_map()`` returning False is still
            # positive recognition of a reviewed login/main/campaign startup
            # surface; only an exception means the observer does not know the
            # current UI.  No action freshness threshold is widened here.
            start_deadline = (
                time.monotonic() + args.state_machine_start_timeout_seconds
            )
            startup_in_map = False
            while True:
                try:
                    startup_in_map = (
                        semantic_session.open().oracle.campaign_is_in_map()
                    )
                    break
                except (ObserverTransportError, alas_headless.SemanticGateClosed):
                    pass
                if time.monotonic() >= start_deadline:
                    raise SystemExit(
                        "no fresh reviewed campaign surface before state-machine start"
                    )
                time.sleep(0.1)
            if (
                not startup_in_map
                and semantic_session.open().oracle.enabled("login/enter")
            ):
                from module.handler.login import LoginHandler  # noqa: E402

                semantic_session.begin_login()
                try:
                    LoginHandler(
                        alas.config, device=alas.device
                    ).handle_app_login()
                finally:
                    semantic_session.end_login()
            try:
                alas.run("main", skip_first_screenshot=True)
            except ScriptEnd as exc:
                if str(exc) != "Semantic ALAS goto input preview validation complete":
                    raise
            except SystemExit as exc:
                # ALAS's outer run() treats ScriptEnd as an unexpected generic
                # exception and converts it to exit(1).  Accept that conversion
                # only after our exact one-use commit has already been recorded.
                if exc.code != 1 or len(committed) != 1:
                    raise
        finally:
            os.chdir(str(previous_cwd))
            alas_headless.preview_alas_campaign_goto_input = original_preview
            AlasSemanticSession.from_environment = original_session_factory
            try:
                semantic_session.close()
            except ObserverTransportError:
                pass

        if len(committed) != 1 or len(admitted_context) != 1 or not isinstance(
            committed[0], AlasCampaignGotoInputCommit
        ):
            raise SystemExit("original ALAS path did not commit exactly one input")
        commit = committed[0]
        admission, state = admitted_context[0]

        capture_output, _ = capture.communicate(
            timeout=args.duration_seconds + 30.0
        )
        if capture.returncode != 0:
            raise SystemExit("trace recorder failed: " + capture_output.strip())

        trace = load_alas_combat_observer_trace(args.output, manifest)
        first_generation = trace.generations[0]
        last_generation = trace.generations[-1]
        if (
            first_generation > commit.preview.input_generation
            or last_generation <= commit.receipt.generation
        ):
            raise SystemExit("raw trace does not straddle the controlled input")
        receipt = {
            "schema": ALAS_COMBAT_ACQUISITION_SCHEMA,
            "captured_at_utc": utc_now(),
            "package": manifest.package,
            "driver_revision": manifest.driver_revision,
            "game_fingerprint": manifest.game_fingerprint,
            "pid": trace.pid,
            "controlled_input_injected": True,
            "trace_recorder_input_injected": False,
            "trace_path": str(args.output),
            "trace_sha256": sha256_file(args.output),
            "sample_count": len(trace.samples),
            "first_generation": first_generation,
            "last_generation": last_generation,
            "map_before": alas_campaign_combat_map_state_to_json(state),
            "input": {
                "stage_code": commit.preview.stage_code,
                "battle_count": commit.preview.battle_count,
                "branch_name": commit.preview.branch_name,
                "fleet_index": commit.preview.fleet_index,
                "fleet_marker": commit.preview.fleet_marker,
                "enemy_object_id": admission.enemy_object_id,
                "ammo_before": admission.ammo_before,
                "origin_node": commit.preview.origin_node,
                "target_node": commit.preview.target_node,
                "route_nodes": list(commit.preview.route_nodes),
                "expected": commit.preview.expected,
                "cell_path": commit.preview.cell_path,
                "point": {
                    "x": commit.preview.point.x,
                    "y": commit.preview.point.y,
                },
                "bounds": {
                    "left": commit.preview.bounds.left,
                    "top": commit.preview.bounds.top,
                    "right": commit.preview.bounds.right,
                    "bottom": commit.preview.bounds.bottom,
                },
                "admission_generation": commit.preview.generation,
                "preflight_generation": commit.preview.input_generation,
                "receipt_generation": commit.receipt.generation,
                "receipt_semantic_id": commit.receipt.semantic_id,
                "call_order": list(commit.preview.call_order),
            },
        }
        write_json(args.receipt_output, receipt)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        if capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.wait()


if __name__ == "__main__":
    raise SystemExit(main())
