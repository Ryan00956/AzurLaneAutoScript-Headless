# G14 read-only ALAS map synchronization and planning validation

Date: 2026-08-10

## Outcome

G14 passes the implementation and pinned-native-object qualification for
read-only ALAS map synchronization. The G13 semantic model is projected into a
deep copy of ALAS's own `CampaignMap` and native `GridInfo` objects. Static map
initialization and route calculation remain owned by the pinned ALAS code.

This is not a movement pass. The synchronization layer deliberately does not
bind the two semantic fleet markers to ALAS fleet indexes, does not call
`map_control_init()`, and does not expose a grid input. The current live map is
still covered by the recurring exact `[NetworkDown]` dialog, so a fresh
same-process live projection was not claimed.

## ALAS ownership boundary

The semantic already-in-map branch now performs these steps:

1. asks the existing adapter for the complete stable G13 map state;
2. validates its stage, shape, land/passable topology, dynamic nodes, and
   static ALAS spawn capabilities;
3. deep-copies the loaded ALAS `CampaignMap`;
4. calls ALAS's existing `map_data_init()` on that copy;
5. writes fleet, enemy, and ammunition state into native `GridInfo` fields;
6. calls ALAS's existing `find_path_initial()` and `_find_path()` for each
   semantic fleet marker;
7. returns deterministic reachability summaries before ALAS's retreat branch.

The integration does not call `map_control_init()`, `update()`, `full_scan()`,
`fleet_set()`, `goto()`, `clear_enemy()`, combat, retreat, or reward handling.
Default non-semantic ALAS behavior is unchanged.

The projection is transactional at this boundary. It snapshots the campaign
attributes that `map_data_init()` owns, restores them if initialization or
planning fails, and restores the `POOR_MAP_DATA` configuration field even on a
successful shadow initialization. Planning costs and path connections are
cleared after the immutable result is built.

## Pinned ALAS object qualification

The live G13 generation `4817` state was replayed without a Device object into
`campaign.campaign_main.campaign_12_4.Campaign` from pinned ALAS commit
`81ccf63b4540f00241628c82a58c02c7a2bb11af`. The run printed
`ALAS_G14_PINNED_MAP_RESULT True` and confirmed:

- `12-4`, `11x8`, 68 passable cells, and 20 land cells;
- native enemy state at `C6` and `D6`;
- native fleet state at `D6` and `F8`, including the valid fleet/enemy overlap
  at fighting cell `D6`;
- native ammunition state at `F2`;
- empty `fleet_1_location` and `fleet_2_location` after projection;
- every temporary ALAS cost reset to `9999` and every connection reset to
  `None`.

The native planner returned:

| Semantic fleet | Target | ALAS cost | Native route |
| --- | --- | ---: | --- |
| `cell_fleet_shengwang_younv @ D6` | enemy `D6` | 0 | `D6` |
| same | enemy `C6` | 1 | `D6,C6` |
| same | ammo `F2` | 33 | `D6,D5,E5,F5,F4,F3,F2` |
| `cell_fleet_ying @ F8` | enemy `D6` | 22 | `F8,F7,F6,E6,D6` |
| same | enemy `C6` | 23 | `F8,F7,E7,D7,C7,C6` |
| same | ammo `F2` | 33 | `F8,F7,F6,F5,F4,F3,F2` |

These are ALAS-native path costs, not simple step counts. Recommendations use
the existing ALAS-style `weight`, then `cost`, with node identity only as a
deterministic tie-break. They are planning summaries, not authorized campaign
decisions.

## Fleet-index safety boundary

G13 proves two stable fleet markers and their cells, but it does not yet prove
which marker is ALAS fleet 1 and which is fleet 2. A visible active shadow or
the top-stage fleet number alone is not a sufficient persistent identity
contract.

G14 therefore stores only `semantic_fleet_locations` keyed by the exact Unity
marker. It leaves `fleet_1_location`, `fleet_2_location`, and current-fleet
identity unset. ALAS's movement state machine cannot start from this
projection accidentally. Resolving that identity is a separate gate; the
state-machine logic itself should remain ALAS-owned.

## Current live condition

A read-only observer check found the original game PID `19277` healthy and
foreground at generation `21296`, with 96 Buttons, 320 Images, and 60 Texts.
The underlying `LevelGrid` Buttons were still present, but the exact typed
message was `服务器连接失败，是否重新连接？ [NetworkDown]`; both reviewed
dialog Buttons were top raycast targets.

No input was injected during this check. Because the blocker is still present
after an earlier reviewed reconnect attempt, G14 does not claim a new live
same-process projection result. The last unobstructed complete live map input
remains the G13 generation `4817` proof.

## Verification

- Controller and integration suite: `230/230` passed.
- `python/alas_headless` compiles successfully.
- The canonical ALAS patch applies cleanly to
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- The complete canonical patch exactly matches the exercised patched
  checkout's Git diff.
- Final observer APK SHA-256 remains
  `bb9bdaa7838182731296ce5ab4f6f17aad0394660aa7b24c245a1ccfed18b220`.
- Driver revision remains
  `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Package remains pinned CN `9.7.10`, x86_64/API 32.

## Remaining boundary

The next safe gate is passive fleet-index reconciliation: prove a persistent
semantic marker-to-ALAS fleet 1/2 mapping, populate indexed fleet state, and
observe repeated map generations without enabling input. Only after that
should one separately budgeted ALAS-owned grid move be considered. Combat,
post-battle refresh, enemy removal, ammunition pickup, boss handling, retreat,
and map rewards remain closed.
