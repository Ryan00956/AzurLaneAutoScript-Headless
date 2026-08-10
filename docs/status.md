# Validation status

Status is evidence-scoped. A later gate is not implied by an earlier pass.

## 2026-08-10

### G20 exact combat observer input: contract pass, live mappings open

- G19's six replay phases can now be built from complete raw Unity observer
  snapshots. Fixture phase labels, OCR, image templates, coordinates, and
  scripted booleans are not accepted as production evidence.
- The original ALAS chain's `104` presence calls are pinned to an exact
  `38`-resource surface; both added and removed upstream queries now fail.
- Every resource requires reviewed exact full paths and record identity. The
  three post-grid action resources additionally require actionable top-raycast
  Unity Buttons; all frames require complete Button/Text/Image slices, coherent
  PID/generations, game/driver identity, blockers, and hash-bound payloads.
- A test-only complete six-frame fixture drives the same G19 replay without a
  phase field. Tampering, unqualified coverage, active blocker, non-top
  raycast, and resource-surface drift fail closed.
- The honest live manifest remains `0/38`, with blockers and six-ship HP/level
  mappings also unqualified. Therefore `production_ready=false`, the canonical
  ALAS patch is unchanged, and D6 input remains closed at G18.
- The suite passes `275/275`. Current read-only generations
  `119693..119695` remained complete (`96` Buttons, `60` Texts, `320` Images)
  and still showed the exact `[NetworkDown]` text; no input was injected.

See [G20 ALAS combat observer contract](g20-alas-combat-observer-contract-validation-report.md).

### G19 original combat state machine: pinned Device-free replay pass

- Six strictly increasing typed frames now represent battle preparation,
  combat execution, S result, experience result, enemy searching, and the
  stable post-battle map. Extra/reordered frames or resource/flag/stat drift
  fail before replay.
- Real pinned ALAS executed its original `_goto()`, `combat_appear()`,
  `combat()`, `combat_preparation()`, `combat_execute()`, `combat_status()`,
  enemy-searching handler, arrival confirmation, native grid mutation, and
  path rebuild.
- The exact virtual actions were D6, `BATTLE_PREPARATION`, `BATTLE_STATUS_S`,
  and `EXP_INFO_S`. No adapter or ADB method was called.
- The isolated native result was battle `0 -> 1`, ammo `5 -> 4`, D6 enemy
  removed, current fleet retained, source MAP restored, projected map
  unchanged, and shared ALAS timers unchanged.
- The original chain made `104` queries over `38` allowlisted ALAS resources;
  any new upstream query prevents success rather than silently returning false.
- Current read-only generations `103330..103331` remained complete with
  `96` Buttons, `60` Texts, `320` Images and the exact `[NetworkDown]` blocker.
- The suite passes `267/267`; the reusable qualification script passes; the
  canonical patch remains clean and identical to patchcheck.

See [G19 ALAS combat state replay](g19-alas-combat-state-replay-validation-report.md).

### G18 original ALAS `_goto()` prefix: pinned zero-input pass

- After the G17 admission, an isolated campaign shell now calls the original
  `_goto(target, expected)` and captures its own `device.click(grid)` boundary.
  The adapter click port is never invoked, the budget remains unspent, and no
  ADB input occurs.
- ALAS owns the exact sequence: low-HP retreat check, original
  `fleet_ensure()`, visibility/focus, zero-vector map swipe, grid centering,
  global-to-local conversion, color-baseline ordering, and final grid click.
  Only the fleet/camera/view/color inputs are supplied semantically.
- Low-HP retreat, fleet/index drift, stale map or decision data, native target
  drift, early Device access, changed grid annotation, any real swipe, and any
  second click fail before input.
- Real pinned `campaign_12_4.Campaign` reproduced D6 as local D3 with sight
  `(-3, 0, 3, 2)`, reached all eight expected calls, restored the exact native
  map/grid dictionaries, and left the projected map unchanged.
- A fresh read-only live request at generations `91862..91863` remained
  complete (`96` Buttons, `60` Texts, `320` Images) and still showed the exact
  `[NetworkDown]` prompt. No current live execution is claimed.
- The full suite passes `261/261`; sources compile; the canonical patch applies
  cleanly and exactly matches the exercised checkout diff.

See [G18 ALAS `_goto()` input preview](g18-alas-goto-input-preview-validation-report.md).

### G17 campaign combat admission: contract pass, live execution still closed

- A separate `ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET` now defaults to `0`; the
  first slice accepts only exactly `1` and binds it to the immutable ALAS
  decision plus the same stable semantic map object.
- The qualified shape is deliberately minimal: current fleet and one typed
  `fighting` enemy share the target cell, native cost is `0`, and both the full
  route and goto route contain only that node. Movement, fleet switching,
  bosses, pickups, and multi-node routes remain closed.
- ALAS's original `_goto()` grid annotation is recognized only at its existing
  `device.click(grid)` input boundary. The exact Unity Button is revalidated
  for path, geometry, top raycast, foreground, screen bounds, and blockers;
  the budget is consumed immediately after the tap and cannot replay.
- The independent completion contract requires ALAS battle count `+1`, target
  object removal, current fleet still on target, ammunition `-1`, stable map
  topology, and a newer complete generation.
- A Device-free replay derived `68` passable and `20` land cells from the real
  pinned `campaign_12_4.MAP` and accepted exactly D6 object `1204090` with
  ammunition `5` and cell path `chapter_cell_quad_6_4`.
- The patched runner intentionally raises `ScriptEnd` after admission
  preflight and before calling `goto()`: the original `_goto()` and combat
  observation closure is not yet qualified, so G17 performs no live grid tap.
- A fresh read-only observer sample at generations `74795..74797` was healthy
  and complete (`96` Buttons, `60` Texts, `320` Images) but still contained the
  exact `[NetworkDown]` overlay. No input was injected.
- The full controller/integration suite passes `253/253`; the canonical patch
  applies cleanly to the pinned upstream SHA.

See [G17 campaign combat admission](g17-campaign-combat-admission-validation-report.md).

### G16 original ALAS campaign decision: pinned decision-only pass

- The indexed shadow map now runs ALAS's original `battle_function()` on an
  isolated campaign/config shell and intercepts the first public `goto()`
  admission before ALAS's `goto()` implementation runs.
- Pinned real `campaign_12_4.Campaign` selected `battle_0`, logical fleet `1`
  (`cell_fleet_shengwang_younv`), and enemy `D6` from origin `D6`, with
  expected `combat`, native cost `0`, route `D6`, and native goto nodes `D6`.
- ALAS's original emotion check returned at values `119/119`; any timed wait
  fails closed. Class-level road grids, the projected map, and real config
  were unchanged after the transaction.
- Device access, `_goto()`, fleet switching, map control, scanning, combat,
  retreat, and branches without a projected enemy/ammo decision all fail
  closed.
- A fresh live read at generation `59956` still found the exact
  `[NetworkDown]` blocker over the same fleet identity. No input was injected,
  and no fresh complete same-process decision is claimed.
- The full controller/integration suite passes `245/245`; the canonical patch
  applies cleanly to the pinned upstream SHA and exactly matches the exercised
  checkout's full Git diff.

See [G16 ALAS campaign decision preview](g16-alas-campaign-decision-preview-validation-report.md).

### G15 fleet-index reconciliation: live passive and pinned native pass

- The current displayed fleet now comes from one exact `1|2` top-stage Text
  plus a unique exact match between a `cell_fleet_*` marker suffix and the
  displayed fleet's typed ship sprites.
- Three live read-only generations `33896 -> 33905 -> 33913` consistently
  reported displayed fleet `1`, six roster sprites, map markers
  `cell_fleet_shengwang_younv/cell_fleet_ying`, and only
  `cell_fleet_shengwang_younv` as the roster match. No input was injected.
- The exact `[NetworkDown]` overlay remained present. A full map-model call
  failed closed, so no fresh same-process indexed projection is claimed.
- The projection now supplies ALAS `fleet_show_index`, logical
  `fleet_current_index`, indexed fleet locations, and one native
  `is_current_fleet` flag. It reuses ALAS's own reversed-fleet rule.
- Pinned real-ALAS tests passed both normal (`fleet1=D6`, `fleet2=F8`, current
  `1`) and reversed (`fleet1=F8`, `fleet2=D6`, current `2`) configurations.
- Map control, fleet switching, movement, combat, retreat, and rewards remain
  uncalled and unmapped. The suite passes `235/235`; the canonical patch
  applies cleanly and exactly matches the exercised checkout.

See [G15 fleet-index validation](g15-campaign-fleet-index-validation-report.md).

### G14 read-only ALAS map synchronization: pinned native-object pass

- The G13 model now projects transactionally into a deep-copied native ALAS
  `CampaignMap`; ALAS's own `map_data_init()`, `find_path_initial()`, and
  `_find_path()` remain the data/path owners.
- A Device-free run against pinned `campaign_12_4.Campaign` reproduced the
  live generation `4817` topology and dynamic state: 68 passable cells, 20
  land cells, fleets `D6/F8`, enemies `C6/D6`, and ammunition `F2`.
- Native ALAS routes were produced for both semantic fleet markers. Temporary
  costs/connections were then reset, and configuration changes made by shadow
  initialization were restored.
- Semantic marker-to-ALAS fleet-index identity is deliberately unresolved.
  `fleet_1_location` and `fleet_2_location` remain empty, so this projection
  cannot start ALAS movement accidentally.
- `map_control_init()`, scanning, fleet switching, grid movement, combat,
  retreat, and rewards are not called or mapped.
- A current read-only live check at generation `21296` still found the exact
  `[NetworkDown]` overlay above the loaded map. No input was injected, and no
  new same-process live pass is claimed.
- The controller/integration suite passes `230/230`; the canonical patch
  applies cleanly to the pinned upstream SHA and exactly matches the exercised
  checkout's full Git diff.

See [G14 ALAS map synchronization validation](g14-alas-map-sync-validation-report.md).

### G13 read-only campaign map model: live ALAS pass

- The stable `12-4` model combines ALAS's own `11x8` shape and exact 20-cell
  land topology with complete Unity state: 92 Buttons, 300 Images, and 55
  Texts, all non-truncated and unchanged across two increasing generations.
- It reported 68 passable cells, fleets `D6/F8` with `5/5` ammo, enemies
  `C6/D6` with typed class/scale/level/fighting state, and the `event4`
  ammunition pickup at `F2`.
- Fleet localization no longer depends on visible `shadow` Images. Each
  active fleet child carries its `cell_fleet_*` ancestor world position and
  must match one grid Button uniquely. Both live distances were exactly zero;
  the next-nearest cells were about `1.528` away.
- The final campaign replay used stage/fleet/sortie budgets `0/0/0`, replaced
  input injection with a rejecting assertion, logged the model at generation
  `4817`, and returned `ALAS_G13_READ_ONLY_MAP_RESULT True` before upstream
  retreat.
- One controlled `1/3/1` sortie recreated the map after the observer update.
  Its later generic `POPUP_CONFIRM_WHITE` probe failed closed after arrival;
  no grid, movement, combat, retreat, or reward input occurred.
- A later recurring `[NetworkDown]` overlay left the underlying map loaded but
  blocked the read-only model exactly as intended; no obscured map state was
  returned.
- Final observer APK SHA-256:
  `bb9bdaa7838182731296ce5ab4f6f17aad0394660aa7b24c245a1ccfed18b220`.
  The controller/integration suite passes `225/225`.

See [G13 campaign map-model validation](g13-campaign-map-model-validation-report.md).

### G12 campaign sortie: one exact input and real map-root proof

- `ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET` is independent, defaults to `0`, and
  qualifies only the exact positive value `1`. Fleet validity, disabled
  auto-search/2x, submarine mode, fleet order, oil, and the unique sortie
  target are all revalidated before ALAS's original sortie click.
- The budget-zero final command returned
  `ALAS_G12_SORTIE_BUDGET0_FINAL True` after exact fleet reconciliation and
  cancel, with no sortie. A later budget-one replay injected exactly one
  `campaign/fleet-preparation/sortie` at `2026-08-10 11:20:51.703`.
- The original map postcondition failed closed because it assumed a nonexistent
  `LevelScene(Clone)` root. After restart, the game restored the same `12-4`
  map. Generation `3103` proved the real `LevelCamera/.../LevelGrid` root, 70
  reviewed map Button paths, three fixed Image/sprite anchors, and
  `IN_MAP=True`.
- The first map attempt exposed a recursive IL2CPP liveness stack failure. The
  final observer uses non-recursive `Resources.FindObjectsOfTypeAll(Type)` and
  a bounded approximately 10 Hz typed-snapshot cadence. It remained fresh and
  stable on the recovered map beyond the earlier failure window.
- No grid, fleet movement, combat, retreat, or reward input occurred. The
  evidence is intentionally split rather than spending another sortie merely
  for a same-process success line.
- Final observer APK SHA-256:
  `7481e25e6a5d51e05101b55befdd331a051b76181819fe80ce676b7c26bbb38a`.
  The relevant controller/integration suite passes `220/220`.

See [G12 campaign sortie validation](g12-campaign-sortie-validation-report.md).

### G11 campaign fleet preparation: exact three-mutation reversible pass

- The pinned campaign command now calls ALAS's original
  `self.fleet_preparation()` and preserves the existing `FleetPreparation` and
  `FleetOperator` branch, retry, dropdown, and selection loops. Semantic mode
  replaces only reviewed typed observations and exact input endpoints.
- `ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET` is independent and defaults
  to `0`. Preflight simulates ALAS's ordered branch decisions before any fleet
  input. The positive run reconciled `(1, 2, 1) -> (1, 2, 0)` using exactly
  `fleet/2/clear`, `submarine/1/clear`, and `option/2`, then returned
  `ALAS_G11_FLEET_BUDGET3_FINAL True`.
- The final-artifact budget-zero command injected no fleet input and returned
  `ALAS_G11_FINAL_ARTIFACT_BUDGET0 True` with generations
  `1220 -> 1237 -> 1245`. An independent re-entry found the original
  `(1, 2, 1)` selection restored at generation `1051`; the second cancel
  returned to the same chapter/stage set at generation `1057` with
  `IN_MAP=False`.
- Dropdown navigation and idempotent empty-row clears do not consume mutation
  budget. Any failure closes the dropdown if necessary and invokes ALAS's
  original cancel loop. Hard mode and formation-layout changes remain closed.
- The fleet sortie target remains absent from the native raycast allowlist and
  adapter click map. No sortie, map movement, combat, or reward input occurred.
- The final observer APK SHA-256 is
  `29f49a33318321b1c38fa2e590879701159d6404beabfe59af54a2fccb6ef91f`.
  The controller suite passes `217/217`; the 22-file canonical patch applies
  cleanly to `81ccf63b4540f00241628c82a58c02c7a2bb11af`, compiles, and matches
  the live patched source by SHA-256.

See [G11 campaign fleet-preparation validation](g11-campaign-fleet-preparation-validation-report.md).

### G10 campaign pre-sortie: bounded reversible ALAS pass

- The original ALAS campaign navigation, chapter/stage selection,
  `enter_map()`, and `enter_map_cancel()` loops remain in control. Semantic
  mode replaces their reviewed OCR/template/page/input ports; one narrow
  safety checkpoint cancels and stops at proven fleet preparation.
- `ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET` defaults to `0`. The zero-budget
  full command returned `True` before stage input. The budget-1 command clicked
  exact `12-4`, exact map-preparation proceed, and exact fleet-preparation
  cancel, then returned `ALAS_CAMPAIGN_BUDGET1_FINAL_ARTIFACT True`.
- The final-artifact proof generations were `2102 -> 2120 -> 2132`. A final
  independent read at generation `2208` observed `马里亚纳风云上`, stages `12-1` through `12-4`,
  no preparation layer, and `IN_MAP=False`.
- The fleet sortie `start_button` remains outside the native raycast allowlist
  and semantic click map. Formation changes, sortie, map movement, combat, and
  rewards remain closed.
- Stale-root transition windows failed closed during development. Their final
  tolerance is limited to a proven map-proceed or cancel receipt and a finite
  deadline. A final cold-start run also exposed chapter-page settling after
  campaign-menu entry; that exact input is receipt-cached and its incomplete
  page check is passive only inside the existing finite campaign transition
  window. The legacy direct `campaign_extract_name_image()` caller now receives
  typed stage Buttons instead of pixels.
- The observer APK SHA-256 is
  `6bd736dadb3741599ce2d9d449c474356ebbbe7d7b4b21ffcf55ca3e37b9c2c9`.
  The controller suite passes `209/209`. The 21-file ALAS patch applies cleanly
  to `81ccf63b4540f00241628c82a58c02c7a2bb11af`; every patched file matches the
  live source by SHA-256 and compiles.
- An earlier login automatically received a `1500`-coin login/daily reward.
  External ALAS test configurations also recorded scheduler/emotion and
  screenshot-benchmark updates. These side effects are disclosed and are not
  part of the campaign authorization.

See [G10 campaign pre-sortie validation](g10-campaign-pre-sortie-validation-report.md).

## 2026-08-09

### G9 bounded task inputs: three full ALAS replays passed; Gacha recovery pending

- The pinned patch now brackets the original Tactical, Research, Dorm, and
  Gacha `run()` implementations without replacing their state machines. ALAS
  still owns ship/book/project/food/pool filtering, retry and popup loops,
  queue filling, and scheduling; semantic mode replaces only reviewed
  observations, OCR values, and exact input endpoints.
- The five completed input slices are read-only research selection alignment,
  one bounded research start, full research queue/reward/scheduling I/O,
  tactical course assignment, and dorm collect/feed plus one construction
  submit. Every mutating slice is default-closed behind an integer budget.
- Live adapter passes assigned `Hipper` with skill `荆棘与坚盾` and a matching
  T4 book; claimed five queued research completions and one finished card,
  then started exact project `G-412` after matching its `1500`-coin prompt.
- Dorm quick collect used its exact control. Feed input targets the food-card
  `icon_bg`, not the adjacent purchase `+`, and proved inventory
  `17783 -> 17782` plus food `0 -> 1000`.
- Complete patched commands now return `TACTICAL_RESULT=True`,
  `RESEARCH_RESULT=True`, and `DORM_RESULT=True`, preserving ALAS navigation,
  filtering, retry loops, and scheduling. Dorm's full replay also tolerated
  slow CourtYard hierarchy rebuilds and a network-reconnect prompt without
  replaying a food-card input.
- Construction previously selected the heavy pool, cross-checked `3662` cubes
  and `84908` coins against the exact one-order `2`-cube/`1500`-coin prompt,
  and reached a typed queue countdown. The current full Gacha replay selected
  Light and submitted one exact `1`-cube/`600`-coin order, but returned
  `GACHA_RESULT=False` because the ALAS warning alias was initially allowed to
  confirm the order one state too early. Preparation and order aliases are now
  disjoint. The resulting natural countdown remains fail-closed to a fresh
  task context and is neither accelerated nor collected.
- Observer APK SHA-256 is
  `bfd782b307de51621dfd8f796962e25ffbc7bbba12b60e8204631c6ba15729fc`.
  The final G4 package/observer evidence is
  `evidence/g4-game-init-20260809T114938Z-emulator-5580`. The controller suite
  passes `197/197`; Python compilation, diff whitespace, native observer build,
  installation, package fingerprint, and clean application plus compilation
  of the pinned ALAS patch pass.
- A corrected full Gacha command replay requires the queue to be empty again.
  Event/wishing-well construction, multi-order submission,
  accelerating or collecting an existing queue, stage selection, map/battle
  input, and Lua state remain closed.

See [G9 patched-ALAS task replay validation](g9-alas-task-replay-validation-report.md).

### G8 real ALAS reward and commission slice: clean bounded pass

- A clean checkout of pinned upstream ALAS commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af` completed the real `Reward`
  command twice. Both runs observed typed claimable state and stopped before
  claim because the mission claim budget was zero.
- The real `Commission` command completed once with start budget zero. ALAS
  scanned typed rows, applied its existing `cube` preset, selected three daily
  candidates, and stopped before row input.
- Two separately bounded start invocations selected `高阶战术研发II` and
  `高阶战术研发I`. Each revalidated the exact typed row/detail identity, assigned
  ships, zero oil cost, and one remaining budget unit before one input. Their
  post-states were proved with the matching identity, decreasing countdown,
  exact `tag_ongoing` marker, and `取消` action label. No third start was made.
- The second positive run returned from the proven detail to the list, then a
  redundant ALAS tab reset encountered a transient truncated Image snapshot.
  Complete transition reads now receive a bounded retry, and the pinned patch
  skips that reset once the independent start budget is exhausted.
- When `高阶战术研发I` finished, a separate integer reward budget of one admitted
  the exact commission finish input only after the typed finished counter was
  read as `1` twice, including immediately before the click. ALAS then closed
  the reviewed ship-EXP and award popups.
- That original reward command did not finish its proof: the combined reward
  and award view filled the observer's 64-Button buffer and correctly failed
  closed as truncated. The native capacity was raised to 128 and rebuilt. After
  a `-force-gfx-st` restart, the snapshot was complete at 58/128, the exact
  finished counter was `0`, and a full reward/start-budget-zero `Commission`
  replay returned successfully without a second claim or a third start.
- At that historical recovery point, the remaining running commission was
  parsed as `1/4` and scheduled for `2026-08-09 16:52:07`. That first claim
  remains recovery-qualified rather than being rewritten as an in-context
  `CommissionRewardProof`.
- A later five-row daily list qualified exact typed multipage scrolling. The
  reviewed handle moved from normalized top through `0.695` to bottom `0.998`
  and returned to `0.010`; actionable row indexes changed `0-3 -> 0-4 -> 1-4`.
  The ALAS replay deduplicated overlapping viewports by stable list mode and
  row index, reporting exactly five daily rows and one running commission.
  Single-page urgent state was proven by complete typed absence of both scroll
  track and handle. Generic swipe and drag paths remain closed.
- A separate one-hour `日常资源开发III` start was allowed to finish naturally.
  The next real ALAS reward call used reward budget `1` and start budget `0`,
  logged `SemanticCommissionReward 1 -> 0` with the reviewed ship-EXP and
  AwardInfo close chain, and returned successfully. An exact dashboard read
  and full dual-budget-zero ALAS replay then proved counter `0`, five pending
  rows, and zero running rows. Commission reward budget `1` is therefore now
  clean-qualified in addition to the preserved earlier recovery evidence.
- One exact `[NetworkDown]` prompt blocked the pre-reward page. Its reviewed
  Chinese prompt/labels and top-raycast confirm target were live-proven and
  restored the page. Larger budgets, nonzero-oil rows, cancellation, and
  unattended repeated starts remain unqualified. See the
  [G8 validation report](g8-alas-reward-commission-validation-report.md).
- Final observer APK SHA-256:
  `3b86a745cefbc2a493b941571e6929e965cd7f44be4a2a14ccfa257efdf99fed`.
  The controller suite passes `148/148`; Python compilation, native build,
  diff whitespace, and clean pinned-patch application checks pass.

### G7 typed task surfaces and read-only campaign: passed in reviewed scope

- The typed controller now models the reward dashboard, commission rows and
  empty marker, tactical slots and countdowns, five research cards,
  construction pool/cost, dorm occupancy/food/comfort/floor, and the visible
  campaign chapter/stage labels. Missing, duplicate, truncated, incoherent, or
  contradictory records fail closed.
- The pinned ALAS patch retains the original mission, commission, tactical,
  and research state machines. It supplies typed observation, countdown, and
  safe-popup inputs; the dorm scheduler obtains its occupied-slot count from
  typed state. The patch applies cleanly to upstream commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- Live adapter validation completed exact reward-to-tactical entry, observed
  four empty tactical slots, and returned through the contextual ALAS
  `BACK_ARROW`. Earlier in the same controlled session, four completed
  tactical rewards were received and every exact “continue learning” prompt
  was canceled; no new class was started.
- Live dorm state was `6/6` occupied slots, `0/40000` food, `454` comfort, and
  floor `1`; the exact statistics confirmation and return controls were
  validated. Feeding, collecting, decorating, and ship assignment remain
  unmapped.
- Live construction state was pool `heavy`, `3661` cubes, `2` cubes/build, and
  `1500` coins/build. The ALAS `GOTO_MAIN` alias returned through the exact
  construction `back_btn`; the construction start control remains
  presence-only and cannot be clicked through the adapter.
- Live campaign validation entered only the normal chapter list, read chapter
  `马里亚纳风云上` and stages `12-1` through `12-4` with their typed names,
  then returned. Generic `BACK_ARROW` remained unmapped; no stage, formation,
  sortie, or battle control was clicked.
- The final observer APK SHA-256 is
  `3c05c2bf913464ad7dee7a0e62c4fea3b5919a5c59c6a11d2274c8bd867d6c4e`.
  The controller suite passes `109/109`; Python compilation, diff whitespace,
  native observer build, installation, package fingerprint, and clean pinned
  patch application checks also passed.
- This is not a full unattended ALAS pass. Commission selection/start,
  tactical course assignment, research selection/start, dorm mutations,
  construction submission, campaign stage selection, map control, battle
  control, and Lua state are still closed.

### G6 typed UI and mission sidebar: passed in reviewed scope

- `GET /v1/ui` now exposes bounded, typed Toggle, UGUI Text, TextMesh Pro, and
  Image records. The final live capture reported method mask 15, zero observer
  errors, and no Image truncation.
- Typed text includes UTF-8 content and exact RectTransform bounds. The ALAS OCR
  hook resolves only text inside the requested OCR area and rejects missing,
  overlapping, truncated, malformed, out-of-bounds, and alphabet-invalid
  matches.
- Six exact task-sidebar Image paths expose selected/unselected sprite identity.
  Only those reviewed paths receive native EventSystem top-raycast evaluation.
- A live task-page loop selected weekly, observed `icon_week_sel`, returned to
  all, and exited to main. No reward input was injected by this loop.
- Final observer APK SHA-256:
  `fbc288dbe20e0264e90d522772922b72a24d799888e0804cd47781727475a571`.
  The read-only final capture is
  `evidence/g6-semantic-ui-20260809T030729Z-emulator-5580`; see the
  [G6 validation report](g6-semantic-ui-report.md).

### Post-G5 ALAS state-machine reuse: implemented; full live rerun pending

- The integration patch no longer calls a replacement mission flow from the
  top of `Reward.reward_mission()`. It brackets an adapter context and leaves
  ALAS's original notice, navigation, collect, claim, receive, retry, timeout,
  and daily/weekly ordering in control.
- ALAS reward observations from `appear()`, `match_template_color()`, and
  `image_color_count()` now consume typed semantic input. Normal `click()` is
  translated to reviewed semantic actions; raw coordinate and gesture paths
  remain rejected.
- `MISSION_MULTI`, `MISSION_SINGLE`, `MISSION_UNFINISH`, mission-page identity,
  the default sidebar, and `GET_ITEMS_1`/`GET_ITEMS_2` have explicit adapters.
  A claimable/unfinished state requires the same signature across two
  increasing observer generations.
- The separate environment opt-in now creates a one-claim budget per ALAS
  `reward_mission()` invocation. The budget is discarded in `finally`, and a
  missing opt-in refuses the claim before ADB input.
- Weekly-tab state and exact semantic input are now reviewed and live-proven at
  the adapter boundary. Weekly-only end-to-end execution, positive mission
  red-dot behavior, numeric-row claiming, ship-reward popups, and empty-page
  inference remain closed.
- This refactor has unit coverage and was syntax/lifecycle checked against the
  clean pinned upstream commit. The historical G5 claim evidence below still
  predates this ownership change, so the complete ALAS-owned claim path is not
  yet a new live pass.

### G5a/G5b - ALAS mission no-claim and controlled claim-all: passed

- The final observer evaluates the exact task-page back and `GetAllButton`
  paths plus bounded task-row `get_btn` and `go_btn` shapes. The controller
  accepts only exact numeric row indexes. These targets are subject to the same
  top-EventSystem-raycast gate as earlier actions.
- Mission state must have the same non-unknown signature across at least two
  increasing generations. Duplicate rows, clipped claim controls, blockers,
  and mere absence of task Buttons fail closed.
- The pinned upstream ALAS patch routes `Reward.reward_mission()` through the
  semantic adapter only when semantic mode is explicitly enabled. Claim input
  requires the separate `ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE=1` opt-in.
- G5a entered the exact main task Button, observed five stable unfinished
  `go_btn` rows, returned to main, and injected zero claim inputs.
- G5b's zero-claim preflight observed a unique actionable `GetAllButton` and
  three numeric-row `get_btn` targets, all with top-raycast proof.
- The controlled run injected exactly one claim at `GetAllButton`, observed the
  exact `AwardInfoUI(Clone)/items/close`, closed it, and proved claim rows
  changed from three to zero while five unfinished rows remained stable.
- It then returned through the exact task back Button. An independent second
  task-page run reported `nothing-claimable`, and a no-input main-page oracle
  found no blockers with all eight reviewed targets actionable.

Primary evidence is in
`evidence/g4-game-init-20260809T013349Z-emulator-5580`; see the
[G5 validation report](g5-mission-validation-report.md).

### Final-driver regressions: passed

- Final observer ANGLE APK SHA-256:
  `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7`.
- The real game passed login/main reachability and a 40-second sustained run:
  40/40 valid samples, 36 fresh, generations 2 through 28, and 27 distinct
  generations. This did not repeat the earlier formal settings round trip.
- G3 passed in `evidence/g3-observer-20260809T013932Z-emulator-5570` with the
  exact contract Button raycast, foreground/freshness refusal, and recovery.
- G2 passed in `evidence/g2-null-20260809T014015Z-emulator-5570`: 47.117
  seconds, 20 structured events, three scenes, eight completed readbacks over
  the full run, and zero readback errors.

## 2026-08-08

### G0 - baseline capture tooling: implemented and exercised

- `capture-g0.ps1` completed against `127.0.0.1:16384` and
  `com.bilibili.azurlane` without failed commands.
- The evidence manifest's file sizes and SHA-256 values were independently
  rechecked.
- The live process mapped native x86_64 `libunity.so`, `libil2cpp.so`, EGL,
  GLES, and Vulkan/emulation libraries.
- This is environment provenance, not proof of the active game renderer. A
  separate same-host SwiftShader comparison now exists for the G2 Unity
  contract, but it is not a same-guest game baseline for MuMu.

### G1 - NULL GLES contract: passed on the validation host

- ANGLE is pinned to `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- The x86_64 Android driver APK builds with only the NULL renderer enabled.
- The Android loader successfully selects the custom package for only the
  contract probe package.
- A final 3,600-second run passed shader/program, buffer, texture, FBO, query,
  draw, fence, direct readback, PBO readback, swap pacing, and logical surface
  checks.
- Observed identity: `Google Inc. (NULL)` / `ANGLE (NULL, NULL, )`.
- Observed surface: `1280x720`; direct and PBO RGBA: `00000000`.
- The final heartbeat reported 219,300 frames at 60.000 FPS. The 121 memory/CPU
  samples showed PSS falling from 94,703 KiB to 74,355 KiB and RSS falling from
  176,380 KiB to 153,348 KiB. The post-warm-up PSS trend was approximately
  +2 KiB/minute, with no monotonic growth.
- Coarse `top` samples reported 0.73% mean CPU, 4% p95, and 4% maximum.
- No fatal signal, Android Runtime fatal, or context-loss marker was found in
  the captured process logs.
- Driver and probe APK hashes revalidated against the manifest. All modified
  Android ANGLE settings were restored to their original unset state, and the
  game PID remained unchanged throughout the package-isolated test.

See the [G1 validation report](g1-validation-report.md) for artifact hashes,
evidence scope, and remaining limitations.

### G2 - Unity contract and software baseline: passed

- The contract was built with Unity `2022.3.62f3` changeset `96770f904ca7`,
  IL2CPP, and x86_64 only. The final APK SHA-256 is
  `94ee95a8a6988c6b360047c66739cace3e1201e7b389b6d0e61503284ffeb696`.
- The original package-isolated 80-second functional run used
  `ANGLE (NULL, NULL, )`, OpenGLES3, and a `1280x720` logical surface.
- `Update`, `FixedUpdate`, `WaitForEndOfFrame`, animated UI state, five scene
  transitions, and app pause/resume all advanced without process restart.
- A safe test-button click changed its semantic marker from `contract/button`
  to `contract/button-clicked` with generation 2.
- All 15 AsyncGPUReadback requests completed with 1,024 zero-filled bytes;
  there were no errors or timeouts.
- The run produced 31 structured events and six heartbeats. The final heartbeat
  reported 1,800 updates, 3,365 fixed updates, and 1,799 end-of-frame resumes.
- PSS/RSS changed from 160,195/243,128 KiB to 154,475/238,372 KiB. Coarse
  process CPU samples averaged 5.87% with an 8% maximum.
- No fatal signal or context-loss marker was found. APK hashes matched the
  manifest, all ANGLE settings were restored, the test process was stopped,
  and the game PID remained `7547`.
- The software comparison used Android Emulator `37.1.11`, the same API 32
  x86_64 AVD/image, identical Unity APK and `1280x720` surface, and separate
  cold QEMU processes for official `-gpu swiftshader` and package-routed NULL.
- SwiftShader and NULL both passed the full functional contract. Host QEMU
  sustained CPU fell from 2.0551 to 0.5178 core equivalents (-74.8%). CPU time
  per 1,000 Updates fell 71.6%, so the advantage remains after accounting for
  the NULL leg's lower Update count.
- Host QEMU median working set fell 9.54%; Android app median PSS/RSS fell
  7.67%/4.83%. The fail-closed comparison manifest passed with no failures.
- Final evidence is in
  `evidence/g2-system-20260808T111131Z-emulator-5570`,
  `evidence/g2-null-20260808T111610Z-emulator-5570`, and
  `evidence/g2-comparison-20260808T112155Z`.

See the [G2 validation report](g2-validation-report.md) for the evidence scope.

### G3 - Observer contract: passed on the Unity contract workload

- The ANGLE component found all 32 allowlisted IL2CPP exports through the
  in-memory ELF dynamic table despite Android linker-namespace isolation;
  `RTLD_DEFAULT`, soname `RTLD_NOLOAD`, and full-path `RTLD_NOLOAD` remained
  unavailable.
- The unmodified Unity Android activity accepted the `unity` Intent extra
  `-force-gfx-st`. NULL Surface Swap and managed `Update()` then executed on
  the same Unity main-thread TID.
- Main-thread typed snapshots used Unity liveness enumeration for
  `UnityEngine.UI.Button`, fixed getter invocation, active scene handles, and
  monotonic snapshot/scene/semantic generations.
- A local abstract Unix socket exposed only `GET /v1/snapshot`, checked
  `SO_PEERCRED`, rejected an arbitrary invocation-shaped request, and returned
  a fixed `alas-headless.observer/v1` schema.
- The safe contract click changed one active Button from interactable to
  non-interactable and advanced semantic generation. A later scene transition
  advanced scene generation.
- Pressing Home changed the top-resumed package to Launcher and made the last
  snapshot stale. The action gate stayed closed; resuming restored a fresh,
  higher-generation snapshot.
- The observer also exposes `GET /v1/buttons` with fixed schema
  `alas-headless.buttons/v1`, bounded records, full hierarchy paths, Canvas
  identity, state flags, screen/ADB points, and four-corner RectTransform
  bounds. It exposes no object addresses or generic invocation.
- Final G3 evidence with bounds and top-raycast validation is
  `evidence/g3-observer-20260809T013932Z-emulator-5570`; its manifest passed
  with no failures. The final observer ANGLE and Unity APK SHA-256 values are
  `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7`
  and `87e845359bc1d957b0c75f685f461b017ed6e05d0a593088683511400e8e99ba`.
- A final 47.117-second G2 regression with the 32-symbol, typed-bounds,
  reviewed-target raycast observer passed in
  `evidence/g2-null-20260809T014015Z-emulator-5570`: 900 Updates, 1,689
  FixedUpdates, 899 end-of-frame resumes, eight completed readbacks over the
  full run, and zero readback errors.

See the [G3 validation report](g3-validation-report.md) for evidence scope and
remaining limitations.

### G4 - harmless real-game closed loop: passed

- After the user completed agreement and account login, Chinese 9.7.10 reached
  its login/main Unity UI on the dedicated API 32 x86_64 AVD under NULL.
- A 120-second no-input run produced 120/120 structurally valid samples,
  113 fresh samples, generations 2 through 99, and 98 distinct generations;
  no fatal marker was found.
- The game exposed exact paths and bounds for login and the main-page battle,
  formation, settings, mail, shop, dock, task, and build Buttons.
- The action runner clicked only the exact login target, waited for an exact
  `battle` postcondition, detected and dismissed the known bulletin overlay,
  entered settings at `(1221,36)`, observed 23 settings Buttons, clicked the
  exact settings `back_btn` at about `(57,54)`, and verified that main
  battle/settings targets and the exact foreground Activity returned. Every
  injected target was independently the top `EventSystem.RaycastAll` result at
  its point (or an ancestor of that result).
- The standard-library Python oracle independently passed a live no-input smoke
  over all 14 reviewed ALAS aliases (seven main semantics), including top
  raycast identity. It checks schema, package, PID, peer UID, driver revision,
  foreground component, freshness, generation coherence, unique path mapping,
  bounds, and known blockers.
- The ALAS-name bridge maps only 14 reviewed aliases for seven main-page
  semantics. It independently verifies version, ABI, base APK, and IL2CPP
  hashes. Unmapped assets and raw multi-click/long-click/swipe/drag calls raise
  instead of injecting coordinates.

Evidence is in
`evidence/g4-game-init-20260808T160921Z-emulator-5580`,
`evidence/g4-game-init-20260808T172750Z-emulator-5580`, and
`evidence/g4-game-init-20260808T172941Z-emulator-5580` (including
`alas-adapter-live.json`). G4 is passed. The later G5a result covers only the
mission no-claim branch and does not retroactively broaden G4. See the
[G4 validation report](g4-preflight-report.md).

## Android loader compatibility found during G1

Android's `GraphicsEnvironment` requests a developer ANGLE package with the
Vulkan platform token even when the application did not choose a renderer.
The NULL-only build therefore needs a narrow loader-token translation before
display construction. It also needs common RGBX Android configs and an
implementation of swap-with-damage used by HWUI. These are maintained as
separate patches so each compatibility behavior remains auditable.
