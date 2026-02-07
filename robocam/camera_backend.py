"""
Camera Backend Detection - Pi HQ vs USB

Detects which camera is available: Raspberry Pi HQ (libcamera/Picamera2) or
USB camera (e.g. Mars 662M). Uses the first one found: tries Pi HQ first, then USB.
Tries USB at indices 0, 1, 2 (e.g. /dev/video0, /dev/video1) and uses V4L2 on Linux.

Author: RoboCam-Suite
"""

import sys
from typing import Optional, Literal, Tuple, Union
from robocam.logging_config import get_logger

logger = get_logger(__name__)

CameraBackend = Literal["pihq", "playerone", "usb"]

# Result: "pihq", ("playerone", index), ("usb", index), or None
DetectResult = Union[
    Literal["pihq"],
    Tuple[Literal["playerone"], int],
    Tuple[Literal["usb"], int],
    None,
]


def _open_usb_capture(index: int):
    """Open USB camera with index; use V4L2 on Linux for reliable detection."""
    import cv2
    if sys.platform == "linux":
        # Prefer V4L2 on Raspberry Pi / Linux so /dev/video* is used correctly
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(index)
    return cap


def detect_camera() -> DetectResult:
    """
    Detect which camera is available. Tries Pi HQ first, then Player One (SDK), then USB (OpenCV/V4L2).

    Returns:
        "pihq" if Raspberry Pi HQ camera is available,
        ("playerone", 0) if a Player One camera (e.g. Mars 662M) is available via SDK,
        ("usb", index) if a USB (V4L2) camera is available,
        None if no camera could be opened.
    """
    # Try Pi HQ (libcamera / Picamera2) first
    try:
        from picamera2 import Picamera2
        cam = Picamera2()
        config = cam.create_preview_configuration(main={"size": (640, 480)})
        cam.configure(config)
        cam.start()
        cam.stop()
        logger.info("Camera detected: Raspberry Pi HQ (Picamera2)")
        return "pihq"
    except Exception as e:
        logger.debug(f"Pi HQ camera not available: {e}")

    # Try Player One (Mars 662M etc.) via SDK
    try:
        from robocam.playerone_camera import get_playerone_camera_count
        count = get_playerone_camera_count()
        if count and count > 0:
            logger.info("Camera detected: Player One (SDK), count=%d", count)
            return ("playerone", 0)
    except Exception as e:
        logger.debug(f"Player One camera not available: {e}")

    # Try USB camera at indices 0..31 (on Pi, devices can be e.g. /dev/video10-31)
    for index in range(32):
        try:
            cap = _open_usb_capture(index)
            if cap.isOpened():
                ret, _ = cap.read()
                cap.release()
                if ret:
                    logger.info("Camera detected: USB camera (OpenCV) at index %d (/dev/video%d)", index, index)
                    return ("usb", index)
        except Exception as e:
            logger.debug(f"USB camera index %d not available: %s", index, e)

    logger.warning("No camera detected (neither Pi HQ nor USB)")
    return None
