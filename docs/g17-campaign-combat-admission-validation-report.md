# G17 campaign combat-admission validation

Date: 2026-08-10

## Outcome

G17 passes the decision-bound admission contract and exact dynamic grid-input
port. It is not a movement or combat execution pass. The patched campaign
runner still stops after admission preflight, before ALAS's public `goto()` is
allowed to enter `_goto()`.

This boundary is intentional. ALAS's original execution path continues from
the selected grid through fleet verification, camera/view conversion, combat
appearance, the combat loop, result handling, and post-battle scanning. Those
observations are not yet a complete semantic closure. Injecting D6 first and
discovering a missing observation afterward would leave the game in a mutated
half-run, so G17 fails before the first live grid input instead.

## ALAS ownership and input port

ALAS remains the sole decision and future execution owner:

```text
battle_function -> battle_0 -> battle_default -> clear_enemy
  -> clear_chosen_enemy -> goto -> _goto -> device.click(grid)
```

The semantic layer does not reproduce that branch or route logic. It consumes
the immutable G16 decision and recognizes only the explicit global-location
annotation that ALAS itself places on the local `Grid` immediately before its
existing `device.click(grid)` call. Generic coordinate input, ordinary
`GridInfo`, multi-click, swipe, drag, and all unmapped resources remain closed.

The canonical ALAS patch now asks the adapter to prepare the admission after
the original decision preview. With budget zero it preserves G16 behavior. If
exactly one budget unit is configured, it logs the validated admission and
raises `ScriptEnd` without calling `goto()`; no unit is consumed and no ADB tap
occurs in this G17 runner path.

## Admission contract

`ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET` is a canonical non-negative integer and
defaults to `0`. The first slice requires exactly `1` when admission is
requested. It accepts only:

- normal mode and the same in-memory stable `CampaignMapState` used by G16;
- matching stage and generation between map and ALAS decision;
- `target_kind=enemy` and exact `expected=combat`;
- native cost `0`;
- origin, target, full native route, and optimized goto route all equal to one
  node;
- no fleet-step movement;
- exactly one typed `fighting` enemy at that node;
- the current semantic fleet marker at the same node with positive ammunition.

The pinned G16 result fits this shape: `battle_0`, logical fleet `1`, marker
`cell_fleet_shengwang_younv`, and fighting enemy `enemy_1204090` at `D6`, with
cost `0` and one-node route/goto route `D6`.

That exact G16 decision and G13 dynamic state were replayed through the G17
contract while deriving all `68` passable and `20` land cells from the real
pinned `campaign_12_4.MAP`. The Device-free qualification printed:

```text
ALAS_G17_PINNED_ADMISSION_RESULT 68 20 D6 1204090 5 True
```

Bosses, ammunition pickups, portals, multi-node navigation, fleet switching,
zero-ammunition battles, and any route or generation drift fail before input.

## Exact cell and one-use semantics

Immediately before a future admitted tap, the oracle re-reads the Button with
the exact cell path saved in the stable map state. The unique Button must keep
the same point and bounds and be active in hierarchy, active and enabled,
interactable, the top EventSystem raycast target, within the pinned logical
screen, unblocked, and in the pinned foreground component.

The one unit is consumed and the receipt is recorded immediately after the ADB
tap returns, before subsequent receipt assertions. Therefore a malformed or
unexpected post-input receipt cannot reopen the lease or cause a second tap.
Unit tests exercise exact success, default closure, route drift, geometry
drift, global blockers, failed postconditions, and anomalous-receipt no-replay.

## Independent post-battle proof

The prepared completion contract does not accept an ALAS return value alone.
After the original combat state machine eventually becomes qualified, a new
stable complete map must independently prove all of the following:

- ALAS battle count advanced by exactly one;
- the exact target enemy object id disappeared;
- the same current fleet marker remains on the target node;
- fleet ammunition decreased by exactly one;
- the passable-cell topology is unchanged;
- the stable map generation is newer than the recorded grid input;
- the input receipt path is the admitted Unity cell path.

Failure does not restore the budget or replay the input.

## Current live condition

A new read-only request against the still-running pinned process reported:

- process `19277`;
- healthy main-thread flags `15`;
- generations `74795` (snapshot), `74796` (Buttons), and `74797` (UI);
- `96` complete Buttons, `60` Texts, and `320` Images;
- no Button or Image truncation;
- exact typed text `服务器连接失败，是否重新连接？ [NetworkDown]`.

No input was injected. The blocker prevents a fresh complete same-process map,
decision, and admission proof. The older unobstructed generation `4817` plus
the pinned native G16 decision remains the evidence for the D6 contract shape,
not a claim of current live executability.

## Verification

- Controller and integration suite: `253/253` passed.
- The pinned native `campaign_12_4.MAP` topology accepted exactly enemy object
  `1204090` at `D6` with ammunition `5` and cell path
  `chapter_cell_quad_6_4`.
- `python/alas_headless` and the patched ALAS campaign runner compile.
- `git diff --check` passes.
- The complete canonical patch applies cleanly to upstream
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- The canonical patch was regenerated from the complete exercised patchcheck
  Git diff.

## Remaining boundary

G18 should connect the inputs needed by ALAS's existing execution state
machine, not introduce a parallel combat controller. The next closure is:

1. typed current/displayed fleet observation for `fleet_ensure()`;
2. semantic camera/view initialization and exact global-to-local cell binding;
3. typed combat-appearance and combat-loop observations;
4. original ALAS result/popup handling;
5. the G17 independent post-battle map proof.

Only after that entire chain passes offline and pinned tests should the runner
continue past the current preflight `ScriptEnd` and spend the one grid-input
budget on a live map.
