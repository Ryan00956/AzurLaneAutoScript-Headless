# Acceptance gates

Status terms are deliberately strict. A build passing does not imply a later gate has passed.

Current status: G1-G4, G5a, controlled G5b, scoped G6-G8, and the G9 bounded
adapter slices passed. G4 includes login/main reachability, sustained semantic
state, RectTransform bounds, top EventSystem raycast identity for each action,
and a settings-page return loop. G5a covers only the ALAS mission-reward
no-claim branch. G5b covers one `GetAllButton` claim on the default task page.
G6-G8 add typed UI/task observation and real bounded Reward/Commission passes.

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

## Stop or pivot conditions

- A critical flow depends on rendered GPU results rather than completion signaling.
- A readback dependency closure approaches full-scene rendering.
- Main-thread-safe snapshots require fragile per-build code hooks with no reliable fingerprint gate.
- NULL mode provides no operational CPU/RSS advantage over SwiftShader.
- Compatibility requires concealment or anti-detection bypass.
