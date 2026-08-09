# ALAS integration overlay

Target: upstream commit `81ccf63b4540f00241628c82a58c02c7a2bb11af`.

The patch adds four opt-in hooks without changing default ALAS behavior:

- `ModuleBase.appear()` routes named resources to the semantic adapter.
- `Control.click()` routes mapped clicks to the observer-derived ADB point.
- Raw multi-click, long-click, swipe, drag, and low-level click dispatch are
  rejected while semantic mode is active.
- `Reward.reward_mission()` routes to the reviewed mission semantic flow before
  any image matching is attempted.

The adapter is deliberately incomplete. Only the reviewed main-page aliases in
`alas_headless.alas_adapter.DEFAULT_ALAS_BUTTON_TARGETS` are accepted. Any other
resource, including the widely reused `BACK_ARROW`, raises
`AlasSemanticUnmapped`; it never falls back to a black screenshot or an asset's
old rectangle.

Mapped presence/clicks also require the observer's top EventSystem raycast
result to belong to the mapped Button. Active/interactable state and bounds
alone are insufficient.

The mission hook is narrower than normal ALAS reward handling. It may dismiss
only the exact reviewed bulletin or guild-message close Button, enter the exact
main task Button, require a stable `TaskScene` classification over two
increasing generations, and return through the exact task back Button. A live
no-claim page with five `go_btn` rows passed. Claim input remains disabled by
default even when `GetAllButton` is present.

One controlled claim-all per `reward_mission()` invocation is available only
with a second explicit opt-in:

```powershell
$env:ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE = '1'
```

That branch requires the unique actionable `GetAllButton`, waits for exactly
one reviewed `AwardInfoUI`/`AwardInfoUI1` close target, closes it, proves the
post-claim page is stably unfinished with no claim rows, and returns to main.
The live validation changed three claim rows to zero with exactly one claim
input. Without this variable, a claimable state first returns to main and then
raises `MissionClaimableDetected`.

To stage this against a compatible ALAS checkout:

```powershell
git apply --check H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
git apply H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
$env:PYTHONPATH = 'H:\program\AzurLaneAutoScript-Headless\python'
$env:ALAS_SEMANTIC_MODE = '1'
$env:ALAS_SEMANTIC_DRIVER_REVISION = (Get-Content H:\program\AzurLaneAutoScript-Headless\ANGLE_REVISION -Raw).Trim()
```

Do not enable unattended ALAS operation yet. The default task page's no-claim
and one controlled claim-all closure have evidence; numeric-row claiming,
weekly-tab traversal, campaign maps, battle state, other reward popups,
scroll/drag semantics, and all other task flows remain fail-closed.
