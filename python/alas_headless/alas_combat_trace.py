"""Read-only raw observer traces for qualifying ALAS combat inputs.

The trace contains no trusted phase labels and performs no input.  Reviewers
select one bounded 6-10 generation sequence only after capture; the compiler
derives the two map projections from those frozen raw endpoint payloads and
emits G20's hash-bound fixture format.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .alas_combat_observer import (
    ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA,
    AlasCombatObserverManifest,
    AlasCombatObserverSnapshot,
    canonical_alas_combat_observer_frame_sha256,
    parse_alas_combat_observer_fixture_frame,
)
from .alas_combat_state_replay import (
    ALAS_COMBAT_REPLAY_PHASES,
    ALAS_COMBAT_REPLAY_PHASE_SEQUENCES,
    AlasCombatReplayPhase,
)
from .semantic_oracle import (
    CampaignMapState,
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
)


ALAS_COMBAT_OBSERVER_TRACE_SCHEMA = "alas-headless.g21-combat-observer-trace/v1"
ALAS_COMBAT_OBSERVER_CANDIDATE_SCHEMA = (
    "alas-headless.g21-combat-observer-candidates/v1"
)
_UTC_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z"
)


@dataclass(frozen=True)
class AlasCombatObserverTraceSample:
    sequence: int
    captured_at_utc: str
    frame: Mapping[str, Any]
    snapshot: AlasCombatObserverSnapshot


@dataclass(frozen=True)
class AlasCombatObserverTrace:
    package: str
    driver_revision: str
    game_fingerprint: str
    pid: int
    samples: Tuple[AlasCombatObserverTraceSample, ...]

    @property
    def generations(self) -> Tuple[int, ...]:
        return tuple(sample.snapshot.generation for sample in self.samples)


def build_alas_combat_trace_frame(
    snapshot_payload: Mapping[str, Any],
    button_payload: Mapping[str, Any],
    ui_payload: Mapping[str, Any],
    manifest: AlasCombatObserverManifest,
) -> Tuple[Mapping[str, Any], AlasCombatObserverSnapshot]:
    """Validate and hash one coherent, raw, input-free endpoint triple."""

    payload = {
        "snapshot": snapshot_payload,
        "buttons": button_payload,
        "ui": ui_payload,
        "campaign_map": None,
    }
    frame = {
        **payload,
        "sha256": canonical_alas_combat_observer_frame_sha256(payload),
    }
    typed = parse_alas_combat_observer_fixture_frame(frame, manifest)
    return frame, typed


def build_alas_combat_observer_trace(
    manifest: AlasCombatObserverManifest,
    samples: Sequence[Tuple[str, Mapping[str, Any]]],
) -> Mapping[str, Any]:
    """Build the durable trace document from already validated raw frames."""

    if not samples:
        raise SemanticGateClosed("combat observer trace has no samples")
    output = []
    previous = -1
    pid = None
    for sequence, (captured_at_utc, frame) in enumerate(samples, start=1):
        if _UTC_PATTERN.fullmatch(captured_at_utc) is None:
            raise SemanticGateClosed("combat observer trace timestamp is malformed")
        typed = parse_alas_combat_observer_fixture_frame(frame, manifest)
        if typed.campaign_map is not None:
            raise SemanticGateClosed("raw combat trace must not contain a map projection")
        if typed.generation <= previous:
            raise SemanticGateClosed("combat observer trace generations are not increasing")
        previous = typed.generation
        frame_pid = typed.oracle_state.snapshot.get("pid")
        if isinstance(frame_pid, bool) or not isinstance(frame_pid, int):
            raise SemanticGateClosed("combat observer trace PID is malformed")
        if pid is None:
            pid = frame_pid
        elif pid != frame_pid:
            raise SemanticGateClosed("combat observer trace PID changed")
        output.append(
            {
                "sequence": sequence,
                "captured_at_utc": captured_at_utc,
                "frame": frame,
            }
        )
    assert pid is not None
    return {
        "schema": ALAS_COMBAT_OBSERVER_TRACE_SCHEMA,
        "package": manifest.package,
        "driver_revision": manifest.driver_revision,
        "game_fingerprint": manifest.game_fingerprint,
        "pid": pid,
        "input_injected": False,
        "samples": output,
    }


def parse_alas_combat_observer_trace(
    value: Any,
    manifest: AlasCombatObserverManifest,
) -> AlasCombatObserverTrace:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "package",
        "driver_revision",
        "game_fingerprint",
        "pid",
        "input_injected",
        "samples",
    }:
        raise SemanticGateClosed("combat observer trace schema changed")
    if value["schema"] != ALAS_COMBAT_OBSERVER_TRACE_SCHEMA:
        raise SemanticGateClosed("combat observer trace version changed")
    if value["input_injected"] is not False:
        raise SemanticGateClosed("combat observer trace is not read-only")
    if (
        value["package"] != manifest.package
        or value["driver_revision"] != manifest.driver_revision
        or value["game_fingerprint"] != manifest.game_fingerprint
    ):
        raise SemanticGateClosed("combat observer trace identity changed")
    pid = value["pid"]
    if isinstance(pid, bool) or not isinstance(pid, int):
        raise SemanticGateClosed("combat observer trace PID is malformed")
    raw_samples = value["samples"]
    if not isinstance(raw_samples, list) or not raw_samples:
        raise SemanticGateClosed("combat observer trace samples are malformed")
    parsed = []
    previous = -1
    for expected_sequence, raw in enumerate(raw_samples, start=1):
        if not isinstance(raw, dict) or set(raw) != {
            "sequence",
            "captured_at_utc",
            "frame",
        }:
            raise SemanticGateClosed("combat observer trace sample schema changed")
        if raw["sequence"] != expected_sequence:
            raise SemanticGateClosed("combat observer trace sequence changed")
        captured = raw["captured_at_utc"]
        if not isinstance(captured, str) or _UTC_PATTERN.fullmatch(captured) is None:
            raise SemanticGateClosed("combat observer trace timestamp is malformed")
        frame = raw["frame"]
        if not isinstance(frame, dict) or "phase" in frame:
            raise SemanticGateClosed("combat observer trace frame is malformed")
        typed = parse_alas_combat_observer_fixture_frame(frame, manifest)
        if typed.campaign_map is not None:
            raise SemanticGateClosed("raw combat trace contains a map projection")
        if typed.oracle_state.snapshot.get("pid") != pid:
            raise SemanticGateClosed("combat observer trace endpoint PID changed")
        if typed.generation <= previous:
            raise SemanticGateClosed("combat observer trace generations are not increasing")
        previous = typed.generation
        parsed.append(
            AlasCombatObserverTraceSample(
                sequence=expected_sequence,
                captured_at_utc=captured,
                frame=frame,
                snapshot=typed,
            )
        )
    return AlasCombatObserverTrace(
        package=value["package"],
        driver_revision=value["driver_revision"],
        game_fingerprint=value["game_fingerprint"],
        pid=pid,
        samples=tuple(parsed),
    )


def load_alas_combat_observer_trace(
    path: Path,
    manifest: AlasCombatObserverManifest,
) -> AlasCombatObserverTrace:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticGateClosed("combat observer trace cannot be read") from exc
    return parse_alas_combat_observer_trace(value, manifest)


def merge_alas_combat_observer_traces(
    traces: Sequence[AlasCombatObserverTrace],
) -> AlasCombatObserverTrace:
    """Join adjacent read-only captures without weakening identity checks."""

    if not traces or any(
        not isinstance(trace, AlasCombatObserverTrace) for trace in traces
    ):
        raise SemanticGateClosed("combat observer trace merge input is malformed")
    first = traces[0]
    identity = (
        first.package,
        first.driver_revision,
        first.game_fingerprint,
        first.pid,
    )
    if any(
        (
            trace.package,
            trace.driver_revision,
            trace.game_fingerprint,
            trace.pid,
        )
        != identity
        for trace in traces[1:]
    ):
        raise SemanticGateClosed("combat observer trace merge identity changed")
    flattened = tuple(sample for trace in traces for sample in trace.samples)
    generations = tuple(sample.snapshot.generation for sample in flattened)
    if any(right <= left for left, right in zip(generations, generations[1:])):
        raise SemanticGateClosed(
            "combat observer trace merge generations are not increasing"
        )
    samples = tuple(
        AlasCombatObserverTraceSample(
            sequence=index,
            captured_at_utc=sample.captured_at_utc,
            frame=sample.frame,
            snapshot=sample.snapshot,
        )
        for index, sample in enumerate(flattened, start=1)
    )
    return AlasCombatObserverTrace(
        package=first.package,
        driver_revision=first.driver_revision,
        game_fingerprint=first.game_fingerprint,
        pid=first.pid,
        samples=samples,
    )


def select_alas_combat_observer_trace_samples(
    trace: AlasCombatObserverTrace,
    generations: Sequence[int],
) -> Tuple[AlasCombatObserverTraceSample, ...]:
    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("combat observer trace is not typed")
    if (
        len(generations) not in {len(item) for item in ALAS_COMBAT_REPLAY_PHASE_SEQUENCES}
        or any(isinstance(item, bool) or not isinstance(item, int) for item in generations)
        or any(right <= left for left, right in zip(generations, generations[1:]))
    ):
        raise SemanticGateClosed("combat observer selection requires 6 to 10 generations")
    indexed = {sample.snapshot.generation: sample for sample in trace.samples}
    if len(indexed) != len(trace.samples):
        raise SemanticGateClosed("combat observer trace generations are ambiguous")
    try:
        return tuple(indexed[generation] for generation in generations)
    except KeyError as exc:
        raise SemanticGateClosed("selected combat generation is absent") from exc


def _active_records(snapshot: AlasCombatObserverSnapshot) -> Tuple[Mapping[str, Any], ...]:
    records = []
    for button in snapshot.oracle_state.buttons:
        if button.active_in_hierarchy and button.active_and_enabled:
            records.append(
                {
                    "kind": "button",
                    "path": button.path,
                    "name": button.name,
                    "value": "",
                    "actionable": button.actionable,
                }
            )
    for toggle in snapshot.ui_state.toggles:
        if toggle.active_in_hierarchy and toggle.active_and_enabled:
            records.append(
                {
                    "kind": "toggle_on" if toggle.checked else "toggle_off",
                    "path": toggle.path,
                    "name": toggle.name,
                    "value": "true" if toggle.checked else "false",
                    "actionable": toggle.actionable,
                }
            )
    for image in snapshot.ui_state.images:
        if image.active_in_hierarchy and image.active_and_enabled and not image.truncated:
            records.append(
                {
                    "kind": "image",
                    "path": image.path,
                    "name": image.name,
                    "value": image.sprite,
                    "actionable": False,
                }
            )
    for text in snapshot.ui_state.texts:
        if text.active_in_hierarchy and text.active_and_enabled and not text.truncated:
            records.append(
                {
                    "kind": "text",
                    "path": text.path,
                    "name": text.name,
                    "value": text.text,
                    "actionable": False,
                }
            )
    return tuple(
        sorted(
            records,
            key=lambda item: (item["kind"], item["path"], item["name"], item["value"]),
        )
    )


def _validate_selected_samples(
    selected: Sequence[AlasCombatObserverTraceSample],
    phase_sequence: Sequence[AlasCombatReplayPhase],
) -> None:
    phases = tuple(phase_sequence)
    if phases not in ALAS_COMBAT_REPLAY_PHASE_SEQUENCES:
        raise SemanticGateClosed("combat trace phase sequence is outside pinned paths")
    if len(selected) != len(phases) or any(
        not isinstance(sample, AlasCombatObserverTraceSample) for sample in selected
    ):
        raise SemanticGateClosed("combat trace selection disagrees with phase sequence")
    generations = tuple(sample.snapshot.generation for sample in selected)
    if any(right <= left for left, right in zip(generations, generations[1:])):
        raise SemanticGateClosed("combat trace selected generations are not increasing")
    pids = tuple(sample.snapshot.oracle_state.snapshot.get("pid") for sample in selected)
    if any(isinstance(pid, bool) or not isinstance(pid, int) for pid in pids):
        raise SemanticGateClosed("combat trace selected PID is malformed")
    if len(set(pids)) != 1:
        raise SemanticGateClosed("combat trace selected PID changed")
    fingerprints = tuple(sample.snapshot.game_fingerprint for sample in selected)
    if len(set(fingerprints)) != 1:
        raise SemanticGateClosed("combat trace selected game fingerprint changed")
    if any(sample.snapshot.campaign_map is not None for sample in selected):
        raise SemanticGateClosed("combat trace selection contains derived map state")


def analyze_alas_combat_observer_candidates(
    selected: Sequence[AlasCombatObserverTraceSample],
    *,
    phase_sequence: Sequence[AlasCombatReplayPhase] = ALAS_COMBAT_REPLAY_PHASES,
) -> Mapping[str, Any]:
    """Emit deterministic phase-local candidates; it never writes mappings."""

    phases_expected = tuple(phase_sequence)
    _validate_selected_samples(selected, phases_expected)
    active = tuple(_active_records(sample.snapshot) for sample in selected)
    keys = tuple(
        {
            (item["kind"], item["path"], item["name"], item["value"])
            for item in records
        }
        for records in active
    )
    phases = []
    for index, (phase, sample, records) in enumerate(
        zip(phases_expected, selected, active)
    ):
        other = set().union(
            *(
                keys[position]
                for position in range(len(keys))
                if position != index
            )
        )
        unique = [
            item
            for item in records
            if (item["kind"], item["path"], item["name"], item["value"])
            not in other
        ]
        phases.append(
            {
                "phase": phase.value,
                "generation": sample.snapshot.generation,
                "capture_sha256": sample.snapshot.capture_sha256,
                "record_count": len(records),
                "phase_unique_records": unique,
                "actionable_buttons": [
                    item for item in records if item["kind"] == "button" and item["actionable"]
                ],
            }
        )
    searching_index = phases_expected.index(AlasCombatReplayPhase.MAP_SEARCHING)
    stable_index = phases_expected.index(AlasCombatReplayPhase.MAP_STABLE)
    map_common = keys[searching_index] & keys[stable_index]
    return {
        "schema": ALAS_COMBAT_OBSERVER_CANDIDATE_SCHEMA,
        "input_injected": False,
        "generations": [sample.snapshot.generation for sample in selected],
        "phases": phases,
        "map_phase_common_records": [
            {
                "kind": kind,
                "path": path,
                "name": name,
                "value": value,
            }
            for kind, path, name, value in sorted(map_common)
        ],
    }


def _offline_campaign_map(
    frame: Mapping[str, Any],
    manifest: AlasCombatObserverManifest,
    *,
    stage_code: str,
    columns: int,
    rows: int,
    land_cells: Sequence[Tuple[int, int]],
    expected_fleet_count: int,
) -> CampaignMapState:
    payloads = {
        "GET /v1/snapshot\n": frame["snapshot"],
        "GET /v1/buttons\n": frame["buttons"],
        "GET /v1/state\n": {
            "protocol_schema": "alas-headless.observer/v1",
            "status": "ok",
            "snapshot": frame["snapshot"],
            "buttons": frame["buttons"],
        },
        "GET /v1/ui\n": frame["ui"],
    }
    oracle = SemanticOracle(
        request=lambda request: payloads[request],
        foreground_component=lambda: manifest.package + "/fixture",
        tap=lambda x, y: (_ for _ in ()).throw(
            SemanticGateClosed("offline combat fixture attempted input")
        ),
        fingerprint=OracleFingerprint(
            package=manifest.package,
            component=manifest.package + "/fixture",
            driver_revision=manifest.driver_revision,
            expected_pid=frame["snapshot"].get("pid"),
        ),
    )
    normalized_land = tuple(
        sorted((row0 + 1, column0 + 1) for column0, row0 in land_cells)
    )
    return oracle._campaign_map_state_once(
        stage_code,
        columns=columns,
        rows=rows,
        land=normalized_land,
        expected_fleet_count=expected_fleet_count,
    )


def _serialize_campaign_map(state: CampaignMapState) -> Mapping[str, Any]:
    return {
        "generation": state.generation,
        "stage_code": state.stage_code,
        "rows": state.rows,
        "columns": state.columns,
        "cells": [
            {
                "row": cell.row,
                "column": cell.column,
                "node": cell.node,
                "button_path": cell.button_path,
                "point": {"x": cell.point.x, "y": cell.point.y},
                "bounds": {
                    "left": cell.bounds.left,
                    "top": cell.bounds.top,
                    "right": cell.bounds.right,
                    "bottom": cell.bounds.bottom,
                },
            }
            for cell in state.cells
        ],
        "land_nodes": list(state.land_nodes),
        "fleets": [
            {
                "marker": fleet.marker,
                "node": fleet.node,
                "ammo": fleet.ammo,
                "ammo_capacity": fleet.ammo_capacity,
            }
            for fleet in state.fleets
        ],
        "enemies": [
            {
                "row": enemy.row,
                "column": enemy.column,
                "node": enemy.node,
                "object_id": enemy.object_id,
                "sprite": enemy.sprite,
                "scale": enemy.scale,
                "genre": enemy.genre,
                "level": enemy.level,
                "fighting": enemy.fighting,
            }
            for enemy in state.enemies
        ],
        "pickups": [
            {
                "row": pickup.row,
                "column": pickup.column,
                "node": pickup.node,
                "kind": pickup.kind,
                "sprite": pickup.sprite,
            }
            for pickup in state.pickups
        ],
        "displayed_fleet_index": state.displayed_fleet_index,
        "current_fleet_marker": state.current_fleet_marker,
        "current_fleet_roster_sprites": list(state.current_fleet_roster_sprites),
    }


def compile_alas_combat_observer_fixture(
    selected: Sequence[AlasCombatObserverTraceSample],
    manifest: AlasCombatObserverManifest,
    *,
    stage_code: str,
    columns: int,
    rows: int,
    land_cells: Sequence[Tuple[int, int]],
    expected_fleet_count: int,
    phase_sequence: Sequence[AlasCombatReplayPhase] = ALAS_COMBAT_REPLAY_PHASES,
) -> Mapping[str, Any]:
    """Compile one bounded raw sequence into G20's phase-label-free fixture."""

    phases_expected = tuple(phase_sequence)
    _validate_selected_samples(selected, phases_expected)
    if any(
        sample.snapshot.game_fingerprint != manifest.game_fingerprint
        for sample in selected
    ):
        raise SemanticGateClosed("combat fixture selection disagrees with manifest")
    frames = []
    for phase, sample in zip(phases_expected, selected):
        raw = sample.frame
        campaign_map = None
        if phase in (
            AlasCombatReplayPhase.MAP_SEARCHING,
            AlasCombatReplayPhase.MAP_STABLE,
        ):
            campaign_map = _serialize_campaign_map(
                _offline_campaign_map(
                    raw,
                    manifest,
                    stage_code=stage_code,
                    columns=columns,
                    rows=rows,
                    land_cells=land_cells,
                    expected_fleet_count=expected_fleet_count,
                )
            )
        payload = {
            "snapshot": raw["snapshot"],
            "buttons": raw["buttons"],
            "ui": raw["ui"],
            "campaign_map": campaign_map,
        }
        frame = {
            **payload,
            "sha256": canonical_alas_combat_observer_frame_sha256(payload),
        }
        parse_alas_combat_observer_fixture_frame(frame, manifest)
        frames.append(frame)
    return {
        "schema": ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA,
        "game_fingerprint": manifest.game_fingerprint,
        "frames": frames,
    }
