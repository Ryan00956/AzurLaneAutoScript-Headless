# G2 Unity validation report

## Outcome

G2 passed on the validation host. The exact Unity `2022.3.62f3` x86_64
IL2CPP contract passed under the custom ANGLE NULL renderer, and a cold-start,
same-host software-rendering comparison showed a material CPU and memory
advantage over the Android Emulator's SwiftShader mode.

At the time of this comparison, the result advanced the project to G3 observer
research. Later G3/G4 evidence separately proved driver-namespace IL2CPP
resolution and real-game initialization; those claims are intentionally not
derived from this comparison.

Final evidence directories:

```text
evidence/avd-cold-system-20260808T111054Z
evidence/g2-system-20260808T111131Z-emulator-5570
evidence/avd-cold-null-20260808T111502Z
evidence/g2-null-20260808T111610Z-emulator-5570
evidence/g2-comparison-20260808T112155Z
```

The final comparison manifest SHA-256 is
`ea039eda51235626e0374a7f4339ae618a81a049b98ff6016bf0909853a8a6d3`.

## Artifacts and toolchain

| Artifact | Value |
| --- | --- |
| Unity editor | `2022.3.62f3` changeset `96770f904ca7` |
| Scripting backend and ABI | IL2CPP, x86_64 only |
| Unity APK SHA-256 | `94ee95a8a6988c6b360047c66739cace3e1201e7b389b6d0e61503284ffeb696` |
| ANGLE revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |
| ANGLE NULL APK SHA-256 | `0ea5284f0f92b074479403936a81a1f53bc9b0e187d07ae3c4c1d478626b61ea` |
| Android Emulator | `37.1.11` |
| Android image | API 32, default x86_64 image revision 2 |
| AVD | `alas_api32_x64`, four vCPUs, 4,096 MiB RAM, `1280x720` |
| Test package | `io.github.alasheadless.unitycontract` |

The Unity APK contains only `lib/x86_64/libunity.so`, `libil2cpp.so`, and
`libmain.so`. Both final legs used this identical APK.

## Comparison design

The two final legs ran on the same Windows host, AVD, Android image, vCPU/RAM
configuration, logical surface, test package, and Unity APK. Each leg received
a new QEMU process with snapshots disabled:

- SwiftShader leg: QEMU PID `7772`, launched with `-gpu swiftshader`.
- NULL leg: QEMU PID `21768`, with the Emulator still launched in the same
  SwiftShader mode but the Unity package alone routed to the custom ANGLE APK.

The Emulator logs identify `SwiftShader Device (LLVM 10.0.0)` and
`Android Emulator OpenGL ES Translator (Google SwiftShader)`. The NULL run
loaded `libEGL_angle.so` and `libGLESv2_angle.so` from the package and Unity
reported `ANGLE (NULL, NULL, )`.

Each leg ran approximately 185 seconds and performed the same safe button tap
and Home/resume cycle. The runner sampled both the Android app process and the
host QEMU process. The Android Emulator documents `swiftshader` as its software
graphics mode: <https://developer.android.com/studio/run/emulator-acceleration>.

## Functional contract

| Requirement | SwiftShader | ANGLE NULL |
| --- | ---: | ---: |
| Renderer | Google SwiftShader | `ANGLE (NULL, NULL, )` |
| Logical surface | `1280x720` | `1280x720` |
| Structured events | 69 | 67 |
| Heartbeats | 17 | 15 |
| Final `Update` count | 5,100 | 4,500 |
| Final `FixedUpdate` count | 8,565 | 8,411 |
| Final `WaitForEndOfFrame` count | 5,099 | 4,499 |
| AsyncGPUReadback outcomes | 35 | 35 |
| Semantic marker after click | `contract/button-clicked` | `contract/button-clicked` |
| Contract failures | 0 | 0 |

Both legs advanced UI animation, generated scene transitions, survived
pause/resume without a PID change, and completed every observed readback without
a timeout. NULL readbacks remained deterministic zero-filled data.

The NULL leg produced fewer Updates per wall-clock interval. Therefore the raw
host CPU comparison is supplemented by CPU time per 1,000 Updates; the savings
remain material after this normalization.

## CPU and memory comparison

| Metric | SwiftShader | ANGLE NULL | NULL change |
| --- | ---: | ---: | ---: |
| Host QEMU CPU seconds in sample interval | 380.188 s | 95.281 s | -74.9% raw time |
| Host QEMU sustained core equivalents | 2.0551 | 0.5178 | **-74.8%** |
| Host CPU seconds per 1,000 Updates | 74.5466 s | 21.1736 s | **-71.6%** |
| Host QEMU working-set median | 3,330.4 MiB | 3,012.7 MiB | **-9.54%** |
| Host QEMU private-memory median | 5,979.1 MiB | 5,595.6 MiB | **-6.41%** |
| Android app CPU sample mean | 22.665% | 16.856% | -25.63% |
| Android app PSS median | 125,908 KiB | 116,257 KiB | **-7.67%** |
| Android app RSS median | 230,740 KiB | 219,592 KiB | **-4.83%** |

Host QEMU CPU is the primary CPU metric because SwiftShader executes in the
host Emulator process. Android `top` is retained as a coarse secondary signal.
QEMU memory includes guest backing and Emulator infrastructure, so its absolute
size is not attributable solely to graphics; the comparison is useful because
both legs were cold-started with the same configuration.

## Isolation, cleanup, and discarded diagnostics

ANGLE was routed only to the Unity contract package. After every run the four
modified global ANGLE settings were restored to their original unset state and
the contract process was stopped.

Two earlier 180-second captures are not used as final evidence:

- The first SwiftShader run was covered by Android's first-use immersive-mode
  confirmation, which intercepted the test tap. Closing that system overlay
  made the unchanged coordinate emit `button-click` generation 2.
- The first NULL attempt installed the driver without `--force-queryable`.
  Android 11+ reported the debug package as not installed to
  `GraphicsEnvironment` even though `dumpsys package` could see it, so the app
  stayed on SwiftShader. The runner now installs the driver with
  `-d --force-queryable`; a short probe then proved the ANGLE libraries and NULL
  renderer loaded before the final leg.

The fail-closed comparison script validates both leg results, renderer
identities, serial, Unity APK hash, surface, cold-process separation, duration,
and a positive CPU/RSS advantage before emitting a passing manifest.

## Final observer-driver regression

After the observer gained the 32-symbol IL2CPP allowlist, typed Button bounds,
and reviewed-target `EventSystem.RaycastAll` checks, the final driver was run
against the same Unity contract for another 46.745 seconds:

```text
evidence/g2-null-20260808T173503Z-emulator-5570
```

That manifest passed with no failures. It identifies `ANGLE (NULL, NULL, )`,
OpenGLES3, and the `1280x720` surface. The last heartbeat at 44.578 seconds
reported 600 Updates, 1,871 FixedUpdates, 599 end-of-frame resumes, eight
completed zero-filled AsyncGPUReadbacks, and zero readback errors. The safe
contract click still advanced `contract/button-clicked` to generation 2.

The final observer ANGLE APK SHA-256 is
`ac5c9bd696badd7d9b3bd62cce27c74acf474808f712ab78632be91b9e5c33bf`;
the final contract APK SHA-256 is
`87e845359bc1d957b0c75f685f461b017ed6e05d0a593088683511400e8e99ba`.
This short regression protects G2 behavior after observer changes; it does not
replace the cold-process SwiftShader/NULL performance comparison above.

## Remaining scope

The performance comparison remains a synthetic Unity contract on an official
Android Emulator, not an Azur Lane workload on MuMu or Redroid. It proves the
NULL driver can preserve the tested Unity lifecycle while materially reducing
software-rendering cost. Real-game initialization and harmless semantic clicks
are covered separately by the G4 report; neither report yet proves complete
ALAS task coverage.
