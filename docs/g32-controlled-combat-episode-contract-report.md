# G32 controlled combat episode contract

## Outcome

G32 adds a fail-closed evidence contract for one ordinary live battle, but it
does **not** claim a completed live episode or hand production control to the
observer. The original pinned ALAS owns login, campaign branch selection, and
the `_goto()` prefix up to its exact `device.click(grid)` statement. The
qualification harness still sequences post-click preparation/result actions
explicitly, so `live_post_click_alas_state_machine_owner=false` and
`production_enabled=false` are mandatory record fields.

The first live acquisition attempt exposed a real input-boundary defect before
any battle was started. ALAS selected 12-4 enemy B3 from fleet 1 at D3, but the
cell center reported `raycast_top=false`. Temporarily accepting that coordinate
opened the map's `制空权确保` information panel instead of moving the fleet. The
map-cell gate now again requires exact top-raycast actionability, with a
regression test for HUD-covered cells. The invalid run produced no acquisition
receipt, no combat action receipt, and no post-map proof.

## Contracts added

- A versioned G32 acquisition receipt binds the one grid input to its complete
  pre-combat map, route, cell geometry, ALAS `_goto()` call order, PID, raw
  trace SHA-256, sample count, and first/last generations.
- The episode verifier requires three consecutive checked-in S-result frames
  for both battle status and experience, rejects alternate-grade ambiguity and
  active qualified blockers, and never emits a mapping promotion draft.
- Every post-click action receipt must use a qualified original-ALAS resource
  and action variant, an increasing same-PID generation pair, stable in-bounds
  geometry, and the exact bounded optional-phase ordering.
- The final map checkpoint must retain stage/topology/current-fleet identity,
  move the admitted fleet from route origin to target, remove the exact enemy,
  and prove ammunition decreased exactly once.
- A short-lived immutable package-process lease can replace repeated expensive
  APK hashing only after a fully parsed, identity-bound recent raw trace. ADB
  commands have explicit bounded timeouts, and recorder/watch loops treat
  transient transport failures as rejected samples rather than false evidence.
- The canonical integration patch brackets the original `LoginHandler` with a
  semantic login context. It does not replace the handler loop.

## Live diagnostics

- Device: `emulator-5580`, cold-restarted AVD `alas_game_api32_x64`.
- Game launch retained Unity's required Intent extra `-force-gfx-st`.
- Fresh read-only preflight: `artifacts/g32-post-restart-preflight-r3.trace.json`,
  PID `3366`, 20 coherent samples, generations `566..663`, zero rejected
  endpoint triples.
- The original login handler reached the main UI, closed the bulletin, entered
  campaign, and resumed 12-4 under semantic input.
- ALAS's original decision selected branch `battle_0`, fleet 1, target B3, and
  route `D3,C3,B3`.
- Diagnostic trace
  `artifacts/g32-controlled-acquisition-r12.trace.json` captured the mistaken
  HUD-covered coordinate. It is negative evidence only and is not accepted by
  the G32 episode verifier.
- A controlled package restart removed that transient panel. The cleanup
  preflight captured three coherent input-free samples at generations
  `411..431` on new PID `20379`, with zero endpoint rejects or duplicates.

## Remaining boundary

The next step is a typed campaign-viewport movement contract. It must let
ALAS's existing `in_sight()` / `focus_to_grid_center()` logic request a map
swipe, translate only that final gesture through the semantic adapter, and
prove from a fresh same-PID map model that the intended cell moved coherently
into an exact top-raycast position. Only then should the original `_goto()`
loop continue into combat. Broad raw `swipe` remains rejected.

Until that proof and a complete positive episode exist, coverage remains
canonical `16/41`, defensive `18/54`, actions `12/38`, blockers `1/4`, and
`production_ready=false`. The full Python suite passes `351/351`, and the
canonical ALAS integration patch applies cleanly to pinned commit `81ccf63`.
