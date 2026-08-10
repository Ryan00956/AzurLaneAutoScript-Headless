"""Short-lived same-process lease derived from a fully verified raw trace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .alas_combat_observer import AlasCombatObserverManifest
from .alas_combat_trace import AlasCombatObserverTrace
from .semantic_oracle import SemanticGateClosed


_LEASE_TOKEN = object()


@dataclass(frozen=True, init=False, slots=True)
class AlasPackageProcessLease:
    """Opaque proof that one exact live PID was fully fingerprinted recently."""

    package: str
    driver_revision: str
    game_fingerprint: str
    pid: int
    generation: int
    captured_at_utc: str

    def __init__(
        self,
        *,
        package: str,
        driver_revision: str,
        game_fingerprint: str,
        pid: int,
        generation: int,
        captured_at_utc: str,
        _token: object,
    ) -> None:
        if _token is not _LEASE_TOKEN:
            raise TypeError("package process leases must come from a verified trace")
        object.__setattr__(self, "package", package)
        object.__setattr__(self, "driver_revision", driver_revision)
        object.__setattr__(self, "game_fingerprint", game_fingerprint)
        object.__setattr__(self, "pid", pid)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "captured_at_utc", captured_at_utc)


def alas_package_process_lease_from_trace(
    trace: AlasCombatObserverTrace,
    manifest: AlasCombatObserverManifest,
    *,
    maximum_age_seconds: int = 900,
    now: Optional[datetime] = None,
) -> AlasPackageProcessLease:
    """Issue a bounded lease only from a parsed, identity-bound raw trace."""

    if not isinstance(trace, AlasCombatObserverTrace):
        raise SemanticGateClosed("package process lease trace is not typed")
    if (
        trace.package != manifest.package
        or trace.driver_revision != manifest.driver_revision
        or trace.game_fingerprint != manifest.game_fingerprint
    ):
        raise SemanticGateClosed("package process lease identity changed")
    if (
        isinstance(maximum_age_seconds, bool)
        or not isinstance(maximum_age_seconds, int)
        or not 1 <= maximum_age_seconds <= 900
    ):
        raise SemanticGateClosed("package process lease age bound is invalid")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise SemanticGateClosed("package process lease clock is naive")
    captured_text = trace.samples[-1].captured_at_utc
    try:
        captured = datetime.fromisoformat(captured_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SemanticGateClosed("package process lease timestamp changed") from exc
    age = (current.astimezone(timezone.utc) - captured).total_seconds()
    if not -5.0 <= age <= maximum_age_seconds:
        raise SemanticGateClosed("package process lease trace is stale")
    return AlasPackageProcessLease(
        package=trace.package,
        driver_revision=trace.driver_revision,
        game_fingerprint=trace.game_fingerprint,
        pid=trace.pid,
        generation=trace.generations[-1],
        captured_at_utc=captured_text,
        _token=_LEASE_TOKEN,
    )
