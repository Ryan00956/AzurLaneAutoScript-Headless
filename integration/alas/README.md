# ALAS integration overlay

Target: upstream commit `81ccf63b4540f00241628c82a58c02c7a2bb11af`.

The patch adds opt-in observation and action ports without changing default
ALAS behavior:

- `ModuleBase.appear()` routes named resources to the semantic adapter.
- `ModuleBase.match_template_color()` and `image_color_count()` route the
  remaining reward-state observations to the same adapter.
- `Control.click()` routes mapped clicks to the observer-derived ADB point.
- `Ocr.ocr()` resolves reviewed OCR rectangles from typed Unity text while a
  semantic session is active; it never silently uses pixels in semantic mode.
- Raw multi-click, long-click, swipe, drag, and low-level click dispatch are
  rejected while semantic mode is active.
- `Reward.reward_mission()` only brackets one adapter context. The original
  ALAS reward state machine, including its timers, retries, collection loop,
  popup receive loop, and daily/weekly branch ordering, remains the owner.

The adapter is deliberately incomplete. Reviewed main-page aliases and the
explicit task virtual resources are accepted. The widely reused `BACK_ARROW`
is contextual only inside reviewed commission/tactical flows and remains
unmapped elsewhere. `GOTO_MAIN` resolves only when one reviewed campaign-menu,
construction, or research page identity supplies a unique exact back target.
During a task context, unrelated presence checks may return false only while
an independently proven task surface exists; otherwise they also raise. The
adapter never falls back to a black screenshot or an asset's old rectangle.

Mapped presence/clicks also require the observer's top EventSystem raycast
result to belong to the mapped Button. Active/interactable state and bounds
alone are insufficient.

The generic ALAS `POPUP_CONFIRM` path is not broadly enabled. It resolves only
when the typed Msgbox content exactly matches the pinned Chinese
`服务器连接失败，是否重新连接？ [NetworkDown]` prompt, both button labels are
the reviewed cancel/confirm pair, and the chosen confirm Button is the top
EventSystem raycast target. Other confirmation dialogs remain closed.

The mission input provider is narrower than normal ALAS reward handling. It
translates ALAS's `MISSION_MULTI`, `MISSION_SINGLE`, `MISSION_UNFINISH`, page,
reward-popup, and default-navbar observations from typed Unity snapshots. It
requires the same mission signature across two increasing generations before
reporting a claimable or unfinished state. The provider maps the exact
`GetAllButton` and reviewed `AwardInfoUI` close actions back into ALAS's normal
claim/click/receive loop. Claim input remains disabled by default even when
`GetAllButton` is present.

One controlled claim-all per `reward_mission()` invocation is available only
with a second explicit opt-in:

```powershell
$env:ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE = '1'
```

The adapter resets a one-input claim budget when ALAS enters
`Reward.reward_mission()` and discards it in `finally`. The claim action still
requires the unique actionable `GetAllButton`; ALAS then owns the popup receive
loop while `GET_ITEMS_1`/`GET_ITEMS_2` are translated to exactly one reviewed
`AwardInfoUI`/`AwardInfoUI1` close target. Without this variable, ALAS may
observe the claimable state but the first claim action fails closed before ADB
input.

The typed observer exposes the six mission sidebar Images with exact selected
and unselected sprite pairs. ALAS's existing Navbar remains the state-machine
owner; reads and clicks are translated to those reviewed Images. A live adapter
loop selected weekly, proved the selected sprite, returned to all, and exited
the task page. Positive mission red-dot behavior is not yet proven. Weekly-only
full reward runs, numeric-row claiming, ship-reward popups, and empty-page
inference remain closed.

Additional typed readers cover reward summary counts, commission rows and
empty state, tactical slots/books/skills, research cards/detail/queue,
construction pool/cost/submit confirmation, dorm summary/feed inventory, and
visible campaign chapter/stage labels. The pinned patch changes those ALAS
observation and input ports while leaving ALAS responsible for filtering,
selection, retry loops, queue filling, popup loops, and scheduling.

When ALAS is already on a normal campaign map, the patch now passes ALAS's own
map shape, land cells, and enabled fleet count to the read-only semantic map
model. The returned stable cells, fleets, enemies, and pickups are validated
against a deep copy of ALAS's native `CampaignMap`, initialized through
`map_data_init()`, and planned through ALAS's existing path methods. The
invocation logs immutable per-marker reachability summaries and returns before
ALAS's existing retreat branch. A semantic marker is assigned to the displayed
fleet only when its suffix uniquely matches one typed ship sprite in the exact
top-stage roster across stable generations. The displayed `1|2` number is then
translated with ALAS's existing reversed-fleet rule before native indexed
locations are populated. G33 separately qualifies one ALAS-requested typed
viewport swipe. G34 then lets original `Camera.update()` consume a typed Unity
`View` and lets original `_goto()` recheck the target, but no grid Button,
fleet movement, combat, retreat, or map reward input is production-enabled.

The indexed projection is now also passed to a decision-only executor. It
calls ALAS's original `find_path_initial()` and `battle_function()` on an
isolated shell, keeps campaign-file `RoadGrids` attached to transactionally
overlaid native grid identities, and intercepts the first public `goto()`.
The runner logs ALAS's branch, logical fleet, target, expected result, cost,
full route, and optimized goto nodes, then returns. Any Device access, fleet
switch, `_goto()`, combat, retreat, timed emotion wait, unknown target, stale
projection, or route disagreement fails closed.

Campaign viewport movement has a separate canonical integer budget and remains
closed by default:

```powershell
$env:ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET = '1'
```

G33 uses one unit only at ALAS's existing `device.swipe_vector()` boundary.
The original `focus_to -> map_swipe -> _map_swipe` path owns the request; the
adapter validates the requested target and turns only the final vector into a
typed semantic gesture. A fresh same-PID map must preserve its logical
signature and all visible cells under a coherent planar projective transform,
with the requested target ending exact top-raycast. The qualification proof
stops before any grid click and keeps production enablement false.

G34 patches only ALAS's existing `Camera._update_view()` semantic-session
input. A normalized projective model turns fresh Unity grid geometry into the
`View` fields consumed by original `Camera.update()`; ALAS still owns its wait,
swipe prediction, camera coordinate, centering, and global-to-local logic. The
qualification continues through original `_goto()` and captures its final
`device.click(grid)` statement without delegating it. On the live F6 case,
`grid_input_injected=false`. Because that target was already within
`_walk_sight`, the harness used original `focus_to(F6)` as a bounded prelude;
an organically out-of-sight `_goto()`-initiated swipe remains a later gate.

Campaign combat has a separate canonical integer budget and remains closed by
default:

```powershell
$env:ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET = '1'
```

G17 uses this value to prepare one decision-bound, zero-distance
fighting-enemy admission. It revalidates the exact Unity cell path, geometry,
top raycast, foreground, and blockers. G18 then runs ALAS's original `_goto()`
on an isolated shell through the low-HP check, original fleet ensure,
visibility/focus/centering, global-to-local conversion, color initialization,
and its own `device.click(grid)` statement. That call is captured and aborted;
the dynamic adapter input port is not invoked, the budget is not consumed, and
no grid tap is injected. The runner logs the eight-call prefix and raises
`ScriptEnd`. Do not treat a positive budget as live combat enablement until
the post-click ALAS combat observation chain is also qualified.

G19 supplies a separate qualification-only replay for that post-click chain.
Six complete typed phase tokens drive the original ALAS combat preparation,
execution, status, enemy-searching, arrival, native-map mutation, and path
rebuild on an isolated shell. Its D6, preparation, S-result, and experience
actions are virtual records only. The canonical ALAS patch deliberately does
not import or invoke this synthetic replay; the production runner remains at
the G18 capture boundary until every phase has an exact live Unity mapping.

G20 adds that replacement input boundary without changing the ALAS patch or
state machine. It accepts six complete, hash-bound raw observer snapshots only
when all 38 resource queries, blockers, three post-grid action Buttons, and
fleet HP/levels have reviewed exact Unity mappings. Fixture-provided phase
tokens are rejected. The G20 baseline was deliberately `0/38`, so the boundary
was testable but could not run production combat or spend the campaign-combat
budget.

G21 made the remaining evidence work reproducible. At that gate the sole
durable mapping source, `combat-observer-manifest.json`, retained exactly 38
entries; later gates expand and version that surface explicitly.
The package-verified trace recorder stores only raw, hash-bound observer
triples with `input_injected=false`:

```powershell
python scripts/python/capture_alas_combat_observer_trace.py `
  --serial 127.0.0.1:5581 `
  --output artifacts/g21-combat-trace.json
```

After review chooses six exact increasing generations, the fixture compiler
emits phase-local candidates and reconstructs the two map frames offline using
the pinned 12-4 topology. Neither tool imports or changes ALAS state-machine
logic, writes mappings automatically, or enables D6.

G22 adds a separate evidence-review promotion boundary. A review names exact
generations and exact all-of selectors; the promoter reparses the raw trace,
requires every selector in every chosen frame, computes evidence hashes, and
emits a manifest plus a source-frame receipt. The receipt verifier binds those
selectors back to the current manifest and raw frame hashes.

The first review promotes only `IN_MAP` from three complete blocked-surface
frames (`1/38`). It also records the exact `network_down` blocker as one
three-selector all-of rule. Blocker rules are now named and grouped, so a
generic cancel Button alone cannot trigger the rule. The separately explicit
`blocker_review_complete=false`, the remaining `37/38`, and unqualified fleet
stats keep `production_ready=false`:

```powershell
python scripts/python/verify_alas_combat_mapping_receipt.py `
  --trace artifacts/g21-current-blocked-trace.json `
  --receipt integration/alas/combat-observer-reviews/g22-in-map-network-down.receipt.json
```

This is still an observer-input change only. The canonical ALAS patch, G19
state machine, G18 production stop, D6 input, and combat budget are unchanged.

G23 uses the same separation for a qualification-only live combat chain. The
grid acquisition tool lets original `_goto()` spend one admitted exact map
input while an independent recorder remains read-only. Result-page actions
require two stable generations, exact foreground/PID/path/geometry continuity,
and an explicit one-use action budget.

The observed post-battle sequence may include AwardInfo and an urgent
commission dialog. G19/G20 therefore accept only four bounded 6-8 phase
sequences, with `GET_ITEMS_1` and `GET_MISSION` in fixed positions. Original
`handle_get_items()` and `handle_urgent_commission()` still own those clicks.
The union query surface is now 40 resources because the urgent-commission path
also reaches `EXP_INFO_A` and `EXP_INFO_B` fallbacks.

The checked-in manifest is currently `6/40`: `IN_MAP`, `PAUSE`,
`BATTLE_STATUS_S`, `GET_ITEMS_1`, `EXP_INFO_S`, and `GET_MISSION`. Blocker
review and fleet stats remain incomplete, so production replay and the G18
runner stop remain fail-closed. See
`docs/g23-alas-controlled-combat-acquisition-validation-report.md`.

G24 adds only observer inputs and qualification tooling; it does not change the
canonical ALAS patch or move the production stop. The bounded replay can place
an optional automation-confirm phase before preparation, so original
`handle_combat_automation_confirm()` owns the exact `知道了` action. The union
query surface is now 41 resources.

`AUTOMATION_ON` is an exact typed Toggle state (`checked=true`), while
`AUTOMATION_CONFIRM` and `BATTLE_PREPARATION` remain exact top-raycast Button
actions. Three reviewed receipts raise checked-in coverage to `10/41`.
Adjacent same-PID read-only traces can be identity-checked and merged by the
fixture compiler, which produced a seven-frame J3 evidence fixture. Blocker
review and fleet stats are still incomplete; `AUTOMATION_OFF`, automation
switching, `MAP_ENEMY_SEARCHING`, and the remaining defensive resources remain
unqualified. Therefore `production_ready=false` and the G18 runner stop is
unchanged. See
`docs/g24-alas-combat-preparation-observer-validation-report.md`.

G25 closes automation switching, radar searching, and ordered fleet statistics
without moving the G18 production stop. G26 then corrects the readiness model:
the canonical all-false replay still asks 41 names, while its pinned defensive
allowlist contains 52 possible queries and their original handlers can select
37 distinct click targets. Manifest v2 stores observations and actions
separately and adds an independent branch-review gate.

A reversible live retreat dialog promotes generic `POPUP_CANCEL`, the
true-branch-only `POPUP_CONFIRM`, and both exact top-raycast targets. The
headless boundary accepts a contextual target only when it is one of the
targets the original query may drive; ALAS still chooses confirm versus cancel.
Current coverage is canonical `13/41`, defensive `14/52`, actions `9/37`, with
branch and blocker review incomplete and `production_ready=false`. See
`docs/g26-alas-defensive-input-surface-validation-report.md`.

G27 upgrades the manifest/review/receipt schemas to v3. An action target now
contains named, evidence-bound variants; the observer accepts a target only
when exactly one complete variant is visible. This is required for
`MAP_PREPARATION_CANCEL`, whose stage-information and fleet-selection pages
have different Unity back buttons even though original ALAS uses the same
target name. The action commit binds and rechecks the selected variant; the
adapter still does not decide which ALAS branch should run.

The exact defensive surface is now 54 queries and 38 actions after adding the
source-reachable `EXERCISE_CHECK` and `STORY_LETTERS_ONLY` paths. Ambush,
retirement, and story roots are reported separately and their blocker reviews
remain open. Repeated historical frames qualify campaign, map-preparation,
fleet-preparation, and battle-preparation-under-overlay inputs. Current coverage
is canonical `16/41`, defensive `18/54`, actions `12/38`, and blockers `1/4`;
fleet stats are qualified, but `production_ready=false` and G18 remains the
production stop. See
`docs/g27-alas-action-variant-and-nested-branch-validation-report.md`.

G28 adds a separate Device-free defensive-branch replay. It instantiates the
pinned real `Campaign`, copies it per scenario, and invokes the original ALAS
methods for alternate result/experience grades, guild and mission popups,
retirement, story, and ambush evasion. The virtual boundary rejects unknown
queries, extra or reordered actions, unowned targets, unexpected Device access,
and changed source method owners. The checked record binds the ALAS commit and
the four participating source files:

```powershell
python scripts/python/verify_alas_combat_defensive_branch_replay.py `
  --alas-root H:\program\AzurLaneAutoScript-patchcheck
```

All 16 scenarios pass with source restoration and zero input. This record does
not contain Unity selectors and explicitly reports
`live_mapping_promoted=false`; manifest coverage stays canonical `16/41`,
defensive `18/54`, actions `12/38`, and blockers `1/4`. See
`docs/g28-alas-defensive-branch-replay-validation-report.md`.

G29 adds a dedicated read-only acquisition boundary for the contextual guild
and mission dialog pairs. It requires three adjacent coherent frames with both
controls simultaneously top-raycast actionable, exact stable paths/names, and
stable geometry. A success writes only a G27 review draft; it never edits the
manifest or performs input:

```powershell
python scripts/python/watch_alas_combat_rare_surface.py `
  --serial 127.0.0.1:5581 `
  --profile guild-popup `
  --trace-output artifacts/g29-guild.trace.json `
  --evidence-output artifacts/g29-guild.evidence.json

python scripts/python/analyze_alas_combat_rare_surface.py `
  --trace artifacts/g29-guild.trace.json `
  --profile mission-popup `
  --output artifacts/g29-mission.evidence.json
```

The first restored-game run saw neither dialog in 25 complete map samples, so
both rare profiles and all four resource/action pairs remain unqualified. See
`docs/g29-alas-rare-surface-acquisition-validation-report.md`.

G30 adds six passive result profiles to the same watcher:

```powershell
python scripts/python/watch_alas_combat_rare_surface.py `
  --serial 127.0.0.1:5581 `
  --profile battle-status-a `
  --trace-output artifacts/g30-result.trace.json `
  --evidence-output artifacts/g30-battle-status-a.evidence.json
```

Available profile names are `battle-status-a` through `battle-status-d` and
`exp-info-a` / `exp-info-b`. Each one verifies the qualified S mapping has not
changed, then requires three repeated exact grade pages and a stable
top-raycast action Button. The current map trace is negative for all six, so
none is promoted. See
`docs/g30-alas-passive-result-surface-validation-report.md`.

G31 removes profile prediction during acquisition. `all` captures one raw
trace and checks all two dialog plus six passive-result profiles:

```powershell
python scripts/python/watch_alas_combat_rare_surface.py `
  --serial 127.0.0.1:5581 `
  --profile all `
  --trace-output artifacts/g31-all.trace.json `
  --evidence-output artifacts/g31-all.evidence.json
```

Exactly one completed child profile exposes one review draft. Multiple matches
are ambiguous and expose none. The prefilter skips only repeated analysis, not
raw samples, and final verification always reruns all eight profiles. See
`docs/g31-alas-combat-surface-multiplex-validation-report.md`.

Commission start has a separate integer budget and remains closed by default:

```powershell
$env:ALAS_SEMANTIC_COMMISSION_START_BUDGET = '1'
```

Each commission invocation receives the configured budget and decrements it
only for an exact start input. The selected row/detail signature, assigned ship
count, zero oil cost, and typed transition to `tag_ongoing` are required. The
live qualified value is `1`; larger budgets are parsing-compatible but are not
live-qualified. Once that single start is proven and its budget is exhausted,
the patch returns through the reviewed detail back target and skips ALAS's
otherwise redundant tab reset.

ALAS also retains ownership of its original multipage commission scan. Only
the exact typed commission scrollbar handle has a gesture adapter: it requires
the reviewed track/handle paths, complete Image state, handle top-raycast,
foreground continuity, newer generation, directional position movement, and a
stable actionable-row viewport change before another page is scanned.
Returning to the top instead requires the exact top position, using at most six
individually proven steps. Countdown and status changes cannot prove a new
page. The exact absence of both track and handle is a single-page state;
partial pairs fail closed. Typed rows use `(daily|urgent, row_index)` as their
merge identity, so overlapping viewports do not duplicate a ticking running
row. No generic ALAS swipe or drag is enabled.

Commission reward receipt uses its own integer budget and remains closed by
default:

```powershell
$env:ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET = '1'
```

The finish input is admitted only when the exact typed commission counter is
`1`, and that counter is re-read immediately before input. One budget unit is
consumed on the exact finish click. ALAS retains ownership of its existing
reward-popup loop; the adapter records only reviewed popup close targets, then
returns to the reward dashboard and requires the finished counter to become
`0`. The removed boolean `ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS` is rejected so
it cannot accidentally authorize an unbounded claim loop. Tactical reward
handling is separately scoped by `ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS=1`.

The following newer mutations are also default-closed integer budgets. Each
unit admits one exact mutation, not an entire task invocation. These minimal
examples admit one unit each:

```powershell
$env:ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET = '1'
$env:ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET = '1'
$env:ALAS_SEMANTIC_RESEARCH_START_BUDGET = '1'
$env:ALAS_SEMANTIC_DORM_COLLECT_BUDGET = '1'
$env:ALAS_SEMANTIC_DORM_FEED_BUDGET = '1'
$env:ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET = '1'
$env:ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET = '1'
$env:ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET = '3'
```

Tactical assignment reuses ALAS's original ship, skill, book-filter, and
course-start state machine. The budget is consumed only by the exact final
course confirmation. Research keeps ALAS's project filter, queue/reward loops,
and scheduler; visual card positions are dynamically revalidated and the
start budget is consumed only when the exact resource prompt matches the
selected project. Dorm keeps ALAS's food filter and count choice, but clicks
the exact food-card Image rather than the adjacent purchase `+`, and proves
inventory `-1` plus food `+value` per budget unit. Construction admits only one
order and cross-checks typed cube/coin costs before the final confirmation.
ALAS's original side and bottom `Navbar` objects consume exact Toggle state;
the queue-empty input additionally requires the selected queue tab, capacity
`2`, and either the exact two-entry empty layout or exact three-entry nonempty
layout. A pre-existing nonempty queue is refused before the bounded submit
instead of being accelerated or collected. The ALAS `GACHA_PREP` warning alias
and `GACHA_ORDER` final-confirm alias are disjoint and reject each other's
dialog.

Tactical assignment, a single research start/reward chain, corrected dorm
food-card input, and final one-order construction submit have live passes.
Dorm quick collect also has a live exact-click pass. The dorm proof observed
inventory `17783 -> 17782` and food `0 -> 1000`; the construction proof opened
the heavy pool with `3662` cubes and `84908` coins, cross-checked a `2` cube +
`1500` coin cost, submitted one order, and observed the queue countdown. The
research invocation admitted six reward units (five queued completions and one
finished card) followed by one exact `G-412` start. Qualified maxima are
therefore tactical assignment `1`, research reward `6`, research start `1`,
dorm collect `1`, dorm feed `1`, and construction submit `1`; larger values
remain unqualified. Campaign stage entry is separately qualified only at `1`
for the exact reversible `12-4 -> map preparation -> fleet preparation ->
cancel` pre-sortie flow. Fleet preparation has a second independent budget
that defaults to zero. Before its first fleet input, the adapter simulates
ALAS's exact normal-mode branch order and requires budget for the complete
ordered mutation plan. The qualified request `(1, 2, 0)` from live
`(1, 2, 1)` consumed exactly three units: clear fleet 2, clear submarine 1,
then select fleet option 2. ALAS's original `FleetPreparation` and
`FleetOperator` loops remained the owners, and its cancel loop restored the
original selection. Hard mode remains closed because its restriction rows are
not typed. One separately budgeted normal-mode sortie is qualified, and the
resulting map is consumed only through the read-only model described above;
formation-layout, map movement, and battle input remain unauthorized. Complete
patched commands return success for Tactical, Research, Dorm, and the bounded
campaign slice. A
full Gacha attempt submitted one exact Light order but returned
false after exposing the now-fixed warning/order phase alias; its corrected
full replay remains gated by the resulting natural nonempty queue.

To stage this against a compatible ALAS checkout:

```powershell
git apply --check H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
git apply H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
$env:PYTHONPATH = 'H:\program\AzurLaneAutoScript-Headless\python'
$env:ALAS_SEMANTIC_MODE = '1'
$env:ALAS_SEMANTIC_DRIVER_REVISION = (Get-Content H:\program\AzurLaneAutoScript-Headless\ANGLE_REVISION -Raw).Trim()
```

Do not enable unattended ALAS operation yet. The ALAS-owned reward flow has a
fresh live zero-claim double run. Commission has two separately bounded live
zero-oil start proofs plus a later one-hour start used to create a natural
completion. The first bounded reward remains recovery-qualified after an old
64-record observer-capacity failure. The later event cleanly produced an
in-context `CommissionRewardProof` from exact counter `1 -> 0`, completed the
reviewed popup chain, and passed a full dual-budget-zero replay. Reward budget
`1` is therefore live-qualified; larger budgets are not. The five-row daily
list also passed exact-handle multipage scanning and stable row-index merging.
Nonzero-oil rows, cancellation, repeated unattended starts, and multi-order
construction are not live-qualified. Numeric-row claiming, campaign hard-mode
fleet restrictions, formation-layout changes, original-ALAS post-swipe view
update and grid recheck, fleet movement, and battle input,
Lua/game-state access, other reward popups,
gestures outside the exact commission handle, and full unattended task flows
remain fail-closed.
