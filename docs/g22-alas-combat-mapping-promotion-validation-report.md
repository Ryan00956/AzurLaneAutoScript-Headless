# G22 ALAS combat mapping promotion validation

Date: 2026-08-10

## Result

The first real raw-trace evidence has been promoted into the ALAS combat
observer input manifest without changing ALAS's state machine. The exact
`IN_MAP` mapping is now qualified, moving resource coverage from `0/38` to
`1/38`. The recurrent `[NetworkDown]` surface is recorded as one exact named
blocker rule.

This is a **partial observer-input pass, not a battle or combat-input pass**.
Blocker review remains explicitly incomplete, fleet HP/level mappings remain
empty, and 37 resource queries remain unmapped. The audit therefore continues
to report `production_ready=false`; D6 input and the campaign-combat lease stay
closed at G18.

## Evidence source

The ignored local G21 raw trace
`artifacts/g21-current-blocked-trace.json` has SHA-256:

`82ed1d7c76142c3113283d6eec327970eced816aeb2e4b15f4911c38764436f5`

All three input-free samples were used:

| Generation | Frame SHA-256 |
| --- | --- |
| `137332` | `d72396de0e99d987a4fcb94e1bd1c7a8c911bccc1b2f972a714c6d3d61f8d288` |
| `137335` | `71b8a411850d2a168db5654abd22baa66dd8b645c3debc9092c2928c394ffaab` |
| `137337` | `34bd41a45a01c1a3ff0ad1bdc526a5b36d568237733858c138edf6eac7f9870d` |

The G21 parser revalidated the complete raw snapshot/Button/UI triples before
review. Package, driver revision, game fingerprint, PID, endpoint schemas,
generation coherence, truncation flags, extraction errors, and frame hashes
all remain part of the gate. The trace top-level contract still requires
`input_injected=false` and rejects phase labels or derived maps.

## Qualified `IN_MAP` mapping

The reviewed resource requires all three exact active Image identities in
every selected frame:

1. `LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat/retreat`,
   name `retreat`, sprite `reteat_popo`;
2. `LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/display/mask/sea`,
   name `sea`, sprite `sea_day`;
3. `LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)/top_stage/back_button/mask/Image`,
   name `Image`, sprite `back_btn`.

Their evidence digest is
`bb889cce779285bd23d7e8a226c931a5583d83ac4083dd3d95a5a621eb6615d3`.
It binds the mapping type/name, exact selectors, source trace hash, and all
three generation/frame hashes. A sprite, name, path, activity, completeness,
or source-frame change prevents the review from reproducing.

No generic LevelGrid prefix, suffix match, coordinate, OCR value, or trusted
phase token is used.

## Partial blocker evidence

The former flat blocker-selector list was unsafe for compound identities: one
generic Button could satisfy an OR-style check. G22 replaces it with named
all-of mappings. The reviewed `network_down` rule requires all of:

- the exact cancel Button path/name and actionable top EventSystem raycast;
- its exact `取 消` Text child;
- the exact message Text `服务器连接失败，是否重新连接？\n[NetworkDown]`.

Its evidence digest is
`e3c5369e2c97e0b28df7af4ea86a166354207a81466864a0204a63f95dfc67b6`.
Removing any member leaves that blocker inactive; the generic cancel Button
alone is not enough.

One known blocker is not the complete blocker surface. The manifest therefore
stores `blocker_review_complete=false`. Coverage reports one qualified blocker
rule but `blockers_qualified=false`, preventing partial evidence from being
misreported as production readiness.

## Review and receipt pipeline

`scripts/python/promote_alas_combat_mapping_review.py` consumes a strict review
document plus a raw trace. It:

1. verifies the whole trace-file SHA-256 and pinned runtime identity;
2. selects at least two exact increasing generations;
3. parses every full selector through the production matcher;
4. requires every selector to be active in every chosen frame;
5. refuses to replace a different already-qualified mapping;
6. computes evidence hashes and emits a candidate manifest plus receipt;
7. remains idempotent when the exact reviewed mapping is already present.

The committed review and receipt are under
`integration/alas/combat-observer-reviews/`. The receipt binds the original
zero-coverage manifest hash, promoted manifest hash, source frames, selectors,
evidence digests, before/after coverage, and `input_injected=false`.

`scripts/python/verify_alas_combat_mapping_receipt.py` independently reparses
the raw trace, re-runs the same selector presence checks, recomputes both
evidence digests, and requires the receipt's after-manifest hash and coverage
to match the checked-in manifest.

Example:

```powershell
python scripts/python/verify_alas_combat_mapping_receipt.py `
  --trace artifacts/g21-current-blocked-trace.json `
  --receipt integration/alas/combat-observer-reviews/g22-in-map-network-down.receipt.json
```

## Verification

- Mapping receipt verification passes for three source frames, one resource,
  and one blocker; manifest SHA-256 is
  `8f93a9ab9ce1fb4f53c75b1ba75a156ae8f649586c4543ca3294fbf17774bb0a`.
- Coverage audit reports exact `1/38`, one qualified partial blocker,
  incomplete blocker review, unqualified fleet stats, and
  `production_ready=false`.
- Focused tests cover compound blocker all-of behavior, evidence promotion,
  missing/drifted selector refusal, receipt re-verification, and tampered frame
  refusal.
- The full controller/integration suite passes `281/281`.
- Python compilation and `git diff --check` pass.
- The canonical ALAS integration patch is unchanged. No ALAS state-machine
  code, D6 input, Android input, or combat budget was enabled.

## Next boundary

The next evidence must come from a stable, controlled ordinary S-rank battle.
Capture enough complete generations around preparation, execution, result,
experience, enemy-searching, and stable-map transitions. Promote mappings one
resource at a time only when exact positive and negative frames support their
actual ALAS meaning; do not infer generic popup resources from this one
NetworkDown instance. Fleet HP/levels and the complete blocker review remain
separate hard gates before G20 can drive G19.
