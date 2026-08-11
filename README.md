# AzurLaneAutoScript Headless

Research runtime for running the native x86_64 Azur Lane Unity client on an Android 10+ guest without a hardware GPU. The project combines a pinned ANGLE NULL-only GLES driver, explicit Android window/frame-pacing behavior, contract probes, and a fail-closed semantic observation provider.

This repository does **not** claim complete ALAS task coverage. The pinned game
now reaches the main UI under NULL, exports typed Button paths and RectTransform
bounds, and has passed a harmless login -> bulletin close -> settings -> back
loop. The controller and ALAS bridge remain opt-in and reject every unmapped
action instead of falling back to black-screen image matching or old
coordinates.

## Current scope

- `G0`: capture a reproducible, read-only Android/game/runtime fingerprint.
- `G1`: build a pinned ANGLE APK with only the NULL backend and run a GLES contract probe.
- `G2`: run an exact Unity `2022.3.62f3` IL2CPP contract project.
- `G3`: validate a main-thread, typed, local semantic observer contract.
- `G4`: route the game only after G3, then validate a harmless closed loop.
- `G5`: replace one ALAS task flow at a time with stable, fail-closed semantics.

See [acceptance gates](docs/acceptance-gates.md) and [architecture](docs/architecture.md).
The latest evidence-scoped result is recorded in [validation status](docs/status.md).
The completed Android NULL contract run is documented in the
[G1 validation report](docs/g1-validation-report.md).
The Unity IL2CPP functional run is documented in the
[G2 validation report](docs/g2-validation-report.md).
The in-process typed observer contract is documented in the
[G3 validation report](docs/g3-validation-report.md).
The first task-specific ALAS slice is documented in the
[G5 mission validation report](docs/g5-mission-validation-report.md). The
bounded typed UI layer and mission-sidebar closure are documented in the
[G6 semantic UI report](docs/g6-semantic-ui-report.md). The broader typed
reward/task surfaces and read-only campaign slice are documented in the
[G7 adaptation report](docs/g7-task-campaign-adaptation-report.md). The real
ALAS reward double run, bounded commission starts, clean one-budget commission
reward, and typed multipage scan are documented in the
[G8 validation report](docs/g8-alas-reward-commission-validation-report.md).
The bounded patched-ALAS task replays are documented in the
[G9 validation report](docs/g9-alas-task-replay-validation-report.md), and the
reversible campaign entry through fleet preparation is documented in the
[G10 validation report](docs/g10-campaign-pre-sortie-validation-report.md).
The bounded ALAS-owned fleet-selection pass is documented in the
[G11 validation report](docs/g11-campaign-fleet-preparation-validation-report.md).
The separately budgeted single-sortie and real map-entry proof are documented
in the [G12 validation report](docs/g12-campaign-sortie-validation-report.md).
The complete read-only ALAS-backed map model is documented in the
[G13 validation report](docs/g13-campaign-map-model-validation-report.md). Its
transactional projection into native ALAS map objects and read-only path
planning are documented in the
[G14 validation report](docs/g14-alas-map-sync-validation-report.md). The
passive semantic-marker to ALAS fleet-index reconciliation is documented in
the [G15 validation report](docs/g15-campaign-fleet-index-validation-report.md).
The original-ALAS decision preview, separately budgeted combat admission, and
captured original `_goto()` input prefix are documented in the
[G16 validation report](docs/g16-alas-campaign-decision-preview-validation-report.md)
and [G17 validation report](docs/g17-campaign-combat-admission-validation-report.md),
plus the [G18 validation report](docs/g18-alas-goto-input-preview-validation-report.md).
The Device-free replay of ALAS's complete ordinary-combat/result/arrival chain
is documented in the
[G19 validation report](docs/g19-alas-combat-state-replay-validation-report.md).
Its exact raw-Unity input contract and intentionally unqualified live mapping
manifest are documented in the
[G20 validation report](docs/g20-alas-combat-observer-contract-validation-report.md).
The input-free raw trace, candidate-diff, and frozen-fixture acquisition
pipeline is documented in the
[G21 validation report](docs/g21-alas-combat-trace-pipeline-validation-report.md).
The first evidence-bound mapping promotion and compound blocker contract are
documented in the
[G22 validation report](docs/g22-alas-combat-mapping-promotion-validation-report.md).
Controlled combat acquisition and result handling are documented in the
[G23 validation report](docs/g23-alas-controlled-combat-acquisition-validation-report.md),
combat preparation in the
[G24 validation report](docs/g24-alas-combat-preparation-observer-validation-report.md),
and automation switching, radar search, and ordered fleet statistics in the
[G25 validation report](docs/g25-alas-combat-input-closure-validation-report.md).

G1, G2, G3, and the formal G4 harmless closed loop passed. G4 includes
EventSystem top-raycast proof for every injected target, not only object state
and RectTransform bounds. G5a passed the real ALAS mission-reward no-claim
branch. G5b then passed one controlled `GetAllButton` claim: three claimable
rows became zero, the exact `AwardInfoUI` close target was verified, five
unfinished rows remained stable, and main returned. Automatic mission claiming
requires a second explicit environment opt-in. Commission now has bounded live
mutation slices: independent integer budgets admitted bounded zero-oil starts
and one clean same-context finished reward proof. The earlier reward's original
command remains recovery-qualified after an observer-capacity failure. The
exact commission scrollbar also passed a five-row ALAS multipage scan without
enabling generic gestures. Tactical course assignment and bounded research
reward/start now have live passes while preserving the original ALAS state
machines. Dorm collect and corrected food-card input have live passes, as does
one bounded heavy-pool construction submit with a typed queue countdown. All
of these mutations remain default-closed and single-invocation qualified.
Complete patched commands now pass for Tactical, Research, and Dorm. Gacha's
warning/order phases are separately typed after a first full replay exposed a
phase-alias bug; its corrected full replay still requires an empty queue.
Campaign stage entry and fleet selection have independent default-zero
budgets. The live G11 pass preserved ALAS's original fleet-preparation state
machine, reconciled `(1, 2, 1) -> (1, 2, 0)` with exactly three mutations,
then canceled and independently proved `(1, 2, 1)` restored. G12 separately
admits exactly one default-closed sortie after typed fleet/settings/oil proof,
then stops at the real read-only `LevelGrid` map identity. G13 builds a stable
`11x8` model from ALAS topology plus complete Unity Button/Image/Text state,
including both fleets, enemies, and the ammunition pickup. ALAS consumes that
model at its existing already-in-map checkpoint and returns before retreat;
there is still no map input. G14 validates that model against a deep-copied
native ALAS `CampaignMap`, reuses `map_data_init()` and the native path finder,
and emits deterministic per-marker reachability summaries. G15 then proves the
displayed marker from the exact top-stage fleet number and current roster,
including ALAS's reversed-fleet rule, and populates native indexed locations.
Movement remains structurally closed because the patched runner stops before
`goto()`. G17 defines a default-zero, decision-bound exact grid-input lease and
post-battle proof. G18 now runs ALAS's original `_goto()` retreat/fleet/camera/
conversion prefix on an isolated shell and captures its own
`device.click(grid)` call without spending that lease or injecting input. The
G19 qualification then drives ALAS's original combat preparation, execution,
status, enemy-searching, arrival, and native-map mutation logic with six
strict typed replay phases and four virtual actions. G20 can reconstruct those
phases only from six complete, hash-bound raw Unity snapshots and an exact
38-resource mapping; it rejects fixture phase labels. G21 makes that gap
operationally fillable through a versioned mapping manifest, package-verified
raw trace recorder, exact six-generation selection, and offline map/fixture
compilation. G22 evidence-binds the first real `IN_MAP` mapping and an exact
compound `network_down` blocker across three complete raw frames. G23-G25 then
qualify the ordinary result chain, automation confirmation/switching, battle
start, radar search, and ordered six-ship HP/levels while original ALAS remains
the behavioral owner. G26 then separates the canonical path from the defensive
input union. G27 closes two omitted true-branch queries, supports mutually
exclusive Unity variants for one original-ALAS action target, and pins ambush,
retirement, and story branch roots without replacing their handlers. Current
coverage is canonical `16/41`, defensive `18/54`, actions `12/38`, and blockers
`1/4`; branch and blocker review remain incomplete, so production remains at
the G18 capture boundary. G28 separately replays 16 rare result, popup,
retirement, story, and ambush paths through their original ALAS methods with
virtual inputs and source-hash binding. It confirms control-flow ownership but
does not promote live Unity mappings. G29 adds a zero-input, three-frame
rare-dialog watcher for guild and mission button pairs. Its first real map run
is a verified negative observation, so it emits no review draft and changes no
mapping. G30 extends the same non-applying acquisition boundary to passive A-D
battle grades and A/B experience pages, with their structure bound to the
qualified S mappings. Its fresh six-profile map scan is also negative, so
coverage is unchanged. G31 combines those eight dialog/result profiles into a
single non-applying watcher with deterministic one-match dispatch and
multi-match rejection. G32 adds a hash-bound controlled-episode verifier,
same-PID process leases, checked S-result positive controls, and original-login
bracketing. Its first live acquisition correctly remains incomplete: an ALAS
selected B3 center was covered by the map HUD, and accepting its non-top
raycast coordinate opened the air-supremacy information panel. Map cells now
fail closed again. G33 now qualifies one typed ALAS-requested viewport movement:
the original camera path requested `(1, -2)`, the adapter translated only its
final swipe, all 68 logical cells moved coherently under a projective model,
and F6 ended exact top-raycast. G34 now supplies a typed Unity `View` only at
ALAS's existing `_update_view()` input boundary. The original `Camera.update()`
then updates F4 to F6 and the original `_goto()` rechecks the fresh target,
centers it, converts global to local, and reaches its own `device.click(grid)`
statement. That final click is captured without injection, so production stays
disabled. Because F6 was already within `_walk_sight`, the qualifying gesture
was initiated by an original `focus_to(F6)` prelude; a natural out-of-sight
`_goto()` camera branch remains unclaimed. Lua/game-state coverage,
formation-layout changes, campaign movement execution, battle state,
weekly-only end-to-end
coverage, repeated sorties, and full unattended ALAS task coverage remain
open.

## Repository layout

- `ANGLE_REVISION` pins the upstream ANGLE checkout used by every build.
- `patches/angle` contains the base NULL-renderer compatibility patch series.
- `patches/angle-g3` and `overlays/angle-g3` contain the observer patch series
  and the new source files installed before that series is applied.
- `probes/gles-contract` and `unity/HeadlessContract` are the Android GLES and
  Unity IL2CPP contract workloads.
- `python/alas_headless` is the fail-closed controller library;
  `scripts/python` contains live probes and `tests` contains its unit tests.
- `scripts/wsl` owns ANGLE bootstrap/build steps, while `scripts/windows` owns
  ADB execution, capture, and comparison steps.
- `integration/alas` is the opt-in, commit-pinned upstream ALAS integration
  patch. `docs` contains contracts, validation reports, and current status.

Generated APKs, extracted game files, raw captures, and Unity/Gradle build state
stay local under ignored paths such as `artifacts`, `evidence`, `Build`, and
`Library`. Durable results belong in `docs` with hashes and evidence paths, not
as large binaries committed to Git.

## Host layout

ANGLE must be built on Linux. On Windows, the supported path is WSL2:

```text
Windows workspace: H:\program\AzurLaneAutoScript-Headless
WSL build cache:   ~/src/alas-headless-angle
```

Bootstrap and build commands are run from WSL, while APK installation and evidence capture may be run through Windows ADB.

## Quick start

From WSL:

```bash
cd /mnt/h/program/AzurLaneAutoScript-Headless
./scripts/wsl/bootstrap-angle.sh
./scripts/wsl/apply-angle-patches.sh
./scripts/wsl/build-angle-null.sh
./scripts/wsl/build-gles-contract.sh
./scripts/wsl/apply-angle-g3-patches.sh
./scripts/wsl/build-angle-null-observer.sh
```

The bootstrap and build scripts do not route a game package. The separate G4
runner does so only when explicitly invoked, requires the pinned game
fingerprint, refuses to restart an already-running game by default, and restores
all ANGLE settings afterward. Input is disabled unless exact semantic target and
postcondition arguments are supplied.

The Unity contract is version-locked and intentionally refuses any editor other than
`2022.3.62f3`. Build it with that editor's executable:

```powershell
Unity.exe -batchmode -quit `
  -projectPath H:\program\AzurLaneAutoScript-Headless\unity\HeadlessContract `
  -executeMethod Alas.Headless.Contract.Editor.BuildAndroidPlayer.Build `
  -logFile -
```

The resulting player is x86_64, IL2CPP, and written to
`unity/HeadlessContract/Build/HeadlessContract.apk`.

The G3 runner launches the contract with Unity's supported `unity` Intent extra
and `-force-gfx-st`, then validates the typed local socket and negative gates:

```powershell
.\scripts\windows\run-g3-observer.ps1 `
  -Serial emulator-5570 `
  -AngleApk <observer-AngleLibraries.apk> `
  -UnityApk .\unity\HeadlessContract\Build\HeadlessContract.apk
```

The G4 runner expects an already installed, pinned Chinese 9.7.10 package. A
read-only sustained run is still the default:

```powershell
.\scripts\windows\run-g4-game-init.ps1 `
  -Serial emulator-5580 `
  -AngleApk <observer-AngleLibraries.apk>
```

Semantic clicks require exact name/path mappings and expected postconditions;
unknown or ambiguous targets fail closed. See the
[G4 validation report](docs/g4-preflight-report.md) for the tested harmless loop
and evidence scope.

The controller package and its tests are independent of ALAS:

```powershell
$env:PYTHONPATH = 'python'
python -m unittest discover -s tests -v
```

The staged ALAS integration overlay targets upstream commit
`81ccf63b4540f00241628c82a58c02c7a2bb11af`; see
[integration instructions](integration/alas/README.md). The reviewed mission
inputs now feed ALAS's original reward state machine rather than replacing it.
Claiming remains disabled by default; one `GetAllButton` mission claim per ALAS
invocation is available only through the separate controlled-claim opt-in. The
observer now also exposes typed Toggle, Text, TextMesh Pro, and Image records
through `GET /v1/ui`. Exact task-sidebar selected sprites and top-raycast input
have a live adapter-level pass. Reward summary counts, commission rows,
tactical slots/books/skills, research cards/detail/queue, construction
navigation/pool/cost/queue, dorm summary/feed, and visible campaign labels use
typed state rather than OCR. A real patched ALAS
checkout also passed reward twice with zero claims, a commission dry run, two
separately budgeted zero-oil starts, and zero-budget idempotency passes. The
first commission reward remains recovery-qualified after a fail-closed
64-record observer-capacity fault. A later natural completion cleanly produced
an in-context `1 -> 0` proof with the reviewed popup chain and a second
dual-budget-zero replay. The five-row daily list also passed exact typed
scrollbar scanning and stable row-index deduplication. Complete unattended ALAS
execution awaits task-by-task live qualification.

The campaign slice now also has a decision-only pinned pass: the typed indexed
map is given to ALAS's original `battle_function()`, and the first public
`goto()` is recorded and aborted. For the qualified `12-4` state ALAS selected
`battle_0`, fleet `1`, and the fighting enemy at `D6`; no movement, combat,
retreat, or map reward input is enabled. See the
[G16 validation report](docs/g16-alas-campaign-decision-preview-validation-report.md).
G17 binds that decision to one exact default-closed D6 combat lease, and G18
runs the original `_goto()` prefix through its exact click statement using
typed fleet/camera/grid observations. The click is captured before dispatch,
so this remains a zero-input preflight rather than a movement or battle pass.
G19 separately replays the full original combat chain without a Device:
ALAS advances battle `0 -> 1`, ammunition `5 -> 4`, clears D6, confirms arrival,
and rebuilds paths while all four intended actions remain virtual records.
