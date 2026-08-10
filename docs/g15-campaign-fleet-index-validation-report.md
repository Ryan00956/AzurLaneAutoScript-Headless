# G15 campaign fleet-index reconciliation validation

Date: 2026-08-10

## Outcome

G15 passes the live passive identity slice and the pinned native-ALAS indexed
projection slice. It resolves the G14 fleet-index gap without adding a map
input or replacing ALAS's state machine.

The identity is not inferred from the optional map `shadow` Image. The typed
map model now requires one exact displayed-fleet number and one exact match
between a `cell_fleet_*` marker suffix and the ship sprites in the displayed
fleet roster. That identity participates in the same two-increasing-generation
stability signature as the rest of the map model.

The current `[NetworkDown]` overlay still prevents a fresh complete live map
model and same-process projection. G15 therefore keeps two claims separate:

- three increasing live generations proved one stable fleet identity with no
  input;
- the unobstructed G13 state plus that identity passed both normal and reversed
  fleet indexing against the pinned real ALAS `Campaign` class.

## Typed fleet identity

The observer already exposed the required records; no driver or native
observer change was needed. The controller now requires:

- exactly one active, complete Text at
  `LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)/top_stage/`
  `msg_panel/fleet_info/number`, containing only `1` or `2`;
- between one and six active, complete ship icon Images under the exact
  displayed-fleet `left_stage/fleet/{vanguard|main}/shiptpl(Clone)/icon_bg/icon`
  paths;
- ASCII resource sprite names for that roster;
- exactly one map marker whose `cell_fleet_` suffix equals exactly one roster
  sprite;
- if an enemy is marked `行动中`, exactly that current fleet must occupy the
  same node.

Missing numbers, malformed values, empty or oversized rosters, duplicate
matches, two matching fleet markers, no matching marker, and a fighting enemy
at another fleet all fail closed. The displayed number, matched marker, and
sorted roster sprites are part of `CampaignMapState.signature`, so a changing
identity cannot satisfy the existing stable-map read.

## ALAS ownership and reversed fleets

Pinned ALAS distinguishes the fleet number shown by the game from its logical
mob/boss fleet index:

- `get_fleet_show_index()` reads the displayed game fleet number;
- `get_fleet_current_index()` keeps that value normally and uses
  `3 - fleet_show_index` when `fleets_reversed` is true.

The projection reuses exactly that rule. After ALAS's existing
`map_data_init()` builds the shadow map, it supplies these observed inputs:

- `fleet_show_index`;
- logical `fleet_current_index`;
- `fleet_1_location` and, when present, `fleet_2_location`;
- native `GridInfo.is_fleet` and exactly one `is_current_fleet`.

ALAS still owns route finding and every later campaign decision. G15 does not
call `map_control_init()`, `fleet_set()`, `update()`, `full_scan()`, `goto()`,
enemy clearing, combat, retreat, or rewards. No grid Button is mapped.

## Live passive identity proof

Three read-only samples from the still-running pinned game produced increasing
generations `33896 -> 33905 -> 33913` and the same logical identity:

- displayed fleet: `1`;
- displayed roster sprites:
  `dulianglai`, `kewei_younv`, `linggu`, `shengwang_younv`, `xuefeng`,
  `zhuiganzhe`;
- map markers: `cell_fleet_shengwang_younv`, `cell_fleet_ying`;
- unique roster match: `cell_fleet_shengwang_younv`.

The exact typed blocker remained
`服务器连接失败，是否重新连接？ [NetworkDown]`. No input was injected. A
complete `campaign_map_state()` call was also attempted with an input-rejecting
tap function and failed closed with `campaign map-scene identity is absent`.
The passive identity evidence is therefore not misrepresented as a fresh full
live-map pass.

## Pinned native-ALAS projection

The G13 generation `4817` state was replayed without constructing a Device
against pinned `campaign.campaign_main.campaign_12_4.Campaign` at upstream
commit `81ccf63b4540f00241628c82a58c02c7a2bb11af`.

For normal `fleet1_mob_fleet2_boss` order, the result was:

- displayed index `1`, logical current index `1`;
- `fleet_1_location = D6`;
- `fleet_2_location = F8`;
- `D6.is_current_fleet = True`.

For reversed `fleet1_boss_fleet2_mob` order, the same displayed game state
correctly became:

- displayed index `1`, logical current index `2`;
- `fleet_1_location = F8`;
- `fleet_2_location = D6`;
- `D6.is_current_fleet = True`.

Both runs printed `ALAS_G15_PINNED_FLEET_INDEX_RESULT ... True`, used ALAS's
native map initialization and route logic, and reset all temporary costs and
connections afterward.

## Verification

- Controller and integration suite: `235/235` passed.
- `python/alas_headless` compiles successfully.
- The canonical ALAS patch applies cleanly to the pinned upstream commit.
- The complete canonical patch exactly matches the exercised patched
  checkout's Git diff.
- Final observer APK SHA-256 remains
  `bb9bdaa7838182731296ce5ab4f6f17aad0394660aa7b24c245a1ccfed18b220`.
- Driver revision remains
  `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Package remains pinned CN `9.7.10`, x86_64/API 32.

## Remaining boundary

A fresh unobstructed same-process map read must still exercise the indexed
projection after the network condition clears. The next safe implementation
stage is a decision-only run of ALAS's original campaign branch with its first
`goto()` admission intercepted and recorded, not executed. Only after the
chosen fleet, target, route, and preconditions are reproducible should one
separately budgeted grid move be considered. Combat and all post-move state
transitions remain closed.
