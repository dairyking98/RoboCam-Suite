"""
Picamera2 High-FPS Capture Module - High-FPS Grayscale Capture

Fast grayscale capture using Picamera2 with YUV420 format.
Allows grayscale video capture at very high frame rates (100+ FPS) using modern libcamera stack.

This is the recommended approach for Raspberry Pi OS (Bullseye/Bookworm) using libcamera.
Replaces the legacy raspividyuv command-line tool.

Based on: https://gist.github.com/CarlosGS/b8462a8a1cb69f55d8356cbb0f3a4d63

Author: RoboCam-Suite
"""

import numpy as np
import cv2
import atexit
import time
import os
from typing import Optional, List
from picamera2 import Picamera2
from robocam.logging_config import get_logger

logger = get_logger(__name__)


class Picamera2HighFpsCapture:
    """
    High-FPS grayscale capture using Picamera2 with YUV420 format.
    
    Provides direct access to raw YUV420 frames, extracting Y (luminance) channel for grayscale.
    Supports saving frames as individual PNG files or encoding to video.
    
    Attributes:
        width (int): Frame width in pixels
        height (int): Frame height in pixels
        fps (int): Target frames per second
        picam2 (Optional[Picamera2]): Picamera2 instance
        frames (List[np.ndarray]): Buffer for captured frames
        _recording (bool): Whether currently recording frames
    """
    
    def __init__(self, width: int = 640, height: int = 480, fps: int = 250, picam2: Optional[Picamera2] = None) -> None:
        """
        Initialize Picamera2 high-FPS capture.
        
        Args:
            width: Frame width in pixels (should be multiple of 32 for optimal performance)
            height: Frame height in pixels (should be multiple of 16 for optimal performance)
            fps: Target frames per second
            picam2: Optional existing Picamera2 instance to reuse (will be stopped and reconfigured)
        """
        self.width: int = width
        self.height: int = height
        self.fps: int = fps
        self.picam2: Optional[Picamera2] = picam2  # Use provided instance or create new one
        self._picam2_provided: bool = picam2 is not None  # Track if we need to clean up on stop
        self.frames: List[np.ndarray] = []
        self._recording: bool = False
        self.last_error: Optional[str] = None
        
    def start_capture(self) -> bool:
        """
        Start capturing frames from camera.
        
        Returns:
            True if capture started successfully, False otherwise
        """
        self.last_error = None
        try:
            # Always stop existing camera if it's running (critical for proper transitions)
            if self.picam2 is not None:
                try:
                    # Clear any callbacks that might interfere with new configuration
                    if hasattr(self.picam2, 'post_callback'):
                        self.picam2.post_callback = None
                    if hasattr(self.picam2, 'pre_callback'):
                        self.picam2.pre_callback = None
                    
                    # Always stop the camera instance - this is required before reconfiguring
                    if hasattr(self.picam2, 'started') and self.picam2.started:
                        self.picam2.stop()
                        logger.info("Stopped existing Picamera2 instance before reconfiguring")
                    
                    # If allocator is missing (older picamera2 builds), recreate instance
                    if not hasattr(self.picam2, "allocator"):
                        self.picam2 = Picamera2()
                        self._picam2_provided = False
                        logger.info("Recreated Picamera2 instance because allocator was missing")
                    
                    # Wait for camera to fully stop and release hardware
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Error stopping existing Picamera2 instance: {e}")
            else:
                # Create new Picamera2 instance if none was provided
                self.picam2 = Picamera2()
                self._picam2_provided = False
                logger.info("Created new Picamera2 instance for high-FPS capture")
            
            # Create video configuration with single-plane Y format for fastest readout.
            # Fallback to YUV420 if Y is unsupported on this platform.
            try:
                config = self.picam2.create_video_configuration(
                    main={"format": "Y", "size": (self.width, self.height)},
                    controls={"FrameRate": self.fps},
                    buffer_count=2  # Optimize buffer for high FPS
                )
                selected_format = "Y"
            except Exception as e:
                logger.warning(f"Y format not available, falling back to YUV420: {e}")
                config = self.picam2.create_video_configuration(
                    main={"format": "YUV420", "size": (self.width, self.height)},
                    controls={"FrameRate": self.fps},
                    buffer_count=2
                )
                selected_format = "YUV420"
            self._selected_format = selected_format
            
            # Always configure before starting - this initializes the allocator properly
            self.picam2.configure(config)
            logger.info(f"Configured Picamera2: {self.width}x{self.height} @ {self.fps} FPS ({selected_format})")
            
            # Brief pause after configure to ensure allocator is ready
            time.sleep(0.2)
            
            # Start the camera - this activates the allocator
            self.picam2.start()
            logger.info("Started Picamera2 for high-FPS capture")
            
            # Wait for camera to be ready
            time.sleep(0.2)
            
            # Register cleanup on exit
            atexit.register(self.stop_capture)
            
            # Wait for first frame and discard it (warmup)
            try:
                # Capture a frame to warm up
                with self.picam2.capture_request() as request:
                    _ = request.make_array("main")
            except Exception as e:
                logger.error(f"Error during warmup: {e}")
                self.last_error = str(e)
                self.stop_capture()
                return False
            
            logger.info(f"Picamera2 high-FPS capture started: {self.width}x{self.height} @ {self.fps} FPS")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Picamera2 capture: {e}")
            self.last_error = str(e)
            self.stop_capture()
            return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read a single frame from the camera stream.
        
        Returns:
            Grayscale frame as numpy array (height, width), or None if error
        """
        if self.picam2 is None:
            logger.error("Capture not started")
            return None
        
        try:
            # Use single-plane Y format; this avoids copying chroma planes for maximum throughput
            with self.picam2.capture_request() as request:
                frame = request.make_array("main")
            
            if frame is None:
                logger.warning("Received empty frame")
                return None
            
            # Expect a 2D array shaped (h, w) for Y format
            if frame.ndim == 2 and frame.shape[0] == self.height and frame.shape[1] == self.width:
                return frame
            
            # Fallback: handle YUV layouts if a different format slips through
            if frame.ndim == 2 and frame.shape[0] == self.height * 3 // 2:
                return frame[:self.height, :self.width].copy()
            if frame.ndim == 3:
                return frame[:, :, 0].copy()
            
            logger.warning(f"Unexpected frame shape: {frame.shape}")
            return None
                
        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            return None
    
    def capture_frame_sequence(self, num_frames: int, 
                               save_individual: bool = False,
                               output_dir: Optional[str] = None) -> List[np.ndarray]:
        """
        Capture a sequence of frames.
        
        Args:
            num_frames: Number of frames to capture
            save_individual: If True, save each frame as PNG file
            output_dir: Directory to save individual frames (if save_individual is True)
            
        Returns:
            List of captured frames as numpy arrays
        """
        frames = []
        start_time = time.time()
        
        for i in range(num_frames):
            frame = self.read_frame()
            if frame is None:
                logger.warning(f"Failed to capture frame {i+1}/{num_frames}")
                continue
            
            frames.append(frame.copy())
            
            # Save individual frame if requested
            if save_individual and output_dir:
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                frame_path = os.path.join(output_dir, f"frame_{i:06d}_{timestamp}.png")
                cv2.imwrite(frame_path, frame)
        
        elapsed = time.time() - start_time
        if elapsed > 0:
            actual_fps = len(frames) / elapsed
            logger.info(f"Captured {len(frames)} frames in {elapsed:.2f}s ({actual_fps:.1f} FPS)")
        
        return frames
    
    def start_recording(self) -> None:
        """Start recording frames to buffer."""
        self.frames = []
        self._recording = True
        logger.info("Started recording frames")
    
    def stop_recording(self) -> None:
        """Stop recording frames."""
        self._recording = False
        logger.info(f"Stopped recording. Captured {len(self.frames)} frames")
    
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording
    
    def save_frames_to_video(self, output_path: str, 
                            fps: Optional[float] = None,
                            codec: str = "FFV1") -> bool:
        """
        Save captured frames to video file with minimal compression.
        
        Args:
            output_path: Path to save video file
            fps: Frames per second for video (uses capture FPS if None)
            codec: Video codec to use ("FFV1" for lossless, "PNG" for PNG codec)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.frames:
            logger.error("No frames to save")
            return False
        
        if fps is None:
            fps = float(self.fps)
        
        # Determine codec
        if codec == "FFV1":
            # FFV1 lossless codec (requires OpenCV with FFV1 support)
            fourcc = cv2.VideoWriter_fourcc(*'FFV1')
            ext = ".avi"
        elif codec == "PNG":
            # PNG codec (lossless, but very large files)
            fourcc = cv2.VideoWriter_fourcc(*'PNG ')
            ext = ".avi"
        else:
            logger.warning(f"Unknown codec {codec}, using FFV1")
            fourcc = cv2.VideoWriter_fourcc(*'FFV1')
            ext = ".avi"
        
        # Ensure output path has correct extension
        if not output_path.endswith(ext):
            base_path = os.path.splitext(output_path)[0]
            output_path = base_path + ext
        
        # Convert grayscale frames to BGR for video codec
        # Most codecs require 3-channel images
        height, width = self.frames[0].shape
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height), isColor=True)
        
        if not out.isOpened():
            logger.error(f"Failed to open video writer for {output_path}")
            return False
        
        logger.info(f"Saving {len(self.frames)} frames to {output_path} using {codec} codec @ {fps} FPS")
        
        for i, frame in enumerate(self.frames):
            # Convert grayscale to BGR (3-channel)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            out.write(frame_bgr)
            
            if (i + 1) % 100 == 0:
                logger.debug(f"Saved {i+1}/{len(self.frames)} frames")
        
        out.release()
        logger.info(f"Successfully saved video: {output_path}")
        return True
    
    def save_frames_to_png_sequence(self, output_dir: str, prefix: str = "frame") -> bool:
        """
        Save captured frames as individual PNG files.
        
        Args:
            output_dir: Directory to save PNG files
            prefix: Filename prefix for frames
            
        Returns:
            True if successful, False otherwise
        """
        if not self.frames:
            logger.error("No frames to save")
            return False
        
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Saving {len(self.frames)} frames as PNG sequence to {output_dir}")
        
        for i, frame in enumerate(self.frames):
            frame_path = os.path.join(output_dir, f"{prefix}_{i:06d}.png")
            cv2.imwrite(frame_path, frame)
            
            if (i + 1) % 100 == 0:
                logger.debug(f"Saved {i+1}/{len(self.frames)} frames")
        
        logger.info(f"Successfully saved {len(self.frames)} PNG frames to {output_dir}")
        return True
    
    def stop_capture(self) -> None:
        """Stop capturing and clean up Picamera2 instance."""
        if self.picam2 is not None:
            try:
                if hasattr(self.picam2, 'started') and self.picam2.started:
                    self.picam2.stop()
            except Exception as e:
                logger.warning(f"Error stopping Picamera2: {e}")
            finally:
                # Only set to None if we created it (not if it was provided)
                if not self._picam2_provided:
                    self.picam2 = None
                self._recording = False
                logger.info("Picamera2 high-FPS capture stopped")

