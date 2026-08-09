# G6 typed semantic UI validation

G6 adds bounded Unity UI observation for the semantic controller. The native
observer now exposes `Toggle`, legacy UGUI `Text`, TextMesh Pro text, and
`Image` records through `GET /v1/ui`. The endpoint remains read-only: it does
not expose object addresses or a generic managed-method invocation surface.

## Final build and package

- ANGLE revision: `be80ce591a481c12d60c50d6040d40c035b40a2b`
- Final observer APK SHA-256:
  `fbc288dbe20e0264e90d522772922b72a24d799888e0804cd47781727475a571`
- Game package: `com.bilibili.azurlane`, version `9.7.10` (`9710`), x86_64
- Base APK SHA-256:
  `e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f`
- `libil2cpp.so` SHA-256:
  `e3f1cfc442b67f1d4c9877fd9ceaedc3d68f2842ad677445241b9cc9c05d1c67`

The final read-only capture is in
`evidence/g6-semantic-ui-20260809T030729Z-emulator-5580`. Its manifest records
observer generation 159, UI method mask 15, 42 Buttons, 5 Toggles, 16 text
records, 100 Images, zero observer errors, no Image truncation, and
`input_injected=false`.

`skipped_count=47` is not an extraction error. It records bounded candidate
objects which failed the Unity liveness check while the scene hierarchy was
being enumerated. Actual active-object extraction failures remain fatal.

## Text and ALAS OCR contract

The observer returns UTF-8 text with exact `RectTransform` bounds and a
per-record truncation flag. The controller resolves an ALAS OCR rectangle to
typed Unity text inside that rectangle, strips rich-text markup and whitespace,
and applies the caller's alphabet restriction. Missing, overlapping,
out-of-bounds, truncated, or alphabet-invalid matches fail closed. It never
falls back to a black screenshot or silently invokes the legacy pixel OCR in
semantic mode.

Live probes observed login-page labels and task-row text, including task
descriptions and progress such as `0/1`. The ALAS OCR hook and its context
lifecycle have unit and pinned-patch application coverage. A complete live
ALAS reward invocation using this OCR hook has not yet been claimed.

## Mission sidebar contract

The task sidebar is represented by six exact Image paths and selected/unselected
sprite pairs: all, main, side, daily, weekly, and event. The native observer
computes EventSystem top-raycast identity only for those reviewed paths. A
semantic click requires the expected sprite, active state, in-screen bounds,
top-raycast proof, foreground package, PID, coherent generation, and freshness.

A live closed loop proved:

1. exact main task entry;
2. `all` selected and `weekly` unselected;
3. exact weekly Image action with `raycast_top=true`;
4. postcondition `icon_week_sel`;
5. exact all Image action and selected-state recovery;
6. exact task back action and main-page recovery.

No reward control was clicked during this sidebar test. ALAS still owns the
Navbar and reward state machines; the adapter supplies the Image state and
action. Unit tests cover that ownership boundary. The full ALAS-owned
`Reward.reward_mission()` no-claim/controlled-claim rerun remains open.

## Remaining closed gates

This result does not enable unattended ALAS. Positive mission red-dot behavior,
empty-page inference, numeric-row claims, ship reward popups, scrolling, mail,
commission, dorm, tactical training, research, construction, maps, and battle
state require their own exact mappings and live closures.
