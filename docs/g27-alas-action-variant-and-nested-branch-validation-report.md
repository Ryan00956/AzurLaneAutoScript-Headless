# G27 ALAS action-variant and nested-branch validation

## Outcome

G27 keeps original ALAS as the combat state-machine owner and changes only the
semantic input boundary. One original ALAS action target may now have multiple
evidence-bound Unity realizations, selected only when exactly one variant is
fully visible. The first real example is `MAP_PREPARATION_CANCEL`: the stage
information page and fleet-selection page have different `btnBack` objects.

The checked-in manifest remains fail-closed. Current coverage is canonical
`16/41`, defensive `18/54`, actions `12/38`, and blockers `1/4`. Fleet stats
remain qualified, but branch and blocker review are incomplete, so
`production_ready=false` and the production runner still stops at G18.

## Boundary preserved

- No ALAS handler or branch order was replaced.
- Reviews still bind exact selectors to repeated raw frames and emit
  independently verifiable receipts.
- Every non-empty action variant has exactly one top-raycast control; auxiliary
  selectors may distinguish two screens that expose the same ALAS target.
- Resolution requires exactly one visible variant. Zero or overlapping
  variants close the action gate.
- A live commit records the selected `action_variant_id` and rechecks the same
  variant on both stable pre-input generations.
- The G18 grid-input lease, production stop, and combat budgets are unchanged.

## Defensive surface and nested branches

The source audit found two previously omitted true-branch queries:
`EXERCISE_CHECK` in combat mis-click recovery and `STORY_LETTERS_ONLY` in the
story handler. The exact defensive surface is therefore 54 query names and 38
possible action targets.

The manifest now carries explicit unqualified blocker placeholders for the
ambush, retirement, and story-option branches. Their root queries are pinned
separately:

| branch | original-ALAS roots |
| --- | --- |
| ambush | `MAP_AMBUSH_EVADE` |
| retirement | `RETIRE_APPEAR_1`, `IN_RETIREMENT_CHECK` |
| story | `STORY_SKIP_3`, `STORY_LETTERS_ONLY`, `STORY_CLOSE` |

The replay configuration gate also pins ambush evasion, main-campaign event
mode, emergency repair off, one-click retirement, story skipping on, and story
option zero. These pins constrain qualification; they do not claim the nested
branches are mapped.

## Evidence promotions

The read-only trace
`artifacts/g24-fresh-unlocked-preparation-sortie-gate-failed.trace.json`
has SHA-256
`81b2534068d2da24ed67588e8426ddaf7f17fa23c7190a25fb3ef20360040fb2`.
It promoted:

| generations | resource | action variants |
| --- | --- | --- |
| `16207,16217,16227` | `CAMPAIGN_CHECK` | none |
| `16373,16384,16394` | `MAP_PREPARATION` | `MAP_PREPARATION#map-preparation`, `MAP_PREPARATION_CANCEL#map-preparation` |
| `16412,16422,16431` | `FLEET_PREPARATION` | `FLEET_PREPARATION#fleet-preparation`, `MAP_PREPARATION_CANCEL#fleet-preparation` |

The earlier automation-confirm trace
`artifacts/g24-fresh-unlocked-preparation.trace.json` has SHA-256
`6eb9043ed54138571cdc19522eab5ae29a5e9b259ba9db2f74e9ef138e56e4e9`.
Generations `7608,7613,7618` promoted
`BATTLE_PREPARATION_WITH_OVERLAY` from the inactive-under-modal battle start
button plus exact information-dialog anchors. No background action was
promoted or clicked.

All four G27 receipts reverify against the final manifest. The canonical
manifest digest reported by the verifier is
`63e9d04e0938bd5d9c099b0739e9c55e88bf3be31f27890865fe416477d03ff2`.

## Current-game preservation

Before promotion, an eight-sample read-only baseline captured generations
`57117..57142` on PID `23161`. Its SHA-256 is
`3b1f81bcf16528916b746c63064311b0b443ca8cdafeb6c981a80ffa67045196`.
The 12-4 map remained open; G27 injected no input and did not retreat or start a
new battle.

## Verification

- Focused observer/map tests: `69/69` passed.
- Full Python suite: `313/313` passed.
- Maximum original-ALAS replay: passed ten phases, 135 calls over the unchanged
  41 canonical query names, with source restoration and `input_injected=false`.
- Coverage audit: contract valid; canonical `16/41`, defensive `18/54`, actions
  `12/38`, blockers `1/4`, fleet stats qualified, production closed.
- Action-variant tests prove append-and-receipt verification, exclusive
  resolution on two pages, and fail-closed behavior when variants overlap.

## Remaining gaps

Alternative result grades, guild and mission popups, ambush, retirement,
story-option/close flows, and the remaining defensive actions still lack
repeated exact evidence. The three nested-branch blockers are placeholders,
not qualifications. G27 therefore improves the input adapter without claiming
large-scale unattended combat or moving the production boundary.
