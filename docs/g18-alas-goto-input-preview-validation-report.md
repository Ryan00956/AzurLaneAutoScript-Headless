# G18 ALAS `_goto()` input-preview validation

Date: 2026-08-10

## Outcome

G18 passes a zero-input execution of the original ALAS campaign `_goto()`
prefix. The G17 admission is revalidated against the same immutable map,
decision, projection, fleet, enemy, and exact Unity cell geometry. An isolated
campaign shell then calls the real `_goto(D6, expected='combat')` and interrupts
only when that method reaches its own `device.click(grid)` statement.

This is not a movement or battle execution pass. The capture device never
calls the semantic adapter's grid-click port, so the campaign combat budget is
not consumed and no ADB input occurs. Every screenshot, sleep, swipe requiring
input, premature Device access, retreat, changed target, or second click fails
closed.

## Original ALAS control flow retained

The qualified pinned call order is:

```text
_goto
  -> hp_retreat_triggered
  -> fleet_ensure -> fleet_set
  -> in_sight -> focus_to -> map_swipe(0, 0)
  -> focus_to_grid_center
  -> convert_global_to_local
  -> ambush_color_initial
  -> enemy_searching_color_initial
  -> device.click(grid)  [captured; no input]
```

ALAS retains the sequencing and branch ownership. The semantic layer replaces
only the observations at that boundary:

- the typed displayed/current fleet identity makes the original
  `fleet_ensure()` observe that no switch is needed;
- the already-overlapping zero-distance admission supplies camera `D6`, a
  centered one-cell view, and the exact admitted cell geometry;
- original `in_sight()`, `focus_to()`, zero-vector `map_swipe()`,
  `focus_to_grid_center()`, and `convert_global_to_local()` execute unchanged;
- the pixel-only pre-click ambush color seed is replaced with a neutral typed
  baseline; post-click ambush recognition remains closed;
- the global location annotation written by `_goto()` must still equal `D6`
  when the original `device.click(grid)` is reached.

The original low-HP check also executes. A true result reaches a blocked
`withdraw()` boundary and fails before Device input. No retreat behavior is
silently bypassed.

## Isolation and rollback

The preview reuses the G16 class-level map transaction. It deep-copies the
validated projected map, temporarily overlays the class-level native grid
dictionaries so campaign `RoadGrids` keep their identities, and restores the
exact original map and every grid dictionary in `finally`.

The campaign instance, projected map, real configuration, G17 admission, and
combat budget are unchanged. The semantic local grid exposes only the fields
needed at ALAS's existing click boundary: local location, corner/button
geometry, mechanism-neutral fields, and the exact typed path, point, and
bounds. No Device implementation capable of Android input is present.

## Pinned native-ALAS result

The unobstructed generation `4817` map was reconstructed from all `68`
passable and `20` land cells of the real pinned
`campaign_main/campaign_12_4.py` map. The real
`campaign.campaign_main.campaign_12_4.Campaign` class and the actual
`semantic_e2e` campaign configuration ran the G16 decision, G17 admission,
and G18 `_goto()` prefix.

The run printed:

```text
ALAS_G18_PINNED_GOTO_INPUT_RESULT 68 20 D6 (3, 2) (-3, 0, 3, 2) 8 device.click LevelGrid/chapter_cell_quad_6_4 False
SOURCE_RESTORED True True
PROJECTED_UNCHANGED True
```

ALAS logged its original `In sight: D6`, `Focus to: D6`,
`Map swipe: (0, 0)`, and `Global D6 (camera=D6) -> Local D3 (center=D3)`
messages before the capture. The preview recorded the exact eight-call order
above, with `retreat_triggered=False`. No adapter click method was called.

## Current live condition

A fresh read-only observer request against the still-running pinned process
`19277` reported generations `91862` (snapshot/buttons) and `91863` (UI),
with `96` Buttons, `60` Texts, and `320` Images. Button and Image collections
were not truncated. The exact content remained
`服务器连接失败，是否重新连接？\n[NetworkDown]`.

No input was injected. The blocker still prevents a fresh complete
same-process map/decision/admission/preview chain, so the pinned replay is not
described as current live executability.

## Verification

- Controller and integration suite: `261/261` passed.
- Tests cover exact capture and rollback, stale state, changed decisions,
  fleet-index drift, native target drift, low-HP retreat, premature Device
  access, and changed global-grid annotation.
- `python/alas_headless` and the patched campaign runner compile.
- `git diff --check` passes.
- The canonical patch applies cleanly to upstream
  `81ccf63b4540f00241628c82a58c02c7a2bb11af` and exactly matches the full
  exercised patchcheck diff.

## Remaining boundary

G19 should continue adapting inputs, not replace the ALAS combat state
machine. Before the D6 lease can be spent, the complete post-click path needs
typed `combat_appear()` and map/battle page identity, the original combat and
result-popup loop, arrival confirmation, post-battle map refresh, and the G17
independent enemy-removal/ammunition proof. Until that closure is qualified,
the runner still raises `ScriptEnd` at the captured pre-input boundary.
