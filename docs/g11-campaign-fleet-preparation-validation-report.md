# G11 bounded campaign fleet-preparation validation

Date: 2026-08-10

## Outcome

G11 passes the reviewed normal-mode fleet-selection slice on
`emulator-5580`. The pinned ALAS campaign command retained its original
`FleetPreparation.fleet_preparation()` and `FleetOperator` loops, reconciled
the live selection `(1, 2, 1)` to the configured `(1, 2, 0)`, and then used
ALAS's existing `enter_map_cancel()` loop. The complete command returned:

```text
ALAS_G11_FLEET_BUDGET3_FINAL True
```

The three budget-consuming inputs were exactly:

```text
campaign/fleet-preparation/fleet/2/clear
campaign/fleet-preparation/submarine/1/clear
campaign/fleet-preparation/option/2
```

The fleet sortie `start_button` remains outside the native raycast allowlist
and adapter click map. G11 does not authorize formation-layout changes,
sortie, map movement, combat, or rewards.

## ALAS ownership boundary

The patch does not implement a replacement fleet state machine. It calls
ALAS's original `self.fleet_preparation()` from the existing pre-sortie safety
checkpoint. The following ALAS behavior remains unchanged:

- hard-mode checks and the normal-mode branch order;
- submarine allowance and clearing logic;
- fleet clear/open/selected/close/click retry loops and timers;
- `ensure_to_be()` and its forced fleet-2 reselection;
- the final `enter_map_cancel()` loop.

Semantic mode replaces only the observation and input endpoints used by those
loops. An exception at any fleet step enters nested `finally` rollback: an
open dropdown is closed without changing selection, then
`enter_map_cancel()` is attempted. The safety checkpoint stops before the
original later `self.device.click(FLEET_PREPARATION)` line.

## Typed fleet model

The closed fleet panel requires exact typed state for:

- surface rows `fleet/1` and `fleet/2`;
- submarine row `sub/1`;
- each row's exact select and clear Button;
- selected fleet name, ship icon count, and numeric ship levels;
- surface/submarine selected-capacity counters;
- mob, boss, and submarine oil costs;
- the observation-only sortie Button and exact cancel Button.

The reviewed row inputs are:

```text
LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/btn_select
LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/btn_clear
LevelFleetSelectView(Clone)/panel/ShipList/fleet/2/btn_select
LevelFleetSelectView(Clone)/panel/ShipList/fleet/2/btn_clear
LevelFleetSelectView(Clone)/panel/ShipList/sub/1/btn_select
LevelFleetSelectView(Clone)/panel/ShipList/sub/1/btn_clear
```

The dropdown requires all six exact Toggle paths `mask/list/item1` through
`item6`. Selected indices come from each Toggle's active `on`/`off` numeric
child, not its unreliable checked flag. Every admitted input is revalidated as
the unique top EventSystem raycast target immediately before ADB input.

## Budget and proof contract

`ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET` is a canonical non-negative
integer and defaults to `0`. It is independent of the stage-entry budget.

Before the first fleet input, the adapter simulates the original ALAS branch
order against the complete typed initial state. It computes the exact semantic
mutation sequence and rejects an insufficient budget before any fleet input.
During execution, each real clear or option selection consumes one unit. The
final proof requires both the mutation count and ordered semantic IDs to equal
the preflight plan and requires the prepared typed selection to equal the
configuration.

Opening or closing a dropdown does not consume a mutation unit. An idempotent
ALAS clear on an already empty reviewed row is observation-only and injects no
ADB input. Hard mode remains closed because its fleet restriction lines are
not yet typed.

The final artifact produced two complete command results:

- fleet budget `3`: `(1, 2, 1) -> (1, 2, 0)`, exact three-input sequence,
  cancel/restoration generations `944 -> 951`;
- fleet budget `0`: no fleet input, pre-sortie proof
  `1220 -> 1237 -> 1245`, result
  `ALAS_G11_FINAL_ARTIFACT_BUDGET0 True`.

The fleet preparation view is transactional. An independent post-pass check
observed chapter generation `1039`, re-entered fleet preparation, and found
the canceled selection restored to `(1, 2, 1)` at generation `1051`. It
canceled again and observed the same chapter/stage set at generation `1057`
with `IN_MAP=False`.

## Transition and long-session hardening

Live evidence exposed two bounded observation issues:

- the six Toggle records can appear up to two generations before the dropdown
  mask Button;
- fleet icon and level text children settle in separate animation frames.

The oracle now retries only the complete read-only view: up to two seconds for
the dropdown and three seconds for the closed fleet panel. The final attempt
must still satisfy every original completeness, coherence, identity, and
raycast check; no input is injected by a retry.

Repeated Unity overlays also retained enough destroyed Image components to
fill the native 512-identity liveness scratch buffer. The final observer raises
only that temporary collector to 1024 so destroyed objects can be filtered.
The active typed Image record limit remains 256, and `image_truncated` still
fails closed. The final fleet read reported no Image truncation.

## Live incidents and side effects

- An initial G4 startup probe sampled a zero-Button Unity scene and stopped on
  its old `semantic-button-record-incomplete` requirement. It injected no
  input.
- One cold start stopped swapping at generation `168` during hot-update load.
  The stale observer was rejected and the game was restarted.
- Login required the reviewed account/server entry phases across cold starts,
  followed by the exact bulletin close. No new login reward was observed.
- One exact `[NetworkDown]` reconnect prompt was handled by the already
  reviewed semantic target before a diagnostic run.
- Development attempts failed closed on the dropdown mask race and on
  incomplete/truncated fleet typed state. Their nested rollback canceled the
  preparation layer. A later independent read proved the original fleets were
  restored.
- ADB screenshots remained black under NULL. Campaign and fleet decisions
  came from typed observer state; screenshots were not used as a fallback.

No sortie, map movement, combat, or campaign reward input was injected.

## Verification

- Controller suite: `217 passed`.
- Final observer APK:
  `artifacts/AngleLibraries-g11-fleet-prep.apk`.
- APK SHA-256:
  `29f49a33318321b1c38fa2e590879701159d6404beabfe59af54a2fccb6ef91f`.
- Driver revision:
  `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Package: `com.bilibili.azurlane`.
- The 22-file canonical ALAS patch passes clean `git apply --check` against
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- All 22 patched Python files compile and match the clean-applied validation
  worktree by SHA-256.

## Remaining boundary

The next campaign phase is sortie confirmation as a separate default-closed
contract. It should first type fleet validity, oil/resource preconditions,
auto-search and submarine settings, then admit at most one exact sortie input
with a postcondition that proves map entry. Map parsing, fleet movement,
combat entry, battle decisions, battle input, rewards, and repeated unattended
runs remain independent later gates.
