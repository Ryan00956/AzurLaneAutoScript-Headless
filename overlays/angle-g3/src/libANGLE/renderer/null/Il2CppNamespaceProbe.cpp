// Copyright 2026 The ANGLE Project Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"

#include "common/platform.h"

#include <atomic>
#include <chrono>
#include <mutex>

#if defined(ANGLE_PLATFORM_ANDROID)
#    include <android/log.h>
#    include <elf.h>
#    include <inttypes.h>
#    include <link.h>
#    include <sys/types.h>
#    include <unistd.h>

#    include <algorithm>
#    include <array>
#    include <cstring>
#    include <limits>
#    include <string>
#    include <string_view>

#    include "common/unsafe_buffers.h"
#endif

namespace rx::alas
{

#if defined(ANGLE_PLATFORM_ANDROID)
namespace
{
constexpr std::array<std::string_view, kIl2CppAllowlistSize> kAllowlistedSymbols = {
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

bool IsRangeInModule(const dl_phdr_info &info, uintptr_t address, size_t size)
{
    for (ElfW(Half) index = 0; index < info.dlpi_phnum; ++index)
    {
        const ElfW(Phdr) &header = ANGLE_UNSAFE_BUFFERS(info.dlpi_phdr[index]);
        if (header.p_type != PT_LOAD)
        {
            continue;
        }
        const uintptr_t start = info.dlpi_addr + header.p_vaddr;
        if (start > std::numeric_limits<uintptr_t>::max() - header.p_memsz)
        {
            continue;
        }
        const uintptr_t end = start + header.p_memsz;
        if (address >= start && address <= end && size <= end - address)
        {
            return true;
        }
    }
    return false;
}

uintptr_t ResolveDynamicAddress(const dl_phdr_info &info, ElfW(Addr) value, size_t size)
{
    if (info.dlpi_addr <= std::numeric_limits<uintptr_t>::max() - value)
    {
        const uintptr_t relative = info.dlpi_addr + value;
        if (IsRangeInModule(info, relative, size))
        {
            return relative;
        }
    }
    const uintptr_t absolute = static_cast<uintptr_t>(value);
    return IsRangeInModule(info, absolute, size) ? absolute : 0;
}

bool ResolveFromDynamic(const dl_phdr_info &info, Il2CppDynamicProbe *result)
{
    result->diagnosticStage  = 10;
    const ElfW(Dyn) *dynamic = nullptr;
    size_t dynamicCount      = 0;
    for (ElfW(Half) index = 0; index < info.dlpi_phnum; ++index)
    {
        const ElfW(Phdr) &header = ANGLE_UNSAFE_BUFFERS(info.dlpi_phdr[index]);
        if (header.p_type != PT_DYNAMIC)
        {
            continue;
        }
        const uintptr_t address = info.dlpi_addr + header.p_vaddr;
        dynamicCount            = header.p_memsz / sizeof(ElfW(Dyn));
        if (dynamicCount == 0 || !IsRangeInModule(info, address, dynamicCount * sizeof(ElfW(Dyn))))
        {
            return false;
        }
        dynamic              = reinterpret_cast<const ElfW(Dyn) *>(address);
        result->dynamicFound = true;
        break;
    }
    if (dynamic == nullptr)
    {
        return false;
    }

    result->diagnosticStage = 20;

    uintptr_t symbolTableAddress = 0;
    uintptr_t stringTableAddress = 0;
    uintptr_t hashAddress        = 0;
    size_t stringTableSize       = 0;
    size_t symbolEntrySize       = 0;
    for (size_t index = 0; index < dynamicCount; ++index)
    {
        const ElfW(Dyn) &entry = ANGLE_UNSAFE_BUFFERS(dynamic[index]);
        if (entry.d_tag == DT_NULL)
        {
            break;
        }
        switch (entry.d_tag)
        {
            case DT_SYMTAB:
                symbolTableAddress =
                    ResolveDynamicAddress(info, entry.d_un.d_ptr, sizeof(ElfW(Sym)));
                result->symbolTableFound = symbolTableAddress != 0;
                break;
            case DT_STRTAB:
                stringTableAddress       = ResolveDynamicAddress(info, entry.d_un.d_ptr, 1);
                result->stringTableFound = stringTableAddress != 0;
                break;
            case DT_HASH:
                hashAddress = ResolveDynamicAddress(info, entry.d_un.d_ptr, 2 * sizeof(uint32_t));
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
        stringTableSize == 0 || symbolEntrySize != sizeof(ElfW(Sym)))
    {
        return false;
    }

    const auto *hash         = reinterpret_cast<const uint32_t *>(hashAddress);
    const size_t symbolCount = ANGLE_UNSAFE_BUFFERS(hash[1]);
    result->rawSymbolCount   = symbolCount;
    result->diagnosticStage  = 40;
    if (symbolCount == 0 || symbolCount > std::numeric_limits<size_t>::max() / sizeof(ElfW(Sym)) ||
        !IsRangeInModule(info, symbolTableAddress, symbolCount * sizeof(ElfW(Sym))) ||
        !IsRangeInModule(info, stringTableAddress, stringTableSize))
    {
        return false;
    }

    result->diagnosticStage = 50;

    const auto *symbolTable = reinterpret_cast<const ElfW(Sym) *>(symbolTableAddress);
    const auto *stringTable = reinterpret_cast<const char *>(stringTableAddress);
    for (size_t symbolIndex = 0; symbolIndex < symbolCount; ++symbolIndex)
    {
        const ElfW(Sym) &symbol = ANGLE_UNSAFE_BUFFERS(symbolTable[symbolIndex]);
        if (symbol.st_name >= stringTableSize || symbol.st_shndx == SHN_UNDEF ||
            symbol.st_value == 0)
        {
            continue;
        }
        const char *nameStart = ANGLE_UNSAFE_BUFFERS(stringTable + symbol.st_name);
        std::string_view remaining(nameStart, stringTableSize - symbol.st_name);
        const size_t terminator = remaining.find('\0');
        if (terminator == std::string_view::npos)
        {
            continue;
        }
        const std::string_view name = remaining.substr(0, terminator);
        for (size_t allowlistIndex = 0; allowlistIndex < kAllowlistedSymbols.size();
             ++allowlistIndex)
        {
            if (name != kAllowlistedSymbols[allowlistIndex] || result->symbols[allowlistIndex] != 0)
            {
                continue;
            }
            const uintptr_t address = info.dlpi_addr + symbol.st_value;
            if (IsRangeInModule(info, address, 1))
            {
                result->symbols[allowlistIndex] = address;
                ++result->symbolCount;
            }
        }
    }
    result->diagnosticStage = 60;
    return true;
}

int FindAndResolveIl2Cpp(dl_phdr_info *info, size_t, void *opaque)
{
    auto *result = static_cast<Il2CppDynamicProbe *>(opaque);
    if (info == nullptr || info->dlpi_name == nullptr ||
        std::string_view(info->dlpi_name).find("libil2cpp.so") == std::string_view::npos)
    {
        return 0;
    }
    result->moduleFound   = true;
    result->dynamicParsed = ResolveFromDynamic(*info, result);
    return 1;
}

struct UiProbeResult
{
    bool success                                                  = false;
    uint32_t buttonCount                                          = 0;
    uint32_t activeCount                                          = 0;
    uint32_t interactableCount                                    = 0;
    int32_t sceneHandle                                           = 0;
    uint32_t diagnosticStage                                      = 0;
    uint32_t methodMask                                           = 0;
    uint32_t recordCount                                          = 0;
    uint32_t recordTruncated                                      = 0;
    uint32_t recordErrors                                         = 0;
    std::array<ObserverButtonRecord, kMaxObserverButtons> records = {};
};

template <size_t Size>
bool CopyBoundedString(std::string_view source, std::array<char, Size> *destination)
{
    static_assert(Size > 0);
    if (destination == nullptr)
    {
        return false;
    }
    const size_t copyLength = std::min(source.size(), Size - 1);
    if (copyLength > 0)
    {
        ANGLE_UNSAFE_TODO(std::memcpy(destination->data(), source.data(), copyLength));
    }
    (*destination)[copyLength] = '\0';
    return copyLength == source.size();
}

bool EndsWith(std::string_view value, std::string_view suffix)
{
    return value.size() >= suffix.size() && value.substr(value.size() - suffix.size()) == suffix;
}

bool ShouldEvaluateTopRaycast(std::string_view name, std::string_view path)
{
    if (name == "ContractButton" && path == "ContractCanvas/ContractButton")
    {
        return true;
    }
    if (name == "LoginUI2(Clone)" && EndsWith(path, "UICamera/Canvas/UIMain/LoginUI2(Clone)"))
    {
        return true;
    }
    if (name == "close_btn" && EndsWith(path, "NewBulletinBoardUI(Clone)/bg/close_btn"))
    {
        return true;
    }
    if (name == "close" && EndsWith(path, "GuildMsgBoxUI(Clone)/frame/close"))
    {
        return true;
    }
    if (name == "back_btn" && EndsWith(path, "NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn"))
    {
        return true;
    }
    if (name == "back_btn" && EndsWith(path, "TaskScene(Clone)/blur_panel/adapt/top/back_btn"))
    {
        return true;
    }
    if (name == "GetAllButton" &&
        EndsWith(path, "TaskScene(Clone)/blur_panel/adapt/top/GetAllButton"))
    {
        return true;
    }
    if (name == "close" &&
        (EndsWith(path, "AwardInfoUI(Clone)/items/close") ||
         EndsWith(path, "AwardInfoUI1(Clone)/items/close")))
    {
        return true;
    }
    if ((name == "get_btn" || name == "go_btn") &&
        path.find("TaskScene(Clone)/pages/TaskListPage(Clone)/right_panel/"
                  "content/") != std::string_view::npos &&
        EndsWith(path, name == "get_btn" ? "/frame/get_btn" : "/frame/go_btn"))
    {
        return true;
    }
    struct Target
    {
        std::string_view name;
        std::string_view suffix;
    };
    constexpr std::array<Target, 8> kMainButtons = {
        Target{"battle", "frame/right/1/battle"},
        Target{"formation", "frame/right/1/formation"},
        Target{"settings", "frame/top/btns/settings"},
        Target{"mail", "frame/top/btns/mail"},
        Target{"shop", "frame/bottom/frame/shop"},
        Target{"dock", "frame/bottom/frame/dock"},
        Target{"task", "frame/bottom/frame/task"},
        Target{"build", "frame/bottom/frame/build"},
    };
    return std::any_of(kMainButtons.begin(), kMainButtons.end(), [&](const Target &target) {
        return name == target.name && EndsWith(path, target.suffix);
    });
}

struct LivenessCollector
{
    std::array<void *, 256> objects = {};
    size_t count                    = 0;
    void *(*allocate)(size_t)       = nullptr;
    void (*release)(void *)         = nullptr;
};

void CollectLivenessObjects(void **objects, int count, void *opaque)
{
    auto *collector = static_cast<LivenessCollector *>(opaque);
    if (collector == nullptr || objects == nullptr || count <= 0)
    {
        return;
    }
    for (int index = 0; index < count && collector->count < collector->objects.size(); ++index)
    {
        collector->objects[collector->count++] = ANGLE_UNSAFE_BUFFERS(objects[index]);
    }
}

void *ReallocateLiveness(void *buffer, size_t size, void *opaque)
{
    auto *collector = static_cast<LivenessCollector *>(opaque);
    if (collector == nullptr)
    {
        return nullptr;
    }
    if (buffer != nullptr && size == 0)
    {
        collector->release(buffer);
        return nullptr;
    }
    return collector->allocate(size);
}

UiProbeResult ProbeUnityUi(const Il2CppDynamicProbe &probe,
                           const void *coreImage,
                           const void *uiImage,
                           const void *uiModuleImage,
                           int screenHeight)
{
    UiProbeResult result;
    result.diagnosticStage = 10;
    if (coreImage == nullptr || uiImage == nullptr)
    {
        return result;
    }

    using ClassFromName          = void *(*)(const void *, const char *, const char *);
    using ClassGetMethodFromName = const void *(*)(void *, const char *, int);
    using RuntimeInvoke          = void *(*)(const void *, void *, void **, void **);
    using ObjectUnbox            = void *(*)(void *);
    using ClassGetParent         = void *(*)(void *);
    using ClassGetType           = const void *(*)(void *);
    using TypeGetObject          = void *(*)(const void *);
    using StringLength           = int32_t (*)(void *);
    using StringChars            = const uint16_t *(*)(void *);
    using LivenessAllocate       = void *(*)(void *, int, void (*)(void **, int, void *), void *,
                                             void *(*)(void *, size_t, void *));
    using LivenessAction         = void (*)(void *);
    using GcWorldAction          = void (*)();
    using Allocate               = void *(*)(size_t);
    using Release                = void (*)(void *);
    using ObjectNew              = void *(*)(const void *);
    using MethodGetParam         = const void *(*)(const void *, uint32_t);
    using MethodGetReturnType    = const void *(*)(const void *);
    using ClassFromType          = void *(*)(const void *);
    using ClassGetFieldFromName  = void *(*)(void *, const char *);
    using FieldGetValue          = void (*)(void *, void *, void *);

    const auto classFromName          = reinterpret_cast<ClassFromName>(probe.symbols[7]);
    const auto classGetMethodFromName = reinterpret_cast<ClassGetMethodFromName>(probe.symbols[10]);
    const auto runtimeInvoke          = reinterpret_cast<RuntimeInvoke>(probe.symbols[11]);
    const auto objectUnbox            = reinterpret_cast<ObjectUnbox>(probe.symbols[12]);
    const auto classGetParent         = reinterpret_cast<ClassGetParent>(probe.symbols[16]);
    const auto classGetType           = reinterpret_cast<ClassGetType>(probe.symbols[8]);
    const auto typeGetObject          = reinterpret_cast<TypeGetObject>(probe.symbols[9]);
    const auto stringLength           = reinterpret_cast<StringLength>(probe.symbols[14]);
    const auto stringChars            = reinterpret_cast<StringChars>(probe.symbols[15]);
    const auto livenessAllocate       = reinterpret_cast<LivenessAllocate>(probe.symbols[18]);
    const auto livenessFromStatics    = reinterpret_cast<LivenessAction>(probe.symbols[19]);
    const auto livenessFinalize       = reinterpret_cast<LivenessAction>(probe.symbols[20]);
    const auto livenessFree           = reinterpret_cast<LivenessAction>(probe.symbols[21]);
    const auto stopGcWorld            = reinterpret_cast<GcWorldAction>(probe.symbols[22]);
    const auto startGcWorld           = reinterpret_cast<GcWorldAction>(probe.symbols[23]);
    const auto allocate               = reinterpret_cast<Allocate>(probe.symbols[24]);
    const auto release                = reinterpret_cast<Release>(probe.symbols[25]);
    const auto objectNew              = reinterpret_cast<ObjectNew>(probe.symbols[26]);
    const auto methodGetParam         = reinterpret_cast<MethodGetParam>(probe.symbols[27]);
    const auto methodGetReturnType    = reinterpret_cast<MethodGetReturnType>(probe.symbols[28]);
    const auto classFromType          = reinterpret_cast<ClassFromType>(probe.symbols[29]);
    const auto classGetFieldFromName  = reinterpret_cast<ClassGetFieldFromName>(probe.symbols[30]);
    const auto fieldGetValue          = reinterpret_cast<FieldGetValue>(probe.symbols[31]);

    void *sceneManagerClass =
        classFromName(coreImage, "UnityEngine.SceneManagement", "SceneManager");
    void *buttonClass = classFromName(uiImage, "UnityEngine.UI", "Button");
    if (sceneManagerClass == nullptr || buttonClass == nullptr)
    {
        return result;
    }
    result.diagnosticStage = 20;

    const void *getActiveScene = classGetMethodFromName(sceneManagerClass, "GetActiveScene", 0);
    auto findMethodInHierarchy = [&](void *klass, const char *name, int parameterCount = 0) {
        for (int depth = 0; klass != nullptr && depth < 8; ++depth)
        {
            const void *method = classGetMethodFromName(klass, name, parameterCount);
            if (method != nullptr)
            {
                return method;
            }
            klass = classGetParent(klass);
        }
        return static_cast<const void *>(nullptr);
    };
    const void *getActiveAndEnabled = findMethodInHierarchy(buttonClass, "get_isActiveAndEnabled");
    const void *getInteractable     = findMethodInHierarchy(buttonClass, "get_interactable");
    result.methodMask               = 0x1u | (getActiveScene != nullptr ? 0x2u : 0u) |
                                      (getActiveAndEnabled != nullptr ? 0x4u : 0u) |
                                      (getInteractable != nullptr ? 0x8u : 0u);
    if (getActiveScene == nullptr || getActiveAndEnabled == nullptr || getInteractable == nullptr)
    {
        return result;
    }
    result.diagnosticStage = 30;

    void *gameObjectClass    = classFromName(coreImage, "UnityEngine", "GameObject");
    void *transformClass     = classFromName(coreImage, "UnityEngine", "Transform");
    void *rectTransformClass = classFromName(coreImage, "UnityEngine", "RectTransform");
    void *cameraClass        = classFromName(coreImage, "UnityEngine", "Camera");
    void *eventSystemClass   = classFromName(uiImage, "UnityEngine.EventSystems", "EventSystem");
    void *pointerEventDataClass =
        classFromName(uiImage, "UnityEngine.EventSystems", "PointerEventData");
    void *canvasClass =
        uiModuleImage != nullptr ? classFromName(uiModuleImage, "UnityEngine", "Canvas") : nullptr;
    const void *getGameObject = findMethodInHierarchy(buttonClass, "get_gameObject");
    const void *getComponentInParent =
        findMethodInHierarchy(buttonClass, "GetComponentInParent", 2);
    const void *getName =
        gameObjectClass != nullptr ? findMethodInHierarchy(gameObjectClass, "get_name") : nullptr;
    const void *getActiveInHierarchy =
        gameObjectClass != nullptr ? findMethodInHierarchy(gameObjectClass, "get_activeInHierarchy")
                                   : nullptr;
    const void *getTransform = gameObjectClass != nullptr
                                   ? findMethodInHierarchy(gameObjectClass, "get_transform")
                                   : nullptr;
    const void *getParent =
        transformClass != nullptr ? findMethodInHierarchy(transformClass, "get_parent") : nullptr;
    const void *getPosition =
        transformClass != nullptr ? findMethodInHierarchy(transformClass, "get_position") : nullptr;
    const void *transformPoint = transformClass != nullptr
                                     ? findMethodInHierarchy(transformClass, "TransformPoint", 1)
                                     : nullptr;
    const void *getRect        = rectTransformClass != nullptr
                                     ? findMethodInHierarchy(rectTransformClass, "get_rect")
                                     : nullptr;
    const void *getWorldCamera =
        canvasClass != nullptr ? findMethodInHierarchy(canvasClass, "get_worldCamera") : nullptr;
    const void *getRenderMode =
        canvasClass != nullptr ? findMethodInHierarchy(canvasClass, "get_renderMode") : nullptr;
    const void *worldToScreenPoint =
        cameraClass != nullptr ? findMethodInHierarchy(cameraClass, "WorldToScreenPoint", 1)
                               : nullptr;
    const void *getCurrentEventSystem = eventSystemClass != nullptr
                                            ? findMethodInHierarchy(eventSystemClass, "get_current")
                                            : nullptr;
    const void *raycastAll = eventSystemClass != nullptr
                                 ? findMethodInHierarchy(eventSystemClass, "RaycastAll", 2)
                                 : nullptr;
    const void *pointerEventDataConstructor =
        pointerEventDataClass != nullptr ? findMethodInHierarchy(pointerEventDataClass, ".ctor", 1)
                                         : nullptr;
    const void *setPointerPosition =
        pointerEventDataClass != nullptr
            ? findMethodInHierarchy(pointerEventDataClass, "set_position", 1)
            : nullptr;
    void *canvasTypeObject =
        canvasClass != nullptr ? typeGetObject(classGetType(canvasClass)) : nullptr;

    void *raycastListClass = nullptr;
    if (raycastAll != nullptr)
    {
        const void *listType = methodGetParam(raycastAll, 1);
        raycastListClass     = listType != nullptr ? classFromType(listType) : nullptr;
    }
    const void *raycastListConstructor =
        raycastListClass != nullptr ? findMethodInHierarchy(raycastListClass, ".ctor") : nullptr;
    const void *clearRaycastList =
        raycastListClass != nullptr ? findMethodInHierarchy(raycastListClass, "Clear") : nullptr;
    const void *getRaycastCount = raycastListClass != nullptr
                                      ? findMethodInHierarchy(raycastListClass, "get_Count")
                                      : nullptr;
    const void *getRaycastItem  = raycastListClass != nullptr
                                      ? findMethodInHierarchy(raycastListClass, "get_Item", 1)
                                      : nullptr;
    void *raycastResultClass    = nullptr;
    if (getRaycastItem != nullptr)
    {
        const void *resultType = methodGetReturnType(getRaycastItem);
        raycastResultClass     = resultType != nullptr ? classFromType(resultType) : nullptr;
    }
    void *raycastGameObjectField = raycastResultClass != nullptr
                                       ? classGetFieldFromName(raycastResultClass, "m_GameObject")
                                       : nullptr;

    struct Vector2
    {
        float x;
        float y;
    };
    struct Vector3
    {
        float x;
        float y;
        float z;
    };
    struct Rect
    {
        float x;
        float y;
        float width;
        float height;
    };

    auto invokeObject = [&](const void *method, void *instance, void **arguments = nullptr) {
        if (method == nullptr)
        {
            return static_cast<void *>(nullptr);
        }
        void *invokeException = nullptr;
        void *value           = runtimeInvoke(method, instance, arguments, &invokeException);
        return invokeException == nullptr ? value : static_cast<void *>(nullptr);
    };
    auto invokeVoid = [&](const void *method, void *instance, void **arguments = nullptr) {
        if (method == nullptr)
        {
            return false;
        }
        void *invokeException = nullptr;
        runtimeInvoke(method, instance, arguments, &invokeException);
        return invokeException == nullptr;
    };
    auto invokeValue = [&](const void *method, void *instance, void **arguments, void *destination,
                           size_t destinationSize) {
        void *boxed = invokeObject(method, instance, arguments);
        if (boxed == nullptr)
        {
            return false;
        }
        void *unboxed = objectUnbox(boxed);
        if (unboxed == nullptr)
        {
            return false;
        }
        ANGLE_UNSAFE_TODO(std::memcpy(destination, unboxed, destinationSize));
        return true;
    };
    auto readString = [&](void *stringObject) {
        std::string value;
        if (stringObject == nullptr)
        {
            return value;
        }
        const int32_t length       = stringLength(stringObject);
        const uint16_t *characters = stringChars(stringObject);
        if (length <= 0 || length > 1024 || characters == nullptr)
        {
            return value;
        }
        value.reserve(static_cast<size_t>(length));
        for (int32_t index = 0; index < length; ++index)
        {
            uint32_t codePoint = ANGLE_UNSAFE_BUFFERS(characters[index]);
            if (codePoint >= 0xD800u && codePoint <= 0xDBFFu && index + 1 < length)
            {
                const uint32_t low = ANGLE_UNSAFE_BUFFERS(characters[index + 1]);
                if (low >= 0xDC00u && low <= 0xDFFFu)
                {
                    codePoint = 0x10000u + ((codePoint - 0xD800u) << 10u) + (low - 0xDC00u);
                    ++index;
                }
            }
            if (codePoint <= 0x7Fu)
            {
                value.push_back(static_cast<char>(codePoint));
            }
            else if (codePoint <= 0x7FFu)
            {
                value.push_back(static_cast<char>(0xC0u | (codePoint >> 6u)));
                value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
            }
            else if (codePoint <= 0xFFFFu)
            {
                value.push_back(static_cast<char>(0xE0u | (codePoint >> 12u)));
                value.push_back(static_cast<char>(0x80u | ((codePoint >> 6u) & 0x3Fu)));
                value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
            }
            else if (codePoint <= 0x10FFFFu)
            {
                value.push_back(static_cast<char>(0xF0u | (codePoint >> 18u)));
                value.push_back(static_cast<char>(0x80u | ((codePoint >> 12u) & 0x3Fu)));
                value.push_back(static_cast<char>(0x80u | ((codePoint >> 6u) & 0x3Fu)));
                value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
            }
        }
        return value;
    };
    auto invokeString = [&](void *instance) { return readString(invokeObject(getName, instance)); };

    void *eventSystem = invokeObject(getCurrentEventSystem, nullptr);
    void *pointerEventData =
        pointerEventDataClass != nullptr ? objectNew(pointerEventDataClass) : nullptr;
    void *raycastResults = raycastListClass != nullptr ? objectNew(raycastListClass) : nullptr;
    bool raycastReady    = eventSystem != nullptr && pointerEventData != nullptr &&
                           raycastResults != nullptr && pointerEventDataConstructor != nullptr &&
                           setPointerPosition != nullptr && raycastAll != nullptr &&
                           raycastListConstructor != nullptr && clearRaycastList != nullptr &&
                           getRaycastCount != nullptr && getRaycastItem != nullptr &&
                           raycastGameObjectField != nullptr;
    if (raycastReady)
    {
        void *pointerArguments[] = {eventSystem};
        raycastReady =
            invokeVoid(pointerEventDataConstructor, pointerEventData, pointerArguments) &&
            invokeVoid(raycastListConstructor, raycastResults);
    }

    auto topRaycastMatches = [&](void *buttonTransform, const Vector2 &position, bool *evaluated) {
        *evaluated = false;
        if (!raycastReady || buttonTransform == nullptr)
        {
            return false;
        }
        if (!invokeVoid(clearRaycastList, raycastResults))
        {
            return false;
        }
        Vector2 pointerPosition   = position;
        void *positionArguments[] = {&pointerPosition};
        if (!invokeVoid(setPointerPosition, pointerEventData, positionArguments))
        {
            return false;
        }
        void *raycastArguments[] = {pointerEventData, raycastResults};
        if (!invokeVoid(raycastAll, eventSystem, raycastArguments))
        {
            return false;
        }
        int32_t count = 0;
        if (!invokeValue(getRaycastCount, raycastResults, nullptr, &count, sizeof(count)) ||
            count < 0 || count > 4096)
        {
            return false;
        }
        *evaluated = true;
        if (count == 0)
        {
            return false;
        }
        int32_t firstIndex    = 0;
        void *itemArguments[] = {&firstIndex};
        void *firstResult     = invokeObject(getRaycastItem, raycastResults, itemArguments);
        if (firstResult == nullptr)
        {
            return false;
        }
        void *topGameObject = nullptr;
        fieldGetValue(firstResult, raycastGameObjectField, &topGameObject);
        if (topGameObject == nullptr)
        {
            return false;
        }
        void *topTransform = invokeObject(getTransform, topGameObject);
        for (int depth = 0; topTransform != nullptr && depth < 24; ++depth)
        {
            if (topTransform == buttonTransform)
            {
                return true;
            }
            topTransform = getParent != nullptr ? invokeObject(getParent, topTransform) : nullptr;
        }
        return false;
    };

    void *exception = nullptr;
    void *sceneBox  = runtimeInvoke(getActiveScene, nullptr, nullptr, &exception);
    if (exception != nullptr || sceneBox == nullptr)
    {
        return result;
    }
    result.diagnosticStage = 40;
    void *sceneValue       = objectUnbox(sceneBox);
    if (sceneValue == nullptr)
    {
        return result;
    }
    result.diagnosticStage = 50;
    ANGLE_UNSAFE_TODO(std::memcpy(&result.sceneHandle, sceneValue, sizeof(result.sceneHandle)));

    LivenessCollector collector;
    collector.allocate     = allocate;
    collector.release      = release;
    result.diagnosticStage = 60;
    stopGcWorld();
    void *livenessState =
        livenessAllocate(buttonClass, 0, CollectLivenessObjects, &collector, ReallocateLiveness);
    if (livenessState != nullptr)
    {
        livenessFromStatics(livenessState);
        livenessFinalize(livenessState);
    }
    startGcWorld();
    if (livenessState == nullptr)
    {
        return result;
    }
    livenessFree(livenessState);
    result.diagnosticStage = 90;
    const size_t length    = collector.count;
    for (size_t index = 0; index < length; ++index)
    {
        void *button = collector.objects[index];
        if (button == nullptr)
        {
            continue;
        }
        ++result.buttonCount;
        auto invokeBoolean = [&](const void *method, bool *value) {
            void *invokeException = nullptr;
            void *boxed           = runtimeInvoke(method, button, nullptr, &invokeException);
            if (invokeException != nullptr || boxed == nullptr)
            {
                return false;
            }
            void *unboxed = objectUnbox(boxed);
            if (unboxed == nullptr)
            {
                return false;
            }
            uint8_t raw = 0;
            ANGLE_UNSAFE_TODO(std::memcpy(&raw, unboxed, sizeof(raw)));
            *value = raw != 0;
            return true;
        };
        bool active       = false;
        bool interactable = false;
        if (!invokeBoolean(getActiveAndEnabled, &active) ||
            !invokeBoolean(getInteractable, &interactable))
        {
            result.diagnosticStage = 95;
            return result;
        }
        result.activeCount += active ? 1u : 0u;
        result.interactableCount += interactable ? 1u : 0u;

        if (!active || getGameObject == nullptr || getTransform == nullptr || getName == nullptr)
        {
            continue;
        }
        void *gameObject       = invokeObject(getGameObject, button);
        void *transform        = invokeObject(getTransform, gameObject);
        bool activeInHierarchy = false;
        if (gameObject == nullptr || transform == nullptr || getActiveInHierarchy == nullptr ||
            !invokeValue(getActiveInHierarchy, gameObject, nullptr, &activeInHierarchy,
                         sizeof(uint8_t)))
        {
            ++result.recordErrors;
            continue;
        }
        if (!activeInHierarchy)
        {
            continue;
        }
        if (result.recordCount >= result.records.size())
        {
            result.recordTruncated = 1;
            continue;
        }

        ObserverButtonRecord &record = result.records[result.recordCount++];
        record.flags                 = 0x1u | 0x2u | (interactable ? 0x4u : 0u);
        const std::string objectName = invokeString(gameObject);
        if (!objectName.empty())
        {
            if (!CopyBoundedString(objectName, &record.name))
            {
                record.flags |= 0x200u;
            }
            record.flags |= 0x8u;
        }

        std::string path;
        void *currentTransform = transform;
        for (int depth = 0; currentTransform != nullptr && depth < 24; ++depth)
        {
            const std::string part = invokeString(currentTransform);
            if (part.empty())
            {
                break;
            }
            path = path.empty() ? part : part + "/" + path;
            currentTransform =
                getParent != nullptr ? invokeObject(getParent, currentTransform) : nullptr;
        }
        if (!path.empty())
        {
            if (!CopyBoundedString(path, &record.path))
            {
                record.flags |= 0x200u;
            }
            record.flags |= 0x10u;
        }

        Vector3 world = {};
        if (getPosition != nullptr &&
            invokeValue(getPosition, transform, nullptr, &world, sizeof(world)))
        {
            record.worldX = world.x;
            record.worldY = world.y;
            record.worldZ = world.z;
            record.flags |= 0x20u;
        }
        Rect rect = {};
        if (getRect != nullptr && invokeValue(getRect, transform, nullptr, &rect, sizeof(rect)))
        {
            record.rectX      = rect.x;
            record.rectY      = rect.y;
            record.rectWidth  = rect.width;
            record.rectHeight = rect.height;
            record.flags |= 0x40u;
        }

        void *canvas = nullptr;
        if (getComponentInParent != nullptr && canvasTypeObject != nullptr)
        {
            uint8_t includeInactive = 0;
            void *arguments[]       = {canvasTypeObject, &includeInactive};
            canvas                  = invokeObject(getComponentInParent, button, arguments);
        }
        int32_t renderMode = -1;
        if (canvas != nullptr)
        {
            const std::string canvasName = invokeString(canvas);
            if (!canvasName.empty())
            {
                if (!CopyBoundedString(canvasName, &record.canvasName))
                {
                    record.flags |= 0x200u;
                }
            }
            if (getRenderMode != nullptr)
            {
                invokeValue(getRenderMode, canvas, nullptr, &renderMode, sizeof(renderMode));
            }
            record.canvasRenderMode = renderMode;
            record.flags |= 0x80u;
        }

        Vector3 screen       = {};
        bool screenValid     = false;
        void *camera         = canvas != nullptr && getWorldCamera != nullptr
                                   ? invokeObject(getWorldCamera, canvas)
                                   : nullptr;
        auto projectToScreen = [&](const Vector3 &worldPoint, Vector3 *screenPoint) {
            if (camera != nullptr && worldToScreenPoint != nullptr)
            {
                Vector3 argument  = worldPoint;
                void *arguments[] = {&argument};
                return invokeValue(worldToScreenPoint, camera, arguments, screenPoint,
                                   sizeof(*screenPoint));
            }
            if (renderMode == 0)
            {
                *screenPoint = worldPoint;
                return true;
            }
            return false;
        };
        if ((record.flags & 0x20u) != 0)
        {
            screenValid = projectToScreen(world, &screen);
        }
        if (screenValid)
        {
            record.screenX = screen.x;
            record.screenY = screen.y;
            record.adbX    = screen.x;
            record.adbY    = static_cast<float>(screenHeight) - screen.y;
            record.flags |= 0x100u;
        }
        if (transformPoint != nullptr && (record.flags & 0x40u) != 0)
        {
            const std::array<Vector3, 4> localCorners = {
                Vector3{rect.x, rect.y, 0.0f},
                Vector3{rect.x + rect.width, rect.y, 0.0f},
                Vector3{rect.x + rect.width, rect.y + rect.height, 0.0f},
                Vector3{rect.x, rect.y + rect.height, 0.0f},
            };
            float left       = std::numeric_limits<float>::max();
            float bottom     = std::numeric_limits<float>::max();
            float right      = std::numeric_limits<float>::lowest();
            float top        = std::numeric_limits<float>::lowest();
            bool boundsValid = true;
            for (const Vector3 &localCorner : localCorners)
            {
                Vector3 localArgument = localCorner;
                void *arguments[]     = {&localArgument};
                Vector3 worldCorner   = {};
                Vector3 screenCorner  = {};
                if (!invokeValue(transformPoint, transform, arguments, &worldCorner,
                                 sizeof(worldCorner)) ||
                    !projectToScreen(worldCorner, &screenCorner))
                {
                    boundsValid = false;
                    break;
                }
                left   = std::min(left, screenCorner.x);
                bottom = std::min(bottom, screenCorner.y);
                right  = std::max(right, screenCorner.x);
                top    = std::max(top, screenCorner.y);
            }
            if (boundsValid)
            {
                record.screenLeft   = left;
                record.screenBottom = bottom;
                record.screenRight  = right;
                record.screenTop    = top;
                record.adbLeft      = left;
                record.adbTop       = static_cast<float>(screenHeight) - top;
                record.adbRight     = right;
                record.adbBottom    = static_cast<float>(screenHeight) - bottom;
                record.flags |= 0x400u;
            }
        }
        if (ShouldEvaluateTopRaycast(objectName, path) && (record.flags & 0x100u) != 0 &&
            (record.flags & 0x400u) != 0)
        {
            bool raycastEvaluated     = false;
            const bool raycastMatches = topRaycastMatches(
                transform, Vector2{record.screenX, record.screenY}, &raycastEvaluated);
            if (raycastEvaluated)
            {
                record.flags |= 0x800u;
                record.flags |= raycastMatches ? 0x1000u : 0u;
            }
        }
    }
    result.success         = true;
    result.diagnosticStage = 100;
    return result;
}
}  // namespace
#endif

Il2CppDynamicProbe ProbeIl2CppDynamicSymbols()
{
    static const Il2CppDynamicProbe result = [] {
        Il2CppDynamicProbe resolved;
#if defined(ANGLE_PLATFORM_ANDROID)
        dl_iterate_phdr(FindAndResolveIl2Cpp, &resolved);
#endif
        return resolved;
    }();
    return result;
}

namespace
{
std::mutex gObserverSnapshotMutex;
ObserverSnapshot gObserverSnapshot;
ObserverSemanticSnapshot gObserverSemanticSnapshot;
std::atomic<uint64_t> gObserverGeneration{0};
std::atomic<int> gObserverMainThreadTid{0};
std::atomic<int32_t> gLastSceneHandle{0};
std::atomic<uint64_t> gSceneGeneration{0};
std::atomic<uint32_t> gLastSemanticState{0};
std::atomic<uint64_t> gSemanticGeneration{0};
}  // namespace

int32_t ObserverMainThreadTick(uint64_t requestGeneration,
                               uint64_t sceneGeneration,
                               uint32_t semanticCode,
                               uint64_t semanticGeneration,
                               int width,
                               int height,
                               int expectedTid)
{
    ObserverSnapshot snapshot;
    ObserverSemanticSnapshot semanticSnapshot;
#if defined(ANGLE_PLATFORM_ANDROID)
    const int actualTid = gettid();
    snapshot.tid        = actualTid;
    if (actualTid != expectedTid)
    {
        snapshot.flags = 0x80000002u;
        return -2;
    }
    if (requestGeneration == 0 || sceneGeneration == 0 || semanticGeneration == 0 ||
        (semanticCode != 1 && semanticCode != 2) || width != 1280 || height != 720)
    {
        snapshot.flags = 0x80000003u;
        return -3;
    }

    const Il2CppDynamicProbe probe = ProbeIl2CppDynamicSymbols();
    if (!probe.dynamicParsed || probe.symbolCount != kIl2CppAllowlistSize)
    {
        snapshot.flags = 0x80000001u;
        return -1;
    }

    using DomainGet                = void *(*)();
    using DomainGetAssemblies      = const void **(*)(const void *, size_t *);
    using AssemblyGetImage         = const void *(*)(const void *);
    using ImageGetName             = const char *(*)(const void *);
    using ThreadAttach             = void *(*)(const void *);
    using ThreadDetach             = void (*)(void *);
    using ThreadCurrent            = void *(*)();
    const auto domainGet           = reinterpret_cast<DomainGet>(probe.symbols[0]);
    const auto domainGetAssemblies = reinterpret_cast<DomainGetAssemblies>(probe.symbols[1]);
    const auto assemblyGetImage    = reinterpret_cast<AssemblyGetImage>(probe.symbols[2]);
    const auto imageGetName        = reinterpret_cast<ImageGetName>(probe.symbols[3]);
    const auto threadAttach        = reinterpret_cast<ThreadAttach>(probe.symbols[4]);
    const auto threadDetach        = reinterpret_cast<ThreadDetach>(probe.symbols[5]);
    const auto threadCurrent       = reinterpret_cast<ThreadCurrent>(probe.symbols[6]);

    void *domain = domainGet();
    if (domain == nullptr)
    {
        snapshot.flags = 0x80000004u;
        return -4;
    }
    void *currentThread       = threadCurrent();
    const bool observerAttach = currentThread == nullptr;
    if (observerAttach)
    {
        currentThread = threadAttach(domain);
        if (currentThread == nullptr)
        {
            snapshot.flags = 0x80000007u;
            return -7;
        }
    }
    size_t assemblyCount    = 0;
    const void **assemblies = domainGetAssemblies(domain, &assemblyCount);
    if (assemblies == nullptr || assemblyCount == 0 || assemblyCount > 512)
    {
        if (observerAttach)
        {
            threadDetach(currentThread);
        }
        snapshot.flags = 0x80000005u;
        return -5;
    }

    bool assemblyCSharp       = false;
    bool unityUi              = false;
    const void *coreImage     = nullptr;
    const void *uiImage       = nullptr;
    const void *uiModuleImage = nullptr;
    for (size_t index = 0; index < assemblyCount; ++index)
    {
        const void *assembly = ANGLE_UNSAFE_BUFFERS(assemblies[index]);
        const void *image    = assemblyGetImage(assembly);
        const char *name     = image != nullptr ? imageGetName(image) : nullptr;
        if (name == nullptr)
        {
            continue;
        }
        const std::string_view imageName(name);
        assemblyCSharp |= imageName == "Assembly-CSharp" || imageName == "Assembly-CSharp.dll";
        unityUi |= imageName == "UnityEngine.UI" || imageName == "UnityEngine.UI.dll";
        if (imageName == "UnityEngine.CoreModule" || imageName == "UnityEngine.CoreModule.dll")
        {
            coreImage = image;
        }
        if (imageName == "UnityEngine.UI" || imageName == "UnityEngine.UI.dll")
        {
            uiImage = image;
        }
        if (imageName == "UnityEngine.UIModule" || imageName == "UnityEngine.UIModule.dll")
        {
            uiModuleImage = image;
        }
    }
    if (!assemblyCSharp || !unityUi)
    {
        if (observerAttach)
        {
            threadDetach(currentThread);
        }
        snapshot.flags = 0x80000006u;
        return -6;
    }

    snapshot.structSize         = sizeof(ObserverSnapshot);
    snapshot.schema             = 1;
    snapshot.assemblyCount      = static_cast<uint32_t>(assemblyCount);
    snapshot.requestGeneration  = requestGeneration;
    snapshot.sceneGeneration    = sceneGeneration;
    snapshot.semanticGeneration = semanticGeneration;
    snapshot.monotonicNanos =
        static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
                                  std::chrono::steady_clock::now().time_since_epoch())
                                  .count());
    semanticSnapshot.requestGeneration = requestGeneration;
    semanticSnapshot.monotonicNanos    = snapshot.monotonicNanos;
    snapshot.semanticCode              = semanticCode;
    snapshot.width                     = width;
    snapshot.height                    = height;
    snapshot.flags                     = 0x7;
    snapshot.processId                 = static_cast<uint32_t>(getpid());
    snapshot.observerAttached          = observerAttach ? 1u : 0u;
    snapshot.mainThread                = actualTid == gObserverMainThreadTid.load() ? 1u : 0u;
    if (snapshot.mainThread != 0)
    {
        const UiProbeResult ui     = ProbeUnityUi(probe, coreImage, uiImage, uiModuleImage, height);
        snapshot.uiDiagnosticStage = ui.diagnosticStage;
        snapshot.uiMethodMask      = ui.methodMask;
        semanticSnapshot.buttonCount = ui.recordCount;
        semanticSnapshot.truncated   = ui.recordTruncated;
        semanticSnapshot.errorCount  = ui.recordErrors;
        semanticSnapshot.buttons     = ui.records;
        if (ui.success)
        {
            snapshot.flags |= 0x8;
            snapshot.buttonCount             = ui.buttonCount;
            snapshot.activeButtonCount       = ui.activeCount;
            snapshot.interactableButtonCount = ui.interactableCount;
            snapshot.semanticState =
                ui.buttonCount == 0 ? 0u : (ui.interactableCount > 0 ? 1u : 2u);
            snapshot.sceneHandle = ui.sceneHandle;

            const uint64_t priorSceneGeneration = gSceneGeneration.load();
            const int32_t priorSceneHandle      = gLastSceneHandle.exchange(ui.sceneHandle);
            if (priorSceneGeneration == 0 || priorSceneHandle != ui.sceneHandle)
            {
                gSceneGeneration.fetch_add(1);
            }
            snapshot.sceneGeneration = gSceneGeneration.load();

            const uint64_t priorSemanticGeneration = gSemanticGeneration.load();
            const uint32_t priorSemanticState = gLastSemanticState.exchange(snapshot.semanticState);
            if (priorSemanticGeneration == 0 || priorSemanticState != snapshot.semanticState)
            {
                gSemanticGeneration.fetch_add(1);
            }
            snapshot.semanticGeneration = gSemanticGeneration.load();
            snapshot.semanticCode       = snapshot.semanticState;
        }
    }

    static uint64_t lastSemanticGeneration = 0;
    if (requestGeneration == 1 || requestGeneration % 10 == 0 ||
        semanticGeneration != lastSemanticGeneration)
    {
        lastSemanticGeneration = semanticGeneration;
        __android_log_print(ANDROID_LOG_INFO, "ALAS_G3",
                            "ALAS_G3_SNAPSHOT {\"schema\":1,\"request_generation\":%" PRIu64
                            ",\"scene_generation\":%" PRIu64
                            ",\"semantic_code\":%u,"
                            "\"semantic_generation\":%" PRIu64
                            ",\"width\":%d,\"height\":%d,"
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
    if (observerAttach)
    {
        threadDetach(currentThread);
    }
    {
        std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
        gObserverSnapshot         = snapshot;
        gObserverSemanticSnapshot = semanticSnapshot;
    }
    return 0;
#else
    snapshot.flags = 0x80000009u;
    return -9;
#endif
}

int32_t ObserverFrameTick(uint64_t frameGeneration, int width, int height)
{
#if defined(ANGLE_PLATFORM_ANDROID)
    static_cast<void>(frameGeneration);
    RegisterObserverMainThread();
    const int32_t mainThreadTid = gObserverMainThreadTid.load();
    if (mainThreadTid == 0 || gettid() != mainThreadTid)
    {
        return mainThreadTid;
    }
    const uint64_t generation = gObserverGeneration.fetch_add(1) + 1;
    return ObserverMainThreadTick(generation, 1, 1, 1, width, height, gettid());
#else
    return -9;
#endif
}

void RegisterObserverMainThread()
{
#if defined(ANGLE_PLATFORM_ANDROID)
    const Il2CppDynamicProbe probe = ProbeIl2CppDynamicSymbols();
    if (probe.symbols[6] == 0)
    {
        return;
    }
    using ThreadCurrent        = void *(*)();
    const auto threadCurrent   = reinterpret_cast<ThreadCurrent>(probe.symbols[6]);
    const void *currentThread  = threadCurrent();
    int32_t expectedThreadTid  = 0;
    const int32_t candidateTid = gettid();
    if (currentThread != nullptr &&
        gObserverMainThreadTid.compare_exchange_strong(expectedThreadTid, candidateTid))
    {
        __android_log_print(ANDROID_LOG_INFO, "ALAS_G3",
                            "ALAS_G3_MAIN_THREAD {\"tid\":%d,\"il2cpp_attached\":true}",
                            candidateTid);
    }
#endif
}

bool GetLatestObserverSnapshot(ObserverSnapshot *snapshot)
{
    if (snapshot == nullptr)
    {
        return false;
    }
    std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
    if (gObserverSnapshot.requestGeneration == 0)
    {
        return false;
    }
    *snapshot = gObserverSnapshot;
    return true;
}

bool GetLatestObserverSemanticSnapshot(ObserverSemanticSnapshot *snapshot)
{
    if (snapshot == nullptr)
    {
        return false;
    }
    std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
    if (gObserverSemanticSnapshot.requestGeneration == 0)
    {
        return false;
    }
    *snapshot = gObserverSemanticSnapshot;
    return true;
}

}  // namespace rx::alas
