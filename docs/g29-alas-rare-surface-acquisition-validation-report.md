# G29 ALAS rare-surface acquisition validation

## Outcome

G29 adds a zero-input watcher and deterministic evidence analyzer for the two
lowest-risk rare original-ALAS dialog pairs: guild confirm/cancel and mission
go/acknowledge. It closes the acquisition-tooling gap left by G28, but it does
not claim that either live mapping has been observed or qualified.

The watcher reads only `snapshot`, `buttons`, and `ui`, retains the existing
package/fingerprint/PID/coherence gates, and requires at least three adjacent
typed samples with both controls simultaneously actionable. Exact paths and
names must remain unchanged, and all four bounds coordinates may drift by no
more than two pixels. A missing, covered, duplicated, non-top-raycast, or
geometrically unstable control fails closed.

When those requirements pass, the analyzer emits a G27 review **draft** for the
two resource mappings and their two matching action targets. It never applies
that draft, edits the manifest, imports ALAS, or injects Android input. The
review remains an explicit separate promotion step.

## Profiles

| profile | acquisition identity | status |
| --- | --- | --- |
| `guild-popup` | Exact historical `GuildMsgBoxUI(Clone)/frame/cancel_btn` and `confirm_btn` hypotheses plus current top-raycast and ALAS template-region checks | not observed in a coherent repeated live trace |
| `mission-popup` | ALAS template regions discover a pair, then three frames must retain the same exact Unity paths and names | not observed in the current live trace |

The old guild endpoint is used only to narrow acquisition. It is still one
legacy endpoint, not promotion evidence. Mission geometry is also discovery
metadata only; any future review draft contains exact Unity selectors and must
pass the normal raw-trace promotion verifier.

## Real negative observation

The restored game remained top-resumed on PID `23161` at the open 12-4 map.
This read-only run used the same instance through `127.0.0.1:5581`:

```powershell
python scripts/python/watch_alas_combat_rare_surface.py `
  --serial 127.0.0.1:5581 `
  --profile guild-popup `
  --trace-output artifacts/g29-current-rare-surface.trace.json `
  --evidence-output artifacts/g29-current-guild-popup.evidence.json `
  --duration-seconds 8 `
  --interval-seconds 0.10 `
  --max-samples 90

python scripts/python/analyze_alas_combat_rare_surface.py `
  --trace artifacts/g29-current-rare-surface.trace.json `
  --profile mission-popup `
  --output artifacts/g29-current-mission-popup.evidence.json
```

Results:

- 25 complete samples, generations `101652..101756`;
- trace SHA-256
  `5b21f8a3529e65dfd038cce6d7e14313db1343e103dee83ae4ee12b56a8b8bc1`;
- zero rejected endpoint triples, duplicate generations, or ambiguous target
  generations;
- guild evidence complete: false;
- mission evidence complete: false;
- input injected: false;
- auto promoted: false;
- PID and foreground activity unchanged.

This is a useful negative qualification: ordinary map controls do not satisfy
either popup profile. It is not evidence for the absent dialogs.

## Tests and coverage

Focused tests cover exact guild matching, mission pair discovery, the
three-frame threshold, non-actionable controls, region ambiguity, deterministic
verification, and record/hash tampering. The coverage audit now reports both
rare profiles independently; both remain false with the checked manifest.
The focused suite passes `6/6` and the full Python suite passes `324/324`.

No coverage count changes in G29: canonical `16/41`, defensive `18/54`,
actions `12/38`, blockers `1/4`, branch/blocker reviews incomplete, and
`production_ready=false`.

## Next step

Run the watcher while a real reversible guild or mission dialog is naturally
present. Review its two exact paths and surrounding context, then feed only the
frozen three-frame draft through the existing mapping promoter and receipt
verifier. Passive alternate result screens can be collected in parallel, but
ambush, retirement, and story branches remain behind their explicit blockers.
