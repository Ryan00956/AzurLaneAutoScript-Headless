# G0 evidence bundle

`scripts/windows/capture-g0.ps1` creates a timestamped, read-only evidence directory. It does not launch, stop, clear, install, or click an application.

## Files

- `host-adb.txt`: host ADB identity.
- `devices.txt`: connected device inventory.
- `properties.txt`: Android build, ABI, graphics, and display properties.
- `display.txt`: physical/logical display and density state.
- `package.txt`: target package metadata.
- `top-activity.txt`: resumed/top package evidence.
- `process.txt`: target PID and process row.
- `graphics-log.txt`: existing process log filtered to graphics/Unity initialization signals.
- `mapped-libraries.txt`: filtered process mappings for Unity, IL2CPP, EGL, GLES, Vulkan, ANGLE, and translation layers.
- `binary-hashes.txt`: hashes of readable APK/native-library paths.
- `manifest.json`: command status, capture metadata, and SHA-256 for every evidence file.

Root is optional. Without `-UseRoot`, protected process maps and `/data/app` native-library hashes may be unavailable and are reported as such rather than silently omitted.
