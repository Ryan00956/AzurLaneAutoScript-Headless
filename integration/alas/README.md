# ALAS integration overlay

Target: upstream commit `81ccf63b4540f00241628c82a58c02c7a2bb11af`.

The patch adds three opt-in hooks without changing default ALAS behavior:

- `ModuleBase.appear()` routes named resources to the semantic adapter.
- `Control.click()` routes mapped clicks to the observer-derived ADB point.
- Raw multi-click, long-click, swipe, drag, and low-level click dispatch are
  rejected while semantic mode is active.

The adapter is deliberately incomplete. Only the reviewed main-page aliases in
`alas_headless.alas_adapter.DEFAULT_ALAS_BUTTON_TARGETS` are accepted. Any other
resource, including the widely reused `BACK_ARROW`, raises
`AlasSemanticUnmapped`; it never falls back to a black screenshot or an asset's
old rectangle.

Mapped presence/clicks also require the observer's top EventSystem raycast
result to belong to the mapped Button. Active/interactable state and bounds
alone are insufficient.

To stage this against a compatible ALAS checkout:

```powershell
git apply --check H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
git apply H:\program\AzurLaneAutoScript-Headless\integration\alas\0001-semantic-oracle-hooks.patch
$env:PYTHONPATH = 'H:\program\AzurLaneAutoScript-Headless\python'
$env:ALAS_SEMANTIC_MODE = '1'
$env:ALAS_SEMANTIC_DRIVER_REVISION = (Get-Content H:\program\AzurLaneAutoScript-Headless\ANGLE_REVISION -Raw).Trim()
```

Do not enable an ALAS task yet. The current mapping proves controller plumbing
and the harmless main/settings loop only; campaign maps, battle state, popups,
scroll/drag semantics, and task-specific buttons remain unmapped.
