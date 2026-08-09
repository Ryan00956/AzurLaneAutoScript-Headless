# G3 observer validation report

## Outcome

G3 passed on the exact Unity `2022.3.62f3` x86_64 IL2CPP contract workload.
The final driver produced typed Button and active-scene snapshots on Unity's
managed main thread, served them through a credential-checked local protocol,
and passed foreground, freshness, generation, version, and negative-request
gates.

G3 by itself did not prove that Azur Lane initializes under NULL. Subsequent G4
runs established sustained real-game generations, typed bounds, top EventSystem
raycast identity, and a harmless settings-page closed loop; those results are
reported separately.

Final evidence:

```text
evidence/g3-observer-20260809T013932Z-emulator-5570
evidence/g2-null-20260809T014015Z-emulator-5570
```

## Artifacts

| Artifact | Value |
| --- | --- |
| ANGLE revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| Observer ANGLE APK SHA-256 | `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7` |
| Unity contract APK SHA-256 | `87e845359bc1d957b0c75f685f461b017ed6e05d0a593088683511400e8e99ba` |
| Unity command line | `-force-gfx-st` through Intent extra `unity` |
| Protocols | `alas-headless.observer/v1`, `alas-headless.buttons/v1` |
| Socket | abstract local `alas.g3.<pid>` |

## Main-thread rendezvous

The first render-thread experiment was intentionally fail-closed: normal
multithreaded rendering called `SurfaceNULL::swap()` on
`UnityGfxDeviceW`, not managed `Update()`. Metadata enumeration worked after a
temporary `il2cpp_thread_attach`, but it was not accepted as a Unity object
snapshot rendezvous.

Unity's stock `UnityPlayerActivity` reads the Intent string extra named
`unity`. Launching with `-force-gfx-st` removed the graphics worker and made
NULL Swap and managed `Update()` share one TID. The final G3 run recorded TID
2625 in both the Unity telemetry and every checked observer snapshot. A G4
follow-up showed that Android HWUI and WebView may create additional ANGLE
displays in the same process. The final observer therefore accepts only the
first thread that is already attached to IL2CPP and ignores every other
surface's Swap.

## Linker namespace and IL2CPP access

The process mapped `libil2cpp.so`, but ordinary dynamic-loader lookup remained
blocked across Android namespaces. The observer parsed the mapped ELF
`PT_DYNAMIC`, SysV hash, symbol table, and string table in place and resolved a
fixed 32-symbol allowlist. The final namespace record reported:

```text
dynamic_parsed=true
manual_symbols=32
allowlisted_total=32
rtld_default_domain_get=false
soname_noload=false
path_noload=false
```

No general symbol lookup or invocation endpoint is exposed by the socket.

## Typed snapshot behavior

The observer uses Unity 2022 liveness exports to enumerate only
`UnityEngine.UI.Button` instances into a bounded 256-pointer buffer. On the
validated main thread it invokes only fixed getters for active/enabled and
interactable state, plus the fixed active-scene getter. Snapshot flags `15`, UI
stage `100`, and method mask `15` mean the typed path completed.

The final bounds-enabled run observed:

| Checkpoint | Generation | Scene generation | Semantic generation | Buttons active/interactable | Age |
| --- | ---: | ---: | ---: | --- | ---: |
| Before click | 2 | 2 | 2 | 1 / 1 | 87 ms |
| After click | 3 | 2 | 3 | 1 / 0 | 90 ms |
| After scene change | 9 | 3 | 3 | 1 / 0 | 136 ms |
| Home | 9 | 3 | 3 | 1 / 0 | 4,523 ms |
| After resume | 10 | 3 | 3 | 1 / 0 | 452 ms |

The top-resumed package changed from the contract to Launcher at Home. The
combined foreground/freshness gate stayed closed even though the socket still
held the last read-only snapshot.

## Protocol restrictions

- Only exact `GET /v1/snapshot` requests return snapshots.
- Unknown requests return `bad-request` without generation or object data.
- `SO_PEERCRED` permits only the process UID, root, or Android shell UID 2000.
- Responses include package, PID, UID, ABI, driver revision, schema, snapshot
  age, main-thread TID, and monotonic generations.
- `GET /v1/buttons` adds bounded typed records with full path, Canvas, state,
  screen/ADB point, four-corner screen/ADB bounds, and a nullable
  `raycast_top` result. Raycast evaluation is limited to reviewed semantic
  targets. It returns neither object addresses nor arbitrary field/method
  access.
- The Windows controller independently checks the top-resumed package, Android
  and package version fingerprint, APK hashes, and maximum age before treating
  a snapshot as actionable.

## Regression and limitations

With typed sampling and reviewed-target top-raycast checks enabled, the final
47.117-second G2 run still passed Update, FixedUpdate, WaitForEndOfFrame, UI
animation, the safe click, and pause/resume. Eight AsyncGPUReadback requests
completed across the full run; seven were complete by the last heartbeat, with
no errors or timeouts.

An intermediate EventSystem prototype invoked `RaycastResult.gameObject` on a
boxed value-type receiver and crashed only the Unity contract process. The
native backtrace identified the invalid `GameObject.get_transform` receiver.
The implementation was replaced with allowlisted
`il2cpp_class_get_field_from_name` / `il2cpp_field_get_value` access to
`m_GameObject`; the final G3 and G4 runs passed without that failure. The game
was not started with the crashing build.

Remaining risks are explicit:

- Lua/game-state observation is not yet implemented.
- The liveness pause cost must be remeasured during a long real-game soak.
- The later G5b result covers one controlled default-page claim-all closure.
  Row-only claims, tab traversal, and every other task flow remain fail closed.
