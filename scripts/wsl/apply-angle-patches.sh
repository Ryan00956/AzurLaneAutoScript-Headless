#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
revision="$(tr -d '\r\n' < "${repo_root}/ANGLE_REVISION")"
angle_dir="${ALAS_ANGLE_DIR:-${ALAS_ANGLE_WORKSPACE:-${HOME}/src/alas-headless-angle}/angle}"
patch_dir="${repo_root}/patches/angle"

if ! git -C "${angle_dir}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ANGLE checkout not found at ${angle_dir}; run bootstrap-angle.sh first" >&2
  exit 1
fi

if [[ "$(git -C "${angle_dir}" rev-parse HEAD)" != "${revision}" ]]; then
  echo "Refusing to patch an unpinned ANGLE checkout" >&2
  exit 1
fi

mapfile -t patches < <(find "${patch_dir}" -maxdepth 1 -type f -name '*.patch' -print | sort)
if [[ "${#patches[@]}" -eq 0 ]]; then
  echo "No ANGLE patches found" >&2
  exit 1
fi

patch_marker_present() {
  case "$1" in
    0001-android-null-window-contract.patch)
      grep -Fq 'debug.angle.null_refresh_hz' \
        "${angle_dir}/src/libANGLE/renderer/null/SurfaceNULL.cpp"
      ;;
    0002-android-null-aosp-vulkan-token.patch)
      grep -Fq "Android's loader always supplies the Vulkan token" \
        "${angle_dir}/src/libANGLE/validationEGL.cpp"
      ;;
    0003-android-null-common-window-configs.patch)
      grep -Fq 'egl::Config rgbxConfig' \
        "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"
      ;;
    0004-android-null-swap-with-damage.patch)
      grep -Fq 'SurfaceNULL::swapWithDamage' \
        "${angle_dir}/src/libANGLE/renderer/null/SurfaceNULL.cpp"
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
  if git -C "${angle_dir}" apply --reverse --check "${patch}" >/dev/null 2>&1; then
    echo "already applied: ${patch_name}"
    continue
  fi
  git -C "${angle_dir}" apply --check "${patch}"
  git -C "${angle_dir}" apply "${patch}"
  echo "applied: ${patch_name}"
done
