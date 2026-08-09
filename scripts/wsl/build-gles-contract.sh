#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
angle_dir="${ALAS_ANGLE_DIR:-${ALAS_ANGLE_WORKSPACE:-${HOME}/src/alas-headless-angle}/angle}"
gradle_version="9.4.1"
gradle_cache="${ALAS_GRADLE_CACHE:-${HOME}/.cache/alas-headless/gradle-${gradle_version}}"
target_sdk="${ALAS_TARGET_SDK:-32}"

sdk_candidates=(
  "${ANDROID_SDK_ROOT:-}"
  "${ANDROID_HOME:-}"
  "${angle_dir}/third_party/android_sdk/public"
  "${angle_dir}/third_party/android_sdk/cipd"
  "${angle_dir}/third_party/android_sdk"
)

sdk_root=""
for candidate in "${sdk_candidates[@]}"; do
  if [[ -n "${candidate}" && -d "${candidate}/platforms" && -d "${candidate}/build-tools" ]] &&
     [[ -n "$(find "${candidate}/platforms" -mindepth 2 -maxdepth 2 -type f -name android.jar -print -quit)" ]] &&
     [[ -n "$(find "${candidate}/build-tools" -mindepth 1 -maxdepth 1 -type d -print -quit)" ]]; then
    sdk_root="${candidate}"
    break
  fi
done

if [[ -z "${sdk_root}" ]]; then
  echo "Android SDK not found. Bootstrap ANGLE or set ANDROID_SDK_ROOT." >&2
  exit 1
fi

compile_sdk="$(
  find "${sdk_root}/platforms" -mindepth 2 -maxdepth 2 -type f -name android.jar -printf '%h\n' |
    xargs -r -n1 basename |
    grep -E '^android-[0-9]+([.][0-9]+)?$' |
    sort -V |
    tail -n 1
)"
if [[ -z "${compile_sdk}" ]]; then
  echo "No numeric Android platform was found under ${sdk_root}/platforms." >&2
  exit 1
fi

build_tools_version="$(
  find "${sdk_root}/build-tools" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
    sort -V |
    tail -n 1
)"
if [[ -z "${build_tools_version}" ]]; then
  echo "No Android build-tools installation was found under ${sdk_root}/build-tools." >&2
  exit 1
fi

if [[ ! -x "${gradle_cache}/bin/gradle" ]]; then
  archive="${gradle_cache}.zip"
  mkdir -p "$(dirname "${gradle_cache}")"
  curl --fail --location --retry 3 "https://services.gradle.org/distributions/gradle-${gradle_version}-bin.zip" --output "${archive}"
  rm -rf "${gradle_cache}"
  unzip -q "${archive}" -d "$(dirname "${gradle_cache}")"
  rm -f "${archive}"
fi

export ANDROID_SDK_ROOT="${sdk_root}"
"${gradle_cache}/bin/gradle" \
  --no-daemon \
  --project-dir "${repo_root}/probes/gles-contract" \
  -PalasCompileSdk="${compile_sdk}" \
  -PalasBuildTools="${build_tools_version}" \
  -PalasTargetSdk="${target_sdk}" \
  :app:assembleDebug

apk="${repo_root}/probes/gles-contract/app/build/outputs/apk/debug/app-debug.apk"
sha256sum "${apk}"
echo "GLES contract APK: ${apk}"
