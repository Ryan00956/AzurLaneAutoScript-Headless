// Copyright 2026 The ANGLE Project Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "libANGLE/renderer/null/ObserverServer.h"

#include "common/platform.h"
#include "common/unsafe_buffers.h"
#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>

#if defined(ANGLE_PLATFORM_ANDROID)
#include <android/log.h>
#include <inttypes.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#endif

namespace rx::alas {
namespace {
constexpr char kProtocolSchema[] = "alas-headless.observer/v1";
constexpr char kDriverRevision[] = "be80ce591a481c12d60c50d6040d40c035b40a2b";

#if defined(ANGLE_PLATFORM_ANDROID)
std::string ReadProcessPackage() {
  FILE *file = std::fopen("/proc/self/cmdline", "rb");
  if (file == nullptr) {
    return {};
  }
  char buffer[256] = {};
  const size_t count = std::fread(buffer, 1, sizeof(buffer) - 1, file);
  std::fclose(file);
  return std::string(buffer, ANGLE_UNSAFE_TODO(strnlen(buffer, count)));
}

uint64_t MonotonicNanos() {
  return static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
}

bool SendAll(int socket, std::string_view response) {
  while (!response.empty()) {
    const ssize_t sent =
        send(socket, response.data(), response.size(), MSG_NOSIGNAL);
    if (sent <= 0) {
      return false;
    }
    response.remove_prefix(static_cast<size_t>(sent));
  }
  return true;
}

void AppendJsonString(std::string *output, std::string_view value) {
  output->push_back('"');
  for (const unsigned char byte : value) {
    switch (byte) {
    case '"':
      output->append("\\\"");
      break;
    case '\\':
      output->append("\\\\");
      break;
    case '\b':
      output->append("\\b");
      break;
    case '\f':
      output->append("\\f");
      break;
    case '\n':
      output->append("\\n");
      break;
    case '\r':
      output->append("\\r");
      break;
    case '\t':
      output->append("\\t");
      break;
    default:
      if (byte < 0x20u) {
        char escaped[7] = {};
        ANGLE_UNSAFE_TODO(std::snprintf(escaped, sizeof(escaped), "\\u%04x",
                                        static_cast<unsigned int>(byte)));
        output->append(escaped);
      } else {
        output->push_back(static_cast<char>(byte));
      }
      break;
    }
  }
  output->push_back('"');
}

template <size_t Size>
std::string_view BoundedStringView(const std::array<char, Size> &value) {
  return std::string_view(
      value.data(), ANGLE_UNSAFE_TODO(strnlen(value.data(), value.size())));
}

std::string SnapshotResponseFor(uid_t peerUid, const std::string &package,
                                const ObserverSnapshot &snapshot) {
  const uint64_t now = MonotonicNanos();
  const uint64_t ageMillis = now >= snapshot.monotonicNanos
                                 ? (now - snapshot.monotonicNanos) / 1000000u
                                 : UINT64_MAX;
  char response[2048];
  const int count = ANGLE_UNSAFE_TODO(std::snprintf(
      response, sizeof(response),
      "{\"protocol_schema\":\"%s\",\"status\":\"ok\",\"package\":\"%s\","
      "\"pid\":%u,\"uid\":%u,\"peer_uid\":%u,\"abi\":\"x86_64\","
      "\"driver_revision\":\"%s\",\"snapshot_schema\":%u,"
      "\"snapshot_struct_size\":%u,\"generation\":%" PRIu64
      ",\"scene_generation\":%" PRIu64 ",\"semantic_generation\":%" PRIu64
      ",\"snapshot_monotonic_ns\":%" PRIu64
      ",\"response_monotonic_ns\":%" PRIu64 ",\"age_ms\":%" PRIu64
      ",\"observer_tid\":%d,\"assembly_count\":%u,"
      "\"semantic_code\":%u,\"width\":%d,\"height\":%d,\"flags\":%u,"
      "\"observer_attached\":%s,\"main_thread\":%s,\"button_count\":%u,"
      "\"active_button_count\":%u,\"interactable_button_count\":%u,"
      "\"scene_handle\":%d,\"ui_stage\":%u,\"ui_method_mask\":%u}\n",
      kProtocolSchema, package.c_str(), snapshot.processId, getuid(), peerUid,
      kDriverRevision, snapshot.schema, snapshot.structSize,
      snapshot.requestGeneration, snapshot.sceneGeneration,
      snapshot.semanticGeneration, snapshot.monotonicNanos, now, ageMillis,
      snapshot.tid, snapshot.assemblyCount, snapshot.semanticCode,
      snapshot.width, snapshot.height, snapshot.flags,
      snapshot.observerAttached != 0 ? "true" : "false",
      snapshot.mainThread != 0 ? "true" : "false", snapshot.buttonCount,
      snapshot.activeButtonCount, snapshot.interactableButtonCount,
      snapshot.sceneHandle, snapshot.uiDiagnosticStage, snapshot.uiMethodMask));
  return count > 0 && static_cast<size_t>(count) < sizeof(response)
             ? std::string(response, static_cast<size_t>(count))
             : std::string();
}

std::string SnapshotResponse(uid_t peerUid, const std::string &package) {
  ObserverSnapshot snapshot;
  if (!GetLatestObserverSnapshot(&snapshot)) {
    char response[512];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(
        response, sizeof(response),
        "{\"protocol_schema\":\"%s\",\"status\":\"unavailable\","
        "\"package\":\"%s\",\"pid\":%d,\"uid\":%u,"
        "\"peer_uid\":%u}\n",
        kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid));
    return count > 0 ? std::string(response, static_cast<size_t>(count))
                     : std::string();
  }
  return SnapshotResponseFor(peerUid, package, snapshot);
}

std::string SemanticResponseFor(uid_t peerUid, const std::string &package,
                                const ObserverSemanticSnapshot &snapshot) {
  const uint64_t now = MonotonicNanos();
  const uint64_t ageMillis = now >= snapshot.monotonicNanos
                                 ? (now - snapshot.monotonicNanos) / 1000000u
                                 : UINT64_MAX;
  std::string response;
  response.reserve(2048 + snapshot.buttonCount * 768u);
  char header[1024];
  const int headerCount = ANGLE_UNSAFE_TODO(std::snprintf(
      header, sizeof(header),
      "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless.buttons/"
      "v1\","
      "\"status\":\"ok\",\"package\":\"%s\",\"pid\":%d,\"uid\":%u,\"peer_uid\":"
      "%u,"
      "\"driver_revision\":\"%s\",\"schema\":%u,\"struct_size\":%u,"
      "\"generation\":%" PRIu64 ",\"snapshot_monotonic_ns\":%" PRIu64
      ",\"response_monotonic_ns\":%" PRIu64 ",\"age_ms\":%" PRIu64
      ",\"button_count\":%u,\"truncated\":%s,\"error_count\":%u,\"buttons\":[",
      kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid,
      kDriverRevision, snapshot.schema, snapshot.structSize,
      snapshot.requestGeneration, snapshot.monotonicNanos, now, ageMillis,
      snapshot.buttonCount, snapshot.truncated != 0 ? "true" : "false",
      snapshot.errorCount));
  if (headerCount <= 0 || static_cast<size_t>(headerCount) >= sizeof(header)) {
    return {};
  }
  response.append(header, static_cast<size_t>(headerCount));

  const size_t buttonCount = std::min(static_cast<size_t>(snapshot.buttonCount),
                                      snapshot.buttons.size());
  for (size_t index = 0; index < buttonCount; ++index) {
    const ObserverButtonRecord &button = snapshot.buttons[index];
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"name\":");
    AppendJsonString(
        &response,
        std::string_view(button.name.data(),
                         ANGLE_UNSAFE_TODO(
                             strnlen(button.name.data(), button.name.size()))));
    response.append(",\"path\":");
    AppendJsonString(
        &response,
        std::string_view(button.path.data(),
                         ANGLE_UNSAFE_TODO(
                             strnlen(button.path.data(), button.path.size()))));
    response.append(",\"canvas\":");
    AppendJsonString(
        &response,
        std::string_view(button.canvasName.data(),
                         ANGLE_UNSAFE_TODO(strnlen(button.canvasName.data(),
                                                   button.canvasName.size()))));

    char fields[1024];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,\"active_and_enabled\":%s,"
        "\"interactable\":%s,\"raycast_top\":%s,\"canvas_render_mode\":%d,"
        "\"world_position\":%s,\"local_rect\":%s,\"screen_point\":%s,"
        "\"adb_point\":%s,\"screen_bounds\":%s,\"adb_bounds\":%s}",
        button.flags, (button.flags & 0x1u) != 0 ? "true" : "false",
        (button.flags & 0x2u) != 0 ? "true" : "false",
        (button.flags & 0x4u) != 0 ? "true" : "false",
        (button.flags & 0x800u) != 0
            ? ((button.flags & 0x1000u) != 0 ? "true" : "false")
            : "null",
        button.canvasRenderMode, (button.flags & 0x20u) != 0 ? "{}" : "null",
        (button.flags & 0x40u) != 0 ? "{}" : "null",
        (button.flags & 0x100u) != 0 ? "{}" : "null",
        (button.flags & 0x100u) != 0 ? "{}" : "null",
        (button.flags & 0x400u) != 0 ? "{}" : "null",
        (button.flags & 0x400u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));

    auto replaceEmptyObject = [&](std::string_view key, bool present,
                                  const char *format, auto... values) {
      if (!present) {
        return;
      }
      const std::string marker = std::string("\"") + std::string(key) + "\":{}";
      const size_t position = response.rfind(marker);
      if (position == std::string::npos) {
        return;
      }
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(
          std::snprintf(value, sizeof(value), format, values...));
      if (count > 0 && static_cast<size_t>(count) < sizeof(value)) {
        response.replace(position, marker.size(), value,
                         static_cast<size_t>(count));
      }
    };
    replaceEmptyObject("world_position", (button.flags & 0x20u) != 0,
                       "\"world_position\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f}",
                       button.worldX, button.worldY, button.worldZ);
    replaceEmptyObject("local_rect", (button.flags & 0x40u) != 0,
                       "\"local_rect\":{\"x\":%.3f,\"y\":%.3f,\"width\":%.3f,"
                       "\"height\":%.3f}",
                       button.rectX, button.rectY, button.rectWidth,
                       button.rectHeight);
    replaceEmptyObject("screen_point", (button.flags & 0x100u) != 0,
                       "\"screen_point\":{\"x\":%.3f,\"y\":%.3f}",
                       button.screenX, button.screenY);
    replaceEmptyObject("adb_point", (button.flags & 0x100u) != 0,
                       "\"adb_point\":{\"x\":%.3f,\"y\":%.3f}", button.adbX,
                       button.adbY);
    replaceEmptyObject("screen_bounds", (button.flags & 0x400u) != 0,
                       "\"screen_bounds\":{\"left\":%.3f,\"bottom\":%.3f,"
                       "\"right\":%.3f,\"top\":%.3f}",
                       button.screenLeft, button.screenBottom,
                       button.screenRight, button.screenTop);
    replaceEmptyObject("adb_bounds", (button.flags & 0x400u) != 0,
                       "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,"
                       "\"right\":%.3f,\"bottom\":%.3f}",
                       button.adbLeft, button.adbTop, button.adbRight,
                       button.adbBottom);
  }
  response.append("]}\n");
  return response;
}

std::string SemanticResponse(uid_t peerUid, const std::string &package) {
  ObserverSemanticSnapshot snapshot;
  if (!GetLatestObserverSemanticSnapshot(&snapshot)) {
    char response[512];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(
        response, sizeof(response),
        "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless."
        "buttons/v1\","
        "\"status\":\"unavailable\",\"package\":\"%s\",\"pid\":%d,\"uid\":%u,"
        "\"peer_uid\":%u}\n",
        kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid));
    return count > 0 ? std::string(response, static_cast<size_t>(count))
                     : std::string();
  }
  return SemanticResponseFor(peerUid, package, snapshot);
}

std::string UiResponse(uid_t peerUid, const std::string &package) {
  ObserverUiSnapshot snapshot;
  if (!GetLatestObserverUiSnapshot(&snapshot)) {
    char response[512];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(
        response, sizeof(response),
        "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless.ui/"
        "v1\",\"status\":\"unavailable\",\"package\":\"%s\",\"pid\":%d,"
        "\"uid\":%u,\"peer_uid\":%u}\n",
        kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid));
    return count > 0 ? std::string(response, static_cast<size_t>(count))
                     : std::string();
  }

  const uint64_t now = MonotonicNanos();
  const uint64_t ageMillis = now >= snapshot.monotonicNanos
                                 ? (now - snapshot.monotonicNanos) / 1000000u
                                 : UINT64_MAX;
  std::string response;
  response.reserve(4096 + snapshot.toggleCount * 768u +
                   snapshot.textCount * 1200u + snapshot.imageCount * 1000u);
  char header[1536];
  const int headerCount = ANGLE_UNSAFE_TODO(std::snprintf(
      header, sizeof(header),
      "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless.ui/v1\","
      "\"status\":\"ok\",\"package\":\"%s\",\"pid\":%d,\"uid\":%u,"
      "\"peer_uid\":%u,\"driver_revision\":\"%s\",\"schema\":%u,"
      "\"struct_size\":%u,\"generation\":%" PRIu64
      ",\"snapshot_monotonic_ns\":%" PRIu64
      ",\"response_monotonic_ns\":%" PRIu64 ",\"age_ms\":%" PRIu64
      ",\"method_mask\":%u,\"toggle_count\":%u,\"text_count\":%u,"
      "\"image_count\":%u,\"toggle_truncated\":%s,\"text_truncated\":%s,"
      "\"image_truncated\":%s,\"error_count\":%u,"
      "\"skipped_count\":%u,"
      "\"toggles\":[",
      kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid,
      kDriverRevision, snapshot.schema, snapshot.structSize,
      snapshot.requestGeneration, snapshot.monotonicNanos, now, ageMillis,
      snapshot.methodMask, snapshot.toggleCount, snapshot.textCount,
      snapshot.imageCount, snapshot.toggleTruncated != 0 ? "true" : "false",
      snapshot.textTruncated != 0 ? "true" : "false",
      snapshot.imageTruncated != 0 ? "true" : "false", snapshot.errorCount,
      snapshot.skippedCount));
  if (headerCount <= 0 || static_cast<size_t>(headerCount) >= sizeof(header)) {
    return {};
  }
  response.append(header, static_cast<size_t>(headerCount));

  const size_t toggleCount = std::min(static_cast<size_t>(snapshot.toggleCount),
                                      snapshot.toggles.size());
  for (size_t index = 0; index < toggleCount; ++index) {
    const ObserverToggleRecord &toggle = snapshot.toggles[index];
    const ObserverButtonRecord &control = toggle.control;
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"kind\":\"toggle\",\"name\":");
    AppendJsonString(&response, BoundedStringView(control.name));
    response.append(",\"path\":");
    AppendJsonString(&response, BoundedStringView(control.path));
    char fields[768];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,"
        "\"active_and_enabled\":%s,\"interactable\":%s,\"checked\":%s,"
        "\"raycast_top\":%s,\"adb_point\":%s,\"adb_bounds\":%s}",
        control.flags, (control.flags & 0x1u) != 0 ? "true" : "false",
        (control.flags & 0x2u) != 0 ? "true" : "false",
        (control.flags & 0x4u) != 0 ? "true" : "false",
        (toggle.stateFlags & 0x1u) != 0
            ? ((toggle.stateFlags & 0x2u) != 0 ? "true" : "false")
            : "null",
        (control.flags & 0x800u) != 0
            ? ((control.flags & 0x1000u) != 0 ? "true" : "false")
            : "null",
        (control.flags & 0x100u) != 0 ? "{}" : "null",
        (control.flags & 0x400u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));
    if ((control.flags & 0x100u) != 0) {
      const std::string marker = "\"adb_point\":{}";
      const size_t position = response.rfind(marker);
      char value[192];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value), "\"adb_point\":{\"x\":%.3f,\"y\":%.3f}",
          control.adbX, control.adbY));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
    if ((control.flags & 0x400u) != 0) {
      const std::string marker = "\"adb_bounds\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,\"right\":%.3f,"
          "\"bottom\":%.3f}",
          control.adbLeft, control.adbTop, control.adbRight,
          control.adbBottom));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
  }

  response.append("],\"texts\":[");
  const size_t textCount =
      std::min(static_cast<size_t>(snapshot.textCount), snapshot.texts.size());
  for (size_t index = 0; index < textCount; ++index) {
    const ObserverTextRecord &record = snapshot.texts[index];
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"kind\":");
    AppendJsonString(&response,
                     (record.flags & 0x200u) != 0 ? "tmp-text" : "ugui-text");
    response.append(",\"name\":");
    AppendJsonString(&response, BoundedStringView(record.name));
    response.append(",\"path\":");
    AppendJsonString(&response, BoundedStringView(record.path));
    response.append(",\"text\":");
    AppendJsonString(&response, BoundedStringView(record.text));
    char fields[512];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,"
        "\"active_and_enabled\":%s,\"adb_bounds\":%s}",
        record.flags, (record.flags & 0x1u) != 0 ? "true" : "false",
        (record.flags & 0x2u) != 0 ? "true" : "false",
        (record.flags & 0x8u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));
    if ((record.flags & 0x8u) != 0) {
      const std::string marker = "\"adb_bounds\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,\"right\":%.3f,"
          "\"bottom\":%.3f}",
          record.adbLeft, record.adbTop, record.adbRight, record.adbBottom));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
  }
  response.append("],\"images\":[");
  const size_t imageCount = std::min(static_cast<size_t>(snapshot.imageCount),
                                     snapshot.images.size());
  for (size_t index = 0; index < imageCount; ++index) {
    const ObserverImageRecord &record = snapshot.images[index];
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"kind\":\"image\",\"name\":");
    AppendJsonString(&response, BoundedStringView(record.name));
    response.append(",\"path\":");
    AppendJsonString(&response, BoundedStringView(record.path));
    response.append(",\"sprite\":");
    AppendJsonString(&response, BoundedStringView(record.spriteName));
    char fields[768];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,"
        "\"active_and_enabled\":%s,\"raycast_target\":%s,\"raycast_top\":%s,"
        "\"color\":{\"red\":%.6f,\"green\":%.6f,\"blue\":%.6f,"
        "\"alpha\":%.6f},\"fill_amount\":%.6f,\"adb_bounds\":%s,"
        "\"anchor_world_position\":%s}",
        record.flags, (record.flags & 0x1u) != 0 ? "true" : "false",
        (record.flags & 0x2u) != 0 ? "true" : "false",
        (record.flags & 0x40u) != 0 ? "true" : "false",
        (record.flags & 0x200u) != 0
            ? ((record.flags & 0x400u) != 0 ? "true" : "false")
            : "null",
        record.red, record.green, record.blue, record.alpha, record.fillAmount,
        (record.flags & 0x4u) != 0 ? "{}" : "null",
        (record.flags & 0x800u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));
    if ((record.flags & 0x4u) != 0) {
      const std::string marker = "\"adb_bounds\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,\"right\":%.3f,"
          "\"bottom\":%.3f}",
          record.adbLeft, record.adbTop, record.adbRight, record.adbBottom));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
    if ((record.flags & 0x800u) != 0) {
      const std::string marker = "\"anchor_world_position\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"anchor_world_position\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f}",
          record.anchorWorldX, record.anchorWorldY, record.anchorWorldZ));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
  }
  response.append("]}\n");
  return response;
}

std::string StateResponse(uid_t peerUid, const std::string &package) {
  ObserverSnapshot observerSnapshot;
  ObserverSemanticSnapshot semanticSnapshot;
  bool coherent = false;
  // Both snapshots are published under the same producer lock. A concurrent
  // publish can occur between the two public getters, so retry and admit only
  // an identical generation rather than claiming false atomicity.
  for (int attempt = 0; attempt < 3 && !coherent; ++attempt) {
    if (!GetLatestObserverSnapshot(&observerSnapshot) ||
        !GetLatestObserverSemanticSnapshot(&semanticSnapshot)) {
      break;
    }
    coherent = observerSnapshot.requestGeneration ==
               semanticSnapshot.requestGeneration;
  }
  if (!coherent) {
    return std::string("{\"protocol_schema\":\"") + kProtocolSchema +
           "\",\"status\":\"unavailable\"}\n";
  }

  std::string snapshot =
      SnapshotResponseFor(peerUid, package, observerSnapshot);
  std::string buttons = SemanticResponseFor(peerUid, package, semanticSnapshot);
  if (!snapshot.empty() && snapshot.back() == '\n') {
    snapshot.pop_back();
  }
  if (!buttons.empty() && buttons.back() == '\n') {
    buttons.pop_back();
  }
  if (snapshot.empty() || buttons.empty()) {
    return {};
  }
  std::string response;
  response.reserve(snapshot.size() + buttons.size() + 128u);
  response.append("{\"protocol_schema\":\"");
  response.append(kProtocolSchema);
  response.append("\",\"status\":\"ok\",\"snapshot\":");
  response.append(snapshot);
  response.append(",\"buttons\":");
  response.append(buttons);
  response.append("}\n");
  return response;
}

void ServeObserver() {
  const pid_t processId = getpid();
  const uid_t processUid = getuid();
  const std::string package = ReadProcessPackage();
  const std::string socketName = "alas.g3." + std::to_string(processId);

  const int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (listener < 0) {
    __android_log_print(ANDROID_LOG_ERROR, "ALAS_G3",
                        "ALAS_G3_SOCKET_ERROR socket=%d", errno);
    return;
  }

  sockaddr_un address = {};
  address.sun_family = AF_UNIX;
  if (socketName.size() + 1 >= sizeof(address.sun_path)) {
    close(listener);
    return;
  }
  ANGLE_UNSAFE_TODO(
      std::memcpy(address.sun_path + 1, socketName.data(), socketName.size()));
  const socklen_t addressLength = static_cast<socklen_t>(
      offsetof(sockaddr_un, sun_path) + 1 + socketName.size());
  if (bind(listener, reinterpret_cast<const sockaddr *>(&address),
           addressLength) != 0 ||
      listen(listener, 4) != 0) {
    __android_log_print(ANDROID_LOG_ERROR, "ALAS_G3",
                        "ALAS_G3_SOCKET_ERROR bind=%d", errno);
    close(listener);
    return;
  }

  ANGLE_UNSAFE_TODO(
      __android_log_print(ANDROID_LOG_INFO, "ALAS_G3",
                          "ALAS_G3_SOCKET {\"schema\":\"%s\",\"name\":\"%s\","
                          "\"package\":\"%s\",\"pid\":%d,\"uid\":%u}",
                          kProtocolSchema, socketName.c_str(), package.c_str(),
                          processId, processUid));

  for (;;) {
    const int client = accept4(listener, nullptr, nullptr, SOCK_CLOEXEC);
    if (client < 0) {
      continue;
    }
    timeval timeout = {2, 0};
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    ucred credentials = {};
    socklen_t credentialsLength = sizeof(credentials);
    const bool credentialOk = getsockopt(client, SOL_SOCKET, SO_PEERCRED,
                                         &credentials, &credentialsLength) == 0;
    const bool peerAllowed =
        credentialOk && (credentials.uid == processUid ||
                         credentials.uid == 0 || credentials.uid == 2000);
    if (!peerAllowed) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"forbidden\"}\n");
      close(client);
      continue;
    }

    char requestBuffer[128] = {};
    const ssize_t received =
        recv(client, requestBuffer, sizeof(requestBuffer) - 1, 0);
    const std::string_view request(
        requestBuffer, received > 0 ? static_cast<size_t>(received) : 0u);
    const bool snapshotRequest =
        request == "GET /v1/snapshot\n" || request == "GET /v1/snapshot\r\n";
    const bool semanticRequest =
        request == "GET /v1/buttons\n" || request == "GET /v1/buttons\r\n";
    const bool uiRequest =
        request == "GET /v1/ui\n" || request == "GET /v1/ui\r\n";
    const bool stateRequest =
        request == "GET /v1/state\n" || request == "GET /v1/state\r\n";
    if (!snapshotRequest && !semanticRequest && !uiRequest && !stateRequest) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"bad-request\"}\n");
    } else if (snapshotRequest) {
      SendAll(client, SnapshotResponse(credentials.uid, package));
    } else if (semanticRequest) {
      SendAll(client, SemanticResponse(credentials.uid, package));
    } else if (stateRequest) {
      SendAll(client, StateResponse(credentials.uid, package));
    } else {
      SendAll(client, UiResponse(credentials.uid, package));
    }
    close(client);
  }
}
#endif
} // namespace

void StartObserverServer() {
#if defined(ANGLE_PLATFORM_ANDROID)
  static std::once_flag once;
  std::call_once(once, [] { std::thread(ServeObserver).detach(); });
#endif
}

} // namespace rx::alas
