# G23 controlled ALAS combat acquisition validation

Date: 2026-08-10

## Result

G23 passed a qualification-only 12-4 ordinary-combat slice on the pinned CN
client without moving combat control flow out of ALAS. The observer supplies
exact Unity identities and one-use input receipts; original ALAS still owns
target selection, `_goto()`, combat preparation/execution/status handlers,
reward handling, urgent-commission handling, enemy searching, and native map
mutation.

This is not a production-ready combat release. The checked-in observer
manifest is now `6/40`, blocker review remains incomplete, six-ship HP/level
records are unqualified, and the production runner retains its G18 stop.

## Pinned runtime

- Device: `127.0.0.1:5581`
- Package: `com.bilibili.azurlane`
- Game PID throughout the E5 acquisition and result chain: `13448`
- Observer revision: `be80ce591a481c12d60c50d6040d40c035b40a2b`
- Observer APK SHA-256:
  `4fa4bfca741198de95952f40c836845e225666d72473840f8fd55afecb63bf25`
- Pinned ALAS revision: `81ccf63b4540f00241628c82a58c02c7a2bb11af`
- Game initialization evidence:
  `evidence/g4-game-init-20260810T080914Z-127.0.0.1_5581`

## Controlled input boundary

The campaign input tool starts an independent read-only trace recorder, lets
the pinned original `_goto()` reach its own `device.click(grid)` statement,
and replaces only the G18 zero-input preview callback in that qualification
process. Admission is immutable and one-use. It binds package, PID,
generation, fleet, target, ALAS branch, path, exact Unity Button geometry, and
the original call order.

The E5 receipt proved:

- ALAS branch `battle_0`, expected result `combat`;
- fleet 1 marker `cell_fleet_shengwang_younv`;
- origin `C6`, target `E5`;
- route `C6 -> C5 -> D5 -> E5`;
- admission generation `12927`, tap receipt generation `12932`;
- exact semantic input `campaign/map/grid/E5`;
- one controlled grid input while the independent recorder remained
  `input_injected=false`.

The 220-sample trace spans generations `12796..16139` and has SHA-256
`2eefa860bc949c70f6c42f8ec9d5e4287b6a4bae23846566753972c521cc5d22`.
It contains map, loading, combat, and S-result observations from one PID.

## Exact result-chain mappings

Five G23 reviews were promoted through the same all-of selector verifier used
by G22:

| ALAS resource | Exact Unity meaning | Mapping evidence SHA-256 |
| --- | --- | --- |
| `BATTLE_STATUS_S` | top-raycast result grade page plus `letter_S`, `label_S`, `VICTORY`, and `点击继续` | `c7637c4cc3cebf3765f226a58ffee83c3354a7344ddfe0f86965eb906828633d` |
| `GET_ITEMS_1` | top-raycast AwardInfo close plus `touch_to_continue`, `get_item`, and `awardinfo_bg` | `20330544a5f71922227467423586fabed77ba03df0d10ef9eba44afc1037b78b` |
| `EXP_INFO_S` | top-raycast statistics confirm plus S-grade sprites and exact `确 定` text | `e6db62a249cfb05500feb2566d49f8751f3e3a2b0417e3550df3b82a2767ee5f` |
| `GET_MISSION` | top-raycast one-button information dialog with blue confirm, `信息`, and `INFORMATION` | `53941f9135539e7d480e07c64214fce8068c961c8078e580335562703ee27664` |
| `PAUSE` | active combat `PauseBtn` Image with exact `pause_btn` sprite | `6601a6cf9e5c4e30d8a348834f72aeaaa8e908223e3c95c631c8c952af6292b2` |

`IN_MAP` remains the G22 mapping, so current coverage is `6/40`.
`EXP_INFO_A` and `EXP_INFO_B` were added to the unqualified manifest surface
because original ALAS queries those fallbacks after an experience page when a
subsequent urgent-commission dialog is present. They are not silently treated
as false mappings.

Each live result action required two increasing coherent generations with the
same exact path, point, bounds, foreground activity, PID, and mapping evidence,
then spent an explicit action budget of exactly one. E5 commit generations
were `16900` (`BATTLE_STATUS_S`), `17355` (`GET_ITEMS_1`), `19875`
(`EXP_INFO_S`), and `26949` (`GET_MISSION`). Each per-action receipt records
`outcome_verified=false`; the chain outcome is established independently by
the later map proof rather than asserted by the click helper.

## Original ALAS optional branch replay

The G19 qualification replay now accepts only four phase sequences:

1. the original six phases;
2. six phases plus `GET_ITEMS_1`;
3. six phases plus `GET_MISSION`;
4. both optional phases in their only admitted positions.

The fully observed order is:

`battle_preparation -> combat_executing -> battle_status_s -> get_items_1 ->
exp_info_s -> get_mission -> map_enemy_searching -> map_stable`.

Frames still contain no trusted phase token. The observer builder infers one
unique allowed sequence from exact visible-resource sets. The trace selector,
candidate report, fixture compiler, and fixture loader accept 6-8 frames but
derive map state only for the final searching/stable pair.

Pinned ALAS passed both Device-free qualifications:

- base path: 6 phases, 104 calls, 38 unique resources, 4 virtual actions;
- reward/mission path: 8 phases, 126 calls, 40 unique resources, 6 virtual
  actions.

The added virtual actions are only `GET_ITEMS_1` and `GET_MISSION`, and both
are emitted by original `handle_get_items()` and
`handle_urgent_commission()`. Source `MAP` dictionaries, projected map, shared
timers, battle increment, ammo decrement, and arrival checks all passed.

## Post-battle map closure

After the urgent-commission dialog was closed, a fresh exact map read at
generation `30340` proved:

- stage `12-4`;
- current fleet marker unchanged;
- fleet 1 at `E5`, ammo `2` (pre-battle ammo `3`);
- fleet 2 still at `F8`, ammo `5`;
- no enemy remains at E5;
- alive enemies are I2, E3, A7, and E7.

The newly spawned I2 enemy exposed sprite `qz1`. Unity uses `qz` for a
destroyer piece; it is now grouped into ALAS's existing `Light` genre, beside
the already supported `qx` light-cruiser piece. No new ALAS decision category
was introduced. Exact cleared variants `qz[1-3]_d_blue` follow the same
already-reviewed cleared-enemy rule.

## Validation

- Modern Python full suite: `302/302` passed.
- ALAS Python 3.7 package import: passed.
- Pinned original ALAS six-phase replay: passed.
- Pinned original ALAS eight-phase reward/mission replay: passed.
- Canonical ALAS patch reverse-apply check against the exercised pinned
  checkout: passed.
- `git diff --check`: passed.

## Remaining gates

- `34/40` resource mappings remain unqualified, including battle preparation,
  automation state/confirmation, alternate grades, map searching, and popup
  variants.
- The observed self-battle warning (`知道了`) needs its own exact
  `AUTOMATION_CONFIRM_CHECK`/action qualification; it is not conflated with
  `GET_MISSION`.
- Blocker review is still explicitly incomplete.
- Stable six-ship HP and level selectors remain unqualified.
- No continuous production combat loop, retry/recovery campaign, or default-on
  combat budget is claimed.

The next stage should collect a clean preparation/automation trace and promote
those mappings before attempting a complete observer-built 8-frame fixture.
