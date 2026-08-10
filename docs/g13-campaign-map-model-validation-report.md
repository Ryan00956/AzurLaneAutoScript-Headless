# G13 read-only campaign map model validation

Date: 2026-08-10

## Outcome

G13 passes the read-only `12-4` map-model slice. The pinned ALAS campaign
state machine remains the owner of navigation, fleet preparation, sortie,
future movement, combat, recovery, and rewards. Semantic mode changes only
the already-in-map observation boundary: ALAS supplies its own map shape,
land topology, and enabled fleet count, receives one complete typed model,
logs it, and returns before the upstream retreat branch.

The live model reported:

- map shape `11x8`;
- `68` passable cells and the exact `20` ALAS land cells;
- fleets `cell_fleet_shengwang_younv @ D6, 5/5` and
  `cell_fleet_ying @ F8, 5/5`;
- enemies `enemy_1204050 @ C6, zl1, Main, Lv.113` and
  `enemy_1204090 @ D6, hm1, Carrier, Lv.113, fighting`;
- the `event4` ammunition pickup at `F2`.

No map Button is mapped as an input. The live direct model read and the final
ALAS replay both replaced the oracle tap function with a rejecting assertion;
both completed without calling it. Grid movement, combat, retreat, reward,
and a repeated sortie remain closed.

## ALAS ownership boundary

The canonical patch adds one branch at the existing
`if self.campaign.is_in_map()` checkpoint in `CampaignRun`. In semantic mode
that branch:

1. reads `shape`, `is_land`, and configured fleet enablement from the loaded
   ALAS `CampaignMap`;
2. calls `semantic_adapter.campaign_map_state(...)`;
3. logs the stable map summary;
4. returns `True` before ALAS's existing `withdraw()` path.

Default ALAS behavior is unchanged when semantic mode is absent. The patch
does not copy ALAS movement, battle, retreat, or reward logic into the
adapter. The map model is context-bound to the normal-mode campaign flow and
rejects calls made without an active canonical stage context.

## Complete typed model contract

The observer produced one complete generation with `92` Buttons, `300`
Images, and `55` Text records; all three collections reported zero truncation.
The model then required the same logical result across two increasing
generations.

Static topology is not inferred from visible pixels. Every active
`chapter_cell_quad_<row>_<column>` Button must be unique, bounded, and inside
the ALAS-provided shape. Its complete coordinate set must equal all shape
coordinates minus ALAS's zero-based `is_land` set. Missing, duplicate,
out-of-shape, malformed, or extra passable coordinates fail closed.

Dynamic attachments are allowlisted from complete Image/Text paths:

- enemy icons accept only `qx|zl|hm` plus scale `1..3`, an exact numeric level
  and `Lv.` label, and an internally consistent optional `xingdongzhong` /
  `行动中` pair;
- the only qualified pickup is exact sprite `event4` under the reviewed
  supply path;
- any other visible attachment root fails closed.

Fleet ammunition requires one exact `ammo/bg` Image with sprite
`danyao_bar` and one canonical `current/capacity` Text. The inactive shadow of
the second fleet is deliberately not used.

## Fleet world-position anchor

The native observer now walks only the bounded Transform ancestry of active
Images. When it finds a `cell_fleet_*` ancestor, it exports that ancestor's
Unity world position as additive field `anchor_world_position`. Each grid
Button already exposes its own `world_position`.

The model matches each fleet anchor to exactly one passable grid position with
a maximum three-dimensional distance of `0.05`, rejects an ambiguous nearest
cell, and rejects two fleets occupying the same modeled node. On the live
map, both matches were exact after JSON rounding:

| Fleet | Anchor | Cell | Distance | Next cell |
| --- | --- | --- | ---: | ---: |
| `cell_fleet_ying` | `(1.117, -2.462, -178.243)` | `F8` | `0.000` | `1.528` |
| `cell_fleet_shengwang_younv` | `(-1.940, -0.301, -176.082)` | `D6` | `0.000` | `1.528` |

This removes the earlier screen-offset guess and correctly represents the
fighting fleet and enemy sharing `D6`.

## Live qualification

Installing the new observer restarted the game, so one additional bounded
sortie was used to recreate the map. Login, bulletin close, and exact
`[NetworkDown]` reconnect prompts were handled only through reviewed semantic
targets. The campaign invocation used independent budgets `1 / 3 / 1` for
stage entry, fleet reconciliation, and sortie, with fleets `(1, 2, 0)`,
auto-search disabled, 2x disabled, and the reviewed fleet order.

The controlled invocation reached the real map and then failed closed when a
generic ALAS page scan asked for unmapped `POPUP_CONFIRM_WHITE`. That failure
occurred after map arrival and did not authorize a map input. It is not used
as the final success claim.

The final proof started on the stable map with all three campaign budgets set
to zero. ALAS logged:

```text
Semantic campaign map model: 12-4, 11x8, cells=68, land=20,
fleets=['D6', 'F8'], enemies=['C6', 'D6'], pickups=['F2'], generation=4817
ALAS_G13_READ_ONLY_MAP_RESULT True
```

Because the map branch returns before upstream retreat, the game remained on
the map. During a later passive recheck, `[NetworkDown]` appeared again. The
underlying map objects were still present, but the model correctly rejected
the blocked surface. An exact reconnect was injected, and the prompt
reappeared under the current network condition, so no further map result was
claimed. The process and observer stayed fresh beyond the earlier map-scene
failure window.

## Verification

- Controller and integration suite: `225/225` passed.
- Final observer APK:
  `artifacts/AngleLibraries-g13-map-model.apk`.
- APK SHA-256:
  `bb9bdaa7838182731296ce5ab4f6f17aad0394660aa7b24c245a1ccfed18b220`.
- Driver revision:
  `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- Package: `com.bilibili.azurlane`, pinned CN `9.7.10`, x86_64/API 32.
- The fixed ANGLE checkout rebuilt successfully with `512` Image records,
  a `4096`-object scratch collector, thread-local large map snapshots, and the
  fleet ancestor anchor.
- The canonical ALAS patch applies cleanly to upstream commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.

## Remaining boundary

G13 is observation only. The next safe stage is read-only ALAS map
synchronization and planning: translate this model into ALAS's existing grid
objects and validate fleet/enemy/pickup updates across passive generations,
without enabling a grid click. Movement admission should remain a separate
later gate owned by ALAS's existing map state machine.
