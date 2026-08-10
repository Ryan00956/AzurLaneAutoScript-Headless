# G16 ALAS campaign decision-preview validation

Date: 2026-08-10

## Outcome

G16 passes the decision-only implementation and pinned native-ALAS
qualification. The semantic layer still supplies only typed map input. ALAS's
original `battle_function()`, `battle_0()`, roadblock checks, default enemy
selection, multi-fleet path initialization, and native route builder remain
the decision owners.

The first public `goto()` admission is captured as immutable data and aborted
before ALAS's `goto()` implementation runs. This is not a movement or combat
pass. `_goto()`, fleet switching, Device access, combat, retreat, map control,
full scanning, and timed emotion waiting remain fail-closed.

The recurring exact `[NetworkDown]` overlay still blocks a fresh complete live
map model. G16 therefore keeps the pinned decision proof separate from the
current read-only live blocker evidence.

## Original ALAS path

For pinned `campaign_main/campaign_12_4.py` at battle count `0`, the exercised
call chain was:

```text
battle_function
  -> battle_0
  -> clear_roadblocks / clear_potential_roadblocks
  -> battle_default
  -> clear_enemy
  -> clear_chosen_enemy
  -> goto  [captured, never executed]
```

No selection rule from that chain is copied into the adapter. The preview
first calls ALAS's existing `find_path_initial()`, then invokes the original
`battle_function()` on an isolated campaign shell. A stale projection, an
unknown target, an unreachable or changed route, a fleet switch, a branch
that returns without `goto()`, any Device access, or any lower action boundary
closes the gate.

## Class-level map transaction

ALAS campaign files keep `RoadGrids` and named grid constants attached to the
class-level `MAP`. Merely replacing `campaign.map` with a deep copy would make
`battle_0()` inspect stale road objects and would no longer exercise the
original branch faithfully.

The preview therefore performs a narrow transaction under a process lock:

1. deep-copy the already validated semantic projection;
2. keep every class-level ALAS grid object's identity;
3. temporarily replace only its attribute dictionary with the projected
   native `GridInfo` state;
4. run native path initialization and the original battle branch;
5. restore the exact original map and grid dictionaries in `finally`.

The campaign instance, its projected map, and its real configuration remain
unchanged. The configuration clone has persistence disabled. ALAS's original
emotion calculation is allowed to prove that no wait is required; the first
attempt to sleep fails closed.

## Pinned native-ALAS result

The unobstructed G13 generation `4817` model plus G15 fleet identity was
replayed against real `campaign.campaign_main.campaign_12_4.Campaign` from
upstream commit `81ccf63b4540f00241628c82a58c02c7a2bb11af`, using the actual
`semantic_e2e` campaign configuration and no Device implementation.

ALAS produced:

| Field | Result |
| --- | --- |
| branch | `battle_0` |
| battle count | `0` |
| logical fleet | `1` |
| fleet marker | `cell_fleet_shengwang_younv` |
| origin | `D6` |
| target | enemy `D6` |
| expected | `combat` |
| native cost / weight | `0 / 50.0` |
| full native route | `D6` |
| native `goto` click nodes | `D6` |
| step / turning optimization | `false / true` |

The ALAS emotion check calculated both fleet values as `119` and returned
without sleeping. The proof printed `SOURCE_RESTORED True True` and
`PROJECTED_UNCHANGED True`. No input method was available to the campaign
shell.

## Current live condition

A new read-only observer sample from the still-running pinned game reported
generation `59956`, `60` Texts and `320` Images, with no truncation. It still
contained:

- displayed fleet Text `1`;
- the same six roster sprites;
- both `cell_fleet_shengwang_younv` and `cell_fleet_ying` markers;
- exact typed content `服务器连接失败，是否重新连接？ [NetworkDown]`.

No input was injected. Because the overlay obscures the canonical map-scene
identity, no fresh same-process `campaign_map_state -> projection -> decision`
result is claimed.

## Verification

- Controller and integration suite: `245/245` passed.
- Decision and integration tests cover capture, exact transaction restore,
  configuration isolation, stale projections, route disagreement, unknown
  targets, Device access, fleet switching, timed emotion waiting, and a branch
  returning without `goto()`.
- `python/alas_headless` and the patched ALAS campaign runner compile.
- The canonical patch applies cleanly to upstream
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- The canonical patch exactly matches the complete exercised patchcheck Git
  diff after normalized newline comparison.

## Remaining boundary

The chosen target is the fighting enemy already under the current fleet at
`D6`. Therefore the next action is not a harmless navigation-only move:
executing `goto(D6, expected='combat')` enters ALAS's `_goto()` and combat
transition. A fresh unobstructed same-process decision replay is still needed,
followed by a separately designed one-input combat-admission and post-battle
refresh gate. Movement, battle, enemy removal, ammunition mutation, boss
handling, retreat, and map rewards remain closed.
