# G31 ALAS combat-surface multiplex validation

## Outcome

G31 removes the need to predict which rare surface will appear. One
`--profile all` watcher now captures a single raw trace and evaluates all eight
G29/G30 profiles in fixed order:

1. guild popup;
2. mission popup;
3. battle grades A, B, C, and D;
4. experience grades A and B.

The raw endpoint capture remains continuous and input-free. A cheap current-
frame prefilter controls only when the full eight-profile trace analysis runs;
it never suppresses raw samples. The watcher always recomputes the aggregate
record against the final frozen trace before verification.

## Aggregate contract

The G31 evidence record binds the trace SHA-256, package, driver revision, game
fingerprint, PID, thresholds, and the deterministic result hash of every child
profile. Its dispatch rules are fail-closed:

| child matches | aggregate result |
| --- | --- |
| zero | candidate/evidence incomplete; no draft |
| exactly one | candidate and evidence complete; export exactly that one review draft |
| two or more | candidate complete but evidence incomplete; mark ambiguous and export no draft |

Every outcome retains `input_injected=false`, `auto_promoted=false`, and
`review_required=true`. The aggregate verifier reruns all eight child analyzers
and rejects profile order, child hash, selected generation, draft, ambiguity,
or trace identity drift.

## Low-cost prefilter

Full analysis is requested only when the current typed frame contains at least
one of these hypotheses:

- exact actionable guild cancel and confirm paths;
- two actionable mission-region controls;
- an active non-S `letter_A..D` or `label_A..D` result sprite.

A false prefilter result skips analysis for that iteration, not capture. This
keeps a long map wait from repeatedly reparsing the growing raw trace while
still preserving any frame for final offline verification.

## Real multiplex negative observation

The final run used one command and no predicted surface:

```powershell
python scripts/python/watch_alas_combat_rare_surface.py `
  --serial 127.0.0.1:5581 `
  --profile all `
  --trace-output artifacts/g31-final-all-surfaces.trace.json `
  --evidence-output artifacts/g31-final-all-surfaces.evidence.json `
  --duration-seconds 2 `
  --interval-seconds 0.10 `
  --max-samples 24

python scripts/python/analyze_alas_combat_rare_surface.py `
  --trace artifacts/g31-final-all-surfaces.trace.json `
  --profile all `
  --output artifacts/g31-final-all-surfaces.evidence.json `
  --verify
```

Results:

- 10 complete samples, generations `113131..113155`;
- trace SHA-256
  `f5def46ae1a12a39110f88ad419fddd90b4f5d63ace3b8cf74bea7b0258b16c7`;
- profile count: 8;
- matched profiles: none;
- zero rejected endpoint triples, duplicates, or ambiguous generations;
- candidate/evidence complete: false;
- ambiguous match: false;
- input injected and auto promoted: false;
- game PID remained `23161`.

This is a real negative map observation, not evidence for any absent surface.

## Tests and coverage

G31 tests pin the exact eight-profile order, result and mission prefilters,
zero/one/multiple-match dispatch, no-draft ambiguity behavior, deterministic
verification, and tamper rejection. The combined G29-G31 focused suite passes
`18/18`.
The full Python suite passes `336/336`.

The coverage audit reports the multiplex profile count and readiness while all
eight mappings remain false. Mapping totals do not change: canonical `16/41`,
defensive `18/54`, actions `12/38`, blockers `1/4`, and
`production_ready=false`.

## Next step

Use `--profile all` around a controlled ordinary battle or a naturally
appearing dialog. If exactly one profile matches, preserve the generated draft
and independently promote/verify that one frozen episode. The watcher itself
must remain non-applying; ambush, retirement, and story inputs remain behind
their existing blockers.
