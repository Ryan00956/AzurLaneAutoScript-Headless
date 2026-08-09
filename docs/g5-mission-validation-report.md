# G5 mission semantic validation

## Outcome

G5a and controlled G5b passed on the pinned Chinese Azur Lane 9.7.10 x86_64
build. The semantic ALAS mission flow first proved a no-claim page without
claim input. After the account exposed rewards, it performed one exact
`GetAllButton` claim, closed the exact `AwardInfoUI` popup, proved three claim
rows became zero while five unfinished rows remained, and returned to main.

Automatic claim input remains disabled by default. It requires a second
explicit environment opt-in and is bounded to one claim-all input per
`reward_mission()` invocation. Numeric-row claiming and task-tab traversal are
still fail-closed.

Primary evidence:

```text
evidence/g4-game-init-20260809T013349Z-emulator-5580/manifest.json
evidence/g4-game-init-20260809T013349Z-emulator-5580/mission-claimable-before.json
evidence/g4-game-init-20260809T013349Z-emulator-5580/mission-claim-once.json
evidence/g4-game-init-20260809T013349Z-emulator-5580/mission-after-claim.json
evidence/g4-game-init-20260809T013349Z-emulator-5580/oracle-after-claim.json
```

## Pinned runtime

| Item | Value |
| --- | --- |
| Package | `com.bilibili.azurlane` |
| Version | `9.7.10` / code `9710` |
| ABI | native x86_64 |
| Base APK SHA-256 | `e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f` |
| `libil2cpp.so` SHA-256 | `e3f1cfc442b67f1d4c9877fd9ceaedc3d68f2842ad677445241b9cc9c05d1c67` |
| Observer ANGLE SHA-256 | `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7` |
| ANGLE revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| Test guest | `alas_game_api32_x64`, ADB `emulator-5580` |
| Upstream ALAS target | `81ccf63b4540f00241628c82a58c02c7a2bb11af` |

The runner and Python `PinnedPackageGate` independently enforce the installed
package fingerprint before semantic input.

## Exact task and reward contracts

Installed game AssetBundles were copied read-only and inspected to establish
the prefab hierarchy. Task assets are under
`evidence/g4-game-init-20260809T002941Z-emulator-5580/task-assets`:

| Bundle | SHA-256 |
| --- | --- |
| `tasklistpage` | `036fdb39a9199985cc82f4c5215d97e3e50b85da2e6f43d2a2a014ba2e938faa` |
| `taskscene` | `9ac9a7b0c36bda5f863ace66f60020504cd26038c87bd2da3a3d2431d2feda13` |
| `tasktpl` | `d6faeaaf8752fc2cb466863278870af322924eeb6bf8a5132ff8154a58a91505` |

Reward assets are under the primary evidence bundle's `claim-assets` folder:

| Bundle | SHA-256 |
| --- | --- |
| `awardinfoui` | `ce6d52be8fd94e0556329b3cb15fb82d93f7a297b7a2db5e4d38e7eb4cead731` |
| `awardinfoui1` | `8f41bd4b6a252cacc88d2ec0a598eca68d6087aaf4057f85cf09ea61121173a8` |

The native observer's reviewed top-raycast allowlist contains these task and
reward shapes:

```text
TaskScene(Clone)/blur_panel/adapt/top/back_btn
TaskScene(Clone)/blur_panel/adapt/top/GetAllButton
TaskScene(Clone)/pages/TaskListPage(Clone)/right_panel/content/<row>/frame/get_btn
TaskScene(Clone)/pages/TaskListPage(Clone)/right_panel/content/<row>/frame/go_btn
AwardInfoUI(Clone)/items/close
AwardInfoUI1(Clone)/items/close
```

The observer computes raycast identity for the bounded task-row shape, but does
not make it actionable by itself. The controller requires `<row>` to be an
exact decimal index and rejects duplicates. It classifies claim-all,
row-claimable, unfinished, or unknown, but never infers an empty page merely
from missing Buttons. A non-unknown signature must remain identical across at
least two increasing snapshot generations before any result is accepted.

`AwardInfoUI` and `AwardInfoUI1` are explicit blockers. Only their own exact
close target is allowed while present. The live run exercised `AwardInfoUI`;
the `AwardInfoUI1` hierarchy was established from the installed asset but was
not live-triggered.

## G5a no-claim loop

The original no-claim run entered the exact main task Button, proved five
unfinished `go_btn` rows, returned through the exact task back Button, and
injected zero claim inputs. It established that missing claim controls are not
treated as a safe click or an inferred empty page.

After G5b, an independent repeat in `mission-after-claim.json` again returned
`nothing-claimable`: generation 118, five unfinished rows, zero claim rows, no
`GetAllButton`, two navigation inputs, and zero claim inputs.

## G5b controlled claim-all loop

The final-driver preflight returned safely to main with no claim input and
recorded:

| Measure | Result |
| --- | ---: |
| Stable page generation | 54 |
| Unique `GetAllButton` | present, actionable, top raycast |
| Numeric `get_btn` rows | 3 |
| Numeric `go_btn` rows | 1 visible/actionable row |
| Claim inputs | 0 |

The controlled run then performed this bounded sequence without screenshots:

```text
exact main/task
  -> stable claimable-all state
  -> exact GetAllButton
  -> exact AwardInfoUI(Clone)/items/close
  -> stable unfinished state with zero claim rows
  -> exact TaskScene back_btn
  -> exact main/task returns
```

`mission-claim-once.json` recorded:

| Measure | Result |
| --- | ---: |
| Outcome | `claimed-all-once` |
| Pre/post generations | 87 / 90 |
| Claim rows before/after | 3 / 0 |
| Unfinished rows after | 5 |
| Claim inputs | 1 |
| Total semantic inputs | 4 |
| Unreviewed or overlay-dismiss inputs | 0 |

Each action receipt is emitted only after exact package, foreground, freshness,
generation, unique path, active/interactable state, bounds, blocker, and top
EventSystem raycast checks pass. A post-run no-input oracle snapshot passed at
generation 120 with no blockers, 42 typed Buttons, and all eight reviewed
main-page targets actionable.

## ALAS integration boundary

The commit-pinned patch adds an opt-in early hook to
`Reward.reward_mission()`. In semantic mode it calls
`AlasSemanticSession.run_mission_reward()` before the original pixel loop. The
default ALAS path is unchanged when semantic mode is off.

Semantic mission mode is still no-claim by default. A claimable page first
returns safely to main and raises `MissionClaimableDetected`. The separately
validated claim-all path requires:

```text
ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE=1
```

With that opt-in, one invocation may inject one `GetAllButton` claim, close one
reviewed reward popup, prove the stable post-claim state, and return. The hook
does not map generic `BACK_ARROW`, use image coordinates, or expose raw swipe,
drag, long-click, or low-level click fallback.

## Regression and integrity checks

The same final observer APK also passed:

- G4 login/main plus 40-second sustained health in the primary evidence bundle:
  40/40 structurally valid samples, 36 fresh samples, generations 2 through 28,
  and 27 distinct generations.
- G3 observer contract in
  `evidence/g3-observer-20260809T013932Z-emulator-5570`.
- G2 Unity contract in
  `evidence/g2-null-20260809T014015Z-emulator-5570` with a 47.117-second run,
  three scene transitions, eight completed AsyncGPUReadbacks, and zero errors.

Evidence SHA-256 values:

| File | SHA-256 |
| --- | --- |
| G4/G5 manifest | `08e1a9da73fb065960b5523851d46f1894c94e5009175ff80b4bc9050abd3dd2` |
| `mission-claimable-before.json` | `25536b9f4896a19c3df9cfa717a950fb4021c838ba2b57a166a1f1b2054dfad3` |
| `mission-claim-once.json` | `ac475427b3394d3aeb4891b65378ebeeae0d80e910bd88c158a34c623ef621c9` |
| `mission-after-claim.json` | `79b252dafc6960a907598dd11f112310215202a54a3758d9e93af0d6a4b1e7bb` |
| `oracle-after-claim.json` | `7e88cda2cf2fb56662bdc055fafe9539369291dcaae56ee1b75880933f14b467` |
| G3 manifest | `94be2b9f8f5d5266a52d7f6e7e8265261b1562278f3dd6eedf36a8268eafcfc1` |
| G2 manifest | `16baf23ffc70e5ea96db642b1452b0f9d007dd5c78633a14c2f6aaebfe491c76` |

The Python controller suite passes 37 tests. The staged ALAS patch applies
cleanly to the pinned upstream checkout. The upstream audit checkout remains
unchanged.

## Remaining scope

G5b proves one default-page `GetAllButton` closure, not complete ALAS reward
coverage. Numeric-row-only claiming, daily/weekly tab identity and traversal,
other popup variants, repeated scheduler invocation, and a long unattended
soak remain separate gates. Every unmapped case continues to fail closed.

## Subsequent ownership refactor

After this evidence bundle was frozen, the integration boundary was changed so
the production-intended hook no longer replaces `Reward.reward_mission()` with
the probe state machine. ALAS again owns its original reward loop; typed
semantic observations feed `appear()`, `match_template_color()`, and
`image_color_count()`, and semantic clicks feed its normal action calls. The
probe methods and this report remain the regression oracle for the proven
primitive closure.

That refactor has unit, syntax, pinned-patch application, and extracted
`Reward.reward_mission()` lifecycle checks. It has not yet repeated this live
claim, so this historical G5 pass must not be cited as live validation of the
new ALAS-owned wiring.
