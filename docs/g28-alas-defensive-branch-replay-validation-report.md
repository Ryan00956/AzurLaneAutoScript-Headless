# G28 ALAS defensive-branch replay validation

## Outcome

G28 proves that 16 rare combat paths still execute through original ALAS
methods when their screenshot/OCR inputs are replaced by typed virtual
observations. The replay is Device-free: it records queries, clicks, sleeps,
return values, and short-circuit order on isolated campaign copies, restores
the source object, and injects no Android input.

This is a state-machine ownership pass, not a live Unity mapping pass. No G28
scenario promotes a manifest selector or closes a blocker. Coverage therefore
remains canonical `16/41`, defensive `18/54`, actions `12/38`, and blockers
`1/4`; `branch_review_complete=false`, `blocker_review_complete=false`, and
`production_ready=false` remain unchanged.

## Why replay came before promotion

The existing raw trace corpus was audited before implementation:

- all complete battle-result evidence contains S-grade anchors; no exact
  `letter_A..D` or `label_A..D` records were found;
- the guild dialog exists only in one old endpoint observation, not three
  complete repeated frames;
- no complete raw trace contains mission-popup, ambush, retirement, or story
  roots suitable for evidence promotion.

Promoting any of those inputs would therefore overstate the evidence. G28
keeps them unqualified and instead pins the exact source-controlled behavior
that future Unity observations must drive.

## Replayed original-ALAS scenarios

| group | scenarios | original behavior proved |
| --- | --- | --- |
| result grades | A, B, C, D | `handle_battle_status()` queries S then lower grades in order, sleeps, and clicks the matched grade |
| experience grades | A, B | `handle_exp_info()` queries S/A/B in order and clicks the matched page |
| guild popup | confirm, cancel | both buttons must be visible; ALAS chooses the contextual target |
| mission popup | go, acknowledge | both buttons must be visible; ALAS chooses the contextual target |
| retirement | entry, page dispatch | entry click returns for a later loop; retirement-page detection dispatches the existing retire handler |
| story | letters-only, skip, close | black-story letters, normal skip, and close retain their original short-circuit order |
| ambush | evade success | the evade button is waited for, clicked once, and the original info-bar success branch completes |

The two `False` return values are intentional source behavior, not failures:
`handle_retirement()` returns `False` after entering retirement so the caller
can observe the next page, and the fallback-button path in `handle_ambush()`
finishes its work before falling through to `False`.

## Source binding

The checked replay record is
`integration/alas/combat-defensive-branch-replay-g28.json`. It binds ALAS commit
`81ccf63b4540f00241628c82a58c02c7a2bb11af` and these exact source hashes:

| source | SHA-256 |
| --- | --- |
| `module/combat/combat.py` | `b9dca471e8454dd95d802e0e63d76e26f90e7d3e3196ed1bc6997e0523898bfa` |
| `module/handler/info_handler.py` | `455e3a20776eaa8176e7320c3d6b0b161d5eda96bbcfd789ba1acf2125c07241` |
| `module/handler/ambush.py` | `c6ead02b8c3e54a82ff45f350fe3ab7116a41418bd4fdc7645cd33397123c6c5` |
| `module/retire/retirement.py` | `c205ec99c80da3855a6c2756ade1e8a883f77c372a5b9d81952b1fc8beb63471` |

The verifier checks the record schema, all 16 exact scenario outputs, source
method owners, commit, and current file hashes. It also reports
`live_mapping_promoted=false` so this pass cannot be mistaken for observer
coverage.

## Commands and results

```powershell
H:\program\AzurLaneAutoScript-semantic-e2e\.venv\Scripts\python.exe `
  scripts/python/qualify_alas_combat_defensive_branches.py `
  --alas-root H:\program\AzurLaneAutoScript-patchcheck `
  --output integration/alas/combat-defensive-branch-replay-g28.json

python scripts/python/verify_alas_combat_defensive_branch_replay.py `
  --alas-root H:\program\AzurLaneAutoScript-patchcheck
```

Results:

- defensive branch replay: `16/16`, passed;
- source files and commit: matched;
- source campaign object: restored;
- Android input: none;
- full Python suite: `318/318`, passed;
- maximum original ordinary-combat replay: ten phases, 135 resource queries
  over the unchanged 41 canonical names, passed;
- observer coverage audit: branch replay passed but live mapping promoted
  false, production closed.

The live game remained top-resumed on PID `23161`. A final read-only trace at
generations `92061..92063` retained the same map UI, one enemy, fleet-lock and
retreat controls, with no rejected endpoint triples or duplicate generations.
Its SHA-256 is
`5a5d2af43e3d09c5c8a16d80fe4c714847d28992708b9c16112ac854e84f7659`.
G28 did not click, retreat, start a battle, or alter the open 12-4 map.

## Remaining work

G29 should acquire repeated complete Unity traces for the replayed scenarios,
starting with reversible guild/mission cancel-or-ack paths and passive result
screens. Ambush, retirement internals, and story options remain higher-risk
and must stay behind their explicit blockers until their full nested inputs and
exit conditions are observed.
