"""Qualify a naturally out-of-sight ALAS `_goto()` camera branch.

The pinned ALAS ``focus_to() -> map_swipe() -> _map_swipe() ->
device.swipe_vector()`` chain owns the grid vector, pixel scaling, random safe
path selection, duration conversion, and distance check.  Its original
``Camera.update()`` consumes a typed Unity View.  A separate qualification-only
empty-cell gesture first places the camera out of sight; ALAS then chooses the
same target again and original ``_goto()`` owns the camera request and recheck.
The qualifier stops at the exact grid-click statement without injecting it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import alas_headless  # noqa: E402
from alas_headless import (  # noqa: E402
    AlasSemanticSession,
    CampaignMapViewportSwipeProof,
    ObserverTransportError,
    SemanticGateClosed,
    alas_package_process_lease_from_trace,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
    position_alas_campaign_camera_for_qualification,
    preview_alas_campaign_decision,
    preview_alas_campaign_viewport_continuation,
    synchronize_alas_campaign_map,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", default="semantic_e2e")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument("--verified-trace", type=Path)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-command-timeout-seconds", type=int, default=10)
    parser.add_argument("--startup-timeout-seconds", type=int, default=120)
    return parser.parse_args()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def proof_to_json(proof: CampaignMapViewportSwipeProof, *, pid: int) -> dict:
    return {
        "schema": "alas-headless.g35-natural-goto-camera/v1",
        "captured_at_utc": utc_now(),
        "pid": pid,
        "semantic_id": proof.semantic_id,
        "target_node": proof.target_node,
        "pre_generation": proof.pre_generation,
        "input_generation": proof.input_generation,
        "post_generation": proof.post_generation,
        "name": proof.name,
        "grid_vector": list(proof.grid_vector),
        "pixel_vector": list(proof.pixel_vector),
        "start": list(proof.start),
        "end": list(proof.end),
        "duration_ms": proof.duration_ms,
        "coherent_cell_count": proof.coherent_cell_count,
        "median_cell_delta": list(proof.median_cell_delta),
        "maximum_delta_residual": proof.maximum_delta_residual,
        "target_path": proof.target_path,
        "target_before_point": {
            "x": proof.target_before_point.x,
            "y": proof.target_before_point.y,
        },
        "target_after_point": {
            "x": proof.target_after_point.x,
            "y": proof.target_after_point.y,
        },
        "target_after_bounds": {
            "left": proof.target_after_bounds.left,
            "top": proof.target_after_bounds.top,
            "right": proof.target_after_bounds.right,
            "bottom": proof.target_after_bounds.bottom,
        },
        "logical_map_signature_unchanged": True,
        "target_after_top_raycast": True,
        "input_injected": True,
        "production_enabled": False,
        "post_swipe_alas_view_update_owner": True,
    }


def main() -> int:
    args = parse_args()
    args.alas_root = args.alas_root.resolve()
    args.output = args.output.resolve()
    args.manifest = args.manifest.resolve()
    if not (args.alas_root / "alas.py").is_file():
        raise SystemExit("ALAS root does not contain alas.py")
    if args.output.exists():
        raise SystemExit("viewport proof output already exists")
    if not 1 <= args.adb_command_timeout_seconds <= 120:
        raise SystemExit("ADB timeout must be in [1, 120]")
    if not 20 <= args.startup_timeout_seconds <= 360:
        raise SystemExit("startup timeout must be in [20, 360]")

    manifest = load_alas_combat_observer_manifest(args.manifest)
    process_lease = None
    if args.verified_trace is not None:
        trace = load_alas_combat_observer_trace(
            args.verified_trace.resolve(), manifest
        )
        process_lease = alas_package_process_lease_from_trace(trace, manifest)

    session = AlasSemanticSession(
        serial=args.serial,
        driver_revision=manifest.driver_revision,
        adb=args.adb,
        package=manifest.package,
        campaign_stage_entry_budget=1,
        campaign_fleet_mutation_budget=3,
        campaign_sortie_budget=1,
        campaign_combat_budget=1,
        campaign_viewport_swipe_budget=1,
        campaign_camera_positioning_budget=2,
        adb_command_timeout_seconds=args.adb_command_timeout_seconds,
        package_process_lease=process_lease,
    )
    original_factory = AlasSemanticSession.__dict__["from_environment"]
    original_preview = alas_headless.preview_alas_campaign_goto_input
    proofs = []
    continuations = []
    camera_positionings = []
    camera_positioning_proofs = []
    camera_positioning_proof_sequences = []
    decision_revalidations = []
    dismissed_overlays = []
    startup_page_records = []

    def stable_campaign_page():
        last_error = None
        for _ in range(4):
            try:
                return session.open().oracle.campaign_page_state()
            except SemanticGateClosed as exc:
                if str(exc) not in (
                    "observer endpoints are not generation-coherent",
                    "campaign snapshots are not coherent",
                ):
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    def click_if_enabled_when_coherent(semantic_id):
        last_error = None
        for _ in range(8):
            try:
                oracle = session.open().oracle
                if not oracle.enabled(semantic_id):
                    return None
                return oracle.click(semantic_id)
            except SemanticGateClosed as exc:
                if str(exc) not in (
                    "observer snapshot is stale",
                    "observer endpoints are not generation-coherent",
                    "Msgbox snapshots are not coherent",
                ):
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    def leased_factory(cls, serial):
        del cls
        if serial != args.serial:
            raise RuntimeError("G33 semantic session serial changed")
        return session

    sys.path.insert(0, str(args.alas_root))
    from alas import AzurLaneAutoScript  # noqa: E402
    from module.exception import ScriptEnd  # noqa: E402

    def qualify_viewport(campaign, projection, decision, admission, state):
        if proofs:
            raise SemanticGateClosed("G35 attempted a second viewport input")
        map_kwargs = {
            "columns": campaign.MAP.shape[0] + 1,
            "rows": campaign.MAP.shape[1] + 1,
            "land_cells": tuple(
                grid.location for grid in campaign.MAP if grid.is_land
            ),
            "expected_fleet_count": sum(
                (
                    bool(campaign.config.Fleet_Fleet1),
                    bool(campaign.config.Fleet_Fleet2),
                )
            ),
        }
        original_identity = (
            decision.branch_name,
            decision.battle_count,
            decision.fleet_index,
            decision.fleet_marker,
            decision.target_kind,
            decision.target_node,
            decision.expected,
            decision.cost,
            decision.route_nodes,
            decision.goto_nodes,
        )

        # The live camera is currently centered on F6.  Use one independent,
        # qualification-only empty-cell gesture to place it at F3, close that
        # flow, then reacquire the map and let ALAS independently choose again.
        session.end_campaign_pre_sortie()
        session.begin_campaign_pre_sortie(state.stage_code)
        positioning_state = session.campaign_map_state(**map_kwargs)
        positioning_projection = synchronize_alas_campaign_map(
            campaign, positioning_state
        )
        positioning = position_alas_campaign_camera_for_qualification(
            campaign,
            positioning_projection,
            positioning_state,
            target_node="F3",
            semantic_session=session,
        )
        positioning_proof = session.campaign_camera_positioning_proof()
        positioning_proof_sequence = (
            session.campaign_camera_positioning_proofs()
        )
        camera_positionings.append(positioning)
        camera_positioning_proofs.append(positioning_proof)
        camera_positioning_proof_sequences.append(
            positioning_proof_sequence
        )

        session.end_campaign_pre_sortie()
        session.begin_campaign_pre_sortie(state.stage_code)
        fresh_state = session.campaign_map_state(**map_kwargs)
        fresh_projection = synchronize_alas_campaign_map(
            campaign, fresh_state
        )
        fresh_decision = preview_alas_campaign_decision(
            campaign, fresh_projection
        )
        fresh_identity = (
            fresh_decision.branch_name,
            fresh_decision.battle_count,
            fresh_decision.fleet_index,
            fresh_decision.fleet_marker,
            fresh_decision.target_kind,
            fresh_decision.target_node,
            fresh_decision.expected,
            fresh_decision.cost,
            fresh_decision.route_nodes,
            fresh_decision.goto_nodes,
        )
        if fresh_identity != original_identity:
            raise SemanticGateClosed(
                "G35 camera setup changed ALAS's original decision"
            )
        decision_revalidations.append(
            {
                "before_generation": decision.generation,
                "after_generation": fresh_decision.generation,
                "branch_name": fresh_decision.branch_name,
                "fleet_index": fresh_decision.fleet_index,
                "fleet_marker": fresh_decision.fleet_marker,
                "target_kind": fresh_decision.target_kind,
                "target_node": fresh_decision.target_node,
                "route_nodes": list(fresh_decision.route_nodes),
                "goto_nodes": list(fresh_decision.goto_nodes),
                "unchanged": True,
            }
        )
        fresh_admission = session.authorize_campaign_combat(
            fresh_decision, fresh_state
        )
        if fresh_admission is None:
            raise SemanticGateClosed(
                "G35 did not receive a fresh combat admission"
            )
        continuation = preview_alas_campaign_viewport_continuation(
            campaign,
            fresh_projection,
            fresh_decision,
            fresh_admission,
            fresh_state,
            semantic_session=session,
            original_goto_initiates_camera=True,
        )
        proof = session.campaign_map_viewport_swipe_proof()
        proofs.append(proof)
        continuations.append(continuation)
        raise ScriptEnd(
            "Semantic ALAS natural goto camera validation complete"
        )

    AlasSemanticSession.from_environment = classmethod(leased_factory)
    alas_headless.preview_alas_campaign_goto_input = qualify_viewport
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = manifest.driver_revision
    os.environ["ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET"] = "1"
    os.environ["ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET"] = "3"
    os.environ["ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET"] = "1"
    os.environ["ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET"] = "1"
    os.environ["ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET"] = "1"

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
        cleanup_semantic_ids = (
            "overlay/network-reconnect/confirm",
            "overlay/bulletin/close",
            "reward/award-info/close",
            "reward/award-info1/close",
            "reward/campaign-total/exit",
            "campaign/fleet-preparation/cancel",
            "campaign/map-preparation/cancel",
        )
        for _cleanup_round in range(8):
            cleanup = None
            for semantic_id in cleanup_semantic_ids:
                receipt = click_if_enabled_when_coherent(semantic_id)
                if receipt is not None:
                    cleanup = (semantic_id, receipt)
                    break
            if cleanup is None:
                break
            semantic_id, receipt = cleanup
            dismissed_overlays.append(
                {
                    "semantic_id": receipt.semantic_id,
                    "generation": receipt.generation,
                    "path": receipt.path,
                }
            )
            time.sleep(
                3.0
                if semantic_id == "overlay/network-reconnect/confirm"
                else 1.0
            )
        else:
            raise SystemExit(
                "G33 startup cleanup exhausted its exact-input budget"
            )
        if session.open().oracle.dock_full_prompt_active():
            raise SystemExit(
                "G33 sortie is blocked because the dock is full; "
                "clear at least one slot without spending resources, then rerun"
            )
        if any(
            item["semantic_id"].startswith("campaign/")
            for item in dismissed_overlays
        ):
            recovery_deadline = time.monotonic() + args.startup_timeout_seconds
            while True:
                try:
                    recovered_page = stable_campaign_page()
                    break
                except SemanticGateClosed:
                    if time.monotonic() >= recovery_deadline:
                        raise SystemExit(
                            "campaign preparation cleanup did not restore chapter page"
                        )
                    time.sleep(0.1)
            startup_page_records.append(
                {
                    "generation": recovered_page.generation,
                    "chapter_name": recovered_page.chapter_name,
                    "stage_codes": [
                        item.stage_code for item in recovered_page.stages
                    ],
                    "owner": "typed-preparation-cleanup-proof",
                }
            )
        deadline = time.monotonic() + args.startup_timeout_seconds
        startup_in_map = False
        while True:
            try:
                startup_in_map = session.open().oracle.campaign_is_in_map()
                break
            except (ObserverTransportError, SemanticGateClosed):
                if time.monotonic() >= deadline:
                    raise SystemExit("no fresh campaign surface before G33 start")
                time.sleep(0.1)
        login_handled = False

        def handle_login_once_if_present():
            nonlocal login_handled
            if login_handled:
                return False
            try:
                oracle = session.open().oracle
                login_present = oracle.enabled("login/enter") or oracle.enabled(
                    "overlay/login-data-expired/confirm"
                )
            except (ObserverTransportError, SemanticGateClosed):
                return False
            if not login_present:
                return False
            from module.handler.login import LoginHandler  # noqa: E402

            login_handled = True
            LoginHandler(alas.config, device=alas.device).handle_app_login()
            return True

        if not startup_in_map:
            handle_login_once_if_present()
        from module.campaign.run import CampaignRun  # noqa: E402
        from module.ui.page import page_campaign  # noqa: E402

        runner = CampaignRun(config=alas.config, device=alas.device)
        run_name = alas.config.Campaign_Name
        run_folder = alas.config.Campaign_Event
        run_mode = alas.config.Campaign_Mode
        campaign_page = None
        if not startup_in_map:
            surface_deadline = time.monotonic() + args.startup_timeout_seconds
            while True:
                try:
                    if session.open().oracle.campaign_is_in_map():
                        startup_in_map = True
                        break
                except (ObserverTransportError, SemanticGateClosed):
                    pass
                try:
                    if session.open().oracle.enabled("main/battle"):
                        break
                except SemanticGateClosed:
                    pass
                try:
                    if session.open().oracle.campaign_menu_is_entry():
                        break
                except SemanticGateClosed:
                    pass
                if handle_login_once_if_present():
                    continue
                try:
                    campaign_page = stable_campaign_page()
                    break
                except SemanticGateClosed:
                    if time.monotonic() >= surface_deadline:
                        raise SystemExit(
                            "G33 start surface did not settle to main or campaign page"
                        )
                    time.sleep(0.1)
            if campaign_page is not None:
                visible_stage_codes = tuple(
                    item.stage_code for item in campaign_page.stages
                )
                expected_stage = run_name.replace("campaign_", "")
                expected_stage = expected_stage.replace("_", "-")
                if expected_stage not in visible_stage_codes:
                    raise SemanticGateClosed(
                        "typed campaign bootstrap does not expose configured stage"
                    )
                original_load_campaign = runner.load_campaign

                def load_campaign_with_typed_bootstrap(
                    self, name, folder="campaign_main"
                ):
                    loaded = original_load_campaign(name, folder=folder)
                    original_get_current_page = self.campaign.ui_get_current_page
                    used = False

                    def typed_first_current_page(
                        campaign_self, *unused_args, **unused_kwargs
                    ):
                        nonlocal used
                        del unused_args, unused_kwargs
                        if used:
                            return original_get_current_page()
                        confirmed = stable_campaign_page()
                        if expected_stage not in tuple(
                            item.stage_code for item in confirmed.stages
                        ):
                            raise SemanticGateClosed(
                                "typed campaign bootstrap changed before ALAS use"
                            )
                        used = True
                        campaign_self.ui_current = page_campaign
                        campaign_self.ui_get_current_page = original_get_current_page
                        original_campaign_page_state = session.campaign_page_state
                        cached_page_reads_remaining = 4

                        def cached_campaign_page_state():
                            nonlocal cached_page_reads_remaining
                            if cached_page_reads_remaining <= 0:
                                return original_campaign_page_state()
                            cached_page_reads_remaining -= 1
                            context = session.open()._campaign_context
                            if context is not None:
                                context.passive_transition_until = (
                                    time.monotonic() + 90.0
                                )
                            return confirmed

                        # The pinned ALAS OCR adapter immediately asks for the
                        # same chapter labels again, before any input.  Reuse
                        # this just-proven immutable view for that bounded
                        # bootstrap instead of requiring a second lucky
                        # three-endpoint sampling phase.
                        session.campaign_page_state = cached_campaign_page_state
                        startup_page_records.append(
                            {
                                "generation": confirmed.generation,
                                "chapter_name": confirmed.chapter_name,
                                "stage_codes": list(visible_stage_codes),
                                "owner": "typed-qualification-bootstrap-once",
                                "cached_read_budget": 4,
                            }
                        )
                        return page_campaign

                    self.campaign.ui_get_current_page = MethodType(
                        typed_first_current_page, self.campaign
                    )
                    return loaded

                runner.load_campaign = MethodType(
                    load_campaign_with_typed_bootstrap, runner
                )

        try:
            runner.run(
                name=run_name,
                folder=run_folder,
                mode=run_mode,
            )
            if not proofs:
                # G11 deliberately ends the first CampaignRun immediately
                # after proving sortie -> typed map root.  G33 belongs to the
                # next original ALAS start-in-map pass, where map projection,
                # decision, combat admission, and goto preview already live.
                # Prove that exact handoff before allowing a second pass; do
                # not re-enter the stage from any non-map surface.
                handoff_deadline = (
                    time.monotonic() + args.startup_timeout_seconds
                )
                while True:
                    try:
                        handoff_in_map = (
                            session.open().oracle.campaign_is_in_map()
                        )
                    except (ObserverTransportError, SemanticGateClosed):
                        handoff_in_map = False
                    if handoff_in_map:
                        break
                    if time.monotonic() >= handoff_deadline:
                        raise SystemExit(
                            "G11 did not hand off a typed map to G33"
                        )
                    time.sleep(0.1)
                startup_page_records.append(
                    {
                        "owner": "typed-g11-to-g33-map-handoff",
                        "input_injected": False,
                    }
                )
                campaign_map = runner.campaign.MAP
                enemy_deadline = (
                    time.monotonic() + args.startup_timeout_seconds
                )
                while True:
                    try:
                        ready_state = session.open().oracle.campaign_map_state(
                            run_name.replace("campaign_", "").replace("_", "-"),
                            columns=campaign_map.shape[0] + 1,
                            rows=campaign_map.shape[1] + 1,
                            land_cells=tuple(
                                grid.location for grid in campaign_map if grid.is_land
                            ),
                            expected_fleet_count=sum(
                                (
                                    bool(runner.campaign.config.Fleet_Fleet1),
                                    bool(runner.campaign.config.Fleet_Fleet2),
                                )
                            ),
                        )
                    except (ObserverTransportError, SemanticGateClosed):
                        ready_state = None
                    if ready_state is not None and ready_state.enemies:
                        break
                    if time.monotonic() >= enemy_deadline:
                        raise SystemExit(
                            "G33 map did not expose a stable enemy before decision"
                        )
                    time.sleep(0.25)
                startup_page_records.append(
                    {
                        "owner": "typed-g33-enemy-ready",
                        "generation": ready_state.generation,
                        "enemy_nodes": [
                            enemy.node for enemy in ready_state.enemies
                        ],
                        "input_injected": False,
                    }
                )
                runner.run(
                    name=run_name,
                    folder=run_folder,
                    mode=run_mode,
                )
        except ScriptEnd as exc:
            if str(exc) != (
                "Semantic ALAS natural goto camera validation complete"
            ):
                raise
    finally:
        os.chdir(str(previous_cwd))
        alas_headless.preview_alas_campaign_goto_input = original_preview
        AlasSemanticSession.from_environment = original_factory
        try:
            session.close()
        except ObserverTransportError:
            pass

    if (
        len(proofs) != 1
        or len(continuations) != 1
        or len(camera_positionings) != 1
        or len(camera_positioning_proofs) != 1
        or len(camera_positioning_proof_sequences) != 1
        or len(decision_revalidations) != 1
    ):
        raise SystemExit(
            "pinned ALAS did not prove one setup and one natural goto gesture"
        )
    record = proof_to_json(proofs[0], pid=session.bridge.pid or 0)
    continuation = continuations[0]
    record["alas_camera_continuation"] = {
        "camera_before_node": continuation.camera_before_node,
        "camera_after_node": continuation.camera_after_node,
        "camera_before_offset": list(continuation.camera_before_offset),
        "camera_after_offset": list(continuation.camera_after_offset),
        "requested_grid_vector": list(continuation.requested_grid_vector),
        "camera_state_generation": continuation.camera_state_generation,
        "recheck_generation": continuation.recheck_generation,
        "target_local_location": list(continuation.target_local_location),
        "call_order": list(continuation.call_order),
        "original_camera_update_owner": (
            continuation.original_camera_update_owner
        ),
        "original_alas_goto_recheck_owner": (
            continuation.original_alas_goto_recheck_owner
        ),
        "original_alas_goto_camera_initiator": (
            continuation.original_alas_goto_camera_initiator
        ),
    }
    positioning = camera_positionings[0]
    positioning_proof = camera_positioning_proofs[0]
    positioning_proof_sequence = camera_positioning_proof_sequences[0]
    record["qualification_camera_setup"] = {
        "target_node": positioning.target_node,
        "camera_before_node": positioning.camera_before_node,
        "camera_after_node": positioning.camera_after_node,
        "camera_before_offset": list(positioning.camera_before_offset),
        "camera_after_offset": list(positioning.camera_after_offset),
        "requested_grid_vector": list(positioning.requested_grid_vector),
        "gesture_grid_vectors": [
            list(item) for item in positioning.gesture_grid_vectors
        ],
        "gesture_count": positioning.gesture_count,
        "pre_generation": positioning_proof.pre_generation,
        "input_generation": positioning_proof.input_generation,
        "post_generation": positioning_proof.post_generation,
        "proof_generations": [
            {
                "pre": item.pre_generation,
                "input": item.input_generation,
                "post": item.post_generation,
            }
            for item in positioning_proof_sequence
        ],
        "call_order": list(positioning.call_order),
        "input_injected": positioning.input_injected,
        "qualification_only": positioning.qualification_only,
        "production_enabled": positioning.production_enabled,
    }
    record["grid_input_injected"] = continuation.grid_input_injected
    record["decision_revalidation_after_setup"] = decision_revalidations[0]
    record["total_camera_inputs"] = positioning.gesture_count + 1
    record["production_enabled"] = continuation.production_enabled
    record["dismissed_overlays"] = dismissed_overlays
    record["startup_page_bootstrap"] = startup_page_records
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(args.output))
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
