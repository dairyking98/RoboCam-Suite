"""
Camera Backend Detection - Pi HQ vs Player One

Detects which camera is available: Raspberry Pi HQ (libcamera/Picamera2) or
Player One (e.g. Mars 662M via SDK). Uses the first one found: tries Pi HQ first, then Player One.

Author: RoboCam-Suite
"""

from typing import Any, Optional, Literal, Tuple, Union
from robocam.logging_config import get_logger

logger = get_logger(__name__)

CameraBackend = Literal["pihq", "playerone"]

# Result: Picamera2 instance (Pi HQ), ("playerone", index), or None
# NOTE: For Pi HQ we return the camera instance to avoid creating a second one,
# which would fail with "Camera in Configured state trying acquire() requiring state Available"
# because libcamera does not release the camera immediately after stop().
DetectResult = Union[Any, Tuple[Literal["playerone"], int], None]


def detect_camera() -> DetectResult:
    """
    Detect which camera is available. Tries Pi HQ first, then Player One (SDK).

    Returns:
        Picamera2 instance if Raspberry Pi HQ camera is available (stopped, ready to reconfigure),
        ("playerone", 0) if a Player One camera (e.g. Mars 662M) is available via SDK,
        None if no camera could be opened.

    For Pi HQ, returns the actual camera instance to avoid creating a second one
    (which fails when the first instance hasn't fully released the camera).
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
        return cam  # Return instance to reuse; avoid second Picamera2() causing state error
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

    logger.warning("No camera detected (neither Pi HQ nor Player One)")
    return None
