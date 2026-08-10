# G10 bounded campaign pre-sortie validation

Date: 2026-08-10

## Outcome

G10 passes the bounded pre-sortie scope on `emulator-5580`. The pinned ALAS
campaign command selected exact stage `12-4`, opened its exact map-preparation
layer, continued to the exact fleet-preparation layer, invoked ALAS's existing
`enter_map_cancel()` loop, and returned to the same chapter page. The final
command returned `ALAS_CAMPAIGN_BUDGET1_FINAL_ARTIFACT True`.

This is not a sortie or map-control pass. The fleet `start_button` is
deliberately absent from the native raycast allowlist and semantic input map.
Map movement, fleet formation changes, sortie confirmation, combat, and
post-battle handling remain closed.

## ALAS ownership and integration boundary

The integration retains ALAS's original `CampaignRun`, campaign UI navigation,
chapter selection, stage lookup, `CampaignBase.run()`, `enter_map()`, and
`enter_map_cancel()` loops. Typed semantic state replaces the relevant OCR,
template, oil-counter, page-presence, stage-entrance, and click endpoints.

The only campaign control-flow hook is a narrow pre-sortie safety checkpoint
inside the existing `enter_map()` loop. When the typed fleet-preparation layer
is proven, it calls ALAS's own `enter_map_cancel()`, requires an exact semantic
restoration proof, and raises `ScriptEnd` before ALAS can continue toward the
map. It does not implement an alternate campaign state machine.

The legacy `is_stage_page_has_entrance()` path calls
`campaign_extract_name_image()` directly rather than the normal campaign OCR
entrypoint. Semantic mode now supplies the same typed stage Buttons to that
path, closing the last pixel dependency without changing its caller.

## Typed observations and exact inputs

The chapter page requires the exact chapter title plus unique visible stage
codes and titles. Stage `12-4` resolves to the top-raycast-proven child Button:

```text
UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/levels/items/Chapter_1204/main
```

The two preparation layers require exact stage identity and titles:

- map preparation: `12–4`, `TF58，翱翔于天际`;
- fleet preparation: `舰队选择` with underlying stage `12-4`.

The reviewed preparation inputs are:

```text
OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/start_button
OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/btnBack
OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/btnBack
```

The fleet sortie control at
`LevelFleetSelectView(Clone)/panel/Fixed/start_button` is observation-only and
has no native top-raycast result or adapter click mapping.

## Budget and proof contract

`ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET` is a canonical non-negative integer
and defaults to `0`. A zero-budget command may navigate and inspect the exact
chapter/stage state but stops before the stage input. The live zero-budget
replay returned `True` without opening `12-4`.

A budget of `1` admits exactly one stage input. The map-preparation transition
is separately single-use, and the only permitted fleet-preparation input is
cancel. The successful full-command proof recorded generations:

```text
stage entry 2102 -> fleet cancel 2120 -> restored chapter 2132
```

The independent final read observed generation `2208`, chapter
`马里亚纳风云上`, stages `12-1` through `12-4`, no preparation layer, and
`IN_MAP=False`.

Transition tolerance is bounded. After the map proceed or fleet cancel input,
temporarily stale layer roots may coexist with removed child controls. Only a
previously proven transition receipt and its finite deadline can turn that
specific incomplete read into a passive `False`; outside that window the
original semantic error propagates.

The final cold-start replay also exposed a chapter-page settling window after
the exact campaign-menu input. That input is now receipt-cached, and only the
existing 20-second campaign transition deadline may report an incomplete
`CAMPAIGN_CHECK` as passive `False`; the same incomplete identity fails closed
after the deadline. The final zero-budget and one-budget commands both passed
after this regression was added.

## Live incidents and side effects

- The stage root was initially treated as the action target. Live native
  raycast evidence showed that the actionable target is its `main` child; the
  allowlist and oracle now require that exact path.
- Map and fleet transitions exposed stale-root windows. Both initially failed
  closed. The final bounded transition handling is regression-tested and the
  complete ALAS command passes without relaxing target identity.
- A test configuration auto-selected DroidCast and produced black screenshots.
  The final command forced ADB screenshots in process. Campaign decisions still
  came from typed state, and the direct stage-entrance bypass was replaced as
  described above.
- An earlier login during this development session automatically received a
  `1500`-coin login/daily reward before the campaign slice ran. No campaign
  gate authorized that receipt; it is recorded as an environmental side effect.
- ALAS test runs updated scheduler/emotion fields, and one benchmark updated
  screenshot selection, in external `semantic_e2e`/patchcheck configuration
  files. Those files are outside this repository and are not release inputs.

No sortie, map movement, battle, fleet-change, or campaign reward input was
injected by G10.

## Verification

- Controller suite: `209 passed`.
- The final observer APK is
  `artifacts/AngleLibraries-g10-pre-sortie.apk`, SHA-256
  `6bd736dadb3741599ce2d9d449c474356ebbbe7d7b4b21ffcf55ca3e37b9c2c9`.
- Driver revision:
  `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Package: `com.bilibili.azurlane`.
- The canonical ALAS patch applies cleanly to upstream
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- All 21 patched ALAS Python files compile, and their SHA-256 hashes match the
  live patchcheck sources after clean application.

## Remaining boundary

The next campaign gate should model fleet selection/formation and the sortie
confirmation as separate typed contracts, still default-closed and with a
rollback path. It must not inherit this pre-sortie pass. Map parsing, map
movement, combat entry, battle decisions, battle input, rewards, and repeated
unattended runs each remain independent later gates.
