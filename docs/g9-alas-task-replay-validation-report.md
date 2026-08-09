# G9 patched-ALAS task replay validation

Date: 2026-08-09

This gate keeps the pinned ALAS task state machines in control. Semantic mode
replaces only page observations, OCR-derived values, Navbar state, and exact
input endpoints. Every irreversible endpoint remains default-closed behind an
independent integer budget.

## Result

The complete patched ALAS commands for Tactical, Research, and Dorm returned
successfully on `emulator-5580`. Gacha reached and executed one exact bounded
Light-pool order, but that invocation returned `False` after a preparation
alias admitted the final confirmation one state too early. The alias contract
is now split and regression-tested; a pre-existing queue remains fail-closed
and the naturally running order is not accelerated or collected by this gate.

| Command | ALAS-owned behavior retained | Live result |
| --- | --- | --- |
| Tactical | slot scan, ship/skill/book choice, course loop, scheduling | `TACTICAL_RESULT=True`; Hipper course scheduled to 2026-08-10 07:23:35 |
| Research | project filter, detail/start, queue fill, reward loop, scheduling | `RESEARCH_RESULT=True`; exact `G-412` 1500-coin start and queue confirmation; zero-start replay scheduled from the real queue |
| Dorm | page navigation, food filter/count choice, collect loop, scheduling | `DORM_RESULT=True`; exact food-card mutations and exact quick-collect input |
| Gacha | queue flush check, pool choice, affordability, preparation, submit loop | bounded Light order reached the typed queue, but the first complete invocation returned `False`; corrected full-command replay remains pending an empty queue |

## Input and observation contracts added

- Tactical consumes typed slots, candidate ships, skills, books, exact prompt
  text, and one final course-confirm budget. Duplicate navigation and prompt
  transition probes are idempotent.
- Research dynamically revalidates card positions, distinguishes detail,
  running, and finished actions, reads queue capacity/countdowns, and admits
  start, queue, and reward confirmations through separate exact contracts.
- Dorm identifies the CourtYard page, feed panel, empty-food prompt, statistics
  popup, and food cards from exact typed hierarchy and sprite evidence. Food
  proof requires inventory `-1` and the expected food increase, allowing only
  the bounded concurrent consumption of up to six resident ships.
- Gacha consumes exact side/pool Toggles, pool costs, the global coin counter,
  one-order confirmation text, and both empty `list_single_line` and nonempty
  `list_mult_line` queue layouts. A task starting on the Build page can read
  the exact global resource panel without first returning to Main.
- The Gacha `POPUP_CONFIRM_GACHA_PREP` alias can confirm only the exact UR-point
  warning. `POPUP_CONFIRM_GACHA_ORDER` can confirm only the typed one-order
  dialog. The two stages reject each other.

## Live evidence and incidents

Tactical assigned Hipper, selected skill `荆棘与坚盾`, selected the matching T4
book, and returned through ALAS scheduling. Research admitted one exact
`G-412` start with the `1500`-coin prompt, added it to the queue, confirmed the
irreversible queue prompt, and later read the real queue to schedule the next
run.

During Research recovery, the selected detail root was initially allowed as a
generic quit target while a finished action was also present. The project
completed during the delay and that root click opened an award popup under a
zero reward budget, claiming the finished reward unintentionally. The popup
was closed, and the oracle now forbids detail-root input whenever the exact
finish action is actionable. A regression test covers that race.

Dorm used food item `50005` four times while establishing stable mutation
proof, then one `50001` item after natural resident consumption. Its latest
successful full command observed inventory beginning at `17781`, found the
remaining deficit below ALAS's feed threshold, performed the exact collect
input, and scheduled normally. Network reconnect prompts encountered during
the sequence were handled only through their reviewed exact confirmation.

The first full Gacha attempt exposed an ALAS resource-name distinction:
`GACHA_PREP` labels only the UR-point warning, while `GACHA_ORDER` labels the
final order. Treating both as generic confirmation caused the one permitted
Light order to be submitted inside `gacha_prep`; ALAS then waited for the
preparation controls and returned `GACHA_RESULT=False`. The order cost one cube
and 600 coins and produced an exact nonempty queue countdown. No second order
is admitted while that queue is nonempty.

## Verification

- Controller suite: `197 passed`.
- `python -m compileall -q python tests`: passed.
- `git diff --check`: passed.
- Canonical patch applied cleanly to a new detached worktree at upstream ALAS
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- All 17 patched ALAS Python modules compiled in the validation virtualenv.
- SHA-256 comparison confirmed every patched file in the clean worktree was
  identical to the live patchcheck source.
- Observer/driver revision remained
  `be80ce591a481c12d60c50d6040d40c035b40a2b`; package remained
  `com.bilibili.azurlane`.

## Remaining boundary

This gate does not enable unattended operation. Event and wishing-well pools,
multi-order construction, queue acceleration or collection, stage selection,
map movement, battle input, generic gestures, and Lua/game-state access remain
closed. Larger mutation budgets are parsing-compatible but not live-qualified.
