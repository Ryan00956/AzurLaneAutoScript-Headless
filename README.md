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
[G5 mission validation report](docs/g5-mission-validation-report.md).

G1, G2, G3, and the formal G4 harmless closed loop passed. G4 includes
EventSystem top-raycast proof for every injected target, not only object state
and RectTransform bounds. G5a passed the real ALAS mission-reward no-claim
branch. G5b then passed one controlled `GetAllButton` claim: three claimable
rows became zero, the exact `AwardInfoUI` close target was verified, five
unfinished rows remained stable, and main returned. Automatic mission claiming
requires a second explicit environment opt-in. Lua/game-state coverage,
campaign maps, battle state, weekly-tab coverage, and full ALAS task coverage
remain open.

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
Claiming remains disabled by default; one `GetAllButton` claim per ALAS
invocation is available only through the separate controlled-claim opt-in. The
ownership refactor is unit/pinned-patch validated and still awaits a fresh live
run.
