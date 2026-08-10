# G19 original-ALAS combat state replay validation

Date: 2026-08-10

## Outcome

G19 passes a bounded, Device-free replay of the original ALAS ordinary-combat
state machine. It demonstrates that the G17/G18 zero-distance D6 slice can be
driven by typed post-click phase inputs without copying ALAS's combat,
result-popup, enemy-searching, arrival, or map-mutation logic.

This is still not a live combat pass. The replay records four virtual actions
and never calls the semantic adapter, its grid-click port, or ADB. The patched
production runner remains at the G18 capture boundary; it does not manufacture
the replay sequence or spend the campaign budget.

## Original ALAS ownership

The real pinned methods executed in this order:

```text
_goto(D6, expected='combat')
  -> combat_appear
  -> combat
       -> combat_preparation
       -> combat_execute
       -> combat_status(expected_end='with_searching')
            -> handle_in_map_with_enemy_searching
  -> hp_get / lv_get
  -> arrival confirmation
  -> GridInfo.wipe_out
  -> battle_count + 1 / fleet_ammo - 1
  -> predict / find_path_initial
```

The semantic replay replaces observations and Device actions only. Original
ALAS still decides when to leave each loop, which result to click, whether the
expected map ending is `with_searching`, when D6 arrival is confirmed, and how
its native map/fleet/battle fields mutate.

## Typed six-phase contract

The canonical replay requires exactly six strictly increasing frames after
the admitted input generation:

1. `battle_preparation`: `BATTLE_PREPARATION` and `AUTOMATION_ON`, combat
   loading true, not in map;
2. `combat_executing`: `PAUSE`, combat executing true;
3. `battle_status_s`: exact S-rank result;
4. `exp_info_s`: exact experience result;
5. `map_enemy_searching`: map identity, searching overlay, fleet/current-fleet
   both on D6;
6. `map_stable`: map identity without searching, fleet/current-fleet still on
   D6, plus six typed HP and level values.

Phase identity, visible resource set, boolean flags, stage, target, admission
generation, and generation ordering are immutable. Extra resources, reordered
or repeated frames, early fleet stats, invalid HP/level values, or fleet/map
flag drift close the gate before state-machine execution.

The exact virtual action sequence is:

```text
campaign_grid:D6
BATTLE_PREPARATION
BATTLE_STATUS_S
EXP_INFO_S
```

Any additional or reordered action fails. `campaign_grid:D6` is a virtual
record in this qualification harness, not the G17 adapter input method.

## Observation closure and upstream drift

The pinned original chain issued `104` resource checks over `38` unique ALAS
resource names. The replay frame is treated as a complete typed surface: only
its exact visible resources return true, and every false query must belong to
the reviewed pinned allowlist. A new upstream query is collected but prevents
the replay from returning success, so it cannot silently become false.

Direct pixel-only observations used inside otherwise original handlers are
replaced at their narrow inputs: combat loading/executing, story-black state,
ambush/air-raid state, info-bar count, map-cat color count, enemy-searching,
HP, levels, and final map prediction. Popup, retirement, story, mission,
guild, auto-search, mystery, and mis-click handlers still run their original
branch order over those typed presence results.

## Isolation

The replay uses the G16/G18 class-level native-map transaction and an isolated
campaign/config shell. It additionally deep-copies every mutable ALAS timer
touched by combat preparation, auto mode, submarine handling, story handling,
map arrival, and enemy searching. Statistics output is replaced with a null
context so the qualification writes no drop records.

The source class `MAP`, every native grid dictionary, projected campaign map,
real configuration, admission, and shared timer state remain unchanged. An
unsupported Device method, real swipe, low-level input, sleep with external
effect, retreat, or unexpected resource action fails closed.

## Pinned native-ALAS result

The reusable qualification script is
`scripts/python/qualify_alas_combat_state_replay.py`. It derives all `68`
passable and `20` land cells from the real pinned `campaign_12_4.MAP`, restores
the reviewed G13 fleets/enemies/ammunition state, and runs the real
`campaign.campaign_main.campaign_12_4.Campaign` with the actual
`semantic_e2e` campaign configuration.

The original ALAS log reached:

```text
Combat preparation.
[Automation] ON
[BattleUI] PAUSE
Combat execute
Combat status
[expected_end] with_searching
Enemy searching appeared.
Combat end.
Arrive D6 confirm. Result: combat. Expected: combat
```

The final machine-readable result reported:

- `passed=true`, `input_injected=false`;
- battle count `0 -> 1`;
- ammunition `5 -> 4`;
- D6 enemy cleared and current fleet retained;
- all six phases and all four virtual actions in exact order;
- only the four pinned virtual waits `(0.25..0.5)` twice, `1.2`, and `0.3`;
- source map restored and projected map unchanged.

## Current live condition

A fresh read-only observer request against process `19277` reported generations
`103330 -> 103331`, with `96` Buttons, `60` Texts, `320` Images, and no Button
or Image truncation. The exact blocker remained
`服务器连接失败，是否重新连接？\n[NetworkDown]`.

No input was injected. There are no real typed battle-preparation/executing/
result/searching snapshots in current evidence, so the six replay frames are a
strict qualification contract, not a claim that their Unity mappings are live.

## Verification

- Controller and integration suite: `267/267` passed.
- Contract tests reject phase order, generation, resource, early-stat, flag,
  and configuration drift.
- The reusable real-ALAS qualification passes with no Device implementation.
- Python sources and qualification script compile.
- `git diff --check` passes.
- The unchanged canonical ALAS patch still applies cleanly and exactly matches
  the exercised patchcheck diff.

## Remaining boundary

G20 must map the six abstract replay phases and the `38` reviewed resource
queries to exact Unity observer paths, sprites, text, active/enabled state,
top EventSystem raycasts, and blockers. Recorded complete typed fixtures should
first drive this same replay offline. Only after all four future live action
targets and every intervening observation are independently qualified should
the production runner be allowed to replace G18 capture with the one real D6
input and the G17 post-battle proof.
