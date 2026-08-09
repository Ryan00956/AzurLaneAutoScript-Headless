# G8 real ALAS reward and commission validation

## Outcome

G8 now covers the real pinned ALAS reward and commission state machines with
independent, bounded mutation budgets:

1. Two real `Reward` commands completed with typed semantic inputs and a zero
   mission-claim budget.
2. A zero-start `Commission` dry run preserved ALAS selection and scheduling
   while refusing row input.
3. Two separate one-start invocations started `高阶战术研发II` and
   `高阶战术研发I`; both obtained typed running-state proof. No third start was
   attempted.
4. One one-reward invocation claimed the finished `高阶战术研发I`. The original
   command failed closed during popup cleanup because the observer's 64-Button
   buffer became full. After increasing the capacity to 128 and restarting,
   an exact typed counter of zero plus a complete zero-budget ALAS replay proved
   that the claim succeeded and was not repeated.
5. A later naturally completed `日常资源开发III` produced a clean, same-call
   `CommissionRewardProof`: exact finished count `1 -> 0`, the reviewed
   ship-EXP and AwardInfo close chain, successful ALAS completion, and a full
   reward/start-budget-zero replay.
6. The five-row daily list passed exact typed scrollbar round trips and the
   original ALAS multipage scan without duplicate running rows.

The first reward remains recovery-qualified historical evidence. Commission
reward budget `1` is now also clean-qualified by the later independent natural
completion and in-context proof.

This is not full unattended ALAS qualification. Larger budgets, nonzero-oil
starts, cancellation, gestures outside the exact reviewed commission handle,
and other task mutations remain separate gates.

## Pinned runtime

| Item | Value |
| --- | --- |
| Upstream ALAS | `81ccf63b4540f00241628c82a58c02c7a2bb11af` |
| Device | `emulator-5580` |
| Package | `com.bilibili.azurlane` |
| Game build | pinned CN `9.7.10` fingerprint |
| Observer/driver revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| Final observer APK SHA-256 | `3b86a745cefbc2a493b941571e6929e965cd7f44be4a2a14ccfa257efdf99fed` |
| Semantic mode | `ALAS_SEMANTIC_MODE=1` |
| Qualified start/reward budget | `1` per controlled invocation |

Every game launch and restart used Unity `-force-gfx-st`. The final retained
restart is recorded in
`evidence/g4-game-init-20260809T090409Z-emulator-5580`. ADB screenshots were
black throughout, so all decisions and inputs used the typed observer rather
than pixel fallback.

## Reward no-claim runs

The patched checkout ran the real `Reward` command twice. On each pass ALAS
owned page navigation, notice handling, daily/weekly ordering, retry timers,
and termination. The semantic adapter supplied task-page identity, sidebar
state, row disposition, and reviewed return controls.

Both passes observed a claimable row state and stopped before claim input
because the independent mission claim budget was zero:

```text
ALAS_REWARD_RESULT True
ALAS_REWARD_SECOND_RESULT True
```

## Commission dry run

With commission start budget zero, ALAS scanned the daily and urgent tabs,
built its normal `Commission` objects from typed Unity rows, and applied its
existing `cube` preset. It selected these daily candidates in normal priority
order:

- `高阶战术研发II`, level 50, 7200 seconds;
- `高阶战术研发I`, level 50, 3600 seconds;
- `日常资源开发III`, level 15, 3600 seconds.

The adapter stopped ALAS before row input. The command returned
`ALAS_COMMISSION_DRY_RESULT True`.

## Two bounded starts

Each positive invocation used the canonical integer start budget `1`. Before a
start input, the adapter required the original typed row signature to match the
detail name, level, and duration, at least three assigned ships, exact zero oil
cost, and one remaining independent budget unit. Package identity, foreground,
freshness, unique bounds, blockers, and top EventSystem raycast also had to
remain valid.

The first invocation started `高阶战术研发II`. Its post-state showed the same
identity at a decreasing countdown, exact `tag_ongoing`, and the `取消` action.
This exposed the game's post-start detail view and led to the reviewed exact
detail-back transition.

The second invocation started `高阶战术研发I` and logged:

```text
SemanticCommissionStart 高阶战术研发I: 3600s -> 3599s, tag_ongoing
```

It returned through the exact detail back target to the list. The command then
encountered a transient truncated Image frame during ALAS's redundant tab
reset. Semantic transition reads now retry only complete snapshots, and the
pinned patch skips that reset after a proved start exhausts the budget. No
third commission was started to manufacture another positive run.

A subsequent zero-budget command observed both running rows, stopped before a
third selection, and returned successfully.

## One bounded reward and recovery proof

At the first finish window, the commission reward budget was set to `1` while
the start budget remained `0`. The reward preflight read the exact typed
finished counter as `1`. The adapter re-read the counter immediately before
input, again required exactly `1`, injected one exact
`reward/commission/finish` input, and consumed the budget. Duplicate ALAS
probes of that resource returned the cached receipt and could not inject a
second finish input.

ALAS then used its existing reward loop to close the reviewed
`reward/ship-exp/close` and `reward/award-info/close` targets. During that
transition, the combined reward/award hierarchy filled the native fixed
64-Button array. The observer reported `truncated=true`, so the adapter refused
to treat the state as proof and the original command exited with an error.

The buffer was increased to 128, the native observer was rebuilt, and the game
was restarted with `-force-gfx-st`. The live snapshot then reported 58 Button
records with `truncated=false`, while the typed UI snapshot was also complete.
A reward-dashboard read with both budgets zero proved:

```text
ALAS_COMMISSION_AFTER_FINISHED_COUNT=0
ALAS_COMMISSION_AFTER_ZERO_PROOF=True
```

A full real ALAS `Commission` replay from the main page, again with both
budgets zero, then scanned the remaining rows, reported one running commission,
refused all starts, and completed:

```text
Running 1/4
Semantic commission start budget exhausted
Commission finish: ['2026-08-09 16:52:07']
ALAS_COMMISSION_POST_CLAIM_BUDGET0_RESULT=True
```

Together, the exact `1` preflight/revalidation, one cached finish receipt,
reviewed popup chain, exact post-restart `0`, and successful zero-budget replay
show that one reward was claimed and could not be repeated. Because the first
process lost its flow context at the capacity gate, this cross-run evidence is
kept distinct from the clean in-context proof required on future claims.

## Clean one-budget reward follow-up

A later bounded start used the existing zero-oil start gate to start
`日常资源开发III` and logged the exact typed transition
`SemanticCommissionStart 日常资源开发III: 3600s -> 3599s, tag_ongoing`. It was
then allowed to finish naturally; no clock change, quick-finish item, or
additional commission was used to manufacture the reward event.

On the reward dashboard, the typed finished counter changed from `0` to `1` at
observer generation `2218`. A real ALAS invocation used reward budget `1` and
start budget `0`. The adapter revalidated finished=`1` immediately before the
only finish input. ALAS closed the reviewed ship-EXP and AwardInfo targets, and
the same invocation logged:

```text
SemanticCommissionReward 1 -> 0,
close=['reward/ship-exp/close', 'reward/award-info/close']
ALAS_COMMISSION_CLEAN_REWARD_RESULT True
```

ALAS probed its cached AwardInfo resource more than once after the Unity object
disappeared. The adapter reused the already-recorded exact receipt for those
late probes; it did not inject another ADB input. A distinct new AwardInfo
target would still require a new exact click.

An independent dashboard read then returned finished=`0`. A complete second
ALAS invocation with both budgets at zero returned successfully, scanned all
five replacement pending rows, and reported zero running rows:

```text
CLEAN_REWARD_POST_FINISHED 0
ALAS_COMMISSION_CLEAN_POST_BUDGET0_RESULT True
ALAS_COMMISSION_CLEAN_POST_DAILY_COUNT 5
ALAS_COMMISSION_CLEAN_POST_RUNNING 0
```

This later event is the clean same-context qualification that the earlier
capacity-fault recovery could not provide.

## Typed multipage commission follow-up

The daily list later contained five rows, so the fifth row was outside the
initial actionable viewport. The native observer now evaluates EventSystem
top-raycast only for the exact
`EventUI(Clone)/blur_panel/adapt/scroll_bar/Image` handle. The controller
requires a complete typed Image snapshot, the exact track/handle pair,
reviewed geometry, foreground continuity, a newer generation, and movement in
the requested direction before it accepts each bounded vertical handle
gesture. Returning to the top permits at most six individually proven steps.
There is no generic semantic swipe API.

The live handle was top-raycastable. Its normalized position moved from the
top through `0.695` to `0.998`; stable actionable row indexes changed from
`0-3` to `0-4` and then `1-4`. Returning to the top reached `0.010`. Running
countdown ticks and lifecycle changes are excluded from the viewport identity,
so they cannot prove a page transition. A complete typed Image snapshot with
neither track nor handle is accepted only as an exact single-page state; a
partial or ambiguous pair fails closed.

The pinned ALAS scan now reuses its original `_commission_scan_list()` loop and
delegates only its scroll operations to those typed primitives. Semantic
commissions carry a stable `(daily|urgent, row_index)` key so a ticking running
row is deduplicated across viewports while two real same-name rows at different
indexes remain distinct. A full reward/start-budget-zero run reported:

```text
ALAS_COMMISSION_MULTIPAGE_BUDGET0_RESULT True
ALAS_DAILY_COUNT 5
ALAS_DAILY_KEYS [('daily', 0), ('daily', 1), ('daily', 2), ('daily', 3), ('daily', 4)]
ALAS_DAILY_RUNNING 1
```

The urgent list had no instantiated scrollbar and was correctly treated as a
single page. No reward or start mutation was admitted by this run.

## Additional hardening

- Commission reward and start permissions are independent canonical integer
  budgets and default to `0`.
- The removed boolean `ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS` is rejected;
  tactical rewards require the separate
  `ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS=1` opt-in.
- Typed transition reads retry a small fixed number of times, but never accept
  missing, incoherent, or truncated snapshots.
- An empty commission list is accepted only with the exact typed
  `暂无可以进行的委托` marker.
- `POPUP_CONFIRM`, `POPUP_CANCEL`, and `POPUP_CONFIRM_UI_ADDITIONAL` resolve
  only for the exact Chinese reconnect prompt ending in `[NetworkDown]`, the
  exact `取消`/`确定` pair, and a top-raycast target. Immediately before the
  clean reward run, one real outage blocked the commission page. The exact
  reviewed confirm target was top-raycastable and restored the page; no other
  Msgbox prompt is admitted by this mapping.
- The current start mutation slice permits only exact pending, zero-oil rows;
  cancellation remains unallowlisted.

## Verification

- Controller suite: `148 passed`.
- Main Python and patched ALAS compilation: passed.
- Native observer build with 128 Button records: passed.
- Final APK installation and post-restart complete snapshot: passed.
- `git diff --check`: passed.
- Clean `git apply --check` against pinned upstream ALAS: passed.
