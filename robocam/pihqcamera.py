"""
PiHQ Camera Module

Wrapper for Picamera2 providing simplified interface for still and video capture.
Designed for Raspberry Pi Camera Module.

Author: RoboCam-Suite
"""

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
import time
from typing import Optional, Tuple


class PiHQCamera:
    """
    Simplified interface for Raspberry Pi Camera Module using Picamera2.
    
    Provides methods for capturing still images and recording video with
    configurable resolution, exposure, and gain settings.
    
    Attributes:
        preset_resolution (Tuple[int, int]): Default resolution (width, height)
        picam2 (Picamera2): Picamera2 instance
        config: Current camera configuration
    """
    
    def __init__(self, resolution: Tuple[int, int] = (1920, 1080), 
                 exposure: int = 0, gain: int = 0, 
                 red_gain: int = 0, blue_gain: int = 0) -> None:
        """
        Initialize camera with specified settings.
        
        Args:
            resolution: Camera resolution as (width, height) tuple. Default: (1920, 1080)
            exposure: Exposure time (currently not applied - see note)
            gain: Analogue gain (currently not applied - see note)
            red_gain: Red color gain (currently not applied - see note)
            blue_gain: Blue color gain (currently not applied - see note)
            
        Note:
            Exposure and gain controls are commented out as they may not work
            correctly with current Picamera2 version. Use set_exposure() and
            set_gain() methods after initialization if needed.
        """
        self.preset_resolution: Tuple[int, int] = resolution
        self.picam2 = Picamera2()
        self.config = self.picam2.create_still_configuration(main={"size": resolution})
        self.picam2.configure(self.config)
        #self.picam2.set_controls({"ExposureTime": exposure, "AnalogueGain": gain}) #, "RedGain": red_gain, "BlueGain": blue_gain}) # those aren't working right now
        
    def start(self) -> None:
        """Start the camera."""
        self.picam2.start()

    def set_resolution(self, width: int, height: int) -> None:
        """
        Set camera resolution.
        
        Args:
            width: Image width in pixels
            height: Image height in pixels
        """
        self.config = self.picam2.create_still_configuration(main={"size": (width, height)})
        self.picam2.configure(self.config)

    def set_exposure(self, exposure: int) -> None:
        """
        Set camera exposure time.
        
        Args:
            exposure: Exposure time value
        """
        self.picam2.set_controls({"ExposureTime": exposure})

    def set_gain(self, gain: int) -> None:
        """
        Set camera analogue gain.
        
        Args:
            gain: Analogue gain value
        """
        self.picam2.set_controls({"AnalogueGain": gain})
    
    def set_color_gains(self, red_gain: float = 1.0, blue_gain: float = 1.0) -> None:
        """
        Set color gains for white balance adjustment.
        
        Args:
            red_gain: Red color gain multiplier (default: 1.0)
            blue_gain: Blue color gain multiplier (default: 1.0)
        """
        self.picam2.set_controls({"ColourGains": (red_gain, blue_gain)})

    def take_photo_and_save(self, file_path: Optional[str] = None) -> None:
        """
        Capture a still image and save to file.
        
        Args:
            file_path: Path to save image. If None, generates timestamped filename.
            
        Note:
            Stops camera, reconfigures for still capture, captures image, then restarts.
            Debug print statements ("a", "b", "c", "d") should be removed in production.
        """
        self.picam2.stop()
        self.config = self.picam2.create_still_configuration(main={"size": self.preset_resolution})
        print("a")
        self.picam2.configure(self.config)
        print("b")
        if file_path is None:
            file_path = f"{time.strftime('%Y%m%d_%H%M%S')}.png"
        print("c")
        self.picam2.start()
        # self.picam2.switch_mode_and_capture_file(self.config, file_path)
        self.picam2.capture_file(file_path)
        print("d")

    def start_recording_video(self, video_path: Optional[str] = None) -> None:
        """
        Start recording video.
        
        Args:
            video_path: Path to save video. If None, generates timestamped filename.
            
        Note:
            Stops camera, reconfigures for video capture, then starts recording.
            Uses H264 encoding.
        """
        self.picam2.stop()
        config = self.picam2.create_video_configuration(main={"size": self.preset_resolution})
        self.picam2.configure(config)
        if video_path is None:
            video_path = f"{time.strftime('%Y%m%d_%H%M%S')}.h264"
        encoder = H264Encoder()
        output = FileOutput(video_path)
        self.picam2.start_recording(encoder, output)

    def stop_recording_video(self) -> None:
        """Stop video recording."""
        self.picam2.stop_recording()
