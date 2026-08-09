#!/usr/bin/env bash
set -euo pipefail

angle_dir="${ALAS_ANGLE_DIR:-${ALAS_ANGLE_WORKSPACE:-${HOME}/src/alas-headless-angle}/angle}"
depot_tools_dir="${ALAS_DEPOT_TOOLS_DIR:-${HOME}/src/depot_tools}"
out_dir="${ALAS_ANGLE_OBSERVER_OUT_DIR:-out/AndroidNullObserverX64}"

if ! grep -Fq 'ALAS_G3_NAMESPACE' \
    "${angle_dir}/src/libANGLE/renderer/null/DisplayNULL.cpp"; then
  echo "G3 namespace probe is not applied; run apply-angle-g3-patches.sh first" >&2
  exit 1
fi
if ! grep -Fq 'semantic_schema' \
    "${angle_dir}/src/libANGLE/renderer/null/ObserverServer.cpp"; then
  echo "Typed Button observer overlay is missing; run apply-angle-g3-patches.sh first" >&2
  exit 1
fi
if ! grep -Fq 'raycast_top' \
    "${angle_dir}/src/libANGLE/renderer/null/ObserverServer.cpp"; then
  echo "EventSystem raycast observer overlay is missing" >&2
  exit 1
fi
if ! grep -Fq 'kIl2CppAllowlistSize = 32' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.h"; then
  echo "32-symbol raycast observer allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'TaskScene(Clone)/blur_panel/adapt/top/GetAllButton' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "G5 mission Button raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'AwardInfoUI(Clone)/items/close' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "G5 reward popup raycast allowlist is missing" >&2
  exit 1
fi

export PATH="${depot_tools_dir}:${PATH}"
cd "${angle_dir}"

gn gen "${out_dir}" --args='target_os="android"
target_cpu="x64"
is_component_build=false
is_debug=false
symbol_level=1
angle_assert_always_on=true
angle_enable_null=true
angle_enable_vulkan=false
angle_enable_gl=false
angle_enable_wgpu=false
angle_enable_d3d11=false
angle_enable_metal=false
use_thin_lto=false'

autoninja -C "${out_dir}" angle_chromium_apk

apk="${angle_dir}/${out_dir}/apks/AngleLibraries.apk"
if [[ ! -f "${apk}" ]]; then
  echo "Expected observer ANGLE APK was not produced: ${apk}" >&2
  exit 1
fi

sha256sum "${apk}"
echo "ANGLE NULL observer APK: ${apk}"
