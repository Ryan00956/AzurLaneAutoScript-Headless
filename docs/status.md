# Validation status

Status is evidence-scoped. A later gate is not implied by an earlier pass.

## 2026-08-08

### G0 - baseline capture tooling: implemented and exercised

- `capture-g0.ps1` completed against `127.0.0.1:16384` and
  `com.bilibili.azurlane` without failed commands.
- The evidence manifest's file sizes and SHA-256 values were independently
  rechecked.
- The live process mapped native x86_64 `libunity.so`, `libil2cpp.so`, EGL,
  GLES, and Vulkan/emulation libraries.
- This is environment provenance, not proof of the active game renderer. A
  separate same-host SwiftShader comparison now exists for the G2 Unity
  contract, but it is not a same-guest game baseline for MuMu.

### G1 - NULL GLES contract: passed on the validation host

- ANGLE is pinned to `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- The x86_64 Android driver APK builds with only the NULL renderer enabled.
- The Android loader successfully selects the custom package for only the
  contract probe package.
- A final 3,600-second run passed shader/program, buffer, texture, FBO, query,
  draw, fence, direct readback, PBO readback, swap pacing, and logical surface
  checks.
- Observed identity: `Google Inc. (NULL)` / `ANGLE (NULL, NULL, )`.
- Observed surface: `1280x720`; direct and PBO RGBA: `00000000`.
- The final heartbeat reported 219,300 frames at 60.000 FPS. The 121 memory/CPU
  samples showed PSS falling from 94,703 KiB to 74,355 KiB and RSS falling from
  176,380 KiB to 153,348 KiB. The post-warm-up PSS trend was approximately
  +2 KiB/minute, with no monotonic growth.
- Coarse `top` samples reported 0.73% mean CPU, 4% p95, and 4% maximum.
- No fatal signal, Android Runtime fatal, or context-loss marker was found in
  the captured process logs.
- Driver and probe APK hashes revalidated against the manifest. All modified
  Android ANGLE settings were restored to their original unset state, and the
  game PID remained unchanged throughout the package-isolated test.

See the [G1 validation report](g1-validation-report.md) for artifact hashes,
evidence scope, and remaining limitations.

### G2 - Unity contract and software baseline: passed

- The contract was built with Unity `2022.3.62f3` changeset `96770f904ca7`,
  IL2CPP, and x86_64 only. The final APK SHA-256 is
  `94ee95a8a6988c6b360047c66739cace3e1201e7b389b6d0e61503284ffeb696`.
- The original package-isolated 80-second functional run used
  `ANGLE (NULL, NULL, )`, OpenGLES3, and a `1280x720` logical surface.
- `Update`, `FixedUpdate`, `WaitForEndOfFrame`, animated UI state, five scene
  transitions, and app pause/resume all advanced without process restart.
- A safe test-button click changed its semantic marker from `contract/button`
  to `contract/button-clicked` with generation 2.
- All 15 AsyncGPUReadback requests completed with 1,024 zero-filled bytes;
  there were no errors or timeouts.
- The run produced 31 structured events and six heartbeats. The final heartbeat
  reported 1,800 updates, 3,365 fixed updates, and 1,799 end-of-frame resumes.
- PSS/RSS changed from 160,195/243,128 KiB to 154,475/238,372 KiB. Coarse
  process CPU samples averaged 5.87% with an 8% maximum.
- No fatal signal or context-loss marker was found. APK hashes matched the
  manifest, all ANGLE settings were restored, the test process was stopped,
  and the game PID remained `7547`.
- The software comparison used Android Emulator `37.1.11`, the same API 32
  x86_64 AVD/image, identical Unity APK and `1280x720` surface, and separate
  cold QEMU processes for official `-gpu swiftshader` and package-routed NULL.
- SwiftShader and NULL both passed the full functional contract. Host QEMU
  sustained CPU fell from 2.0551 to 0.5178 core equivalents (-74.8%). CPU time
  per 1,000 Updates fell 71.6%, so the advantage remains after accounting for
  the NULL leg's lower Update count.
- Host QEMU median working set fell 9.54%; Android app median PSS/RSS fell
  7.67%/4.83%. The fail-closed comparison manifest passed with no failures.
- Final evidence is in
  `evidence/g2-system-20260808T111131Z-emulator-5570`,
  `evidence/g2-null-20260808T111610Z-emulator-5570`, and
  `evidence/g2-comparison-20260808T112155Z`.

See the [G2 validation report](g2-validation-report.md) for the evidence scope.

### G3 - Observer contract: passed on the Unity contract workload

- The ANGLE component found all 32 allowlisted IL2CPP exports through the
  in-memory ELF dynamic table despite Android linker-namespace isolation;
  `RTLD_DEFAULT`, soname `RTLD_NOLOAD`, and full-path `RTLD_NOLOAD` remained
  unavailable.
- The unmodified Unity Android activity accepted the `unity` Intent extra
  `-force-gfx-st`. NULL Surface Swap and managed `Update()` then executed on
  the same Unity main-thread TID.
- Main-thread typed snapshots used Unity liveness enumeration for
  `UnityEngine.UI.Button`, fixed getter invocation, active scene handles, and
  monotonic snapshot/scene/semantic generations.
- A local abstract Unix socket exposed only `GET /v1/snapshot`, checked
  `SO_PEERCRED`, rejected an arbitrary invocation-shaped request, and returned
  a fixed `alas-headless.observer/v1` schema.
- The safe contract click changed one active Button from interactable to
  non-interactable and advanced semantic generation. A later scene transition
  advanced scene generation.
- Pressing Home changed the top-resumed package to Launcher and made the last
  snapshot stale. The action gate stayed closed; resuming restored a fresh,
  higher-generation snapshot.
- The observer also exposes `GET /v1/buttons` with fixed schema
  `alas-headless.buttons/v1`, bounded records, full hierarchy paths, Canvas
  identity, state flags, screen/ADB points, and four-corner RectTransform
  bounds. It exposes no object addresses or generic invocation.
- Final G3 evidence with bounds and top-raycast validation is
  `evidence/g3-observer-20260808T172655Z-emulator-5570`; its manifest passed
  with no failures. The final observer ANGLE and Unity APK SHA-256 values are
  `ac5c9bd696badd7d9b3bd62cce27c74acf474808f712ab78632be91b9e5c33bf`
  and `87e845359bc1d957b0c75f685f461b017ed6e05d0a593088683511400e8e99ba`.
- A final 46.745-second G2 regression with the 32-symbol, typed-bounds,
  reviewed-target raycast observer passed in
  `evidence/g2-null-20260808T173503Z-emulator-5570`: 600 Updates, 1,871
  FixedUpdates, 599 end-of-frame resumes, eight completed readbacks, and zero
  readback errors.

See the [G3 validation report](g3-validation-report.md) for evidence scope and
remaining limitations.

### G4 - harmless real-game closed loop: passed; ALAS task coverage remains open

- After the user completed agreement and account login, Chinese 9.7.10 reached
  its login/main Unity UI on the dedicated API 32 x86_64 AVD under NULL.
- A 120-second no-input run produced 120/120 structurally valid samples,
  113 fresh samples, generations 2 through 99, and 98 distinct generations;
  no fatal marker was found.
- The game exposed exact paths and bounds for login and the main-page battle,
  formation, settings, mail, shop, dock, task, and build Buttons.
- The action runner clicked only the exact login target, waited for an exact
  `battle` postcondition, detected and dismissed the known bulletin overlay,
  entered settings at `(1221,36)`, observed 23 settings Buttons, clicked the
  exact settings `back_btn` at about `(57,54)`, and verified that main
  battle/settings targets and the exact foreground Activity returned. Every
  injected target was independently the top `EventSystem.RaycastAll` result at
  its point (or an ancestor of that result).
- The standard-library Python oracle independently passed a live no-input smoke
  over all 14 reviewed ALAS aliases (seven main semantics), including top
  raycast identity. It checks schema, package, PID, peer UID, driver revision,
  foreground component, freshness, generation coherence, unique path mapping,
  bounds, and known blockers.
- The ALAS-name bridge maps only 14 reviewed aliases for seven main-page
  semantics. It independently verifies version, ABI, base APK, and IL2CPP
  hashes. Unmapped assets and raw multi-click/long-click/swipe/drag calls raise
  instead of injecting coordinates.

Evidence is in
`evidence/g4-game-init-20260808T160921Z-emulator-5580`,
`evidence/g4-game-init-20260808T172750Z-emulator-5580`, and
`evidence/g4-game-init-20260808T172941Z-emulator-5580` (including
`alas-adapter-live.json`). G4 is passed; task-specific semantic coverage is the
next gate. See
the [G4 validation report](g4-preflight-report.md).

## Android loader compatibility found during G1

Android's `GraphicsEnvironment` requests a developer ANGLE package with the
Vulkan platform token even when the application did not choose a renderer.
The NULL-only build therefore needs a narrow loader-token translation before
display construction. It also needs common RGBX Android configs and an
implementation of swap-with-damage used by HWUI. These are maintained as
separate patches so each compatibility behavior remains auditable.
