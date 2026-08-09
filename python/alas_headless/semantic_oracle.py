"""Fail-closed client for the in-process ALAS headless semantic observer.

The observer is intentionally read-only.  This module performs input through an
independent ADB backend only after package, foreground, freshness, generation,
mapping, bounds, and known-blocker gates have all passed.
"""

from __future__ import annotations

import json
import math
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple


OBSERVER_SCHEMA = "alas-headless.observer/v1"
BUTTON_SCHEMA = "alas-headless.buttons/v1"


class SemanticOracleError(RuntimeError):
    """Base error for semantic observation and action failures."""


class SemanticGateClosed(SemanticOracleError):
    """The requested action was refused because a safety gate is not proven."""


class SemanticTargetMissing(SemanticGateClosed):
    """A mapped semantic target is not present in the current valid snapshot."""


class ObserverTransportError(SemanticOracleError):
    """The local observer transport failed or returned malformed data."""


@dataclass(frozen=True)
class OracleFingerprint:
    package: str
    component: str
    driver_revision: str
    width: int = 1280
    height: int = 720
    max_age_ms: int = 2500
    peer_uid: int = 2000
    expected_pid: Optional[int] = None


@dataclass(frozen=True)
class AndroidPackageFingerprint:
    version_name: str
    version_code: int
    primary_abi: str
    base_apk_sha256: str
    il2cpp_sha256: str


@dataclass(frozen=True)
class SemanticTarget:
    semantic_id: str
    name: str
    path_suffix: str


@dataclass(frozen=True)
class BlockerRule:
    blocker_id: str
    path_fragment: str
    allowed_target_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, point: Point) -> bool:
        return (
            self.left <= point.x <= self.right
            and self.top <= point.y <= self.bottom
        )


@dataclass(frozen=True)
class ButtonState:
    name: str
    path: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    interactable: bool
    raycast_top: Optional[bool]
    point: Optional[Point]
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]

    @property
    def actionable(self) -> bool:
        return (
            self.active_in_hierarchy
            and self.active_and_enabled
            and self.interactable
            and self.raycast_top is True
            and self.point is not None
            and self.bounds is not None
            and self.bounds.contains(self.point)
        )


@dataclass(frozen=True)
class OracleState:
    generation: int
    scene_handle: int
    snapshot: Mapping[str, Any]
    buttons_snapshot: Mapping[str, Any]
    buttons: Tuple[ButtonState, ...]


@dataclass(frozen=True)
class ActionReceipt:
    semantic_id: str
    generation: int
    point: Point
    bounds: Bounds
    path: str


DEFAULT_TARGETS: Tuple[SemanticTarget, ...] = (
    SemanticTarget(
        "login/enter",
        "LoginUI2(Clone)",
        "UICamera/Canvas/UIMain/LoginUI2(Clone)",
    ),
    SemanticTarget("main/battle", "battle", "frame/right/1/battle"),
    SemanticTarget("main/formation", "formation", "frame/right/1/formation"),
    SemanticTarget("main/settings", "settings", "frame/top/btns/settings"),
    SemanticTarget("main/mail", "mail", "frame/top/btns/mail"),
    SemanticTarget("main/shop", "shop", "frame/bottom/frame/shop"),
    SemanticTarget("main/dock", "dock", "frame/bottom/frame/dock"),
    SemanticTarget("main/task", "task", "frame/bottom/frame/task"),
    SemanticTarget("main/build", "build", "frame/bottom/frame/build"),
    SemanticTarget(
        "overlay/bulletin/close",
        "close_btn",
        "NewBulletinBoardUI(Clone)/bg/close_btn",
    ),
    SemanticTarget(
        "settings/back",
        "back_btn",
        "NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn",
    ),
)


DEFAULT_BLOCKERS: Tuple[BlockerRule, ...] = (
    BlockerRule("loading", "/UIOverlay/Loading(Clone)"),
    BlockerRule(
        "bulletin",
        "/NewBulletinBoardUI(Clone)/",
        ("overlay/bulletin/close",),
    ),
)


class TcpObserverTransport:
    """One-request-per-connection client for an ADB-forwarded observer socket."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 3.0,
        maximum_response_bytes: int = 1024 * 1024,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._maximum_response_bytes = maximum_response_bytes

    def request(self, request_line: str) -> Mapping[str, Any]:
        if request_line not in ("GET /v1/snapshot\n", "GET /v1/buttons\n"):
            raise ObserverTransportError("client refused an unsupported observer request")
        try:
            with socket.create_connection(
                (self._host, self._port), self._timeout_seconds
            ) as client:
                client.settimeout(self._timeout_seconds)
                client.sendall(request_line.encode("ascii"))
                chunks = bytearray()
                while True:
                    chunk = client.recv(8192)
                    if not chunk:
                        break
                    chunks.extend(chunk)
                    if len(chunks) > self._maximum_response_bytes:
                        raise ObserverTransportError("observer response exceeded size limit")
                    if b"\n" in chunk:
                        break
        except (OSError, TimeoutError) as exc:
            raise ObserverTransportError("observer socket request failed") from exc

        line = bytes(chunks).split(b"\n", 1)[0]
        if not line:
            raise ObserverTransportError("observer returned an empty response")
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ObserverTransportError("observer returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ObserverTransportError("observer response is not a JSON object")
        return value


class AdbObserverBridge:
    """ADB forwarding, foreground inspection, and tap injection for one game PID."""

    _FOREGROUND_PATTERN = re.compile(
        r"topResumedActivity=.*?\bu\d+\s+([^\s}]+/[^\s}]+)"
    )
    _DEVICE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9_./:+@=~-]+$")
    _SHA256_PATTERN = re.compile(r"^([0-9a-fA-F]{64})(?:\s|$)")

    def __init__(
        self,
        serial: str,
        package: str,
        adb: str = "adb",
        command_timeout_seconds: float = 10.0,
    ) -> None:
        self.serial = serial
        self.package = package
        self.adb = adb
        self.command_timeout_seconds = command_timeout_seconds
        self.pid: Optional[int] = None
        self.port: Optional[int] = None
        self.transport: Optional[TcpObserverTransport] = None

    def _run(
        self,
        arguments: Sequence[str],
        timeout_seconds: Optional[float] = None,
    ) -> str:
        timeout = (
            self.command_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        try:
            completed = subprocess.run(
                [self.adb, "-s", self.serial, *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ObserverTransportError("ADB command failed") from exc
        return completed.stdout.strip()

    def open(self) -> "AdbObserverBridge":
        if self.transport is not None:
            return self
        if self._run(("get-state",)) != "device":
            raise ObserverTransportError("ADB device is not ready")
        pid_text = self._run(("shell", "pidof", self.package))
        if not pid_text.isdigit():
            raise ObserverTransportError("expected exactly one numeric game PID")
        self.pid = int(pid_text)
        port_text = self._run(
            (
                "forward",
                "tcp:0",
                "localabstract:alas.g3.{0}".format(self.pid),
            )
        )
        if not port_text.isdigit():
            raise ObserverTransportError("ADB did not return a forwarding port")
        self.port = int(port_text)
        self.transport = TcpObserverTransport("127.0.0.1", self.port)
        return self

    def close(self) -> None:
        if self.port is not None:
            try:
                self._run(("forward", "--remove", "tcp:{0}".format(self.port)))
            finally:
                self.transport = None
                self.port = None

    def __enter__(self) -> "AdbObserverBridge":
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def request(self, request_line: str) -> Mapping[str, Any]:
        if self.transport is None:
            raise ObserverTransportError("ADB observer bridge is not open")
        return self.transport.request(request_line)

    def foreground_component(self) -> str:
        output = self._run(("shell", "dumpsys", "activity", "activities"))
        match = self._FOREGROUND_PATTERN.search(output)
        return match.group(1) if match else ""

    def tap(self, x: int, y: int) -> None:
        self._run(("shell", "input", "tap", str(x), str(y)))

    @classmethod
    def _device_path(cls, value: str, field: str) -> str:
        path = value.strip()
        if not cls._DEVICE_PATH_PATTERN.fullmatch(path):
            raise SemanticGateClosed("unsafe or malformed device path: {0}".format(field))
        return path

    def _device_sha256(self, path: str) -> str:
        safe_path = self._device_path(path, "sha256 target")
        # The pinned base APK is large enough that hashing it on an emulator can
        # legitimately exceed the normal short ADB command timeout.
        output = self._run(("shell", "sha256sum", safe_path), timeout_seconds=120.0)
        match = self._SHA256_PATTERN.match(output)
        if match is None:
            raise SemanticGateClosed("device sha256 output is malformed")
        return match.group(1).lower()

    def package_fingerprint(self) -> AndroidPackageFingerprint:
        """Read the installed game identity without trusting observer output."""

        package_dump = self._run(("shell", "dumpsys", "package", self.package))
        version_code_match = re.search(r"\bversionCode=(\d+)", package_dump)
        version_name_match = re.search(r"\bversionName=([^\r\n]+)", package_dump)
        primary_abi_match = re.search(r"\bprimaryCpuAbi=([^\r\n]+)", package_dump)
        native_dir_match = re.search(
            r"\b(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\r\n]+)",
            package_dump,
        )
        if not all(
            (
                version_code_match,
                version_name_match,
                primary_abi_match,
                native_dir_match,
            )
        ):
            raise SemanticGateClosed("installed package identity is incomplete")

        base_output = self._run(("shell", "pm", "path", self.package))
        base_paths = [
            line[len("package:") :]
            for line in base_output.splitlines()
            if line.startswith("package:")
        ]
        if len(base_paths) != 1:
            raise SemanticGateClosed("expected exactly one base APK path")
        base_path = self._device_path(base_paths[0], "base APK")
        native_dir = self._device_path(native_dir_match.group(1), "nativeLibraryDir")
        il2cpp_output = self._run(
            (
                "shell",
                "find",
                native_dir,
                "-type",
                "f",
                "-name",
                "libil2cpp.so",
                "-print",
            )
        )
        il2cpp_paths = [line.strip() for line in il2cpp_output.splitlines() if line.strip()]
        if len(il2cpp_paths) != 1:
            raise SemanticGateClosed("expected exactly one libil2cpp.so")
        il2cpp_path = self._device_path(il2cpp_paths[0], "libil2cpp.so")

        return AndroidPackageFingerprint(
            version_name=version_name_match.group(1).strip(),
            version_code=int(version_code_match.group(1)),
            primary_abi=primary_abi_match.group(1).strip(),
            base_apk_sha256=self._device_sha256(base_path),
            il2cpp_sha256=self._device_sha256(il2cpp_path),
        )

    def require_package_fingerprint(
        self, expected: AndroidPackageFingerprint
    ) -> AndroidPackageFingerprint:
        actual = self.package_fingerprint()
        if actual != expected:
            raise SemanticGateClosed("installed package fingerprint is not allowlisted")
        return actual


class SemanticOracle:
    """Mapped semantic observation and input with fail-closed action gates."""

    def __init__(
        self,
        request: Callable[[str], Mapping[str, Any]],
        foreground_component: Callable[[], str],
        tap: Callable[[int, int], None],
        fingerprint: OracleFingerprint,
        targets: Iterable[SemanticTarget] = DEFAULT_TARGETS,
        blockers: Iterable[BlockerRule] = DEFAULT_BLOCKERS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._request = request
        self._foreground_component = foreground_component
        self._tap = tap
        self.fingerprint = fingerprint
        self._targets = self._index_targets(targets)
        self._blockers = tuple(blockers)
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_generation: Optional[int] = None

    @staticmethod
    def _index_targets(
        targets: Iterable[SemanticTarget],
    ) -> Dict[str, SemanticTarget]:
        indexed: Dict[str, SemanticTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError("duplicate semantic target id: {0}".format(target.semantic_id))
            if not target.name or not target.path_suffix:
                raise ValueError("semantic target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _integer(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SemanticGateClosed("invalid integer field: {0}".format(field))
        return value

    @staticmethod
    def _finite_number(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SemanticGateClosed("invalid numeric field: {0}".format(field))
        result = float(value)
        if not math.isfinite(result):
            raise SemanticGateClosed("non-finite numeric field: {0}".format(field))
        return result

    def _validate_identity(self, value: Mapping[str, Any], semantic: bool) -> None:
        if value.get("protocol_schema") != OBSERVER_SCHEMA:
            raise SemanticGateClosed("observer protocol schema mismatch")
        if semantic and value.get("semantic_schema") != BUTTON_SCHEMA:
            raise SemanticGateClosed("button schema mismatch")
        if value.get("status") != "ok":
            raise SemanticGateClosed("observer status is not ok")
        if value.get("package") != self.fingerprint.package:
            raise SemanticGateClosed("observer package mismatch")
        if value.get("driver_revision") != self.fingerprint.driver_revision:
            raise SemanticGateClosed("observer driver revision mismatch")
        if self._integer(value.get("peer_uid"), "peer_uid") != self.fingerprint.peer_uid:
            raise SemanticGateClosed("observer peer credential mismatch")
        if self.fingerprint.expected_pid is not None and self._integer(
            value.get("pid"), "pid"
        ) != self.fingerprint.expected_pid:
            raise SemanticGateClosed("observer PID mismatch")
        if self._integer(value.get("age_ms"), "age_ms") > self.fingerprint.max_age_ms:
            raise SemanticGateClosed("observer snapshot is stale")

    def _parse_button(self, raw: Any) -> ButtonState:
        if not isinstance(raw, dict):
            raise SemanticGateClosed("button record is not an object")
        name = raw.get("name")
        path = raw.get("path")
        if not isinstance(name, str) or not isinstance(path, str) or not name or not path:
            raise SemanticGateClosed("button identity is incomplete")

        point_value = raw.get("adb_point")
        bounds_value = raw.get("adb_bounds")
        point = None
        bounds = None
        if point_value is not None:
            if not isinstance(point_value, dict):
                raise SemanticGateClosed("button point is malformed")
            point = Point(
                self._finite_number(point_value.get("x"), "adb_point.x"),
                self._finite_number(point_value.get("y"), "adb_point.y"),
            )
        if bounds_value is not None:
            if not isinstance(bounds_value, dict):
                raise SemanticGateClosed("button bounds are malformed")
            candidate_bounds = Bounds(
                self._finite_number(bounds_value.get("left"), "adb_bounds.left"),
                self._finite_number(bounds_value.get("top"), "adb_bounds.top"),
                self._finite_number(bounds_value.get("right"), "adb_bounds.right"),
                self._finite_number(bounds_value.get("bottom"), "adb_bounds.bottom"),
            )
            # Some active Unity Buttons are layout sentinels with a zero-area
            # RectTransform. They remain observable but are never actionable.
            if (
                candidate_bounds.left < candidate_bounds.right
                and candidate_bounds.top < candidate_bounds.bottom
            ):
                bounds = candidate_bounds
        raycast_top = raw.get("raycast_top")
        if raycast_top is not None and not isinstance(raycast_top, bool):
            raise SemanticGateClosed("button raycast state is malformed")
        return ButtonState(
            name=name,
            path=path,
            active_in_hierarchy=raw.get("active_in_hierarchy") is True,
            active_and_enabled=raw.get("active_and_enabled") is True,
            interactable=raw.get("interactable") is True,
            raycast_top=raycast_top,
            point=point,
            bounds=bounds,
            raw=raw,
        )

    def read_state(self) -> OracleState:
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity is not top-resumed")
        snapshot = self._request("GET /v1/snapshot\n")
        buttons_snapshot = self._request("GET /v1/buttons\n")
        if not isinstance(snapshot, dict) or not isinstance(buttons_snapshot, dict):
            raise ObserverTransportError("observer response is not a mapping")
        self._validate_identity(snapshot, semantic=False)
        self._validate_identity(buttons_snapshot, semantic=True)

        if snapshot.get("snapshot_schema") != 1 or buttons_snapshot.get("schema") != 1:
            raise SemanticGateClosed("observer snapshot schema mismatch")
        if (
            snapshot.get("main_thread") is not True
            or self._integer(snapshot.get("flags"), "flags") != 15
            or self._integer(snapshot.get("ui_stage"), "ui_stage") != 100
            or self._integer(snapshot.get("ui_method_mask"), "ui_method_mask") != 15
        ):
            raise SemanticGateClosed("typed main-thread UI probe is incomplete")
        if (
            self._integer(snapshot.get("width"), "width") != self.fingerprint.width
            or self._integer(snapshot.get("height"), "height") != self.fingerprint.height
        ):
            raise SemanticGateClosed("logical screen size mismatch")
        if snapshot.get("pid") != buttons_snapshot.get("pid"):
            raise SemanticGateClosed("observer endpoints disagree on PID")

        generation = self._integer(snapshot.get("generation"), "generation")
        button_generation = self._integer(
            buttons_snapshot.get("generation"), "button generation"
        )
        if button_generation < generation or button_generation > generation + 2:
            raise SemanticGateClosed("observer endpoints are not generation-coherent")
        if self._last_generation is not None and generation < self._last_generation:
            raise SemanticGateClosed("observer generation moved backwards")
        self._last_generation = generation

        if buttons_snapshot.get("truncated") is not False:
            raise SemanticGateClosed("button snapshot is truncated")
        if self._integer(buttons_snapshot.get("error_count"), "error_count") != 0:
            raise SemanticGateClosed("button snapshot contains extraction errors")
        raw_buttons = buttons_snapshot.get("buttons")
        if not isinstance(raw_buttons, list):
            raise SemanticGateClosed("button list is malformed")
        if self._integer(buttons_snapshot.get("button_count"), "button_count") != len(
            raw_buttons
        ):
            raise SemanticGateClosed("button count does not match the record list")
        buttons = tuple(self._parse_button(raw) for raw in raw_buttons)
        return OracleState(
            generation=button_generation,
            scene_handle=self._integer(snapshot.get("scene_handle"), "scene_handle"),
            snapshot=snapshot,
            buttons_snapshot=buttons_snapshot,
            buttons=buttons,
        )

    def _mapping(self, semantic_id: str) -> SemanticTarget:
        try:
            return self._targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic target is not mapped: {0}".format(semantic_id)
            ) from exc

    def _matches(self, state: OracleState, semantic_id: str) -> Tuple[ButtonState, ...]:
        target = self._mapping(semantic_id)
        return tuple(
            button
            for button in state.buttons
            if button.name == target.name and button.path.endswith(target.path_suffix)
        )

    def _unique(self, state: OracleState, semantic_id: str) -> ButtonState:
        matches = self._matches(state, semantic_id)
        if not matches:
            raise SemanticTargetMissing("semantic target is absent: {0}".format(semantic_id))
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic target mapping is ambiguous: {0}".format(semantic_id)
            )
        return matches[0]

    def _blocking_rules(
        self, state: OracleState, semantic_id: str
    ) -> Tuple[BlockerRule, ...]:
        return tuple(
            rule
            for rule in self._blockers
            if semantic_id not in rule.allowed_target_ids
            and any(rule.path_fragment in button.path for button in state.buttons)
        )

    def exists(self, semantic_id: str) -> bool:
        return bool(self._matches(self.read_state(), semantic_id))

    def enabled(self, semantic_id: str) -> bool:
        state = self.read_state()
        matches = self._matches(state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed("semantic target mapping is ambiguous")
        return bool(
            matches
            and matches[0].actionable
            and not self._blocking_rules(state, semantic_id)
        )

    def bounds(self, semantic_id: str) -> Bounds:
        target = self._unique(self.read_state(), semantic_id)
        if target.bounds is None:
            raise SemanticGateClosed("semantic target has no screen bounds")
        return target.bounds

    def current_scene(self) -> int:
        return self.read_state().scene_handle

    def click(self, semantic_id: str) -> ActionReceipt:
        state = self.read_state()
        target = self._unique(state, semantic_id)
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("semantic target is not actionable")
        if not (
            0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("semantic target point is outside the screen")

        disallowed = tuple(
            rule.blocker_id for rule in self._blocking_rules(state, semantic_id)
        )
        if disallowed:
            raise SemanticGateClosed(
                "semantic input is blocked by: {0}".format(", ".join(disallowed))
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")

        x = int(round(target.point.x))
        y = int(round(target.point.y))
        self._tap(x, y)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def wait_for(
        self,
        semantic_id: str,
        timeout_seconds: float,
        minimum_generation: Optional[int] = None,
        interval_seconds: float = 0.5,
    ) -> ButtonState:
        deadline = self._monotonic() + timeout_seconds
        last_error: Optional[SemanticOracleError] = None
        while self._monotonic() < deadline:
            try:
                state = self.read_state()
                matches = self._matches(state, semantic_id)
                if len(matches) > 1:
                    raise SemanticGateClosed("semantic target mapping is ambiguous")
                if (
                    matches
                    and matches[0].actionable
                    and (
                        minimum_generation is None
                        or state.generation > minimum_generation
                    )
                ):
                    return matches[0]
            except SemanticOracleError as exc:
                last_error = exc
            self._sleep(interval_seconds)
        if last_error is not None:
            raise SemanticGateClosed("semantic wait timed out") from last_error
        raise SemanticGateClosed("semantic wait timed out")

    def click_and_wait(
        self,
        semantic_id: str,
        expected_semantic_id: str,
        timeout_seconds: float,
    ) -> ButtonState:
        receipt = self.click(semantic_id)
        return self.wait_for(
            expected_semantic_id,
            timeout_seconds,
            minimum_generation=receipt.generation,
        )
