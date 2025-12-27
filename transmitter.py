#!/usr/bin/env python3
"""
Pixel Update Screenshot Sender
Captures a monitor (defaults to the leftmost) as the video source and streams
per-pixel updates to the ESP32 receiver using the same pixel-update protocol.
"""

import argparse
import socket
import struct
import time
from typing import Optional, Sequence

import cv2
import mss
import numpy as np
import ctypes

try:
    from Quartz import CGEventCreate, CGEventGetLocation
except Exception:  # noqa: BLE001
    CGEventCreate = None  # type: ignore
    CGEventGetLocation = None  # type: ignore


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

DEFAULT_IP = "192.168.1.100"
DEFAULT_PORT = 8090
DISPLAY_WIDTH = 179
DISPLAY_HEIGHT = 320
HEADER_VERSION = 0x02  # carries frame_id in header (pixels)
RUN_HEADER_VERSION = 0x01  # version for run packets


class ScreenshotPixelSender:
    def __init__(
        self,
        ip: str,
        port: int,
        monitor_index: Optional[int],
        prefer_largest: bool,
        target_fps: float,
        threshold: int,
        full_frame: bool,
        max_updates_per_frame: int,
        rotate_deg: int,
        show_cursor: bool,
    ) -> None:
        self.ip = ip
        self.port = port
        self.monitor_index = monitor_index
        self.prefer_largest = prefer_largest
        self.target_fps = target_fps
        self.threshold = threshold
        self.full_frame = full_frame
        self.max_updates_per_frame = max_updates_per_frame
        self.rotate_deg = rotate_deg
        self.show_cursor = show_cursor

        self.sock: Optional[socket.socket] = None
        self.prev_rgb: Optional[np.ndarray] = None  # (H, W, 3) uint8
        self.sent_initial_full: bool = False
        self.frame_id: int = 0
        self.monitor: Optional[dict] = None
        self.sct: Optional[mss.mss] = None
        self.cursor_warned: bool = False
        self.cursor_backend: Optional[tuple[str, Optional[ctypes.CDLL]]] = self._init_cursor_backend()

    def _init_cursor_backend(self) -> Optional[tuple[str, Optional[ctypes.CDLL]]]:
        # Prefer Quartz if available (pyobjc); otherwise fall back to CoreGraphics via ctypes
        if CGEventCreate is not None and CGEventGetLocation is not None:
            return ("quartz", None)
        try:
            cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cg.CGEventCreate.restype = ctypes.c_void_p
            cg.CGEventGetLocation.restype = CGPoint
            cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
            return ("ctypes", cg)
        except Exception:
            return None

    # Connection helpers -------------------------------------------------
    def ensure_connection(self) -> bool:
        if self.sock:
            return True
        return self.connect()

    def connect(self, retries: int = 3) -> bool:
        for attempt in range(1, retries + 1):
            try:
                if self.sock:
                    self.sock.close()
                print(f"[CONNECT] Attempt {attempt}/{retries} to {self.ip}:{self.port}")
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock.settimeout(10)
                self.sock.connect((self.ip, self.port))
                print("[CONNECT] ✓ Connected")
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"[CONNECT] ✗ {type(exc).__name__}: {exc}")
                if attempt < retries:
                    time.sleep(2)
        return False

    def disconnect(self) -> None:
        if self.sock:
            self.sock.close()
        self.sock = None
        print("[CONNECT] Disconnected")

    # Monitor helpers ----------------------------------------------------
    @staticmethod
    def _select_monitor(
        monitors: Sequence[dict],
        monitor_index: Optional[int],
        prefer_largest: bool,
    ) -> Optional[dict]:
        if monitor_index is not None:
            if 1 <= monitor_index < len(monitors):
                return monitors[monitor_index]
            print(f"[MON] Invalid monitor index {monitor_index}; available 1..{len(monitors) - 1}")
            return None

        usable_monitors = monitors[1:]  # index 0 is the virtual bounding box
        if not usable_monitors:
            return None

        if prefer_largest:
            return max(
                usable_monitors,
                key=lambda m: m.get("width", 0) * m.get("height", 0),
            )

        # Default: choose the leftmost monitor (smallest 'left' coordinate)
        usable_monitors = monitors[1:]  # index 0 is the virtual bounding box
        if not usable_monitors:
            return None
        return min(usable_monitors, key=lambda m: m.get("left", 0))

    def setup_capture(self) -> bool:
        try:
            self.sct = mss.mss()
        except Exception as exc:  # noqa: BLE001
            print(f"[MON] Unable to start screen capture: {exc}")
            return False

        monitor = self._select_monitor(self.sct.monitors, self.monitor_index, self.prefer_largest)
        if not monitor:
            print("[MON] No monitor selected or available")
            return False

        self.monitor = monitor
        print(
            f"[MON] Using monitor at ({monitor['left']}, {monitor['top']}) "
            f"{monitor['width']}x{monitor['height']}"
        )
        return True

    def grab_frame(self) -> Optional[np.ndarray]:
        if not self.sct or not self.monitor:
            return None
        try:
            shot = self.sct.grab(self.monitor)
        except Exception as exc:  # noqa: BLE001
            print(f"[MON] Capture failed: {exc}")
            return None
        # mss returns BGRA; drop alpha
        frame = np.array(shot)[:, :, :3]
        return frame

    # Cursor helpers -----------------------------------------------------
    def get_cursor_global(self) -> Optional[tuple[int, int]]:
        if not self.cursor_backend:
            if self.show_cursor and not self.cursor_warned:
                print(
                    "[CURSOR] No cursor backend available (need Screen Recording permission and "
                    "either Quartz/pyobjc or CoreGraphics via ctypes)"
                )
                self.cursor_warned = True
            return None
        backend, cg = self.cursor_backend
        try:
            if backend == "quartz":
                evt = CGEventCreate(None)
                if evt is None:
                    return None
                loc = CGEventGetLocation(evt)
                return int(loc.x), int(loc.y)
            if backend == "ctypes" and cg is not None:
                evt = cg.CGEventCreate(None)
                if not evt:
                    return None
                loc = cg.CGEventGetLocation(evt)
                return int(loc.x), int(loc.y)
        except Exception:
            return None
        return None

    def map_cursor_to_local(self, cursor: tuple[int, int]) -> Optional[tuple[int, int]]:
        if not self.monitor:
            return None
        cx, cy = cursor
        left = int(self.monitor.get("left", 0))
        top = int(self.monitor.get("top", 0))
        width = int(self.monitor.get("width", 0))
        height = int(self.monitor.get("height", 0))

        if width <= 0 or height <= 0:
            return None

        local_x = cx - left
        local_y = cy - top
        if local_x < 0 or local_y < 0 or local_x >= width or local_y >= height:
            if self.show_cursor and not self.cursor_warned:
                print(f"[CURSOR] Cursor not on selected monitor (global {cx},{cy})")
                self.cursor_warned = True
            return None  # cursor not on this monitor

        if self.show_cursor and not self.cursor_warned:
            print(f"[CURSOR] Global {cx},{cy} -> local {local_x},{local_y}")
            self.cursor_warned = True
        return int(local_x), int(local_y)

    # Conversion helpers -------------------------------------------------
    @staticmethod
    def rgb888_to_rgb565(rgb: np.ndarray) -> np.ndarray:
        r = (rgb[:, :, 0] >> 3).astype(np.uint16)
        g = (rgb[:, :, 1] >> 2).astype(np.uint16)
        b = (rgb[:, :, 2] >> 3).astype(np.uint16)
        return (r << 11) | (g << 5) | b

    def draw_cursor_icon(self, frame: np.ndarray, point: tuple[int, int]) -> None:
        x, y = point
        # Simple white arrow with black outline, drawn on full-res frame
        scale = 1.8  # enlarge arrow
        pts = np.array(
            [
                (0, 0),
                (0, int(12 * scale)),
                (int(4 * scale), int(10 * scale)),
                (int(8 * scale), int(16 * scale)),
                (int(10 * scale), int(14 * scale)),
                (int(6 * scale), int(8 * scale)),
                (int(12 * scale), int(8 * scale)),
            ],
            dtype=np.int32,
        )
        pts[:, 0] += x
        pts[:, 1] += y

        cv2.fillPoly(frame, [pts], (0, 0, 0))
        cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 0), thickness=2, lineType=cv2.LINE_AA)
        cv2.fillPoly(frame, [pts], (255, 255, 255))
        cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 0), thickness=1, lineType=cv2.LINE_AA)

    def resize_and_convert(
        self, frame: np.ndarray, cursor_point_local: Optional[tuple[int, int]]
    ) -> tuple[np.ndarray, np.ndarray]:
        # Ensure contiguous buffer for OpenCV drawing (mss can return non-contiguous)
        frame = np.ascontiguousarray(frame)

        # Draw cursor on the full-res capture before rotation/scale
        if cursor_point_local:
            cx, cy = cursor_point_local
            h, w, _ = frame.shape
            if 0 <= cx < w and 0 <= cy < h:
                self.draw_cursor_icon(frame, (cx, cy))

        # Apply rotation to match device orientation
        if self.rotate_deg == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotate_deg == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self.rotate_deg == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # Implementing a frame crop
        # [Width, height]
        # frame = frame[1600:1920, 100:400] # youcan change these values to crop the frame as you want
        resized = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT))

        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        rgb565 = self.rgb888_to_rgb565(rgb)
        return rgb, rgb565

    # Packet creation ----------------------------------------------------
    def build_packets(self, rgb: np.ndarray, rgb565: np.ndarray) -> list[bytes]:
        # Force the first frame to be full-frame, then optionally delta-mode
        if self.full_frame or not self.sent_initial_full or self.prev_rgb is None:
            mask = np.ones((DISPLAY_HEIGHT, DISPLAY_WIDTH), dtype=bool)
        else:
            diff = np.abs(rgb.astype(np.int16) - self.prev_rgb.astype(np.int16))
            mask = diff.max(axis=2) > self.threshold

        ys, xs = np.nonzero(mask)
        colors = rgb565[ys, xs]
        count = len(colors)

        # If no pixels changed, send an empty pixel frame to keep sync
        packets: list[bytes] = []
        if count == 0:
            header = (
                b"PXUP"
                + bytes([HEADER_VERSION])
                + struct.pack("<I", self.frame_id)
                + struct.pack("<H", 0)
            )
            packets.append(header)
            self.frame_id += 1
            return packets

        # Try run-length encoding by rows; choose smaller payload
        run_packets = self._build_run_packets(mask, rgb565)
        pixel_packets = self._build_pixel_packets(xs, ys, colors, count)

        run_bytes = sum(len(p) for p in run_packets)
        pixel_bytes = sum(len(p) for p in pixel_packets)
        if run_bytes < pixel_bytes:
            self.frame_id += len(run_packets)
            return run_packets
        self.frame_id += len(pixel_packets)
        return pixel_packets

    def _build_pixel_packets(
        self, xs: np.ndarray, ys: np.ndarray, colors: np.ndarray, count: int
    ) -> list[bytes]:
        packets: list[bytes] = []
        max_per = max(1, self.max_updates_per_frame)
        start = 0
        while start < count:
            end = min(start + max_per, count)
            slice_count = end - start
            header = (
                b"PXUP"
                + bytes([HEADER_VERSION])
                + struct.pack("<I", self.frame_id)
                + struct.pack("<H", slice_count)
            )
            payload = bytearray(header)
            append = payload.extend
            for x, y, color in zip(xs[start:end], ys[start:end], colors[start:end]):
                append(struct.pack("<HHH", int(x), int(y), int(color)))
            packets.append(bytes(payload))
            start = end
        return packets

    def _build_run_packets(self, mask: np.ndarray, rgb565: np.ndarray) -> list[bytes]:
        packets: list[bytes] = []
        max_per = max(1, self.max_updates_per_frame)
        runs: list[tuple[int, int, int, int]] = []  # y, x0, length, color

        for y in range(DISPLAY_HEIGHT):
            row_mask = mask[y]
            if not row_mask.any():
                continue
            x = 0
            while x < DISPLAY_WIDTH:
                if not row_mask[x]:
                    x += 1
                    continue
                x0 = x
                color = int(rgb565[y, x0])
                x += 1
                while x < DISPLAY_WIDTH and row_mask[x] and int(rgb565[y, x]) == color:
                    x += 1
                length = x - x0
                runs.append((y, x0, length, color))

        total_runs = len(runs)
        if total_runs == 0:
            header = (
                b"PXUP"
                + bytes([HEADER_VERSION])
                + struct.pack("<I", self.frame_id)
                + struct.pack("<H", 0)
            )
            packets.append(header)
            return packets

        start = 0
        while start < total_runs:
            end = min(start + max_per, total_runs)
            slice_count = end - start
            header = (
                b"PXUR"
                + bytes([RUN_HEADER_VERSION])
                + struct.pack("<I", self.frame_id)
                + struct.pack("<H", slice_count)
            )
            payload = bytearray(header)
            append = payload.extend
            for y, x0, length, color in runs[start:end]:
                append(struct.pack("<HHHH", y, x0, length, color))
            packets.append(bytes(payload))
            start = end
        return packets

    # Main loop ----------------------------------------------------------
    def run(self) -> None:
        if not self.setup_capture():
            return
        if not self.ensure_connection():
            return

        frame_delay = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        frame_count = 0
        sent_packets = 0
        sent_pixels = 0
        start_t = time.time()

        print("[STREAM] Starting screenshot update loop (Ctrl+C to stop)")
        try:
            while True:
                frame_start = time.time()
                frame = self.grab_frame()
                if frame is None:
                    print("[STREAM] Capture stopped")
                    break

                cursor_point = None
                if self.show_cursor:
                    cur = self.get_cursor_global()
                    if cur:
                        cursor_point = self.map_cursor_to_local(cur)
                    else:
                        print("[CURSOR] Unable to read cursor position")

                rgb, rgb565 = self.resize_and_convert(frame, cursor_point)
                packets = self.build_packets(rgb, rgb565)
                self.prev_rgb = rgb

                if not self.ensure_connection():
                    print("[SEND] Could not reconnect; exiting")
                    break

                for pkt in packets:
                    updates_in_frame = struct.unpack_from("<H", pkt, 9)[0]
                    print(f"[FRAME] id={struct.unpack_from('<I', pkt, 5)[0]} updates={updates_in_frame}")
                    try:
                        self.sock.sendall(pkt)
                        sent_packets += 1
                        sent_pixels += updates_in_frame
                        if not self.sent_initial_full:
                            self.sent_initial_full = True
                    except (BrokenPipeError, ConnectionResetError):
                        print("[SEND] Connection lost; attempting reconnect")
                        self.disconnect()
                        if not self.ensure_connection():
                            print("[SEND] Reconnect failed; exiting")
                            break
                        try:
                            self.sock.sendall(pkt)
                            sent_packets += 1
                            sent_pixels += updates_in_frame
                        except Exception as exc:  # noqa: BLE001
                            print(f"[SEND] Retry failed: {type(exc).__name__}: {exc}")
                            break
                    except Exception as exc:  # noqa: BLE001
                        print(f"[SEND] Error: {type(exc).__name__}: {exc}")
                        self.disconnect()
                        break
                else:
                    frame_count += 1
                    now = time.time()
                    elapsed_frame = now - frame_start
                    if frame_delay > 0 and elapsed_frame < frame_delay:
                        time.sleep(frame_delay - elapsed_frame)

                    # Stats roughly every second
                    if now - start_t >= 1.0:
                        elapsed = now - start_t
                        fps_est = frame_count / elapsed if elapsed > 0 else 0.0
                        print(
                            f"[STATS] frames:{frame_count} packets:{sent_packets} "
                            f"pixels:{sent_pixels} fps~{fps_est:.2f}"
                        )
                        start_t = now
                        frame_count = 0
                        sent_packets = 0
                        sent_pixels = 0
                    continue
                break  # outer while if inner loop broke
        except KeyboardInterrupt:
            print("\n[STREAM] Interrupted by user")
        finally:
            self.disconnect()
            if self.sct:
                self.sct.close()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a monitor and send per-pixel updates to ESP32"
    )
    parser.add_argument("--ip", type=str, default=DEFAULT_IP, help="ESP32 IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default 8090)")
    parser.add_argument(
        "--monitor-index",
        type=int,
        default=None,
        help="Monitor index as reported by mss (1-based). Default: leftmost monitor",
    )
    parser.add_argument(
        "--prefer-largest",
        action="store_true",
        help="Pick the largest-resolution monitor instead of the leftmost",
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        default=15.0,
        help="Max capture/send rate (frames per second)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Per-channel diff threshold (0-255) to consider a pixel changed",
    )
    parser.add_argument(
        "--full-frame",
        action="store_true",
        help="Send every pixel of every frame (no diffing)",
    )
    parser.add_argument(
        "--max-updates-per-frame",
        type=int,
        default=3000,
        help="Cap updates per sent frame slice (default 3000)",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        choices=[0, 90, 180, 270],
        default=0,
        help="Rotate capture before scaling to match device orientation",
    )
    parser.add_argument(
        "--show-cursor",
        action="store_true",
        help="Draw the cursor location onto the captured frame (requires Quartz/pyobjc on macOS)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    sender = ScreenshotPixelSender(
        ip=args.ip,
        port=args.port,
        monitor_index=args.monitor_index,
        prefer_largest=args.prefer_largest,
        target_fps=args.target_fps,
        threshold=args.threshold,
        full_frame=args.full_frame,
        max_updates_per_frame=args.max_updates_per_frame,
        rotate_deg=args.rotate,
        show_cursor=args.show_cursor,
    )
    sender.run()


if __name__ == "__main__":
    main()

