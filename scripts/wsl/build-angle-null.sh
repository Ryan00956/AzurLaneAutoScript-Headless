#!/usr/bin/env bash
set -euo pipefail

angle_dir="${ALAS_ANGLE_DIR:-${ALAS_ANGLE_WORKSPACE:-${HOME}/src/alas-headless-angle}/angle}"
depot_tools_dir="${ALAS_DEPOT_TOOLS_DIR:-${HOME}/src/depot_tools}"
out_dir="${ALAS_ANGLE_OUT_DIR:-out/AndroidNullX64}"

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
  echo "Expected ANGLE APK was not produced: ${apk}" >&2
  exit 1
fi

sha256sum "${apk}"
echo "ANGLE NULL APK: ${apk}"
