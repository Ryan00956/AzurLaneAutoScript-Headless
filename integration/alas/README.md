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
not typed. The fleet sortie target is not mapped; formation-layout, map
movement, and battle input remain unauthorized. Complete patched commands
return success for Tactical, Research, Dorm, and the bounded campaign slice. A
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
fleet restrictions, formation-layout changes, sortie, map and battle state,
Lua/game-state access, other reward popups, gestures outside the exact
commission handle, and full unattended task flows remain fail-closed.
