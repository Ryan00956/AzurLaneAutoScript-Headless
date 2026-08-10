# G20 ALAS combat observer contract validation

Date: 2026-08-10

## Result

The production input boundary for G19's six-frame combat replay is now
implemented and fail-closed. It consumes complete typed Unity observer
records; it does not accept a fixture-supplied phase name, OCR result, image
template result, coordinate, or scripted boolean. ALAS's original campaign and
combat state-machine methods remain unchanged.

This is a **contract pass, not a live combat-mapping pass**. No real typed
battle capture exists in the evidence set while the current account is behind
the exact `[NetworkDown]` dialog. The checked-in live manifest therefore
reports `0/38` qualified resources, unqualified blocker coverage, and
unqualified six-ship HP/level coverage. It cannot build a production replay or
enable D6 input.

## Exact G19 resource surface

The G19 qualification output now records both `104` presence calls and their
exact `38`-name unique surface. Replay completion rejects both added and removed
queries:

```text
AUTOMATION_CONFIRM_CHECK  AUTOMATION_OFF          AUTOMATION_ON
AUTO_SEARCH_MENU_EXIT     BATTLE_PREPARATION      BATTLE_STATUS_A
BATTLE_STATUS_B           BATTLE_STATUS_C         BATTLE_STATUS_D
BATTLE_STATUS_S           CAMPAIGN_CHECK          EVENT_CHECK
EXP_INFO_S                FLEET_PREPARATION       GAME_TIPS
GAME_TIPS3                GAME_TIPS4              GET_ITEMS_1
GET_ITEMS_2               GET_ITEMS_3             GET_MISSION
GET_SHIP                  GUILD_POPUP_CONFIRM     IN_MAP
IN_RETIREMENT_CHECK       MAP_AMBUSH_EVADE        MAP_CAT_ATTACK
MAP_CAT_ATTACK_MIRROR     MAP_ENEMY_SEARCHING     MAP_PREPARATION
MISSION_POPUP_GO          PAUSE                   POPUP_CANCEL
POPUP_CONFIRM_WHITE       RETIRE_APPEAR_1         SP_CHECK
STORY_CLOSE               STORY_SKIP_3
```

Every one must map to one or more exact full Unity paths plus exact record
kind/name and, for Images or fixed Text, exact sprite/text. The three future
post-grid actions (`BATTLE_PREPARATION`, `BATTLE_STATUS_S`, `EXP_INFO_S`) must
include an exact actionable Button whose point is inside its bounds and whose
EventSystem raycast is topmost.

## Six-snapshot inference

`build_alas_campaign_combat_replay_from_observer()` accepts exactly six
strictly increasing, package/driver/game-bound snapshots. It recomputes all 38
presence results at each step, then admits only these positive sets:

1. `AUTOMATION_ON`, `BATTLE_PREPARATION`;
2. `PAUSE`;
3. `BATTLE_STATUS_S`;
4. `EXP_INFO_S`;
5. `IN_MAP`, `MAP_ENEMY_SEARCHING`;
6. `IN_MAP`.

The phase values in the returned G19 replay are derived from this exact order
and visibility proof. The fixture schema explicitly rejects a `phase` field,
so the old canonical synthetic tokens cannot masquerade as production
observations.

The last two frames additionally require the complete typed campaign map,
exact admitted stage/cell/fleet/path/point/bounds, and a current fleet on the
target. The stable frame requires the target enemy absent, ammunition reduced
by one, and six exact HP Image paths plus six exact level Text paths. HP uses
typed Image `fill_amount`; levels use strict numeric Unity Text in `1..125`.

## Raw fixture closure

`load_alas_combat_observer_fixture()` reuses the observer's existing Button,
Toggle, Text, and Image record parser. Each raw frame contains the original
`/v1/snapshot`, `/v1/buttons`, and `/v1/ui` payloads plus the complete typed
campaign-map projection where applicable. A canonical SHA-256 binds all four
parts of each frame.

Loading or replay closes on:

- schema, package, driver revision, game fingerprint, PID, main-thread probe,
  logical size, or generation disagreement;
- Button, Toggle, Text, or Image truncation; extraction errors; incomplete
  typed method masks; malformed or duplicate exact paths;
- missing, extra, ambiguous, inactive, renamed, re-sprited, or re-texted
  resource records;
- a non-top-raycast action Button, reviewed active blocker, changed target
  geometry/fleet/ammunition, invalid HP/level, or non-increasing frame;
- any manifest other than the exact 38-resource surface, or any resource,
  blocker review, or fleet-stat mapping without evidence hashes.

The positive fixture in tests uses conspicuously test-only `Combat/...` paths.
It proves that raw records can drive the same G19 replay, but none of those
paths are installed in the production manifest.

## Verification

- Controller and integration suite: `275/275` passed.
- Eight new contract tests cover the complete raw-fixture replay and negative
  gates for unqualified coverage, phase tokens, frame tampering, top raycast,
  blockers, and resource-surface drift.
- `audit_alas_combat_observer_coverage.py` reports a valid 38-resource contract,
  `production_ready=false`, `qualified_resources=0`, and `input_injected=false`.
- The real pinned ALAS G19 qualification still passes and emits the exact
  `104`/`38` query counts and names.
- A current read-only observer sample at generations `119693..119695` returned
  `96` Buttons, `60` Texts, and `320` Images with no Button/Text/Image
  truncation. The exact text remained
  `服务器连接失败，是否重新连接？\n[NetworkDown]`; no input was injected.
- The canonical ALAS integration patch is unchanged; production still stops at
  the G18 captured `_goto()` click boundary.

## Next boundary

G21 is evidence acquisition and mapping, not another state-machine rewrite.
After the account can reach a map, capture the six complete raw observer
frames from one controlled ordinary S-rank battle, review every positive and
negative selector plus blockers and fleet stats, and replay that frozen bundle
offline. Only a `38/38` manifest and an independently passing fixture can make
the G20 builder production-ready. D6 input remains outside this result.
