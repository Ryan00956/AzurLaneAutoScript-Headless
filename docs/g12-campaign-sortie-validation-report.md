# G12 bounded campaign sortie validation

Date: 2026-08-10

## Outcome

G12 qualifies one normal-mode `12-4` sortie as a separate, default-closed
contract. The pinned ALAS command still owns campaign navigation, map and fleet
preparation, fleet selection, settings, timers, retries, and the original
`self.device.click(FLEET_PREPARATION)` call. Semantic mode supplies the typed
observations and admits that existing call only after exact fleet, settings,
oil, target, and budget preconditions pass.

The live qualification is deliberately reported as split evidence rather than
as a clean same-process success line:

- the final budget-zero replay reconciled `(1, 2, 1) -> (1, 2, 0)`, canceled,
  and returned `ALAS_G12_SORTIE_BUDGET0_FINAL True` without sortie input;
- the budget-one replay injected exactly one
  `campaign/fleet-preparation/sortie` input at `2026-08-10 11:20:51.703`;
- the first map proof used an incorrect hypothetical `LevelScene(Clone)` root
  and failed closed; no second input was injected;
- after observer hardening and process restarts, the server restored the same
  live `12-4` map. A final read at generation `3103` proved the real map root
  `LevelCamera/Canvas/UIMain/LevelGrid`, 70 reviewed map Button paths, three
  fixed Image/sprite anchors, and `IN_MAP=True`.

No fleet movement, grid click, combat input, retreat, or reward input was
injected. A second sortie was not manufactured merely to obtain a cleaner log.

## ALAS ownership boundary

The integration does not implement a replacement sortie state machine. Inside
ALAS's existing `enter_map()` loop it:

1. calls the original `self.fleet_preparation()`;
2. retains the original 2x-book, submarine-call, auto-search, fleet-order, and
   selection handlers;
3. authorizes the existing `self.device.click(FLEET_PREPARATION)` call;
4. continues the original `self.is_in_map()` loop;
5. stops with `ScriptEnd` immediately after the read-only map proof.

Once semantic map preparation has been committed, an observation generation
that is between two reviewed preparation surfaces cannot fall through to the
unmodified later fleet/sortie input branches. Earlier ALAS navigation and
recovery states still fall through normally.

## Budget and preconditions

`ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET` is a canonical non-negative integer and
defaults to `0`. The only qualified positive value is exactly `1`; larger
values fail before input. It is independent of the stage-entry and fleet
mutation budgets.

The positive preflight requires all of the following from exact typed state:

- normal mode and requested fleets `(1, 2, 0)`;
- non-empty surface fleet 1 and 2 rows and an empty submarine row;
- surface/submarine capacity summaries `(2, 2)` and `(0, 1)`;
- auto-search disabled and 2x-book disabled;
- submarine mode `do_not_use`;
- order `fleet1_mob_fleet2_boss`;
- oil captured before the stage click and at least the typed mob plus boss oil
  costs;
- the unique actionable sortie Button at
  `LevelFleetSelectView(Clone)/panel/Fixed/start_button`.

The sortie input spends the sole budget unit and records its exact generation.
Confirmation requires a later map generation; no map input is exposed by the
proof.

## Real map identity

The pinned game does not create the assumed `LevelScene(Clone)` UGUI root. The
reviewed `12-4` map identity instead requires all three independent families:

- exact map controls
  `LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat` and
  `OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/top_stage/back_button`;
- at least one exact grid Button matching
  `LevelGrid/DragLayer/plane/quads/chapter_cell_quad_<row>_<column>`;
- exact Image/sprite pairs for `reteat_popo`, `sea_day`, and `back_btn` at
  their fixed map paths.

All preparation Button and Text roots must be absent. The real map has more
than 256 active Images, so `image_truncated=True` is expected. The gate uses
only positive exact Image anchors and proves preparation absence from the
complete, non-truncated Button and Text slices; it never infers absence from a
truncated Image list.

## Observer hardening

The initial map attempt exposed a native safety defect. Repeated
`il2cpp_unity_liveness_calculation_from_statics` calls recursively traversed
the map's large static object graph and the Unity process later terminated with
a stack-overflow-shaped SIGSEGV. This was an observer failure, not an ALAS or
game-state transition.

The final observer no longer executes recursive static-root liveness
enumeration. It uses Unity's `Resources.FindObjectsOfTypeAll(Type)` to obtain
the four reviewed component families, copies only a bounded 1024-object
identity slice, and preserves all existing typed parsing and API schemas.
Complete typed snapshots are sampled every three rendered frames, about 10 Hz
on this guest. That remains well inside the freshness gate, bounds work on map
scenes, and keeps sequential Button/UI endpoint reads generation-coherent.

The final observer remained alive and fresh on the recovered map well beyond
the earlier approximately 36-second failure window.

## Verification

- Relevant controller/integration suite: `220/220` passed.
- Final observer APK:
  `artifacts/AngleLibraries-g12-sortie-safe.apk`.
- APK SHA-256:
  `7481e25e6a5d51e05101b55befdd331a051b76181819fe80ce676b7c26bbb38a`.
- Driver revision:
  `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Package: `com.bilibili.azurlane`.
- The native observer rebuild passed with the non-recursive enumeration and
  bounded cadence guards.
- The canonical ALAS patch applies to pinned upstream commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af` and retains ALAS's original
  campaign state-machine calls.

## Remaining boundary

G12 proves arrival only. Map parsing, fleet localization, read-only map model,
movement planning, grid input, combat entry, battle decisions, battle input,
post-battle rewards, retreat, and repeated unattended sorties remain separate
later gates. The next safe slice should be a read-only map model with no grid
input budget.
