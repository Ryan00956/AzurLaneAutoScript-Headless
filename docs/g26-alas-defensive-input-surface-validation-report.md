# G26 ALAS defensive input-surface validation

Date: 2026-08-10

## Outcome

G26 prevents a future false production-ready claim from canonical combat
coverage alone. The maximum original-ALAS replay still asks exactly 41 unique
resource names when every defensive branch is false, but those are not the
complete input surface: true short-circuit branches can ask 11 more already
pinned names and can select 37 distinct click targets.

The manifest is therefore versioned as four independent gates:

| Gate | Current |
| --- | ---: |
| canonical replay queries | `13/41` |
| complete pinned defensive queries | `14/52` |
| original-ALAS click targets | `9/37` |
| defensive branch review | incomplete |

Fleet statistics remain qualified. One compound `network_down` blocker is
qualified, but blocker review remains incomplete. Consequently
`production_ready=false`, and production remains stopped at G18.

## Why 41 was insufficient

The original state machine uses Python short-circuit evaluation. For example,
the normal all-false path asks `POPUP_CANCEL` but does not ask
`POPUP_CONFIRM`; once the first query is true it asks the second and may click
one of the pair. The same pattern exists for guild and mission dialogs.

The complete pinned defensive query union is 52 names. The 11 names absent
from the canonical 41-query trace are:

`BACK_ARROW`, `BATTLE_PREPARATION_WITH_OVERLAY`, `DAILY_CHECK`,
`EMERGENCY_REPAIR_CONFIRM`, `GET_AMMO`, `GET_ITEMS_SHIP_1`,
`GUILD_POPUP_CANCEL`, `MISSION_POPUP_ACK`, `MUNITIONS_CHECK`, `NEW_SHIP`, and
`POPUP_CONFIRM`.

G26 also pins every query to the click targets the original ALAS code may
choose. Examples:

| Query | Original-ALAS target |
| --- | --- |
| `GET_ITEMS_2`, `GET_ITEMS_3` | `GET_ITEMS_1` |
| `GAME_TIPS3`, `GAME_TIPS4` | `GAME_TIPS` |
| `MAP_CAT_ATTACK_MIRROR` | `MAP_CAT_ATTACK` |
| `AUTOMATION_OFF`, `AUTOMATION_ON` | `AUTOMATION_SWITCH` |
| `DAILY_CHECK`, `MUNITIONS_CHECK` | `BACK_ARROW` |
| `MAP_PREPARATION`, `FLEET_PREPARATION` | self or `MAP_PREPARATION_CANCEL` |
| `POPUP_CANCEL`, `POPUP_CONFIRM` | confirm or cancel, selected by the existing handler |
| `STORY_SKIP_3` | `STORY_SKIP`, safe area, or a dynamic story option |

This table does not make decisions. It is a checked input contract around the
unchanged ALAS query order, configuration branches, target choice, timing, and
click call.

## Manifest and action contract

Manifest v2 separates observation from action:

- `resources` contains all 52 exact Unity observation mappings;
- `actions` contains all 37 exact original-ALAS click targets;
- every qualified action requires one exact top-raycast Button, Image, or
  Toggle alternative;
- `branch_review_complete` is independent of mapping counts;
- production readiness requires all resources, all actions, complete branch
  review, complete blocker review, and qualified fleet statistics.

For contextual controls, the action boundary requires both the triggering
query and the exact click target chosen by original ALAS. Supplying a target
not owned by that query fails closed. Supplying no target for a contextual
query also fails closed. This supports two-button dialogs without copying the
handler's confirm/cancel decision into the headless layer.

The evidence promotion and receipt formats now include action promotions and
branch-review state. The G26 popup receipt independently re-proves two resource
mappings and two action mappings against three raw frames.

## Reversible live popup qualification

The game remained on PID `23161` and the existing 12-4 map. A recurrent
`[NetworkDown]` dialog was first recovered only after two increasing
generations (`35360`, `35366`) proved its reviewed content, confirm text,
top-raycast Button, foreground, PID, and stable point `(790,515)`.

The exact map retreat Button was then stable at generations `36110` and
`36115`. One tap opened the confirmation dialog; it did not retreat. The raw
read-only trace contains eight complete samples at generations
`36266..36282`, SHA-256
`265819cd606e86843f740ec6d0d560222a7abcd9315e174b9b4c37fe8fc5f5d5`.

Three generations (`36266`, `36269`, `36275`) promoted:

- generic `POPUP_CANCEL` observation and exact cancel action;
- true-branch-only `POPUP_CONFIRM` observation and exact confirm action.

The cancel Button was then re-proved at generations `36814` and `36819`, with
exact text `取 消`, exact retreat content, and stable point `(490,515)`. Only
that cancel target was tapped. Generation `37055` showed the map still open,
one top-raycast retreat control, no Msgbox, no network dialog, and the same
PID. The retreat confirm target was never tapped.

The generic popup mappings intentionally do not match on message content;
that mirrors original ALAS's generic button-template semantics. The existing
compound `network_down` blocker still wins before either action. Offline proof
confirmed that both popup targets resolve on the retreat trace and that the
same cancel request is rejected on the network-down trace.

## Validation

- Full controller suite: `311/311` passed.
- Focused combat observer suite: `29/29` passed.
- Maximum ten-phase original-ALAS replay: passed with 135 queries over the
  unchanged canonical 41 names and the unchanged eight virtual actions.
- G25 seven-frame real observer fixture: parsed unchanged at generations
  `3999,5898,6164,6653,8483,8630,8693`.
- G26 popup receipt verification: passed, two resources and two actions.
- Current coverage: canonical `13/41`, defensive `14/52`, actions `9/37`.
- `branch_review_complete=false`, `blocker_review_complete=false`,
  `production_ready=false`.

## Next gates

1. Qualify paired guild/mission dialogs and their two explicit targets.
2. Qualify passive stage-page anchors and reversible preparation-cancel
   targets.
3. Capture ship-drop and alternate battle/experience results without aliasing
   them to the S variants.
4. Treat retirement, ambush, and story-option entry as nested branches; expand
   and review their internal query/action surfaces before setting branch
   review complete.
5. Complete blocker review over every newly reachable foreground surface.

No count in this report authorizes production combat. The G18 stop remains the
enforced boundary.
