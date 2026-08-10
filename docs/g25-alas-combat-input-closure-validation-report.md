# G25 ALAS combat input-closure validation

Date: 2026-08-10

## Outcome

G25 closes the three evidence gaps left by G24: the original ALAS
automation-off switch branch, the short enemy-searching animation, and ordered
six-ship HP/level input. The behavioral owner is still pinned ALAS. The
headless layer supplies exact observations and one-use guarded actions; it does
not replace `_goto()`, `combat_preparation()`, automation handling, combat,
result handling, enemy searching, arrival, or map mutation.

Production remains fail-closed. Exact resource coverage is `12/41`, ordered
fleet statistics are qualified, but the blocker review is incomplete and 29
defensive resources remain unqualified. Therefore `production_ready=false`
and the production runner remains stopped at G18.

## Observer and device identity

- Package: `com.bilibili.azurlane` 9.7.10 x86_64.
- Driver revision: `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Observer APK: `artifacts/AngleLibraries-g25-automation-image.apk`.
- Observer APK SHA-256:
  `15f28390d3d78f8678b142f630bb4eec10a81baf30ab4336c6096e095e5552f4`.
- Live device: `emulator-5580`; stable game PID `23161` after the observer
  restart.

The automation `Toggle` itself is a zero-area control. Its checked state is
valid passive evidence, but it is not an action target. G25 adds top-raycast
evaluation only for the exact child Image
`ChapterPreCombatUI(Clone)/adapt/middle/auto_toggle/bg`. Five consecutive ON
frames and 28 OFF frames proved the same bounds
`(725.122,98.674)-(913.728,143.326)` and center `(819.425,121.0)`.

## Original-ALAS automation branch

The bounded replay admits `battle_preparation_automation_off` immediately
before normal battle preparation. Original ALAS observes `AUTOMATION_OFF`,
logs `[Automation] OFF`, invokes its existing `device.click(AUTOMATION_SWITCH)`,
sleeps for one second, and resumes its unchanged preparation loop.

The maximum ten-phase Device-free qualification passed with optional
automation confirmation, automation switching, item reward, and urgent
commission enabled:

- 135 resource queries over exactly 41 pinned names;
- virtual actions: grid, automation confirm, automation switch, preparation,
  S result, item, experience, and urgent commission;
- battle `0 -> 1`, ammunition `5 -> 4`, target cleared, current fleet retained;
- original source map restored and projected map unchanged outside the replay.

The replay now has 16 bounded optional combinations and at most ten frames. No
new resource name or second combat state machine was added.

## Live automation-off mapping and action

One qualification-only exact `bg` click changed the live Toggle from ON to
OFF at generations `3787 -> 3791 -> 3809`. The input was allowed only after two
increasing samples agreed on PID, foreground component, full path, sprite,
top-raycast result, bounds, and center.

The OFF trace is hash-bound as:

- trace: `artifacts/g25-automation-off.trace.json`;
- SHA-256:
  `a0d0bd05fc0c0e2ef50637b38e929e5c5414d2e94d9a1b55b2f434d31c54262d`;
- reviewed generations: `3956,3999,4063`;
- exact evidence: `toggle_off`, child `on/auto_toggle_off`, and actionable
  `bg/auto_toggle_bg`.

After promotion, the normal combat-resource action guard clicked
`AUTOMATION_OFF` at generation `5414` and the live Toggle became ON at
generation `5548`. `BATTLE_PREPARATION` remained blocked while OFF was visible
and became eligible only after the original switch precedence was satisfied.

## Ordered fleet statistics

The map fleet rows reuse the same Unity path for three cloned main-fleet and
three cloned vanguard entries. G25 adds bounded selector ordinals, sorts exact
records by geometry, rejects duplicate/missing clone geometry, and requires the
complete ordinal set `0,1,2` for each branch.

The Unity Image `fill_amount` is constant and does not represent health on this
surface. HP is therefore derived from the exact green-bar width divided by the
original ALAS 66-pixel bar scale; values outside `[0,1]` fail closed. Dynamic
level Text remains exact-path, integer-only input. The promoted live roster is:

- levels: `118,109,117,110,118,107`;
- promotion HP: approximately
  `0.9617,0.8484,0.8863,0.7415,0.9979,0.9417`;
- final post-battle fixture HP: approximately
  `0.9055,0.8226,0.7377,0.6606,0.9791,0.8997`.

The fleet-stat review and receipt re-prove all 12 ordered selectors across
three increasing frames.

## Controlled live battle and short search capture

After exact login and bulletin recovery, original ALAS read the real 12-4 map,
selected the fighting D3 enemy, and spent one admitted zero-distance grid
input at generation `3026`. The guarded result chain then advanced through:

| Resource | Commit generation | Exact point |
| --- | ---: | --- |
| `BATTLE_PREPARATION` | 5970 | `(1142.0,641.467)` |
| `BATTLE_STATUS_S` | 7133 | `(640.0,360.0)` |
| `GET_ITEMS_1` | 7789 | `(640.0,482.067)` |
| `EXP_INFO_S` | 8598 | `(1177.333,665.177)` |

A 20 ms read-only trace around the experience action captured four complete
radar generations `8630,8635,8640,8645`. Three exact identities were stable:

- `RadarEffectUI(Clone)/wenzi` with sprite `suodizhong`;
- `RadarEffectUI(Clone)/wangge` with sprite `zhongjian`;
- `RadarEffectUI(Clone)/saomiaoquyu` with sprite `xuanzhuan`.

The trace SHA-256 is
`71aef13bb927d8006354eb7d842dad86a6fde3edaeddf2fffcf1a76cece1e510`.
Generations `8630,8635,8640` promoted and independently verified
`MAP_ENEMY_SEARCHING`.

## Foreground observation compatibility

Unity keeps some underlying map and battle objects active behind modal pages.
That differs from the original ALAS screenshot `appear()` contract. The input
adapter now applies only evidence-backed foreground masking:

- `ChapterPreCombatUI` suppresses the background `IN_MAP` anchor;
- S, item, and experience result pages suppress the background `PAUSE` anchor;
- a complete parsed campaign-map model proves `IN_MAP` during enemy searching
  and on the stable map.

This translation changes observation semantics only. The original ALAS query
order, branches, sleeps, clicks, and state transitions remain untouched.

## Compiled real observer fixture

Three PID-23161 traces compiled into a phase-label-free seven-frame fixture at
generations:

`3999,5898,6164,6653,8483,8630,8693`

The phases are automation off, preparation, execution, S result, experience,
enemy searching, and stable map. The optional live item page is separately
covered by its guarded action receipt.

- fixture SHA-256:
  `600a6a800ee669c5350e896f5de889c6d5755532b57e3be54289952d2e27af54`;
- candidate report SHA-256:
  `24e2f9c145609bbab1506989913aa82dc41472777a9c1069c48339a924857c89`;
- final map: fleet 1 at D3 with ammunition `1`, fleet 2 at E8 with ammunition
  `5`, D3 enemy absent, newly spawned K6 enemy present.

The fixture is valid evidence, not permission to bypass the manifest gate. A
production observer replay still refuses to start until every resource and
blocker is qualified.

## Validation

- Full controller suite: `310/310` passed.
- Focused combat observer/map suite: `66/66` passed.
- Maximum ten-phase original-ALAS replay: passed.
- Real seven-frame observer fixture compile: passed.
- `AUTOMATION_OFF`, `MAP_ENEMY_SEARCHING`, and fleet-stat promotion receipts:
  passed at promotion time; current final manifest receipt verifies.
- Observer ANGLE build and APK installation: passed.
- Current manifest: `12/41`, fleet stats qualified,
  `blocker_review_complete=false`, `production_ready=false`.

## Remaining gates

- Review and map the 29 remaining defensive ALAS query resources, prioritizing
  popup, ambush, retirement, ship-drop, and alternate-result branches.
- Complete blocker review across those defensive surfaces.
- Exercise the real compiled observer fixture only after the full manifest is
  production-ready; do not add a qualification bypass.
- Keep production at the G18 boundary until those gates close.
