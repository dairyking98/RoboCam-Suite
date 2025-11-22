"""
Raspividyuv Capture Module - High-FPS Grayscale Capture

Fast reading from Raspberry Pi camera using raspividyuv command-line tool.
Allows grayscale video capture at very high frame rates (100+ FPS).

Based on: https://gist.github.com/CarlosGS/b8462a8a1cb69f55d8356cbb0f3a4d63

Author: RoboCam-Suite
"""

import subprocess as sp
import numpy as np
import cv2
import atexit
import time
import os
from typing import Optional, Tuple, List
from robocam.logging_config import get_logger

logger = get_logger(__name__)


class RaspividyuvCapture:
    """
    High-FPS grayscale capture using raspividyuv command-line tool.
    
    Provides direct access to raw YUV frames for maximum performance.
    Supports saving frames as individual PNG files or encoding to video.
    
    Attributes:
        width (int): Frame width in pixels
        height (int): Frame height in pixels
        fps (int): Target frames per second
        bytes_per_frame (int): Number of bytes per frame (width * height for grayscale)
        process (Optional[sp.Popen]): Subprocess running raspividyuv
        frames (List[np.ndarray]): Buffer for captured frames
    """
    
    def __init__(self, width: int = 640, height: int = 480, fps: int = 250) -> None:
        """
        Initialize raspividyuv capture.
        
        Args:
            width: Frame width in pixels
            height: Frame height in pixels
            fps: Target frames per second (250 requests maximum)
        """
        self.width: int = width
        self.height: int = height
        self.fps: int = fps
        self.bytes_per_frame: int = width * height
        self.process: Optional[sp.Popen] = None
        self.frames: List[np.ndarray] = []
        self._recording: bool = False
        
    def start_capture(self) -> bool:
        """
        Start capturing frames from camera.
        
        Returns:
            True if capture started successfully, False otherwise
        """
        if self.process is not None:
            logger.warning("Capture already started")
            return False
        
        # Check if raspividyuv is available
        try:
            sp.run(["raspividyuv", "--help"], 
                   stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=2)
        except (FileNotFoundError, sp.TimeoutExpired):
            logger.error("raspividyuv command not found. Please install Raspberry Pi camera tools.")
            return False
        
        # Build raspividyuv command
        # --luma discards chroma channels, only luminance is sent
        # --output - sends output to stdout
        # --timeout 0 specifies continuous video
        # --nopreview disables preview window
        video_cmd = [
            "raspividyuv",
            "-w", str(self.width),
            "-h", str(self.height),
            "--output", "-",
            "--timeout", "0",
            "--framerate", str(self.fps),
            "--luma",
            "--nopreview"
        ]
        
        try:
            # Start subprocess with unbuffered output
            self.process = sp.Popen(
                video_cmd,
                stdout=sp.PIPE,
                bufsize=1  # Line buffered
            )
            
            # Register cleanup on exit
            atexit.register(self.stop_capture)
            
            # Wait for first frame and discard it (warmup)
            try:
                raw_stream = self.process.stdout.read(self.bytes_per_frame)
                if len(raw_stream) != self.bytes_per_frame:
                    logger.error("Failed to read initial frame")
                    self.stop_capture()
                    return False
            except Exception as e:
                logger.error(f"Error reading initial frame: {e}")
                self.stop_capture()
                return False
            
            logger.info(f"Raspividyuv capture started: {self.width}x{self.height} @ {self.fps} FPS")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start raspividyuv: {e}")
            self.process = None
            return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read a single frame from the camera stream.
        
        Returns:
            Grayscale frame as numpy array (height, width), or None if error
        """
        if self.process is None:
            logger.error("Capture not started")
            return None
        
        try:
            # Flush any buffered frames to get latest
            self.process.stdout.flush()
            
            # Read raw bytes
            frame_bytes = self.process.stdout.read(self.bytes_per_frame)
            
            if len(frame_bytes) != self.bytes_per_frame:
                logger.warning(f"Read incomplete frame: {len(frame_bytes)}/{self.bytes_per_frame} bytes")
                return None
            
            # Convert to numpy array
            frame = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame = frame.reshape((self.height, self.width))
            
            return frame
            
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
        """Stop capturing and clean up subprocess."""
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except sp.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            except Exception as e:
                logger.warning(f"Error stopping process: {e}")
            finally:
                self.process = None
                self._recording = False
                logger.info("Raspividyuv capture stopped")

