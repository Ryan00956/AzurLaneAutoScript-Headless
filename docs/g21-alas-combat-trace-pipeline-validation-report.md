# G21 ALAS combat trace pipeline validation

Date: 2026-08-10

## Result

The evidence-acquisition pipeline needed to populate G20 is implemented. A
package-verified recorder can persist coherent raw `/v1/snapshot`,
`/v1/buttons`, and `/v1/ui` triples without input; reviewers can then select
six exact generations, inspect phase-local Unity path/sprite/text candidates,
and compile a phase-label-free G20 fixture with offline-derived campaign-map
projections.

This is an **acquisition-pipeline pass, not a real battle-trace pass**. The
current server connection recovered only briefly after one already reviewed
network-reconnect confirmation and then returned to the exact `[NetworkDown]`
dialog. No D6 or combat input was injected. The durable production manifest
therefore remains `0/38` and cannot drive G19.

## Versioned manifest

`integration/alas/combat-observer-manifest.json` is now the single durable
mapping source. Its strict schema pins:

- package, observer driver revision, and the complete game fingerprint token;
- exactly the 38 G19 ALAS resource names;
- full Unity record kind/path/name plus sprite or fixed text;
- top-raycast requirements for action Buttons;
- one evidence SHA-256 per resource mapping;
- reviewed blocker selectors and evidence hash;
- six HP Image and six dynamic level Text selectors plus evidence hash.

Unknown fields, missing resources, duplicate selectors, malformed hashes, or
selector type/value drift close the loader. The coverage audit now reads this
file instead of constructing an in-memory placeholder. The committed file is
intentionally empty of selectors and reports `production_ready=false`.

## Read-only trace recorder

`scripts/python/capture_alas_combat_observer_trace.py` performs the independent
pinned package fingerprint gate before its capture clock starts. It then:

1. proves the expected activity remains top-resumed;
2. reads the three raw observer endpoints;
3. reuses the G20 parser to validate schemas, package/driver/PID, main-thread
   state, completeness, truncation, extraction errors, and generation
   coherence;
4. hashes the exact triple with `campaign_map=null`;
5. keeps only strictly increasing generations;
6. atomically rewrites a trace whose top-level `input_injected` is always
   false.

The trace schema rejects phase fields, map projections, PID changes, repeated
or decreasing generations, tampered frame hashes, and any input claim. Startup
package-hash time is outside the requested recording duration. Rejected
endpoint triples are counted by reason instead of being silently discarded.

Example:

```powershell
python scripts/python/capture_alas_combat_observer_trace.py `
  --serial 127.0.0.1:5581 `
  --output artifacts/g21-combat-trace.json `
  --duration-seconds 90 `
  --interval-seconds 0.20 `
  --max-samples 480
```

## Selection, candidates, and fixture compilation

`scripts/python/compile_alas_combat_observer_fixture.py` accepts exactly six
strictly increasing generations from one trace. The trace still contains no
phase token; the selected positions are paired with G19's pinned order only in
the review report and compiled replay contract.

For every selected generation, the candidate report records:

- all active exact Button/Image/Text identities;
- records unique to that one position;
- every actionable Button and its full path;
- exact records common to the two map positions;
- generation and source-frame SHA-256.

The analyzer never writes mappings into the manifest. A reviewer must assign
each ALAS resource and evidence hash explicitly.

For selected positions five and six, the compiler reconstructs the 12-4 map
from frozen raw records by running the existing G13 typed map parser offline
against pinned ALAS topology. It serializes all cells/land, fleets/ammunition,
enemies, pickups, displayed/current fleet identity, and roster. The resulting
frame is rehashed and reparsed as a G20 fixture. Any overlay, incomplete map,
unknown attachment, or topology drift prevents compilation.

Example:

```powershell
python scripts/python/compile_alas_combat_observer_fixture.py `
  --trace artifacts/g21-combat-trace.json `
  --generations 1001,1002,1003,1004,1005,1006 `
  --alas-root H:\program\AzurLaneAutoScript-patchcheck `
  --output artifacts/g21-combat-fixture.json
```

The compiler writes a separate candidate report before attempting the final
map compilation, so map failure does not discard useful reviewed deltas.

## Current live result

The installed package fingerprint was verified before one exact semantic
`overlay/network-reconnect/confirm` input. It used the reviewed top-raycast
Button path
`OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)`
at generation `130033`. The prompt was absent at generations
`130098..130099`, but later reappeared.

The underlying typed hierarchy still exposed the 12-4 `LevelGrid`, both fleet
ammunition texts at `5/5`, enemy `1204090` with `行动中` on D6, and enemy
`1204050` on C6. Because the renewed Msgbox covered the surface, the complete
map parser correctly returned `campaign map-scene identity is absent`; these
underlying records are not promoted to a fresh map pass.

The corrected recorder then captured three complete read-only samples at
generations `137332..137337`, PID `19277`, with zero rejected triples and zero
duplicates. The ignored local artifact is
`artifacts/g21-current-blocked-trace.json`. It contains the blocker scenario,
not combat evidence, and injected no input during recording.

## Verification

- Controller and integration suite: `279/279` passed.
- Twelve focused combat-observer tests pass, including strict versioned
  manifest loading, raw trace round-trip, generation selection, candidate
  analysis, read-only/phase-token refusal, and derived-map-only fixture
  compilation.
- Coverage audit: valid exact 38-resource surface, `0/38` qualified,
  blockers/stats unqualified, `production_ready=false`.
- New and changed Python sources compile; `git diff --check` passes.
- The canonical ALAS integration patch remains unchanged. ALAS state-machine
  logic and the G18 production stop remain unchanged.

## Next boundary

When the connection remains stable, run the recorder across one controlled
ordinary S-rank battle and retain enough generations around every transition.
Review and select six frames, compile the frozen fixture, then populate the
manifest one mapping at a time. Only a `38/38` audit plus successful G20/G19
offline replay may authorize a separately reviewed progressive live action.
D6 remains closed now.
