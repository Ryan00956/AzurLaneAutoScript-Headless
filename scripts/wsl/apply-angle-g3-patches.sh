#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
revision="$(tr -d '\r\n' < "${repo_root}/ANGLE_REVISION")"
angle_dir="${ALAS_ANGLE_DIR:-${ALAS_ANGLE_WORKSPACE:-${HOME}/src/alas-headless-angle}/angle}"
patch_dir="${repo_root}/patches/angle-g3"
overlay_dir="${repo_root}/overlays/angle-g3"

if ! git -C "${angle_dir}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ANGLE checkout not found at ${angle_dir}; run bootstrap-angle.sh first" >&2
  exit 1
fi
if [[ "$(git -C "${angle_dir}" rev-parse HEAD)" != "${revision}" ]]; then
  echo "Refusing to patch an unpinned ANGLE checkout" >&2
  exit 1
fi
if ! grep -Fq 'debug.angle.null_refresh_hz' \
    "${angle_dir}/src/libANGLE/renderer/null/SurfaceNULL.cpp"; then
  echo "Base NULL patches are missing; run apply-angle-patches.sh first" >&2
  exit 1
fi

while IFS= read -r -d '' overlay; do
  relative="${overlay#${overlay_dir}/}"
  install -D -m 0644 "${overlay}" "${angle_dir}/${relative}"
done < <(find "${overlay_dir}" -type f -print0)

mapfile -t patches < <(find "${patch_dir}" -maxdepth 1 -type f -name '*.patch' -print | sort)
if [[ "${#patches[@]}" -eq 0 ]]; then
  echo "No G3 ANGLE patches found" >&2
  exit 1
fi

patch_marker_present() {
  case "$1" in
    0001-android-null-il2cpp-namespace-probe.patch)
      grep -Fq 'ALAS_G3_NAMESPACE' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0002-android-null-safe-maps-reader.patch)
      grep -Fq 'std::ifstream maps("/proc/self/maps")' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0003-android-null-logcat-probe.patch)
      grep -Fq '__android_log_print' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0004-android-null-phdr-namespace-probe.patch)
      grep -Fq 'dl_iterate_phdr' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0005-android-null-dynamic-symbol-probe.patch)
      grep -Fq 'ProbeIl2CppDynamicSymbols' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0006-android-null-dynamic-probe-diagnostics.patch)
      grep -Fq 'dynamic_stage' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0007-android-null-dynamic-allowlist-total.patch)
      grep -Fq 'visibleSymbols, rx::alas::kIl2CppAllowlistSize' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0008-android-null-observer-socket.patch)
      grep -Fq 'StartObserverServer' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0009-android-null-swap-observer.patch)
      grep -Fq 'ObserverFrameTick' \
        "${angle_dir}/src/libANGLE/renderer/null/SurfaceNULL.cpp"
      ;;
    0010-android-null-snapshot-cadence.patch)
      grep -Eq 'mSwapCount % 60|Internal request/monotonic cadence' \
        "${angle_dir}/src/libANGLE/renderer/null/SurfaceNULL.cpp"
      ;;
    0011-android-null-register-main-thread.patch)
      grep -Fq 'RegisterObserverMainThread' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    *)
      return 1
      ;;
  esac
}

for patch in "${patches[@]}"; do
  patch_name="$(basename "${patch}")"
  if patch_marker_present "${patch_name}"; then
    echo "already applied: ${patch_name}"
    continue
  fi
  git -C "${angle_dir}" apply --check "${patch}"
  git -C "${angle_dir}" apply "${patch}"
  echo "applied: ${patch_name}"
done
