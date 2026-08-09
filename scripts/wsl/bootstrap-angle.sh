#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
revision="$(tr -d '\r\n' < "${repo_root}/ANGLE_REVISION")"

angle_workspace="${ALAS_ANGLE_WORKSPACE:-${HOME}/src/alas-headless-angle}"
depot_tools_dir="${ALAS_DEPOT_TOOLS_DIR:-${HOME}/src/depot_tools}"
angle_dir="${angle_workspace}/angle"

mkdir -p "$(dirname "${depot_tools_dir}")" "${angle_workspace}"

if [[ ! -d "${depot_tools_dir}/.git" ]]; then
  git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git "${depot_tools_dir}"
fi

export PATH="${depot_tools_dir}:${PATH}"

if [[ ! -d "${angle_dir}/.git" ]]; then
  git clone --filter=blob:none https://chromium.googlesource.com/angle/angle "${angle_dir}"
fi

git -C "${angle_dir}" fetch --no-tags origin "${revision}"
git -C "${angle_dir}" checkout --detach "${revision}"

cd "${angle_dir}"
if [[ ! -f .gclient ]]; then
  python3 scripts/bootstrap.py
fi

gclient sync -D --no-history --revision "angle@${revision}"

actual_revision="$(git rev-parse HEAD)"
if [[ "${actual_revision}" != "${revision}" ]]; then
  echo "ANGLE revision mismatch: expected ${revision}, got ${actual_revision}" >&2
  exit 1
fi

echo "ANGLE ready at ${angle_dir} (${actual_revision})"
