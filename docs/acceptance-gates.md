# Acceptance gates

Status terms are deliberately strict. A build passing does not imply a later gate has passed.

Current status: G1-G4 passed. G4 includes login/main reachability, sustained
semantic state, RectTransform bounds, top EventSystem raycast identity for each
action, and a settings-page return loop. Task-specific ALAS coverage is a later
gate and is not implied by G4.

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

## Stop or pivot conditions

- A critical flow depends on rendered GPU results rather than completion signaling.
- A readback dependency closure approaches full-scene rendering.
- Main-thread-safe snapshots require fragile per-build code hooks with no reliable fingerprint gate.
- NULL mode provides no operational CPU/RSS advantage over SwiftShader.
- Compatibility requires concealment or anti-detection bypass.
