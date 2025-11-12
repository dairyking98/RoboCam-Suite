"""
Calibration Application - Manual Positioning and Calibration GUI

Provides a GUI for manually positioning the camera over well plates and
recording coordinates for calibration. Uses native Picamera2 preview for
high-performance camera display and tkinter for control interface.

Author: RoboCam-Suite
"""

import tkinter as tk
from picamera2 import Picamera2
from robocam.robocam_ccc import RoboCam
from robocam.camera_preview import start_best_preview, FPSTracker, has_desktop_session
from robocam.config import get_config

# Preview resolution for camera display
preview_resolution: tuple[int, int] = (1024, 820)  # (640, 480)


class CameraApp:
    """
    Calibration application GUI for manual positioning and coordinate recording.
    
    Provides:
    - Native hardware-accelerated camera preview (separate window)
    - Precise movement controls (0.1mm, 1.0mm, 10.0mm steps)
    - Real-time position display
    - FPS monitoring
    - Home functionality
    
    Attributes:
        root (tk.Tk): Main tkinter window (controls)
        picam2 (Picamera2): Camera instance
        robocam (RoboCam): Printer control instance
        running (bool): Application running state
        step_size (tk.DoubleVar): Current step size selection
        position_label (tk.Label): Current position display
        fps_label (tk.Label): FPS display
        fps_tracker (FPSTracker): FPS tracking instance
        preview_backend (str): Preview backend being used
    """
    
    def __init__(self, root: tk.Tk, preview_backend: str = "auto") -> None:
        """
        Initialize calibration application.
        
        Args:
            root: Tkinter root window
            preview_backend: Preview backend to use ("auto", "drm", "qtgl", "null")
        """
        self.root: tk.Tk = root
        self.root.title("RoboCam Calibration - Controls")

        # Picamera2 setup
        self.picam2: Picamera2 = Picamera2()
        self.picam2_config = self.picam2.create_preview_configuration(
            main={"size": preview_resolution},
            buffer_count=2  # Optimize buffer count
        )
        self.picam2.configure(self.picam2_config)
        
        # Set up FPS tracking
        self.fps_tracker: FPSTracker = FPSTracker()
        
        def frame_callback(request):
            """Callback fired for each camera frame."""
            self.fps_tracker.update()
        
        self.picam2.post_callback = frame_callback
        
        # Start native preview (creates separate window)
        try:
            self.preview_backend: str = start_best_preview(self.picam2, backend=preview_backend)
            self.picam2.start()
            print(f"Camera preview started using {self.preview_backend} backend")
        except Exception as exc:
            # Provide helpful error messages
            hint = []
            if preview_backend == "auto":
                if has_desktop_session():
                    hint.append("Try: --backend qtgl (desktop session detected)")
                else:
                    hint.append("Try: --backend drm (no desktop session detected)")
            hint.append("Diagnostic: libcamera-hello -t 0")
            msg = f"Camera/preview start failed: {exc}"
            if hint:
                msg += " | " + " | ".join(hint)
            raise RuntimeError(msg) from exc

        # UI Elements
        self.create_widgets()

        self.running: bool = True
        # Load config for baudrate
        config = get_config()
        baudrate = config.get("hardware.printer.baudrate", 115200)
        
        # Initialize RoboCam with error handling
        try:
            self.robocam: RoboCam = RoboCam(baudrate=baudrate, config=config)
        except Exception as e:
            error_msg = str(e)
            if "not connected" in error_msg.lower() or "serial port" in error_msg.lower():
                user_msg = "Printer connection failed. Check USB cable and try again."
            else:
                user_msg = f"Initialization error: {error_msg}"
            
            # Show error in a message box
            import tkinter.messagebox as messagebox
            messagebox.showerror("Connection Error", user_msg)
            print(f"RoboCam initialization error: {e}")
            # Continue anyway - user can retry connection later
            self.robocam = None

        # Start updating position and FPS display
        self.update_status()

    def create_widgets(self) -> None:
        """
        Create and layout GUI widgets.
        
        Creates:
        - Step size radio buttons (0.1mm, 1.0mm, 10.0mm)
        - Movement direction buttons (X+, X-, Y+, Y-, Z+, Z-)
        - Position display label
        - FPS display label
        - Home button
        - Preview backend info label
        """
        # Info label about preview window
        info_text = f"Camera preview running in separate window ({self.preview_backend} backend)"
        tk.Label(self.root, text=info_text, font=("Arial", 9), fg="gray").grid(
            row=0, column=0, columnspan=4, padx=10, pady=5
        )

        # Radio buttons for step size
        tk.Label(self.root, text="Step Size:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.step_size = tk.DoubleVar(value=1.0)
        tk.Radiobutton(self.root, text="0.1 mm", variable=self.step_size, value=0.1).grid(row=1, column=1, padx=5)
        tk.Radiobutton(self.root, text="1.0 mm", variable=self.step_size, value=1.0).grid(row=1, column=2, padx=5)
        tk.Radiobutton(self.root, text="10.0 mm", variable=self.step_size, value=10.0).grid(row=1, column=3, padx=5)

        # XYZ movement buttons layout
        tk.Label(self.root, text="Movement Controls:").grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        tk.Button(self.root, text="Y+", command=lambda: self.robocam.move_relative(Y=self.step_size.get()),
                 width=8, height=2).grid(row=3, column=2, padx=2, pady=2)
        tk.Button(self.root, text="X-", command=lambda: self.robocam.move_relative(X=-self.step_size.get()),
                 width=8, height=2).grid(row=4, column=1, padx=2, pady=2)
        tk.Button(self.root, text="X+", command=lambda: self.robocam.move_relative(X=self.step_size.get()),
                 width=8, height=2).grid(row=4, column=3, padx=2, pady=2)
        tk.Button(self.root, text="Y-", command=lambda: self.robocam.move_relative(Y=-self.step_size.get()),
                 width=8, height=2).grid(row=5, column=2, padx=2, pady=2)
        tk.Button(self.root, text="Z-", command=lambda: self.robocam.move_relative(Z=-self.step_size.get()),
                 width=8, height=2).grid(row=3, column=4, padx=2, pady=2)
        tk.Button(self.root, text="Z+", command=lambda: self.robocam.move_relative(Z=self.step_size.get()),
                 width=8, height=2).grid(row=5, column=4, padx=2, pady=2)

        # Position label
        tk.Label(self.root, text="Position (X, Y, Z):").grid(row=6, column=0, sticky="e", padx=5, pady=5)
        self.position_label = tk.Label(self.root, text="0.00, 0.00, 0.00", font=("Courier", 10))
        self.position_label.grid(row=6, column=1, columnspan=2, sticky="w", padx=5)

        # FPS label
        tk.Label(self.root, text="Preview FPS:").grid(row=7, column=0, sticky="e", padx=5, pady=5)
        self.fps_label = tk.Label(self.root, text="0.0", font=("Courier", 10))
        self.fps_label.grid(row=7, column=1, sticky="w", padx=5)

        # Status/Error label
        tk.Label(self.root, text="Status:").grid(row=8, column=0, sticky="e", padx=5, pady=5)
        self.status_label = tk.Label(self.root, text="Ready", fg="green", font=("Arial", 9))
        self.status_label.grid(row=8, column=1, columnspan=2, sticky="w", padx=5)
        
        # Home button
        tk.Button(self.root, text="Home Printer", command=self.home_printer,
                 width=15, height=2, bg="#4CAF50", fg="white").grid(
            row=9, column=0, columnspan=2, padx=10, pady=10
        )
    
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
            if "not connected" in error_msg.lower():
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
            if "not connected" in error_msg.lower():
                user_msg = "Printer not connected. Check USB cable."
            elif "timeout" in error_msg.lower():
                user_msg = "Homing timed out. Check printer connection."
            else:
                user_msg = f"Homing failed: {error_msg}"
            self.status_label.config(text=user_msg, fg="red")
            print(f"Homing error: {e}")
        
        

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
            fps = self.fps_tracker.get_fps()
            self.fps_label.config(text=f"{fps:.1f}")
            
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
        
        Stops camera, sets running flag to False, and destroys window.
        """
        self.running = False
        try:
            self.picam2.stop()
        except Exception:
            pass
        self.root.destroy()


# Main application
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RoboCam Calibration - Manual positioning and calibration")
    parser.add_argument(
        "--backend", 
        default="auto", 
        choices=["auto", "drm", "qtgl", "null"],
        help="Preview backend to use (default: auto)"
    )
    args = parser.parse_args()
    
    root = tk.Tk()
    app = CameraApp(root, preview_backend=args.backend)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
