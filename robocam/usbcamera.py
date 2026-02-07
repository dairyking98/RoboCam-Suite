"""
USB Camera Module - OpenCV/V4L2 Monochrome USB Cameras (e.g. Mars 662M).

On Linux (e.g. Raspberry Pi), uses CAP_V4L2 so /dev/video0, /dev/video1, etc.
are opened correctly.

Wrapper for monochrome USB cameras via OpenCV (cv2.VideoCapture). Mars 662M
USB3.0 is a monochrome camera; all capture is grayscale only. Supported
resolutions and FPS from published specs:
- 1936×1100: 76.5 FPS (12-bit) / 108 FPS (10-bit)
- 1920×1080: 78 FPS / 110 FPS
- 1280×720:  114 FPS / 162 FPS

Author: RoboCam-Suite
"""

import sys
import time
from typing import Optional, Tuple
import numpy as np
import cv2
from robocam.logging_config import get_logger

logger = get_logger(__name__)

# Mars 662M (and similar monochrome) supported resolutions; driver may support others
USB_CAMERA_SUPPORTED_RESOLUTIONS = [
    (1936, 1100),
    (1920, 1080),
    (1280, 720),
]


def _ensure_grayscale(frame: np.ndarray) -> np.ndarray:
    """Return frame as 2D grayscale (Mars 662M is monochrome; driver may sometimes give 3-channel)."""
    if frame is None:
        return frame
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] >= 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame[:, :, 0] if frame.ndim == 3 else frame


class USBCamera:
    """
    Simplified interface for monochrome USB cameras using OpenCV (V4L2).

    Mars 662M is monochrome; all frames are grayscale. Uses the first USB
    camera (index 0).

    Attributes:
        preset_resolution (Tuple[int, int]): Default resolution (width, height)
        cap: OpenCV VideoCapture instance
        _writer: VideoWriter for recording (when active)
        _recording_path: Path for current recording
    """

    def __init__(
        self,
        resolution: Tuple[int, int] = (1920, 1080),
        fps: float = 30.0,
        camera_index: int = 0,
    ) -> None:
        """
        Initialize USB camera (monochrome only).

        Args:
            resolution: (width, height). Use one of USB_CAMERA_SUPPORTED_RESOLUTIONS for best results.
            fps: Requested FPS (camera may cap to supported rate).
            camera_index: OpenCV camera index (0 = first camera).
        """
        self.preset_resolution: Tuple[int, int] = resolution
        self.fps: float = fps
        self.camera_index: int = camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self._writer: Optional[cv2.VideoWriter] = None
        self._recording_path: Optional[str] = None
        self._open()

    def _open(self) -> None:
        """Open camera and set resolution/FPS. Uses V4L2 on Linux for reliable USB access."""
        if sys.platform == "linux":
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        else:
            self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError("Failed to open USB camera (index %d)" % self.camera_index)
        w, h = self.preset_resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Read back actual values
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        logger.info("USB camera opened: %dx%d @ %.1f FPS (requested %dx%d @ %.1f)",
                    actual_w, actual_h, actual_fps, w, h, self.fps)

    def start(self) -> None:
        """Start the camera (already running after _open)."""
        if self.cap is not None and not self.cap.isOpened():
            self._open()

    def set_resolution(self, width: int, height: int) -> None:
        """Set resolution. May require reopening the device."""
        self.preset_resolution = (width, height)
        if self.cap is not None:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def take_photo_and_save(self, file_path: Optional[str] = None) -> None:
        """Capture a still grayscale image and save to file."""
        if file_path is None:
            file_path = f"{time.strftime('%Y%m%d_%H%M%S')}.png"
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError("USB camera not open")
        ret, frame = self.cap.read()
        if not ret or frame is None:
            raise RuntimeError("Failed to read frame from USB camera")
        frame = _ensure_grayscale(frame)
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "png"
        if ext in ("jpg", "jpeg"):
            cv2.imwrite(file_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        else:
            cv2.imwrite(file_path, frame)

    def capture_grayscale_frame(self) -> Optional[np.ndarray]:
        """Capture a single grayscale frame as numpy array (height, width)."""
        return self.read_frame()

    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read one grayscale frame (height, width). Monochrome camera only.
        Used by CaptureManager and preview.
        """
        if self.cap is None or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        return _ensure_grayscale(frame)

    def start_recording_video(self, video_path: Optional[str] = None, fps: Optional[float] = None) -> None:
        """Start recording grayscale video (OpenCV VideoWriter, monochrome)."""
        if video_path is None:
            video_path = f"{time.strftime('%Y%m%d_%H%M%S')}.avi"
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError("USB camera not open")
        if self._writer is not None:
            self.stop_recording_video()
        w, h = self.preset_resolution
        use_fps = fps if fps is not None else self.fps
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self._writer = cv2.VideoWriter(video_path, fourcc, use_fps, (w, h), False)  # grayscale only
        self._recording_path = video_path
        if not self._writer.isOpened():
            self._writer = None
            self._recording_path = None
            raise RuntimeError("Failed to open VideoWriter for %s" % video_path)
        logger.info("USB camera recording started: %s @ %.1f FPS", video_path, use_fps)

    def stop_recording_video(self) -> None:
        """Stop video recording and release writer."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            logger.info("USB camera recording stopped: %s", self._recording_path)
            self._recording_path = None

    def write_frame(self, frame: np.ndarray) -> bool:
        """Write a frame to the current recording. Returns True if written."""
        if self._writer is None:
            return False
        self._writer.write(frame)
        return True

    def release(self) -> None:
        """Release camera and any recording."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            self._recording_path = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        logger.info("USB camera released")
