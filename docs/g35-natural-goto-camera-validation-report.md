# G35 natural `_goto()` camera validation

## Outcome

G35 passes the natural out-of-sight camera gate. After a separate
qualification-only setup placed the camera at F3, pinned ALAS independently
ran `battle_0` again, selected the same fleet 1 and enemy F6 route, and entered
its original `_goto(F6)` method. `_goto()` itself called `in_sight()`, which
requested `focus_to(F4)` and owned the resulting camera gesture and update.

The canonical ALAS state machine is unchanged. Headless code supplies a typed
Unity `View` at the existing `_update_view()` input boundary and validates the
final guarded input ports. The run reaches ALAS's original
`device.click(grid)` statement, but captures it without delegating the grid
click. `grid_input_injected=false` and `production_enabled=false` remain hard
evidence fields.

## Qualification-only camera setup

F6 was already inside `_walk_sight` after G34, so a natural `_goto()` camera
branch required an out-of-sight starting view. G35 adds an explicit-only setup
contract with these restrictions:

- The budget defaults to zero and has no environment-variable production
  opt-in. Only an explicitly constructed qualification session can grant one
  or two gestures.
- The target must be one exact empty sea cell. Land, enemy, fleet, and pickup
  cells are rejected. F3 is an empty sea cell in pinned 12-4.
- Every gesture must still originate in original ALAS
  `focus_to -> map_swipe -> _map_swipe -> device.swipe_vector` and pass the
  existing same-map projective movement proof.
- Original `focus_to(F3)` may use a second correction after observing the first
  real movement. The contract permits at most two, requires the final typed
  camera state to expose F3 exact top-raycast, then explicitly completes the
  setup and clears any unused budget.
- The setup context is closed. A fresh map is acquired and original ALAS
  decision logic runs again; generation is allowed to advance, but branch,
  fleet, target, expected result, route, and optimized goto nodes must be
  unchanged.

## Live evidence

- Device serial: `emulator-5580`; game PID: `28206`.
- Accepted record: `artifacts/g35-natural-goto-camera.json`; source log:
  `artifacts/g35-qualifier-live-2.log`.
- The accepted setup moved camera F4 -> F3 with original ALAS vector `(0,-1)`
  and gesture `(638,472) -> (638,541)` over 370 ms. Its observer generations
  were `38998 -> 38999 -> 39010`; original `Camera.update()` observed F3 at
  generation `39024`.
- After the setup context closed, ALAS again selected `battle_0`, fleet 1,
  enemy F6, full route `E8,E7,E6,F6`, and optimized goto node F6.
- Original `_goto(F6)` began from camera F3. With pinned
  `_walk_sight=(-3,0,3,2)`, the target delta `(0,3)` produced the exact natural
  camera request `(0,1)` to F4.
- The natural gesture was `(870,434) -> (870,317)` over 413 ms, at observer
  generations `39032 -> 39034 -> 39056`. All 68 logical cells remained
  identical; median projected movement was `(2.640,-118.310)` pixels and the
  maximum projective residual was `0.001030` pixels.
- Original `Camera.update()` observed F4 at generation `39072`. Original
  `_goto()` then continued through centering, global-to-local conversion, and
  its final grid-click statement. F6 was freshly rebound to the exact
  top-raycast path at `(639.825,550.117)` immediately before interception.
- The accepted call order starts with `_goto` and contains
  `_goto -> in_sight -> focus_to -> device.swipe_vector -> update ->
  _update_view -> convert_global_to_local -> target_recheck -> device.click`.
- A separate input-free post-run trace captured eight coherent samples at
  generations `39424..39436` on the same PID with zero endpoint rejects.

The first setup attempt is retained as negative evidence in
`artifacts/g35-qualifier-live-1.log`. Starting at F6, original
`focus_to(F3)` requested `(0,-3)`, but its fresh typed update correctly
observed only F4 and requested a second `(0,-1)` correction. The then one-input
setup proxy rejected that second input before injection. That attempt injected
one camera-only gesture, no grid click, and motivated the bounded two-gesture
completion contract; no movement or combat claim depends on hiding it.

## Remaining boundary

G35 closes the organically `_goto()`-initiated camera branch, but it still
does not move a fleet. The next gate should authorize the freshly rechecked
final grid click and then leave original ALAS in control of its complete
post-click wait/combat/result/map-mutation loop. The adapter may replace only
typed observations and guarded input dispatches; it must not recreate those
loops in a harness or claim production readiness from the older controlled
episode replay.

Grid-edge camera correction, the live post-click state-machine handoff,
combat, repeated sorties, and the campaign-menu no-op transition race remain
open. The full Python suite passes `384/384`; the canonical integration patch
still applies cleanly to pinned ALAS `81ccf63`.
