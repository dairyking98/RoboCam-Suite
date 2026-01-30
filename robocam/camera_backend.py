"""
Camera Backend Detection - Pi HQ vs USB

Detects which camera is available: Raspberry Pi HQ (libcamera/Picamera2) or
USB camera (e.g. Mars 662M). Uses the first one found: tries Pi HQ first, then USB.
Only one camera is expected in the system at a time.

Author: RoboCam-Suite
"""

from typing import Optional, Literal
from robocam.logging_config import get_logger

logger = get_logger(__name__)

CameraBackend = Literal["pihq", "usb"]


def detect_camera() -> Optional[CameraBackend]:
    """
    Detect which camera is available. Tries Pi HQ (Picamera2) first, then USB (OpenCV).
    Uses the first one that opens successfully; only one camera is in the system at a time.

    Returns:
        "pihq" if Raspberry Pi HQ camera is available,
        "usb" if a USB camera (e.g. Mars 662M) is available,
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

    # Try USB camera (OpenCV / V4L2)
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            if ret:
                logger.info("Camera detected: USB camera (OpenCV)")
                return "usb"
    except Exception as e:
        logger.debug(f"USB camera not available: {e}")

    logger.warning("No camera detected (neither Pi HQ nor USB)")
    return None
