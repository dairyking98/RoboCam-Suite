"""
Preview Window - Hardware-Optimized Native Preview with Capture Settings

Provides a separate window with hardware-accelerated native preview (DRM/QTGL)
and capture settings. Uses native Picamera2 preview for maximum performance.

Author: RoboCam-Suite
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple
from datetime import datetime
import os
import time
import threading
from PIL import Image, ImageTk
from robocam.capture_interface import CaptureManager
from robocam.camera_preview import FPSTracker, start_best_preview
from robocam.logging_config import get_logger

logger = get_logger(__name__)


class PreviewWindow:
    """
    Separate window for hardware-optimized camera preview and capture settings.
    
    Uses native Picamera2 preview (DRM/QTGL) for maximum performance.
    For grayscale mode, shows a captured image preview instead of live preview.
    
    Attributes:
        window (tk.Toplevel): The preview window
        capture_manager (Optional[CaptureManager]): Capture manager instance
        picam2: Picamera2 instance
        _recording (bool): Whether currently recording video
        _native_preview_active (bool): Whether native preview is active
        _preview_backend (Optional[str]): Active preview backend name
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
        self._native_preview_active = False
        self._preview_backend: Optional[str] = None
        self._measuring_fps = False
        
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
        
        self._recording: bool = False
        self.fps_tracker: Optional[FPSTracker] = None
        self._running: bool = True
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Camera Preview & Capture Settings")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Create main frame - only settings, no preview embedded
        main_frame = tk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Settings frame (no preview area in tkinter - preview is separate native window)
        settings_frame = tk.LabelFrame(main_frame, text="Capture Settings", padx=5, pady=5)
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=5)
        
        # Preview status label (info only, not actual preview)
        preview_status_frame = tk.LabelFrame(main_frame, text="Preview Status", padx=5, pady=5)
        preview_status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.preview_info_label = tk.Label(
            preview_status_frame,
            text="Native preview opens in separate window",
            font=("Arial", 9),
            fg="gray",
            justify=tk.LEFT
        )
        self.preview_info_label.pack(anchor="w", padx=5, pady=5)
        
        # Grayscale preview canvas (shown when in grayscale mode - for captured image only)
        self.grayscale_canvas = tk.Canvas(
            preview_status_frame,
            width=min(initial_resolution[0], 400),
            height=min(initial_resolution[1], 300),
            bg="black",
            highlightthickness=1,
            highlightbackground="gray"
        )
        self.grayscale_image_id = None
        # Canvas is hidden by default, only shown for grayscale captured images
        
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
        
        # Measure FPS Button
        self.measure_fps_btn = tk.Button(
            settings_frame,
            text="Measure FPS",
            command=self.on_measure_fps,
            width=15,
            bg="#4CAF50",
            fg="white"
        )
        self.measure_fps_btn.grid(row=6, column=0, columnspan=2, padx=2, pady=5, sticky="ew")
        
        # Preview FPS label
        tk.Label(settings_frame, text="Preview FPS:").grid(row=7, column=0, sticky="w", padx=2, pady=2)
        self.fps_label = tk.Label(settings_frame, text="0.0", font=("Courier", 10))
        self.fps_label.grid(row=7, column=1, sticky="w", padx=2, pady=2)
        
        # Status label
        self.status_label = tk.Label(
            settings_frame,
            text="Ready",
            fg="gray",
            font=("Arial", 9),
            wraplength=200
        )
        self.status_label.grid(row=8, column=0, columnspan=2, padx=2, pady=5, sticky="w")
        
        # Initialize FPS tracking if picam2 is available
        if self.picam2 is not None and not self._simulate_cam:
            self.fps_tracker = FPSTracker()
            # Set up frame callback for FPS tracking
            def frame_callback(request):
                """Callback fired for each camera frame."""
                if self.fps_tracker:
                    self.fps_tracker.update()
            
            self.picam2.post_callback = frame_callback
        
        # Defer preview start to allow window to fully initialize
        # This prevents issues with preview backends that need a fully rendered window
        def start_preview_after_init():
            """Start preview after window is fully initialized."""
            self.window.update_idletasks()  # Ensure window is rendered
            time.sleep(0.1)  # Brief additional wait
            # Start native preview (if not grayscale)
            self.update_preview()
        
        # Schedule preview start after window initialization
        self.window.after(100, start_preview_after_init)
        
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
                    # Update preview based on capture type
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
        """Update preview based on current settings and capture type."""
        if self.picam2 is None or self._simulate_cam:
            return
        
        try:
            # Get current capture type
            current_capture_type = self.capture_type_var.get()
            is_grayscale = "Grayscale" in current_capture_type
            
            if is_grayscale:
                # For grayscale mode, stop native preview and show captured image
                self._stop_native_preview()
                self._show_grayscale_preview()
            else:
                # For color mode, use native hardware-accelerated preview
                self._hide_grayscale_preview()
                self._start_native_preview()
                
        except Exception as e:
            logger.error(f"Error updating preview: {e}")
            self.status_label.config(text=f"Preview error: {e}", fg="red")
    
    def _start_native_preview(self) -> None:
        """Start native hardware-accelerated preview."""
        if self._native_preview_active or self.picam2 is None:
            return
        
        try:
            # Get current resolution and FPS
            try:
                res_x = int(self.res_x_var.get().strip())
                res_y = int(self.res_y_var.get().strip())
                fps = float(self.fps_var.get().strip())
            except ValueError:
                res_x, res_y = 800, 600
                fps = 30.0
            
            # Check if camera is already started and configured
            camera_ready = False
            if hasattr(self.picam2, 'started') and self.picam2.started:
                # Camera is already started - check if we need to reconfigure
                try:
                    # Try to check current config - if it matches, don't reconfigure
                    current_config = getattr(self.picam2, 'camera_config', None)
                    if current_config:
                        # Camera already running - only reconfigure if settings changed
                        main_config = current_config.get('main', {})
                        current_size = main_config.get('size')
                        if current_size == (res_x, res_y):
                            # Same resolution, camera is ready
                            camera_ready = True
                            logger.info("Camera already configured correctly, skipping reconfiguration")
                except:
                    pass
            
            # Only reconfigure if needed
            if not camera_ready:
                # Stop camera if running
                try:
                    if hasattr(self.picam2, 'started') and self.picam2.started:
                        self.picam2.stop()
                        time.sleep(0.1)  # Brief pause after stopping
                except Exception as e:
                    logger.warning(f"Error stopping camera: {e}")
                
                # Configure and start camera
                try:
                    self.picam2_config = self.picam2.create_preview_configuration(
                        main={"size": (res_x, res_y)},
                        controls={"FrameRate": fps},
                        buffer_count=2
                    )
                    self.picam2.configure(self.picam2_config)
                    self.picam2.start()
                    logger.info(f"Camera configured: {res_x}x{res_y} @ {fps} FPS")
                except Exception as e:
                    logger.error(f"Failed to configure camera: {e}")
                    self.preview_info_label.config(
                        text=f"✗ Camera configuration error: {str(e)[:60]}...",
                        fg="red"
                    )
                    return
                
                # Give camera time to fully start before attempting preview
                time.sleep(0.2)  # Increased wait time for camera initialization
            
            # Stop any existing preview first (in case preview was already started)
            try:
                if hasattr(self.picam2, '_preview'):
                    # Check if preview is active
                    if self.picam2._preview is not None:
                        logger.info("Stopping existing preview before starting new one...")
                        self.picam2.stop_preview()
                        time.sleep(0.1)
            except Exception as e:
                logger.debug(f"Error checking for existing preview (likely none): {e}")
            
            # Ensure camera is in the right state for preview
            # Check if camera is actually started and ready
            if not hasattr(self.picam2, 'started') or not self.picam2.started:
                logger.warning("Camera not started, attempting to start...")
                try:
                    self.picam2.start()
                    time.sleep(0.2)  # Give it more time to initialize
                except Exception as e:
                    logger.error(f"Failed to start camera: {e}")
                    self.preview_info_label.config(
                        text=f"✗ Camera start failed: {str(e)[:60]}...",
                        fg="red"
                    )
                    return
            
            # Start native preview using the smart backend selection function
            # This function automatically detects desktop session and picks the best backend
            error_details = []
            try:
                self._preview_backend = start_best_preview(self.picam2, backend="auto")
                self._native_preview_active = True
                self.preview_info_label.config(
                    text=f"✓ Native preview active in separate window (Backend: {self._preview_backend.upper()})",
                    fg="green"
                )
                logger.info(f"Started native preview with backend: {self._preview_backend.upper()}")
            except RuntimeError as e:
                error_msg = str(e)
                error_details.append(f"Auto-selection: {error_msg}")
                logger.warning(f"start_best_preview failed: {error_msg}")
                
                # Try each backend individually with better error messages
                from picamera2 import Preview
                backends_to_try = [
                    ("DRM", Preview.DRM),
                    ("QTGL", Preview.QTGL),
                    ("NULL", Preview.NULL)
                ]
                
                preview_started = False
                for backend_name, backend_type in backends_to_try:
                    if preview_started:
                        break
                    try:
                        logger.info(f"Trying {backend_name} backend...")
                        self.picam2.start_preview(backend_type)
                        self._preview_backend = backend_name.lower()
                        self._native_preview_active = True
                        preview_started = True
                        logger.info(f"Successfully started {backend_name} preview")
                        
                        if backend_name == "NULL":
                            self.preview_info_label.config(
                                text=f"⚠ Preview unavailable (headless mode)\nCapture still works\n\nAll visual backends failed.\nErrors: {error_msg[:60]}",
                                fg="orange"
                            )
                        else:
                            self.preview_info_label.config(
                                text=f"✓ Native preview active (Backend: {backend_name})",
                                fg="green"
                            )
                    except Exception as be:
                        be_msg = str(be)
                        error_details.append(f"{backend_name}: {be_msg[:40]}")
                        logger.warning(f"{backend_name} backend failed: {be_msg}")
                
                if not preview_started:
                    # All preview backends failed - but we can still capture
                    error_summary = "\n".join(error_details[:3])  # Show first 3 errors
                    logger.error(f"All preview backends failed. Errors: {error_details}")
                    self.preview_info_label.config(
                        text=f"⚠ Preview unavailable\nCapture still works\n\nAll backends failed.\n{error_summary[:80]}...\n\nCheck display/camera connection.",
                        fg="orange"
                    )
                    self._native_preview_active = False
                    # Don't return - allow app to continue without preview
                    return
            except Exception as e:
                # Unexpected error
                error_msg = str(e)
                logger.error(f"Unexpected error starting preview: {error_msg}", exc_info=True)
                self.preview_info_label.config(
                    text=f"✗ Preview error: {error_msg[:80]}...\n\nCheck logs for details.",
                    fg="red"
                )
                self._native_preview_active = False
        except Exception as e:
            logger.error(f"Error starting native preview: {e}")
            self.preview_info_label.config(
                text=f"✗ Preview error: {str(e)[:60]}...",
                fg="red"
            )
    
    def _stop_native_preview(self) -> None:
        """Stop native preview."""
        if not self._native_preview_active:
            return
        
        try:
            if self.picam2 is not None:
                self.picam2.stop_preview()
            self._native_preview_active = False
            self._preview_backend = None
            logger.info("Stopped native preview")
        except Exception as e:
            logger.error(f"Error stopping native preview: {e}")
    
    def _show_grayscale_preview(self) -> None:
        """Show captured grayscale image preview."""
        if self.picam2 is None:
            return
        
        try:
            # Ensure camera is running
            try:
                if hasattr(self.picam2, 'started') and not self.picam2.started:
                    self.picam2.start()
            except:
                pass
            
            # Capture a frame from picam2
            import numpy as np
            array = self.picam2.capture_array("main")
            
            # Convert to grayscale
            if array.ndim == 3 and array.shape[2] == 3:
                # RGB - convert to grayscale
                gray = np.dot(array[...,:3], [0.2989, 0.5870, 0.1140]).astype(np.uint8)
                frame = gray
            elif array.ndim == 2:
                # Already grayscale
                frame = array
            elif array.ndim == 3 and array.shape[2] == 1:
                # Single channel
                frame = array[:, :, 0]
            else:
                # Extract first channel
                frame = array[:, :, 0] if array.ndim == 3 else array
            
            if frame is not None:
                # Convert to PIL Image
                if frame.ndim == 2:
                    pil_image = Image.fromarray(frame, mode='L')
                else:
                    pil_image = Image.fromarray(frame)
                
                # Resize to fit canvas
                canvas_width = self.grayscale_canvas.winfo_width()
                canvas_height = self.grayscale_canvas.winfo_height()
                if canvas_width > 1 and canvas_height > 1:
                    pil_image = pil_image.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage and display
                photo = ImageTk.PhotoImage(image=pil_image)
                
                # Show canvas below info label
                self.grayscale_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                
                # Update canvas
                if self.grayscale_image_id is None:
                    self.grayscale_image_id = self.grayscale_canvas.create_image(
                        canvas_width // 2,
                        canvas_height // 2,
                        image=photo,
                        anchor='center'
                    )
                else:
                    self.grayscale_canvas.itemconfig(self.grayscale_image_id, image=photo)
                    self.grayscale_canvas.coords(
                        self.grayscale_image_id,
                        canvas_width // 2,
                        canvas_height // 2
                    )
                
                # Keep reference to prevent garbage collection
                self.grayscale_canvas.photo = photo
                
                self.preview_info_label.config(
                    text="✓ Grayscale preview (captured image shown below)",
                    fg="blue"
                )
        except Exception as e:
            logger.error(f"Error showing grayscale preview: {e}")
            self.preview_info_label.config(
                text=f"Preview error: {e}",
                fg="red"
            )
    
    def _hide_grayscale_preview(self) -> None:
        """Hide grayscale preview canvas."""
        self.grayscale_canvas.pack_forget()
    
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
                    # Update grayscale preview if in grayscale mode
                    if "Grayscale" in self.capture_type_var.get():
                        self._show_grayscale_preview()
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
                    else:
                        self.status_label.config(text="Failed to start recording", fg="red")
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg="red")
            logger.error(f"Quick capture error: {e}")
    
    def on_measure_fps(self) -> None:
        """Measure maximum grayscale capture FPS at current settings."""
        if self.picam2 is None or self._simulate_cam:
            self.status_label.config(text="Camera not available", fg="orange")
            return
        
        if self._measuring_fps:
            self.status_label.config(text="FPS measurement in progress...", fg="orange")
            return
        
        def measure_fps_thread():
            """Measure grayscale capture FPS in a separate thread."""
            self._measuring_fps = True
            self.measure_fps_btn.config(state="disabled", text="Measuring...")
            self.status_label.config(text="Stopping preview and measuring grayscale capture FPS...", fg="orange")
            
            # Store current preview state
            was_preview_active = self._native_preview_active
            previous_backend = self._preview_backend
            
            try:
                # Stop native preview if active
                self._stop_native_preview()
                
                # Get current settings
                try:
                    res_x = int(self.res_x_var.get().strip())
                    res_y = int(self.res_y_var.get().strip())
                    fps = float(self.fps_var.get().strip())
                except ValueError:
                    res_x, res_y = 800, 600
                    fps = 30.0
                
                # Stop camera
                try:
                    if hasattr(self.picam2, 'started') and self.picam2.started:
                        self.picam2.stop()
                except:
                    pass
                
                # Configure for grayscale capture (YUV420 format for maximum speed)
                # Use video configuration which allows higher FPS
                import numpy as np
                grayscale_config = self.picam2.create_video_configuration(
                    main={"size": (res_x, res_y), "format": "YUV420"},
                    controls={"FrameRate": fps},
                    buffer_count=2  # Minimal buffer for maximum speed
                )
                self.picam2.configure(grayscale_config)
                self.picam2.start()
                
                # Give camera time to initialize
                time.sleep(0.5)
                
                # Measure grayscale capture FPS by repeatedly capturing frames
                self.status_label.config(text="Measuring grayscale capture FPS (5 seconds)...", fg="orange")
                fps_tracker = FPSTracker()
                
                # Measure for 5 seconds by capturing frames as fast as possible
                start_time = time.time()
                frame_count = 0
                measurement_duration = 5.0
                
                while time.time() - start_time < measurement_duration:
                    try:
                        # Capture a grayscale frame (YUV420 format)
                        array = self.picam2.capture_array("main")
                        
                        # Extract Y channel (luminance) for grayscale
                        if array.ndim == 3:
                            # YUV420: Y channel is first channel or first 2/3 of data
                            # Depending on YUV420 layout, Y is typically the first channel
                            gray_frame = array[:, :, 0] if array.shape[2] >= 1 else array
                        elif array.ndim == 2:
                            # Already 2D grayscale
                            gray_frame = array
                        else:
                            gray_frame = array
                        
                        # Frame captured successfully
                        fps_tracker.update()
                        frame_count += 1
                    except Exception as e:
                        logger.warning(f"Frame capture error during FPS measurement: {e}")
                        # Continue measuring even if some frames fail
                        time.sleep(0.01)  # Small delay to prevent busy loop
                
                measured_fps = fps_tracker.get_fps()
                actual_duration = time.time() - start_time
                
                logger.info(f"Grayscale capture FPS test: {frame_count} frames in {actual_duration:.2f}s = {measured_fps:.1f} FPS")
                
                # Restore preview configuration
                try:
                    self.picam2.stop()
                    time.sleep(0.1)
                except:
                    pass
                
                # Restore preview configuration
                try:
                    res_x = int(self.res_x_var.get().strip())
                    res_y = int(self.res_y_var.get().strip())
                    fps = float(self.fps_var.get().strip())
                except ValueError:
                    res_x, res_y = 800, 600
                    fps = 30.0
                
                self.picam2_config = self.picam2.create_preview_configuration(
                    main={"size": (res_x, res_y)},
                    controls={"FrameRate": fps},
                    buffer_count=2
                )
                self.picam2.configure(self.picam2_config)
                self.picam2.start()
                
                # Restore FPS tracking callback
                if self.fps_tracker:
                    def restore_callback(request):
                        if self.fps_tracker:
                            self.fps_tracker.update()
                    self.picam2.post_callback = restore_callback
                
                # Give camera time to restart
                time.sleep(0.2)
                
                # Restart preview window (always, regardless of grayscale mode)
                # This ensures preview is displayed after FPS test
                if was_preview_active:
                    # Restore preview if it was active before
                    if "Grayscale" not in self.capture_type_var.get():
                        self._start_native_preview()
                    else:
                        # For grayscale, show the preview image
                        self._show_grayscale_preview()
                else:
                    # Even if preview wasn't active, start it now
                    if "Grayscale" not in self.capture_type_var.get():
                        self._start_native_preview()
                    else:
                        self._show_grayscale_preview()
                
                # Update status with measured FPS
                self.status_label.config(
                    text=f"Grayscale capture FPS: {measured_fps:.1f} at {res_x}x{res_y} ({frame_count} frames in {actual_duration:.2f}s)",
                    fg="green"
                )
                logger.info(f"Measured grayscale capture FPS: {measured_fps:.1f} at {res_x}x{res_y}")
                
            except Exception as e:
                logger.error(f"Error measuring grayscale capture FPS: {e}", exc_info=True)
                self.status_label.config(text=f"FPS measurement error: {e}", fg="red")
                
                # Try to restore preview even on error
                try:
                    if hasattr(self.picam2, 'started') and self.picam2.started:
                        self.picam2.stop()
                    # Restore preview config
                    try:
                        res_x = int(self.res_x_var.get().strip())
                        res_y = int(self.res_y_var.get().strip())
                        fps = float(self.fps_var.get().strip())
                    except ValueError:
                        res_x, res_y = 800, 600
                        fps = 30.0
                    
                    self.picam2_config = self.picam2.create_preview_configuration(
                        main={"size": (res_x, res_y)},
                        controls={"FrameRate": fps},
                        buffer_count=2
                    )
                    self.picam2.configure(self.picam2_config)
                    self.picam2.start()
                    time.sleep(0.2)
                    
                    # Restart preview
                    if "Grayscale" not in self.capture_type_var.get():
                        self._start_native_preview()
                    else:
                        self._show_grayscale_preview()
                except Exception as restore_error:
                    logger.error(f"Failed to restore preview after FPS measurement error: {restore_error}")
            finally:
                self._measuring_fps = False
                self.measure_fps_btn.config(state="normal", text="Measure FPS")
        
        # Start measurement in separate thread
        thread = threading.Thread(target=measure_fps_thread, daemon=True)
        thread.start()
    
    def on_close(self) -> None:
        """Handle window close."""
        # Stop FPS update loop
        self._running = False
        
        # Stop native preview
        self._stop_native_preview()
        
        # Stop recording if active
        if self._recording and self.capture_manager:
            try:
                self.capture_manager.stop_video_recording()
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
