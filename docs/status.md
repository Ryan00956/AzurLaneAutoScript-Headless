# Validation status

Status is evidence-scoped. A later gate is not implied by an earlier pass.

## 2026-08-09

### G8 real ALAS reward and commission slice: bounded recovery pass

- A clean checkout of pinned upstream ALAS commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af` completed the real `Reward`
  command twice. Both runs observed typed claimable state and stopped before
  claim because the mission claim budget was zero.
- The real `Commission` command completed once with start budget zero. ALAS
  scanned typed rows, applied its existing `cube` preset, selected three daily
  candidates, and stopped before row input.
- Two separately bounded start invocations selected `高阶战术研发II` and
  `高阶战术研发I`. Each revalidated the exact typed row/detail identity, assigned
  ships, zero oil cost, and one remaining budget unit before one input. Their
  post-states were proved with the matching identity, decreasing countdown,
  exact `tag_ongoing` marker, and `取消` action label. No third start was made.
- The second positive run returned from the proven detail to the list, then a
  redundant ALAS tab reset encountered a transient truncated Image snapshot.
  Complete transition reads now receive a bounded retry, and the pinned patch
  skips that reset once the independent start budget is exhausted.
- When `高阶战术研发I` finished, a separate integer reward budget of one admitted
  the exact commission finish input only after the typed finished counter was
  read as `1` twice, including immediately before the click. ALAS then closed
  the reviewed ship-EXP and award popups.
- That original reward command did not finish its proof: the combined reward
  and award view filled the observer's 64-Button buffer and correctly failed
  closed as truncated. The native capacity was raised to 128 and rebuilt. After
  a `-force-gfx-st` restart, the snapshot was complete at 58/128, the exact
  finished counter was `0`, and a full reward/start-budget-zero `Commission`
  replay returned successfully without a second claim or a third start.
- The remaining running commission was parsed as `1/4` and scheduled for
  `2026-08-09 16:52:07`. This is a recovery-qualified live claim, not a claim
  whose original command produced an in-context `CommissionRewardProof`.
- Exact `[NetworkDown]` confirm/cancel semantics are build- and unit-validated,
  but no live reconnect input was injected. Larger budgets, nonzero-oil rows,
  cancellation, and unattended repeated starts remain unqualified. See the
  [G8 validation report](g8-alas-reward-commission-validation-report.md).
- Final observer APK SHA-256:
  `111ac661e3ba7d9ff0eebeeb4c803f22226092318b0b43161cfe8506a76c8d1d`.
  The controller suite passes `139/139`; Python compilation, native build,
  diff whitespace, and clean pinned-patch application checks pass.

### G7 typed task surfaces and read-only campaign: passed in reviewed scope

- The typed controller now models the reward dashboard, commission rows and
  empty marker, tactical slots and countdowns, five research cards,
  construction pool/cost, dorm occupancy/food/comfort/floor, and the visible
  campaign chapter/stage labels. Missing, duplicate, truncated, incoherent, or
  contradictory records fail closed.
- The pinned ALAS patch retains the original mission, commission, tactical,
  and research state machines. It supplies typed observation, countdown, and
  safe-popup inputs; the dorm scheduler obtains its occupied-slot count from
  typed state. The patch applies cleanly to upstream commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- Live adapter validation completed exact reward-to-tactical entry, observed
  four empty tactical slots, and returned through the contextual ALAS
  `BACK_ARROW`. Earlier in the same controlled session, four completed
  tactical rewards were received and every exact “continue learning” prompt
  was canceled; no new class was started.
- Live dorm state was `6/6` occupied slots, `0/40000` food, `454` comfort, and
  floor `1`; the exact statistics confirmation and return controls were
  validated. Feeding, collecting, decorating, and ship assignment remain
  unmapped.
- Live construction state was pool `heavy`, `3661` cubes, `2` cubes/build, and
  `1500` coins/build. The ALAS `GOTO_MAIN` alias returned through the exact
  construction `back_btn`; the construction start control remains
  presence-only and cannot be clicked through the adapter.
- Live campaign validation entered only the normal chapter list, read chapter
  `马里亚纳风云上` and stages `12-1` through `12-4` with their typed names,
  then returned. Generic `BACK_ARROW` remained unmapped; no stage, formation,
  sortie, or battle control was clicked.
- The final observer APK SHA-256 is
  `3c05c2bf913464ad7dee7a0e62c4fea3b5919a5c59c6a11d2274c8bd867d6c4e`.
  The controller suite passes `109/109`; Python compilation, diff whitespace,
  native observer build, installation, package fingerprint, and clean pinned
  patch application checks also passed.
- This is not a full unattended ALAS pass. Commission selection/start,
  tactical course assignment, research selection/start, dorm mutations,
  construction submission, campaign stage selection, map control, battle
  control, and Lua state are still closed.

### G6 typed UI and mission sidebar: passed in reviewed scope

- `GET /v1/ui` now exposes bounded, typed Toggle, UGUI Text, TextMesh Pro, and
  Image records. The final live capture reported method mask 15, zero observer
  errors, and no Image truncation.
- Typed text includes UTF-8 content and exact RectTransform bounds. The ALAS OCR
  hook resolves only text inside the requested OCR area and rejects missing,
  overlapping, truncated, malformed, out-of-bounds, and alphabet-invalid
  matches.
- Six exact task-sidebar Image paths expose selected/unselected sprite identity.
  Only those reviewed paths receive native EventSystem top-raycast evaluation.
- A live task-page loop selected weekly, observed `icon_week_sel`, returned to
  all, and exited to main. No reward input was injected by this loop.
- Final observer APK SHA-256:
  `fbc288dbe20e0264e90d522772922b72a24d799888e0804cd47781727475a571`.
  The read-only final capture is
  `evidence/g6-semantic-ui-20260809T030729Z-emulator-5580`; see the
  [G6 validation report](g6-semantic-ui-report.md).

### Post-G5 ALAS state-machine reuse: implemented; full live rerun pending

- The integration patch no longer calls a replacement mission flow from the
  top of `Reward.reward_mission()`. It brackets an adapter context and leaves
  ALAS's original notice, navigation, collect, claim, receive, retry, timeout,
  and daily/weekly ordering in control.
- ALAS reward observations from `appear()`, `match_template_color()`, and
  `image_color_count()` now consume typed semantic input. Normal `click()` is
  translated to reviewed semantic actions; raw coordinate and gesture paths
  remain rejected.
- `MISSION_MULTI`, `MISSION_SINGLE`, `MISSION_UNFINISH`, mission-page identity,
  the default sidebar, and `GET_ITEMS_1`/`GET_ITEMS_2` have explicit adapters.
  A claimable/unfinished state requires the same signature across two
  increasing observer generations.
- The separate environment opt-in now creates a one-claim budget per ALAS
  `reward_mission()` invocation. The budget is discarded in `finally`, and a
  missing opt-in refuses the claim before ADB input.
- Weekly-tab state and exact semantic input are now reviewed and live-proven at
  the adapter boundary. Weekly-only end-to-end execution, positive mission
  red-dot behavior, numeric-row claiming, ship-reward popups, and empty-page
  inference remain closed.
- This refactor has unit coverage and was syntax/lifecycle checked against the
  clean pinned upstream commit. The historical G5 claim evidence below still
  predates this ownership change, so the complete ALAS-owned claim path is not
  yet a new live pass.

### G5a/G5b - ALAS mission no-claim and controlled claim-all: passed

- The final observer evaluates the exact task-page back and `GetAllButton`
  paths plus bounded task-row `get_btn` and `go_btn` shapes. The controller
  accepts only exact numeric row indexes. These targets are subject to the same
  top-EventSystem-raycast gate as earlier actions.
- Mission state must have the same non-unknown signature across at least two
  increasing generations. Duplicate rows, clipped claim controls, blockers,
  and mere absence of task Buttons fail closed.
- The pinned upstream ALAS patch routes `Reward.reward_mission()` through the
  semantic adapter only when semantic mode is explicitly enabled. Claim input
  requires the separate `ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE=1` opt-in.
- G5a entered the exact main task Button, observed five stable unfinished
  `go_btn` rows, returned to main, and injected zero claim inputs.
- G5b's zero-claim preflight observed a unique actionable `GetAllButton` and
  three numeric-row `get_btn` targets, all with top-raycast proof.
- The controlled run injected exactly one claim at `GetAllButton`, observed the
  exact `AwardInfoUI(Clone)/items/close`, closed it, and proved claim rows
  changed from three to zero while five unfinished rows remained stable.
- It then returned through the exact task back Button. An independent second
  task-page run reported `nothing-claimable`, and a no-input main-page oracle
  found no blockers with all eight reviewed targets actionable.

Primary evidence is in
`evidence/g4-game-init-20260809T013349Z-emulator-5580`; see the
[G5 validation report](g5-mission-validation-report.md).

### Final-driver regressions: passed

- Final observer ANGLE APK SHA-256:
  `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7`.
- The real game passed login/main reachability and a 40-second sustained run:
  40/40 valid samples, 36 fresh, generations 2 through 28, and 27 distinct
  generations. This did not repeat the earlier formal settings round trip.
- G3 passed in `evidence/g3-observer-20260809T013932Z-emulator-5570` with the
  exact contract Button raycast, foreground/freshness refusal, and recovery.
- G2 passed in `evidence/g2-null-20260809T014015Z-emulator-5570`: 47.117
  seconds, 20 structured events, three scenes, eight completed readbacks over
  the full run, and zero readback errors.

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
  `evidence/g3-observer-20260809T013932Z-emulator-5570`; its manifest passed
  with no failures. The final observer ANGLE and Unity APK SHA-256 values are
  `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7`
  and `87e845359bc1d957b0c75f685f461b017ed6e05d0a593088683511400e8e99ba`.
- A final 47.117-second G2 regression with the 32-symbol, typed-bounds,
  reviewed-target raycast observer passed in
  `evidence/g2-null-20260809T014015Z-emulator-5570`: 900 Updates, 1,689
  FixedUpdates, 899 end-of-frame resumes, eight completed readbacks over the
  full run, and zero readback errors.

See the [G3 validation report](g3-validation-report.md) for evidence scope and
remaining limitations.

### G4 - harmless real-game closed loop: passed

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
`alas-adapter-live.json`). G4 is passed. The later G5a result covers only the
mission no-claim branch and does not retroactively broaden G4. See the
[G4 validation report](g4-preflight-report.md).

## Android loader compatibility found during G1

Android's `GraphicsEnvironment` requests a developer ANGLE package with the
Vulkan platform token even when the application did not choose a renderer.
The NULL-only build therefore needs a narrow loader-token translation before
display construction. It also needs common RGBX Android configs and an
implementation of swap-with-damage used by HWUI. These are maintained as
separate patches so each compatibility behavior remains auditable.
