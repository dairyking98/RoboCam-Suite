"""
Unified Capture Interface - Multi-Capture Type Manager

Provides a unified interface for different capture types:
- Picamera2 (Color)
- Picamera2 (Grayscale)
- raspividyuv (Grayscale - High FPS)

Author: RoboCam-Suite
"""

import os
import time
import cv2
import numpy as np
from typing import Optional, Tuple, List
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, JpegEncoder
from picamera2.outputs import FileOutput
from robocam.pihqcamera import PiHQCamera
from robocam.raspividyuv_capture import RaspividyuvCapture
from robocam.logging_config import get_logger

logger = get_logger(__name__)


class CaptureManager:
    """
    Unified interface for multiple capture types.
    
    Supports three capture modes:
    - "Picamera2 (Color)": Standard color capture using Picamera2
    - "Picamera2 (Grayscale)": Grayscale capture using Picamera2 with YUV420
    - "raspividyuv (Grayscale - High FPS)": High-FPS grayscale using raspividyuv
    
    Attributes:
        capture_type (str): Current capture type
        resolution (Tuple[int, int]): Capture resolution (width, height)
        fps (float): Target frames per second
        picam2 (Optional[Picamera2]): Picamera2 instance (for Picamera2 modes)
        pihq_camera (Optional[PiHQCamera]): PiHQCamera wrapper (for Picamera2 modes)
        raspividyuv (Optional[RaspividyuvCapture]): Raspividyuv instance (for high-FPS mode)
        _recording (bool): Whether currently recording video
        _recorded_frames (List): Buffer for recorded frames (raspividyuv mode)
    """
    
    CAPTURE_TYPES = [
        "Picamera2 (Color)",
        "Picamera2 (Grayscale)",
        "raspividyuv (Grayscale - High FPS)"
    ]
    
    def __init__(self, capture_type: str = "Picamera2 (Color)",
                 resolution: Tuple[int, int] = (1920, 1080),
                 fps: float = 30.0) -> None:
        """
        Initialize capture manager.
        
        Args:
            capture_type: Capture type from CAPTURE_TYPES
            resolution: Capture resolution (width, height)
            fps: Target frames per second
        """
        if capture_type not in self.CAPTURE_TYPES:
            raise ValueError(f"Invalid capture type: {capture_type}. Must be one of {self.CAPTURE_TYPES}")
        
        self.capture_type: str = capture_type
        self.resolution: Tuple[int, int] = resolution
        self.fps: float = fps
        self.width, self.height = resolution
        
        # Initialize capture instances based on type
        self.picam2: Optional[Picamera2] = None
        self.pihq_camera: Optional[PiHQCamera] = None
        self.raspividyuv: Optional[RaspividyuvCapture] = None
        
        self._recording: bool = False
        self._recorded_frames: List[np.ndarray] = []
        self._video_output_path: Optional[str] = None
        
        # Initialize based on capture type
        self._initialize_capture()
    
    def _initialize_capture(self) -> None:
        """Initialize the appropriate capture instance based on capture_type."""
        if "raspividyuv" in self.capture_type:
            # High-FPS grayscale mode
            self.raspividyuv = RaspividyuvCapture(
                width=self.width,
                height=self.height,
                fps=int(self.fps)
            )
            if not self.raspividyuv.start_capture():
                logger.error("Failed to start raspividyuv capture")
                raise RuntimeError("raspividyuv capture failed to start")
        else:
            # Picamera2 modes (Color or Grayscale)
            grayscale = "Grayscale" in self.capture_type
            self.picam2 = Picamera2()
            self.pihq_camera = PiHQCamera(
                resolution=self.resolution,
                grayscale=grayscale
            )
            self.pihq_camera.start()
            logger.info(f"Initialized {self.capture_type} capture")
    
    def capture_image(self, output_path: Optional[str] = None) -> bool:
        """
        Capture a single image and save to file.
        
        Args:
            output_path: Path to save image. If None, generates timestamped filename.
            
        Returns:
            True if successful, False otherwise
        """
        if output_path is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            ext = ".png"
            output_path = f"capture_{timestamp}{ext}"
        
        try:
            if "raspividyuv" in self.capture_type:
                # Capture single frame from raspividyuv
                frame = self.raspividyuv.read_frame()
                if frame is None:
                    logger.error("Failed to read frame from raspividyuv")
                    return False
                cv2.imwrite(output_path, frame)
                logger.info(f"Saved image: {output_path}")
                return True
            else:
                # Use Picamera2
                if self.pihq_camera is None:
                    logger.error("Picamera2 not initialized")
                    return False
                self.pihq_camera.take_photo_and_save(output_path)
                logger.info(f"Saved image: {output_path}")
                return True
        except Exception as e:
            logger.error(f"Error capturing image: {e}")
            return False
    
    def start_video_recording(self, output_path: Optional[str] = None,
                            codec: str = "FFV1") -> bool:
        """
        Start recording video.
        
        Args:
            output_path: Path to save video. If None, generates timestamped filename.
            codec: Video codec ("FFV1" for lossless, "MJPG" for high-quality MJPEG, "PNG" for PNG codec)
            
        Returns:
            True if successful, False otherwise
        """
        if self._recording:
            logger.warning("Already recording")
            return False
        
        if output_path is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            if codec == "FFV1" or codec == "PNG":
                ext = ".avi"
            elif codec == "MJPG":
                ext = ".avi"
            else:
                ext = ".h264"
            output_path = f"video_{timestamp}{ext}"
        
        self._video_output_path = output_path
        self._recording = True
        
        try:
            if "raspividyuv" in self.capture_type:
                # Start frame buffering
                self._recorded_frames = []
                self.raspividyuv.start_recording()
                logger.info(f"Started raspividyuv recording: {output_path}")
                return True
            else:
                # Use Picamera2
                if self.pihq_camera is None:
                    logger.error("Picamera2 not initialized")
                    return False
                
                # For Picamera2, we'll use H264Encoder or JpegEncoder
                # Note: For minimal compression, we might need to save frames and encode later
                # For now, use standard Picamera2 recording
                self.pihq_camera.start_recording_video(output_path, fps=self.fps)
                logger.info(f"Started Picamera2 recording: {output_path}")
                return True
        except Exception as e:
            logger.error(f"Error starting video recording: {e}")
            self._recording = False
            return False
    
    def capture_frame_for_video(self) -> bool:
        """
        Capture a frame during video recording (for raspividyuv mode).
        
        Returns:
            True if frame captured successfully, False otherwise
        """
        if not self._recording:
            return False
        
        if "raspividyuv" in self.capture_type:
            frame = self.raspividyuv.read_frame()
            if frame is not None:
                self._recorded_frames.append(frame.copy())
                return True
            return False
        # For Picamera2, frames are automatically recorded
        return True
    
    def stop_video_recording(self, codec: str = "FFV1") -> Optional[str]:
        """
        Stop video recording and save file.
        
        Args:
            codec: Video codec for encoding (for raspividyuv mode)
            
        Returns:
            Path to saved video file, or None if error
        """
        if not self._recording:
            logger.warning("Not recording")
            return None
        
        self._recording = False
        
        try:
            if "raspividyuv" in self.capture_type:
                # Stop recording and encode frames to video
                self.raspividyuv.stop_recording()
                
                if not self._recorded_frames:
                    logger.warning("No frames recorded")
                    return None
                
                # Save frames to video
                success = self.raspividyuv.save_frames_to_video(
                    self._video_output_path,
                    fps=self.fps,
                    codec=codec
                )
                
                if success:
                    logger.info(f"Saved video: {self._video_output_path}")
                    return self._video_output_path
                else:
                    logger.error("Failed to save video")
                    return None
            else:
                # Stop Picamera2 recording
                if self.pihq_camera is None:
                    logger.error("Picamera2 not initialized")
                    return None
                self.pihq_camera.stop_recording_video()
                logger.info(f"Stopped recording: {self._video_output_path}")
                return self._video_output_path
        except Exception as e:
            logger.error(f"Error stopping video recording: {e}")
            return None
    
    def is_recording(self) -> bool:
        """Check if currently recording video."""
        return self._recording
    
    def get_capture_type(self) -> str:
        """Get current capture type."""
        return self.capture_type
    
    def set_capture_type(self, capture_type: str) -> bool:
        """
        Change capture type (requires reinitialization).
        
        Args:
            capture_type: New capture type from CAPTURE_TYPES
            
        Returns:
            True if successful, False otherwise
        """
        if capture_type not in self.CAPTURE_TYPES:
            logger.error(f"Invalid capture type: {capture_type}")
            return False
        
        if capture_type == self.capture_type:
            return True  # Already set
        
        # Stop current capture
        self.cleanup()
        
        # Set new type
        self.capture_type = capture_type
        
        # Reinitialize
        try:
            self._initialize_capture()
            return True
        except Exception as e:
            logger.error(f"Failed to switch capture type: {e}")
            return False
    
    def set_resolution(self, width: int, height: int) -> bool:
        """
        Set capture resolution (requires reinitialization).
        
        Args:
            width: Frame width
            height: Frame height
            
        Returns:
            True if successful, False otherwise
        """
        if self._recording:
            logger.error("Cannot change resolution while recording")
            return False
        
        self.resolution = (width, height)
        self.width = width
        self.height = height
        
        # Reinitialize
        self.cleanup()
        try:
            self._initialize_capture()
            return True
        except Exception as e:
            logger.error(f"Failed to set resolution: {e}")
            return False
    
    def set_fps(self, fps: float) -> None:
        """
        Set target frames per second.
        
        Args:
            fps: Target FPS
        """
        self.fps = fps
        # Note: For raspividyuv, FPS is set at initialization
        # For Picamera2, FPS can be set in video configuration
    
    def cleanup(self) -> None:
        """Clean up capture resources."""
        if self._recording:
            self.stop_video_recording()
        
        if self.raspividyuv is not None:
            self.raspividyuv.stop_capture()
            self.raspividyuv = None
        
        if self.pihq_camera is not None:
            try:
                self.pihq_camera.picam2.stop()
            except:
                pass
            self.pihq_camera = None
        
        if self.picam2 is not None:
            try:
                self.picam2.stop()
            except:
                pass
            self.picam2 = None
        
        self._recorded_frames = []

