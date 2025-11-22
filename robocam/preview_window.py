"""
Preview Window - Separate Window for Camera Preview and Capture Settings

Provides a separate tkinter window that displays live camera preview
and capture settings. The preview automatically uses the capture settings.

Author: RoboCam-Suite
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple
from datetime import datetime
import os
from robocam.tkinter_preview import TkinterPreviewWidget
from robocam.capture_interface import CaptureManager
from robocam.camera_preview import FPSTracker
from robocam.logging_config import get_logger

logger = get_logger(__name__)


class PreviewWindow:
    """
    Separate window for camera preview and capture settings.
    
    The preview automatically uses the capture settings (resolution, FPS, capture type).
    
    Attributes:
        window (tk.Toplevel): The preview window
        preview_canvas (tk.Canvas): Canvas for preview display
        preview_widget (Optional[TkinterPreviewWidget]): Preview widget instance
        capture_manager (Optional[CaptureManager]): Capture manager instance
        picam2: Picamera2 instance
        _recording (bool): Whether currently recording video
    """
    
    def __init__(
        self,
        parent: tk.Tk,
        picam2=None,
        capture_manager: Optional[CaptureManager] = None,
        initial_resolution: Tuple[int, int] = (800, 600),
        initial_fps: float = 30.0,
        simulate_cam: bool = False
    ):
        """
        Initialize preview window.
        
        Args:
            parent: Parent tkinter window
            picam2: Optional Picamera2 camera instance. If None, will be created automatically.
            capture_manager: Optional CaptureManager instance. If None, will be created automatically.
            initial_resolution: Initial preview resolution (width, height)
            initial_fps: Initial preview FPS
            simulate_cam: If True, run in camera simulation mode
        """
        self.parent = parent
        self._simulate_cam = simulate_cam
        
        # Create picam2 if not provided
        if picam2 is None and not simulate_cam:
            from picamera2 import Picamera2
            self.picam2 = Picamera2()
            self.picam2_config = self.picam2.create_preview_configuration(
                main={"size": initial_resolution},
                controls={"FrameRate": initial_fps},
                buffer_count=2
            )
            self.picam2.configure(self.picam2_config)
            try:
                self.picam2.start()
                logger.info("PreviewWindow: Created and started Picamera2 instance")
            except Exception as e:
                logger.error(f"PreviewWindow: Failed to start camera: {e}")
                self.picam2 = None
        else:
            self.picam2 = picam2
        
        # Create capture manager if not provided
        if capture_manager is None and not simulate_cam and self.picam2 is not None:
            try:
                self.capture_manager = CaptureManager(
                    capture_type="Picamera2 (Color)",
                    resolution=initial_resolution,
                    fps=initial_fps,
                    picam2=self.picam2  # Pass existing instance
                )
                logger.info("PreviewWindow: Created CaptureManager")
            except Exception as e:
                logger.warning(f"PreviewWindow: Failed to create capture manager: {e}")
                self.capture_manager = None
        else:
            self.capture_manager = capture_manager
        self.preview_widget: Optional[TkinterPreviewWidget] = None
        self._recording: bool = False
        self.fps_tracker: Optional[FPSTracker] = None
        self._running: bool = True
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Camera Preview & Capture Settings")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Create main frame
        main_frame = tk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left side: Preview
        preview_frame = tk.LabelFrame(main_frame, text="Camera Preview", padx=5, pady=5)
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=initial_resolution[0],
            height=initial_resolution[1],
            bg="black",
            highlightthickness=2,
            highlightbackground="gray"
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Recording indicator (red dot) - initially hidden
        self.recording_indicator = self.preview_canvas.create_oval(
            10, 10, 30, 30,  # Position: top-left corner
            fill="red",
            outline="white",
            width=2,
            state="hidden"  # Hidden by default
        )
        # Recording text
        self.recording_text = self.preview_canvas.create_text(
            35, 20,  # Position: next to the dot
            text="REC",
            fill="white",
            font=("Arial", 12, "bold"),
            anchor="w",
            state="hidden"
        )
        
        # Right side: Capture Settings
        settings_frame = tk.LabelFrame(main_frame, text="Capture Settings", padx=5, pady=5)
        settings_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Capture Type
        tk.Label(settings_frame, text="Capture Type:").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.capture_type_var = tk.StringVar(value="Picamera2 (Color)")
        if capture_manager:
            capture_type_menu = tk.OptionMenu(
                settings_frame,
                self.capture_type_var,
                *CaptureManager.CAPTURE_TYPES,
                command=self.on_capture_type_change
            )
        else:
            capture_type_menu = tk.OptionMenu(
                settings_frame,
                self.capture_type_var,
                *CaptureManager.CAPTURE_TYPES
            )
        capture_type_menu.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # Resolution
        tk.Label(settings_frame, text="Resolution X:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.res_x_var = tk.StringVar(value=str(initial_resolution[0]))
        res_x_entry = tk.Entry(settings_frame, textvariable=self.res_x_var, width=10)
        res_x_entry.grid(row=1, column=1, sticky="w", padx=2, pady=2)
        res_x_entry.bind("<KeyRelease>", self.on_settings_change)
        
        tk.Label(settings_frame, text="Resolution Y:").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.res_y_var = tk.StringVar(value=str(initial_resolution[1]))
        res_y_entry = tk.Entry(settings_frame, textvariable=self.res_y_var, width=10)
        res_y_entry.grid(row=2, column=1, sticky="w", padx=2, pady=2)
        res_y_entry.bind("<KeyRelease>", self.on_settings_change)
        
        # FPS
        tk.Label(settings_frame, text="Target FPS:").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.fps_var = tk.StringVar(value=str(initial_fps))
        fps_entry = tk.Entry(settings_frame, textvariable=self.fps_var, width=10)
        fps_entry.grid(row=3, column=1, sticky="w", padx=2, pady=2)
        fps_entry.bind("<KeyRelease>", self.on_settings_change)
        
        # Capture Mode
        tk.Label(settings_frame, text="Mode:").grid(row=4, column=0, sticky="w", padx=2, pady=2)
        self.capture_mode_var = tk.StringVar(value="Image")
        capture_mode_menu = tk.OptionMenu(settings_frame, self.capture_mode_var, "Image", "Video")
        capture_mode_menu.grid(row=4, column=1, sticky="w", padx=2, pady=2)
        
        # Quick Capture Button
        self.quick_capture_btn = tk.Button(
            settings_frame,
            text="Quick Capture",
            command=self.on_quick_capture,
            width=15,
            bg="#2196F3",
            fg="white"
        )
        self.quick_capture_btn.grid(row=5, column=0, columnspan=2, padx=2, pady=10, sticky="ew")
        
        # Preview FPS label
        tk.Label(settings_frame, text="Preview FPS:").grid(row=6, column=0, sticky="w", padx=2, pady=2)
        self.fps_label = tk.Label(settings_frame, text="0.0", font=("Courier", 10))
        self.fps_label.grid(row=6, column=1, sticky="w", padx=2, pady=2)
        
        # Status label
        self.status_label = tk.Label(
            settings_frame,
            text="Ready",
            fg="gray",
            font=("Arial", 9),
            wraplength=200
        )
        self.status_label.grid(row=7, column=0, columnspan=2, padx=2, pady=5, sticky="w")
        
        # Initialize FPS tracking if picam2 is available
        # Note: We'll use the existing post_callback if available, or create our own
        if self.picam2 is not None and not self._simulate_cam:
            self.fps_tracker = FPSTracker()
            # Set up frame callback for FPS tracking
            # Store existing callback if any
            existing_callback = getattr(self.picam2, 'post_callback', None)
            
            def frame_callback(request):
                """Callback fired for each camera frame."""
                # Call existing callback if it exists
                if existing_callback:
                    try:
                        existing_callback(request)
                    except Exception as e:
                        logger.warning(f"Error in existing post_callback: {e}")
                # Update our FPS tracker
                if self.fps_tracker:
                    self.fps_tracker.update()
            
            self.picam2.post_callback = frame_callback
        else:
            self.fps_tracker = None
        
        # Initialize preview widget
        self.update_preview()
        
        # Start FPS update loop
        self.update_fps()
    
    def update_fps(self) -> None:
        """Update FPS display from fps_tracker."""
        if self.fps_tracker is not None:
            fps = self.fps_tracker.get_fps()
            self.fps_label.config(text=f"{fps:.1f}")
        else:
            self.fps_label.config(text="0.0")
        
        # Schedule next update (every 200ms = 5 Hz update rate)
        if self._running:
            self.window.after(200, self.update_fps)
    
    def on_capture_type_change(self, capture_type: str) -> None:
        """Handle capture type change."""
        if self.capture_manager:
            try:
                success = self.capture_manager.set_capture_type(capture_type)
                if success:
                    self.status_label.config(text=f"Switched to {capture_type}", fg="green")
                    # Update preview to reflect new capture type
                    # Update grayscale flag on existing widget (faster than recreating)
                    is_grayscale = "Grayscale" in capture_type
                    if self.preview_widget is not None:
                        self.preview_widget.set_grayscale(is_grayscale)
                    else:
                        # Recreate preview widget if it doesn't exist
                        self.update_preview()
                else:
                    self.status_label.config(text="Failed to switch capture type", fg="red")
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="red")
                logger.error(f"Error changing capture type: {e}")
    
    
    def on_settings_change(self, event=None) -> None:
        """Handle settings change (resolution, FPS)."""
        # Update preview when settings change
        self.update_preview()
    
    def update_preview(self) -> None:
        """Update preview widget with current settings."""
        try:
            # Stop existing preview
            if self.preview_widget is not None:
                self.preview_widget.stop()
                self.preview_widget = None
            
            # Get current settings
            try:
                res_x = int(self.res_x_var.get().strip())
                res_y = int(self.res_y_var.get().strip())
                fps = float(self.fps_var.get().strip())
            except ValueError:
                # Invalid values, use defaults
                res_x, res_y = 800, 600
                fps = 30.0
            
            # Get current capture type to pass to preview widget
            current_capture_type = self.capture_type_var.get()
            is_grayscale = "Grayscale" in current_capture_type
            
            # Create new preview widget with current settings
            # Pass grayscale flag so it can convert frames appropriately
            if self.picam2 is not None:
                self.preview_widget = TkinterPreviewWidget(
                    canvas=self.preview_canvas,
                    picam2=self.picam2,
                    width=res_x,
                    height=res_y,
                    fps=fps,
                    grayscale=is_grayscale  # Pass grayscale flag
                )
                self.preview_widget.start()
            else:
                logger.warning("Cannot create preview widget: picam2 is None")
            
        except Exception as e:
            logger.error(f"Error updating preview: {e}")
            self.status_label.config(text=f"Preview error: {e}", fg="red")
    
    def on_quick_capture(self) -> None:
        """Handle quick capture button click."""
        if self.capture_manager is None:
            self.status_label.config(text="Capture not available", fg="orange")
            return
        
        mode = self.capture_mode_var.get()
        
        try:
            if mode == "Image":
                # Capture single image
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_dir = "outputs"
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f"capture_{timestamp}.png")
                
                success = self.capture_manager.capture_image(output_path)
                if success:
                    self.status_label.config(text=f"Saved: {os.path.basename(output_path)}", fg="green")
                else:
                    self.status_label.config(text="Capture failed", fg="red")
            else:
                # Video mode - toggle recording
                if self._recording:
                    # Stop recording
                    output_path = self.capture_manager.stop_video_recording(codec="FFV1")
                    if output_path:
                        self.status_label.config(text=f"Saved: {os.path.basename(output_path)}", fg="green")
                        self.quick_capture_btn.config(text="Quick Capture", bg="#2196F3")
                        self._recording = False
                        # Hide recording indicator
                        self.preview_canvas.itemconfig(self.recording_indicator, state="hidden")
                        self.preview_canvas.itemconfig(self.recording_text, state="hidden")
                    else:
                        self.status_label.config(text="Recording failed", fg="red")
                else:
                    # Start recording
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_dir = "outputs"
                    os.makedirs(output_dir, exist_ok=True)
                    output_path = os.path.join(output_dir, f"video_{timestamp}.avi")
                    
                    success = self.capture_manager.start_video_recording(output_path, codec="FFV1")
                    if success:
                        self.status_label.config(text="Recording...", fg="red")
                        self.quick_capture_btn.config(text="Stop Recording", bg="red")
                        self._recording = True
                        # Show recording indicator on preview
                        self.preview_canvas.itemconfig(self.recording_indicator, state="normal")
                        self.preview_canvas.itemconfig(self.recording_text, state="normal")
                    else:
                        self.status_label.config(text="Failed to start recording", fg="red")
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg="red")
            logger.error(f"Quick capture error: {e}")
    
    def on_close(self) -> None:
        """Handle window close."""
        # Stop FPS update loop
        self._running = False
        
        # Stop preview
        if self.preview_widget is not None:
            try:
                self.preview_widget.stop()
            except Exception as e:
                logger.error(f"Error stopping preview widget: {e}")
        
        # Stop recording if active
        if self._recording and self.capture_manager:
            try:
                self.capture_manager.stop_video_recording()
                self._recording = False
                # Hide recording indicator
                self.preview_canvas.itemconfig(self.recording_indicator, state="hidden")
                self.preview_canvas.itemconfig(self.recording_text, state="hidden")
            except Exception as e:
                logger.error(f"Error stopping recording: {e}")
        
        # Cleanup capture manager (if we created it)
        if self.capture_manager is not None:
            try:
                self.capture_manager.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up capture manager: {e}")
        
        # Stop camera (if we created it)
        if self.picam2 is not None:
            try:
                self.picam2.stop()
            except Exception as e:
                logger.error(f"Error stopping camera: {e}")
        
        # Destroy window
        self.window.destroy()
    
    def destroy(self) -> None:
        """Destroy the preview window."""
        self.on_close()

