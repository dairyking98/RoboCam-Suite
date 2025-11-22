"""
Calibration Application - Manual Positioning and Calibration GUI

Provides a GUI for manually positioning the camera over well plates and
recording coordinates for calibration. Uses embedded tkinter preview for
camera display integrated into the main window.

Author: RoboCam-Suite
"""

import tkinter as tk
import os
import json
from datetime import datetime
from typing import Optional, List, Tuple
from picamera2 import Picamera2
from robocam.robocam_ccc import RoboCam
from robocam.camera_preview import FPSTracker
from robocam.config import get_config
from robocam.stentorcam import WellPlatePathGenerator
from robocam.capture_interface import CaptureManager
from robocam.tkinter_preview import TkinterPreviewWidget

# Preview resolution for camera display (will be loaded from config)
# Default resolution optimized for 30 FPS preview (800x600 should easily achieve 30 FPS)
default_preview_resolution: tuple[int, int] = (800, 600)  # Standard SVGA resolution for reliable 30 FPS


class CameraApp:
    """
    Calibration application GUI for manual positioning and coordinate recording.
    
    Provides:
    - Embedded camera preview in main window
    - Precise movement controls (0.1mm, 1.0mm, 10.0mm, or custom step size)
    - Real-time position display
    - FPS monitoring
    - Home functionality
    
    Attributes:
        root (tk.Tk): Main tkinter window
        picam2 (Picamera2): Camera instance
        robocam (RoboCam): Printer control instance
        running (bool): Application running state
        step_size_type (tk.StringVar): Current step size selection ("0.1", "1.0", "10.0", or "custom")
        custom_step_entry (tk.Entry): Entry field for custom step size (default: 9.0 mm)
        position_label (tk.Label): Current position display
        fps_label (tk.Label): FPS display
        fps_tracker (FPSTracker): FPS tracking instance
        preview_widget (Optional[TkinterPreviewWidget]): Embedded preview widget
    """
    
    def __init__(self, root: tk.Tk, simulate_3d: bool = False, simulate_cam: bool = False) -> None:
        """
        Initialize calibration application.
        
        Args:
            root: Tkinter root window
            simulate_3d: If True, run in 3D printer simulation mode (no printer connection)
            simulate_cam: If True, run in camera simulation mode (no camera connection)
        """
        self.root: tk.Tk = root
        sim_text = []
        if simulate_3d:
            sim_text.append("3D PRINTER SIM")
        if simulate_cam:
            sim_text.append("CAMERA SIM")
        title_suffix = f" [{' + '.join(sim_text)}]" if sim_text else ""
        self.root.title("RoboCam Calibration - Controls" + title_suffix)
        self._simulate_3d: bool = simulate_3d
        self._simulate_cam: bool = simulate_cam

        # Load config for camera settings
        config = get_config()
        camera_config = config.get_camera_config()
        default_fps = camera_config.get("default_fps", 30.0)
        
        # Get preview resolution from config, or use default
        preview_res = camera_config.get("preview_resolution", list(default_preview_resolution))
        if isinstance(preview_res, list) and len(preview_res) == 2:
            preview_resolution = tuple(preview_res)
        else:
            preview_resolution = default_preview_resolution

        # Picamera2 setup
        self.preview_widget: Optional[TkinterPreviewWidget] = None
        if self._simulate_cam:
            # Camera simulation mode: skip camera initialization
            self.picam2: Optional[Picamera2] = None
            self.fps_tracker: Optional[FPSTracker] = None
            print("Camera simulation mode: Skipping camera initialization")
        else:
            self.picam2: Picamera2 = Picamera2()
            self.picam2_config = self.picam2.create_preview_configuration(
                main={"size": preview_resolution},
                controls={"FrameRate": default_fps},
                buffer_count=2
            )
            self.picam2.configure(self.picam2_config)
            
            # Set up FPS tracking
            self.fps_tracker: FPSTracker = FPSTracker()
            
            def frame_callback(request):
                """Callback fired for each camera frame."""
                self.fps_tracker.update()
            
            self.picam2.post_callback = frame_callback
            
            # Start camera (no native preview - we'll use tkinter preview)
            try:
                self.picam2.start()
                print("Camera started (embedded preview in tkinter window)")
            except Exception as exc:
                msg = f"Camera start failed: {exc}"
                raise RuntimeError(msg) from exc

        # UI Elements (must be created before preview widget)
        self.create_widgets()
        
        # Initialize embedded preview widget (after widgets are created)
        if not self._simulate_cam and self.picam2 is not None:
            try:
                preview_canvas = getattr(self, 'preview_canvas', None)
                if preview_canvas is not None:
                    self.preview_widget = TkinterPreviewWidget(
                        canvas=preview_canvas,
                        picam2=self.picam2,
                        width=preview_resolution[0],
                        height=preview_resolution[1],
                        fps=default_fps
                    )
                    self.preview_widget.start()
                    print("Embedded preview started")
            except Exception as e:
                print(f"Warning: Failed to start embedded preview: {e}")
        
        # Calculate and set proper initial window size
        self.root.update_idletasks()
        
        # Get required size
        req_width = self.root.winfo_reqwidth()
        req_height = self.root.winfo_reqheight()
        
        # Get current window size
        try:
            current_width = self.root.winfo_width()
            current_height = self.root.winfo_height()
            # If window is too small (less than 10x10, it's not yet displayed properly)
            if current_width < 10 or current_height < 10:
                current_width = req_width
                current_height = req_height
        except:
            current_width = req_width
            current_height = req_height
        
        # Set minimum size (ensure window is never too small)
        min_width = max(req_width, 500)
        min_height = max(req_height, 400)
        self.root.minsize(min_width, min_height)
        
        # Only resize if current window is smaller than required
        if current_width < min_width or current_height < min_height:
            new_width = max(current_width, min_width)
            new_height = max(current_height, min_height)
            self.root.geometry(f"{new_width}x{new_height}")
        
        # Allow user to resize window manually
        self.root.resizable(True, True)

        self.running: bool = True
        # Load config for baudrate (config already loaded above for camera settings)
        baudrate = config.get("hardware.printer.baudrate", 115200)
        
        # Initialize RoboCam with error handling
        try:
            self.robocam: RoboCam = RoboCam(baudrate=baudrate, config=config, simulate_3d=self._simulate_3d)
        except Exception as e:
            error_msg = str(e).lower()
            if self._simulate_3d:
                # In 3D printer simulation mode, don't show error - just continue
                print(f"3D printer simulation mode: Ignoring printer initialization error: {e}")
                user_msg = "You are simulating a 3D printer! No printer connection needed in simulation mode."
                # Don't show error dialog in simulation mode, just print
                print(user_msg)
            elif "not connected" in error_msg or "serial port" in error_msg or "failed to initialize" in error_msg or "connection" in error_msg:
                user_msg = "Printer connection failed. Check USB cable and try again."
                # Show error in a message box
                import tkinter.messagebox as messagebox
                messagebox.showerror("Connection Error", user_msg)
            else:
                user_msg = f"Initialization error: {error_msg}"
                # Show error in a message box
                import tkinter.messagebox as messagebox
                messagebox.showerror("Connection Error", user_msg)
            
            print(f"RoboCam initialization error: {e}")
            # Continue anyway - user can retry connection later
            self.robocam = None

        # Initialize calibration data
        self.upper_left: Optional[Tuple[float, float, float]] = None
        self.lower_left: Optional[Tuple[float, float, float]] = None
        self.upper_right: Optional[Tuple[float, float, float]] = None
        self.lower_right: Optional[Tuple[float, float, float]] = None
        self.x_quantity: int = 0
        self.y_quantity: int = 0
        self.interpolated_positions: List[Tuple[float, float, float]] = []
        self.labels: List[str] = []

        # Initialize capture manager (only if not in camera simulation mode)
        self.capture_manager: Optional[CaptureManager] = None
        if not self._simulate_cam:
            try:
                # Use preview resolution for capture
                self.capture_manager = CaptureManager(
                    capture_type="Picamera2 (Color)",
                    resolution=preview_resolution,
                    fps=default_fps
                )
            except Exception as e:
                print(f"Warning: Failed to initialize capture manager: {e}")

        # Start updating position and FPS display
        self.update_status()

    def create_widgets(self) -> None:
        """
        Create and layout GUI widgets.
        
        Creates:
        - Camera preview canvas (embedded in window)
        - Step size radio buttons (0.1mm, 1.0mm, 10.0mm)
        - Movement direction buttons (X+, X-, Y+, Y-, Z+, Z+)
        - Position display label
        - FPS display label
        - Home button
        """
        # Create main frame with two columns: preview on left, controls on right
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left column: Preview canvas
        preview_frame = tk.Frame(main_frame)
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(preview_frame, text="Camera Preview", font=("Arial", 10, "bold")).pack(pady=5)
        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=800,
            height=600,
            bg="black",
            highlightthickness=2,
            highlightbackground="gray"
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Right column: Controls
        controls_frame = tk.Frame(main_frame)
        controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Radio buttons for step size
        tk.Label(controls_frame, text="Step Size:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.step_size_type = tk.StringVar(value="1.0")
        tk.Radiobutton(controls_frame, text="0.1 mm", variable=self.step_size_type, value="0.1").grid(row=0, column=1, padx=5)
        tk.Radiobutton(controls_frame, text="1.0 mm", variable=self.step_size_type, value="1.0").grid(row=0, column=2, padx=5)
        tk.Radiobutton(controls_frame, text="10.0 mm", variable=self.step_size_type, value="10.0").grid(row=0, column=3, padx=5)
        
        # Custom step size option
        custom_frame = tk.Frame(controls_frame)
        custom_frame.grid(row=0, column=4, padx=5)
        tk.Radiobutton(custom_frame, text="Custom:", variable=self.step_size_type, value="custom").pack(side=tk.LEFT)
        self.custom_step_entry = tk.Entry(custom_frame, width=8)
        self.custom_step_entry.insert(0, "9.0")
        self.custom_step_entry.pack(side=tk.LEFT, padx=2)
        tk.Label(custom_frame, text="mm").pack(side=tk.LEFT)
        self.custom_step_entry.bind("<KeyRelease>", self.update_custom_step_size)

        # XYZ movement buttons layout
        tk.Label(controls_frame, text="Movement Controls:").grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        tk.Button(controls_frame, text="Y+", command=lambda: self._safe_move(lambda: self.robocam.move_relative(Y=self.get_step_size())),
                 width=8, height=2).grid(row=2, column=2, padx=2, pady=2)
        tk.Button(controls_frame, text="X-", command=lambda: self._safe_move(lambda: self.robocam.move_relative(X=-self.get_step_size())),
                 width=8, height=2).grid(row=3, column=1, padx=2, pady=2)
        tk.Button(controls_frame, text="X+", command=lambda: self._safe_move(lambda: self.robocam.move_relative(X=self.get_step_size())),
                 width=8, height=2).grid(row=3, column=3, padx=2, pady=2)
        tk.Button(controls_frame, text="Y-", command=lambda: self._safe_move(lambda: self.robocam.move_relative(Y=-self.get_step_size())),
                 width=8, height=2).grid(row=4, column=2, padx=2, pady=2)
        tk.Button(controls_frame, text="Z-", command=lambda: self._safe_move(lambda: self.robocam.move_relative(Z=-self.get_step_size())),
                 width=8, height=2).grid(row=2, column=4, padx=2, pady=2)
        tk.Button(controls_frame, text="Z+", command=lambda: self._safe_move(lambda: self.robocam.move_relative(Z=self.get_step_size())),
                 width=8, height=2).grid(row=4, column=4, padx=2, pady=2)

        # Position label
        tk.Label(controls_frame, text="Position (X, Y, Z):").grid(row=5, column=0, sticky="e", padx=5, pady=5)
        self.position_label = tk.Label(controls_frame, text="0.00, 0.00, 0.00", font=("Courier", 10))
        self.position_label.grid(row=5, column=1, columnspan=2, sticky="w", padx=5)

        # FPS label
        tk.Label(controls_frame, text="Preview FPS:").grid(row=6, column=0, sticky="e", padx=5, pady=5)
        self.fps_label = tk.Label(controls_frame, text="0.0", font=("Courier", 10))
        self.fps_label.grid(row=6, column=1, sticky="w", padx=5)

        # Go to coordinate section
        tk.Label(controls_frame, text="Go to Coordinate:").grid(row=7, column=0, sticky="e", padx=5, pady=5)
        coord_frame = tk.Frame(controls_frame)
        coord_frame.grid(row=7, column=1, columnspan=3, padx=5, pady=5, sticky="w")
        
        tk.Label(coord_frame, text="X:").pack(side=tk.LEFT, padx=2)
        self.x_coord_entry = tk.Entry(coord_frame, width=10)
        self.x_coord_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Label(coord_frame, text="Y:").pack(side=tk.LEFT, padx=2)
        self.y_coord_entry = tk.Entry(coord_frame, width=10)
        self.y_coord_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Label(coord_frame, text="Z:").pack(side=tk.LEFT, padx=2)
        self.z_coord_entry = tk.Entry(coord_frame, width=10)
        self.z_coord_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Button(coord_frame, text="Go", command=self.go_to_coordinate,
                 width=8, bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=5)

        # Status/Error label
        tk.Label(controls_frame, text="Status:").grid(row=8, column=0, sticky="e", padx=5, pady=5)
        self.status_label = tk.Label(controls_frame, text="Ready", fg="green", font=("Arial", 9))
        self.status_label.grid(row=8, column=1, columnspan=2, sticky="w", padx=5)
        
        # Home button
        tk.Button(controls_frame, text="Home Printer", command=self.home_printer,
                 width=15, height=2, bg="#4CAF50", fg="white").grid(
            row=9, column=0, columnspan=2, padx=10, pady=10
        )
        
        # Store controls_frame for use in other sections
        self.controls_frame = controls_frame
        
        # Capture Settings Section
        self.create_capture_section()
        
        # 4-Corner Calibration Section
        self.create_calibration_section()
    
    def get_step_size(self) -> float:
        """
        Get the current step size value.
        
        Returns the preset value if a preset is selected, or the custom entry value
        if custom is selected. Defaults to 1.0 if custom entry is invalid.
        
        Returns:
            float: Current step size in mm
        """
        if self.step_size_type.get() == "custom":
            try:
                custom_value = float(self.custom_step_entry.get().strip())
                if custom_value > 0:
                    return custom_value
                else:
                    return 1.0  # Default if invalid
            except ValueError:
                return 1.0  # Default if not a number
        else:
            # Preset value selected
            try:
                return float(self.step_size_type.get())
            except ValueError:
                return 1.0  # Default fallback
    
    def update_custom_step_size(self, event=None) -> None:
        """
        Update custom step size entry validation.
        
        Called when the custom step size entry is modified.
        Validates the input and provides visual feedback if invalid.
        """
        try:
            value = float(self.custom_step_entry.get().strip())
            if value <= 0:
                # Invalid (negative or zero)
                self.custom_step_entry.config(fg="red")
            else:
                # Valid
                self.custom_step_entry.config(fg="black")
        except ValueError:
            # Not a number
            if self.custom_step_entry.get().strip():  # Only show error if not empty
                self.custom_step_entry.config(fg="red")
            else:
                self.custom_step_entry.config(fg="black")
    
    def _safe_move(self, move_func) -> None:
        """
        Safely execute a movement command with error handling.
        
        Args:
            move_func: Function to execute (lambda wrapping move_relative)
        """
        if self.robocam is None:
            self.status_label.config(text="Printer not initialized", fg="red")
            return
        
        try:
            move_func()
            self.status_label.config(text="Move successful", fg="green")
        except Exception as e:
            error_msg = str(e)
            # Make error messages more user-friendly
            if self._simulate_3d:
                user_msg = "You are simulating a 3D printer! No printer connection needed in simulation mode."
            elif "not connected" in error_msg.lower():
                user_msg = "Printer not connected. Check USB cable."
            elif "timeout" in error_msg.lower():
                user_msg = "Movement timed out. Check printer connection."
            elif "serial" in error_msg.lower():
                user_msg = "Communication error. Check USB connection."
            else:
                user_msg = f"Movement failed: {error_msg}"
            
            self.status_label.config(text=user_msg, fg="red")
            print(f"Movement error: {e}")
    
    def home_printer(self) -> None:
        """Home the printer and update position display."""
        if self.robocam is None:
            self.status_label.config(text="Printer not initialized", fg="red")
            return
        
        try:
            self.status_label.config(text="Homing...", fg="orange")
            self.root.update()  # Update GUI to show status
            self.robocam.home()
            self.update_position()
            self.status_label.config(text="Homed successfully", fg="green")
        except Exception as e:
            error_msg = str(e)
            if self._simulate_3d:
                user_msg = "You are simulating a 3D printer! No printer connection needed in simulation mode."
            elif "not connected" in error_msg.lower():
                user_msg = "Printer not connected. Check USB cable."
            elif "timeout" in error_msg.lower():
                user_msg = "Homing timed out. Check printer connection."
            else:
                user_msg = f"Homing failed: {error_msg}"
            self.status_label.config(text=user_msg, fg="red")
            print(f"Homing error: {e}")
    
    def go_to_coordinate(self) -> None:
        """
        Move to the specified X, Y, Z coordinates.
        
        Only moves axes that have values entered. Blank entries are ignored.
        """
        if self.robocam is None:
            self.status_label.config(text="Printer not initialized", fg="red")
            return
        
        try:
            # Read entry fields and convert to float if not blank
            x_str = self.x_coord_entry.get().strip()
            y_str = self.y_coord_entry.get().strip()
            z_str = self.z_coord_entry.get().strip()
            
            x = float(x_str) if x_str else None
            y = float(y_str) if y_str else None
            z = float(z_str) if z_str else None
            
            # Check if at least one coordinate is provided
            if x is None and y is None and z is None:
                self.status_label.config(text="Enter at least one coordinate", fg="orange")
                return
            
            # Move to coordinates
            self.status_label.config(text="Moving...", fg="orange")
            self.root.update()  # Update GUI to show status
            self.robocam.move_absolute(X=x, Y=y, Z=z)
            self.update_position()
            self.status_label.config(text="Move successful", fg="green")
            
        except ValueError:
            self.status_label.config(text="Invalid coordinate value", fg="red")
        except Exception as e:
            error_msg = str(e)
            if self._simulate_3d:
                user_msg = "You are simulating a 3D printer! No printer connection needed in simulation mode."
            elif "not connected" in error_msg.lower():
                user_msg = "Printer not connected. Check USB cable."
            elif "timeout" in error_msg.lower():
                user_msg = "Movement timed out. Check printer connection."
            elif "serial" in error_msg.lower():
                user_msg = "Communication error. Check USB connection."
            else:
                user_msg = f"Movement failed: {error_msg}"
            
            self.status_label.config(text=user_msg, fg="red")
            print(f"Go to coordinate error: {e}")
    
    def create_capture_section(self) -> None:
        """
        Create capture settings GUI section.
        
        Adds:
        - Capture type dropdown
        - Capture mode dropdown (Image/Video)
        - Quick capture button
        - Capture status label
        """
        controls_frame = getattr(self, 'controls_frame', self.root)
        
        # Separator
        tk.Label(controls_frame, text="─" * 50, fg="gray").grid(
            row=10, column=0, columnspan=6, padx=5, pady=10
        )
        
        # Capture Settings LabelFrame
        capture_frame = tk.LabelFrame(controls_frame, text="Capture Settings", padx=5, pady=5)
        capture_frame.grid(row=11, column=0, columnspan=6, sticky="ew", padx=5, pady=5)
        capture_frame.grid_columnconfigure(1, weight=1)
        capture_frame.grid_columnconfigure(3, weight=1)
        
        row = 0
        # Capture type dropdown
        tk.Label(capture_frame, text="Capture Type:").grid(row=row, column=0, sticky="w", padx=2, pady=2)
        self.capture_type_var = tk.StringVar(value="Picamera2 (Color)")
        capture_type_menu = tk.OptionMenu(
            capture_frame, 
            self.capture_type_var,
            *CaptureManager.CAPTURE_TYPES,
            command=self.on_capture_type_change
        )
        capture_type_menu.grid(row=row, column=1, sticky="w", padx=2, pady=2)
        
        # Capture mode dropdown
        tk.Label(capture_frame, text="Mode:").grid(row=row, column=2, sticky="w", padx=2, pady=2)
        self.capture_mode_var = tk.StringVar(value="Image")
        capture_mode_menu = tk.OptionMenu(capture_frame, self.capture_mode_var, "Image", "Video")
        capture_mode_menu.grid(row=row, column=3, sticky="w", padx=2, pady=2)
        
        row += 1
        # Quick capture button
        self.quick_capture_btn = tk.Button(
            capture_frame,
            text="Quick Capture",
            command=self.quick_capture,
            width=15,
            bg="#2196F3",
            fg="white"
        )
        self.quick_capture_btn.grid(row=row, column=0, columnspan=2, padx=2, pady=5, sticky="w")
        
        # Capture status label
        self.capture_status_label = tk.Label(
            capture_frame,
            text="Ready",
            fg="gray",
            font=("Arial", 9)
        )
        self.capture_status_label.grid(row=row, column=2, columnspan=2, sticky="w", padx=2, pady=5)
        
        # Store starting row for calibration section
        self.calibration_start_row = 12
    
    def on_capture_type_change(self, capture_type: str) -> None:
        """Handle capture type dropdown change."""
        if self.capture_manager is None:
            return
        
        try:
            success = self.capture_manager.set_capture_type(capture_type)
            if success:
                self.capture_status_label.config(text=f"Switched to {capture_type}", fg="green")
            else:
                self.capture_status_label.config(text="Failed to switch capture type", fg="red")
        except Exception as e:
            self.capture_status_label.config(text=f"Error: {e}", fg="red")
            print(f"Error changing capture type: {e}")
    
    def quick_capture(self) -> None:
        """Handle quick capture button click."""
        if self.capture_manager is None:
            self.capture_status_label.config(text="Capture not available (simulation mode)", fg="orange")
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
                    self.capture_status_label.config(text=f"Saved: {os.path.basename(output_path)}", fg="green")
                else:
                    self.capture_status_label.config(text="Capture failed", fg="red")
            else:
                # Video mode - toggle recording
                if self.capture_manager.is_recording():
                    # Stop recording
                    output_path = self.capture_manager.stop_video_recording(codec="FFV1")
                    if output_path:
                        self.capture_status_label.config(text=f"Saved: {os.path.basename(output_path)}", fg="green")
                        self.quick_capture_btn.config(text="Quick Capture", bg="#2196F3")
                    else:
                        self.capture_status_label.config(text="Recording failed", fg="red")
                else:
                    # Start recording
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_dir = "outputs"
                    os.makedirs(output_dir, exist_ok=True)
                    output_path = os.path.join(output_dir, f"video_{timestamp}.avi")
                    
                    success = self.capture_manager.start_video_recording(output_path, codec="FFV1")
                    if success:
                        self.capture_status_label.config(text="Recording...", fg="red")
                        self.quick_capture_btn.config(text="Stop Recording", bg="red")
                    else:
                        self.capture_status_label.config(text="Failed to start recording", fg="red")
        except Exception as e:
            self.capture_status_label.config(text=f"Error: {e}", fg="red")
            print(f"Quick capture error: {e}")
    
    def create_calibration_section(self) -> None:
        """
        Create 4-corner calibration GUI section.
        
        Adds:
        - X/Y quantity entry fields
        - 4 corner coordinate display fields
        - Set corner buttons
        - Calibration name entry
        - Save calibration button
        - Preview/validation display
        """
        controls_frame = getattr(self, 'controls_frame', self.root)
        
        # Separator
        tk.Label(controls_frame, text="─" * 50, fg="gray").grid(
            row=self.calibration_start_row, column=0, columnspan=6, padx=5, pady=10
        )
        
        # Section title
        tk.Label(controls_frame, text="4-Corner Calibration", font=("Arial", 12, "bold")).grid(
            row=self.calibration_start_row + 1, column=0, columnspan=6, padx=5, pady=5
        )
        
        # X and Y quantity entry
        tk.Label(controls_frame, text="X Quantity:").grid(row=self.calibration_start_row + 2, column=0, sticky="e", padx=5, pady=5)
        self.x_qty_entry = tk.Entry(controls_frame, width=10)
        self.x_qty_entry.grid(row=self.calibration_start_row + 2, column=1, padx=5, pady=5)
        self.x_qty_entry.bind("<KeyRelease>", self.on_quantity_change)
        
        tk.Label(controls_frame, text="Y Quantity:").grid(row=self.calibration_start_row + 2, column=2, sticky="e", padx=5, pady=5)
        self.y_qty_entry = tk.Entry(controls_frame, width=10)
        self.y_qty_entry.grid(row=self.calibration_start_row + 2, column=3, padx=5, pady=5)
        self.y_qty_entry.bind("<KeyRelease>", self.on_quantity_change)
        
        # Corner coordinate displays and buttons arranged in a 2x2 grid matching actual corner positions
        # Create a frame for the corner grid layout
        corner_grid_frame = tk.Frame(controls_frame)
        corner_grid_frame.grid(row=self.calibration_start_row + 3, column=0, columnspan=6, padx=5, pady=10)
        # Configure equal column weights for balanced layout
        corner_grid_frame.columnconfigure(0, weight=1)
        corner_grid_frame.columnconfigure(1, weight=1)
        
        # Define corners in a 2x2 layout: [Upper-Left, Upper-Right]
        #                                   [Lower-Left, Lower-Right]
        corners = [
            ("Upper-Left", "upper_left", 0, 0),   # Top-left of grid
            ("Upper-Right", "upper_right", 0, 1), # Top-right of grid
            ("Lower-Left", "lower_left", 1, 0),   # Bottom-left of grid
            ("Lower-Right", "lower_right", 1, 1)  # Bottom-right of grid
        ]
        
        self.corner_labels = {}
        self.corner_status_labels = {}
        
        # Create a frame for each corner in the 2x2 grid
        for corner_name, attr_name, grid_row, grid_col in corners:
            # Frame for this corner's UI elements
            corner_frame = tk.Frame(corner_grid_frame, relief=tk.RIDGE, borderwidth=1, padx=5, pady=5)
            corner_frame.grid(row=grid_row, column=grid_col, padx=5, pady=5, sticky="nsew")
            
            # Corner label
            tk.Label(corner_frame, text=corner_name, font=("Arial", 9, "bold")).pack(pady=(0, 3))
            
            # Set button (prominent, positioned at the corner)
            set_btn = tk.Button(
                corner_frame, 
                text=f"Set",
                command=lambda a=attr_name: self.set_corner(a),
                width=12,
                height=2,
                bg="#4CAF50",
                fg="white",
                font=("Arial", 9, "bold")
            )
            set_btn.pack(pady=3)
            
            # Status indicator
            status_label = tk.Label(corner_frame, text="○", fg="gray", font=("Arial", 16))
            status_label.pack(pady=2)
            self.corner_status_labels[attr_name] = status_label
            
            # Coordinate display (read-only, smaller)
            coord_label = tk.Label(
                corner_frame, 
                text="Not set", 
                font=("Courier", 8), 
                fg="gray",
                wraplength=120,
                justify=tk.CENTER
            )
            coord_label.pack(pady=2)
            self.corner_labels[attr_name] = coord_label
        
        # Calibration name entry (positioned below the corner grid)
        tk.Label(controls_frame, text="Calibration Name:").grid(row=self.calibration_start_row + 4, column=0, sticky="e", padx=5, pady=5)
        self.calib_name_entry = tk.Entry(controls_frame, width=30)
        self.calib_name_entry.grid(row=self.calibration_start_row + 4, column=1, columnspan=2, padx=5, pady=5)
        
        # Save calibration button
        self.save_calib_btn = tk.Button(
            controls_frame,
            text="Save Calibration",
            command=self.save_calibration,
            bg="#2196F3",
            fg="white",
            width=15
        )
        self.save_calib_btn.grid(row=self.calibration_start_row + 4, column=3, padx=5, pady=5)
        
        # Preview/validation display
        self.calib_preview_label = tk.Label(
            controls_frame,
            text="Enter X and Y quantities, then set all 4 corners",
            font=("Arial", 9),
            fg="gray"
        )
        self.calib_preview_label.grid(row=self.calibration_start_row + 5, column=0, columnspan=5, padx=5, pady=5, sticky="w")
    
    def on_quantity_change(self, event=None) -> None:
        """Update preview when X/Y quantities change."""
        try:
            x_qty = int(self.x_qty_entry.get().strip()) if self.x_qty_entry.get().strip() else 0
            y_qty = int(self.y_qty_entry.get().strip()) if self.y_qty_entry.get().strip() else 0
            
            if x_qty > 0 and y_qty > 0:
                total_wells = x_qty * y_qty
                self.calib_preview_label.config(
                    text=f"Grid: {x_qty}x{y_qty} = {total_wells} wells. Set all 4 corners to interpolate.",
                    fg="blue"
                )
            else:
                self.calib_preview_label.config(
                    text="Enter X and Y quantities, then set all 4 corners",
                    fg="gray"
                )
        except ValueError:
            self.calib_preview_label.config(
                text="Invalid quantity values",
                fg="red"
            )
    
    def set_corner(self, corner_attr: str) -> None:
        """
        Set corner coordinate from current printer position.
        
        Args:
            corner_attr: Attribute name ('upper_left', 'lower_left', 'upper_right', 'lower_right')
        """
        if self.robocam is None:
            self.status_label.config(text="Printer not initialized", fg="red")
            return
        
        try:
            x = self.robocam.X if self.robocam.X is not None else 0.0
            y = self.robocam.Y if self.robocam.Y is not None else 0.0
            z = self.robocam.Z if self.robocam.Z is not None else 0.0
            
            coord = (x, y, z)
            
            # Store coordinate
            if corner_attr == "upper_left":
                self.upper_left = coord
            elif corner_attr == "lower_left":
                self.lower_left = coord
            elif corner_attr == "upper_right":
                self.upper_right = coord
            elif corner_attr == "lower_right":
                self.lower_right = coord
            
            # Update display
            coord_text = f"X:{x:.2f} Y:{y:.2f} Z:{z:.2f}"
            self.corner_labels[corner_attr].config(text=coord_text, fg="black")
            self.corner_status_labels[corner_attr].config(text="✓", fg="green")
            
            self.status_label.config(text=f"{corner_attr.replace('_', ' ').title()} set", fg="green")
            
            # Try to interpolate if all corners are set
            self.try_interpolate()
            
        except Exception as e:
            self.status_label.config(text=f"Error setting corner: {e}", fg="red")
            print(f"Error setting corner: {e}")
    
    def try_interpolate(self) -> None:
        """Attempt to interpolate well positions if all corners and quantities are set."""
        try:
            x_qty = int(self.x_qty_entry.get().strip()) if self.x_qty_entry.get().strip() else 0
            y_qty = int(self.y_qty_entry.get().strip()) if self.y_qty_entry.get().strip() else 0
            
            if (x_qty > 0 and y_qty > 0 and 
                self.upper_left is not None and 
                self.lower_left is not None and
                self.upper_right is not None and
                self.lower_right is not None):
                
                # Store quantities
                self.x_quantity = x_qty
                self.y_quantity = y_qty
                
                # Generate interpolated positions
                self.interpolated_positions = WellPlatePathGenerator.generate_path(
                    width=x_qty,
                    depth=y_qty,
                    upper_left_loc=self.upper_left,
                    lower_left_loc=self.lower_left,
                    upper_right_loc=self.upper_right,
                    lower_right_loc=self.lower_right
                )
                
                # Generate labels
                self.labels = self.generate_labels(x_qty, y_qty)
                
                # Update preview
                total_wells = len(self.interpolated_positions)
                preview_text = f"✓ Interpolated {total_wells} wells. Labels: {', '.join(self.labels[:5])}..."
                if len(self.labels) > 5:
                    preview_text += f" ({self.labels[-1]})"
                self.calib_preview_label.config(text=preview_text, fg="green")
                
        except Exception as e:
            self.calib_preview_label.config(text=f"Interpolation error: {e}", fg="red")
            print(f"Interpolation error: {e}")
    
    def generate_labels(self, x_qty: int, y_qty: int) -> List[str]:
        """
        Generate well plate labels in format A1, A2, ..., B1, B2, ...
        
        Args:
            x_qty: Number of wells horizontally
            y_qty: Number of wells vertically
            
        Returns:
            List of labels in order matching interpolated positions
        """
        labels = []
        for row in range(y_qty):
            row_letter = chr(ord('A') + row) if row < 26 else f"A{chr(ord('A') + row - 26)}"
            for col in range(x_qty):
                labels.append(f"{row_letter}{col + 1}")
        return labels
    
    def save_calibration(self) -> None:
        """Save calibration to JSON file in calibrations/ directory."""
        # Validate all corners are set
        if (self.upper_left is None or self.lower_left is None or
            self.upper_right is None or self.lower_right is None):
            self.status_label.config(text="Error: All 4 corners must be set", fg="red")
            return
        
        # Validate quantities
        try:
            x_qty = int(self.x_qty_entry.get().strip())
            y_qty = int(self.y_qty_entry.get().strip())
            if x_qty <= 0 or y_qty <= 0:
                raise ValueError("Quantities must be positive")
        except ValueError:
            self.status_label.config(text="Error: Invalid X/Y quantities", fg="red")
            return
        
        # Validate calibration name
        calib_name = self.calib_name_entry.get().strip()
        if not calib_name:
            self.status_label.config(text="Error: Enter calibration name", fg="red")
            return
        
        # Ensure interpolated positions exist
        if not self.interpolated_positions:
            self.try_interpolate()
            if not self.interpolated_positions:
                self.status_label.config(text="Error: Could not interpolate positions", fg="red")
                return
        
        try:
            # Create calibrations directory if it doesn't exist
            calib_dir = "calibrations"
            os.makedirs(calib_dir, exist_ok=True)
            
            # Prepare calibration data
            calib_data = {
                "name": calib_name,
                "upper_left": list(self.upper_left),
                "lower_left": list(self.lower_left),
                "upper_right": list(self.upper_right),
                "lower_right": list(self.lower_right),
                "x_quantity": x_qty,
                "y_quantity": y_qty,
                "interpolated_positions": [list(pos) for pos in self.interpolated_positions],
                "labels": self.labels
            }
            
            # Generate date_time prefix
            date_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save to file with date_time prefix
            calib_file = os.path.join(calib_dir, f"{date_time_str}_{calib_name}.json")
            with open(calib_file, 'w') as f:
                json.dump(calib_data, f, indent=2)
            
            filename = f"{date_time_str}_{calib_name}.json"
            self.status_label.config(
                text=f"Calibration saved: {filename}",
                fg="green"
            )
            self.calib_preview_label.config(
                text=f"✓ Saved {len(self.interpolated_positions)} wells to {filename}",
                fg="green"
            )
            
        except Exception as e:
            self.status_label.config(text=f"Error saving calibration: {e}", fg="red")
            print(f"Error saving calibration: {e}")

    def update_status(self) -> None:
        """
        Update position and FPS display.
        
        Updates position and FPS labels in the tkinter window.
        Camera preview runs natively in a separate window for better performance.
        Schedules next update after 200ms.
        """
        if self.running:
            # Update position display
            self.update_position()
            
            # Update FPS display
            if self._simulate_cam:
                # In camera simulation mode, show "SIM" instead of FPS
                self.fps_label.config(text="SIM")
            elif self.fps_tracker is not None:
                fps = self.fps_tracker.get_fps()
                self.fps_label.config(text=f"{fps:.1f}")
            else:
                self.fps_label.config(text="N/A")
            
            # Schedule next update (200ms = 5 Hz update rate for status)
            self.root.after(200, self.update_status)
    
    def update_position(self) -> None:
        """Update position display with current printer coordinates."""
        if self.robocam is None:
            self.position_label.config(text="N/A, N/A, N/A")
            return
        
        x = self.robocam.X if self.robocam.X is not None else 0.0
        y = self.robocam.Y if self.robocam.Y is not None else 0.0
        z = self.robocam.Z if self.robocam.Z is not None else 0.0
        position = f"{x:.2f}, {y:.2f}, {z:.2f}"
        self.position_label.config(text=position)

    def on_close(self) -> None:
        """
        Handle window close event.
        
        Stops camera, preview widget, sets running flag to False, and destroys window.
        """
        self.running = False
        
        # Stop preview widget
        if self.preview_widget is not None:
            try:
                self.preview_widget.stop()
            except Exception as e:
                print(f"Error stopping preview widget: {e}")
        
        # Cleanup capture manager
        if self.capture_manager is not None:
            try:
                self.capture_manager.cleanup()
            except Exception as e:
                print(f"Error cleaning up capture manager: {e}")
        
        # Stop camera
        try:
            if self.picam2 is not None:
                self.picam2.stop()
        except Exception:
            pass
        
        self.root.destroy()


# Main application
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RoboCam Calibration - Manual positioning and calibration")
    parser.add_argument(
        "--simulate_3d",
        action="store_true",
        help="Run in 3D printer simulation mode (no printer connection, movements are simulated)"
    )
    parser.add_argument(
        "--simulate_cam",
        action="store_true",
        help="Run in camera simulation mode (no camera connection, placeholder image used)"
    )
    args = parser.parse_args()
    
    root = tk.Tk()
    app = CameraApp(root, simulate_3d=args.simulate_3d, simulate_cam=args.simulate_cam)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
