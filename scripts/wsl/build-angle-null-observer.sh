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
if ! grep -Fq 'GET /v1/ui' \
    "${angle_dir}/src/libANGLE/renderer/null/ObserverServer.cpp"; then
  echo "Typed UI observer endpoint is missing" >&2
  exit 1
fi
if ! grep -Fq 'TextMeshProUGUI' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Typed TextMeshPro observer is missing" >&2
  exit 1
fi
if ! grep -Fq 'ShouldEvaluateImageTopRaycast' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Typed Image raycast observer is missing" >&2
  exit 1
fi
if ! grep -Fq 'MailUI(Clone)/adapt/CommonTitleAndBack/back_btn' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Mail page raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'ShouldEvaluateToggleTopRaycast' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Typed Toggle raycast observer is missing" >&2
  exit 1
fi
if ! grep -Fq 'MailMgrMsgboxUI(Clone)/window/button_container/btn_get' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Mail manager raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'Target{"extend", "frame/left/extend"}' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Main drawer raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'Target{"live", "frame/bottom/frame/live"}' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Dorm-menu main Button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'kBuildPools' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Construction pool Toggle allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'name == "school_btn"' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Dorm-menu Button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'SelectTechnologyUI(Clone)/frame/bg/' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Research-menu Button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'TechnologyUI(Clone)/main/base_page/srcoll_rect/content/' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Research project Button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'Unity liveness can retain a destroyed component' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Destroyed Unity Button tolerance is missing" >&2
  exit 1
fi
if ! grep -Fq 'std::array<void *, 1024> objects' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Long-session Unity liveness capacity is missing" >&2
  exit 1
fi
if ! grep -Fq 'kReviewedRaycastFractions' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Dorm Button bounded raycast search is missing" >&2
  exit 1
fi
if ! grep -Fq 'BackYardStatisticsUI(Clone)/painting/confirm_btn' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Dorm statistics confirm allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'NewNavalTacticsUI(Clone)/adpter/frame/btnBack' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Tactical page back allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'custom_button_2(Clone)' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Tactical continue-cancel allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'custom_button_1(Clone)' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Network reconnect-confirm allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelMainScene(Clone)/top/top_chapter/back_button' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign-menu back-button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelMainScene(Clone)/entrance/enters/enter_main' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign-menu normal-entry allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelMainScene(Clone)/float/levels/items/' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign stage Button raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'name == "main"' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign stage action Button raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelStageInfoView(Clone)/panel/start_button' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign map-preparation start allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelStageInfoView(Clone)/panel/btnBack' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign map-preparation cancel allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelFleetSelectView(Clone)/panel/Fixed/btnBack' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign fleet-preparation cancel allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign fleet-selection row allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'LevelFleetSelectView(Clone)/mask/list/' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Campaign fleet-selection option allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'Overlay/UIMain/blur_panel/adapt/top/back_btn' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Construction-page back-button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'ActivityMainUI(Clone)/adapt/blur_panel/adapt/top/back_btn' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Event-list back-button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'CommissionInfoUI4Mellow(Clone)/frame/main/content/event/' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Reward-page semantic entries are missing" >&2
  exit 1
fi
if ! grep -Fq 'frame/go_btn' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Reward-page go-button allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'kIl2CppAllowlistSize = 32' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.h"; then
  echo "32-symbol raycast observer allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'kMaxObserverButtons = 128' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.h"; then
  echo "128-record Button capacity is missing" >&2
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
if ! grep -Fq 'ShipExpUI(Clone)/skipLayer' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Commission EXP reward raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'EventUI(Clone)/scrollRect$/content/' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Commission-list Button raycast allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq '"daily_btn", "urgency_btn"' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Commission-list tab Image allowlist is missing" >&2
  exit 1
fi
if ! grep -Fq 'EventUI(Clone)/blur_panel/adapt/scroll_bar/Image' \
    "${angle_dir}/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"; then
  echo "Commission scrollbar Image raycast allowlist is missing" >&2
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
