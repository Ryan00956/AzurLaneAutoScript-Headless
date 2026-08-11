# G33 campaign viewport validation

## Outcome

G33 passes the qualification gate for one typed campaign-map viewport swipe.
The original pinned ALAS camera path selected enemy F6, called
`focus_to(F6)`, calculated grid delta `(1, -2)`, and reached its existing
`device.swipe_vector()` boundary. The semantic adapter translated only that
final gesture. It did not select the enemy, move a fleet, start combat, or
replace ALAS's campaign state machine.

The accepted proof keeps `production_enabled=false` and
`post_swipe_alas_view_update_owner=false`. Production campaign movement and
the continuation of the original live `_goto()` loop therefore remain closed.

## Ownership and input contract

- The canonical ALAS patch restores its original `handle_auto_search()` call
  before the semantic map-preparation proceed action. On the live run, ALAS
  observed auto-search on, used the exact typed Toggle to turn it off, observed
  it off, and only then clicked proceed.
- The adapter exposes all four original `AUTO_SEARCH_ON*` and four
  `AUTO_SEARCH_OFF*` resource variants. The one action target requires the
  exact current checked state, map-preparation context, top raycast, and a
  one-use action receipt.
- Viewport movement has an independent canonical integer budget and defaults
  to zero. One qualification run sets it to one; unrelated swipe APIs and a
  second swipe remain rejected.
- The request still originates in ALAS's existing camera implementation:
  `focus_to -> map_swipe -> _map_swipe -> device.swipe_vector`. The adapter
  replaces only the final dispatch.
- The qualifier stops immediately after the typed movement proof. It does not
  click F6 or run any synthetic post-click combat sequence.

## Live evidence

- Device serial: `127.0.0.1:5581`; game PID: `28206`.
- Native observer APK SHA-256:
  `7125f8eb697a90932c03b3f9573d526e340a23e654a620a1a0652f0720308471`.
- Three post-deploy G4 restarts passed:
  `evidence/g4-game-init-20260811T063338Z-127.0.0.1_5581`,
  `evidence/g4-game-init-20260811T065532Z-127.0.0.1_5581`, and
  `evidence/g4-game-init-20260811T070444Z-127.0.0.1_5581`.
- Accepted proof: `artifacts/g33-campaign-viewport-proof.json`; source log:
  `artifacts/g33-qualifier-live-16.log`.
- ALAS selected route `E8,E7,E6,F6` and requested a camera delta of `(1, -2)`
  from E8 toward F6.
- The typed gesture was `(603,331) -> (481,507)` over 390 ms, with observer
  generations `3002 -> 3004 -> 3020`.
- All 68 visible logical cells survived with an unchanged map signature. Their
  median displacement was `(-105.163,157.183)` pixels.
- Because the Unity map uses perspective projection, coherence is fitted as a
  normalized planar homography rather than a uniform translation. The maximum
  residual was `0.001125` pixels; singular, collapsed, infinity-crossing, and
  direction-contradicting models fail closed.
- F6 moved from `(735.324,385.720)` to `(625.303,558.046)` and ended at its
  exact Unity path with `target_after_top_raycast=true`.
- The proof records `input_injected=true`, but still records
  `production_enabled=false` and
  `post_swipe_alas_view_update_owner=false`.

## Remaining boundary

The next gate is to let the original live ALAS `_goto()` loop consume the
post-swipe view update and re-evaluate the target before its own grid click.
That continuation must preserve the one-input budget, rebind the same logical
cell to a fresh exact top-raycast Unity record, and prove that no adapter logic
chooses the fleet, route, or combat branch.

The later grid click, fleet movement, combat preparation/result chain, map
mutation, and repeated sortie remain unauthorized. A campaign-menu navigation
race also remains separate: the page can auto-transition after ALAS observes a
normal-campaign button but before the semantic click commits. The click
correctly fails closed; G33 does not paper over that no-op transition.

The full Python suite passes `371/371`, and the canonical integration patch
applies cleanly to pinned ALAS commit `81ccf63`.
