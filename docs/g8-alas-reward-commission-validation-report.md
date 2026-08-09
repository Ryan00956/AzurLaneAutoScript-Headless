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

The reward result is therefore recovery-qualified. It is not represented as a
clean first-attempt command that produced the adapter's in-context
`CommissionRewardProof` object.

This is not full unattended ALAS qualification. Larger budgets, nonzero-oil
starts, cancellation, unrestricted list gestures, and other task mutations
remain separate gates.

## Pinned runtime

| Item | Value |
| --- | --- |
| Upstream ALAS | `81ccf63b4540f00241628c82a58c02c7a2bb11af` |
| Device | `emulator-5580` |
| Package | `com.bilibili.azurlane` |
| Game build | pinned CN `9.7.10` fingerprint |
| Observer/driver revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| Final observer APK SHA-256 | `111ac661e3ba7d9ff0eebeeb4c803f22226092318b0b43161cfe8506a76c8d1d` |
| Semantic mode | `ALAS_SEMANTIC_MODE=1` |
| Qualified start/reward budget | `1` per controlled invocation |

Every game launch and restart used Unity `-force-gfx-st`. The final retained
restart is recorded in
`evidence/g4-game-init-20260809T083326Z-emulator-5580`. ADB screenshots were
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
  exact `取消`/`确定` pair, and a top-raycast target. A real outage was observed,
  but no reconnect input was injected; this path is build- and unit-validated
  only.
- The current start mutation slice permits only exact pending, zero-oil rows;
  cancellation remains unallowlisted.

## Verification

- Controller suite: `139 passed`.
- Main Python and patched ALAS compilation: passed.
- Native observer build with 128 Button records: passed.
- Final APK installation and post-restart complete snapshot: passed.
- `git diff --check`: passed.
- Clean `git apply --check` against pinned upstream ALAS: passed.
