"""Exact Unity-observer input contract for ALAS campaign combat replay.

G19 qualified ALAS's original state machine with synthetic phase frames.  This
module is the boundary that may replace those frames: every ALAS presence
query must have a reviewed exact Unity selector, every observer slice must be
complete and hash-bound, and the bounded phases are inferred from records
rather than accepted as fixture labels. G25 adds automation switching, radar
search, and ordered fleet statistics while the incomplete defensive-resource
and blocker surface remains fail-closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .alas_combat_admission import AlasCampaignCombatAdmission
from .alas_combat_state_replay import (
    ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES,
    ALAS_COMBAT_REPLAY_PHASE_SEQUENCES,
    ALAS_COMBAT_REPLAY_RESOURCE_NAMES,
    AlasCampaignCombatReplay,
    AlasCombatReplayFrame,
    AlasCombatReplayPhase,
)
from .semantic_oracle import (
    ActionReceipt,
    BUTTON_SCHEMA,
    OBSERVER_SCHEMA,
    UI_SCHEMA,
    Bounds,
    ButtonState,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapPickupState,
    CampaignMapState,
    ImageState,
    OracleFingerprint,
    OracleState,
    Point,
    SemanticGateClosed,
    SemanticOracle,
    TextState,
    ToggleState,
    UiState,
)


ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA = (
    "alas-headless.g20-combat-observer-fixture/v1"
)
ALAS_COMBAT_OBSERVER_MANIFEST_SCHEMA = (
    "alas-headless.g22-combat-observer-manifest/v1"
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_ACTION_RESOURCES = frozenset(
    {
        "AUTOMATION_CONFIRM",
        "AUTOMATION_OFF",
        "BATTLE_PREPARATION",
        "BATTLE_STATUS_S",
        "EXP_INFO_S",
        "GET_ITEMS_1",
        "GET_MISSION",
    }
)
_ACTION_PRECEDENCE_ALLOWLIST = {
    "AUTOMATION_OFF": frozenset({"BATTLE_PREPARATION"}),
}


class AlasCombatUnityRecordKind(str, Enum):
    BUTTON = "button"
    IMAGE = "image"
    TEXT = "text"
    TOGGLE_OFF = "toggle_off"
    TOGGLE_ON = "toggle_on"


@dataclass(frozen=True)
class AlasCombatUnitySelector:
    """One exact record identity; no suffix, regex, OCR, or coordinate match."""

    kind: AlasCombatUnityRecordKind
    path: str
    name: str
    sprite: str = ""
    text: str = ""
    require_top_raycast: bool = False
    ordinal: Optional[int] = None
    width_scale: Optional[float] = None


@dataclass(frozen=True)
class AlasCombatResourceMapping:
    resource_name: str
    selectors: Tuple[AlasCombatUnitySelector, ...] = ()
    evidence_sha256: str = ""

    @property
    def qualified(self) -> bool:
        return bool(self.selectors) and _is_sha256(self.evidence_sha256)


@dataclass(frozen=True)
class AlasCombatBlockerMapping:
    """One reviewed blocking condition expressed as an exact all-of rule."""

    blocker_name: str
    selectors: Tuple[AlasCombatUnitySelector, ...] = ()
    evidence_sha256: str = ""

    @property
    def qualified(self) -> bool:
        return bool(self.selectors) and _is_sha256(self.evidence_sha256)


@dataclass(frozen=True)
class AlasCombatFleetStatsMapping:
    hp_images: Tuple[AlasCombatUnitySelector, ...] = ()
    level_texts: Tuple[AlasCombatUnitySelector, ...] = ()
    evidence_sha256: str = ""

    @property
    def qualified(self) -> bool:
        return (
            len(self.hp_images) == 6
            and len(self.level_texts) == 6
            and _is_sha256(self.evidence_sha256)
        )


@dataclass(frozen=True)
class AlasCombatObserverManifest:
    package: str
    driver_revision: str
    game_fingerprint: str
    resources: Tuple[AlasCombatResourceMapping, ...]
    blockers: Tuple[AlasCombatBlockerMapping, ...] = ()
    blocker_review_complete: bool = False
    fleet_stats: AlasCombatFleetStatsMapping = AlasCombatFleetStatsMapping()


@dataclass(frozen=True)
class AlasCombatObserverCoverage:
    total_resources: int
    qualified_resources: int
    unqualified_resources: Tuple[str, ...]
    total_blockers: int
    qualified_blockers: int
    blocker_review_complete: bool
    blockers_qualified: bool
    fleet_stats_qualified: bool

    @property
    def production_ready(self) -> bool:
        return (
            self.qualified_resources == self.total_resources
            and self.blockers_qualified
            and self.fleet_stats_qualified
        )


@dataclass(frozen=True)
class AlasCombatObserverSnapshot:
    """One complete, coherent observer generation without a trusted phase."""

    capture_sha256: str
    game_fingerprint: str
    oracle_state: OracleState
    ui_state: UiState
    campaign_map: Optional[CampaignMapState] = None

    @property
    def generation(self) -> int:
        values = [self.oracle_state.generation, self.ui_state.generation]
        if self.campaign_map is not None:
            values.append(self.campaign_map.generation)
        return max(values)


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def unqualified_alas_combat_observer_manifest(
    *,
    package: str = "com.bilibili.azurlane",
    driver_revision: str = "UNQUALIFIED",
    game_fingerprint: str = "UNQUALIFIED",
) -> AlasCombatObserverManifest:
    """Return an honest checked-in combat mapping coverage baseline."""

    return AlasCombatObserverManifest(
        package=package,
        driver_revision=driver_revision,
        game_fingerprint=game_fingerprint,
        resources=tuple(
            AlasCombatResourceMapping(name)
            for name in ALAS_COMBAT_REPLAY_RESOURCE_NAMES
        ),
    )


def _selector_from_json(value: Any) -> AlasCombatUnitySelector:
    required = {
        "kind",
        "path",
        "name",
        "sprite",
        "text",
        "require_top_raycast",
    }
    optional = {"ordinal", "width_scale"}
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or not set(value).issubset(required | optional)
    ):
        raise SemanticGateClosed("combat manifest selector schema changed")
    try:
        kind = AlasCombatUnityRecordKind(value["kind"])
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed("combat manifest selector kind changed") from exc
    selector = AlasCombatUnitySelector(
        kind=kind,
        path=value["path"] if isinstance(value["path"], str) else "",
        name=value["name"] if isinstance(value["name"], str) else "",
        sprite=value["sprite"] if isinstance(value["sprite"], str) else "",
        text=value["text"] if isinstance(value["text"], str) else "",
        require_top_raycast=value["require_top_raycast"]
        if isinstance(value["require_top_raycast"], bool)
        else False,
        ordinal=value.get("ordinal")
        if isinstance(value.get("ordinal"), int)
        and not isinstance(value.get("ordinal"), bool)
        else None,
        width_scale=float(value["width_scale"])
        if isinstance(value.get("width_scale"), (int, float))
        and not isinstance(value.get("width_scale"), bool)
        else None,
    )
    if not isinstance(value["require_top_raycast"], bool):
        raise SemanticGateClosed("combat manifest selector raycast flag changed")
    if "ordinal" in value and selector.ordinal is None:
        raise SemanticGateClosed("combat manifest selector ordinal changed")
    if "width_scale" in value and selector.width_scale is None:
        raise SemanticGateClosed("combat manifest selector width scale changed")
    return selector


def parse_alas_combat_unity_selector(
    value: Any, *, allow_dynamic_text: bool = False
) -> AlasCombatUnitySelector:
    selector = _selector_from_json(value)
    _validate_selector(selector, allow_dynamic_text=allow_dynamic_text)
    return selector


def _mapping_from_json(value: Any) -> AlasCombatResourceMapping:
    if not isinstance(value, dict) or set(value) != {
        "resource_name",
        "selectors",
        "evidence_sha256",
    }:
        raise SemanticGateClosed("combat manifest resource schema changed")
    selectors = value["selectors"]
    if not isinstance(selectors, list):
        raise SemanticGateClosed("combat manifest resource selectors are malformed")
    return AlasCombatResourceMapping(
        resource_name=value["resource_name"]
        if isinstance(value["resource_name"], str)
        else "",
        selectors=tuple(_selector_from_json(item) for item in selectors),
        evidence_sha256=value["evidence_sha256"]
        if isinstance(value["evidence_sha256"], str)
        else "",
    )


def _blocker_from_json(value: Any) -> AlasCombatBlockerMapping:
    if not isinstance(value, dict) or set(value) != {
        "blocker_name",
        "selectors",
        "evidence_sha256",
    }:
        raise SemanticGateClosed("combat manifest blocker schema changed")
    selectors = value["selectors"]
    if not isinstance(selectors, list):
        raise SemanticGateClosed("combat manifest blocker selectors are malformed")
    return AlasCombatBlockerMapping(
        blocker_name=(
            value["blocker_name"] if isinstance(value["blocker_name"], str) else ""
        ),
        selectors=tuple(_selector_from_json(item) for item in selectors),
        evidence_sha256=(
            value["evidence_sha256"]
            if isinstance(value["evidence_sha256"], str)
            else ""
        ),
    )


def load_alas_combat_observer_manifest(
    path: Path,
) -> AlasCombatObserverManifest:
    """Load the one strict, versioned resource-to-Unity mapping document."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticGateClosed("combat observer manifest cannot be read") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "package",
        "driver_revision",
        "game_fingerprint",
        "resources",
        "blockers",
        "blocker_review_complete",
        "fleet_stats",
    }:
        raise SemanticGateClosed("combat observer manifest schema changed")
    if value["schema"] != ALAS_COMBAT_OBSERVER_MANIFEST_SCHEMA:
        raise SemanticGateClosed("combat observer manifest version changed")
    if not all(
        isinstance(value[field], str)
        for field in (
            "package",
            "driver_revision",
            "game_fingerprint",
        )
    ):
        raise SemanticGateClosed("combat observer manifest identity is malformed")
    if not isinstance(value["blocker_review_complete"], bool):
        raise SemanticGateClosed("combat blocker review flag is malformed")
    resources = value["resources"]
    blockers = value["blockers"]
    stats = value["fleet_stats"]
    if not isinstance(resources, list) or not isinstance(blockers, list):
        raise SemanticGateClosed("combat observer manifest lists are malformed")
    if not isinstance(stats, dict) or set(stats) != {
        "hp_images",
        "level_texts",
        "evidence_sha256",
    }:
        raise SemanticGateClosed("combat observer fleet stats schema changed")
    if (
        not isinstance(stats["hp_images"], list)
        or not isinstance(stats["level_texts"], list)
        or not isinstance(stats["evidence_sha256"], str)
    ):
        raise SemanticGateClosed("combat observer fleet stats are malformed")
    manifest = AlasCombatObserverManifest(
        package=value["package"],
        driver_revision=value["driver_revision"],
        game_fingerprint=value["game_fingerprint"],
        resources=tuple(_mapping_from_json(item) for item in resources),
        blockers=tuple(_blocker_from_json(item) for item in blockers),
        blocker_review_complete=value["blocker_review_complete"],
        fleet_stats=AlasCombatFleetStatsMapping(
            hp_images=tuple(_selector_from_json(item) for item in stats["hp_images"]),
            level_texts=tuple(
                _selector_from_json(item) for item in stats["level_texts"]
            ),
            evidence_sha256=stats["evidence_sha256"],
        ),
    )
    audit_alas_combat_observer_manifest(manifest)
    return manifest


def alas_combat_unity_selector_to_json(
    selector: AlasCombatUnitySelector,
    *,
    allow_dynamic_text: bool = False,
) -> Mapping[str, Any]:
    _validate_selector(selector, allow_dynamic_text=allow_dynamic_text)
    value = {
        "kind": selector.kind.value,
        "path": selector.path,
        "name": selector.name,
        "sprite": selector.sprite,
        "text": selector.text,
        "require_top_raycast": selector.require_top_raycast,
    }
    if selector.ordinal is not None:
        value["ordinal"] = selector.ordinal
    if selector.width_scale is not None:
        value["width_scale"] = selector.width_scale
    return value


def alas_combat_observer_manifest_to_json(
    manifest: AlasCombatObserverManifest,
) -> Mapping[str, Any]:
    """Serialize only the strict checked-in manifest surface."""

    audit_alas_combat_observer_manifest(manifest)

    def selectors(items: Sequence[AlasCombatUnitySelector]) -> list[Mapping[str, Any]]:
        return [alas_combat_unity_selector_to_json(item) for item in items]

    return {
        "schema": ALAS_COMBAT_OBSERVER_MANIFEST_SCHEMA,
        "package": manifest.package,
        "driver_revision": manifest.driver_revision,
        "game_fingerprint": manifest.game_fingerprint,
        "resources": [
            {
                "resource_name": mapping.resource_name,
                "selectors": selectors(mapping.selectors),
                "evidence_sha256": mapping.evidence_sha256,
            }
            for mapping in manifest.resources
        ],
        "blockers": [
            {
                "blocker_name": mapping.blocker_name,
                "selectors": selectors(mapping.selectors),
                "evidence_sha256": mapping.evidence_sha256,
            }
            for mapping in manifest.blockers
        ],
        "blocker_review_complete": manifest.blocker_review_complete,
        "fleet_stats": {
            "hp_images": selectors(manifest.fleet_stats.hp_images),
            "level_texts": [
                alas_combat_unity_selector_to_json(item, allow_dynamic_text=True)
                for item in manifest.fleet_stats.level_texts
            ],
            "evidence_sha256": manifest.fleet_stats.evidence_sha256,
        },
    }


def audit_alas_combat_observer_manifest(
    manifest: AlasCombatObserverManifest,
) -> AlasCombatObserverCoverage:
    if not isinstance(manifest, AlasCombatObserverManifest):
        raise SemanticGateClosed("combat observer manifest is not typed")
    if not manifest.package or not manifest.driver_revision or not manifest.game_fingerprint:
        raise SemanticGateClosed("combat observer manifest identity is incomplete")
    names = tuple(mapping.resource_name for mapping in manifest.resources)
    if len(names) != len(set(names)):
        raise SemanticGateClosed("combat observer manifest has duplicate resources")
    if set(names) != set(ALAS_COMBAT_REPLAY_RESOURCE_NAMES):
        raise SemanticGateClosed("combat observer resource surface changed")
    for mapping in manifest.resources:
        _validate_mapping_shape(mapping)
    blocker_names = tuple(mapping.blocker_name for mapping in manifest.blockers)
    if len(blocker_names) != len(set(blocker_names)):
        raise SemanticGateClosed("combat observer manifest has duplicate blockers")
    for mapping in manifest.blockers:
        _validate_blocker_shape(mapping)
    _validate_stats_shape(manifest.fleet_stats)
    unqualified = tuple(
        sorted(
            mapping.resource_name
            for mapping in manifest.resources
            if not mapping.qualified
        )
    )
    qualified_blockers = sum(mapping.qualified for mapping in manifest.blockers)
    blockers_qualified = (
        manifest.blocker_review_complete
        and bool(manifest.blockers)
        and qualified_blockers == len(manifest.blockers)
    )
    return AlasCombatObserverCoverage(
        total_resources=len(ALAS_COMBAT_REPLAY_RESOURCE_NAMES),
        qualified_resources=len(ALAS_COMBAT_REPLAY_RESOURCE_NAMES)
        - len(unqualified),
        unqualified_resources=unqualified,
        total_blockers=len(manifest.blockers),
        qualified_blockers=qualified_blockers,
        blocker_review_complete=manifest.blocker_review_complete,
        blockers_qualified=blockers_qualified,
        fleet_stats_qualified=manifest.fleet_stats.qualified,
    )


def _validate_selector(
    selector: AlasCombatUnitySelector, *, allow_dynamic_text: bool = False
) -> None:
    if not isinstance(selector, AlasCombatUnitySelector):
        raise SemanticGateClosed("combat Unity selector is not typed")
    if (
        not selector.path
        or not selector.name
        or "/" not in selector.path
        or selector.path.startswith("*")
    ):
        raise SemanticGateClosed("combat Unity selector identity is incomplete")
    if "*" in selector.path or selector.path.endswith("/"):
        raise SemanticGateClosed("combat Unity selector path is not exact")
    if selector.ordinal is not None and (
        isinstance(selector.ordinal, bool)
        or not isinstance(selector.ordinal, int)
        or not 0 <= selector.ordinal <= 15
        or selector.kind
        not in (AlasCombatUnityRecordKind.IMAGE, AlasCombatUnityRecordKind.TEXT)
    ):
        raise SemanticGateClosed("combat Unity selector ordinal is invalid")
    if selector.width_scale is not None and (
        isinstance(selector.width_scale, bool)
        or not isinstance(selector.width_scale, (int, float))
        or not 0.0 < float(selector.width_scale) < 4096.0
        or selector.kind is not AlasCombatUnityRecordKind.IMAGE
    ):
        raise SemanticGateClosed("combat Unity selector width scale is invalid")
    if selector.kind is AlasCombatUnityRecordKind.IMAGE:
        if not selector.sprite or selector.text:
            raise SemanticGateClosed("combat image selector is incomplete")
    elif selector.kind is AlasCombatUnityRecordKind.TEXT:
        if (
            (not selector.text and not allow_dynamic_text)
            or selector.sprite
            or selector.require_top_raycast
        ):
            raise SemanticGateClosed("combat text selector is incomplete")
    elif selector.kind is AlasCombatUnityRecordKind.BUTTON:
        if selector.sprite or selector.text or selector.width_scale is not None:
            raise SemanticGateClosed("combat button selector is malformed")
    elif selector.kind in (
        AlasCombatUnityRecordKind.TOGGLE_OFF,
        AlasCombatUnityRecordKind.TOGGLE_ON,
    ):
        if selector.sprite or selector.text or selector.width_scale is not None:
            raise SemanticGateClosed("combat Toggle selector is malformed")
    else:
        raise SemanticGateClosed("combat Unity selector kind is unsupported")


def _validate_mapping_shape(mapping: AlasCombatResourceMapping) -> None:
    if not isinstance(mapping, AlasCombatResourceMapping) or not mapping.resource_name:
        raise SemanticGateClosed("combat resource mapping is malformed")
    for selector in mapping.selectors:
        _validate_selector(selector)
    identities = tuple((selector.kind, selector.path) for selector in mapping.selectors)
    if len(identities) != len(set(identities)):
        raise SemanticGateClosed("combat resource mapping has duplicate selectors")
    if mapping.evidence_sha256 and not _is_sha256(mapping.evidence_sha256):
        raise SemanticGateClosed("combat resource evidence hash is malformed")
    if mapping.resource_name in _ACTION_RESOURCES and mapping.qualified:
        if not any(
            selector.kind
            in (
                AlasCombatUnityRecordKind.BUTTON,
                AlasCombatUnityRecordKind.IMAGE,
                AlasCombatUnityRecordKind.TOGGLE_OFF,
                AlasCombatUnityRecordKind.TOGGLE_ON,
            )
            and selector.require_top_raycast
            for selector in mapping.selectors
        ):
            raise SemanticGateClosed(
                "combat action mapping lacks an exact top-raycast control"
            )


def _validate_blocker_shape(mapping: AlasCombatBlockerMapping) -> None:
    if not isinstance(mapping, AlasCombatBlockerMapping) or not mapping.blocker_name:
        raise SemanticGateClosed("combat blocker mapping is malformed")
    if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", mapping.blocker_name) is None:
        raise SemanticGateClosed("combat blocker name is malformed")
    for selector in mapping.selectors:
        _validate_selector(selector)
    identities = tuple((selector.kind, selector.path) for selector in mapping.selectors)
    if len(identities) != len(set(identities)):
        raise SemanticGateClosed("combat blocker mapping has duplicate selectors")
    if mapping.evidence_sha256 and not _is_sha256(mapping.evidence_sha256):
        raise SemanticGateClosed("combat blocker evidence hash is malformed")


def _validate_stats_shape(mapping: AlasCombatFleetStatsMapping) -> None:
    if not isinstance(mapping, AlasCombatFleetStatsMapping):
        raise SemanticGateClosed("combat fleet stats mapping is not typed")
    for selector in mapping.hp_images:
        _validate_selector(selector)
        if selector.kind is not AlasCombatUnityRecordKind.IMAGE:
            raise SemanticGateClosed("combat HP mapping is not an Image")
    for selector in mapping.level_texts:
        _validate_selector(selector, allow_dynamic_text=True)
        if selector.kind is not AlasCombatUnityRecordKind.TEXT:
            raise SemanticGateClosed("combat level mapping is not Text")
    selectors = mapping.hp_images + mapping.level_texts
    identities = tuple(
        (selector.kind, selector.path, selector.ordinal) for selector in selectors
    )
    if len(identities) != len(set(identities)):
        raise SemanticGateClosed("combat fleet stats mapping has duplicate selectors")
    groups: Dict[Tuple[Any, ...], list[AlasCombatUnitySelector]] = {}
    for selector in selectors:
        key = (
            selector.kind,
            selector.path,
            selector.name,
            selector.sprite,
            selector.text,
            selector.width_scale,
        )
        groups.setdefault(key, []).append(selector)
    for group in groups.values():
        ordinals = tuple(sorted(item.ordinal for item in group if item.ordinal is not None))
        if len(group) > 1 and ordinals != tuple(range(len(group))):
            raise SemanticGateClosed(
                "combat fleet stats clone ordinals are incomplete"
            )
        if len(group) == 1 and ordinals:
            raise SemanticGateClosed(
                "combat fleet stats singleton must not use an ordinal"
            )
    if mapping.evidence_sha256 and not _is_sha256(mapping.evidence_sha256):
        raise SemanticGateClosed("combat fleet stats evidence hash is malformed")


def _validate_snapshot(
    snapshot: AlasCombatObserverSnapshot,
    manifest: AlasCombatObserverManifest,
) -> None:
    if not isinstance(snapshot, AlasCombatObserverSnapshot):
        raise SemanticGateClosed("combat observer snapshot is not typed")
    if not _is_sha256(snapshot.capture_sha256):
        raise SemanticGateClosed("combat observer capture hash is malformed")
    if snapshot.game_fingerprint != manifest.game_fingerprint:
        raise SemanticGateClosed("combat observer game fingerprint changed")
    oracle = snapshot.oracle_state
    ui = snapshot.ui_state
    if not isinstance(oracle, OracleState) or not isinstance(ui, UiState):
        raise SemanticGateClosed("combat observer endpoint state is not typed")
    payloads = (oracle.snapshot, oracle.buttons_snapshot, ui.snapshot)
    if any(payload.get("package") != manifest.package for payload in payloads):
        raise SemanticGateClosed("combat observer package changed")
    if any(
        payload.get("driver_revision") != manifest.driver_revision
        for payload in payloads
    ):
        raise SemanticGateClosed("combat observer driver revision changed")
    pids = tuple(payload.get("pid") for payload in payloads)
    if any(isinstance(pid, bool) or not isinstance(pid, int) for pid in pids):
        raise SemanticGateClosed("combat observer PID is malformed")
    if len(set(pids)) != 1:
        raise SemanticGateClosed("combat observer endpoints disagree on PID")
    if oracle.buttons_snapshot.get("truncated") is not False:
        raise SemanticGateClosed("combat Button snapshot is truncated")
    if ui.snapshot.get("toggle_truncated") is not False:
        raise SemanticGateClosed("combat Toggle snapshot is truncated")
    if ui.snapshot.get("text_truncated") is not False:
        raise SemanticGateClosed("combat Text snapshot is truncated")
    if ui.snapshot.get("image_truncated") is not False or ui.image_truncated:
        raise SemanticGateClosed("combat Image snapshot is truncated")
    if oracle.buttons_snapshot.get("error_count") != 0 or ui.snapshot.get(
        "error_count"
    ) != 0:
        raise SemanticGateClosed("combat observer snapshot has extraction errors")
    if ui.method_mask & 0xE != 0xE:
        raise SemanticGateClosed("combat observer typed UI methods are incomplete")
    generations = (oracle.generation, ui.generation)
    if generations[1] < generations[0] - 2 or generations[1] > generations[0] + 2:
        raise SemanticGateClosed("combat observer endpoints are generation-incoherent")
    if snapshot.campaign_map is not None:
        if not isinstance(snapshot.campaign_map, CampaignMapState):
            raise SemanticGateClosed("combat map observation is not typed")
        endpoint_generation = max(oracle.generation, ui.generation)
        if abs(snapshot.campaign_map.generation - endpoint_generation) > 2:
            raise SemanticGateClosed("combat map observation is generation-incoherent")


def validate_alas_combat_observer_snapshot(
    snapshot: AlasCombatObserverSnapshot,
    manifest: AlasCombatObserverManifest,
) -> None:
    """Revalidate a typed snapshot before an evidence-sensitive operation."""

    _validate_snapshot(snapshot, manifest)


def _record_for_selector(
    snapshot: AlasCombatObserverSnapshot,
    selector: AlasCombatUnitySelector,
) -> Optional[Any]:
    if selector.kind is AlasCombatUnityRecordKind.BUTTON:
        records: Iterable[Any] = snapshot.oracle_state.buttons
    elif selector.kind is AlasCombatUnityRecordKind.IMAGE:
        records = snapshot.ui_state.images
    elif selector.kind is AlasCombatUnityRecordKind.TEXT:
        records = snapshot.ui_state.texts
    else:
        records = snapshot.ui_state.toggles
    identities = [record for record in records if record.path == selector.path]
    if not identities:
        return None
    if any(record.name != selector.name for record in identities):
        raise SemanticGateClosed("combat Unity selector name drifted")
    if selector.kind is AlasCombatUnityRecordKind.IMAGE:
        if any(record.truncated for record in identities):
            raise SemanticGateClosed("combat Unity Image identity is truncated")
        if any(record.sprite != selector.sprite for record in identities):
            return None
    elif selector.kind is AlasCombatUnityRecordKind.TEXT:
        if any(record.truncated for record in identities):
            raise SemanticGateClosed("combat Unity Text identity is truncated")
        if selector.text and any(record.text != selector.text for record in identities):
            return None
    elif selector.kind in (
        AlasCombatUnityRecordKind.TOGGLE_OFF,
        AlasCombatUnityRecordKind.TOGGLE_ON,
    ):
        expected_checked = selector.kind is AlasCombatUnityRecordKind.TOGGLE_ON
        if any(
            not isinstance(record, ToggleState)
            or record.checked is not expected_checked
            for record in identities
        ):
            return None
    if selector.ordinal is None:
        if len(identities) > 1:
            raise SemanticGateClosed("combat Unity selector path is ambiguous")
        return identities[0]
    if any(record.bounds is None for record in identities):
        raise SemanticGateClosed("combat Unity selector ordinal lacks bounds")
    ordered = sorted(
        identities,
        key=lambda record: (
            record.bounds.top,
            record.bounds.left,
            record.bounds.bottom,
            record.bounds.right,
        ),
    )
    geometry = tuple(
        (
            record.bounds.top,
            record.bounds.left,
            record.bounds.bottom,
            record.bounds.right,
        )
        for record in ordered
    )
    if len(geometry) != len(set(geometry)):
        raise SemanticGateClosed("combat Unity selector ordinal is ambiguous")
    if selector.ordinal >= len(ordered):
        return None
    record = ordered[selector.ordinal]
    return record


def _selector_present(
    snapshot: AlasCombatObserverSnapshot,
    selector: AlasCombatUnitySelector,
) -> bool:
    record = _record_for_selector(snapshot, selector)
    if record is None:
        return False
    if not record.active_in_hierarchy or not record.active_and_enabled:
        return False
    if selector.require_top_raycast:
        if not _actionable_control(record):
            raise SemanticGateClosed(
                "combat action control is not exact top-raycast actionable"
            )
    return True


def _actionable_control(record: Any) -> bool:
    if isinstance(record, (ButtonState, ToggleState)):
        return record.actionable
    if isinstance(record, ImageState):
        return (
            record.active_in_hierarchy
            and record.active_and_enabled
            and record.raycast_target
            and record.raycast_top is True
            and record.bounds is not None
        )
    return False


def _action_control_point(record: Any) -> Optional[Point]:
    if isinstance(record, (ButtonState, ToggleState)):
        return record.point
    if isinstance(record, ImageState) and record.bounds is not None:
        return Point(
            (record.bounds.left + record.bounds.right) / 2.0,
            (record.bounds.top + record.bounds.bottom) / 2.0,
        )
    return None


def alas_combat_unity_selector_present(
    snapshot: AlasCombatObserverSnapshot,
    selector: AlasCombatUnitySelector,
) -> bool:
    """Review helper using the same exact matcher as production replay."""

    _validate_selector(selector)
    return _selector_present(snapshot, selector)


def prepare_alas_combat_resource_action(
    snapshot: AlasCombatObserverSnapshot,
    manifest: AlasCombatObserverManifest,
    resource_name: str,
) -> ActionReceipt:
    """Resolve one reviewed combat action without injecting input.

    The returned receipt is an intent bound to the exact observer generation.
    A caller still has to perform its own package, PID, foreground, freshness,
    and one-shot authorization checks immediately before using the point.
    """

    audit_alas_combat_observer_manifest(manifest)
    _validate_snapshot(snapshot, manifest)
    if resource_name not in _ACTION_RESOURCES:
        raise SemanticGateClosed("combat resource is not an action resource")
    mappings = tuple(
        mapping
        for mapping in manifest.resources
        if mapping.resource_name == resource_name
    )
    if len(mappings) != 1 or not mappings[0].qualified:
        raise SemanticGateClosed("combat action resource is not qualified")
    mapping = mappings[0]
    active_blockers = tuple(
        blocker.blocker_name
        for blocker in manifest.blockers
        if blocker.qualified
        and all(_selector_present(snapshot, item) for item in blocker.selectors)
    )
    if active_blockers:
        raise SemanticGateClosed(
            "combat action is blocked by: " + ", ".join(active_blockers)
        )
    if not _resource_visible(snapshot, mapping):
        raise SemanticGateClosed("combat action resource is not visible")
    competing_actions = tuple(
        candidate.resource_name
        for candidate in manifest.resources
        if candidate.resource_name in _ACTION_RESOURCES
        and candidate.resource_name != resource_name
        and candidate.resource_name
        not in _ACTION_PRECEDENCE_ALLOWLIST.get(resource_name, frozenset())
        and candidate.qualified
        and _resource_visible(snapshot, candidate)
    )
    if competing_actions:
        raise SemanticGateClosed(
            "combat action resource is ambiguous with: "
            + ", ".join(competing_actions)
        )
    control_selectors = tuple(
        selector
        for selector in mapping.selectors
        if selector.kind
        in (
            AlasCombatUnityRecordKind.BUTTON,
            AlasCombatUnityRecordKind.IMAGE,
            AlasCombatUnityRecordKind.TOGGLE_OFF,
            AlasCombatUnityRecordKind.TOGGLE_ON,
        )
        and selector.require_top_raycast
    )
    if len(control_selectors) != 1:
        raise SemanticGateClosed(
            "combat action resource must have one exact top-raycast control"
        )
    control = _record_for_selector(snapshot, control_selectors[0])
    point = _action_control_point(control)
    if not _actionable_control(control) or point is None or control.bounds is None:
        raise SemanticGateClosed("combat action control is not actionable")
    return ActionReceipt(
        semantic_id="combat/resource/" + resource_name,
        generation=snapshot.generation,
        point=point,
        bounds=control.bounds,
        path=control.path,
    )


def _resource_visible(
    snapshot: AlasCombatObserverSnapshot,
    mapping: AlasCombatResourceMapping,
) -> bool:
    return all(_selector_present(snapshot, item) for item in mapping.selectors)


def _visible_resource_names(
    snapshot: AlasCombatObserverSnapshot,
    mappings: Mapping[str, AlasCombatResourceMapping],
) -> Tuple[str, ...]:
    """Translate active Unity objects into ALAS's foreground appear semantics."""

    visible = {
        name
        for name in ALAS_COMBAT_REPLAY_RESOURCE_NAMES
        if _resource_visible(snapshot, mappings[name])
    }
    if "BATTLE_PREPARATION" in visible:
        # LevelStageView remains active behind ChapterPreCombatUI, whereas the
        # original screenshot template does not see IN_MAP through that layer.
        visible.discard("IN_MAP")
    if visible.intersection(
        {"BATTLE_STATUS_S", "GET_ITEMS_1", "EXP_INFO_S"}
    ):
        # The battle pause object remains active behind result overlays.
        visible.discard("PAUSE")
    if snapshot.campaign_map is not None:
        # Search and stable-map fixtures carry a fully parsed map model; this
        # is stronger evidence than a background Image anchor alone.
        visible.add("IN_MAP")
    return tuple(
        name for name in ALAS_COMBAT_REPLAY_RESOURCE_NAMES if name in visible
    )


def _fleet_stats(
    snapshot: AlasCombatObserverSnapshot,
    mapping: AlasCombatFleetStatsMapping,
) -> Tuple[Tuple[float, ...], Tuple[int, ...]]:
    _validate_stats_shape(mapping)
    for selectors in (mapping.hp_images, mapping.level_texts):
        groups: Dict[Tuple[Any, ...], list[AlasCombatUnitySelector]] = {}
        for selector in selectors:
            key = (
                selector.kind,
                selector.path,
                selector.name,
                selector.sprite,
                selector.text,
                selector.width_scale,
            )
            groups.setdefault(key, []).append(selector)
        for group in groups.values():
            if len(group) <= 1:
                continue
            records = (
                snapshot.ui_state.images
                if group[0].kind is AlasCombatUnityRecordKind.IMAGE
                else snapshot.ui_state.texts
            )
            matches = tuple(
                record
                for record in records
                if record.path == group[0].path and record.name == group[0].name
            )
            if len(matches) != len(group):
                raise SemanticGateClosed(
                    "combat fleet stats clone count changed"
                )
    hp = []
    for selector in mapping.hp_images:
        record = _record_for_selector(snapshot, selector)
        if not isinstance(record, ImageState) or not _selector_present(
            snapshot, selector
        ):
            raise SemanticGateClosed("combat HP Image is absent")
        if selector.width_scale is None:
            value = float(record.fill_amount)
        else:
            if record.bounds is None:
                raise SemanticGateClosed("combat HP Image has no bounds")
            value = float(record.bounds.right - record.bounds.left) / float(
                selector.width_scale
            )
        if not 0.0 <= value <= 1.0:
            raise SemanticGateClosed("combat HP fill is outside [0, 1]")
        hp.append(value)
    levels = []
    for selector in mapping.level_texts:
        record = _record_for_selector(snapshot, selector)
        if not isinstance(record, TextState) or not _selector_present(
            snapshot, selector
        ):
            raise SemanticGateClosed("combat level Text is absent")
        if re.fullmatch(r"(?:[1-9]|[1-9][0-9]|1[01][0-9]|12[0-5])", record.text) is None:
            raise SemanticGateClosed("combat fleet level is outside 1..125")
        levels.append(int(record.text))
    return tuple(hp), tuple(levels)


def alas_combat_fleet_stats(
    snapshot: AlasCombatObserverSnapshot,
    mapping: AlasCombatFleetStatsMapping,
) -> Tuple[Tuple[float, ...], Tuple[int, ...]]:
    """Resolve six ordered typed fleet stats for review and replay."""

    if not isinstance(snapshot, AlasCombatObserverSnapshot):
        raise SemanticGateClosed("combat fleet stats snapshot is not typed")
    return _fleet_stats(snapshot, mapping)


def _map_flags(
    phase: AlasCombatReplayPhase,
    state: Optional[CampaignMapState],
    admission: AlasCampaignCombatAdmission,
) -> Tuple[bool, bool, bool]:
    if phase not in (
        AlasCombatReplayPhase.MAP_SEARCHING,
        AlasCombatReplayPhase.MAP_STABLE,
    ):
        if state is not None:
            raise SemanticGateClosed("combat map observation appeared too early")
        return False, False, False
    if state is None:
        raise SemanticGateClosed("combat map observation is missing")
    if state.stage_code != admission.stage_code:
        raise SemanticGateClosed("combat map stage changed")
    target_cells = tuple(cell for cell in state.cells if cell.node == admission.target_node)
    if len(target_cells) != 1:
        raise SemanticGateClosed("combat target cell is absent or ambiguous")
    target_cell = target_cells[0]
    if (
        target_cell.button_path != admission.cell_path
        or target_cell.point != admission.point
        or target_cell.bounds != admission.bounds
    ):
        raise SemanticGateClosed("combat target cell geometry changed")
    target_fleets = tuple(fleet for fleet in state.fleets if fleet.node == admission.target_node)
    fleet_on_target = any(fleet.marker == admission.fleet_marker for fleet in target_fleets)
    current_on_target = (
        state.current_fleet_marker == admission.fleet_marker and fleet_on_target
    )
    if not fleet_on_target or not current_on_target:
        raise SemanticGateClosed("combat target fleet identity changed")
    if phase is AlasCombatReplayPhase.MAP_STABLE and any(
        enemy.node == admission.target_node for enemy in state.enemies
    ):
        raise SemanticGateClosed("combat target enemy remains on stable map")
    if phase is AlasCombatReplayPhase.MAP_STABLE:
        matching_fleet = next(
            fleet for fleet in target_fleets if fleet.marker == admission.fleet_marker
        )
        if matching_fleet.ammo != admission.ammo_before - 1:
            raise SemanticGateClosed("combat target fleet ammo did not decrement")
    return True, fleet_on_target, current_on_target


def build_alas_campaign_combat_replay_from_observer(
    admission: AlasCampaignCombatAdmission,
    snapshots: Sequence[AlasCombatObserverSnapshot],
    manifest: AlasCombatObserverManifest,
) -> AlasCampaignCombatReplay:
    """Infer one bounded 6-10 frame replay from exact Unity records."""

    if not isinstance(admission, AlasCampaignCombatAdmission):
        raise SemanticGateClosed("combat observer replay requires an admission")
    coverage = audit_alas_combat_observer_manifest(manifest)
    if not coverage.production_ready:
        raise SemanticGateClosed(
            "combat observer manifest is not production-ready: {0}/{1} resources"
            .format(coverage.qualified_resources, coverage.total_resources)
        )
    allowed_lengths = {len(sequence) for sequence in ALAS_COMBAT_REPLAY_PHASE_SEQUENCES}
    if len(snapshots) not in allowed_lengths:
        raise SemanticGateClosed("combat observer replay requires 6 to 10 snapshots")
    mappings: Dict[str, AlasCombatResourceMapping] = {
        item.resource_name: item for item in manifest.resources
    }
    validated = []
    previous = admission.input_generation
    for snapshot in snapshots:
        _validate_snapshot(snapshot, manifest)
        if snapshot.generation <= previous:
            raise SemanticGateClosed(
                "combat observer generations are not strictly increasing"
            )
        previous = snapshot.generation
        active_blockers = tuple(
            mapping.blocker_name
            for mapping in manifest.blockers
            if all(_selector_present(snapshot, item) for item in mapping.selectors)
        )
        if active_blockers:
            raise SemanticGateClosed(
                "combat observer blocker is active: " + ", ".join(active_blockers)
            )
        visible = _visible_resource_names(snapshot, mappings)
        validated.append((snapshot, visible))
    matching_sequences = tuple(
        sequence
        for sequence in ALAS_COMBAT_REPLAY_PHASE_SEQUENCES
        if len(sequence) == len(validated)
        and all(
            set(visible) == set(ALAS_COMBAT_REPLAY_EXPECTED_RESOURCES[phase])
            for phase, (_, visible) in zip(sequence, validated)
        )
    )
    if len(matching_sequences) != 1:
        raise SemanticGateClosed(
            "combat observer records do not prove one bounded phase sequence"
        )
    frames = []
    for phase, (snapshot, visible) in zip(matching_sequences[0], validated):
        in_map, fleet_on_target, current_on_target = _map_flags(
            phase, snapshot.campaign_map, admission
        )
        hp: Tuple[float, ...] = ()
        levels: Tuple[int, ...] = ()
        if phase is AlasCombatReplayPhase.MAP_STABLE:
            hp, levels = _fleet_stats(snapshot, manifest.fleet_stats)
        frames.append(
            AlasCombatReplayFrame(
                generation=snapshot.generation,
                phase=phase,
                visible_resources=tuple(sorted(visible)),
                in_map=in_map,
                combat_loading=phase
                in (
                    AlasCombatReplayPhase.AUTOMATION_CONFIRM,
                    AlasCombatReplayPhase.BATTLE_PREPARATION_AUTOMATION_OFF,
                    AlasCombatReplayPhase.BATTLE_PREPARATION,
                ),
                combat_executing=phase is AlasCombatReplayPhase.COMBAT_EXECUTING,
                enemy_searching=phase is AlasCombatReplayPhase.MAP_SEARCHING,
                fleet_on_target=fleet_on_target,
                current_fleet_on_target=current_on_target,
                hp=hp,
                levels=levels,
            )
        )
    return AlasCampaignCombatReplay(
        stage_code=admission.stage_code,
        target_node=admission.target_node,
        input_generation=admission.input_generation,
        frames=tuple(frames),
    )


def canonical_alas_combat_observer_frame_sha256(
    value: Mapping[str, Any],
) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fixture_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticGateClosed("combat fixture integer is malformed: " + field)
    return value


def _fixture_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticGateClosed("combat fixture number is malformed: " + field)
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise SemanticGateClosed("combat fixture number is non-finite: " + field)
    return result


def _fixture_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SemanticGateClosed("combat fixture text is malformed: " + field)
    return value


def _fixture_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise SemanticGateClosed("combat fixture boolean is malformed: " + field)
    return value


def _parse_campaign_map(value: Any) -> Optional[CampaignMapState]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SemanticGateClosed("combat fixture map is malformed")
    try:
        cells = tuple(
            CampaignMapCellState(
                row=_fixture_int(item["row"], "cell.row"),
                column=_fixture_int(item["column"], "cell.column"),
                node=_fixture_text(item["node"], "cell.node"),
                button_path=_fixture_text(item["button_path"], "cell.button_path"),
                point=Point(
                    _fixture_number(item["point"]["x"], "cell.point.x"),
                    _fixture_number(item["point"]["y"], "cell.point.y"),
                ),
                bounds=Bounds(
                    _fixture_number(item["bounds"]["left"], "cell.bounds.left"),
                    _fixture_number(item["bounds"]["top"], "cell.bounds.top"),
                    _fixture_number(item["bounds"]["right"], "cell.bounds.right"),
                    _fixture_number(item["bounds"]["bottom"], "cell.bounds.bottom"),
                ),
            )
            for item in value["cells"]
        )
        fleets = tuple(
            CampaignMapFleetState(
                marker=_fixture_text(item["marker"], "fleet.marker"),
                node=_fixture_text(item["node"], "fleet.node"),
                ammo=_fixture_int(item["ammo"], "fleet.ammo"),
                ammo_capacity=_fixture_int(
                    item["ammo_capacity"], "fleet.ammo_capacity"
                ),
            )
            for item in value["fleets"]
        )
        enemies = tuple(
            CampaignMapEnemyState(
                row=_fixture_int(item["row"], "enemy.row"),
                column=_fixture_int(item["column"], "enemy.column"),
                node=_fixture_text(item["node"], "enemy.node"),
                object_id=_fixture_int(item["object_id"], "enemy.object_id"),
                sprite=_fixture_text(item["sprite"], "enemy.sprite"),
                scale=_fixture_int(item["scale"], "enemy.scale"),
                genre=_fixture_text(item["genre"], "enemy.genre"),
                level=_fixture_int(item["level"], "enemy.level"),
                fighting=_fixture_bool(item["fighting"], "enemy.fighting"),
            )
            for item in value["enemies"]
        )
        pickups = tuple(
            CampaignMapPickupState(
                row=_fixture_int(item["row"], "pickup.row"),
                column=_fixture_int(item["column"], "pickup.column"),
                node=_fixture_text(item["node"], "pickup.node"),
                kind=_fixture_text(item["kind"], "pickup.kind"),
                sprite=_fixture_text(item["sprite"], "pickup.sprite"),
            )
            for item in value["pickups"]
        )
        state = CampaignMapState(
            generation=_fixture_int(value["generation"], "map.generation"),
            stage_code=_fixture_text(value["stage_code"], "map.stage_code"),
            rows=_fixture_int(value["rows"], "map.rows"),
            columns=_fixture_int(value["columns"], "map.columns"),
            cells=cells,
            land_nodes=tuple(
                _fixture_text(item, "map.land_node") for item in value["land_nodes"]
            ),
            fleets=fleets,
            enemies=enemies,
            pickups=pickups,
            displayed_fleet_index=_fixture_int(
                value["displayed_fleet_index"], "map.displayed_fleet_index"
            ),
            current_fleet_marker=_fixture_text(
                value["current_fleet_marker"], "map.current_fleet_marker"
            ),
            current_fleet_roster_sprites=tuple(
                _fixture_text(item, "map.roster_sprite")
                for item in value["current_fleet_roster_sprites"]
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SemanticGateClosed("combat fixture map is incomplete") from exc
    observed_nodes = tuple(cell.node for cell in state.cells) + state.land_nodes
    if (
        not state.cells
        or not state.fleets
        or state.rows < 1
        or state.columns < 1
        or len(observed_nodes) != state.rows * state.columns
        or len(observed_nodes) != len(set(observed_nodes))
        or len(state.current_fleet_roster_sprites) not in range(1, 7)
    ):
        raise SemanticGateClosed("combat fixture map has no complete topology")
    return state


def parse_alas_combat_observer_fixture_frame(
    value: Any,
    manifest: AlasCombatObserverManifest,
) -> AlasCombatObserverSnapshot:
    if not isinstance(value, dict) or set(value) != {
        "snapshot",
        "buttons",
        "ui",
        "campaign_map",
        "sha256",
    }:
        raise SemanticGateClosed("combat fixture frame schema changed")
    payload = {
        "snapshot": value.get("snapshot"),
        "buttons": value.get("buttons"),
        "ui": value.get("ui"),
        "campaign_map": value.get("campaign_map"),
    }
    declared_hash = value.get("sha256")
    if declared_hash != canonical_alas_combat_observer_frame_sha256(payload):
        raise SemanticGateClosed("combat fixture frame hash changed")
    snapshot_raw = payload["snapshot"]
    buttons_raw = payload["buttons"]
    ui_raw = payload["ui"]
    if not all(isinstance(item, dict) for item in (snapshot_raw, buttons_raw, ui_raw)):
        raise SemanticGateClosed("combat fixture endpoint payload is malformed")
    parser = SemanticOracle(
        request=lambda request: {},
        foreground_component=lambda: "",
        tap=lambda x, y: None,
        fingerprint=OracleFingerprint(
            package=manifest.package,
            component="fixture",
            driver_revision=manifest.driver_revision,
        ),
    )
    parser._validate_identity(snapshot_raw)  # exact live parser, offline transport
    parser._validate_identity(buttons_raw, BUTTON_SCHEMA)
    parser._validate_identity(ui_raw, UI_SCHEMA)
    if snapshot_raw.get("snapshot_schema") != 1:
        raise SemanticGateClosed("combat fixture snapshot schema mismatch")
    if (
        snapshot_raw.get("main_thread") is not True
        or snapshot_raw.get("flags") != 15
        or snapshot_raw.get("ui_stage") != 100
        or snapshot_raw.get("ui_method_mask") != 15
        or snapshot_raw.get("width") != 1280
        or snapshot_raw.get("height") != 720
    ):
        raise SemanticGateClosed("combat fixture main-thread probe is incomplete")
    raw_buttons = buttons_raw.get("buttons")
    raw_toggles = ui_raw.get("toggles")
    raw_texts = ui_raw.get("texts")
    raw_images = ui_raw.get("images")
    if not all(
        isinstance(item, list)
        for item in (raw_buttons, raw_toggles, raw_texts, raw_images)
    ):
        raise SemanticGateClosed("combat fixture record list is malformed")
    if (
        buttons_raw.get("schema") != 1
        or buttons_raw.get("truncated") is not False
        or buttons_raw.get("error_count") != 0
        or buttons_raw.get("button_count") != len(raw_buttons)
        or ui_raw.get("schema") != 1
        or ui_raw.get("toggle_truncated") is not False
        or ui_raw.get("text_truncated") is not False
        or ui_raw.get("image_truncated") is not False
        or ui_raw.get("error_count") != 0
        or ui_raw.get("toggle_count") != len(raw_toggles)
        or ui_raw.get("text_count") != len(raw_texts)
        or ui_raw.get("image_count") != len(raw_images)
        or ui_raw.get("method_mask") != 15
    ):
        raise SemanticGateClosed("combat fixture endpoint completeness changed")
    oracle_generation = parser._integer(
        buttons_raw.get("generation"), "fixture Button generation"
    )
    ui_generation = parser._integer(ui_raw.get("generation"), "fixture UI generation")
    snapshot_generation = parser._integer(
        snapshot_raw.get("generation"), "fixture snapshot generation"
    )
    if (
        oracle_generation < snapshot_generation
        or oracle_generation > snapshot_generation + 2
        or abs(ui_generation - oracle_generation) > 2
    ):
        raise SemanticGateClosed("combat fixture endpoint generations disagree")
    oracle_state = OracleState(
        generation=oracle_generation,
        scene_handle=parser._integer(snapshot_raw.get("scene_handle"), "scene_handle"),
        snapshot=snapshot_raw,
        buttons_snapshot=buttons_raw,
        buttons=tuple(parser._parse_button(item) for item in raw_buttons),
    )
    ui_state = UiState(
        generation=ui_generation,
        method_mask=15,
        skipped_count=parser._integer(ui_raw.get("skipped_count"), "skipped_count"),
        image_truncated=False,
        snapshot=ui_raw,
        toggles=tuple(parser._parse_toggle(item) for item in raw_toggles),
        texts=tuple(parser._parse_text(item) for item in raw_texts),
        images=tuple(parser._parse_image(item) for item in raw_images),
    )
    return AlasCombatObserverSnapshot(
        capture_sha256=declared_hash,
        game_fingerprint=manifest.game_fingerprint,
        oracle_state=oracle_state,
        ui_state=ui_state,
        campaign_map=_parse_campaign_map(payload["campaign_map"]),
    )


def load_alas_combat_observer_fixture(
    path: Path,
    manifest: AlasCombatObserverManifest,
) -> Tuple[AlasCombatObserverSnapshot, ...]:
    """Load hash-bound raw observer endpoint payloads for offline replay."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticGateClosed("combat observer fixture cannot be read") from exc
    if not isinstance(value, dict) or value.get("schema") != ALAS_COMBAT_OBSERVER_FIXTURE_SCHEMA:
        raise SemanticGateClosed("combat observer fixture schema mismatch")
    if value.get("game_fingerprint") != manifest.game_fingerprint:
        raise SemanticGateClosed("combat fixture game fingerprint changed")
    frames = value.get("frames")
    allowed_lengths = {len(sequence) for sequence in ALAS_COMBAT_REPLAY_PHASE_SEQUENCES}
    if not isinstance(frames, list) or len(frames) not in allowed_lengths:
        raise SemanticGateClosed("combat observer fixture requires 6 to 10 frames")
    if any("phase" in frame for frame in frames if isinstance(frame, dict)):
        raise SemanticGateClosed("combat fixture must not provide phase tokens")
    return tuple(
        parse_alas_combat_observer_fixture_frame(frame, manifest)
        for frame in frames
    )
