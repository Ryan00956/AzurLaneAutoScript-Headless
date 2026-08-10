# G30 ALAS passive result-surface acquisition validation

## Outcome

G30 extends the G29 zero-input watcher to six passive alternate-result inputs:
`BATTLE_STATUS_A` through `BATTLE_STATUS_D`, plus `EXP_INFO_A` and
`EXP_INFO_B`. It does not change original ALAS branch order and it does not
promote any mapping without a real repeated result page.

The checked S-grade resource/action mappings are the structural reference.
Each alternate profile keeps a strict subset of the same exact page, control,
invariant Image, and Text paths while requiring its own `letter_A..D` /
`label_A..D` sprites. The S reference's `VICTORY` text is deliberately not
assumed for every lower grade.
The analyzer refuses to run if the qualified S reference mapping or its action
variant changes.

A candidate requires:

- at least three adjacent coherent raw observer samples;
- the full pinned page-selector identity in every sample;
- the exact original-ALAS action Button to be top-raycast actionable;
- no competing grade profile in the same generation;
- action geometry stable within two pixels;
- one package, fingerprint, driver revision, and PID;
- `input_injected=false` and `auto_promoted=false`.

Success emits only a G27-compatible review draft for one resource and its
same-named original-ALAS action target. Applying that draft remains a separate
explicit evidence-review step.

## Profile matrix

| profile | resource/action | required grade sprites | reference |
| --- | --- | --- | --- |
| `battle-status-a` | `BATTLE_STATUS_A` | `letter_A`, `label_A` | `BATTLE_STATUS_S` |
| `battle-status-b` | `BATTLE_STATUS_B` | `letter_B`, `label_B` | `BATTLE_STATUS_S` |
| `battle-status-c` | `BATTLE_STATUS_C` | `letter_C`, `label_C` | `BATTLE_STATUS_S` |
| `battle-status-d` | `BATTLE_STATUS_D` | `letter_D`, `label_D` | `BATTLE_STATUS_S` |
| `exp-info-a` | `EXP_INFO_A` | `letter_A`, `label_A` | `EXP_INFO_S` |
| `exp-info-b` | `EXP_INFO_B` | `letter_B`, `label_B` | `EXP_INFO_S` |

The sprite names are acquisition hypotheses derived from the qualified S page
structure and original ALAS grade assets. They are not called live evidence
until the exact objects occur in a raw trace.

## Real negative observation

The final bounded run completed normally on the open 12-4 map:

```powershell
python scripts/python/watch_alas_combat_rare_surface.py `
  --serial 127.0.0.1:5581 `
  --profile battle-status-a `
  --trace-output artifacts/g30-final-result-surfaces.trace.json `
  --evidence-output artifacts/g30-final-battle-status-a.evidence.json `
  --duration-seconds 3 `
  --interval-seconds 0.10 `
  --max-samples 30
```

The other five profiles were recomputed independently from the same frozen raw
trace with `scripts/python/analyze_alas_combat_rare_surface.py`.

Results:

- 11 complete samples, generations `107224..107246`;
- trace SHA-256
  `cb9cff85c5c868626e26dd37c52ff3ebff9655afb5f3aaf30a3a48f8d7b3a1fe`;
- PID `23161`, game activity still top-resumed;
- zero rejected endpoint triples, duplicates, or ambiguous generations;
- all six profiles: `evidence_complete=false`;
- input injected: false;
- auto promoted: false.

An earlier longer shell wrapper exceeded its outer time limit after writing a
partial diagnostic trace. It was not used for the result above; the fresh
bounded run and all six offline verifiers completed normally.

## Tests and coverage

Tests exercise all six positive profile fixtures, sibling-grade separation,
non-actionable controls, geometry drift, S-reference drift, deterministic
verification, tampering, and the checked-manifest audit. The G29/G30 focused
suite passes `12/12`.
The full Python suite passes `330/330`.

The coverage audit now reports the six profiles separately and all remain
false. No mapping count changes: canonical `16/41`, defensive `18/54`, actions
`12/38`, blockers `1/4`, and `production_ready=false`.

## Next step

Keep the watcher active around controlled battles and collect a naturally
occurring non-S result without trying to force a loss or weaken a fleet. Once
one grade and its following statistics page have three exact frames each,
review and promote those two mappings independently. Ambush, retirement, and
story branches remain higher-risk and stay blocked.
