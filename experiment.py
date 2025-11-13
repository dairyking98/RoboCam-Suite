"""
Experiment Automation Application - Automated Well-Plate Experiment Execution

Provides a GUI for configuring and running automated well-plate experiments with:
- Configurable well positions and patterns
- Automated video/still capture at each well
- Laser control with timing sequences (OFF-ON-OFF)
- Motion configuration (feedrate and acceleration)
- CSV export of well coordinates

Author: RoboCam-Suite
"""

import os
import json
import threading
import time
import re
import csv
import tkinter as tk
from tkinter import filedialog
from typing import Optional, Dict, List, Tuple, Any
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, JpegEncoder
from robocam.robocam_ccc import RoboCam
from robocam.laser import Laser
from robocam.config import get_config
from robocam.logging_config import get_logger

logger = get_logger(__name__)

# Configuration constants
CSV_NAME: str = "experiment_points.csv"
DEFAULT_SCHEME: str = "exp_{y}{x}_{time}_{date}"
DEFAULT_RES: tuple[int, int] = (1920, 1080)
DEFAULT_FPS: float = 30.0
DEFAULT_EXPORT: str = "H264"
DEFAULT_QUALITY: int = 85


def format_hms(seconds: float) -> str:
    """
    Format seconds as HH:MM:SS string.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string (e.g., "01:23:45")
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

class ExperimentWindow:
    """
    Experiment automation window for configuring and running well-plate experiments.
    
    Provides GUI for:
    - Configuring well positions (X, Y coordinates and labels)
    - Setting timing sequences (OFF-ON-OFF durations)
    - Camera settings (resolution, FPS, export type, quality)
    - Motion settings (feedrate, motion configuration)
    - File naming and save location
    - Running, pausing, and stopping experiments
    
    Attributes:
        parent (tk.Tk): Parent tkinter window
        picam2 (Picamera2): Camera instance
        robocam (RoboCam): Printer control instance
        laser (Laser): Laser control instance
        window (Optional[tk.Toplevel]): Experiment configuration window
        thread (Optional[threading.Thread]): Experiment execution thread
        running (bool): Experiment running state
        paused (bool): Experiment paused state
        start_ts (float): Experiment start timestamp
        total_time (float): Total experiment duration in seconds
        feedrate (float): Movement speed in mm/min
        laser_on (bool): Laser ON state
        recording (bool): Video recording state
        seq (List[Tuple]): Well sequence list
        z_val (float): Z coordinate (focus height)
    """
    
    def __init__(self, parent: tk.Tk, picam2: Picamera2, robocam: RoboCam) -> None:
        """
        Initialize experiment window.
        
        Args:
            parent: Parent tkinter window
            picam2: Picamera2 instance for video/still capture
            robocam: RoboCam instance for printer control
        """
        self.parent: tk.Tk = parent
        self.picam2: Picamera2 = picam2
        self.robocam: RoboCam = robocam
        # Load config for laser GPIO pin
        config = get_config()
        laser_pin = config.get("hardware.laser.gpio_pin", 21)
        self.laser: Laser = Laser(laser_pin, config)
        self.window: Optional[tk.Toplevel] = None
        self.thread: Optional[threading.Thread] = None
        self.running: bool = False
        self.paused: bool = False
        self.start_ts: float = 0.0
        self.total_time: float = 0.0
        self.feedrate: float = 100.0
        self.laser_on: bool = False
        self.recording: bool = False
        self.seq: List[Tuple[float, float, str, str]] = []
        self.z_val: float = 0.0
        self.recording_flash_state: bool = False
        self.recording_flash_job: Optional[str] = None
        # Motion configuration
        self.motion_config: Optional[Dict[str, Any]] = None
        self.preliminary_feedrate: float = 3000.0
        self.preliminary_acceleration: float = 500.0
        self.between_wells_feedrate: float = 5000.0
        self.between_wells_acceleration: float = 1000.0
        # Calibration data
        self.loaded_calibration: Optional[Dict[str, Any]] = None
        self.calibration_file: Optional[str] = None
        self.well_checkboxes: Dict[str, tk.BooleanVar] = {}
        self.checkbox_frame: Optional[tk.Frame] = None
        self.checkbox_widgets: Dict[str, tk.Checkbutton] = {}
        self.label_to_row_col: Dict[str, Tuple[int, int]] = {}
        self.checkbox_window: Optional[tk.Toplevel] = None
        self.select_cells_btn: Optional[tk.Button] = None


    def save_csv(self) -> None:
        """
        Save well sequence to CSV file.
        
        Creates CSV file with columns: xlabel, ylabel, xval, yval, zval.
        Saves to experiment save folder.
        
        Note:
            Only saves if sequence exists. Creates folder if it doesn't exist.
        """
        if not self.seq:
            return
        folder: str = self.folder_ent.get().strip() or "/output/filescheme/files"
        os.makedirs(folder, exist_ok=True)
        csv_path: str = os.path.join(folder, CSV_NAME)
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["xlabel", "ylabel", "xval", "yval", "zval"])
            for x_val, y_val, x_lbl, y_lbl in self.seq:
                writer.writerow([x_lbl, y_lbl, x_val, y_val, self.z_val])
        self.status_lbl.config(text=f"CSV saved: {os.path.basename(csv_path)}")

    def open(self) -> None:
        """
        Open experiment configuration window.
        
        Creates or raises the experiment configuration window with all
        settings fields. Loads saved configuration if available.
        If called from __main__, uses the root window directly.
        """
        # If window already exists, just raise it
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        # Use root window directly if this is the main window (no existing window and parent is empty)
        # Otherwise create a Toplevel for embedded use
        if (self.window is None and isinstance(self.parent, tk.Tk) and 
            len(self.parent.winfo_children()) == 0):
            w = self.parent
            w.title("Experiment")
            self.window = w
        else:
            w = tk.Toplevel(self.parent)
            w.title("Experiment")
            self.window = w

        def on_close():
            self.stop()
            self.save_csv()
            # Close checkbox window if open
            if self.checkbox_window and self.checkbox_window.winfo_exists():
                self.checkbox_window.destroy()
                self.checkbox_window = None
            if isinstance(w, tk.Toplevel):
                w.destroy()
                self.window = None
            else:
                # If using root window, quit the application
                self.parent.quit()
        w.protocol("WM_DELETE_WINDOW", on_close)

        # Calibration loading section
        tk.Label(w, text="Calibration:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.calibration_var = tk.StringVar(value="")
        calibration_frame = tk.Frame(w)
        calibration_frame.grid(row=0, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        
        # List available calibrations
        calib_dir = os.path.join("config", "calibrations")
        calibrations = [""]
        if os.path.exists(calib_dir):
            calibrations.extend([f for f in os.listdir(calib_dir) if f.endswith(".json")])
        
        calibration_menu = tk.OptionMenu(calibration_frame, self.calibration_var, *calibrations, command=self.on_calibration_select)
        calibration_menu.pack(side=tk.LEFT, padx=5)
        
        tk.Button(calibration_frame, text="Refresh", command=self.refresh_calibrations).pack(side=tk.LEFT, padx=5)
        
        self.calibration_status_label = tk.Label(w, text="No calibration loaded", fg="red", font=("Arial", 9))
        self.calibration_status_label.grid(row=0, column=3, sticky="w", padx=5)
        
        # Select Cells button (shown when calibration loaded)
        self.select_cells_btn = tk.Button(w, text="Select Cells", command=self.open_checkbox_window, state="disabled")
        self.select_cells_btn.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        tk.Label(w, text="Times (Off,On,Off sec):").grid(row=2, column=0, columnspan=2)
        self.times = tk.Text(w, height=4, width=30, wrap=tk.WORD)
        self.times.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        # Initialize times field (empty by default)
        self.times.insert(tk.END, "30, 0, 0\n")

        # Pattern, filename, folder
        tk.Label(w, text="Pattern:").grid(row=4, column=0)
        self.pattern_var = tk.StringVar(value="snake")
        tk.OptionMenu(w, self.pattern_var, "snake", "raster").grid(row=4, column=1)

        tk.Label(w, text="Filename Scheme:").grid(row=5, column=0)
        self.scheme_ent = tk.Entry(w, width=40)
        self.scheme_ent.insert(0, DEFAULT_SCHEME)
        self.scheme_ent.grid(row=5, column=1, columnspan=2, pady=5, sticky="ew")

        tk.Label(w, text="Save Folder:").grid(row=6, column=0)
        self.folder_ent = tk.Entry(w, width=40)
        self.folder_ent.insert(0, "/output/filescheme/files")
        self.folder_ent.grid(row=6, column=1, sticky="ew")
        tk.Button(w, text="Browse…", command=lambda: (
            self.folder_ent.delete(0, tk.END),
            self.folder_ent.insert(0, filedialog.askdirectory())
        )).grid(row=6, column=2)

        # Resolution, FPS, export, quality, feedrate
        tk.Label(w, text="Resolution X:").grid(row=7, column=0)
        self.res_x_ent = tk.Entry(w); self.res_x_ent.grid(row=7, column=1)
        self.res_x_ent.insert(0, str(DEFAULT_RES[0]))

        tk.Label(w, text="Resolution Y:").grid(row=8, column=0)
        self.res_y_ent = tk.Entry(w); self.res_y_ent.grid(row=8, column=1)
        self.res_y_ent.insert(0, str(DEFAULT_RES[1]))

        tk.Label(w, text="FPS:").grid(row=9, column=0)
        self.fps_ent = tk.Entry(w); self.fps_ent.grid(row=9, column=1)
        self.fps_ent.insert(0, str(DEFAULT_FPS))

        tk.Label(w, text="Export Type:").grid(row=10, column=0)
        self.export_var = tk.StringVar(value=DEFAULT_EXPORT)
        tk.OptionMenu(w, self.export_var, "H264", "MJPEG", "JPEG").grid(row=10, column=1)

        tk.Label(w, text="JPEG Quality:").grid(row=11, column=0)
        self.quality_ent = tk.Entry(w); self.quality_ent.grid(row=11, column=1)
        self.quality_ent.insert(0, str(DEFAULT_QUALITY))

        tk.Label(w, text="Motion Config:").grid(row=12, column=0)
        self.motion_config_var = tk.StringVar(value="default.json")
        # List available motion config files
        motion_configs_dir = os.path.join("config", "motion_configs")
        motion_configs = ["default.json"]
        if os.path.exists(motion_configs_dir):
            motion_configs = [f for f in os.listdir(motion_configs_dir) if f.endswith(".json")]
        motion_config_menu = tk.OptionMenu(w, self.motion_config_var, *motion_configs)
        motion_config_menu.grid(row=12, column=1, padx=5, pady=5)
        
        # Motion settings display
        tk.Label(w, text="Motion Settings:").grid(row=13, column=0, sticky="w", padx=5, pady=5)
        self.motion_info_label = tk.Label(w, text="Load config to see settings", fg="gray", font=("Arial", 9))
        self.motion_info_label.grid(row=14, column=0, columnspan=2, sticky="w", padx=5)

        # Experiment settings export/import
        exp_settings_frame = tk.Frame(w)
        exp_settings_frame.grid(row=15, column=0, columnspan=3, padx=5, pady=5)
        tk.Button(exp_settings_frame, text="Export Experiment Settings", command=self.export_experiment_settings).pack(side=tk.LEFT, padx=5)
        tk.Button(exp_settings_frame, text="Load Experiment Settings", command=self.load_experiment_settings).pack(side=tk.LEFT, padx=5)

        # Status & controls
        tk.Label(w, text="Status:").grid(row=16, column=0, sticky="w")
        self.status_lbl = tk.Label(w, text="Idle")
        self.status_lbl.grid(row=16, column=1, columnspan=2, sticky="w")

        # Recording indicator button (flashing when recording)
        self.recording_btn = tk.Button(w, text="● REC", bg="gray", state="disabled", relief="flat", width=8)
        self.recording_btn.grid(row=16, column=3, padx=5, pady=5)

        self.run_btn = tk.Button(w, text="Run", command=self.start)
        self.run_btn.grid(row=17, column=0, padx=5, pady=5)
        tk.Button(w, text="Pause", command=self.pause).grid(row=17, column=1, padx=5, pady=5)
        tk.Button(w, text="Stop",  command=self.stop).grid(row=17, column=2, padx=5, pady=5)

        # Timers
        tk.Label(w, text="Duration:").grid(row=18, column=0, sticky="e")
        self.duration_lbl = tk.Label(w, text="00:00:00"); self.duration_lbl.grid(row=18, column=1)
        tk.Label(w, text="Elapsed:").grid(row=19, column=0, sticky="e")
        self.elapsed_lbl = tk.Label(w, text="00:00:00");   self.elapsed_lbl.grid(row=19, column=1)
        tk.Label(w, text="Remaining:").grid(row=20, column=0, sticky="e")
        self.remaining_lbl = tk.Label(w, text="00:00:00"); self.remaining_lbl.grid(row=20, column=1)
        
        # Prevent window resizing when entry fields expand
        w.resizable(False, False)
        
        # Load and display motion config on selection change
        def update_motion_info(*args):
            """Update motion settings display when config file changes."""
            try:
                config_file = self.motion_config_var.get()
                config_path = os.path.join("config", "motion_configs", config_file)
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        motion_cfg = json.load(f)
                    prelim = motion_cfg.get("preliminary", {})
                    between = motion_cfg.get("between_wells", {})
                    info = f"Preliminary: {prelim.get('feedrate', 'N/A')} mm/min, {prelim.get('acceleration', 'N/A')} mm/s² | "
                    info += f"Between Wells: {between.get('feedrate', 'N/A')} mm/min, {between.get('acceleration', 'N/A')} mm/s²"
                    self.motion_info_label.config(text=info, fg="black")
                else:
                    self.motion_info_label.config(text="Config file not found", fg="red")
            except Exception as e:
                self.motion_info_label.config(text=f"Error loading config: {e}", fg="red")
        
        self.motion_config_var.trace("w", update_motion_info)
        update_motion_info()  # Initial load
        
        # Update run button state based on calibration
        self.update_run_button_state()

        # Live example filename
        def upd(e=None):
            fld    = self.folder_ent.get() or "/output/filescheme/files"
            sch    = self.scheme_ent.get() or DEFAULT_SCHEME
            ext_map = {"H264": ".h264", "MJPEG": ".mjpeg", "JPEG": ".jpeg"}
            ext    = ext_map.get(self.export_var.get(), ".h264")
            # Use calibration labels if available, otherwise use placeholders
            if self.loaded_calibration and self.loaded_calibration.get("labels"):
                labels = self.loaded_calibration.get("labels", [])
                if labels:
                    first_label = labels[0]
                    x0 = first_label[1:] if len(first_label) > 1 else "1"  # Column number
                    y0 = first_label[0] if len(first_label) > 0 else "A"  # Row letter
                else:
                    x0 = "{x}"
                    y0 = "{y}"
            else:
                x0 = "{x}"
                y0 = "{y}"
            ts     = time.strftime("%H%M%S")
            ds     = time.strftime("%b%-d")
            try:
                fn = sch.format(x=x0, y=y0, time=ts, date=ds) + ext
            except:
                fn = sch + ext
            self.status_lbl.config(text=f"Example: {os.path.join(fld,fn)}")

        for wgt in (self.scheme_ent, self.folder_ent,
                    self.res_x_ent, self.res_y_ent, self.fps_ent):
            wgt.bind("<KeyRelease>", upd)
        self.export_var.trace_add("write", lambda *a: upd())
        # Also update when calibration changes
        if hasattr(self, 'calibration_var'):
            self.calibration_var.trace_add("write", lambda *a: upd())
        upd()

        # Only set transient and grab if it's a Toplevel window
        if isinstance(w, tk.Toplevel):
            w.transient(self.parent)
            w.grab_set()
    
    def refresh_calibrations(self) -> None:
        """Refresh the list of available calibrations."""
        if not self.window:
            return
        
        calib_dir = os.path.join("config", "calibrations")
        calibrations = [""]
        if os.path.exists(calib_dir):
            calibrations.extend([f for f in os.listdir(calib_dir) if f.endswith(".json")])
        
        # Update the option menu (simplified - just update the variable)
        current = self.calibration_var.get()
        if current not in calibrations:
            self.calibration_var.set("")
            self.on_calibration_select("")
        else:
            self.calibration_var.set(current)
    
    def on_calibration_select(self, filename: str) -> None:
        """
        Handle calibration selection from dropdown.
        
        Args:
            filename: Selected calibration filename (empty string if none)
        """
        if not filename or filename == "":
            # No calibration selected
            self.loaded_calibration = None
            self.calibration_file = None
            self.calibration_status_label.config(text="No calibration loaded", fg="red")
            # Disable Select Cells button
            if self.select_cells_btn:
                self.select_cells_btn.config(state="disabled")
            # Close checkbox window if open
            if self.checkbox_window and self.checkbox_window.winfo_exists():
                self.checkbox_window.destroy()
                self.checkbox_window = None
            self.update_run_button_state()
            return
        
        try:
            # Load calibration file
            calib_path = os.path.join("config", "calibrations", filename)
            if not os.path.exists(calib_path):
                self.calibration_status_label.config(
                    text=f"Error: File not found: {filename}",
                    fg="red"
                )
                self.loaded_calibration = None
                self.calibration_file = None
                self.update_run_button_state()
                return
            
            with open(calib_path, 'r') as f:
                self.loaded_calibration = json.load(f)
            
            self.calibration_file = filename
            
            # Validate calibration structure
            required_fields = ["interpolated_positions", "labels", "x_quantity", "y_quantity"]
            if not all(field in self.loaded_calibration for field in required_fields):
                raise ValueError("Invalid calibration file format")
            
            # Update status
            num_wells = len(self.loaded_calibration.get("interpolated_positions", []))
            self.calibration_status_label.config(
                text=f"Loaded: {filename} ({num_wells} wells)",
                fg="green"
            )
            
            # Enable Select Cells button
            if self.select_cells_btn:
                self.select_cells_btn.config(state="normal")
            
            # Initialize checkboxes (all checked by default)
            self.initialize_checkboxes()
            
            self.update_run_button_state()
            
        except Exception as e:
            logger.error(f"Error loading calibration: {e}")
            self.calibration_status_label.config(
                text=f"Error loading calibration: {e}",
                fg="red"
            )
            self.loaded_calibration = None
            self.calibration_file = None
            # Disable Select Cells button
            if self.select_cells_btn:
                self.select_cells_btn.config(state="disabled")
            self.update_run_button_state()
    
    def initialize_checkboxes(self) -> None:
        """Initialize checkbox variables for all wells (all checked by default)."""
        if not self.loaded_calibration:
            return
        
        labels = self.loaded_calibration.get("labels", [])
        x_qty = self.loaded_calibration.get("x_quantity", 0)
        
        self.well_checkboxes = {}
        self.label_to_row_col = {}
        
        for i, label in enumerate(labels):
            var = tk.BooleanVar(value=True)  # All checked by default
            self.well_checkboxes[label] = var
            row = i // x_qty
            col = i % x_qty
            self.label_to_row_col[label] = (row, col)
    
    def open_checkbox_window(self) -> None:
        """Open separate window for checkbox selection."""
        if not self.loaded_calibration:
            return
        
        # If window already exists, just raise it
        if self.checkbox_window and self.checkbox_window.winfo_exists():
            self.checkbox_window.lift()
            return
        
        # Disable the button
        if self.select_cells_btn:
            self.select_cells_btn.config(state="disabled")
        
        # Create new window
        self.checkbox_window = tk.Toplevel(self.window if self.window else self.parent)
        self.checkbox_window.title("Select Wells")
        self.checkbox_window.transient(self.window if self.window else self.parent)
        
        def on_close():
            if self.checkbox_window:
                self.checkbox_window.destroy()
                self.checkbox_window = None
            # Re-enable the button
            if self.select_cells_btn:
                self.select_cells_btn.config(state="normal")
            self.update_run_button_state()
        
        self.checkbox_window.protocol("WM_DELETE_WINDOW", on_close)
        
        # Create checkbox grid in the new window
        self.create_checkbox_grid()
    
    def create_checkbox_grid(self) -> None:
        """Create checkbox grid for well selection in separate window."""
        if not self.loaded_calibration or not self.checkbox_window:
            return
        
        # Clear existing checkboxes
        for widget in self.checkbox_window.winfo_children():
            widget.destroy()
        
        self.checkbox_widgets = {}  # Store checkbox widgets for shift/ctrl click
        
        # Create main container frame
        main_frame = tk.Frame(self.checkbox_window, padx=10, pady=10)
        main_frame.pack(fill="both", expand=True)
        
        # Create button frame for check all/uncheck all
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(0, 10))
        
        tk.Button(button_frame, text="Check All", command=self.check_all_wells).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Uncheck All", command=self.uncheck_all_wells).pack(side=tk.LEFT, padx=5)
        
        def close_window():
            if self.checkbox_window:
                self.checkbox_window.destroy()
                self.checkbox_window = None
            # Re-enable the button
            if self.select_cells_btn:
                self.select_cells_btn.config(state="normal")
            self.update_run_button_state()
        
        tk.Button(button_frame, text="Close", command=close_window).pack(side=tk.RIGHT, padx=5)
        
        # Create scrollable frame for checkboxes
        canvas_frame = tk.Frame(main_frame)
        canvas_frame.pack(fill="both", expand=True)
        
        canvas = tk.Canvas(canvas_frame, borderwidth=0)
        scrollbar_v = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollbar_h = tk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        
        self.checkbox_frame = tk.Frame(canvas)
        
        self.checkbox_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.checkbox_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar_v.set, xscrollcommand=scrollbar_h.set)
        
        # Grid layout for canvas and scrollbars
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar_v.grid(row=0, column=1, sticky="ns")
        scrollbar_h.grid(row=1, column=0, sticky="ew")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Get calibration data
        labels = self.loaded_calibration.get("labels", [])
        x_qty = self.loaded_calibration.get("x_quantity", 0)
        
        # Create checkboxes in grid layout
        for i, label in enumerate(labels):
            if label not in self.well_checkboxes:
                # Initialize if not already done
                var = tk.BooleanVar(value=True)
                self.well_checkboxes[label] = var
            else:
                var = self.well_checkboxes[label]
            
            row = i // x_qty
            col = i % x_qty
            
            # Create checkbox with custom click handler
            checkbox = tk.Checkbutton(
                self.checkbox_frame,
                text=label,
                variable=var,
                width=4,
                command=self.update_run_button_state  # Update state when toggled
            )
            checkbox.grid(row=row, column=col, padx=2, pady=2, sticky="w")
            self.checkbox_widgets[label] = checkbox
            
            # Bind shift-click and control-click
            def make_click_handler(lbl, r, c, v):
                def on_click(event):
                    # Check if shift or control is pressed
                    # Note: event.state uses bit flags: Shift=0x1, Control=0x4
                    if event.state & 0x1:  # Shift key pressed
                        # Prevent default toggle by toggling back, then check all in row
                        v.set(not v.get())  # Undo the default toggle
                        self.check_row(r)
                        return "break"  # Prevent further event propagation
                    elif event.state & 0x4:  # Control key pressed
                        # Prevent default toggle by toggling back, then check all in column
                        v.set(not v.get())  # Undo the default toggle
                        self.check_column(c)
                        return "break"  # Prevent further event propagation
                return on_click
            
            checkbox.bind("<Button-1>", make_click_handler(label, row, col, var), add="+")
        
        # Update instructions
        instructions_frame = tk.Frame(main_frame)
        instructions_frame.pack(fill="x", pady=(10, 0))
        instructions = (
            "Checkbox Controls:\n"
            "• Click: Toggle single well\n"
            "• Shift+Click: Check all in same row\n"
            "• Ctrl+Click: Check all in same column\n"
            "• Use buttons above to check/uncheck all"
        )
        tk.Label(instructions_frame, text=instructions, fg="gray", font=("Arial", 8), justify="left").pack(anchor="w")
        
        # Set window size to show all checkboxes (with some padding)
        # Calculate approximate size needed
        num_cols = x_qty
        num_rows = (len(labels) + x_qty - 1) // x_qty if x_qty > 0 else 1
        
        # Estimate checkbox size (approximately 50x25 pixels each)
        checkbox_width = 50
        checkbox_height = 25
        padding = 50
        
        window_width = min(num_cols * checkbox_width + padding + 20, 800)  # Max 800px wide
        window_height = min(num_rows * checkbox_height + padding + 150, 600)  # Max 600px tall
        
        self.checkbox_window.geometry(f"{window_width}x{window_height}")
        
        # Update canvas scroll region after widgets are created
        self.checkbox_window.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
    
    def check_all_wells(self) -> None:
        """Check all wells."""
        for var in self.well_checkboxes.values():
            var.set(True)
        self.update_run_button_state()
    
    def uncheck_all_wells(self) -> None:
        """Uncheck all wells."""
        for var in self.well_checkboxes.values():
            var.set(False)
        self.update_run_button_state()
    
    def check_row(self, row: int) -> None:
        """Check all wells in the specified row."""
        x_qty = self.loaded_calibration.get("x_quantity", 0)
        for label, (r, c) in self.label_to_row_col.items():
            if r == row:
                self.well_checkboxes[label].set(True)
        self.update_run_button_state()
    
    def check_column(self, col: int) -> None:
        """Check all wells in the specified column."""
        for label, (r, c) in self.label_to_row_col.items():
            if c == col:
                self.well_checkboxes[label].set(True)
        self.update_run_button_state()
    
    def update_run_button_state(self) -> None:
        """Update Run button state based on calibration and well selection."""
        if not self.window:
            return
        
        if not self.loaded_calibration:
            self.run_btn.config(state="disabled")
            if hasattr(self, 'status_lbl'):
                self.status_lbl.config(text="No calibration loaded. Please load a calibration first.")
            return
        
        # Check if at least one well is selected
        selected_wells = [label for label, var in self.well_checkboxes.items() if var.get()]
        if not selected_wells:
            self.run_btn.config(state="disabled")
            if hasattr(self, 'status_lbl'):
                self.status_lbl.config(text="No wells selected. Select at least one well.")
            return
        
        # Enable run button
        self.run_btn.config(state="normal")
        if hasattr(self, 'status_lbl'):
            self.status_lbl.config(text=f"Ready - {len(selected_wells)} wells selected")
    
    def export_experiment_settings(self) -> None:
        """Export current experiment settings to JSON file."""
        if not self.loaded_calibration:
            self.status_lbl.config(text="Error: No calibration loaded. Cannot export settings.", fg="red")
            return
        
        # Get selected wells
        selected_wells = [label for label, var in self.well_checkboxes.items() if var.get()]
        if not selected_wells:
            self.status_lbl.config(text="Error: No wells selected. Cannot export settings.", fg="red")
            return
        
        try:
            # Get all settings
            times_str = self.times.get("1.0", tk.END).strip()
            times_list = [v for v in re.split(r"[\s,]+", times_str) if v]
            if len(times_list) != 3:
                raise ValueError("Invalid times: must provide 3 values (OFF, ON, OFF)")
            
            settings = {
                "calibration_file": self.calibration_file,
                "selected_wells": selected_wells,
                "times": [float(t) for t in times_list],
                "resolution": [int(self.res_x_ent.get().strip()), int(self.res_y_ent.get().strip())],
                "fps": float(self.fps_ent.get().strip()),
                "export_type": self.export_var.get(),
                "quality": int(self.quality_ent.get().strip()),
                "motion_config_file": self.motion_config_var.get(),
                "filename_scheme": self.scheme_ent.get().strip(),
                "save_folder": self.folder_ent.get().strip(),
                "pattern": self.pattern_var.get()
            }
            
            # Ask user for save location
            filename = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                title="Export Experiment Settings"
            )
            
            if filename:
                with open(filename, 'w') as f:
                    json.dump(settings, f, indent=2)
                self.status_lbl.config(text=f"Settings exported to {os.path.basename(filename)}", fg="green")
                
        except Exception as e:
            logger.error(f"Error exporting settings: {e}")
            self.status_lbl.config(text=f"Error exporting settings: {e}", fg="red")
    
    def load_experiment_settings(self) -> None:
        """Load experiment settings from JSON file with calibration validation."""
        try:
            # Ask user for file
            filename = filedialog.askopenfilename(
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                title="Load Experiment Settings"
            )
            
            if not filename:
                return
            
            with open(filename, 'r') as f:
                settings = json.load(f)
            
            # Validate calibration file exists
            calib_file = settings.get("calibration_file")
            if not calib_file:
                self.status_lbl.config(text="Error: No calibration file reference in settings", fg="red")
                return
            
            calib_path = os.path.join("config", "calibrations", calib_file)
            if not os.path.exists(calib_path):
                self.status_lbl.config(
                    text=f"Error: Referenced calibration file '{calib_file}' not found. Please ensure calibration exists.",
                    fg="red"
                )
                return
            
            # Load calibration
            self.calibration_var.set(calib_file)
            self.on_calibration_select(calib_file)
            
            # Wait a moment for calibration to load
            self.window.update()
            
            if not self.loaded_calibration:
                self.status_lbl.config(text="Error: Failed to load calibration", fg="red")
                return
            
            # Restore settings
            selected_wells = settings.get("selected_wells", [])
            for label, var in self.well_checkboxes.items():
                var.set(label in selected_wells)
            
            times = settings.get("times", [30, 0, 0])
            self.times.delete("1.0", tk.END)
            self.times.insert("1.0", f"{times[0]}, {times[1]}, {times[2]}")
            
            resolution = settings.get("resolution", list(DEFAULT_RES))
            self.res_x_ent.delete(0, tk.END)
            self.res_x_ent.insert(0, str(resolution[0]))
            self.res_y_ent.delete(0, tk.END)
            self.res_y_ent.insert(0, str(resolution[1]))
            
            self.fps_ent.delete(0, tk.END)
            self.fps_ent.insert(0, str(settings.get("fps", 30.0)))
            
            self.export_var.set(settings.get("export_type", "H264"))
            self.quality_ent.delete(0, tk.END)
            self.quality_ent.insert(0, str(settings.get("quality", 85)))
            
            self.motion_config_var.set(settings.get("motion_config_file", "default.json"))
            
            self.scheme_ent.delete(0, tk.END)
            self.scheme_ent.insert(0, settings.get("filename_scheme", DEFAULT_SCHEME))
            
            self.folder_ent.delete(0, tk.END)
            self.folder_ent.insert(0, settings.get("save_folder", "/output/filescheme/files"))
            
            self.pattern_var.set(settings.get("pattern", "snake"))
            
            self.update_run_button_state()
            self.status_lbl.config(text=f"Settings loaded from {os.path.basename(filename)}", fg="green")
            
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            self.status_lbl.config(text=f"Error loading settings: {e}", fg="red")

    def start(self) -> None:
        """
        Start the experiment.
        
        Validates inputs, configures camera, builds well sequence,
        and starts experiment execution in a separate thread.
        
        Note:
            - Requires calibration to be loaded (blocking)
            - Builds sequence from selected checkboxes
            - Uses interpolated positions from calibration
            - Requires 3 timing values (OFF, ON, OFF)
            - Builds sequence based on pattern (snake or raster)
            - Starts recording thread for video/still capture
        """
        if self.running:
            return
        
        # Validate calibration is loaded (blocking)
        if not self.loaded_calibration:
            logger.error("No calibration loaded")
            self.status_lbl.config(text="Error: No calibration loaded. Please load a calibration first.", fg="red")
            return
        
        # Get selected wells
        selected_wells = [label for label, var in self.well_checkboxes.items() if var.get()]
        if not selected_wells:
            logger.error("No wells selected")
            self.status_lbl.config(text="Error: No wells selected. Select at least one well.", fg="red")
            return
        
        try:
            # Parse timing
            toks = [v for v in re.split(r"[\s,]+", self.times.get("1.0",tk.END).strip()) if v]
            if len(toks) != 3:
                logger.error("Invalid times: must provide 3 values (OFF, ON, OFF)")
                self.status_lbl.config(text="Error: Enter 3 times (OFF, ON, OFF)")
                return
            off_t, on_t, off2 = map(float, toks)
            
            # Get other settings
            folder = self.folder_ent.get().strip() or "/output/filescheme/files"
            os.makedirs(folder, exist_ok=True)
            scheme = self.scheme_ent.get().strip() or DEFAULT_SCHEME
            res_x = int(self.res_x_ent.get().strip())
            res_y = int(self.res_y_ent.get().strip())
            fps = float(self.fps_ent.get().strip())
            export = self.export_var.get()
            quality = int(self.quality_ent.get().strip())
        except Exception as e:
            logger.error(f"Invalid inputs: {e}")
            self.status_lbl.config(text=f"Error: Invalid inputs - {e}")
            return

        # Load motion configuration
        try:
            config_file = self.motion_config_var.get()
            config_path = os.path.join("config", "motion_configs", config_file)
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    self.motion_config = json.load(f)
                prelim = self.motion_config.get("preliminary", {})
                between = self.motion_config.get("between_wells", {})
                self.preliminary_feedrate = float(prelim.get("feedrate", 3000))
                self.preliminary_acceleration = float(prelim.get("acceleration", 500))
                self.between_wells_feedrate = float(between.get("feedrate", 5000))
                self.between_wells_acceleration = float(between.get("acceleration", 1000))
            else:
                # Use defaults if file not found
                logger.warning(f"Motion config file not found: {config_path}, using defaults")
                self.motion_config = None
        except Exception as e:
            logger.error(f"Error loading motion config: {e}, using defaults")
            self.motion_config = None

        # Create separate configurations for preview and recording
        # Preview: Lower resolution for GUI display (if needed)
        # Recording: Full resolution optimized for capture FPS
        preview_config = self.picam2.create_preview_configuration(
            main={'size': (640, 480)},  # Lower resolution for preview
            buffer_count=2
        )
        
        # Recording configuration optimized for maximum FPS
        video_config = self.picam2.create_video_configuration(
            main={'size': (res_x, res_y)},
            controls={'FrameRate': fps},
            buffer_count=2  # Optimize buffer for recording
        )
        
        # Configure for recording (preview not needed during experiment)
        self.picam2.stop()
        self.picam2.configure(video_config)
        self.picam2.start()
        
        logger.info(f"Camera configured for recording: {res_x}x{res_y} @ {fps} FPS")

        # select encoder for video modes
        if export == "MJPEG":
            self.encoder = JpegEncoder(q=quality)
        elif export == "H264":
            self.encoder = H264Encoder(bitrate=50_000_000)
        else:
            self.encoder = None  # JPEG still mode

        # Build sequence from calibration and selected wells
        interpolated_positions = self.loaded_calibration.get("interpolated_positions", [])
        labels = self.loaded_calibration.get("labels", [])
        
        # Create mapping from label to position
        label_to_pos = {}
        for i, label in enumerate(labels):
            if i < len(interpolated_positions):
                label_to_pos[label] = interpolated_positions[i]
        
        # Build sequence from selected wells
        selected_positions = []
        for label in selected_wells:
            if label in label_to_pos:
                pos = label_to_pos[label]
                # Extract row and column from label (e.g., "A1" -> row=0, col=0)
                row_letter = label[0]
                col_num = int(label[1:]) - 1
                row_num = ord(row_letter) - ord('A')
                selected_positions.append((pos[0], pos[1], pos[2], label, row_num, col_num))
        
        # Sort by pattern
        pattern = self.pattern_var.get()
        if pattern == "snake":
            # Snake pattern: alternate row direction
            selected_positions.sort(key=lambda x: (x[4], x[5] if x[4] % 2 == 0 else -x[5]))
        else:  # raster
            # Raster pattern: consistent direction
            selected_positions.sort(key=lambda x: (x[4], x[5]))
        
        # Build final sequence: (x, y, x_label, y_label)
        # Extract x_label and y_label from combined label
        self.seq = []
        for x, y, z, label, row_num, col_num in selected_positions:
            # Split label into row and column parts
            x_lbl = str(col_num + 1)  # Column number (1-based)
            y_lbl = label[0]  # Row letter
            self.seq.append((x, y, x_lbl, y_lbl))
        
        # Use Z from first position (all should be similar from interpolation)
        if selected_positions:
            self.z_val = selected_positions[0][2]  # Z from first position

        self.save_csv()
        self.total_time = len(self.seq) * (off_t + on_t + off2)
        self.duration_lbl.config(text=format_hms(self.total_time))
        self.start_ts, self.running, self.paused = time.time(), True, False

        def update_timers():
            if not self.running: return
            elapsed   = time.time() - self.start_ts
            remaining = max(0, self.total_time - elapsed)
            self.elapsed_lbl.config(text=format_hms(elapsed))
            self.remaining_lbl.config(text=format_hms(remaining))
            self.parent.after(200, update_timers)
        update_timers()

        def run_loop():
            # Apply preliminary motion settings before homing
            try:
                self.robocam.set_acceleration(self.preliminary_acceleration)
                logger.info(f"Applied preliminary acceleration: {self.preliminary_acceleration} mm/s²")
            except Exception as e:
                logger.warning(f"Could not set preliminary acceleration: {e}")
            
            try:
                self.status_lbl.config(text="Homing printer...")
                self.robocam.home()
                self.status_lbl.config(text="Homing complete")
            except Exception as e:
                logger.error(f"Homing failed: {e}")
                self.status_lbl.config(text=f"Error: Homing failed - {e}")
                self.running = False
                return
            
            # Apply between-wells motion settings for well movements
            try:
                self.robocam.set_acceleration(self.between_wells_acceleration)
                logger.info(f"Applied between-wells acceleration: {self.between_wells_acceleration} mm/s²")
            except Exception as e:
                logger.warning(f"Could not set between-wells acceleration: {e}")
            
            # Use between-wells feedrate from motion config
            use_feedrate = self.between_wells_feedrate
            
            for x_val, y_val, x_lbl, y_lbl in self.seq:
                if not self.running: break
                self.status_lbl.config(text=f"Moving to well {y_lbl}{x_lbl} at ({x_val:.2f}, {y_val:.2f})")
                try:
                    # Use Z value from calibration (stored in self.z_val)
                    self.robocam.move_absolute(X=x_val, Y=y_val, Z=self.z_val, speed=use_feedrate)
                    time.sleep(1)
                except Exception as e:
                    self.status_lbl.config(text=f"Error: Movement to {y_lbl}{x_lbl} failed - {e}")
                    self.running = False
                    break

                ts   = time.strftime("%H%M%S")
                ds   = time.strftime("%b%-d")
                ext_map = {"H264": ".h264", "MJPEG": ".mjpeg", "JPEG": ".jpeg"}
                ext  = ext_map.get(export, ".jpeg")
                fname= scheme.format(x=x_lbl, y=y_lbl, time=ts, date=ds) + ext
                path = os.path.join(folder, fname)
                
                os.makedirs(os.path.dirname(path), exist_ok=True)

                if export == "JPEG":
                    # single JPEG still
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Capturing JPEG...")
                    self.picam2.capture_file(path, format="jpeg") #, q=quality)
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: JPEG captured")
                else:
                    # video (H264 or MJPEG)
                    self.picam2.start_recording(self.encoder, path)
                    self.recording = True
                    self.start_recording_flash()

                    # OFF
                    self.laser.switch(0); self.laser_on = False
                    t0 = time.time()
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Recording - OFF for {off_t}s")
                    while time.time() - t0 < off_t and self.running:
                        time.sleep(0.05 if not self.paused else 0.1)

                    # ON
                    self.laser.switch(1); self.laser_on = True
                    t1 = time.time()
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Recording - ON for {on_t}s")
                    while time.time() - t1 < on_t and self.running:
                        time.sleep(0.05 if not self.paused else 0.1)

                    # OFF2
                    self.laser.switch(0); self.laser_on = False
                    t2 = time.time()
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Recording - OFF for {off2}s")
                    while time.time() - t2 < off2 and self.running:
                        time.sleep(0.05 if not self.paused else 0.1)

                    try:
                        self.picam2.stop_recording()
                    except:
                        pass
                    self.recording = False
                    self.stop_recording_flash()
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Done")

            self.running = False
            if self.recording:
                self.stop_recording_flash()
            self.status_lbl.config(text="Experiment completed")

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

    def pause(self) -> None:
        """
        Pause or resume the experiment.
        
        Toggles pause state. When paused, movement and recording continue
        but timing loops wait longer between checks.
        """
        if self.running:
            self.paused = not self.paused

    def start_recording_flash(self) -> None:
        """Start flashing the recording button."""
        if not hasattr(self, 'recording_btn'):
            return
        self.recording_btn.config(state="normal", bg="red", text="● REC")
        self.recording_flash_state = True
        self.flash_recording_button()
    
    def stop_recording_flash(self) -> None:
        """Stop flashing the recording button."""
        if not hasattr(self, 'recording_btn'):
            return
        self.recording_flash_state = False
        if self.recording_flash_job:
            self.parent.after_cancel(self.recording_flash_job)
            self.recording_flash_job = None
        self.recording_btn.config(state="disabled", bg="gray", text="● REC")
    
    def flash_recording_button(self) -> None:
        """Flash the recording button between red and dark red."""
        if not self.recording_flash_state or not hasattr(self, 'recording_btn'):
            return
        if self.recording_btn.cget("bg") == "red":
            self.recording_btn.config(bg="darkred")
        else:
            self.recording_btn.config(bg="red")
        self.recording_flash_job = self.parent.after(500, self.flash_recording_button)
    
    def stop(self) -> None:
        """
        Stop the experiment.
        
        Stops experiment execution, turns off laser, and stops recording.
        Safe to call even if experiment is not running.
        """
        self.running = False
        if self.laser_on:
            try:
                self.laser.switch(0)
            except Exception:
                pass
            self.laser_on = False
        if self.recording:
            try:
                self.picam2.stop_recording()
            except Exception:
                pass
            self.recording = False
            self.stop_recording_flash()

if __name__ == "__main__":
    """
    Main entry point for experiment application.
    
    Opens the experiment configuration and execution interface directly.
    """
    root: tk.Tk = tk.Tk()
    picam2: Picamera2 = Picamera2()
    # Load config for baudrate
    config = get_config()
    baudrate = config.get("hardware.printer.baudrate", 115200)
    robocam: RoboCam = RoboCam(baudrate=baudrate, config=config)
    app: ExperimentWindow = ExperimentWindow(root, picam2, robocam)
    app.open()  # Open experiment window directly
    root.mainloop()
