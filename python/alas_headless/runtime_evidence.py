"""Offline index for runtime evidence with exact-fingerprint isolation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


RUNTIME_EVIDENCE_INDEX_SCHEMA = "alas-headless.runtime-evidence-index/v1"
RUNTIME_FINGERPRINT_FIELDS = (
    "backend",
    "host_class",
    "android_fingerprint",
    "game_version",
    "game_abi",
    "libil2cpp_sha256",
    "angle_sha256",
    "observer_schema",
    "core_commit",
    "runtime_lock_sha256",
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class RuntimeEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeFingerprint:
    values: Tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RuntimeFingerprint":
        if not isinstance(value, dict):
            raise RuntimeEvidenceError("runtime_fingerprint must be an object")
        unknown = sorted(set(value) - set(RUNTIME_FINGERPRINT_FIELDS))
        missing = sorted(set(RUNTIME_FINGERPRINT_FIELDS) - set(value))
        if unknown or missing:
            raise RuntimeEvidenceError(
                "runtime_fingerprint fields differ (missing={0}; unknown={1})".format(
                    ",".join(missing), ",".join(unknown)
                )
            )
        values = []
        for field in RUNTIME_FINGERPRINT_FIELDS:
            item = value[field]
            if not isinstance(item, str) or not item.strip():
                raise RuntimeEvidenceError(
                    "runtime_fingerprint field is empty: {0}".format(field)
                )
            values.append(item.strip())
        indexed = dict(zip(RUNTIME_FINGERPRINT_FIELDS, values))
        if indexed["backend"] not in (
            "kvm",
            "redroid",
            "tcg",
            "arm64-qemu",
            "external-adb",
        ):
            raise RuntimeEvidenceError("runtime_fingerprint backend is unsupported")
        if indexed["game_abi"] not in ("x86_64", "arm64-v8a"):
            raise RuntimeEvidenceError("runtime_fingerprint game_abi is unsupported")
        for field in ("libil2cpp_sha256", "angle_sha256", "runtime_lock_sha256"):
            if _SHA256_PATTERN.fullmatch(indexed[field].lower()) is None:
                raise RuntimeEvidenceError(
                    "runtime_fingerprint field must be sha256: {0}".format(field)
                )
        if _COMMIT_PATTERN.fullmatch(indexed["core_commit"].lower()) is None:
            raise RuntimeEvidenceError("runtime_fingerprint core_commit must be a full commit")
        return cls(tuple(values))

    def as_mapping(self) -> Mapping[str, str]:
        return dict(zip(RUNTIME_FINGERPRINT_FIELDS, self.values))

    @property
    def key(self) -> str:
        return "|".join(self.values)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeEvidenceError("manifest captured_at_utc is missing")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise RuntimeEvidenceError("manifest captured_at_utc is invalid") from exc
    if parsed.tzinfo is None:
        raise RuntimeEvidenceError("manifest captured_at_utc must include a timezone")
    return parsed


def _load_manifest(path: Path, maximum_bytes: int) -> Mapping[str, Any]:
    if path.stat().st_size > maximum_bytes:
        raise RuntimeEvidenceError("manifest exceeds the size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeEvidenceError("manifest is unreadable JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeEvidenceError("manifest must be a JSON object")
    return value


def index_runtime_evidence(
    roots: Iterable[Path], maximum_manifest_bytes: int = 8 * 1024 * 1024
) -> Mapping[str, Any]:
    """Scan only explicit roots and retain the latest result per gate/fingerprint."""

    resolved_roots = []
    for root in roots:
        resolved = Path(root).resolve()
        if not resolved.is_dir():
            raise RuntimeEvidenceError("evidence root is not a directory: {0}".format(root))
        resolved_roots.append(resolved)
    if not resolved_roots:
        raise RuntimeEvidenceError("at least one explicit evidence root is required")

    accepted: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    rejected: List[Mapping[str, str]] = []
    seen_paths = set()
    for root in sorted(set(resolved_roots), key=lambda item: str(item).lower()):
        for path in sorted(root.rglob("manifest.json"), key=lambda item: str(item).lower()):
            resolved_path = path.resolve()
            try:
                resolved_path.relative_to(root)
            except ValueError:
                rejected.append({"path": str(path), "reason": "manifest escapes evidence root"})
                continue
            normalized_path = str(resolved_path).lower()
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            try:
                manifest = _load_manifest(resolved_path, maximum_manifest_bytes)
                fingerprint = RuntimeFingerprint.from_mapping(
                    manifest.get("runtime_fingerprint")
                )
                gate = manifest.get("gate")
                outcome = manifest.get("outcome")
                if not isinstance(gate, str) or not gate.strip():
                    raise RuntimeEvidenceError("manifest gate is missing")
                if outcome not in ("pass", "fail", "inconclusive"):
                    raise RuntimeEvidenceError("manifest outcome is unsupported")
                captured = _parse_timestamp(manifest.get("captured_at_utc"))
                record = {
                    "gate": gate.strip(),
                    "outcome": outcome,
                    "captured_at_utc": manifest["captured_at_utc"],
                    "manifest_path": str(resolved_path),
                    "runtime_fingerprint": fingerprint.as_mapping(),
                }
                key = (fingerprint.key, gate.strip())
                previous = accepted.get(key)
                if previous is None or captured > _parse_timestamp(previous["captured_at_utc"]):
                    accepted[key] = record
            except (OSError, RuntimeEvidenceError) as exc:
                rejected.append({"path": str(resolved_path), "reason": str(exc)})

    groups: Dict[str, Dict[str, Any]] = {}
    for (fingerprint_key, gate), record in sorted(accepted.items()):
        group = groups.setdefault(
            fingerprint_key,
            {
                "runtime_fingerprint": record["runtime_fingerprint"],
                "gates": {},
            },
        )
        group["gates"][gate] = {
            key: record[key]
            for key in ("outcome", "captured_at_utc", "manifest_path")
        }
    return {
        "schema": RUNTIME_EVIDENCE_INDEX_SCHEMA,
        "roots": [str(root) for root in sorted(set(resolved_roots), key=lambda item: str(item).lower())],
        "fingerprints": [groups[key] for key in sorted(groups)],
        "rejected": sorted(rejected, key=lambda item: item["path"].lower()),
    }


def runtime_evidence_markdown(index: Mapping[str, Any]) -> str:
    if index.get("schema") != RUNTIME_EVIDENCE_INDEX_SCHEMA:
        raise RuntimeEvidenceError("runtime evidence index schema mismatch")
    lines = ["# Runtime evidence index", ""]
    fingerprints = index.get("fingerprints", [])
    if not fingerprints:
        lines.append("No exact runtime fingerprints were indexed.")
    for group in fingerprints:
        fingerprint = group["runtime_fingerprint"]
        lines.extend(
            (
                "## {0} / {1} / {2} / lock {3}".format(
                    fingerprint["backend"],
                    fingerprint["game_abi"],
                    fingerprint["game_version"],
                    fingerprint["runtime_lock_sha256"][:12],
                ),
                "",
                "| Gate | Outcome | Captured | Manifest |",
                "| --- | --- | --- | --- |",
            )
        )
        for gate, record in sorted(group["gates"].items()):
            lines.append(
                "| {0} | {1} | {2} | `{3}` |".format(
                    gate,
                    record["outcome"],
                    record["captured_at_utc"],
                    record["manifest_path"],
                )
            )
        lines.append("")
    rejected = index.get("rejected", [])
    lines.extend(("## Rejected manifests", "", "Count: {0}".format(len(rejected)), ""))
    return "\n".join(lines)
