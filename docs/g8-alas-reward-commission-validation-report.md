# G8 real ALAS reward and commission validation

## Outcome

G8 records two complete real upstream-ALAS closures and one narrower live
mutation proof on `emulator-5580`:

1. ALAS's original reward state machine completed twice with typed semantic
   inputs and a zero claim budget.
2. ALAS's original commission state machine completed a zero-start dry run and
   a later zero-budget run without starting another commission.
3. Between those runs, the positive-budget command injected exactly one
   reviewed zero-oil start and proved its typed running post-state. That command
   then exposed a previously undocumented detail-view transition and did not
   return cleanly. The transition fix has unit and patch validation, but a fresh
   positive-budget full-command clean exit was intentionally not obtained by
   starting a second commission.

This is not full unattended ALAS qualification. Reward claiming, commission
reward receipt, list scrolling, nonzero-oil commissions, and other task
mutations remain separate gates.

## Pinned runtime

| Item | Value |
| --- | --- |
| Upstream ALAS | `81ccf63b4540f00241628c82a58c02c7a2bb11af` |
| Device | `emulator-5580` |
| Package | `com.bilibili.azurlane` |
| Game build | pinned CN `9.7.10` fingerprint |
| Observer/driver revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| Semantic mode | `ALAS_SEMANTIC_MODE=1` |
| Commission rewards | disabled |

The game was already running for this validation. No game launch or restart was
performed. ADB screenshots were black throughout, so the run exercised the
typed observer path and did not rely on successful pixel capture.

## Reward double run

The patched checkout ran the real `Reward` command twice. On each pass ALAS
owned page navigation, notice handling, daily/weekly ordering, retry timers,
and termination. The semantic adapter supplied task-page identity, sidebar
state, row disposition, and reviewed return controls.

Both passes observed a claimable row state and stopped before claim input
because the independent mission claim budget was zero. No reward input was
injected. The two command results were:

```text
ALAS_REWARD_RESULT True
ALAS_REWARD_SECOND_RESULT True
```

## Commission dry run

With `ALAS_SEMANTIC_COMMISSION_START_BUDGET` absent, ALAS scanned the daily and
urgent tabs, built its normal `Commission` objects from typed Unity rows, and
applied its existing `cube` preset. It selected these daily candidates in its
normal priority order:

- `高阶战术研发II`, level 50, 7200 seconds;
- `高阶战术研发I`, level 50, 3600 seconds;
- `日常资源开发III`, level 15, 3600 seconds.

The adapter stopped ALAS before row selection because the start budget was
zero. The command returned `ALAS_COMMISSION_DRY_RESULT True`.

## One controlled start

The budget was then set to the canonical integer `1`. ALAS selected the exact
typed row for `高阶战术研发II`. Its detail identity was re-read as level 50,
7200 seconds, six empty ship slots, and oil cost `0`. The reviewed recommend
input assigned six ships. The start input was admitted only after the adapter
revalidated all of the following:

- the original row signature and selected detail name/level/duration matched;
- at least three ships were assigned;
- oil cost was exactly zero;
- one independent start-budget unit remained;
- package, foreground activity, freshness, bounds, blockers, and exact input
  target still passed.

Exactly one commission-start input was injected and the budget immediately
became zero. The pinned game leaves a successfully started commission on its
detail view. Typed post-state proved the same name, level, and type, a countdown
of `7124` seconds, the exact `tag_ongoing` marker, and the action label `取消`.
That combination is now the success postcondition; the cancel action itself is
never allowlisted as a start action.

The positive-budget live command exposed this previously undocumented
post-start detail state after the successful input, then exited with an error
while probing the now-disabled recommend target. The adapter was corrected to
recognize the running detail, log the proof, return through the exact back
target, and re-enter the commission list through ALAS navigation. No second
start was attempted to manufacture a clean positive-budget rerun. That final
clean-exit path therefore remains unit/pinned-patch validated rather than
live-repeated.

## Zero-budget second pass

The follow-up ALAS `Commission` command ran with the start budget reset to zero.
It parsed the same commission as `running` with `01:53:44` remaining, counted
`1/4` running commissions, and scheduled the next run for the typed finish
time. It then stopped before selecting either remaining candidate:

```text
Semantic commission start budget exhausted
Commission finish: ['2026-08-09 16:52:07']
ALAS_COMMISSION_SECOND_RESULT True
```

No commission reward was collected and no second commission was started.

## Fail-closed boundaries

- Commission start defaults to budget `0`; malformed integers such as `01`
  are rejected.
- Start budget is independent of mission claims and commission rewards.
- The current live mutation slice permits only exact pending, zero-oil rows.
- Pending `kongxian_bg` and running `tag_ongoing` are the only reviewed row
  status markers. Unknown markers fail closed.
- The adapter uses only visible typed rows. Raw scroll, swipe, coordinate, OCR,
  and screenshot fallbacks remain rejected.
- Event commission classification, duplicate-identity resolution after list
  reordering, commission reward receipt, cancellation, and unattended repeated
  starts are not qualified by this result.
- A fresh positive-budget command that exercises the corrected post-start
  return path and exits cleanly is still an open live gate.

The controller suite, Python compilation, whitespace check, and clean
`git apply --check` against the pinned upstream checkout are release gates for
this slice.
