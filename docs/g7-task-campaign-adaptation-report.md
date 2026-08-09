# G7 typed task and campaign adaptation

## Outcome

G7 passes a bounded adapter-level scope. It replaces additional OCR and pixel
observations with exact Unity Button, Toggle, Image, UGUI Text, and TextMesh Pro
state while leaving the pinned ALAS state machines in control. It is not a
claim of full unattended ALAS support.

The final observer APK SHA-256 is
`3c05c2bf913464ad7dee7a0e62c4fea3b5919a5c59c6a11d2274c8bd867d6c4e`.
It was built from the pinned ANGLE checkout, installed on `emulator-5580`, and
the game was cold-started with Unity argument `-force-gfx-st`.

## Adapted typed surfaces

| Surface | Typed input supplied to ALAS/controller | Enabled input |
| --- | --- | --- |
| Reward dashboard | exact finished/ongoing/free counters, including independently proven zero | reviewed finish/go navigation only |
| Commission | tab sprite, row name/level/duration/status/type, explicit empty text | reward receive and exact return; selection/start remains closed |
| Tactical | ship/skill/progress, finished/running state, strict countdown | reward receive, exact continue-prompt cancel, contextual return |
| Research | five card codes, series, and status | existing ALAS status helpers; project start remains closed |
| Construction | selected pool Toggle, cube ownership, cube/coin unit cost | exact return only; `start_btn` is presence-only |
| Dorm | occupied/total slots, food/capacity, comfort, floor, countdown | exact statistics confirm and return; mutations remain closed |
| Campaign | entrance/chapter distinction, chapter title, visible stage codes/names | normal-chapter entry and exact return only |

Generic OCR in semantic mode reads only complete typed text records inside the
requested ALAS rectangle. Missing text, overlap, truncation, out-of-bounds
records, alphabet violations, stale generations, ambiguous identity, blockers,
and non-top raycast targets raise instead of falling back to pixels.

## ALAS ownership

The integration patch brackets ALAS mission, commission, and tactical
invocations with narrow contexts and leaves their retry, timeout, receive, and
navigation loops intact. Research pixel helpers consume the typed project
model, tactical scheduling consumes typed countdowns, and dorm scheduling uses
the typed occupied-slot count. The generic low-level click, multi-click,
long-click, swipe, drag, and direct OCR paths remain rejected in semantic mode.

The patch applies cleanly to pinned upstream commit
`81ccf63b4540f00241628c82a58c02c7a2bb11af`.

## Live checks

- Tactical reward navigation reached a page with four empty slots and returned
  through ALAS's contextual `BACK_ARROW`. Four earlier completed rewards were
  received under explicit authorization; each exact “continue learning” popup
  was canceled, so no new class began.
- Dorm reported `6/6`, food `0/40000`, comfort `454`, and floor `1`. Its
  statistics popup and reviewed return controls were closed exactly.
- Construction reported pool `heavy`, `3661` cubes, and a unit cost of `2`
  cubes plus `1500` coins. ALAS `GOTO_MAIN` returned through the exact
  top-raycast-proven `back_btn` without touching `start_btn`.
- Campaign entry and chapter page were distinguished even though they share a
  back-button hierarchy path. The chapter page reported `马里亚纳风云上` and
  `12-1 先声夺人`, `12-2 鲁莽的后果`, `12-3 空中对决`, and
  `12-4 TF58，翱翔于天际`. No stage Button was allowlisted or clicked.

The controller suite passes `109/109`. `compileall`, `git diff --check`, the
native observer build, APK installation, package fingerprint verification, and
clean pinned-upstream `git apply --check` also passed.

## Closed gates

The observer protocol still exposes only its three fixed read endpoints and no
arbitrary managed or Lua invocation. The following remain deliberately closed:

- commission selection/start;
- tactical course or ship assignment;
- research selection/start;
- dorm feeding, collection, decoration, and assignment;
- construction submission or queue acceleration;
- campaign stage selection, scrolling, map movement, formation, sortie, and
  battle control;
- Lua/game-state inspection and full unattended ALAS execution.

Each requires its own exact typed model, reviewed action allowlist,
postcondition, rollback/stop behavior, and live closure before it can be
enabled.
