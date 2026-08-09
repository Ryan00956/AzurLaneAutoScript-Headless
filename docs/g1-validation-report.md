# G1 validation report

## Outcome

The Android GLES NULL contract passed on the current MuMu x86_64 validation
host. This proves that the pinned custom ANGLE package can satisfy the probe's
EGL/GLES/window/swap contract for one hour without real draw execution. It does
not prove that the Azur Lane Unity player can run on this driver.

Final evidence directory:

```text
evidence/g1-20260808T075833Z-127.0.0.1_16384
```

Evidence is intentionally excluded from Git because it contains host- and
device-specific runtime data.

## Reproducible artifacts

| Artifact | Value |
| --- | --- |
| ANGLE revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| ANGLE APK SHA-256 | `0ea5284f0f92b074479403936a81a1f53bc9b0e187d07ae3c4c1d478626b61ea` |
| Probe APK SHA-256 | `fcc7b39e1ef11cf3475e87ff8d9b030376e3511fad6d7ae5577781eceeff286c` |
| Device serial | `127.0.0.1:16384` |
| Probe package | `io.github.alasheadless.glescontract` |
| Driver package | `org.chromium.angle` |

The APK files were hashed again after the run; both values matched the final
manifest.

## Contract results

| Requirement | Observed result |
| --- | --- |
| Renderer identity | `Google Inc. (NULL)` / `ANGLE (NULL, NULL, )` |
| Logical surface | `1280x720` |
| Shader and program | compiled and linked |
| Buffer, texture, and FBO | stable non-zero IDs; FBO status `36053` (complete) |
| Query | ID `1`; result retrieval completed with value `0` |
| Fence/sync | wait result `37146` (`GL_CONDITION_SATISFIED`) |
| Direct `glReadPixels` | `00000000` |
| PBO readback | `00000000`; map/unmap completed |
| GL error | `0` |
| Swap pacing | final heartbeat 219,300 frames at 60.000 FPS |

The Android compatibility patches are deliberately separate: loader token
translation, common Android window configs, native-window/frame pacing, and
swap-with-damage. The loader translation is narrow because AOSP's developer
ANGLE path appends the Vulkan platform token before calling into ANGLE, even
for this NULL-only package. See the upstream
[`egl_display.cpp`](https://android.googlesource.com/platform/frameworks/native/+/f166e913dc17d3a4442b75cdec047d939dad2689/opengl/libs/EGL/egl_display.cpp).

## One-hour stability

- Requested and completed duration: 3,600 seconds.
- Samples: 121 at approximately 30-second intervals.
- PSS: 94,703 KiB first, 74,355 KiB last, 73,293 KiB minimum, 94,703 KiB
  maximum.
- RSS: 176,380 KiB first, 153,348 KiB last, 151,940 KiB minimum, 176,380 KiB
  maximum.
- Linear PSS slope after the first five minutes: approximately +2 KiB/minute.
- Coarse Android `top` samples: 0.73% mean CPU, 4% p95, 4% maximum.
- No `FATAL EXCEPTION`, fatal signal, `SIGILL`, `SIGSEGV`, or context-loss
  marker was found in the captured probe process logs.
- The probe PID remained `14873`; the unrelated game PID remained `7547`.

These CPU samples establish absence of an unbounded busy loop in this probe.
They are not a replacement for the missing same-host SwiftShader baseline.

## Isolation and cleanup

The runner routed ANGLE only for the probe package. It did not route, launch,
click, or modify the game package. After completion, the following global
settings all read back as unset (`null`):

```text
angle_debug_package
angle_gl_driver_all_angle
angle_gl_driver_selection_pkgs
angle_gl_driver_selection_values
show_angle_in_use_dialog_box
```

An earlier one-hour process run reached the full duration, but its first
contract event had rotated out of logcat before the original collector read it.
That run was not used as the final pass. The runner now persists the contract
immediately after startup and rewrites `progress.json` after every sample; the
second one-hour run above completed with a valid final manifest.

## Remaining gates

- G0 still lacks a same-host SwiftShader or equivalent software-rendering
  CPU/RSS baseline.
- G2 source is ready. Unity's official archive identifies `2022.3.62f3` as
  changeset `96770f904ca7`, but neither the editor nor a Unity license is
  installed on this host. The IL2CPP Unity contract has therefore not been
  built or run.
- G3 and later have not started. No in-process observer, semantic socket, game
  driver routing, game click, or ALAS semantic adapter is claimed.
