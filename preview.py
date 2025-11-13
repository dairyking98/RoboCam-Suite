"""
Preview Application - Sequential Well Alignment Preview

Provides a GUI for sequentially previewing well positions for alignment
verification before running experiments. Loads wells from calibration files
or experiment save files and allows sequential navigation through positions.

Author: RoboCam-Suite
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import os
import json
from typing import Optional, List, Tuple, Dict, Any
from picamera2 import Picamera2
from robocam.robocam_ccc import RoboCam
from robocam.camera_preview import start_best_preview, FPSTracker, has_desktop_session
from robocam.config import get_config

# Preview resolution for camera display (will be loaded from config)
default_preview_resolution: tuple[int, int] = (800, 600)


class PreviewApp:
    """
    Preview application GUI for sequential well alignment checking.
    
    Provides:
    - Native hardware-accelerated camera preview (separate window)
    - Sequential navigation through well positions
    - Load wells from calibration files or experiment save files
    - Real-time position display
    - FPS monitoring
    - Home functionality
    
    Attributes:
        root (tk.Tk): Main tkinter window (controls)
        picam2 (Picamera2): Camera instance
        robocam (RoboCam): Printer control instance
        running (bool): Application running state
        position_label (tk.Label): Current position display
        fps_label (tk.Label): FPS display
        fps_tracker (FPSTracker): FPS tracking instance
        preview_backend (str): Preview backend being used
        wells (List[Tuple]): List of (position, label) tuples
        current_index (int): Current well index
        homed (bool): Whether printer has been homed
    """
    
    def __init__(self, root: tk.Tk, preview_backend: str = "auto") -> None:
        """
        Initialize preview application.
        
        Args:
            root: Tkinter root window
            preview_backend: Preview backend to use ("auto", "drm", "qtgl", "null")
        """
        self.root: tk.Tk = root
        self.root.title("RoboCam Preview - Alignment Check")

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
        
        # Start native preview (creates separate window)
        try:
            self.preview_backend: str = start_best_preview(self.picam2, backend=preview_backend)
            self.picam2.start()
            print(f"Camera preview started using {self.preview_backend} backend")
        except Exception as exc:
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
        self.homed: bool = False
        self.wells: List[Tuple[Tuple[float, float, float], str]] = []  # (position, label)
        self.current_index: int = -1
        
        # Load config for baudrate
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
            
            messagebox.showerror("Connection Error", user_msg)
            print(f"RoboCam initialization error: {e}")
            self.robocam = None

        # Start updating position and FPS display
        self.update_status()

    def create_widgets(self) -> None:
        """Create and layout GUI widgets."""
        # Info label about preview window
        info_text = f"Camera preview running in separate window ({self.preview_backend} backend)"
        tk.Label(self.root, text=info_text, font=("Arial", 9), fg="gray").grid(
            row=0, column=0, columnspan=4, padx=10, pady=5
        )

        # Source selection section
        tk.Label(self.root, text="Load Wells From:", font=("Arial", 10, "bold")).grid(
            row=1, column=0, columnspan=4, sticky="w", padx=5, pady=5
        )
        
        source_frame = tk.Frame(self.root)
        source_frame.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky="w")
        
        self.source_type = tk.StringVar(value="calibration")
        tk.Radiobutton(source_frame, text="Calibration File", variable=self.source_type, 
                      value="calibration").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(source_frame, text="Experiment Save File", variable=self.source_type,
                      value="experiment").pack(side=tk.LEFT, padx=5)
        
        tk.Button(source_frame, text="Load", command=self.load_wells,
                 bg="#2196F3", fg="white", width=10).pack(side=tk.LEFT, padx=10)
        
        self.source_status_label = tk.Label(self.root, text="No wells loaded", fg="gray", font=("Arial", 9))
        self.source_status_label.grid(row=3, column=0, columnspan=4, sticky="w", padx=5, pady=2)

        # Separator
        tk.Label(self.root, text="─" * 50, fg="gray").grid(
            row=4, column=0, columnspan=4, padx=5, pady=10
        )

        # Well list section
        tk.Label(self.root, text="Well List:", font=("Arial", 10, "bold")).grid(
            row=5, column=0, columnspan=4, sticky="w", padx=5, pady=5
        )
        
        # Scrollable listbox
        listbox_frame = tk.Frame(self.root)
        listbox_frame.grid(row=6, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")
        
        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.well_listbox = tk.Listbox(listbox_frame, height=10, yscrollcommand=scrollbar.set)
        self.well_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.well_listbox.yview)
        
        self.well_listbox.bind("<<ListboxSelect>>", self.on_well_select)
        
        # Navigation buttons
        nav_frame = tk.Frame(self.root)
        nav_frame.grid(row=7, column=0, columnspan=4, padx=5, pady=5)
        
        tk.Button(nav_frame, text="Home Printer", command=self.home_printer,
                 width=15, height=2, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="Previous", command=self.previous_well,
                 width=12, bg="#FF9800", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="Next", command=self.next_well,
                 width=12, bg="#FF9800", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="Go to Selected", command=self.go_to_selected_well,
                 width=15, bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=5)

        # Position and status display
        tk.Label(self.root, text="Position (X, Y, Z):").grid(row=8, column=0, sticky="e", padx=5, pady=5)
        self.position_label = tk.Label(self.root, text="0.00, 0.00, 0.00", font=("Courier", 10))
        self.position_label.grid(row=8, column=1, columnspan=2, sticky="w", padx=5)

        tk.Label(self.root, text="Current Well:").grid(row=9, column=0, sticky="e", padx=5, pady=5)
        self.current_well_label = tk.Label(self.root, text="None", font=("Courier", 10))
        self.current_well_label.grid(row=9, column=1, sticky="w", padx=5)

        tk.Label(self.root, text="Preview FPS:").grid(row=10, column=0, sticky="e", padx=5, pady=5)
        self.fps_label = tk.Label(self.root, text="0.0", font=("Courier", 10))
        self.fps_label.grid(row=10, column=1, sticky="w", padx=5)

        tk.Label(self.root, text="Status:").grid(row=11, column=0, sticky="e", padx=5, pady=5)
        self.status_label = tk.Label(self.root, text="Ready", fg="green", font=("Arial", 9))
        self.status_label.grid(row=11, column=1, columnspan=2, sticky="w", padx=5)
        
        # Configure grid weights for resizing
        self.root.grid_rowconfigure(6, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

    def load_wells(self) -> None:
        """Load wells from calibration file or experiment save file."""
        source_type = self.source_type.get()
        
        if source_type == "calibration":
            self.load_from_calibration()
        else:
            self.load_from_experiment()

    def load_from_calibration(self) -> None:
        """Load all wells from a calibration file."""
        # List available calibrations
        calib_dir = os.path.join("config", "calibrations")
        if not os.path.exists(calib_dir):
            messagebox.showerror("Error", "Calibrations directory not found: config/calibrations/")
            return
        
        calibrations = [f for f in os.listdir(calib_dir) if f.endswith(".json")]
        if not calibrations:
            messagebox.showerror("Error", "No calibration files found in config/calibrations/")
            return
        
        # Simple selection dialog
        # For now, use file dialog - could be improved with dropdown
        filename = filedialog.askopenfilename(
            initialdir=calib_dir,
            title="Select Calibration File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                calib_data = json.load(f)
            
            # Validate structure
            required_fields = ["interpolated_positions", "labels"]
            if not all(field in calib_data for field in required_fields):
                raise ValueError("Invalid calibration file format")
            
            positions = calib_data.get("interpolated_positions", [])
            labels = calib_data.get("labels", [])
            
            if len(positions) != len(labels):
                raise ValueError("Mismatch between positions and labels count")
            
            # Store wells
            self.wells = [(tuple(pos), label) for pos, label in zip(positions, labels)]
            self.current_index = -1
            
            # Update listbox
            self.well_listbox.delete(0, tk.END)
            for label in labels:
                self.well_listbox.insert(tk.END, label)
            
            self.source_status_label.config(
                text=f"Loaded {len(self.wells)} wells from {os.path.basename(filename)}",
                fg="green"
            )
            self.status_label.config(text=f"Loaded {len(self.wells)} wells", fg="green")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load calibration file: {e}")
            self.source_status_label.config(text="Error loading file", fg="red")

    def load_from_experiment(self) -> None:
        """Load checked wells from an experiment save file."""
        filename = filedialog.askopenfilename(
            title="Select Experiment Save File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                exp_data = json.load(f)
            
            # Extract calibration file and selected wells
            calib_file = exp_data.get("calibration_file")
            selected_wells = exp_data.get("selected_wells", [])
            
            if not calib_file:
                raise ValueError("No calibration_file field in experiment settings")
            
            if not selected_wells:
                raise ValueError("No selected_wells field in experiment settings")
            
            # Load the referenced calibration file
            calib_path = os.path.join("config", "calibrations", calib_file)
            if not os.path.exists(calib_path):
                raise FileNotFoundError(f"Referenced calibration file not found: {calib_file}")
            
            with open(calib_path, 'r') as f:
                calib_data = json.load(f)
            
            # Validate calibration structure
            required_fields = ["interpolated_positions", "labels"]
            if not all(field in calib_data for field in required_fields):
                raise ValueError("Invalid calibration file format")
            
            positions = calib_data.get("interpolated_positions", [])
            labels = calib_data.get("labels", [])
            
            # Create mapping from label to position
            label_to_pos = {}
            for i, label in enumerate(labels):
                if i < len(positions):
                    label_to_pos[label] = tuple(positions[i])
            
            # Filter to only selected wells
            self.wells = []
            for label in selected_wells:
                if label in label_to_pos:
                    self.wells.append((label_to_pos[label], label))
                else:
                    print(f"Warning: Selected well {label} not found in calibration")
            
            if not self.wells:
                raise ValueError("No valid wells found after filtering")
            
            self.current_index = -1
            
            # Update listbox
            self.well_listbox.delete(0, tk.END)
            for _, label in self.wells:
                self.well_listbox.insert(tk.END, label)
            
            self.source_status_label.config(
                text=f"Loaded {len(self.wells)} selected wells from {os.path.basename(filename)}",
                fg="green"
            )
            self.status_label.config(text=f"Loaded {len(self.wells)} wells", fg="green")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load experiment file: {e}")
            self.source_status_label.config(text="Error loading file", fg="red")

    def on_well_select(self, event=None) -> None:
        """Handle well selection in listbox."""
        selection = self.well_listbox.curselection()
        if selection:
            index = selection[0]
            self.current_index = index

    def go_to_selected_well(self) -> None:
        """Move to the currently selected well in the listbox."""
        selection = self.well_listbox.curselection()
        if not selection:
            self.status_label.config(text="No well selected", fg="orange")
            return
        
        index = selection[0]
        self.go_to_well(index)

    def go_to_well(self, index: int) -> None:
        """Move to the well at the specified index."""
        if not self.wells or index < 0 or index >= len(self.wells):
            self.status_label.config(text="Invalid well index", fg="red")
            return
        
        if self.robocam is None:
            self.status_label.config(text="Printer not initialized", fg="red")
            return
        
        if not self.homed:
            self.status_label.config(text="Please home printer first", fg="orange")
            return
        
        position, label = self.wells[index]
        x, y, z = position
        
        try:
            self.status_label.config(text=f"Moving to {label}...", fg="orange")
            self.root.update()
            self.robocam.move_absolute(X=x, Y=y, Z=z)
            self.current_index = index
            self.update_position()
            self.current_well_label.config(text=label)
            self.status_label.config(text=f"At {label}", fg="green")
            
            # Update listbox selection
            self.well_listbox.selection_clear(0, tk.END)
            self.well_listbox.selection_set(index)
            self.well_listbox.see(index)
            
        except Exception as e:
            error_msg = str(e)
            if "not connected" in error_msg.lower():
                user_msg = "Printer not connected. Check USB cable."
            elif "timeout" in error_msg.lower():
                user_msg = "Movement timed out. Check printer connection."
            else:
                user_msg = f"Movement failed: {error_msg}"
            
            self.status_label.config(text=user_msg, fg="red")
            print(f"Go to well error: {e}")

    def next_well(self) -> None:
        """Move to the next well in sequence."""
        if not self.wells:
            self.status_label.config(text="No wells loaded", fg="orange")
            return
        
        if self.current_index < 0:
            next_index = 0
        elif self.current_index >= len(self.wells) - 1:
            next_index = 0  # Wrap around
        else:
            next_index = self.current_index + 1
        
        self.go_to_well(next_index)

    def previous_well(self) -> None:
        """Move to the previous well in sequence."""
        if not self.wells:
            self.status_label.config(text="No wells loaded", fg="orange")
            return
        
        if self.current_index <= 0:
            prev_index = len(self.wells) - 1  # Wrap around
        else:
            prev_index = self.current_index - 1
        
        self.go_to_well(prev_index)

    def home_printer(self) -> None:
        """Home the printer and update position display."""
        if self.robocam is None:
            self.status_label.config(text="Printer not initialized", fg="red")
            return
        
        try:
            self.status_label.config(text="Homing...", fg="orange")
            self.root.update()
            self.robocam.home()
            self.homed = True
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
            self.homed = False
            print(f"Homing error: {e}")

    def update_status(self) -> None:
        """Update position and FPS display."""
        if self.running:
            self.update_position()
            
            fps = self.fps_tracker.get_fps()
            self.fps_label.config(text=f"{fps:.1f}")
            
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
        """Handle window close event."""
        self.running = False
        try:
            self.picam2.stop()
        except Exception:
            pass
        self.root.destroy()


# Main application
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RoboCam Preview - Sequential well alignment check")
    parser.add_argument(
        "--backend", 
        default="auto", 
        choices=["auto", "drm", "qtgl", "null"],
        help="Preview backend to use (default: auto)"
    )
    args = parser.parse_args()
    
    root = tk.Tk()
    app = PreviewApp(root, preview_backend=args.backend)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

