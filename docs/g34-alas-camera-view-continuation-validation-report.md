# G34 ALAS camera-view continuation validation

## Outcome

G34 passes the next qualification gate: after one typed camera gesture, the
original pinned ALAS `Camera.update()` consumes a Unity-derived `View`, updates
its camera coordinate, and returns control to the original `_goto()` target
recheck. The run reaches ALAS's existing `device.click(grid)` statement, but
captures that call without delegating it to Android.

The ownership boundary remains narrow. The canonical patch changes only
`Camera._update_view()` while a semantic session is active; it supplies the
grid geometry that ALAS normally derives from a screenshot. It does not replace
`Camera.update()`, its wait loop, swipe prediction, centering decisions,
global-to-local conversion, `_goto()`, or the campaign battle state machine.

The proof records `grid_input_injected=false` and
`production_enabled=false`. The one injected input was the already-authorized
camera swipe, not a fleet movement or combat click.

## Typed camera input

- The adapter takes a fresh same-PID `CampaignMapState` after the swipe and
  requires its logical signature to match both the pre-swipe state and combat
  admission.
- A normalized planar homography maps logical cell coordinates to exact Unity
  quad centers. Inverting it at ALAS's `SCREEN_CENTER` yields the actual camera
  cell, fractional center offset, and adjacent-cell swipe calibration.
- The typed `View` implements only the grid lookup, selection, projection, and
  observed-swipe surfaces consumed by the original camera code. Enemy, siren,
  boss, mystery, and fleet flags come from the typed map projection; no OCR or
  screenshot classification is reintroduced.
- Edge-camera observations remain fail closed because the current semantic
  surface does not expose the exact rendered map boundary needed by ALAS's edge
  correction flags.
- ALAS's swipe whitelist is preserved as a preferred candidate set. Its
  documented fallback to the padded safe box is now reproduced exactly, while
  endpoints outside that domain and paths crossing the blacklist remain
  rejected before input.

## Live evidence

- Device serial: `emulator-5580`; game PID: `28206`.
- Qualification record:
  `artifacts/g34-campaign-viewport-continuation.json`; source log:
  `artifacts/g34-qualifier-live-5.log`.
- ALAS selected enemy F6 for fleet 1 with full route `E8,E7,E6,F6`.
- The typed camera model observed F4 with center offset
  `(0.603997,0.518081)` and requested grid vector `(0,2)`.
- The original ALAS input chain selected `(539,497) -> (553,296)` over 358 ms.
  Observer generations were `29085 -> 29086 -> 29097`.
- All 68 logical cells retained the same signature. Their median movement was
  `(18.200,-189.419)` pixels with maximum projective residual
  `0.000792` pixels.
- Original `Camera.update()` then observed F6 with center offset
  `(0.501242,0.604426)` at generation `29110` and retained its own update and
  coordinate logic.
- Original `_goto()` subsequently executed the low-HP query, fleet ensure,
  `in_sight`, centering check, global-to-local conversion, ambush/search color
  initialization, and its own `device.click(grid)` statement. The target was
  rebound to the fresh exact top-raycast F6 path before that statement.
- The final call was intercepted: `grid_input_injected=false`, the campaign
  combat budget remained unspent, and no post-click combat chain ran.
- A separate input-free post-run trace captured eight coherent samples at
  generations `29309..29321` on the same PID with zero endpoint rejects.

## Qualification boundary

F6 was already inside ALAS's `_walk_sight`, so this harness deliberately uses
the original `focus_to(F6)` as a qualification prelude to create the one
bounded camera gesture. The subsequent view update and target recheck are
owned by the original camera and `_goto()` implementations, but G34 does not
claim an organically out-of-sight `_goto()` initiated the swipe.

The next gate should keep the same rule: replace inputs, not ALAS state-machine
logic. It must exercise an out-of-sight target through the natural `_goto()`
camera branch, or safely authorize the rechecked final grid click and let the
original post-click campaign/combat handlers observe the result. Grid-edge
camera correction, fleet movement, combat, repeated sorties, and the separate
campaign-menu no-op transition race remain open. Production stays disabled.

The full Python suite passes `379/379`, and the canonical integration patch
applies cleanly to pinned ALAS commit `81ccf63`.
