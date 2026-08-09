# ALAS integration overlay

Target: upstream commit `81ccf63b4540f00241628c82a58c02c7a2bb11af`.

The patch adds opt-in observation and action ports without changing default
ALAS behavior:

- `ModuleBase.appear()` routes named resources to the semantic adapter.
- `ModuleBase.match_template_color()` and `image_color_count()` route the
  remaining reward-state observations to the same adapter.
- `Control.click()` routes mapped clicks to the observer-derived ADB point.
- Raw multi-click, long-click, swipe, drag, and low-level click dispatch are
  rejected while semantic mode is active.
- `Reward.reward_mission()` only brackets one adapter context. The original
  ALAS reward state machine, including its timers, retries, collection loop,
  popup receive loop, and daily/weekly branch ordering, remains the owner.

The adapter is deliberately incomplete. Reviewed main-page aliases and the
explicit mission virtual resources are accepted. Unknown actions, including
the widely reused `BACK_ARROW`, always raise `AlasSemanticUnmapped`. During the
ALAS mission context, unrelated presence checks may return false only while an
independently proven main/task/reward surface exists; otherwise they also
raise. The adapter never falls back to a black screenshot or an asset's old
rectangle.

Mapped presence/clicks also require the observer's top EventSystem raycast
result to belong to the mapped Button. Active/interactable state and bounds
alone are insufficient.

The mission input provider is narrower than normal ALAS reward handling. It
translates ALAS's `MISSION_MULTI`, `MISSION_SINGLE`, `MISSION_UNFINISH`, page,
reward-popup, and default-navbar observations from typed Unity snapshots. It
requires the same mission signature across two increasing generations before
reporting a claimable or unfinished state. The provider maps the exact
`GetAllButton` and reviewed `AwardInfoUI` close actions back into ALAS's normal
claim/click/receive loop. Claim input remains disabled by default even when
`GetAllButton` is present.

One controlled claim-all per `reward_mission()` invocation is available only
with a second explicit opt-in:

```powershell
$env:ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE = '1'
```

The adapter resets a one-input claim budget when ALAS enters
`Reward.reward_mission()` and discards it in `finally`. The claim action still
requires the unique actionable `GetAllButton`; ALAS then owns the popup receive
loop while `GET_ITEMS_1`/`GET_ITEMS_2` are translated to exactly one reviewed
`AwardInfoUI`/`AwardInfoUI1` close target. Without this variable, ALAS may
observe the claimable state but the first claim action fails closed before ADB
input.

The typed observer does not yet expose the mission red-dot Image. In semantic
mode, an explicitly scheduled daily run uses the proven main task object as
permission to inspect the default task page. The default sidebar state
is accepted only after that exact entry click and a proven `TaskScene` page.
Weekly-only runs, weekly-tab input, numeric-row claiming, ship-reward popups,
and empty-page inference remain closed.

To stage this against a compatible ALAS checkout:

```powershell
git apply --check H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
git apply H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
$env:PYTHONPATH = 'H:\program\AzurLaneAutoScript-Headless\python'
$env:ALAS_SEMANTIC_MODE = '1'
$env:ALAS_SEMANTIC_DRIVER_REVISION = (Get-Content H:\program\AzurLaneAutoScript-Headless\ANGLE_REVISION -Raw).Trim()
```

Do not enable unattended ALAS operation yet. The earlier default-page probe
proved the semantic no-claim and one controlled claim-all primitives. The new
ALAS-owned state-machine wiring has unit, syntax, lifecycle, and pinned-patch
application coverage, but still needs a fresh live no-claim/claim revalidation.
Numeric-row claiming, weekly-tab traversal, campaign maps, battle state, other
reward popups, scroll/drag semantics, and all other task flows remain
fail-closed.
