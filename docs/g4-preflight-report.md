# G4 real-game semantic validation

## Outcome

The formal G4 closed loop passed on the pinned Chinese Azur Lane 9.7.10
x86_64 build. Under package-routed ANGLE NULL, the game advanced from its Unity
login root to the main UI, exported bounded typed Button state with accurate
screen/ADB bounds and top EventSystem raycast identity, and completed a harmless
settings-page round trip without pixel evidence.

This is not a claim that ALAS can run normal tasks headlessly. EventSystem
top-raycast identity, Lua/game-state semantics, campaign maps, battle state,
popups, scrolling, dragging, and most task buttons remain unmapped. Those paths
fail closed.

Formal evidence:

```text
evidence/g4-game-init-20260808T160921Z-emulator-5580
evidence/g4-game-init-20260808T172750Z-emulator-5580
evidence/g4-game-init-20260808T172941Z-emulator-5580
evidence/g3-observer-20260808T172655Z-emulator-5570
```

## Pinned package and runtime

| Item | Value |
| --- | --- |
| Package | `com.bilibili.azurlane` |
| Version | `9.7.10` / code `9710` |
| Entry Activity | `com.manjuu.azurlane.MainActivity` |
| ABI | native x86_64 |
| Base APK SHA-256 | `e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f` |
| `libil2cpp.so` SHA-256 | `e3f1cfc442b67f1d4c9877fd9ceaedc3d68f2842ad677445241b9cc9c05d1c67` |
| Observer ANGLE SHA-256 | `ac5c9bd696badd7d9b3bd62cce27c74acf474808f712ab78632be91b9e5c33bf` |
| ANGLE revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| Test guest | `alas_game_api32_x64`, ADB `emulator-5580` |

The runner checks these package values before routing or input. The controller's
`PinnedPackageGate` repeats version, ABI, base APK, and IL2CPP hash verification
independently instead of trusting observer claims.

## Sustained initialization

After the user handled the first-run agreement and account login, the original
read-only 120-second run passed. The final raycast-enabled 40-second closed-loop
run also passed with 40/40 valid and 36 fresh samples, generations 2 through 27,
and 26 distinct generations:

| Measure | Result |
| --- | ---: |
| Samples structurally valid | 40 / 40 |
| Samples fresh under 2.5 s | 36 |
| First / last generation | 2 / 27 |
| Distinct generations | 26 |
| Maximum typed Buttons | 59 |
| Maximum active Buttons | 9 |

The snapshot remained on the exact Unity Activity and registered already-
attached IL2CPP main thread. Flags `15`, UI stage `100`, and method mask `15`
remained valid. No fatal marker was found.

## Typed Button protocol and bounds

`GET /v1/buttons` returns `alas-headless.buttons/v1`. Each bounded record may
include Button name, full transform path, Canvas name and render mode,
active/enabled/interactable flags, world position, local RectTransform rect,
screen point, ADB point, transformed four-corner bounds, and nullable
`raycast_top`. The observer reuses one `PointerEventData` and one result list and
evaluates only reviewed semantic paths; other Buttons return `raycast_top=null`
and are not actionable. Records contain no object addresses, and the socket has
no generic invocation method.

The G3 contract independently proved the transform calculation: a `280x90`
Button centered at ADB `(640,580)` produced bounds
`left=500, top=535, right=780, bottom=625`.

The live game exposed these reviewed main targets:

| Semantic ID | ADB point | ADB bounds |
| --- | --- | --- |
| `main/battle` | about `(1192,510)` | `1112,427 - 1271,593` |
| `main/formation` | about `(1061,510)` | `1012,427 - 1110,593` |
| `main/settings` | about `(1221,36)` | `1202,18 - 1240,55` |
| `main/mail` | about `(1052,36)` | `1033,18 - 1070,55` |
| `main/shop` | about `(92,684)` | `9,650 - 175,717` |
| `main/dock` | about `(249,684)` | `166,650 - 332,717` |
| `main/task` | about `(875,684)` | `792,650 - 958,717` |
| `main/build` | about `(1031,684)` | `948,650 - 1114,717` |

## Harmless closed loop

The action runner enforced exact package, component, PID, schema, freshness,
generation, path suffix, uniqueness, state, point, and bounds gates at every
step. The completed sequence was:

```text
exact LoginUI2(Clone) at (640,360)
  -> exact main battle postcondition
  -> wait for Loading(Clone) to disappear
  -> exact bulletin close_btn
  -> exact main settings at (1221,36)
  -> NewSettingsUI(Clone), 23 active Button records
  -> exact settings back_btn at about (57,54)
  -> main battle/settings restored and Activity unchanged
```

All four injected targets reported `raycast_top=true`: their Button transform
was the top `EventSystem.RaycastAll` GameObject or an ancestor of it. An earlier
attempt correctly refused to click main settings while the bulletin
overlay was present, even though the underlying Unity Buttons still reported
active and interactable. The controller now models Loading and the bulletin as
explicit blockers; only the reviewed bulletin close target is allowed through
that overlay.

## Controller and ALAS boundary

The Python `SemanticOracle` is standard-library only. The final
`AlasSemanticSession` live smoke independently rehashed the installed package,
resolved all 14 reviewed ALAS aliases (seven semantic targets) against 42 live
Buttons with valid bounds and top raycast identity at generation 65, confirmed
that `BACK_ARROW` and raw input fail closed, and recorded
`input_injected=false`.

The staged upstream ALAS patch targets commit
`81ccf63b4540f00241628c82a58c02c7a2bb11af`. It hooks
`ModuleBase.appear()` and `Control.click()` and rejects raw multi-click,
long-click, swipe, drag, and low-level click dispatch in semantic mode. Only 14
ALAS aliases for seven main-page semantics are mapped. The generic
`BACK_ARROW` is intentionally not mapped because ALAS reuses it on unrelated
pages.

## Remaining scope

G4 and the controller plumbing are proven. This is still not an ALAS task
backend: sufficient task-specific state and controls are not mapped. No
scheduler task should be enabled before those later gates pass.

All test runs restored the modified global ANGLE settings. Unless a successful
run explicitly requested otherwise, the runner also stopped the game process.
