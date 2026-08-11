"""Immutable runtime lock, resource identity, and update admission rules."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


RUNTIME_LOCK_SCHEMA = "alas-headless.runtime-lock/v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SUPPORTED_ABIS = frozenset(("x86_64", "arm64-v8a"))


class RuntimeLockError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        return item

    return json.dumps(
        plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_json(child) for key, child in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(child) for child in value)
    return value


def _required_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise RuntimeLockError("runtime lock field must be an object: {0}".format(key))
    return item


def _required_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise RuntimeLockError("runtime lock field must be non-empty text: {0}".format(key))
    return item.strip()


def _required_hash(value: Mapping[str, Any], key: str) -> str:
    item = _required_text(value, key).lower()
    if SHA256_PATTERN.fullmatch(item) is None:
        raise RuntimeLockError("runtime lock field must be sha256: {0}".format(key))
    return item


def _required_commit(value: Mapping[str, Any], key: str) -> str:
    item = _required_text(value, key).lower()
    if COMMIT_PATTERN.fullmatch(item) is None:
        raise RuntimeLockError("runtime lock field must be a full commit: {0}".format(key))
    return item


def _require_exact_fields(
    value: Mapping[str, Any], section: str, expected: Iterable[str]
) -> None:
    expected_set = set(expected)
    missing = sorted(expected_set - set(value))
    unknown = sorted(set(value) - expected_set)
    if missing or unknown:
        raise RuntimeLockError(
            "runtime lock section differs: {0} (missing={1}; unknown={2})".format(
                section, ",".join(missing), ",".join(unknown)
            )
        )


@dataclass(frozen=True)
class RuntimeLock:
    document: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RuntimeLock":
        if not isinstance(value, dict):
            raise RuntimeLockError("runtime lock must be a JSON object")
        allowed = {
            "schema",
            "core",
            "angle",
            "android",
            "game",
            "resources",
            "userdata",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise RuntimeLockError("runtime lock has unknown fields: {0}".format(", ".join(unknown)))
        if value.get("schema") != RUNTIME_LOCK_SCHEMA:
            raise RuntimeLockError("runtime lock schema mismatch")

        core = _required_mapping(value, "core")
        _require_exact_fields(
            core, "core", ("core_commit", "alas_upstream_commit", "alas_patch_sha256")
        )
        _required_commit(core, "core_commit")
        _required_commit(core, "alas_upstream_commit")
        _required_hash(core, "alas_patch_sha256")

        angle = _required_mapping(value, "angle")
        _require_exact_fields(
            angle,
            "angle",
            ("revision", "patchset_sha256", "abi", "apk_sha256", "observer_schema"),
        )
        _required_commit(angle, "revision")
        _required_hash(angle, "patchset_sha256")
        angle_abi = _required_text(angle, "abi")
        _required_hash(angle, "apk_sha256")
        _required_text(angle, "observer_schema")

        android = _required_mapping(value, "android")
        _require_exact_fields(
            android,
            "android",
            (
                "backend",
                "build_fingerprint",
                "api_level",
                "abi",
                "system_image_sha256",
                "provision_profile_sha256",
            ),
        )
        backend = _required_text(android, "backend")
        if backend not in ("kvm", "redroid", "tcg", "arm64-qemu", "external-adb"):
            raise RuntimeLockError("android.backend is unsupported")
        _required_text(android, "build_fingerprint")
        api_level = android.get("api_level")
        if isinstance(api_level, bool) or not isinstance(api_level, int) or api_level < 21:
            raise RuntimeLockError("android.api_level must be an integer >= 21")
        android_abi = _required_text(android, "abi")
        _required_hash(android, "system_image_sha256")
        _required_hash(android, "provision_profile_sha256")

        game = _required_mapping(value, "game")
        _require_exact_fields(
            game,
            "game",
            (
                "package",
                "region",
                "version_name",
                "version_code",
                "abi",
                "base_apk_sha256",
                "libil2cpp_sha256",
            ),
        )
        _required_text(game, "package")
        _required_text(game, "region")
        _required_text(game, "version_name")
        version_code = game.get("version_code")
        if isinstance(version_code, bool) or not isinstance(version_code, int) or version_code < 1:
            raise RuntimeLockError("game.version_code must be a positive integer")
        game_abi = _required_text(game, "abi")
        _required_hash(game, "base_apk_sha256")
        _required_hash(game, "libil2cpp_sha256")

        resources = _required_mapping(value, "resources")
        _require_exact_fields(
            resources,
            "resources",
            ("resource_set_id", "resource_epoch", "manifest_sha256", "shared_public_paths"),
        )
        observed_resource_set_id = _required_text(resources, "resource_set_id")
        epoch = resources.get("resource_epoch")
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
            raise RuntimeLockError("resources.resource_epoch must be a positive integer")
        resource_manifest_sha256 = _required_hash(resources, "manifest_sha256")
        paths = resources.get("shared_public_paths")
        if not isinstance(paths, list):
            raise RuntimeLockError("resources.shared_public_paths must be a list")
        validate_shared_public_paths(paths)

        userdata = _required_mapping(value, "userdata")
        _require_exact_fields(userdata, "userdata", ("generation", "account_scope"))
        generation = userdata.get("generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise RuntimeLockError("userdata.generation must be a positive integer")
        account_scope = _required_text(userdata, "account_scope")
        if account_scope not in ("per-instance", "external-device"):
            raise RuntimeLockError("userdata.account_scope is unsupported")

        if angle_abi not in SUPPORTED_ABIS or android_abi not in SUPPORTED_ABIS:
            raise RuntimeLockError("runtime lock contains an unsupported ABI")
        if len({angle_abi, android_abi, game_abi}) != 1:
            raise RuntimeLockError("ANGLE, Android, and game ABIs must match")
        if backend == "arm64-qemu" and android_abi != "arm64-v8a":
            raise RuntimeLockError("arm64-qemu requires the arm64-v8a ABI")
        expected_resource_set_id = resource_set_id(
            _required_text(game, "region"),
            _required_text(game, "version_name"),
            resource_manifest_sha256,
        )
        if observed_resource_set_id != expected_resource_set_id:
            raise RuntimeLockError("resources.resource_set_id does not match its content identity")

        frozen = json.loads(canonical_json_bytes(value).decode("utf-8"))
        digest = hashlib.sha256(canonical_json_bytes(frozen)).hexdigest()
        return cls(document=_freeze_json(frozen), sha256=digest)


def validate_shared_public_paths(paths: Iterable[Any]) -> Tuple[str, ...]:
    accepted = []
    sensitive_parts = frozenset(
        ("accounts", "account", "shared_prefs", "databases", "keystore", "users")
    )
    for raw in paths:
        if not isinstance(raw, str) or not raw.strip():
            raise RuntimeLockError("shared public resource paths must be non-empty text")
        normalized = raw.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise RuntimeLockError("shared public resource paths must be relative and normalized")
        lowered = tuple(part.lower() for part in path.parts)
        if not lowered or any(part in sensitive_parts for part in lowered):
            raise RuntimeLockError("shared public resource path includes account data")
        if lowered[0] == "data" and len(lowered) == 1:
            raise RuntimeLockError("the complete Android data directory cannot be shared")
        accepted.append(path.as_posix())
    if len(set(accepted)) != len(accepted):
        raise RuntimeLockError("shared public resource paths must be unique")
    return tuple(accepted)


def resource_set_id(region: str, game_version: str, manifest_sha256: str) -> str:
    if SHA256_PATTERN.fullmatch(manifest_sha256.lower()) is None:
        raise RuntimeLockError("resource manifest identity must be sha256")
    identity = {
        "region": region.strip(),
        "game_version": game_version.strip(),
        "manifest_sha256": manifest_sha256.lower(),
    }
    if not identity["region"] or not identity["game_version"]:
        raise RuntimeLockError("resource identity fields cannot be empty")
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def verify_artifact_files(
    expected_sha256: Mapping[str, str], files: Mapping[str, Path]
) -> Mapping[str, str]:
    if set(expected_sha256) != set(files):
        raise RuntimeLockError("artifact hash keys and file keys must match exactly")
    observed: Dict[str, str] = {}
    for key in sorted(files):
        expected = expected_sha256[key].lower()
        if SHA256_PATTERN.fullmatch(expected) is None:
            raise RuntimeLockError("invalid expected artifact hash: {0}".format(key))
        path = Path(files[key])
        if not path.is_file():
            raise RuntimeLockError("artifact file is missing: {0}".format(key))
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise RuntimeLockError("artifact hash mismatch: {0}".format(key))
        observed[key] = actual
    return observed


class UpdateState(str, Enum):
    DISCOVERED = "discovered"
    STAGED = "staged"
    INTEGRITY_VERIFIED = "integrity-verified"
    COMPATIBILITY_VERIFIED = "compatibility-verified"
    CANARY = "canary"
    PROMOTED = "promoted"
    QUARANTINED = "quarantined"


_UPDATE_TRANSITIONS = {
    UpdateState.DISCOVERED: (UpdateState.STAGED, UpdateState.QUARANTINED),
    UpdateState.STAGED: (UpdateState.INTEGRITY_VERIFIED, UpdateState.QUARANTINED),
    UpdateState.INTEGRITY_VERIFIED: (
        UpdateState.COMPATIBILITY_VERIFIED,
        UpdateState.QUARANTINED,
    ),
    UpdateState.COMPATIBILITY_VERIFIED: (UpdateState.CANARY, UpdateState.QUARANTINED),
    UpdateState.CANARY: (UpdateState.PROMOTED, UpdateState.QUARANTINED),
    UpdateState.PROMOTED: (),
    UpdateState.QUARANTINED: (),
}


def expected_artifact_hashes(runtime_lock: RuntimeLock) -> Mapping[str, str]:
    if not isinstance(runtime_lock, RuntimeLock):
        raise RuntimeLockError("expected a validated runtime lock")
    document = runtime_lock.document
    return {
        "alas-patch": document["core"]["alas_patch_sha256"],
        "angle-apk": document["angle"]["apk_sha256"],
        "angle-patchset": document["angle"]["patchset_sha256"],
        "android-system-image": document["android"]["system_image_sha256"],
        "android-provision-profile": document["android"]["provision_profile_sha256"],
        "game-base-apk": document["game"]["base_apk_sha256"],
        "game-libil2cpp": document["game"]["libil2cpp_sha256"],
        "resource-manifest": document["resources"]["manifest_sha256"],
    }


@dataclass(frozen=True)
class UpdateAdmission:
    artifact_id: str
    state: UpdateState = UpdateState.DISCOVERED
    failure_code: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            raise RuntimeLockError("update admission requires an artifact id")
        if self.state == UpdateState.QUARANTINED:
            if not isinstance(self.failure_code, str) or not self.failure_code.strip():
                raise RuntimeLockError("quarantined updates require a failure code")
        elif self.failure_code is not None:
            raise RuntimeLockError("failure codes are only valid for quarantine")

    def transition(
        self, target: UpdateState, failure_code: Optional[str] = None
    ) -> "UpdateAdmission":
        if target not in _UPDATE_TRANSITIONS[self.state]:
            raise RuntimeLockError(
                "invalid update transition: {0} -> {1}".format(
                    self.state.value, target.value
                )
            )
        if target == UpdateState.QUARANTINED and not failure_code:
            raise RuntimeLockError("quarantined updates require a failure code")
        if target != UpdateState.QUARANTINED and failure_code is not None:
            raise RuntimeLockError("failure codes are only valid for quarantine")
        return UpdateAdmission(self.artifact_id, target, failure_code)
