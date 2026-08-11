# Runtime foundation before complete ALAS coverage

This milestone removes task-independent fixed costs from later optimization
work: backend identity, immutable artifact identity, bounded measurements, and
offline evidence comparison. It does not claim a complete ALAS workload or a
validated production density.

## Separation of responsibilities

```text
ALAS and semantic observation
  -> RuntimeBackend lifecycle contract
       probe -> resolve -> provision -> start -> ready -> recover -> stop
       |
       +-- kvm profile
       +-- redroid profile
       +-- tcg profile
       +-- arm64-qemu profile
       +-- external-adb profile
  -> immutable runtime lock
  -> opt-in bounded trace
  -> exact-fingerprint evidence index
```

The common contract owns lifecycle names and evidence identity. It does not own
QEMU flags, cgroups, cpusets, Android service removal, governor settings, NULL
refresh rate, or instance density. Those remain backend or workload decisions.

The implementation keeps those ownership boundaries visible in the module
layout. `runtime_backend_adb.py` owns the shared ADB lifecycle and external
device adapter, `runtime_backend_kvm.py` owns only the Linux KVM emulator,
and `runtime_backend_deferred.py` owns the fail-closed placeholders. The
existing `runtime_backends.py` import path remains a compatibility facade and
the strict configuration factory. A future executable backend should live in
its own module and be registered through that facade instead of growing a new
cross-backend monolith.

| Concern | Common | Backend-specific |
| --- | --- | --- |
| Artifact hashes and ABI compatibility | Yes | Artifact resolution paths |
| ADB and Android-ready phase names | Yes | Readiness commands |
| Observer RTT and snapshot age fields | Yes | Host process/cgroup samplers |
| Public-resource versus userdata isolation | Yes | qcow2, OCI volume, payload disk, or external-device ownership |
| Recovery result schema | Yes | VM, container, game, or device restart implementation |
| vCPU, MTTCG, affinity, cpuset, governor | No | Yes, after a repeatable workload exists |

## Backend profiles

`built_in_backend_profiles()` provides conservative declarations:

- `kvm`: golden AVD/userdata storage and hardware acceleration capability.
- `redroid`: OCI plus persistent `/data`, BinderFS/cgroup host prerequisites.
- `tcg`: software translation with its optimization policy explicitly frozen
  until a repeatable real workload exists.
- `arm64-qemu`: payload disk plus userdata and an enforced `arm64-v8a` lock.
- `external-adb`: externally owned rooted or unrooted phone; provisioning and
  persistent storage are not claimed by the controller.

`RuntimeBackendRegistry` selects one available backend and freezes that choice
for the run. It never falls from one active backend to another silently.

## Reference qualification runner

The first executable adapters deliberately cover only the two environments
whose lifecycle and identity boundaries are already concrete:

| Backend | Current state | Ownership boundary |
| --- | --- | --- |
| `external-adb` | Executable reference adapter | Attaches to an explicitly named device; it never claims device provisioning or ownership |
| `kvm` | Executable Linux reference adapter | Starts and stops only the emulator process created by the current runner |
| `redroid` | Plan-only, fail closed | BinderFS, OCI image, persistent `/data`, and instance isolation still require an implementation |
| `tcg` | Plan-only, fail closed | The frozen compatibility profile has no executable provisioner yet |
| `arm64-qemu` | Plan-only, fail closed | Payload disk, restart ownership, and recovery still require an implementation |

`scripts/python/qualify_runtime.py` is plan-only by default. Planning parses the
strict config and immutable lock, checks their backend and package identities,
and prints the intended state changes without probing ADB, KVM, Docker, or a
device:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/qualify_runtime.py `
  --backend kvm `
  --config integration/runtime/kvm.config.example.json `
  --lock integration/runtime/runtime-lock.example.json `
  --plan-output out/kvm-qualification-plan.json
```

The example paths are placeholders and are safe for plan generation. An actual
run requires both execution switches, an exact site-specific lock, and an
output directory that does not already exist:

```powershell
python scripts/python/qualify_runtime.py `
  --backend kvm `
  --config runtime-config.json `
  --lock runtime-lock.json `
  --execute `
  --allow-runtime-mutation `
  --output evidence/runtime/kvm/run-001
```

The two switches are intentionally separate. `--execute` alone is refused,
and a plan-only backend is refused before its output directory is created.
There is no automatic fallback from KVM to TCG, Redroid, or a phone.

Every executable run uses the same ordered lifecycle:

```text
probe-host -> resolve-artifacts -> provision -> start
           -> adb-ready -> android-ready -> game-ready
           -> observer-ready -> fingerprint -> stop
```

After that baseline is healthy, `--recovery game` or `--recovery android`
adds one explicit recovery gate. A game recovery closes the old observer
forward, force-stops and relaunches the package with the same allowlisted Unity
command line, waits for the exact foreground component, and requires a new PID,
fresh coherent observer state, and the same complete runtime fingerprint. An
Android recovery additionally requires an observed ADB-offline boundary before
ADB, PackageManager, the game, and observer may be declared recovered:

```powershell
python scripts/python/qualify_runtime.py `
  --backend kvm `
  --config runtime-config.json `
  --lock runtime-lock.json `
  --recovery android `
  --execute `
  --allow-runtime-mutation `
  --output evidence/runtime/kvm/android-recovery-001
```

Recovery plans remain non-mutating by default. Unsupported recovery kinds or
disabled external-device restart switches make the plan non-executable; there
is no silent fallback to a lifecycle-only pass.

Each phase receives a bounded timeout and records duration and a stable failure
code. Cleanup runs after any post-start failure. The resulting `manifest.json`
binds the expected and observed exact runtime fingerprints, the immutable lock
hash, all phase outcomes, trace completeness, whether input was injected, and
whether the runner changed runtime state. A nominal pass is downgraded if
cleanup fails, the observed fingerprint differs, or the bounded trace dropped
or rejected any record. The manifest is compatible with the offline evidence
index described below. If a complete observed fingerprint differs from the
lock, that failed record is indexed under the observed identity rather than
being allowed to overwrite evidence for the expected environment.

The external-ADB example defaults to observing an already running game:
`launch_game`, game restart, and Android restart are all disabled. Enabling any
of them still requires the global mutation gate. The KVM adapter verifies a
real Linux `/dev/kvm` character device, read/write access, KVM API version 12,
the named AVD config, emulator tools, and an unused emulator serial. Its start
profile is the validated compatibility baseline: headless, no audio or boot
animation, snapshot load/save disabled, `swiftshader_indirect`, acceleration
on, cameras disabled, and metrics disabled. It does not introduce vCPU,
MTTCG, affinity, PGO, or other experimental tuning.

Before a configured game launch, the runner reads the Android ANGLE developer
settings and requires the exact game package to map to the pinned ANGLE
package. It does not silently repair global settings. A site may explicitly set
`manage_angle_routing=true`; under the global mutation gate the runner then
captures the four prior values, applies the pinned route for this run, and
restores and verifies every value before stopping the runtime. A launch first
stops an existing package process and then passes only the allowlisted Unity
command line `-force-gfx-st`, which is required by the main-thread observer
rendezvous.

The observer readiness gate requires matching protocol, snapshot/Button
schemas, package, PID, ANGLE revision, and a coherent generation. The final
fingerprint independently checks Android build/API/ABI, the installed ANGLE
package APK hash, plus installed game version, APK hash, and `libil2cpp.so`
hash against the lock. Configuration
examples live in
[`integration/runtime`](../integration/runtime/).

## Runtime lock and updates

[`integration/runtime/runtime-lock.example.json`](../integration/runtime/runtime-lock.example.json)
shows the complete `alas-headless.runtime-lock/v1` document. The validator
requires exact section fields and binds:

- repository, upstream ALAS, and integration patch identities;
- ANGLE revision, patch set, APK, ABI, and observer schema;
- Android image, provision profile, backend, API level, ABI, and fingerprint;
- game package, region, version, APK, ABI, and `libil2cpp.so`;
- public resource manifest plus a content-derived `resource_set_id` and readable
  monotonic `resource_epoch`;
- userdata generation and account ownership scope.

ANGLE, Android, and game ABIs must match. Public shared paths must be relative,
normalized, unique, and must not contain account databases, preferences,
keystores, or the whole Android data directory.

The update admission state machine is intentionally one-way:

```text
discovered -> staged -> integrity-verified -> compatibility-verified
           -> canary -> promoted
any non-terminal stage -> quarantined(with a failure code)
```

Promotion cannot skip integrity, compatibility, or canary evidence.

Validate a lock alone, or additionally hash any named local artifacts:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/validate_runtime_lock.py `
  --lock integration/runtime/runtime-lock.example.json

python scripts/python/validate_runtime_lock.py `
  --lock runtime-lock.json `
  --artifact angle-apk=artifacts/angle.apk `
  --artifact game-base-apk=artifacts/game.apk
```

Supported artifact names are `alas-patch`, `angle-apk`, `angle-patchset`,
`android-system-image`, `android-provision-profile`, `game-base-apk`,
`game-libil2cpp`, and `resource-manifest`.

## Measurements

`RuntimeTraceRecorder` is disabled by default. When explicitly enabled it
writes `alas-headless.runtime-trace/v1` JSONL through a bounded queue. A full
queue drops telemetry instead of blocking ALAS. The summary reports recorded,
dropped, invalid, and writer-error counts.

The semantic transport now records these opt-in measurements:

- observer endpoint RTT and response bytes;
- observer generation and snapshot `age_ms` as a separate value;
- classified ADB operation latency without arguments or command output;
- semantic session open/close and error type.

Backend implementations use `lifecycle_span()` for the standard provision,
start, readiness, recovery, and stop phases. Host/Android/game samplers emit a
common `RuntimeProcessSample`, while future ALAS task hooks use
`alas_action_span(method, task_phase)`. This fixes field semantics now without
inventing workload-dependent sampling rates.

Sensitive field names such as account, token, password, cookie, phone, email,
credential, and secret are rejected. Exception messages are not persisted.

Example:

```python
from pathlib import Path

from alas_headless import AlasSemanticSession, RuntimeTraceRecorder

trace = RuntimeTraceRecorder(Path("evidence/runtime-trace.jsonl"), enabled=True)
session = AlasSemanticSession(
    serial="127.0.0.1:5555",
    driver_revision="0" * 40,
    trace=trace,
)
try:
    session.open()
finally:
    session.close()
    trace.close()
```

The example revision is illustrative; live use remains subject to all existing
package, driver, observer, foreground, freshness, and action-budget gates.

## Atomic observer reads

`SemanticOracle.read_state()` first requests `GET /v1/state`. A valid response
must contain snapshot and Button data from exactly the same generation. An
older observer may explicitly return `status=bad-request`, in which case the
controller uses the previous two-endpoint compatibility path and its bounded
generation-coherence rule. Other malformed combined responses fail closed. The
main-line endpoint reduces two socket round trips to one; it does not yet change
the observer's refresh cadence. Request-driven refresh scheduling remains a
separate change that needs live stability and idle-cost evidence.

Foreground parsing recognizes both Android `topResumedActivity` and older
`mResumedActivity` markers; it does not accept a merely focused or visible
background activity.

## Offline evidence index

The indexer scans only roots explicitly supplied by the operator. A manifest is
admitted only when it contains:

```json
{
  "gate": "G3",
  "outcome": "pass",
  "captured_at_utc": "2026-08-11T00:00:00Z",
  "runtime_fingerprint": {
    "backend": "kvm",
    "host_class": "linux-x86_64-kvm",
    "android_fingerprint": "...",
    "game_version": "...",
    "game_abi": "x86_64",
    "libil2cpp_sha256": "...",
    "angle_sha256": "...",
    "observer_schema": "alas-headless.observer/v1",
    "core_commit": "...",
    "runtime_lock_sha256": "..."
  }
}
```

Run it with:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/index_runtime_evidence.py `
  --root evidence/kvm `
  --root evidence/redroid `
  --output out/runtime-status.json `
  --markdown out/runtime-status.md
```

The newest result is selected per gate and exact fingerprint. The immutable
runtime-lock SHA is part of that fingerprint, so two uncommitted patch trees or
provision/resource generations cannot overwrite each other merely because
their Git commit and Android/game identities match. Evidence from a different
backend, game, ANGLE, Android, observer, core revision, or lock is never used to
overwrite another environment's status. Legacy manifests without the complete
fingerprint are reported under `rejected`; they are not guessed into a group.

## Deliberately deferred

No current code chooses final vCPU count, MTTCG, affinity, NULL refresh rate,
Unity worker count, unpaced execution, Android service removal, instance
density, root governor, or PGO workload. Those decisions require the first
repeatable real ALAS task slice and its trace.

The next implementation milestone is to replace one plan-only adapter at a
time with a reproducible provisioner, beginning with Redroid image and `/data`
ownership or ARM64-QEMU recovery after the corresponding host is available.
Separately, the first repeatable harmless ALAS task slice can start using these
same manifests and traces without mixing backend branches or artifact
generations. No live KVM or phone qualification is claimed by this code-only
milestone.
