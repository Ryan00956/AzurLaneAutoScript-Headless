# Acceptance gates

Status terms are deliberately strict. A build passing does not imply a later gate has passed.

Current status: G1-G4, G5a, controlled G5b, scoped G6-G8, the G9 bounded
adapter slices, and the G10-G13 campaign slices passed. G14 has a pinned
native-object pass while its fresh same-process live replay is network-blocked.
G15 adds a live passive fleet-identity pass and pinned indexed projection; its
fresh complete live-map projection remains blocked by the same network dialog.
G16 adds a pinned original-ALAS decision-only pass with first `goto()` capture;
its fresh same-process replay remains blocked by that dialog, and no movement
or combat input is enabled.
G17 adds a default-zero, decision-bound combat admission contract and an exact
dynamic grid-input port, but the patched runner still stops after preflight.
It is not a movement or battle execution pass.
G4 includes
login/main reachability, sustained semantic state, RectTransform bounds, top
EventSystem raycast identity for each action, and a settings-page return loop.
G5a covers only the ALAS mission-reward no-claim branch. G5b covers one
`GetAllButton` claim on the default task page. G6-G8 add typed UI/task
observation and real bounded Reward/Commission passes.

G7 broadens typed observation to selected task surfaces and a read-only
campaign chapter. It does not enable resource-consuming task starts, stage
selection, map control, battle control, or Lua invocation.

## G0 - Reproducible baseline

Required evidence:

- Android build fingerprint, ABI list, API level, display size/density, and top-resumed package.
- Target package version name/code and APK paths/hashes.
- PID, mapped Unity/IL2CPP/EGL/GLES/Vulkan libraries, and early graphics initialization log.
- `libunity.so` and `libil2cpp.so` build IDs or hashes when root-readable.
- Same-host SwiftShader or existing software-rendering CPU/RSS baseline.

Pass means the evidence bundle is complete and internally consistent. It does not mean ANGLE NULL is compatible.

## G1 - Android GLES NULL contract

Required behavior:

- Android loads the pinned custom ANGLE package for only the contract probe package.
- EGL context and window surface initialize successfully.
- The Unity-visible logical surface remains `1280x720`; a compositor placeholder must not change that logical size.
- Shader/program, texture, buffer, FBO, query, fence/sync, swap, and readback lifecycles complete.
- `glReadPixels` and PBO readback return deterministic zero-filled bytes.
- Swap pacing prevents an unbounded render loop.
- One-hour run: no deadlock, context loss, unbounded CPU spin, or monotonic memory growth.

## G2 - Unity 2022.3.62f3 IL2CPP contract

Required behavior:

- PlayerLoop, `Update`, `FixedUpdate`, `WaitForEndOfFrame`, UI layout, animation state, scene transitions, and app pause/resume continue.
- RenderTexture and AsyncGPUReadback requests complete or fail explicitly; they never wait forever.
- Semantic markers and UI hierarchy continue changing without pixel rendering.
- CPU/RSS are measured against the same-host software-rendering baseline.

## G3 - Observer contract

Required behavior:

- The ANGLE-loaded process component can discover the pinned `libil2cpp.so` across Android linker namespaces.
- Unity object snapshots execute through a proven main-thread-safe rendezvous.
- The protocol exposes allowlisted typed snapshots only; it has no arbitrary IL2CPP invocation endpoint.
- Snapshot generation, scene generation, freshness, package foreground state, and version fingerprint are mandatory action gates.

## G4 - Game closed loop

Required behavior on a test account:

- Reach login and main UI without pixel evidence.
- Observe stable semantic/Lua state changes across a harmless page transition.
- Validate hit bounds from RectTransform world corners and verify the top EventSystem raycast target.
- Enter and return from one side-effect-free page.

## G5 - Task-specific ALAS vertical slices

Each task flow is gated independently; one passing flow does not enable another.

### G5a - Mission no-claim branch: passed

Required behavior:

- The observer evaluates top EventSystem raycast identity only for exact
  `TaskScene` back/`GetAllButton` paths and task-list content-row
  `get_btn`/`go_btn` shapes. The controller accepts only exact numeric row
  indexes as mission state.
- Mission classification remains identical across at least two increasing
  snapshot generations. Absence of claim Buttons is never treated as an empty
  page unless an independently reviewed marker exists.
- The pinned, opt-in ALAS `Reward.reward_mission()` hook enters through the
  exact main task Button, proves unfinished rows, exits through the exact task
  back Button, and proves the main task Button returned.
- The no-claim run injects no `get_btn` or `GetAllButton` input. Unknown,
  ambiguous, loading, clipped, or blocked state fails closed.

### G5b - Mission claim-all branch: controlled pass

Required behavior:

- Capture a live page containing `GetAllButton` or a numeric-row `get_btn`.
- Require the exact unique `GetAllButton`, top-raycast proof, and a separate
  explicit claim opt-in.
- Map the exact `AwardInfoUI` close target, require its top-raycast proof, and
  reject every other popup.
- Inject exactly one claim input, close the reward popup, prove claim rows
  disappeared across stable increasing generations, return to main, and
  independently recheck the no-claim branch.

This pass does not enable numeric-row claiming or tab traversal.

The live G5a/G5b evidence predates the later ownership refactor that returns
control to ALAS's original reward state machine. That new wiring must complete
a separate live revalidation before it inherits the pass.

## G6 - Typed UI and mission sidebar: scoped pass

- `GET /v1/ui` exposes bounded Toggle, UGUI Text, TextMesh Pro, and Image
  records without a generic managed invocation surface.
- Typed OCR is fail-closed on missing, ambiguous, truncated, malformed,
  out-of-bounds, or alphabet-invalid text.
- The six reviewed task-sidebar Images require exact sprite identity and native
  EventSystem top-raycast proof before input.
- A live adapter-level loop selected weekly, proved its selected sprite,
  returned to all, and exited to main. It did not click a reward control.
- The complete ALAS-owned reward state machine, positive red-dot state,
  weekly-only execution, and numeric-row claims remain separate open gates.

See [G6 typed semantic UI validation](g6-semantic-ui-report.md).

## G7 - Typed task surfaces and read-only campaign: scoped pass

- Exact typed state covers reward counters, commission rows/empty state,
  tactical slots/countdowns, research cards, construction pool/cost, dorm
  summary, and visible campaign chapter/stage labels.
- Only reviewed navigation, reward receipt, safe popup cancel/close, and page
  return controls may be injected. Every action requires exact path, active and
  interactable state, coherent fresh generations, foreground/package identity,
  bounds, and native top EventSystem raycast proof.
- ALAS retains state-machine ownership. Semantic mode replaces reviewed
  observation/OCR inputs and rejects raw coordinate, gesture, unknown popup,
  and generic reused-button fallbacks.
- Construction submission, commission selection/start, tactical assignment,
  research selection/start, dorm mutation, stage selection, map movement,
  sortie, battle, and Lua state remain separate gates.

See [G7 typed task and campaign adaptation](g7-task-campaign-adaptation-report.md).

## G8 - Real ALAS reward and one-budget commission start: scoped pass

- The pinned upstream ALAS reward command must complete twice with semantic
  observations and zero claim inputs.
- Commission must first complete with start budget zero and no row-selection or
  start input.
- A controlled start requires an exact pending row/detail signature, assigned
  ships, zero oil cost, an independent integer budget, and a typed transition
  to a lower countdown plus the reviewed `tag_ongoing` marker.
- A second zero-budget run must parse the running commission, schedule from its
  typed countdown, and start no additional row.
- Commission rewards, nonzero-oil rows, larger start budgets, scrolling,
  cancellation, and unattended repetition remain separate gates.

See [G8 real ALAS validation](g8-alas-reward-commission-validation-report.md).

## G9 - Bounded task inputs: three full command replays passed

- Keep the original ALAS Tactical, Research, Dorm, and Gacha state machines;
  replace only reviewed image/OCR/input ports with typed semantic state.
- Qualify read-only research selection, one research start, research queue and
  reward I/O, tactical course assignment, dorm collect/feed, and one
  construction submit under independent default-zero integer budgets.
- Revalidate visual identities immediately before input and spend each budget
  only on its exact mutation boundary. Food input must target the food card,
  and construction must prove count and resource costs at final confirmation.
- Feed original ALAS `Navbar` and queue primitives exact Toggle/capacity/timer
  state. Refuse pre-existing nonempty construction queues rather than
  accelerating or collecting them.
- Adapter-level live passes and clean pinned-patch application are required.
  Tactical, Research, and Dorm must also complete their original patched ALAS
  commands. Gacha must keep warning preparation and final-order confirmation
  disjoint; its corrected full replay remains pending an empty queue after the
  first live attempt submitted one bounded order at the wrong ALAS phase.

## G10 - Campaign pre-sortie: bounded reversible pass

- Keep ALAS's original campaign navigation, chapter selection, stage lookup,
  enter-map, and enter-map-cancel loops. Replace their reviewed OCR/template
  observations and input endpoints with typed semantic state.
- Default stage-entry budget to zero. A value of one admits exactly one exact
  stage input and does not authorize a second stage, sortie, or map input.
- Prove exact `12-4` map preparation, allow its single-use proceed input, prove
  exact fleet preparation, and permit only its exact cancel input.
- Require increasing entry/cancel/restoration generations and the same restored
  chapter/stage identity. Transition grace must be receipt-bound and finite.
- Keep the fleet sortie Button outside both the native raycast allowlist and
  adapter click map. Map movement, combat, and rewards remain separate gates.
- Require a full patched ALAS command pass, final `IN_MAP=False`, clean pinned
  patch application, patched-file hash equality, and controller tests.

See [G10 campaign pre-sortie validation](g10-campaign-pre-sortie-validation-report.md).

## G11 - Campaign fleet preparation: bounded reversible pass

- Keep ALAS's original `FleetPreparation` and `FleetOperator` state machines;
  replace only their reviewed observation and exact input endpoints.
- Type the three fleet rows, selected fleet identities, ship levels, capacity
  counters, oil costs, and all six exact fleet-option Toggles.
- Default the independent fleet-mutation budget to zero. Before any fleet
  input, simulate ALAS's exact branch order and require enough budget for the
  complete ordered mutation plan.
- Count each real clear or fleet-option selection as one mutation. Dropdown
  navigation and an idempotent clear of an already empty row consume no
  mutation unit and inject no unnecessary input.
- Require the prepared fleet selection to match configuration, then cancel
  through ALAS's original loop and prove the original selection, chapter,
  stage set, and `IN_MAP=False` were restored.
- Keep hard-mode restriction lines, formation-layout changes, sortie, map
  movement, battle, and rewards outside this gate.
- Require budget-zero and exact positive-budget full ALAS commands, native
  build guards, clean pinned-patch application, patched-file hash equality,
  controller tests, and an independent post-cancel typed read.

See [G11 campaign fleet-preparation validation](g11-campaign-fleet-preparation-validation-report.md).

## G12 - Campaign sortie: one exact bounded pass

- Keep ALAS's original fleet-preparation, settings, sortie, and map-entry
  loops; authorize only its existing sortie click.
- Default an independent sortie budget to zero and qualify only exact value
  one. Revalidate normal mode, requested fleets, auto-search/2x settings,
  submarine mode, fleet order, oil, and the unique sortie target immediately
  before input.
- Require a later exact real `LevelGrid` map identity and stop without grid,
  movement, combat, retreat, or reward input.
- Keep repeated sorties and every map action outside this gate.

See [G12 campaign sortie validation](g12-campaign-sortie-validation-report.md).

## G13 - Campaign map model: read-only live pass

- Take map shape, land topology, and enabled fleet count from ALAS's loaded
  `CampaignMap`; do not duplicate its state machine or map definition.
- Require a complete Button topology equal to ALAS passable cells and complete
  non-truncated Image/Text collections for all dynamic objects.
- Type only reviewed enemy, ammunition-pickup, fleet-ammo, and fleet-anchor
  identities. Unknown attachments, malformed state, missing anchors, or
  ambiguous locations fail closed.
- Match fleet ancestors to grid Buttons through Unity world position, and
  require an unchanged logical model across two increasing generations.
- Feed the model to ALAS only at its existing already-in-map checkpoint and
  return before retreat. Expose no map input and pass a zero-budget ALAS replay
  with an input-rejecting assertion installed.

See [G13 campaign map-model validation](g13-campaign-map-model-validation-report.md).

## G14 - Read-only ALAS map synchronization and planning

- Validate the complete semantic state against ALAS's loaded stage, shape,
  land/passable topology, and static enemy/ammunition capabilities before
  mutating a shadow map.
- Reuse ALAS's native `CampaignMap`, `GridInfo`, `map_data_init()`, and path
  calculation; do not recreate its map state machine in the adapter.
- Produce deterministic per-marker enemy/ammunition reachability summaries,
  then clear temporary path state.
- Keep semantic marker-to-fleet-index identity unresolved until independently
  proven. Leave ALAS indexed fleet locations empty and expose no grid input.
- Do not call `map_control_init()`, scanning, fleet switching, movement,
  battle, retreat, or rewards.
- Require unit rollback coverage, a pinned real-ALAS-object qualification,
  clean canonical patch application, and an evidence-scoped live-blocker
  disclosure when a same-process replay cannot run.

See [G14 ALAS map synchronization validation](g14-alas-map-sync-validation-report.md).

## G15 - Passive fleet-index reconciliation

- Type the exact displayed fleet number and complete displayed-fleet ship
  sprite roster without adding new observer invocation capabilities.
- Require exactly one map fleet marker suffix to match exactly one displayed
  roster sprite across two increasing stable generations.
- If a fighting enemy exists, require the current fleet to occupy its node.
- Reuse ALAS's normal/reversed `fleet_show_index -> fleet_current_index` rule,
  then populate native indexed fleet locations and `is_current_fleet`.
- Keep `map_control_init()`, fleet switching, grid movement, battle, retreat,
  and rewards closed.
- Require ambiguous/missing/fighting-mismatch negatives, both pinned ALAS
  fleet-order cases, a live passive identity sample, and explicit disclosure
  when an overlay blocks the complete live model.

See [G15 fleet-index validation](g15-campaign-fleet-index-validation-report.md).

## G16 - Original ALAS campaign decision preview

- Feed the indexed native shadow map into ALAS's original
  `find_path_initial()` and `battle_function()`; do not reproduce campaign
  branch or target-selection logic in the semantic layer.
- Preserve class-level `MAP` grid identity so campaign `RoadGrids` see the
  projected state, and restore every map/grid dictionary transactionally.
- Capture and abort the first public `goto()` admission. Record branch, battle
  count, logical fleet/marker, origin, target kind/node, expected result, cost,
  full route, and native goto nodes.
- Reject stale projections, non-semantic targets, route disagreements, Device
  access, fleet switching, `_goto()`, combat, retreat, timed waits, and branches
  that return without a decision.
- Require a pinned real-ALAS qualification, exact rollback assertions, clean
  canonical patch application/matching, and explicit disclosure when the live
  map is blocked.

See [G16 ALAS campaign decision preview](g16-alas-campaign-decision-preview-validation-report.md).

## G17 - Decision-bound campaign combat admission

- Bind ALAS's immutable decision signature to the same stable semantic map
  object and require an exact normal `combat` against one `fighting` enemy.
- Admit only the smallest zero-distance slice: current fleet, enemy, origin,
  target, native route, and native goto nodes must all identify the same cell;
  fleet-step movement, bosses, pickups, portals, fleet switching, and positive
  path cost remain closed.
- Give campaign combat an independent canonical integer budget that defaults
  to zero and requires exactly one unit for this slice.
- Re-read the exact cell Button before input and require unchanged Unity path,
  point, bounds, active/enabled/interactable state, top EventSystem raycast,
  foreground package, screen bounds, and no global blocker.
- Consume the budget immediately after the ADB tap, before validating its
  receipt, so an anomalous post-input result cannot replay the action.
- Accept only ALAS `_goto()`'s explicit global-location annotation at the
  existing `device.click(grid)` boundary; do not expose generic coordinates or
  a second movement implementation.
- Define the postcondition as ALAS battle count `+1`, exact target object
  removal, current fleet still on the target, ammunition `-1`, stable topology,
  and a newer complete map generation.
- Keep the patched campaign runner stopped after admission preflight until the
  original `_goto()`/combat observation closure is qualified. A positive
  budget therefore proves readiness but injects no live input in G17.

See [G17 campaign combat admission](g17-campaign-combat-admission-validation-report.md).

## Stop or pivot conditions

- A critical flow depends on rendered GPU results rather than completion signaling.
- A readback dependency closure approaches full-scene rendering.
- Main-thread-safe snapshots require fragile per-build code hooks with no reliable fingerprint gate.
- NULL mode provides no operational CPU/RSS advantage over SwiftShader.
- Compatibility requires concealment or anti-detection bypass.
