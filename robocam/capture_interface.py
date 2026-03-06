"""
Unified Capture Interface - Multi-Capture Type Manager

Provides a unified interface for three capture types:
- Picamera2 (Color)
- Picamera2 (Grayscale)
- Player One (Grayscale) - Mars 662M etc. via Player One SDK

All video recording uses frame capture + encode (no V4L2 H.264 encoder required).

Author: RoboCam-Suite
"""

import os
import time
import threading
import cv2
import numpy as np
from typing import Optional, Tuple, List
from picamera2 import Picamera2
from robocam.pihqcamera import PiHQCamera
from robocam.playerone_camera import PlayerOneCamera
from robocam.logging_config import get_logger

logger = get_logger(__name__)


class CaptureManager:
    """
    Unified interface for multiple capture types.

    Supports three capture modes:
    - "Picamera2 (Color)": Color capture using Picamera2
    - "Picamera2 (Grayscale)": Grayscale capture using Picamera2 with YUV420
    - "Player One (Grayscale)": Mars 662M etc. via Player One SDK

    Video recording is always frame-buffer + encode (FFV1/AVI), no V4L2 encoder.

    Attributes:
        capture_type (str): Current capture type
        resolution (Tuple[int, int]): Capture resolution (width, height)
        fps (float): Target frames per second
        picam2 (Optional[Picamera2]): Picamera2 instance (for Picamera2 modes)
        pihq_camera (Optional[PiHQCamera]): PiHQCamera wrapper (for Picamera2 when created here)
        _recording (bool): Whether currently recording video
        _recorded_frames (List): Buffer for recorded frames
    """

    CAPTURE_TYPES = [
        "Picamera2 (Color)",
        "Picamera2 (Grayscale)",
        "Player One (Grayscale)",  # Mars 662M etc. via SDK
    ]
    CAPTURE_TYPES_PLAYERONE = ["Player One (Grayscale)"]

    def __init__(self, capture_type: str = "Picamera2 (Color)",
                 resolution: Tuple[int, int] = (1920, 1080),
                 fps: float = 30.0,
                 picam2: Optional[Picamera2] = None,
                 playerone_camera: Optional[PlayerOneCamera] = None) -> None:
        """
        Initialize capture manager.

        Args:
            capture_type: Capture type from CAPTURE_TYPES
            resolution: Capture resolution (width, height)
            fps: Target frames per second
            picam2: Optional existing Picamera2 instance (for Pi HQ modes)
            playerone_camera: Optional PlayerOneCamera instance (for Player One modes)
        """
        if capture_type not in self.CAPTURE_TYPES:
            raise ValueError(f"Invalid capture type: {capture_type}. Must be one of {self.CAPTURE_TYPES}")

        self.capture_type: str = capture_type
        self.resolution: Tuple[int, int] = resolution
        self.fps: float = fps
        self.width, self.height = resolution

        self.picam2: Optional[Picamera2] = picam2
        self.pihq_camera: Optional[PiHQCamera] = None
        self.playerone_camera: Optional[PlayerOneCamera] = playerone_camera
        self._playerone_camera_owned: bool = False

        self._recording: bool = False
        self._recorded_frames: List[np.ndarray] = []  # Unused when streaming; kept for compatibility
        self._video_output_path: Optional[str] = None
        self._video_writer: Optional[cv2.VideoWriter] = None  # When set, we stream directly to file
        self._video_codec: str = "FFV1"
        self._frames_captured: int = 0  # Count of frames written during current recording
        self._picam2_video_configured: bool = False  # True when we reconfigured picam2 for video

        self._initialize_capture()

    def _get_picam2(self) -> Optional[Picamera2]:
        """Return the active Picamera2 instance (from pihq_camera or picam2)."""
        if self.picam2 is not None:
            return self.picam2
        if self.pihq_camera is not None:
            return self.pihq_camera.picam2
        return None

    def _initialize_capture(self) -> None:
        """Initialize the appropriate capture instance based on capture_type."""
        if "Player One" in self.capture_type:
            if self.playerone_camera is None:
                self.playerone_camera = PlayerOneCamera(
                    resolution=self.resolution,
                    fps=self.fps
                )
                self._playerone_camera_owned = True
            else:
                self.playerone_camera.preset_resolution = self.resolution
                self.playerone_camera.fps = self.fps
                self._playerone_camera_owned = False
            logger.info("Initialized Player One (Grayscale) capture")
        else:
            grayscale = "Grayscale" in self.capture_type
            if self.picam2 is None:
                self.pihq_camera = PiHQCamera(
                    resolution=self.resolution,
                    grayscale=grayscale
                )
                self.picam2 = self.pihq_camera.picam2
                self.pihq_camera.start()
                logger.info(f"Initialized {self.capture_type} capture")
            else:
                self.pihq_camera = None
                logger.info(f"Using existing Picamera2 instance for {self.capture_type} capture")

    def capture_image(self, output_path: Optional[str] = None) -> bool:
        """
        Capture a single image and save to file.

        Returns:
            True if successful, False otherwise
        """
        if output_path is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            output_path = f"capture_{timestamp}.png"

        try:
            ext = os.path.splitext(output_path)[1].lower()
            is_jpeg = ext in ['.jpg', '.jpeg']

            if self.playerone_camera is not None:
                frame = self.playerone_camera.read_frame()
                if frame is None:
                    logger.error("Failed to read frame from Player One camera")
                    return False
                if is_jpeg:
                    cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                else:
                    cv2.imwrite(output_path, frame)
                logger.info(f"Saved image: {output_path}")
                return True

            picam2 = self._get_picam2()
            if picam2 is not None:
                if self.pihq_camera is not None:
                    self.pihq_camera.take_photo_and_save(output_path)
                else:
                    picam2.capture_file(output_path)
                logger.info(f"Saved image: {output_path}")
                return True

            logger.error("No camera initialized")
            return False
        except Exception as e:
            logger.error(f"Error capturing image: {e}")
            return False

    def _create_video_writer(self, path: str, codec: str) -> bool:
        """Create and open VideoWriter for streaming. Returns True on success."""
        w, h = self.width, self.height
        grayscale = "Grayscale" in self.capture_type
        is_color = not grayscale
        fourcc = cv2.VideoWriter_fourcc(*("FFV1" if codec == "FFV1" else "MJPG"))
        writer = cv2.VideoWriter(path, fourcc, self.fps, (w, h), is_color)
        if not writer.isOpened():
            logger.error("Failed to open VideoWriter for streaming: %s", path)
            return False
        self._video_writer = writer
        self._video_codec = codec
        logger.info(f"Streaming video to {path} (codec={codec})")
        return True

    def start_video_recording(self, output_path: Optional[str] = None,
                             codec: str = "FFV1") -> bool:
        """
        Start recording video: stream directly to file (no buffer, no post-processing).
        No V4L2 encoder used.
        """
        if self._recording:
            logger.warning("Already recording")
            return False

        if output_path is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            output_path = f"video_{timestamp}.avi"

        self._video_output_path = output_path
        self._frames_captured = 0
        self._recording = True

        try:
            # Open file and create writer immediately so we stream as we capture
            if not self._create_video_writer(output_path, codec):
                self._recording = False
                return False

            if self.playerone_camera is not None:
                logger.info(f"Started Player One recording (streaming): {output_path}")
                return True

            picam2 = self._get_picam2()
            if picam2 is not None:
                grayscale = "Grayscale" in self.capture_type
                picam2.stop()
                if grayscale:
                    config = picam2.create_video_configuration(
                        main={"size": (self.width, self.height), "format": "YUV420"}
                    )
                else:
                    config = picam2.create_video_configuration(
                        main={"size": (self.width, self.height)}
                    )
                picam2.configure(config)
                picam2.start()
                self._picam2_video_configured = True
                logger.info(f"Started Picamera2 recording (streaming): {output_path}")
                return True

            logger.error("No camera initialized")
            self._recording = False
            self._video_writer = None
            return False
        except Exception as e:
            logger.error(f"Error starting video recording: {e}")
            self._recording = False
            self._video_writer = None
            return False

    def capture_frame_for_video(self) -> bool:
        """Capture one frame and write it directly to the open video file (streaming)."""
        if not self._recording or self._video_writer is None:
            return False

        frame = None
        if self.playerone_camera is not None:
            frame = self.playerone_camera.read_frame()
        else:
            picam2 = self._get_picam2()
            if picam2 is not None:
                try:
                    array = picam2.capture_array("main")
                    grayscale = "Grayscale" in self.capture_type
                    if grayscale and array.ndim == 3:
                        frame = array[:, :, 0]  # Y channel
                    elif grayscale:
                        frame = array
                    else:
                        if array.ndim == 3 and array.shape[2] >= 3:
                            frame = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
                        else:
                            frame = array
                except Exception as e:
                    logger.debug(f"Capture frame error: {e}")
                    return False

        if frame is not None:
            grayscale = "Grayscale" in self.capture_type
            if grayscale and frame.ndim == 2:
                self._video_writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
            else:
                self._video_writer.write(frame)
            self._frames_captured += 1
            return True
        return False

    def stop_video_recording(self, codec: str = "FFV1") -> Optional[str]:
        """Stop recording: close the file (already written by streaming). Returns output path or None."""
        if not self._recording:
            logger.warning("Not recording")
            return None

        self._recording = False
        path = self._video_output_path
        self._video_output_path = None

        try:
            if self._video_writer is not None:
                self._video_writer.release()
                self._video_writer = None
                logger.info(f"Stopped recording (streamed): {path} ({self._frames_captured} frames)")
            self._stop_picam2_after_recording()
            return path
        except Exception as e:
            logger.error(f"Error stopping video recording: {e}")
            self._stop_picam2_after_recording()
            return None

    def _stop_picam2_after_recording(self) -> None:
        """Stop Picamera2 after recording. Runs stop() with a timeout to avoid blocking indefinitely."""
        picam2 = self._get_picam2()
        if picam2 is None or not self._picam2_video_configured:
            return
        stop_done = threading.Event()
        stop_exc = []

        def do_stop() -> None:
            try:
                picam2.stop()
            except Exception as e:
                stop_exc.append(e)
            finally:
                stop_done.set()

        t = threading.Thread(target=do_stop, daemon=True)
        t.start()
        if not stop_done.wait(timeout=10.0):
            logger.warning("picam2.stop() did not complete within 10s; continuing anyway")
        if stop_exc:
            logger.warning("picam2.stop() raised: %s", stop_exc[0])
        self._picam2_video_configured = False

    def is_recording(self) -> bool:
        return self._recording

    def get_frames_captured(self) -> int:
        """Return the number of frames written in the last (or current) recording."""
        return self._frames_captured

    def get_capture_type(self) -> str:
        return self.capture_type

    def set_capture_type(self, capture_type: str) -> bool:
        if capture_type not in self.CAPTURE_TYPES:
            logger.error(f"Invalid capture type: {capture_type}")
            return False
        if capture_type == self.capture_type:
            return True
        self.cleanup()
        self.capture_type = capture_type
        try:
            self._initialize_capture()
            return True
        except Exception as e:
            logger.error(f"Failed to switch capture type: {e}")
            return False

    def set_resolution(self, width: int, height: int) -> bool:
        if self._recording:
            logger.error("Cannot change resolution while recording")
            return False
        self.resolution = (width, height)
        self.width, self.height = width, height
        self.cleanup()
        try:
            self._initialize_capture()
            return True
        except Exception as e:
            logger.error(f"Failed to set resolution: {e}")
            return False

    def set_fps(self, fps: float) -> None:
        self.fps = fps

    def cleanup(self) -> None:
        """Clean up capture resources."""
        if self._recording:
            self.stop_video_recording()
        if self._video_writer is not None:
            try:
                self._video_writer.release()
            except Exception:
                pass
            self._video_writer = None

        picam2 = self._get_picam2()
        if picam2 is not None:
            try:
                picam2.stop()
            except Exception:
                pass
        self._picam2_video_configured = False

        if self.pihq_camera is not None:
            try:
                self.pihq_camera.picam2.stop()
            except Exception:
                pass
            self.pihq_camera = None

        self.picam2 = None

        if self.playerone_camera is not None and getattr(self, "_playerone_camera_owned", True):
            try:
                self.playerone_camera.release()
            except Exception:
                pass
            self.playerone_camera = None

        self._recorded_frames = []
