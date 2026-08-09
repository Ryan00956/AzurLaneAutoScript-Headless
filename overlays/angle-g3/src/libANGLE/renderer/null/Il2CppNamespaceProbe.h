// Copyright 2026 The ANGLE Project Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef LIBANGLE_RENDERER_NULL_IL2CPPNAMESPACEPROBE_H_
#define LIBANGLE_RENDERER_NULL_IL2CPPNAMESPACEPROBE_H_

#include <array>
#include <cstddef>
#include <cstdint>

namespace rx::alas {

constexpr size_t kIl2CppAllowlistSize = 32;
constexpr size_t kMaxObserverButtons = 64;
constexpr size_t kObserverNameBytes = 96;
constexpr size_t kObserverPathBytes = 384;

struct Il2CppDynamicProbe {
  bool moduleFound = false;
  bool dynamicParsed = false;
  bool dynamicFound = false;
  bool symbolTableFound = false;
  bool stringTableFound = false;
  bool hashFound = false;
  uint32_t diagnosticStage = 0;
  size_t rawSymbolCount = 0;
  size_t symbolCount = 0;
  std::array<uintptr_t, kIl2CppAllowlistSize> symbols = {};
};

struct ObserverSnapshot {
  uint32_t structSize = sizeof(ObserverSnapshot);
  uint32_t schema = 1;
  int32_t tid = 0;
  uint32_t assemblyCount = 0;
  uint64_t requestGeneration = 0;
  uint64_t sceneGeneration = 0;
  uint64_t semanticGeneration = 0;
  uint64_t monotonicNanos = 0;
  uint32_t semanticCode = 0;
  int32_t width = 0;
  int32_t height = 0;
  uint32_t flags = 0;
  uint32_t processId = 0;
  uint32_t observerAttached = 0;
  uint32_t mainThread = 0;
  uint32_t buttonCount = 0;
  uint32_t activeButtonCount = 0;
  uint32_t interactableButtonCount = 0;
  uint32_t semanticState = 0;
  int32_t sceneHandle = 0;
  uint32_t uiDiagnosticStage = 0;
  uint32_t uiMethodMask = 0;
};

static_assert(sizeof(ObserverSnapshot) == 104);

struct ObserverButtonRecord {
  std::array<char, kObserverNameBytes> name = {};
  std::array<char, kObserverPathBytes> path = {};
  std::array<char, kObserverNameBytes> canvasName = {};
  uint32_t flags = 0;
  int32_t canvasRenderMode = -1;
  float worldX = 0.0f;
  float worldY = 0.0f;
  float worldZ = 0.0f;
  float rectX = 0.0f;
  float rectY = 0.0f;
  float rectWidth = 0.0f;
  float rectHeight = 0.0f;
  float screenX = 0.0f;
  float screenY = 0.0f;
  float adbX = 0.0f;
  float adbY = 0.0f;
  float screenLeft = 0.0f;
  float screenBottom = 0.0f;
  float screenRight = 0.0f;
  float screenTop = 0.0f;
  float adbLeft = 0.0f;
  float adbTop = 0.0f;
  float adbRight = 0.0f;
  float adbBottom = 0.0f;
};

struct ObserverSemanticSnapshot {
  uint32_t structSize = sizeof(ObserverSemanticSnapshot);
  uint32_t schema = 1;
  uint64_t requestGeneration = 0;
  uint64_t monotonicNanos = 0;
  uint32_t buttonCount = 0;
  uint32_t truncated = 0;
  uint32_t errorCount = 0;
  uint32_t reserved = 0;
  std::array<ObserverButtonRecord, kMaxObserverButtons> buttons = {};
};

Il2CppDynamicProbe ProbeIl2CppDynamicSymbols();

int32_t ObserverFrameTick(uint64_t frameGeneration, int width, int height);

void RegisterObserverMainThread();

bool GetLatestObserverSnapshot(ObserverSnapshot *snapshot);

bool GetLatestObserverSemanticSnapshot(ObserverSemanticSnapshot *snapshot);

} // namespace rx::alas

#endif // LIBANGLE_RENDERER_NULL_IL2CPPNAMESPACEPROBE_H_
