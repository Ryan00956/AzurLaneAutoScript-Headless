# G24 ALAS combat preparation and observer validation

Date: 2026-08-10

## Outcome

G24 closes the live input boundary from the already admitted campaign grid
click through automation confirmation and battle preparation, without replacing
ALAS's combat state machine. The original pinned ALAS chain remains the owner
of `combat_preparation()`, automation handling, combat execution, result
handling, enemy searching, arrival, and map mutation.

Production remains fail-closed. Exact manifest coverage is `10/41`; blocker
review is incomplete and six-ship HP/level mappings are still unqualified.

## Observer and device identity

- Package: `com.bilibili.azurlane` 9.7.10 x86_64.
- Driver revision: `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Observer APK: `artifacts/AngleLibraries-g24-combat-preparation.apk`.
- Observer APK SHA-256:
  `f0c5104112c4ff0ca4b3d96cee82a08bf694442674f2cda8b9ebfb5381a7d2fb`.
- Live device: `127.0.0.1:5581`; stable game PID `19079` for the controlled
  combat and all post-battle captures.

The observer added exact top-raycast evaluation only for
`ChapterPreCombatUI(Clone)/adapt/right/start`. The action remained a typed
Unity Button with stable bounds and point; no image-coordinate fallback was
introduced.

## Original-ALAS replay extension

The bounded replay now admits an optional first `automation_confirm` phase.
That phase exposes exact `AUTOMATION_CONFIRM_CHECK` and
`AUTOMATION_CONFIRM` resources, then lets original
`handle_combat_automation_confirm()` perform its normal click. The complete
nine-phase qualification, including optional item and urgent-commission
branches, passed with:

- phases: automation confirmation, preparation, execution, S result, item,
  experience, urgent commission, enemy searching, stable map;
- 135 resource queries over exactly 41 reviewed names;
- virtual actions: admitted grid, automation confirm, preparation, S result,
  item, experience, and urgent commission;
- battle `0 -> 1`, ammunition `5 -> 4`, target cleared, fleet retained, and
  source/projected maps unchanged outside the isolated replay.

No Android input is used by this replay.

## Live mappings promoted

Three evidence-bound reviews promoted four new resources:

- `AUTOMATION_CONFIRM` and `AUTOMATION_CONFIRM_CHECK`: exact `知道了` dialog,
  `zilv` icon, information title, and top-raycast confirmation Button;
- `AUTOMATION_ON`: exact `Toggle.checked=true` plus the
  `auto_toggle_on` and `auto_toggle_bg` Images;
- `BATTLE_PREPARATION`: exact top-raycast `start` Button,
  `btn_formation_sel`, `WEIGH ANCHOR`, and `出击`.

Together with the six G22/G23 mappings, manifest coverage is now `10/41`.
Toggle state is represented explicitly as `toggle_on` or `toggle_off`; it is
not inferred from OCR or treated as an action target.

## Controlled live chain

After a forced-single-thread restart with the new observer, the exact login
and bulletin controls returned to main. Entering battle resumed the existing
12-4 map with both auto-search and fleet lock visibly off.

Original ALAS then selected the fighting J3 enemy and spent one exact admitted
grid input:

- preflight/admission generation `3780`;
- grid receipt generation `3785`;
- fleet 1 at J3, enemy object `1204090`, ammunition `3`;
- zero-distance route `J3` and original eight-call `_goto()` prefix.

The subsequent actions each required two increasing coherent endpoint triples,
the same PID/foreground, unchanged exact geometry, one-use authorization, and
a qualified manifest resource:

| Resource | Commit generation | Exact point |
| --- | ---: | --- |
| `BATTLE_PREPARATION` | 5094 | `(1142.0, 641.467)` |
| `BATTLE_STATUS_S` | 6788 | `(640.0, 360.0)` |
| `GET_ITEMS_1` | 7389 | `(640.0, 482.067)` |
| `EXP_INFO_S` | 7980 | `(1177.333, 665.177)` |

No urgent-commission dialog appeared in this live battle.

## Compiled observer fixture

Three adjacent read-only traces from PID `19079` were identity-checked and
merged without rewriting their raw frames. The compiler selected:

`3825,5631,6613,7057,7684,8017,8034`

for preparation, execution, S result, item, experience, enemy searching, and
stable map. Generation `8017` contains the exact active
`RadarEffectUI(Clone)` record family; generation `8034` is the stable map.

- Fixture SHA-256:
  `92a4b94dfcf9eb92db5b025c9e5d12e45a2cc5a3c1711cd256bb7c6d0b5630a1`.
- Candidate report SHA-256:
  `88bcc7ee3be477831bb3b9c857ddd4392c459408050df71d563a92373b489622`.
- Stable map: fleet 1 at J3 with ammunition `2`, fleet 2 at E8 with
  ammunition `5`, no J3 enemy, and a newly spawned A7 enemy.

Only one captured generation contained the radar effect, so
`MAP_ENEMY_SEARCHING` was not promoted: the promotion gate still requires at
least two increasing generations. The fixture is a durable evidence artifact,
not a production-ready replay claim.

## Additional compatibility fix

The resumed live map simultaneously exposed both reviewed retreat identities:
the `LevelGrid/.../op1/retreat` scene anchor and the
`LevelStageView/.../retreat_button` overlay control. Map identity now accepts
one or both exact variants and still rejects unknown or duplicate paths. This
restored `campaign_is_in_map=true` without broadening any action mapping.

## Validation

- Full controller suite: `306/306` passed.
- Optional nine-phase original-ALAS replay: passed.
- Observer APK build: passed.
- Each mapping receipt was verified immediately after promotion; the final
  `BATTLE_PREPARATION` receipt also verifies the current `10/41` manifest.
- Multi-trace fixture compile: passed.
- JSON validation and `git diff --check`: passed.

## Remaining gates

- Qualify `AUTOMATION_OFF` and the original ALAS automation-switch action.
- Capture at least two increasing radar-search generations before promoting
  `MAP_ENEMY_SEARCHING`.
- Add evidence-bound six-ship HP and level promotion.
- Continue mapping the remaining defensive ALAS query surface and complete
  blocker review.
- Keep the canonical production runner stopped at G18 until the manifest is
  production-ready.
