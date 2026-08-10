// Copyright 2026 The ANGLE Project Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"

#include "common/platform.h"

#include <atomic>
#include <chrono>
#include <mutex>

#if defined(ANGLE_PLATFORM_ANDROID)
#include <android/log.h>
#include <elf.h>
#include <inttypes.h>
#include <link.h>
#include <sys/types.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cstring>
#include <limits>
#include <string>
#include <string_view>

#include "common/unsafe_buffers.h"
#endif

namespace rx::alas {

#if defined(ANGLE_PLATFORM_ANDROID)
namespace {
constexpr std::array<std::string_view, kIl2CppAllowlistSize>
    kAllowlistedSymbols = {
        "il2cpp_domain_get",
        "il2cpp_domain_get_assemblies",
        "il2cpp_assembly_get_image",
        "il2cpp_image_get_name",
        "il2cpp_thread_attach",
        "il2cpp_thread_detach",
        "il2cpp_thread_current",
        "il2cpp_class_from_name",
        "il2cpp_class_get_type",
        "il2cpp_type_get_object",
        "il2cpp_class_get_method_from_name",
        "il2cpp_runtime_invoke",
        "il2cpp_object_unbox",
        "il2cpp_array_length",
        "il2cpp_string_length",
        "il2cpp_string_chars",
        "il2cpp_class_get_parent",
        "il2cpp_resolve_icall",
        "il2cpp_unity_liveness_allocate_struct",
        "il2cpp_unity_liveness_calculation_from_statics",
        "il2cpp_unity_liveness_finalize",
        "il2cpp_unity_liveness_free_struct",
        "il2cpp_stop_gc_world",
        "il2cpp_start_gc_world",
        "il2cpp_alloc",
        "il2cpp_free",
        "il2cpp_object_new",
        "il2cpp_method_get_param",
        "il2cpp_method_get_return_type",
        "il2cpp_class_from_type",
        "il2cpp_class_get_field_from_name",
        "il2cpp_field_get_value",
};

bool IsRangeInModule(const dl_phdr_info &info, uintptr_t address, size_t size) {
  for (ElfW(Half) index = 0; index < info.dlpi_phnum; ++index) {
    const ElfW(Phdr) &header = ANGLE_UNSAFE_BUFFERS(info.dlpi_phdr[index]);
    if (header.p_type != PT_LOAD) {
      continue;
    }
    const uintptr_t start = info.dlpi_addr + header.p_vaddr;
    if (start > std::numeric_limits<uintptr_t>::max() - header.p_memsz) {
      continue;
    }
    const uintptr_t end = start + header.p_memsz;
    if (address >= start && address <= end && size <= end - address) {
      return true;
    }
  }
  return false;
}

uintptr_t ResolveDynamicAddress(const dl_phdr_info &info, ElfW(Addr) value,
                                size_t size) {
  if (info.dlpi_addr <= std::numeric_limits<uintptr_t>::max() - value) {
    const uintptr_t relative = info.dlpi_addr + value;
    if (IsRangeInModule(info, relative, size)) {
      return relative;
    }
  }
  const uintptr_t absolute = static_cast<uintptr_t>(value);
  return IsRangeInModule(info, absolute, size) ? absolute : 0;
}

bool ResolveFromDynamic(const dl_phdr_info &info, Il2CppDynamicProbe *result) {
  result->diagnosticStage = 10;
  const ElfW(Dyn) *dynamic = nullptr;
  size_t dynamicCount = 0;
  for (ElfW(Half) index = 0; index < info.dlpi_phnum; ++index) {
    const ElfW(Phdr) &header = ANGLE_UNSAFE_BUFFERS(info.dlpi_phdr[index]);
    if (header.p_type != PT_DYNAMIC) {
      continue;
    }
    const uintptr_t address = info.dlpi_addr + header.p_vaddr;
    dynamicCount = header.p_memsz / sizeof(ElfW(Dyn));
    if (dynamicCount == 0 ||
        !IsRangeInModule(info, address, dynamicCount * sizeof(ElfW(Dyn)))) {
      return false;
    }
    dynamic = reinterpret_cast<const ElfW(Dyn) *>(address);
    result->dynamicFound = true;
    break;
  }
  if (dynamic == nullptr) {
    return false;
  }

  result->diagnosticStage = 20;

  uintptr_t symbolTableAddress = 0;
  uintptr_t stringTableAddress = 0;
  uintptr_t hashAddress = 0;
  size_t stringTableSize = 0;
  size_t symbolEntrySize = 0;
  for (size_t index = 0; index < dynamicCount; ++index) {
    const ElfW(Dyn) &entry = ANGLE_UNSAFE_BUFFERS(dynamic[index]);
    if (entry.d_tag == DT_NULL) {
      break;
    }
    switch (entry.d_tag) {
    case DT_SYMTAB:
      symbolTableAddress =
          ResolveDynamicAddress(info, entry.d_un.d_ptr, sizeof(ElfW(Sym)));
      result->symbolTableFound = symbolTableAddress != 0;
      break;
    case DT_STRTAB:
      stringTableAddress = ResolveDynamicAddress(info, entry.d_un.d_ptr, 1);
      result->stringTableFound = stringTableAddress != 0;
      break;
    case DT_HASH:
      hashAddress =
          ResolveDynamicAddress(info, entry.d_un.d_ptr, 2 * sizeof(uint32_t));
      result->hashFound = hashAddress != 0;
      break;
    case DT_STRSZ:
      stringTableSize = static_cast<size_t>(entry.d_un.d_val);
      break;
    case DT_SYMENT:
      symbolEntrySize = static_cast<size_t>(entry.d_un.d_val);
      break;
    default:
      break;
    }
  }
  result->diagnosticStage = 30;
  if (symbolTableAddress == 0 || stringTableAddress == 0 || hashAddress == 0 ||
      stringTableSize == 0 || symbolEntrySize != sizeof(ElfW(Sym))) {
    return false;
  }

  const auto *hash = reinterpret_cast<const uint32_t *>(hashAddress);
  const size_t symbolCount = ANGLE_UNSAFE_BUFFERS(hash[1]);
  result->rawSymbolCount = symbolCount;
  result->diagnosticStage = 40;
  if (symbolCount == 0 ||
      symbolCount > std::numeric_limits<size_t>::max() / sizeof(ElfW(Sym)) ||
      !IsRangeInModule(info, symbolTableAddress,
                       symbolCount * sizeof(ElfW(Sym))) ||
      !IsRangeInModule(info, stringTableAddress, stringTableSize)) {
    return false;
  }

  result->diagnosticStage = 50;

  const auto *symbolTable =
      reinterpret_cast<const ElfW(Sym) *>(symbolTableAddress);
  const auto *stringTable = reinterpret_cast<const char *>(stringTableAddress);
  for (size_t symbolIndex = 0; symbolIndex < symbolCount; ++symbolIndex) {
    const ElfW(Sym) &symbol = ANGLE_UNSAFE_BUFFERS(symbolTable[symbolIndex]);
    if (symbol.st_name >= stringTableSize || symbol.st_shndx == SHN_UNDEF ||
        symbol.st_value == 0) {
      continue;
    }
    const char *nameStart = ANGLE_UNSAFE_BUFFERS(stringTable + symbol.st_name);
    std::string_view remaining(nameStart, stringTableSize - symbol.st_name);
    const size_t terminator = remaining.find('\0');
    if (terminator == std::string_view::npos) {
      continue;
    }
    const std::string_view name = remaining.substr(0, terminator);
    for (size_t allowlistIndex = 0; allowlistIndex < kAllowlistedSymbols.size();
         ++allowlistIndex) {
      if (name != kAllowlistedSymbols[allowlistIndex] ||
          result->symbols[allowlistIndex] != 0) {
        continue;
      }
      const uintptr_t address = info.dlpi_addr + symbol.st_value;
      if (IsRangeInModule(info, address, 1)) {
        result->symbols[allowlistIndex] = address;
        ++result->symbolCount;
      }
    }
  }
  result->diagnosticStage = 60;
  return true;
}

int FindAndResolveIl2Cpp(dl_phdr_info *info, size_t, void *opaque) {
  auto *result = static_cast<Il2CppDynamicProbe *>(opaque);
  if (info == nullptr || info->dlpi_name == nullptr ||
      std::string_view(info->dlpi_name).find("libil2cpp.so") ==
          std::string_view::npos) {
    return 0;
  }
  result->moduleFound = true;
  result->dynamicParsed = ResolveFromDynamic(*info, result);
  return 1;
}

struct UiProbeResult {
  bool success = false;
  uint32_t buttonCount = 0;
  uint32_t activeCount = 0;
  uint32_t interactableCount = 0;
  int32_t sceneHandle = 0;
  uint32_t diagnosticStage = 0;
  uint32_t methodMask = 0;
  uint32_t recordCount = 0;
  uint32_t recordTruncated = 0;
  uint32_t recordErrors = 0;
  std::array<ObserverButtonRecord, kMaxObserverButtons> records = {};
  uint32_t toggleRecordCount = 0;
  uint32_t toggleRecordTruncated = 0;
  uint32_t textRecordCount = 0;
  uint32_t textRecordTruncated = 0;
  uint32_t imageRecordCount = 0;
  uint32_t imageRecordTruncated = 0;
  uint32_t uiRecordErrors = 0;
  uint32_t uiRecordSkipped = 0;
  uint32_t uiMethodMask = 0;
  std::array<ObserverToggleRecord, kMaxObserverToggles> toggles = {};
  std::array<ObserverTextRecord, kMaxObserverTexts> texts = {};
  std::array<ObserverImageRecord, kMaxObserverImages> images = {};
};

template <size_t Size>
bool CopyBoundedString(std::string_view source,
                       std::array<char, Size> *destination) {
  static_assert(Size > 0);
  if (destination == nullptr) {
    return false;
  }
  const size_t copyLength = std::min(source.size(), Size - 1);
  if (copyLength > 0) {
    ANGLE_UNSAFE_TODO(
        std::memcpy(destination->data(), source.data(), copyLength));
  }
  (*destination)[copyLength] = '\0';
  return copyLength == source.size();
}

bool EndsWith(std::string_view value, std::string_view suffix) {
  return value.size() >= suffix.size() &&
         value.substr(value.size() - suffix.size()) == suffix;
}

bool ShouldEvaluateTopRaycast(std::string_view name, std::string_view path) {
  if (name == "ContractButton" && path == "ContractCanvas/ContractButton") {
    return true;
  }
  if (name == "LoginUI2(Clone)" &&
      EndsWith(path, "UICamera/Canvas/UIMain/LoginUI2(Clone)")) {
    return true;
  }
  if (name == "close_btn" &&
      EndsWith(path, "NewBulletinBoardUI(Clone)/bg/close_btn")) {
    return true;
  }
  if (name == "close" && EndsWith(path, "GuildMsgBoxUI(Clone)/frame/close")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "TaskScene(Clone)/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "EventUI(Clone)/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "MailUI(Clone)/adapt/CommonTitleAndBack/back_btn")) {
    return true;
  }
  if (name == "btn_managerMail" &&
      EndsWith(path,
               "MailUI(Clone)/adapt/main/content/left/left_content/bottom/"
               "btn_managerMail")) {
    return true;
  }
  if (name == "btnBack" &&
      EndsWith(path, "MailMgrMsgboxUI(Clone)/window/top/btnBack")) {
    return true;
  }
  if (name == "confirm_btn" &&
      EndsWith(path,
               "NewNavalTacticsSkillsPage(Clone)/frame/confirm_btn")) {
    return true;
  }
  if ((name == "confirm_btn" || name == "cancel_btn") &&
      EndsWith(path,
               "NewNavalTacticsLessonPage(Clone)/" + std::string(name))) {
    return true;
  }
  if (name == "btn_get" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/button_container/btn_get")) {
    return true;
  }
  if (name == "btn_delete" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/button_container/btn_delete")) {
    return true;
  }
  if (name == "CommissionInfoUI4Mellow(Clone)" &&
      EndsWith(path, "Overlay/UIMain/CommissionInfoUI4Mellow(Clone)")) {
    return true;
  }
  if (name == "finish_btn" &&
      (EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/event/"
                "frame/finish_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/class/"
                "frame/finish_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/technology/"
                "frame/finish_btn"))) {
    return true;
  }
  if (name == "go_btn" &&
      (EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/event/"
                "frame/go_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/class/"
                "frame/go_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/technology/"
                "frame/go_btn"))) {
    return true;
  }
  if (name == "GetAllButton" &&
      EndsWith(path, "TaskScene(Clone)/blur_panel/adapt/top/GetAllButton")) {
    return true;
  }
  if (name == "close" && (EndsWith(path, "AwardInfoUI(Clone)/items/close") ||
                          EndsWith(path, "AwardInfoUI1(Clone)/items/close"))) {
    return true;
  }
  if (name == "skipLayer" &&
      EndsWith(path, "ShipExpUI(Clone)/skipLayer")) {
    return true;
  }
  if ((name == "get_btn" || name == "go_btn") &&
      path.find("TaskScene(Clone)/pages/TaskListPage(Clone)/right_panel/"
                "content/") != std::string_view::npos &&
      EndsWith(path, name == "get_btn" ? "/frame/get_btn" : "/frame/go_btn")) {
    return true;
  }
  if (name == "bgNormal$" &&
      EndsWith(path, "/bgNormal$")) {
    constexpr std::string_view kPrefix =
        "EventUI(Clone)/scrollRect$/content/";
    const size_t prefix = path.find(kPrefix);
    if (prefix != std::string_view::npos) {
      const size_t indexBegin = prefix + kPrefix.size();
      const size_t indexEnd = path.size() - std::string_view("/bgNormal$").size();
      if (indexBegin < indexEnd &&
          std::all_of(path.begin() + indexBegin, path.begin() + indexEnd,
                      [](char value) { return value >= '0' && value <= '9'; })) {
        return true;
      }
    }
  }
  if ((name == "school_btn" || name == "backyard_btn" ||
       name == "commander_btn" || name == "dorm_btn") &&
      EndsWith(path,
               "MainLiveAreaUI(Clone)/" + std::string(name))) {
    return true;
  }
  if ((name == "return" &&
       EndsWith(path,
                "CourtYardUI(Clone)/main/topPanel/btns/topleft/return")) ||
      (name == "decorate_btn" &&
       EndsWith(path,
                "CourtYardUI(Clone)/main/bottomPanel/bottomright/"
                "decorate_btn")) ||
      ((name == "train_btn" || name == "feed_btn") &&
       EndsWith(path,
                "CourtYardUI(Clone)/main/bottomPanel/bottomleft/" +
                    std::string(name)))) {
    return true;
  }
  if (name == "confirm_btn" &&
      EndsWith(path,
               "BackYardStatisticsUI(Clone)/painting/confirm_btn")) {
    return true;
  }
  if (name == "btnBack" &&
      EndsWith(path,
               "NewNavalTacticsUI(Clone)/adpter/frame/btnBack")) {
    return true;
  }
  if ((name == "custom_button_1(Clone)" ||
       name == "custom_button_2(Clone)") &&
      EndsWith(path,
               "Msgbox(Clone)/window/button_container/"
               + std::string(name))) {
    return true;
  }
  if ((name == "back_button" &&
       EndsWith(path,
                "LevelMainScene(Clone)/top/top_chapter/back_button")) ||
      (name == "enter_main" &&
       EndsWith(path,
                "LevelMainScene(Clone)/entrance/enters/enter_main"))) {
    return true;
  }
  if (name == "main" &&
      path.find("LevelMainScene(Clone)/float/levels/items/Chapter_") !=
          std::string_view::npos &&
      EndsWith(path, "/main")) {
    const size_t marker = path.rfind("/Chapter_");
    if (marker != std::string_view::npos) {
      const size_t begin = marker + std::string_view("/Chapter_").size();
      const size_t end = path.size() - std::string_view("/main").size();
      const std::string_view stageId = path.substr(begin, end - begin);
      if (!stageId.empty() &&
          std::all_of(stageId.begin(), stageId.end(), [](char value) {
            return value >= '0' && value <= '9';
          })) {
        return true;
      }
    }
  }
  constexpr std::string_view kCampaignCellPrefix = "chapter_cell_quad_";
  if (name.rfind(kCampaignCellPrefix, 0) == 0 &&
      EndsWith(path,
               "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/" +
                   std::string(name))) {
    const std::string_view coordinate = name.substr(kCampaignCellPrefix.size());
    const size_t separator = coordinate.find('_');
    if (separator != std::string_view::npos && separator > 0 &&
        separator + 1 < coordinate.size() &&
        coordinate.find('_', separator + 1) == std::string_view::npos &&
        std::all_of(coordinate.begin(), coordinate.begin() + separator,
                    [](char value) { return value >= '0' && value <= '9'; }) &&
        std::all_of(coordinate.begin() + separator + 1, coordinate.end(),
                    [](char value) { return value >= '0' && value <= '9'; })) {
      return true;
    }
  }
  if (name == "NewBattleResultGradePage(Clone)" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
               "NewBattleResultGradePage(Clone)")) {
    return true;
  }
  if (name == "confirmBtn" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
               "NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn")) {
    return true;
  }
  if (name == "lock_fleet" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/"
               "right_stage/event/collapse/lock_fleet")) {
    return true;
  }
  if (name == "retreat_button" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/"
               "bottom_stage/Normal/retreat_button")) {
    return true;
  }
  if (name == "start" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/"
               "adapt/right/start")) {
    return true;
  }
  if ((name == "start_button" &&
       EndsWith(path, "LevelStageInfoView(Clone)/panel/start_button")) ||
      (name == "btnBack" &&
       EndsWith(path, "LevelStageInfoView(Clone)/panel/btnBack"))) {
    return true;
  }
  if ((name == "btnBack" &&
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/Fixed/btnBack")) ||
      (name == "start_button" &&
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/Fixed/start_button"))) {
    return true;
  }
  if ((name == "btn_select" || name == "btn_clear") &&
      (EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/" +
                    std::string(name)) ||
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/2/" +
                    std::string(name)) ||
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/sub/1/" +
                    std::string(name)))) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "Overlay/UIMain/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path,
               "ActivityMainUI(Clone)/adapt/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back" &&
      EndsWith(path,
               "SelectTechnologyUI(Clone)/blur_panel/adapt/top/back")) {
    return true;
  }
  if ((name == "technology_btn" || name == "blueprint_btn" ||
       name == "meta_btn") &&
      EndsWith(path,
               "SelectTechnologyUI(Clone)/frame/bg/" + std::string(name))) {
    return true;
  }
  if (name == "back" &&
      EndsWith(path, "TechnologyUI(Clone)/blur_panel/adapt/top/back")) {
    return true;
  }
  if (name == "btn_queue" &&
      EndsWith(path,
               "TechnologyUI(Clone)/blur_panel/adapt/left/btn_queue")) {
    return true;
  }
  if (name == "btn_award" &&
      EndsWith(path,
               "TechnologyUI(Clone)/blur_panel/adapt/right/btn_award")) {
    return true;
  }
  if (name == "selecte_panel" &&
      EndsWith(path,
               "TechnologyUI(Clone)/main/base_page/selecte_panel")) {
    return true;
  }
  if ((name == "start_btn" || name == "stop_btn" ||
       name == "finish_btn" || name == "queue_btn") &&
      EndsWith(path,
               "TechnologyUI(Clone)/main/base_page/selecte_panel/"
               "technology_card/frame/btns/" + std::string(name))) {
    return true;
  }
  if (name.size() == 1 && name[0] >= '1' && name[0] <= '5' &&
      EndsWith(path,
               "TechnologyUI(Clone)/main/base_page/srcoll_rect/content/" +
                   std::string(name))) {
    return true;
  }
  if (name == "onekey" &&
      EndsWith(path, "CourtYardUI(Clone)/main/rightPanel/onekey")) {
    return true;
  }
  if (name == "close" &&
      EndsWith(path, "BackYardFeedUI(Clone)/close")) {
    return true;
  }
  if (name == "cancel_btn" &&
      EndsWith(path,
               "BackYardFeedUI(Clone)/BackYardFeedShopPanel(Clone)/"
               "frame/cancel_btn")) {
    return true;
  }
  if (name == "start_btn" &&
      EndsWith(path,
               "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/"
               "start_btn")) {
    return true;
  }
  if ((name == "add" || name == "add(Clone)") &&
      EndsWith(path,
               "NewNavalTacticsUI(Clone)/adpter/"
               "NewNavalTacticsStudentsPage(Clone)/" +
                   std::string(name))) {
    return true;
  }
  if ((name == "confirm_btn" || name == "cancel_btn" ||
       name == "close_btn" || name == "minus" || name == "add" ||
       name == "max") &&
      EndsWith(path,
               name == "confirm_btn"
                   ? "BuildShipMsgBoxUI(Clone)/window/btns/confirm_btn"
               : name == "cancel_btn"
                   ? "BuildShipMsgBoxUI(Clone)/window/btns/cancel_btn"
               : name == "close_btn"
                   ? "BuildShipMsgBoxUI(Clone)/window/close_btn"
               : name == "minus"
                   ? "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/minus"
               : name == "add"
                   ? "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/add"
                   : "BuildShipMsgBoxUI(Clone)/window/content/max")) {
    return true;
  }
  if ((name == "confirm_button" || name == "cancel_button") &&
      EndsWith(path,
               "DockyardUI(Clone)/../blur_panel/select_panel/" +
                   std::string(name))) {
    return true;
  }
  if ((name == "confirm_button" || name == "cancel_button") &&
      EndsWith(path,
               "Overlay/UIMain/blur_panel/select_panel/" +
                   std::string(name))) {
    return true;
  }
  if (name == "back" &&
      EndsWith(path, "Overlay/UIMain/blur_panel/adapt/top/back")) {
    return true;
  }
  if (path.find("DockyardUI(Clone)/main/ship_container/ships/") !=
          std::string_view::npos &&
      EndsWith(path, "/" + std::string(name)) && name.size() >= 6 &&
      name.size() <= 8 &&
      std::all_of(name.begin(), name.end(),
                  [](char value) { return value >= '0' && value <= '9'; })) {
    return true;
  }
  struct Target {
    std::string_view name;
    std::string_view suffix;
  };
  constexpr std::array<Target, 11> kMainButtons = {
      Target{"battle", "frame/right/1/battle"},
      Target{"formation", "frame/right/1/formation"},
      Target{"settings", "frame/top/btns/settings"},
      Target{"mail", "frame/top/btns/mail"},
      Target{"shop", "frame/bottom/frame/shop"},
      Target{"dock", "frame/bottom/frame/dock"},
      Target{"task", "frame/bottom/frame/task"},
      Target{"build", "frame/bottom/frame/build"},
      Target{"live", "frame/bottom/frame/live"},
      Target{"tech", "frame/bottom/frame/tech"},
      Target{"extend", "frame/left/extend"},
  };
  return std::any_of(
      kMainButtons.begin(), kMainButtons.end(), [&](const Target &target) {
        return name == target.name && EndsWith(path, target.suffix);
      });
}

bool ShouldEvaluateToggleTopRaycast(std::string_view name,
                                    std::string_view path) {
  if (name.size() == 5 && name.substr(0, 4) == "item" &&
      name[4] >= '1' && name[4] <= '6' &&
      EndsWith(path,
               "LevelFleetSelectView(Clone)/mask/list/" +
                   std::string(name))) {
    return true;
  }
  if ((name == "build_btn" || name == "queue_btn") &&
      EndsWith(path,
               "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/" +
                   std::string(name))) {
    return true;
  }
  if (name == "frame" &&
      path.find("BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/"
                "toggle_bg/bg/toggles/") != std::string_view::npos) {
    constexpr std::array<std::string_view, 3> kBuildPools = {
        "light", "heavy", "special",
    };
    return std::any_of(
        kBuildPools.begin(), kBuildPools.end(), [&](std::string_view pool) {
          return EndsWith(path,
                          "/toggles/" + std::string(pool) + "/frame");
        });
  }
  if (name == "all" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/all")) {
    return true;
  }
  if (name == "filter" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter")) {
    return true;
  }
  return (name == "toggle_tpl" || name == "toggle_tpl(Clone)") &&
         EndsWith(path,
                  name == "toggle_tpl"
                      ? "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/"
                        "filter/content/toggle_tpl"
                      : "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/"
                        "filter/content/toggle_tpl(Clone)");
}

bool ShouldEvaluateImageTopRaycast(std::string_view name,
                                   std::string_view path) {
  if (name == "icon_bg" &&
      path.find("BackYardFeedUI(Clone)/frame/food_5000") !=
          std::string_view::npos) {
    constexpr std::array<std::string_view, 6> kDormFoods = {
        "50001", "50002", "50003", "50004", "50005", "50006",
    };
    return std::any_of(
        kDormFoods.begin(), kDormFoods.end(), [&](std::string_view food) {
          return EndsWith(path,
                          "/food_" + std::string(food) + "/icon_bg");
        });
  }
  if ((name == "item" || name == "item(Clone)") &&
      EndsWith(path,
               "NewNavalTacticsLessonPage(Clone)/items/scorll/content/" +
                   std::string(name))) {
    return true;
  }
  if ((name == "skill" || name == "skill(Clone)") &&
      EndsWith(path,
               "NewNavalTacticsSkillsPage(Clone)/frame/skill_container/"
               "content/" +
                   std::string(name))) {
    return true;
  }
  if (name != "Image") {
    return false;
  }
  if (path.find(
          "TaskScene(Clone)/blur_panel/adapt/left_length/frame/tagRoot/") !=
      std::string_view::npos) {
    constexpr std::array<std::string_view, 6> kMissionTabs = {
        "all", "scenario", "branch", "routine", "weekly", "activity",
    };
    return std::any_of(
        kMissionTabs.begin(), kMissionTabs.end(), [&](std::string_view tab) {
          const std::string direct = "/tagRoot/" + std::string(tab) + "/Image";
          const std::string selected =
              "/tagRoot/" + std::string(tab) + "/selected/Image";
          return EndsWith(path, direct) || EndsWith(path, selected);
        });
  }
  if (path.find("EventUI(Clone)/blur_panel/adapt/left_length/frame/"
                "scroll_rect/tagRoot/") != std::string_view::npos) {
    constexpr std::array<std::string_view, 2> kCommissionTabs = {
        "daily_btn", "urgency_btn",
    };
    return std::any_of(
        kCommissionTabs.begin(), kCommissionTabs.end(),
        [&](std::string_view tab) {
          const std::string direct = "/tagRoot/" + std::string(tab) + "/Image";
          const std::string selected =
              "/tagRoot/" + std::string(tab) + "/selected/Image";
          return EndsWith(path, direct) || EndsWith(path, selected);
        });
  }
  if (EndsWith(path,
               "EventUI(Clone)/blur_panel/adapt/scroll_bar/Image")) {
    return true;
  }
  return false;
}

struct LoadedObjectCollector {
  // FindObjectsOfTypeAll omits destroyed components but can still return
  // inactive objects retained by repeated overlays.  Keep the temporary set
  // bounded independently from the much smaller active typed record set.
  std::array<void *, 4096> objects = {};
  size_t count = 0;
  bool truncated = false;
};

const UiProbeResult &ProbeUnityUi(const Il2CppDynamicProbe &probe,
                                 const void *coreImage, const void *uiImage,
                                 const void *uiModuleImage,
                                 const void *textMeshProImage, int screenWidth,
                                 int screenHeight) {
  // Campaign maps need more complete Image records than overlay pages.  Keep
  // the large reusable collection out of UnityMain's comparatively small
  // native stack; only scalar counters need resetting between generations.
  static thread_local UiProbeResult result;
  result.success = false;
  result.buttonCount = 0;
  result.activeCount = 0;
  result.interactableCount = 0;
  result.sceneHandle = 0;
  result.diagnosticStage = 0;
  result.methodMask = 0;
  result.recordCount = 0;
  result.recordTruncated = 0;
  result.recordErrors = 0;
  result.toggleRecordCount = 0;
  result.toggleRecordTruncated = 0;
  result.textRecordCount = 0;
  result.textRecordTruncated = 0;
  result.imageRecordCount = 0;
  result.imageRecordTruncated = 0;
  result.uiRecordErrors = 0;
  result.uiRecordSkipped = 0;
  result.uiMethodMask = 0;
  result.diagnosticStage = 10;
  if (coreImage == nullptr || uiImage == nullptr) {
    return result;
  }

  using ClassFromName = void *(*)(const void *, const char *, const char *);
  using ClassGetMethodFromName = const void *(*)(void *, const char *, int);
  using RuntimeInvoke = void *(*)(const void *, void *, void **, void **);
  using ObjectUnbox = void *(*)(void *);
  using ClassGetParent = void *(*)(void *);
  using ClassGetType = const void *(*)(void *);
  using TypeGetObject = void *(*)(const void *);
  using ArrayLength = uintptr_t (*)(void *);
  using StringLength = int32_t (*)(void *);
  using StringChars = const uint16_t *(*)(void *);
  using ObjectNew = void *(*)(const void *);
  using MethodGetParam = const void *(*)(const void *, uint32_t);
  using MethodGetReturnType = const void *(*)(const void *);
  using ClassFromType = void *(*)(const void *);
  using ClassGetFieldFromName = void *(*)(void *, const char *);
  using FieldGetValue = void (*)(void *, void *, void *);

  const auto classFromName = reinterpret_cast<ClassFromName>(probe.symbols[7]);
  const auto classGetMethodFromName =
      reinterpret_cast<ClassGetMethodFromName>(probe.symbols[10]);
  const auto runtimeInvoke = reinterpret_cast<RuntimeInvoke>(probe.symbols[11]);
  const auto objectUnbox = reinterpret_cast<ObjectUnbox>(probe.symbols[12]);
  const auto classGetParent =
      reinterpret_cast<ClassGetParent>(probe.symbols[16]);
  const auto classGetType = reinterpret_cast<ClassGetType>(probe.symbols[8]);
  const auto typeGetObject = reinterpret_cast<TypeGetObject>(probe.symbols[9]);
  const auto arrayLength = reinterpret_cast<ArrayLength>(probe.symbols[13]);
  const auto stringLength = reinterpret_cast<StringLength>(probe.symbols[14]);
  const auto stringChars = reinterpret_cast<StringChars>(probe.symbols[15]);
  const auto objectNew = reinterpret_cast<ObjectNew>(probe.symbols[26]);
  const auto methodGetParam =
      reinterpret_cast<MethodGetParam>(probe.symbols[27]);
  const auto methodGetReturnType =
      reinterpret_cast<MethodGetReturnType>(probe.symbols[28]);
  const auto classFromType = reinterpret_cast<ClassFromType>(probe.symbols[29]);
  const auto classGetFieldFromName =
      reinterpret_cast<ClassGetFieldFromName>(probe.symbols[30]);
  const auto fieldGetValue = reinterpret_cast<FieldGetValue>(probe.symbols[31]);

  void *sceneManagerClass =
      classFromName(coreImage, "UnityEngine.SceneManagement", "SceneManager");
  void *resourcesClass =
      classFromName(coreImage, "UnityEngine", "Resources");
  void *buttonClass = classFromName(uiImage, "UnityEngine.UI", "Button");
  void *toggleClass = classFromName(uiImage, "UnityEngine.UI", "Toggle");
  void *legacyTextClass = classFromName(uiImage, "UnityEngine.UI", "Text");
  void *imageClass = classFromName(uiImage, "UnityEngine.UI", "Image");
  void *tmpTextClass =
      textMeshProImage != nullptr
          ? classFromName(textMeshProImage, "TMPro", "TextMeshProUGUI")
          : nullptr;
  if (sceneManagerClass == nullptr || buttonClass == nullptr) {
    return result;
  }
  result.diagnosticStage = 20;

  const void *getActiveScene =
      classGetMethodFromName(sceneManagerClass, "GetActiveScene", 0);
  auto findMethodInHierarchy = [&](void *klass, const char *name,
                                   int parameterCount = 0) {
    for (int depth = 0; klass != nullptr && depth < 8; ++depth) {
      const void *method = classGetMethodFromName(klass, name, parameterCount);
      if (method != nullptr) {
        return method;
      }
      klass = classGetParent(klass);
    }
    return static_cast<const void *>(nullptr);
  };
  const void *findObjectsOfTypeAll =
      resourcesClass != nullptr
          ? findMethodInHierarchy(resourcesClass, "FindObjectsOfTypeAll", 1)
          : nullptr;
  const void *getActiveAndEnabled =
      findMethodInHierarchy(buttonClass, "get_isActiveAndEnabled");
  const void *getInteractable =
      findMethodInHierarchy(buttonClass, "get_interactable");
  const void *getToggleActiveAndEnabled =
      toggleClass != nullptr
          ? findMethodInHierarchy(toggleClass, "get_isActiveAndEnabled")
          : nullptr;
  const void *getToggleInteractable =
      toggleClass != nullptr
          ? findMethodInHierarchy(toggleClass, "get_interactable")
          : nullptr;
  const void *getToggleIsOn =
      toggleClass != nullptr ? findMethodInHierarchy(toggleClass, "get_isOn")
                             : nullptr;
  const void *getLegacyTextActiveAndEnabled =
      legacyTextClass != nullptr
          ? findMethodInHierarchy(legacyTextClass, "get_isActiveAndEnabled")
          : nullptr;
  const void *getLegacyText =
      legacyTextClass != nullptr
          ? findMethodInHierarchy(legacyTextClass, "get_text")
          : nullptr;
  const void *getTmpTextActiveAndEnabled =
      tmpTextClass != nullptr
          ? findMethodInHierarchy(tmpTextClass, "get_isActiveAndEnabled")
          : nullptr;
  const void *getTmpText = tmpTextClass != nullptr
                               ? findMethodInHierarchy(tmpTextClass, "get_text")
                               : nullptr;
  const void *getImageActiveAndEnabled =
      imageClass != nullptr
          ? findMethodInHierarchy(imageClass, "get_isActiveAndEnabled")
          : nullptr;
  const void *getImageSprite =
      imageClass != nullptr ? findMethodInHierarchy(imageClass, "get_sprite")
                            : nullptr;
  const void *getImageColor =
      imageClass != nullptr ? findMethodInHierarchy(imageClass, "get_color")
                            : nullptr;
  const void *getImageFillAmount =
      imageClass != nullptr
          ? findMethodInHierarchy(imageClass, "get_fillAmount")
          : nullptr;
  const void *getImageRaycastTarget =
      imageClass != nullptr
          ? findMethodInHierarchy(imageClass, "get_raycastTarget")
          : nullptr;
  result.methodMask = 0x1u | (getActiveScene != nullptr ? 0x2u : 0u) |
                      (getActiveAndEnabled != nullptr ? 0x4u : 0u) |
                      (getInteractable != nullptr ? 0x8u : 0u);
  if (getActiveScene == nullptr || findObjectsOfTypeAll == nullptr ||
      arrayLength == nullptr || getActiveAndEnabled == nullptr ||
      getInteractable == nullptr) {
    return result;
  }
  result.uiMethodMask =
      (toggleClass != nullptr && getToggleActiveAndEnabled != nullptr &&
               getToggleInteractable != nullptr && getToggleIsOn != nullptr
           ? 0x1u
           : 0u) |
      (legacyTextClass != nullptr && getLegacyTextActiveAndEnabled != nullptr &&
               getLegacyText != nullptr
           ? 0x2u
           : 0u) |
      (tmpTextClass != nullptr && getTmpTextActiveAndEnabled != nullptr &&
               getTmpText != nullptr
           ? 0x4u
           : 0u) |
      (imageClass != nullptr && getImageActiveAndEnabled != nullptr &&
               getImageSprite != nullptr && getImageColor != nullptr &&
               getImageFillAmount != nullptr && getImageRaycastTarget != nullptr
           ? 0x8u
           : 0u);
  result.diagnosticStage = 30;

  void *gameObjectClass = classFromName(coreImage, "UnityEngine", "GameObject");
  void *transformClass = classFromName(coreImage, "UnityEngine", "Transform");
  void *rectTransformClass =
      classFromName(coreImage, "UnityEngine", "RectTransform");
  void *cameraClass = classFromName(coreImage, "UnityEngine", "Camera");
  void *eventSystemClass =
      classFromName(uiImage, "UnityEngine.EventSystems", "EventSystem");
  void *pointerEventDataClass =
      classFromName(uiImage, "UnityEngine.EventSystems", "PointerEventData");
  void *canvasClass =
      uiModuleImage != nullptr
          ? classFromName(uiModuleImage, "UnityEngine", "Canvas")
          : nullptr;
  const void *getGameObject =
      findMethodInHierarchy(buttonClass, "get_gameObject");
  const void *getComponentInParent =
      findMethodInHierarchy(buttonClass, "GetComponentInParent", 2);
  const void *getName = gameObjectClass != nullptr
                            ? findMethodInHierarchy(gameObjectClass, "get_name")
                            : nullptr;
  const void *getActiveInHierarchy =
      gameObjectClass != nullptr
          ? findMethodInHierarchy(gameObjectClass, "get_activeInHierarchy")
          : nullptr;
  const void *getTransform =
      gameObjectClass != nullptr
          ? findMethodInHierarchy(gameObjectClass, "get_transform")
          : nullptr;
  const void *getParent =
      transformClass != nullptr
          ? findMethodInHierarchy(transformClass, "get_parent")
          : nullptr;
  const void *getPosition =
      transformClass != nullptr
          ? findMethodInHierarchy(transformClass, "get_position")
          : nullptr;
  const void *transformPoint =
      transformClass != nullptr
          ? findMethodInHierarchy(transformClass, "TransformPoint", 1)
          : nullptr;
  const void *getRect =
      rectTransformClass != nullptr
          ? findMethodInHierarchy(rectTransformClass, "get_rect")
          : nullptr;
  const void *getWorldCamera =
      canvasClass != nullptr
          ? findMethodInHierarchy(canvasClass, "get_worldCamera")
          : nullptr;
  const void *getRenderMode =
      canvasClass != nullptr
          ? findMethodInHierarchy(canvasClass, "get_renderMode")
          : nullptr;
  const void *worldToScreenPoint =
      cameraClass != nullptr
          ? findMethodInHierarchy(cameraClass, "WorldToScreenPoint", 1)
          : nullptr;
  const void *getCurrentEventSystem =
      eventSystemClass != nullptr
          ? findMethodInHierarchy(eventSystemClass, "get_current")
          : nullptr;
  const void *raycastAll =
      eventSystemClass != nullptr
          ? findMethodInHierarchy(eventSystemClass, "RaycastAll", 2)
          : nullptr;
  const void *pointerEventDataConstructor =
      pointerEventDataClass != nullptr
          ? findMethodInHierarchy(pointerEventDataClass, ".ctor", 1)
          : nullptr;
  const void *setPointerPosition =
      pointerEventDataClass != nullptr
          ? findMethodInHierarchy(pointerEventDataClass, "set_position", 1)
          : nullptr;
  void *canvasTypeObject = canvasClass != nullptr
                               ? typeGetObject(classGetType(canvasClass))
                               : nullptr;

  void *raycastListClass = nullptr;
  if (raycastAll != nullptr) {
    const void *listType = methodGetParam(raycastAll, 1);
    raycastListClass = listType != nullptr ? classFromType(listType) : nullptr;
  }
  const void *raycastListConstructor =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, ".ctor")
          : nullptr;
  const void *clearRaycastList =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, "Clear")
          : nullptr;
  const void *getRaycastCount =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, "get_Count")
          : nullptr;
  const void *getRaycastItem =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, "get_Item", 1)
          : nullptr;
  void *raycastResultClass = nullptr;
  if (getRaycastItem != nullptr) {
    const void *resultType = methodGetReturnType(getRaycastItem);
    raycastResultClass =
        resultType != nullptr ? classFromType(resultType) : nullptr;
  }
  void *raycastGameObjectField =
      raycastResultClass != nullptr
          ? classGetFieldFromName(raycastResultClass, "m_GameObject")
          : nullptr;

  struct Vector2 {
    float x;
    float y;
  };
  struct Vector3 {
    float x;
    float y;
    float z;
  };
  struct Rect {
    float x;
    float y;
    float width;
    float height;
  };

  auto invokeObject = [&](const void *method, void *instance,
                          void **arguments = nullptr) {
    if (method == nullptr) {
      return static_cast<void *>(nullptr);
    }
    void *invokeException = nullptr;
    void *value = runtimeInvoke(method, instance, arguments, &invokeException);
    return invokeException == nullptr ? value : static_cast<void *>(nullptr);
  };
  auto invokeVoid = [&](const void *method, void *instance,
                        void **arguments = nullptr) {
    if (method == nullptr) {
      return false;
    }
    void *invokeException = nullptr;
    runtimeInvoke(method, instance, arguments, &invokeException);
    return invokeException == nullptr;
  };
  auto invokeValue = [&](const void *method, void *instance, void **arguments,
                         void *destination, size_t destinationSize) {
    void *boxed = invokeObject(method, instance, arguments);
    if (boxed == nullptr) {
      return false;
    }
    void *unboxed = objectUnbox(boxed);
    if (unboxed == nullptr) {
      return false;
    }
    ANGLE_UNSAFE_TODO(std::memcpy(destination, unboxed, destinationSize));
    return true;
  };
  auto readString = [&](void *stringObject) {
    std::string value;
    if (stringObject == nullptr) {
      return value;
    }
    const int32_t length = stringLength(stringObject);
    const uint16_t *characters = stringChars(stringObject);
    if (length <= 0 || length > 1024 || characters == nullptr) {
      return value;
    }
    value.reserve(static_cast<size_t>(length));
    for (int32_t index = 0; index < length; ++index) {
      uint32_t codePoint = ANGLE_UNSAFE_BUFFERS(characters[index]);
      if (codePoint >= 0xD800u && codePoint <= 0xDBFFu && index + 1 < length) {
        const uint32_t low = ANGLE_UNSAFE_BUFFERS(characters[index + 1]);
        if (low >= 0xDC00u && low <= 0xDFFFu) {
          codePoint =
              0x10000u + ((codePoint - 0xD800u) << 10u) + (low - 0xDC00u);
          ++index;
        }
      }
      if (codePoint <= 0x7Fu) {
        value.push_back(static_cast<char>(codePoint));
      } else if (codePoint <= 0x7FFu) {
        value.push_back(static_cast<char>(0xC0u | (codePoint >> 6u)));
        value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
      } else if (codePoint <= 0xFFFFu) {
        value.push_back(static_cast<char>(0xE0u | (codePoint >> 12u)));
        value.push_back(static_cast<char>(0x80u | ((codePoint >> 6u) & 0x3Fu)));
        value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
      } else if (codePoint <= 0x10FFFFu) {
        value.push_back(static_cast<char>(0xF0u | (codePoint >> 18u)));
        value.push_back(
            static_cast<char>(0x80u | ((codePoint >> 12u) & 0x3Fu)));
        value.push_back(static_cast<char>(0x80u | ((codePoint >> 6u) & 0x3Fu)));
        value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
      }
    }
    return value;
  };
  auto invokeString = [&](void *instance) {
    return readString(invokeObject(getName, instance));
  };
  auto invokeBoolean = [&](const void *method, void *instance, bool *value) {
    void *invokeException = nullptr;
    void *boxed = runtimeInvoke(method, instance, nullptr, &invokeException);
    if (invokeException != nullptr || boxed == nullptr) {
      return false;
    }
    void *unboxed = objectUnbox(boxed);
    if (unboxed == nullptr) {
      return false;
    }
    uint8_t raw = 0;
    ANGLE_UNSAFE_TODO(std::memcpy(&raw, unboxed, sizeof(raw)));
    *value = raw != 0;
    return true;
  };

  void *eventSystem = invokeObject(getCurrentEventSystem, nullptr);
  void *pointerEventData = pointerEventDataClass != nullptr
                               ? objectNew(pointerEventDataClass)
                               : nullptr;
  void *raycastResults =
      raycastListClass != nullptr ? objectNew(raycastListClass) : nullptr;
  bool raycastReady =
      eventSystem != nullptr && pointerEventData != nullptr &&
      raycastResults != nullptr && pointerEventDataConstructor != nullptr &&
      setPointerPosition != nullptr && raycastAll != nullptr &&
      raycastListConstructor != nullptr && clearRaycastList != nullptr &&
      getRaycastCount != nullptr && getRaycastItem != nullptr &&
      raycastGameObjectField != nullptr;
  if (raycastReady) {
    void *pointerArguments[] = {eventSystem};
    raycastReady = invokeVoid(pointerEventDataConstructor, pointerEventData,
                              pointerArguments) &&
                   invokeVoid(raycastListConstructor, raycastResults);
  }

  auto topRaycastMatches = [&](void *buttonTransform, const Vector2 &position,
                               bool *evaluated) {
    *evaluated = false;
    if (!raycastReady || buttonTransform == nullptr) {
      return false;
    }
    if (!invokeVoid(clearRaycastList, raycastResults)) {
      return false;
    }
    Vector2 pointerPosition = position;
    void *positionArguments[] = {&pointerPosition};
    if (!invokeVoid(setPointerPosition, pointerEventData, positionArguments)) {
      return false;
    }
    void *raycastArguments[] = {pointerEventData, raycastResults};
    if (!invokeVoid(raycastAll, eventSystem, raycastArguments)) {
      return false;
    }
    int32_t count = 0;
    if (!invokeValue(getRaycastCount, raycastResults, nullptr, &count,
                     sizeof(count)) ||
        count < 0 || count > 4096) {
      return false;
    }
    *evaluated = true;
    if (count == 0) {
      return false;
    }
    int32_t firstIndex = 0;
    void *itemArguments[] = {&firstIndex};
    void *firstResult =
        invokeObject(getRaycastItem, raycastResults, itemArguments);
    if (firstResult == nullptr) {
      return false;
    }
    void *topGameObject = nullptr;
    fieldGetValue(firstResult, raycastGameObjectField, &topGameObject);
    if (topGameObject == nullptr) {
      return false;
    }
    void *topTransform = invokeObject(getTransform, topGameObject);
    for (int depth = 0; topTransform != nullptr && depth < 24; ++depth) {
      if (topTransform == buttonTransform) {
        return true;
      }
      topTransform = getParent != nullptr
                         ? invokeObject(getParent, topTransform)
                         : nullptr;
    }
    return false;
  };

  auto populateControlRecord = [&](void *component, bool interactable,
                                   ObserverButtonRecord *record) {
    if (component == nullptr || record == nullptr || getGameObject == nullptr ||
        getTransform == nullptr || getName == nullptr ||
        getActiveInHierarchy == nullptr) {
      return false;
    }
    void *gameObject = invokeObject(getGameObject, component);
    void *transform = gameObject != nullptr
                          ? invokeObject(getTransform, gameObject)
                          : nullptr;
    bool activeInHierarchy = false;
    if (gameObject == nullptr || transform == nullptr ||
        !invokeValue(getActiveInHierarchy, gameObject, nullptr,
                     &activeInHierarchy, sizeof(uint8_t)) ||
        !activeInHierarchy) {
      return false;
    }

    record->flags = 0x1u | 0x2u | (interactable ? 0x4u : 0u);
    const std::string objectName = invokeString(gameObject);
    if (!objectName.empty()) {
      if (!CopyBoundedString(objectName, &record->name)) {
        record->flags |= 0x200u;
      }
      record->flags |= 0x8u;
    }

    std::string path;
    void *currentTransform = transform;
    for (int depth = 0; currentTransform != nullptr && depth < 24; ++depth) {
      const std::string part = invokeString(currentTransform);
      if (part.empty()) {
        break;
      }
      path = path.empty() ? part : part + "/" + path;
      currentTransform = getParent != nullptr
                             ? invokeObject(getParent, currentTransform)
                             : nullptr;
    }
    if (!path.empty()) {
      if (!CopyBoundedString(path, &record->path)) {
        record->flags |= 0x200u;
      }
      record->flags |= 0x10u;
    }

    Vector3 world = {};
    if (getPosition != nullptr &&
        invokeValue(getPosition, transform, nullptr, &world, sizeof(world))) {
      record->worldX = world.x;
      record->worldY = world.y;
      record->worldZ = world.z;
      record->flags |= 0x20u;
    }
    Rect rect = {};
    if (getRect != nullptr &&
        invokeValue(getRect, transform, nullptr, &rect, sizeof(rect))) {
      record->rectX = rect.x;
      record->rectY = rect.y;
      record->rectWidth = rect.width;
      record->rectHeight = rect.height;
      record->flags |= 0x40u;
    }

    void *canvas = nullptr;
    if (getComponentInParent != nullptr && canvasTypeObject != nullptr) {
      uint8_t includeInactive = 0;
      void *arguments[] = {canvasTypeObject, &includeInactive};
      canvas = invokeObject(getComponentInParent, component, arguments);
    }
    int32_t renderMode = -1;
    if (canvas != nullptr) {
      const std::string canvasName = invokeString(canvas);
      if (!canvasName.empty() &&
          !CopyBoundedString(canvasName, &record->canvasName)) {
        record->flags |= 0x200u;
      }
      if (getRenderMode != nullptr) {
        invokeValue(getRenderMode, canvas, nullptr, &renderMode,
                    sizeof(renderMode));
      }
      record->canvasRenderMode = renderMode;
      record->flags |= 0x80u;
    }

    void *camera = canvas != nullptr && getWorldCamera != nullptr
                       ? invokeObject(getWorldCamera, canvas)
                       : nullptr;
    auto projectToScreen = [&](const Vector3 &worldPoint,
                               Vector3 *screenPoint) {
      if (camera != nullptr && worldToScreenPoint != nullptr) {
        Vector3 argument = worldPoint;
        void *arguments[] = {&argument};
        return invokeValue(worldToScreenPoint, camera, arguments, screenPoint,
                           sizeof(*screenPoint));
      }
      if (renderMode == 0) {
        *screenPoint = worldPoint;
        return true;
      }
      return false;
    };
    Vector3 screen = {};
    if ((record->flags & 0x20u) != 0 && projectToScreen(world, &screen)) {
      record->screenX = screen.x;
      record->screenY = screen.y;
      record->adbX = screen.x;
      record->adbY = static_cast<float>(screenHeight) - screen.y;
      record->flags |= 0x100u;
    }
    if (transformPoint == nullptr || (record->flags & 0x40u) == 0) {
      return true;
    }

    const std::array<Vector3, 4> localCorners = {
        Vector3{rect.x, rect.y, 0.0f},
        Vector3{rect.x + rect.width, rect.y, 0.0f},
        Vector3{rect.x + rect.width, rect.y + rect.height, 0.0f},
        Vector3{rect.x, rect.y + rect.height, 0.0f},
    };
    float left = std::numeric_limits<float>::max();
    float bottom = std::numeric_limits<float>::max();
    float right = std::numeric_limits<float>::lowest();
    float top = std::numeric_limits<float>::lowest();
    bool boundsValid = true;
    for (const Vector3 &localCorner : localCorners) {
      Vector3 localArgument = localCorner;
      void *arguments[] = {&localArgument};
      Vector3 worldCorner = {};
      Vector3 screenCorner = {};
      if (!invokeValue(transformPoint, transform, arguments, &worldCorner,
                       sizeof(worldCorner)) ||
          !projectToScreen(worldCorner, &screenCorner)) {
        boundsValid = false;
        break;
      }
      left = std::min(left, screenCorner.x);
      bottom = std::min(bottom, screenCorner.y);
      right = std::max(right, screenCorner.x);
      top = std::max(top, screenCorner.y);
    }
    if (boundsValid) {
      record->screenLeft = left;
      record->screenBottom = bottom;
      record->screenRight = right;
      record->screenTop = top;
      record->adbLeft = left;
      record->adbTop = static_cast<float>(screenHeight) - top;
      record->adbRight = right;
      record->adbBottom = static_cast<float>(screenHeight) - bottom;
      record->flags |= 0x400u;
    }
    return true;
  };

  void *exception = nullptr;
  void *sceneBox = runtimeInvoke(getActiveScene, nullptr, nullptr, &exception);
  if (exception != nullptr || sceneBox == nullptr) {
    return result;
  }
  result.diagnosticStage = 40;
  void *sceneValue = objectUnbox(sceneBox);
  if (sceneValue == nullptr) {
    return result;
  }
  result.diagnosticStage = 50;
  ANGLE_UNSAFE_TODO(
      std::memcpy(&result.sceneHandle, sceneValue, sizeof(result.sceneHandle)));

  struct ManagedArrayHeader {
    void *klass;
    void *monitor;
    void *bounds;
    uintptr_t maxLength;
  };
  static_assert(sizeof(ManagedArrayHeader) == 4 * sizeof(void *));

  auto collectLoadedInstances = [&](void *klass,
                                    LoadedObjectCollector *collector) {
    if (klass == nullptr || collector == nullptr || classGetType == nullptr ||
        typeGetObject == nullptr) {
      return false;
    }
    const void *type = classGetType(klass);
    void *typeObject = type != nullptr ? typeGetObject(type) : nullptr;
    if (typeObject == nullptr) {
      return false;
    }
    void *arguments[] = {typeObject};
    void *objects = invokeObject(findObjectsOfTypeAll, nullptr, arguments);
    if (objects == nullptr) {
      return false;
    }
    const uintptr_t length = arrayLength(objects);
    const auto *header = static_cast<const ManagedArrayHeader *>(objects);
    if (header->maxLength != length) {
      return false;
    }
    const size_t copyCount = std::min(
        static_cast<size_t>(length), collector->objects.size());
    const auto *elements = ANGLE_UNSAFE_BUFFERS(
        reinterpret_cast<void *const *>(
            reinterpret_cast<const uint8_t *>(objects) + sizeof(*header)));
    for (size_t index = 0; index < copyCount; ++index) {
      collector->objects[index] = ANGLE_UNSAFE_BUFFERS(elements[index]);
    }
    collector->count = copyCount;
    collector->truncated = length > collector->objects.size();
    return true;
  };

  LoadedObjectCollector collector;
  result.diagnosticStage = 60;
  if (!collectLoadedInstances(buttonClass, &collector)) {
    return result;
  }
  result.recordTruncated |= collector.truncated ? 1u : 0u;
  result.diagnosticStage = 90;
  const size_t length = collector.count;
  for (size_t index = 0; index < length; ++index) {
    void *button = collector.objects[index];
    if (button == nullptr) {
      continue;
    }
    bool active = false;
    bool interactable = false;
    if (!invokeBoolean(getActiveAndEnabled, button, &active) ||
        !invokeBoolean(getInteractable, button, &interactable)) {
      // Unity can destroy a component between enumeration and the typed
      // accessors below. Omitting it is fail-closed at the semantic target
      // layer; aborting here would suppress every valid Button in the scene.
      continue;
    }
    ++result.buttonCount;
    result.activeCount += active ? 1u : 0u;
    result.interactableCount += interactable ? 1u : 0u;

    if (!active || getGameObject == nullptr || getTransform == nullptr ||
        getName == nullptr) {
      continue;
    }
    void *gameObject = invokeObject(getGameObject, button);
    void *transform = invokeObject(getTransform, gameObject);
    bool activeInHierarchy = false;
    if (gameObject == nullptr || transform == nullptr ||
        getActiveInHierarchy == nullptr ||
        !invokeValue(getActiveInHierarchy, gameObject, nullptr,
                     &activeInHierarchy, sizeof(uint8_t))) {
      ++result.recordErrors;
      continue;
    }
    if (!activeInHierarchy) {
      continue;
    }
    if (result.recordCount >= result.records.size()) {
      result.recordTruncated = 1;
      continue;
    }

    ObserverButtonRecord &record = result.records[result.recordCount++];
    record.flags = 0x1u | 0x2u | (interactable ? 0x4u : 0u);
    const std::string objectName = invokeString(gameObject);
    if (!objectName.empty()) {
      if (!CopyBoundedString(objectName, &record.name)) {
        record.flags |= 0x200u;
      }
      record.flags |= 0x8u;
    }

    std::string path;
    void *currentTransform = transform;
    for (int depth = 0; currentTransform != nullptr && depth < 24; ++depth) {
      const std::string part = invokeString(currentTransform);
      if (part.empty()) {
        break;
      }
      path = path.empty() ? part : part + "/" + path;
      currentTransform = getParent != nullptr
                             ? invokeObject(getParent, currentTransform)
                             : nullptr;
    }
    if (!path.empty()) {
      if (!CopyBoundedString(path, &record.path)) {
        record.flags |= 0x200u;
      }
      record.flags |= 0x10u;
    }

    Vector3 world = {};
    if (getPosition != nullptr &&
        invokeValue(getPosition, transform, nullptr, &world, sizeof(world))) {
      record.worldX = world.x;
      record.worldY = world.y;
      record.worldZ = world.z;
      record.flags |= 0x20u;
    }
    Rect rect = {};
    if (getRect != nullptr &&
        invokeValue(getRect, transform, nullptr, &rect, sizeof(rect))) {
      record.rectX = rect.x;
      record.rectY = rect.y;
      record.rectWidth = rect.width;
      record.rectHeight = rect.height;
      record.flags |= 0x40u;
    }

    void *canvas = nullptr;
    if (getComponentInParent != nullptr && canvasTypeObject != nullptr) {
      uint8_t includeInactive = 0;
      void *arguments[] = {canvasTypeObject, &includeInactive};
      canvas = invokeObject(getComponentInParent, button, arguments);
    }
    int32_t renderMode = -1;
    if (canvas != nullptr) {
      const std::string canvasName = invokeString(canvas);
      if (!canvasName.empty()) {
        if (!CopyBoundedString(canvasName, &record.canvasName)) {
          record.flags |= 0x200u;
        }
      }
      if (getRenderMode != nullptr) {
        invokeValue(getRenderMode, canvas, nullptr, &renderMode,
                    sizeof(renderMode));
      }
      record.canvasRenderMode = renderMode;
      record.flags |= 0x80u;
    }

    Vector3 screen = {};
    bool screenValid = false;
    void *camera = canvas != nullptr && getWorldCamera != nullptr
                       ? invokeObject(getWorldCamera, canvas)
                       : nullptr;
    auto projectToScreen = [&](const Vector3 &worldPoint,
                               Vector3 *screenPoint) {
      if (camera != nullptr && worldToScreenPoint != nullptr) {
        Vector3 argument = worldPoint;
        void *arguments[] = {&argument};
        return invokeValue(worldToScreenPoint, camera, arguments, screenPoint,
                           sizeof(*screenPoint));
      }
      if (renderMode == 0) {
        *screenPoint = worldPoint;
        return true;
      }
      return false;
    };
    if ((record.flags & 0x20u) != 0) {
      screenValid = projectToScreen(world, &screen);
    }
    if (screenValid) {
      record.screenX = screen.x;
      record.screenY = screen.y;
      record.adbX = screen.x;
      record.adbY = static_cast<float>(screenHeight) - screen.y;
      record.flags |= 0x100u;
    }
    if (transformPoint != nullptr && (record.flags & 0x40u) != 0) {
      const std::array<Vector3, 4> localCorners = {
          Vector3{rect.x, rect.y, 0.0f},
          Vector3{rect.x + rect.width, rect.y, 0.0f},
          Vector3{rect.x + rect.width, rect.y + rect.height, 0.0f},
          Vector3{rect.x, rect.y + rect.height, 0.0f},
      };
      float left = std::numeric_limits<float>::max();
      float bottom = std::numeric_limits<float>::max();
      float right = std::numeric_limits<float>::lowest();
      float top = std::numeric_limits<float>::lowest();
      bool boundsValid = true;
      for (const Vector3 &localCorner : localCorners) {
        Vector3 localArgument = localCorner;
        void *arguments[] = {&localArgument};
        Vector3 worldCorner = {};
        Vector3 screenCorner = {};
        if (!invokeValue(transformPoint, transform, arguments, &worldCorner,
                         sizeof(worldCorner)) ||
            !projectToScreen(worldCorner, &screenCorner)) {
          boundsValid = false;
          break;
        }
        left = std::min(left, screenCorner.x);
        bottom = std::min(bottom, screenCorner.y);
        right = std::max(right, screenCorner.x);
        top = std::max(top, screenCorner.y);
      }
      if (boundsValid) {
        record.screenLeft = left;
        record.screenBottom = bottom;
        record.screenRight = right;
        record.screenTop = top;
        record.adbLeft = left;
        record.adbTop = static_cast<float>(screenHeight) - top;
        record.adbRight = right;
        record.adbBottom = static_cast<float>(screenHeight) - bottom;
        record.flags |= 0x400u;
      }
    }
    if (ShouldEvaluateTopRaycast(objectName, path) &&
        (record.flags & 0x100u) != 0 && (record.flags & 0x400u) != 0) {
      if (objectName == "extend" &&
          EndsWith(path, "NewMainMellowTheme(Clone)/frame/left/extend")) {
        const float visibleLeft = std::max(0.0f, record.screenLeft);
        const float visibleRight =
            std::min(static_cast<float>(screenWidth), record.screenRight);
        const float visibleBottom = std::max(0.0f, record.screenBottom);
        const float visibleTop =
            std::min(static_cast<float>(screenHeight), record.screenTop);
        if (visibleLeft < visibleRight && visibleBottom < visibleTop) {
          record.screenX = (visibleLeft + visibleRight) / 2.0f;
          record.screenY = (visibleBottom + visibleTop) / 2.0f;
          record.adbX = record.screenX;
          record.adbY = static_cast<float>(screenHeight) - record.screenY;
        }
      }
      if (objectName == "CommissionInfoUI4Mellow(Clone)" &&
          EndsWith(path, "Overlay/UIMain/CommissionInfoUI4Mellow(Clone)")) {
        record.screenX = 827.0f;
        record.screenY = static_cast<float>(screenHeight) - 622.0f;
        record.adbX = record.screenX;
        record.adbY = 622.0f;
      }
      bool raycastEvaluated = false;
      bool raycastMatches =
          topRaycastMatches(transform, Vector2{record.screenX, record.screenY},
                            &raycastEvaluated);
      const bool needsReviewedPointSearch =
          path.find("CourtYardUI(Clone)/main/") != std::string_view::npos ||
          path.find("BackYardFeedUI(Clone)/") != std::string_view::npos ||
          path.find("TechnologyUI(Clone)/main/base_page/") !=
              std::string_view::npos ||
          path.find("TechnologyUI(Clone)/blur_panel/adapt/left/") !=
              std::string_view::npos ||
          path.find("BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/") !=
              std::string_view::npos ||
          path.find("BuildShipMsgBoxUI(Clone)/") != std::string_view::npos ||
          path.find("DockyardUI(Clone)/main/ship_container/ships/") !=
              std::string_view::npos ||
          path.find("Overlay/UIMain/blur_panel/select_panel/") !=
              std::string_view::npos ||
          path.find("NewNavalTacticsUI(Clone)/adpter/"
                    "NewNavalTacticsStudentsPage(Clone)/") !=
              std::string_view::npos ||
          path.find("LevelStageInfoView(Clone)/panel/") !=
              std::string_view::npos ||
          path.find("LevelFleetSelectView(Clone)/panel/ShipList/") !=
              std::string_view::npos ||
          EndsWith(path,
                   "LevelStageView(Clone)/right_stage/event/collapse/"
                   "lock_fleet") ||
          EndsWith(path,
                   "LevelStageView(Clone)/bottom_stage/Normal/"
                   "retreat_button") ||
          EndsWith(path,
                   "ChapterPreCombatUI(Clone)/adapt/right/start") ||
          EndsWith(path,
                   "LevelFleetSelectView(Clone)/panel/Fixed/btnBack") ||
          EndsWith(path,
                   "NewNavalTacticsUI(Clone)/adpter/frame/btnBack");
      if (!raycastMatches && needsReviewedPointSearch) {
        // Some reviewed controls overlap broader sibling graphics at their
        // RectTransform center.  Search a bounded set of in-rect points, but
        // publish one only after EventSystem proves the exact Button (or one
        // of its children) is topmost there.
        constexpr std::array<float, 3> kReviewedRaycastFractions = {
            0.25f, 0.5f, 0.75f};
        for (float xFraction : kReviewedRaycastFractions) {
          for (float yFraction : kReviewedRaycastFractions) {
            const Vector2 candidate = {
                record.screenLeft +
                    (record.screenRight - record.screenLeft) * xFraction,
                record.screenBottom +
                    (record.screenTop - record.screenBottom) * yFraction,
            };
            bool candidateEvaluated = false;
            if (topRaycastMatches(transform, candidate, &candidateEvaluated)) {
              record.screenX = candidate.x;
              record.screenY = candidate.y;
              record.adbX = candidate.x;
              record.adbY =
                  static_cast<float>(screenHeight) - candidate.y;
              raycastMatches = true;
              raycastEvaluated = true;
              break;
            }
            raycastEvaluated = raycastEvaluated || candidateEvaluated;
          }
          if (raycastMatches) {
            break;
          }
        }
      }
      if (raycastEvaluated) {
        record.flags |= 0x800u;
        record.flags |= raycastMatches ? 0x1000u : 0u;
      }
    }
  }

  if ((result.uiMethodMask & 0x1u) != 0) {
    LoadedObjectCollector toggleCollector;
    if (!collectLoadedInstances(toggleClass, &toggleCollector)) {
      ++result.uiRecordErrors;
    } else {
      result.toggleRecordTruncated |= toggleCollector.truncated ? 1u : 0u;
      for (size_t index = 0; index < toggleCollector.count; ++index) {
        void *toggle = toggleCollector.objects[index];
        bool active = false;
        bool interactable = false;
        bool isOn = false;
        if (toggle == nullptr ||
            !invokeBoolean(getToggleActiveAndEnabled, toggle, &active) ||
            !invokeBoolean(getToggleInteractable, toggle, &interactable) ||
            !invokeBoolean(getToggleIsOn, toggle, &isOn)) {
          ++result.uiRecordSkipped;
          continue;
        }
        if (!active) {
          continue;
        }
        if (result.toggleRecordCount >= result.toggles.size()) {
          result.toggleRecordTruncated = 1;
          continue;
        }
        ObserverToggleRecord &record = result.toggles[result.toggleRecordCount];
        if (!populateControlRecord(toggle, interactable, &record.control)) {
          ++result.uiRecordErrors;
          continue;
        }
        const std::string_view toggleName(
            record.control.name.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.control.name.data(),
                                      record.control.name.size())));
        const std::string_view togglePath(
            record.control.path.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.control.path.data(),
                                      record.control.path.size())));
        if (ShouldEvaluateToggleTopRaycast(toggleName, togglePath) &&
            (record.control.flags & 0x100u) != 0 &&
            (record.control.flags & 0x400u) != 0) {
          void *gameObject = invokeObject(getGameObject, toggle);
          void *transform = gameObject != nullptr
                                ? invokeObject(getTransform, gameObject)
                                : nullptr;
          bool raycastEvaluated = false;
          const bool raycastMatches = topRaycastMatches(
              transform,
              Vector2{record.control.screenX, record.control.screenY},
              &raycastEvaluated);
          if (raycastEvaluated) {
            record.control.flags |= 0x800u;
            record.control.flags |= raycastMatches ? 0x1000u : 0u;
          }
        }
        record.stateFlags = 0x1u | (isOn ? 0x2u : 0u);
        ++result.toggleRecordCount;
      }
    }
  }

  auto appendTextRecords = [&](void *textClass,
                               const void *getTextActiveAndEnabled,
                               const void *getText, uint32_t kindFlag) {
    if (textClass == nullptr || getTextActiveAndEnabled == nullptr ||
        getText == nullptr) {
      return;
    }
    LoadedObjectCollector textCollector;
    if (!collectLoadedInstances(textClass, &textCollector)) {
      ++result.uiRecordErrors;
      return;
    }
    result.textRecordTruncated |= textCollector.truncated ? 1u : 0u;
    for (size_t index = 0; index < textCollector.count; ++index) {
      void *textComponent = textCollector.objects[index];
      bool active = false;
      if (textComponent == nullptr ||
          !invokeBoolean(getTextActiveAndEnabled, textComponent, &active)) {
        ++result.uiRecordSkipped;
        continue;
      }
      if (!active) {
        continue;
      }
      if (result.textRecordCount >= result.texts.size()) {
        result.textRecordTruncated = 1;
        continue;
      }

      ObserverButtonRecord geometry;
      if (!populateControlRecord(textComponent, false, &geometry)) {
        ++result.uiRecordErrors;
        continue;
      }
      void *textObject = invokeObject(getText, textComponent);
      if (textObject == nullptr) {
        ++result.uiRecordErrors;
        continue;
      }

      ObserverTextRecord &record = result.texts[result.textRecordCount++];
      record.name = geometry.name;
      record.path = geometry.path;
      record.flags = 0x1u | 0x2u | 0x4u | kindFlag;
      if ((geometry.flags & 0x200u) != 0) {
        record.flags |= 0x10u;
      }
      const std::string value = readString(textObject);
      if (!CopyBoundedString(value, &record.text)) {
        record.flags |= 0x10u;
      }
      if ((geometry.flags & 0x400u) != 0) {
        record.adbLeft = geometry.adbLeft;
        record.adbTop = geometry.adbTop;
        record.adbRight = geometry.adbRight;
        record.adbBottom = geometry.adbBottom;
        record.flags |= 0x8u;
      }
    }
  };
  appendTextRecords(legacyTextClass, getLegacyTextActiveAndEnabled,
                    getLegacyText, 0x100u);
  appendTextRecords(tmpTextClass, getTmpTextActiveAndEnabled, getTmpText,
                    0x200u);

  if ((result.uiMethodMask & 0x8u) != 0) {
    struct Color {
      float red;
      float green;
      float blue;
      float alpha;
    };
    LoadedObjectCollector imageCollector;
    if (!collectLoadedInstances(imageClass, &imageCollector)) {
      ++result.uiRecordErrors;
    } else {
      result.imageRecordTruncated |= imageCollector.truncated ? 1u : 0u;
      for (size_t index = 0; index < imageCollector.count; ++index) {
        void *image = imageCollector.objects[index];
        bool active = false;
        if (image == nullptr ||
            !invokeBoolean(getImageActiveAndEnabled, image, &active)) {
          ++result.uiRecordSkipped;
          continue;
        }
        if (!active) {
          continue;
        }
        if (result.imageRecordCount >= result.images.size()) {
          result.imageRecordTruncated = 1;
          continue;
        }

        ObserverButtonRecord geometry;
        if (!populateControlRecord(image, false, &geometry)) {
          ++result.uiRecordErrors;
          continue;
        }
        bool raycastTarget = false;
        Color color = {};
        float fillAmount = 0.0f;
        if (!invokeBoolean(getImageRaycastTarget, image, &raycastTarget) ||
            !invokeValue(getImageColor, image, nullptr, &color,
                         sizeof(color)) ||
            !invokeValue(getImageFillAmount, image, nullptr, &fillAmount,
                         sizeof(fillAmount))) {
          ++result.uiRecordErrors;
          continue;
        }

        ObserverImageRecord &record = result.images[result.imageRecordCount++];
        record.name = geometry.name;
        record.path = geometry.path;
        record.flags =
            0x1u | 0x2u | 0x20u | (raycastTarget ? 0x40u : 0u) | 0x80u | 0x100u;
        if ((geometry.flags & 0x200u) != 0) {
          record.flags |= 0x10u;
        }
        void *sprite = invokeObject(getImageSprite, image);
        const std::string spriteName =
            sprite != nullptr ? invokeString(sprite) : std::string();
        if (!spriteName.empty()) {
          if (!CopyBoundedString(spriteName, &record.spriteName)) {
            record.flags |= 0x10u;
          }
          record.flags |= 0x8u;
        }
        record.red = color.red;
        record.green = color.green;
        record.blue = color.blue;
        record.alpha = color.alpha;
        record.fillAmount = fillAmount;
        if ((geometry.flags & 0x400u) != 0) {
          record.adbLeft = geometry.adbLeft;
          record.adbTop = geometry.adbTop;
          record.adbRight = geometry.adbRight;
          record.adbBottom = geometry.adbBottom;
          record.flags |= 0x4u;
        }
        void *imageGameObject = invokeObject(getGameObject, image);
        void *imageTransform = imageGameObject != nullptr
                                   ? invokeObject(getTransform, imageGameObject)
                                   : nullptr;
        void *ancestorTransform = imageTransform;
        for (int depth = 0; ancestorTransform != nullptr && depth < 24;
             ++depth) {
          const std::string ancestorName = invokeString(ancestorTransform);
          if (ancestorName.rfind("cell_fleet_", 0) == 0) {
            Vector3 anchorWorld = {};
            if (getPosition != nullptr &&
                invokeValue(getPosition, ancestorTransform, nullptr,
                            &anchorWorld, sizeof(anchorWorld))) {
              record.anchorWorldX = anchorWorld.x;
              record.anchorWorldY = anchorWorld.y;
              record.anchorWorldZ = anchorWorld.z;
              record.flags |= 0x800u;
            }
            break;
          }
          ancestorTransform = getParent != nullptr
                                  ? invokeObject(getParent, ancestorTransform)
                                  : nullptr;
        }
        const std::string_view imageName(
            record.name.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.name.data(), record.name.size())));
        const std::string_view imagePath(
            record.path.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.path.data(), record.path.size())));
        if (ShouldEvaluateImageTopRaycast(imageName, imagePath) &&
            (geometry.flags & 0x100u) != 0 && (geometry.flags & 0x400u) != 0) {
          bool raycastEvaluated = false;
          const bool raycastMatches = topRaycastMatches(
              imageTransform, Vector2{geometry.screenX, geometry.screenY},
              &raycastEvaluated);
          if (raycastEvaluated) {
            record.flags |= 0x200u;
            record.flags |= raycastMatches ? 0x400u : 0u;
          }
        }
      }
    }
  }

  result.success = true;
  result.diagnosticStage = 100;
  return result;
}
} // namespace
#endif

Il2CppDynamicProbe ProbeIl2CppDynamicSymbols() {
  static const Il2CppDynamicProbe result = [] {
    Il2CppDynamicProbe resolved;
#if defined(ANGLE_PLATFORM_ANDROID)
    dl_iterate_phdr(FindAndResolveIl2Cpp, &resolved);
#endif
    return resolved;
  }();
  return result;
}

namespace {
std::mutex gObserverSnapshotMutex;
ObserverSnapshot gObserverSnapshot;
ObserverSemanticSnapshot gObserverSemanticSnapshot;
ObserverUiSnapshot gObserverUiSnapshot;
std::atomic<uint64_t> gObserverGeneration{0};
std::atomic<int> gObserverMainThreadTid{0};
std::atomic<int32_t> gLastSceneHandle{0};
std::atomic<uint64_t> gSceneGeneration{0};
std::atomic<uint32_t> gLastSemanticState{0};
std::atomic<uint64_t> gSemanticGeneration{0};
} // namespace

int32_t ObserverMainThreadTick(uint64_t requestGeneration,
                               uint64_t sceneGeneration, uint32_t semanticCode,
                               uint64_t semanticGeneration, int width,
                               int height, int expectedTid) {
  ObserverSnapshot snapshot;
  ObserverSemanticSnapshot semanticSnapshot;
  // This snapshot contains the full fixed-capacity Image array.  Reuse TLS
  // storage so increasing the read-only map capacity cannot overflow the
  // Unity main-thread stack before the first observer sample.
  static thread_local ObserverUiSnapshot uiSnapshot;
#if defined(ANGLE_PLATFORM_ANDROID)
  const int actualTid = gettid();
  snapshot.tid = actualTid;
  if (actualTid != expectedTid) {
    snapshot.flags = 0x80000002u;
    return -2;
  }
  if (requestGeneration == 0 || sceneGeneration == 0 ||
      semanticGeneration == 0 || (semanticCode != 1 && semanticCode != 2) ||
      width != 1280 || height != 720) {
    snapshot.flags = 0x80000003u;
    return -3;
  }

  const Il2CppDynamicProbe probe = ProbeIl2CppDynamicSymbols();
  if (!probe.dynamicParsed || probe.symbolCount != kIl2CppAllowlistSize) {
    snapshot.flags = 0x80000001u;
    return -1;
  }

  using DomainGet = void *(*)();
  using DomainGetAssemblies = const void **(*)(const void *, size_t *);
  using AssemblyGetImage = const void *(*)(const void *);
  using ImageGetName = const char *(*)(const void *);
  using ThreadAttach = void *(*)(const void *);
  using ThreadDetach = void (*)(void *);
  using ThreadCurrent = void *(*)();
  const auto domainGet = reinterpret_cast<DomainGet>(probe.symbols[0]);
  const auto domainGetAssemblies =
      reinterpret_cast<DomainGetAssemblies>(probe.symbols[1]);
  const auto assemblyGetImage =
      reinterpret_cast<AssemblyGetImage>(probe.symbols[2]);
  const auto imageGetName = reinterpret_cast<ImageGetName>(probe.symbols[3]);
  const auto threadAttach = reinterpret_cast<ThreadAttach>(probe.symbols[4]);
  const auto threadDetach = reinterpret_cast<ThreadDetach>(probe.symbols[5]);
  const auto threadCurrent = reinterpret_cast<ThreadCurrent>(probe.symbols[6]);

  void *domain = domainGet();
  if (domain == nullptr) {
    snapshot.flags = 0x80000004u;
    return -4;
  }
  void *currentThread = threadCurrent();
  const bool observerAttach = currentThread == nullptr;
  if (observerAttach) {
    currentThread = threadAttach(domain);
    if (currentThread == nullptr) {
      snapshot.flags = 0x80000007u;
      return -7;
    }
  }
  size_t assemblyCount = 0;
  const void **assemblies = domainGetAssemblies(domain, &assemblyCount);
  if (assemblies == nullptr || assemblyCount == 0 || assemblyCount > 512) {
    if (observerAttach) {
      threadDetach(currentThread);
    }
    snapshot.flags = 0x80000005u;
    return -5;
  }

  bool assemblyCSharp = false;
  bool unityUi = false;
  const void *coreImage = nullptr;
  const void *uiImage = nullptr;
  const void *uiModuleImage = nullptr;
  const void *textMeshProImage = nullptr;
  for (size_t index = 0; index < assemblyCount; ++index) {
    const void *assembly = ANGLE_UNSAFE_BUFFERS(assemblies[index]);
    const void *image = assemblyGetImage(assembly);
    const char *name = image != nullptr ? imageGetName(image) : nullptr;
    if (name == nullptr) {
      continue;
    }
    const std::string_view imageName(name);
    assemblyCSharp |=
        imageName == "Assembly-CSharp" || imageName == "Assembly-CSharp.dll";
    unityUi |=
        imageName == "UnityEngine.UI" || imageName == "UnityEngine.UI.dll";
    if (imageName == "UnityEngine.CoreModule" ||
        imageName == "UnityEngine.CoreModule.dll") {
      coreImage = image;
    }
    if (imageName == "UnityEngine.UI" || imageName == "UnityEngine.UI.dll") {
      uiImage = image;
    }
    if (imageName == "UnityEngine.UIModule" ||
        imageName == "UnityEngine.UIModule.dll") {
      uiModuleImage = image;
    }
    if (imageName == "Unity.TextMeshPro" ||
        imageName == "Unity.TextMeshPro.dll") {
      textMeshProImage = image;
    }
  }
  if (!assemblyCSharp || !unityUi) {
    if (observerAttach) {
      threadDetach(currentThread);
    }
    snapshot.flags = 0x80000006u;
    return -6;
  }

  snapshot.structSize = sizeof(ObserverSnapshot);
  snapshot.schema = 1;
  snapshot.assemblyCount = static_cast<uint32_t>(assemblyCount);
  snapshot.requestGeneration = requestGeneration;
  snapshot.sceneGeneration = sceneGeneration;
  snapshot.semanticGeneration = semanticGeneration;
  snapshot.monotonicNanos = static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
  semanticSnapshot.requestGeneration = requestGeneration;
  semanticSnapshot.monotonicNanos = snapshot.monotonicNanos;
  uiSnapshot.requestGeneration = requestGeneration;
  uiSnapshot.monotonicNanos = snapshot.monotonicNanos;
  snapshot.semanticCode = semanticCode;
  snapshot.width = width;
  snapshot.height = height;
  snapshot.flags = 0x7;
  snapshot.processId = static_cast<uint32_t>(getpid());
  snapshot.observerAttached = observerAttach ? 1u : 0u;
  snapshot.mainThread = actualTid == gObserverMainThreadTid.load() ? 1u : 0u;
  if (snapshot.mainThread != 0) {
    const UiProbeResult &ui = ProbeUnityUi(
        probe, coreImage, uiImage, uiModuleImage, textMeshProImage, width,
        height);
    snapshot.uiDiagnosticStage = ui.diagnosticStage;
    snapshot.uiMethodMask = ui.methodMask;
    semanticSnapshot.buttonCount = ui.recordCount;
    semanticSnapshot.truncated = ui.recordTruncated;
    semanticSnapshot.errorCount = ui.recordErrors;
    semanticSnapshot.buttons = ui.records;
    uiSnapshot.toggleCount = ui.toggleRecordCount;
    uiSnapshot.textCount = ui.textRecordCount;
    uiSnapshot.imageCount = ui.imageRecordCount;
    uiSnapshot.toggleTruncated = ui.toggleRecordTruncated;
    uiSnapshot.textTruncated = ui.textRecordTruncated;
    uiSnapshot.imageTruncated = ui.imageRecordTruncated;
    uiSnapshot.errorCount = ui.uiRecordErrors;
    uiSnapshot.skippedCount = ui.uiRecordSkipped;
    uiSnapshot.methodMask = ui.uiMethodMask;
    uiSnapshot.toggles = ui.toggles;
    uiSnapshot.texts = ui.texts;
    uiSnapshot.images = ui.images;
    if (ui.success) {
      snapshot.flags |= 0x8;
      snapshot.buttonCount = ui.buttonCount;
      snapshot.activeButtonCount = ui.activeCount;
      snapshot.interactableButtonCount = ui.interactableCount;
      snapshot.semanticState =
          ui.buttonCount == 0 ? 0u : (ui.interactableCount > 0 ? 1u : 2u);
      snapshot.sceneHandle = ui.sceneHandle;

      const uint64_t priorSceneGeneration = gSceneGeneration.load();
      const int32_t priorSceneHandle =
          gLastSceneHandle.exchange(ui.sceneHandle);
      if (priorSceneGeneration == 0 || priorSceneHandle != ui.sceneHandle) {
        gSceneGeneration.fetch_add(1);
      }
      snapshot.sceneGeneration = gSceneGeneration.load();

      const uint64_t priorSemanticGeneration = gSemanticGeneration.load();
      const uint32_t priorSemanticState =
          gLastSemanticState.exchange(snapshot.semanticState);
      if (priorSemanticGeneration == 0 ||
          priorSemanticState != snapshot.semanticState) {
        gSemanticGeneration.fetch_add(1);
      }
      snapshot.semanticGeneration = gSemanticGeneration.load();
      snapshot.semanticCode = snapshot.semanticState;
    }
  }

  static uint64_t lastSemanticGeneration = 0;
  if (requestGeneration == 1 || requestGeneration % 10 == 0 ||
      semanticGeneration != lastSemanticGeneration) {
    lastSemanticGeneration = semanticGeneration;
    __android_log_print(
        ANDROID_LOG_INFO, "ALAS_G3",
        "ALAS_G3_SNAPSHOT {\"schema\":1,\"request_generation\":%" PRIu64
        ",\"scene_generation\":%" PRIu64 ",\"semantic_code\":%u,"
        "\"semantic_generation\":%" PRIu64 ",\"width\":%d,\"height\":%d,"
        "\"tid\":%d,\"thread_attached\":true,\"observer_attached\":%s,"
        "\"assembly_count\":%zu,"
        "\"assembly_csharp\":true,\"unity_ui\":true,\"main_thread\":%s,"
        "\"ui_typed\":%s,\"button_count\":%u,\"active_button_count\":%u,"
        "\"interactable_button_count\":%u,\"scene_handle\":%d,\"ui_stage\":%u,"
        "\"ui_method_mask\":%u}",
        requestGeneration, sceneGeneration, semanticCode, semanticGeneration,
        width, height, actualTid, observerAttach ? "true" : "false",
        assemblyCount, snapshot.mainThread != 0 ? "true" : "false",
        (snapshot.flags & 0x8u) != 0 ? "true" : "false", snapshot.buttonCount,
        snapshot.activeButtonCount, snapshot.interactableButtonCount,
        snapshot.sceneHandle, snapshot.uiDiagnosticStage,
        snapshot.uiMethodMask);
  }
  if (observerAttach) {
    threadDetach(currentThread);
  }
  {
    std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
    gObserverSnapshot = snapshot;
    gObserverSemanticSnapshot = semanticSnapshot;
    gObserverUiSnapshot = uiSnapshot;
  }
  return 0;
#else
  snapshot.flags = 0x80000009u;
  return -9;
#endif
}

int32_t ObserverFrameTick(uint64_t frameGeneration, int width, int height) {
#if defined(ANGLE_PLATFORM_ANDROID)
  RegisterObserverMainThread();
  const int32_t mainThreadTid = gObserverMainThreadTid.load();
  if (mainThreadTid == 0 || gettid() != mainThreadTid) {
    return mainThreadTid;
  }
  // A complete typed snapshot invokes managed accessors for four component
  // families.  Ten snapshots per second are well inside the controller's
  // freshness gate while leaving consecutive endpoint reads generation-
  // coherent and bounding observer work on complex campaign maps.
  if (frameGeneration != 1 && frameGeneration % 3 != 0) {
    return 0;
  }
  const uint64_t generation = gObserverGeneration.fetch_add(1) + 1;
  return ObserverMainThreadTick(generation, 1, 1, 1, width, height, gettid());
#else
  return -9;
#endif
}

void RegisterObserverMainThread() {
#if defined(ANGLE_PLATFORM_ANDROID)
  const Il2CppDynamicProbe probe = ProbeIl2CppDynamicSymbols();
  if (probe.symbols[6] == 0) {
    return;
  }
  using ThreadCurrent = void *(*)();
  const auto threadCurrent = reinterpret_cast<ThreadCurrent>(probe.symbols[6]);
  const void *currentThread = threadCurrent();
  int32_t expectedThreadTid = 0;
  const int32_t candidateTid = gettid();
  if (currentThread != nullptr &&
      gObserverMainThreadTid.compare_exchange_strong(expectedThreadTid,
                                                     candidateTid)) {
    __android_log_print(
        ANDROID_LOG_INFO, "ALAS_G3",
        "ALAS_G3_MAIN_THREAD {\"tid\":%d,\"il2cpp_attached\":true}",
        candidateTid);
  }
#endif
}

bool GetLatestObserverSnapshot(ObserverSnapshot *snapshot) {
  if (snapshot == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
  if (gObserverSnapshot.requestGeneration == 0) {
    return false;
  }
  *snapshot = gObserverSnapshot;
  return true;
}

bool GetLatestObserverSemanticSnapshot(ObserverSemanticSnapshot *snapshot) {
  if (snapshot == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
  if (gObserverSemanticSnapshot.requestGeneration == 0) {
    return false;
  }
  *snapshot = gObserverSemanticSnapshot;
  return true;
}

bool GetLatestObserverUiSnapshot(ObserverUiSnapshot *snapshot) {
  if (snapshot == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
  if (gObserverUiSnapshot.requestGeneration == 0) {
    return false;
  }
  *snapshot = gObserverUiSnapshot;
  return true;
}

} // namespace rx::alas
