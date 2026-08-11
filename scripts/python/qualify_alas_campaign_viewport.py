"""Qualify one ALAS-owned campaign camera swipe on the live semantic map.

The pinned ALAS ``focus_to() -> map_swipe() -> _map_swipe() ->
device.swipe_vector()`` chain owns the grid vector, pixel scaling, random safe
path selection, duration conversion, and distance check.  The semantic adapter
replaces only the final input dispatch and stops this qualification before any
grid click or post-click combat logic.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import alas_headless  # noqa: E402
from alas_headless import (  # noqa: E402
    AlasSemanticSession,
    CampaignMapViewportSwipeProof,
    ObserverTransportError,
    SemanticGateClosed,
    alas_package_process_lease_from_trace,
    current_semantic_session,
    load_alas_combat_observer_manifest,
    load_alas_combat_observer_trace,
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


def node_location(node: str) -> tuple[int, int]:
    column = ord(node[0]) - ord("A")
    return column, int(node[1:]) - 1


def semantic_swipe_base(state) -> tuple[float, float]:
    cells = {(cell.row, cell.column): cell for cell in state.cells}
    horizontal = []
    vertical = []
    for (row, column), cell in cells.items():
        right = cells.get((row, column + 1))
        below = cells.get((row + 1, column))
        if right is not None:
            horizontal.append(
                ((right.point.x - cell.point.x) ** 2 +
                 (right.point.y - cell.point.y) ** 2) ** 0.5
            )
        if below is not None:
            vertical.append(
                ((below.point.x - cell.point.x) ** 2 +
                 (below.point.y - cell.point.y) ** 2) ** 0.5
            )
    if not horizontal or not vertical:
        raise SemanticGateClosed("semantic map cannot derive ALAS swipe base")
    values = statistics.median(horizontal), statistics.median(vertical)
    if any(not 40.0 <= value <= 240.0 for value in values):
        raise SemanticGateClosed("semantic ALAS swipe base is outside limits")
    return values


def proof_to_json(proof: CampaignMapViewportSwipeProof, *, pid: int) -> dict:
    return {
        "schema": "alas-headless.g33-campaign-viewport-proof/v1",
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
        "post_swipe_alas_view_update_owner": False,
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
        adb_command_timeout_seconds=args.adb_command_timeout_seconds,
        package_process_lease=process_lease,
    )
    original_factory = AlasSemanticSession.__dict__["from_environment"]
    original_preview = alas_headless.preview_alas_campaign_goto_input
    proofs = []
    camera_records = []
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
        del projection
        if proofs:
            raise SemanticGateClosed("G33 attempted a second viewport input")
        adapter = current_semantic_session()
        if adapter is None:
            raise SemanticGateClosed("G33 semantic session is not bound")
        swipe_base = semantic_swipe_base(state)
        origin = node_location(admission.origin_node)
        target = node_location(admission.target_node)
        delta = target[0] - origin[0], target[1] - origin[1]
        if delta == (0, 0) or abs(delta[0]) > 4 or abs(delta[1]) > 3:
            raise SemanticGateClosed("G33 target does not require a bounded camera move")

        sandbox = copy.copy(campaign)
        sandbox.__dict__ = campaign.__dict__.copy()
        # The pinned ALAS exposes DEVICE_CONTROL_METHOD as a read-only
        # property backed by Emulator_ControlMethod.  The preview sandbox only
        # needs Camera._map_swipe's immutable calibration inputs, so provide a
        # narrow detached view instead of mutating or persisting live config.
        sandbox.config = SimpleNamespace(
            DEVICE_CONTROL_METHOD="ADB",
            MAP_SWIPE_DROP=campaign.config.MAP_SWIPE_DROP,
            MAP_SWIPE_MULTIPLY=campaign.config.MAP_SWIPE_MULTIPLY,
            MAP_SWIPE_MULTIPLY_MINITOUCH=(
                campaign.config.MAP_SWIPE_MULTIPLY_MINITOUCH
            ),
            MAP_SWIPE_MULTIPLY_MAATOUCH=(
                campaign.config.MAP_SWIPE_MULTIPLY_MAATOUCH
            ),
            MAP_SWIPE_OPTIMIZE=False,
        )
        sandbox.camera = origin
        sandbox.view = SimpleNamespace(
            center_offset=np.array((0.5, 0.5), dtype=float),
            swipe_base=np.array(swipe_base, dtype=float),
        )
        sandbox.device = campaign.device

        def update_after_proof(self, *unused_args, **unused_kwargs):
            del unused_args, unused_kwargs
            context = adapter.open()._campaign_context
            proof = None if context is None else context.viewport_swipe_proof
            if not isinstance(proof, CampaignMapViewportSwipeProof):
                raise SemanticGateClosed("ALAS camera update preceded viewport proof")
            self.camera = target
            self._prev_view = None
            self._prev_swipe = None
            camera_records.append(
                {
                    "origin": admission.origin_node,
                    "target": admission.target_node,
                    "requested_delta": list(delta),
                    "swipe_base": list(swipe_base),
                    "map_swipe_multiply": list(self.config.MAP_SWIPE_MULTIPLY),
                    "update_wait_swipe": True,
                }
            )
            return True

        sandbox.update = MethodType(update_after_proof, sandbox)
        sandbox.focus_to(target)
        context = adapter.open()._campaign_context
        proof = None if context is None else context.viewport_swipe_proof
        if not isinstance(proof, CampaignMapViewportSwipeProof):
            raise SemanticGateClosed("ALAS focus_to returned without viewport proof")
        proofs.append(proof)
        raise ScriptEnd("Semantic ALAS viewport swipe validation complete")

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
            if str(exc) != "Semantic ALAS viewport swipe validation complete":
                raise
    finally:
        os.chdir(str(previous_cwd))
        alas_headless.preview_alas_campaign_goto_input = original_preview
        AlasSemanticSession.from_environment = original_factory
        try:
            session.close()
        except ObserverTransportError:
            pass

    if len(proofs) != 1 or len(camera_records) != 1:
        raise SystemExit("pinned ALAS did not prove exactly one viewport swipe")
    record = proof_to_json(proofs[0], pid=session.bridge.pid or 0)
    record["alas_camera_request"] = camera_records[0]
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
