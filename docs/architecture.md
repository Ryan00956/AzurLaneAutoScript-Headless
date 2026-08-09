# Architecture

```text
Unity/IL2CPP game
  -> Android EGL/GLES loader
    -> pinned ANGLE APK, NULL backend only
      -> Android-aware NULL surface
         - logical native-window size
         - one deterministic black compositor buffer
         - synthetic swap pacing
      -> no-op draw/dispatch
      -> deterministic zero readback

Unity/IL2CPP game
  -> -force-gfx-st main-thread NULL Swap rendezvous
    -> fixed IL2CPP export allowlist resolved from in-memory ELF metadata
      -> bounded typed Unity UI/scene snapshots and RectTransform bounds
        -> credential-checked, versioned local socket protocol
      -> fail-closed SemanticOracle
        -> independent installed-package fingerprint gate
        -> reviewed ALAS resource-name mapping
        -> ADB input only after foreground/freshness/generation/blocker gates
```

## Trust boundaries

The graphics driver is loaded in-process, but Android places the ANGLE APK in an isolated linker namespace. Co-residency did not make `dlopen`, `RTLD_DEFAULT`, or `RTLD_NOLOAD` succeed in G3. The observer therefore parses the mapped `libil2cpp.so` ELF dynamic table and resolves only a fixed export allowlist.

The local protocol is not a generic debugging bridge. It uses an abstract local
socket, validates `SO_PEERCRED`, publishes fixed snapshot and Button schemas,
and rejects unknown requests. The controller independently hashes the installed
base APK and `libil2cpp.so`, requires the exact foreground Activity and PID,
checks freshness and coherent monotonic generations, resolves one unique
reviewed path, validates point-inside-bounds, and applies known-overlay blockers
before an action can be considered.

G3 proves the rendezvous on the Unity contract. G4 independently verified that
the pinned game accepts `-force-gfx-st`, exposes the allowlisted IL2CPP APIs,
advances under bounded sampling, confirms each action through
`EventSystem.RaycastAll`, and survives one harmless page round trip. Broader
game/Lua semantics remain outside the current proof.

## Hybrid rendering warning

Selective readback is not equivalent to implementing `glReadPixels`. If game logic consumes a RenderTexture, correctness may require the complete upstream shader, texture, and draw dependency closure for that resource. A hybrid renderer is a separate research phase, not an assumed small extension of NULL.
