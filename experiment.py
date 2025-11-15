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
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, JpegEncoder
from robocam.robocam_ccc import RoboCam
from robocam.laser import Laser
from robocam.config import get_config
from robocam.logging_config import get_logger

logger = get_logger(__name__)

# Configuration constants
# CSV files are now named with format: {date}_{time}_{exp}_points.csv
EXPERIMENTS_FOLDER: str = "experiments"  # For exported experiment settings (profile JSON files)
OUTPUTS_FOLDER: str = "outputs"  # Base folder for experiment outputs
# Output folder structure: outputs/YYYYMMDD_{experiment_name}/ contains recordings and CSV
DEFAULT_RES: tuple[int, int] = (1920, 1080)
DEFAULT_FPS: float = 30.0
DEFAULT_EXPORT: str = "H264"
DEFAULT_QUALITY: int = 85


def ensure_directory_exists(folder_path: str) -> tuple[bool, str]:
    """
    Ensure a directory path exists, creating all intermediate directories if needed.
    
    Args:
        folder_path: Full path to the directory to create
        
    Returns:
        Tuple of (success: bool, error_message: str)
        If success is False, error_message contains a helpful error description
    """
    try:
        os.makedirs(folder_path, exist_ok=True)
        # Verify we can actually write to the directory
        test_file = os.path.join(folder_path, ".write_test")
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except (PermissionError, OSError):
            return False, f"Directory '{folder_path}' exists but is not writable. Please check permissions."
        return True, ""
    except PermissionError:
        # Check which level failed
        path_parts = folder_path.strip('/').split('/')
        checked_path = '/'
        for part in path_parts:
            checked_path = os.path.join(checked_path, part)
            if not os.path.exists(checked_path):
                error_msg = f"Permission denied: Cannot create '{checked_path}'. "
                error_msg += f"Please create the directory structure manually or run with sudo:\n"
                error_msg += f"  sudo mkdir -p {folder_path} && sudo chmod 777 {folder_path}"
                return False, error_msg
            elif not os.access(checked_path, os.W_OK):
                error_msg = f"Permission denied: '{checked_path}' exists but is not writable. "
                error_msg += f"Please fix permissions with: sudo chmod 777 {checked_path}"
                return False, error_msg
        return False, f"Permission denied: Cannot create '{folder_path}'. Please check permissions."
    except OSError as e:
        return False, f"Error creating directory '{folder_path}': {e}. Please check permissions."


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
    - Setting adjustable GPIO action phases (customizable ON/OFF sequences with durations)
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
        Saves to outputs/YYYYMMDD_{experiment_name}/ with format: {date}_{time}_{exp}_points.csv
        
        Note:
            Only saves if sequence exists. Creates folder if it doesn't exist.
        """
        if not self.seq:
            return
        
        # Get experiment name and create output folder with date prefix
        experiment_name = self.experiment_name_ent.get().strip() or "exp"
        date_str = datetime.now().strftime("%Y%m%d")
        output_folder = os.path.join(OUTPUTS_FOLDER, f"{date_str}_{experiment_name}")
        
        success, error_msg = ensure_directory_exists(output_folder)
        if not success:
            logger.error(error_msg)
            if hasattr(self, 'status_lbl'):
                self.status_lbl.config(text=error_msg, fg="red")
            return
        
        # Generate filename with date, time, and experiment name
        date_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"{date_time_str}_{experiment_name}_points.csv"
        csv_path: str = os.path.join(output_folder, csv_filename)
        
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
        calib_dir = "calibrations"
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

        # GPIO Action Phases section
        tk.Label(w, text="GPIO Action Phases:").grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))
        
        # Frame to contain phase rows
        self.action_phases_frame = tk.Frame(w)
        self.action_phases_frame.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        
        # Initialize with default phase (GPIO OFF, 30 seconds)
        self.action_phases = []
        self.add_action_phase("GPIO OFF", 30.0)
        
        # Add Action button
        tk.Button(w, text="Add Action", command=self.add_action_phase).grid(row=4, column=0, padx=5, pady=5, sticky="w")

        # Pattern, experiment name
        tk.Label(w, text="Pattern:").grid(row=5, column=0)
        self.pattern_var = tk.StringVar(value="raster →↓")
        tk.OptionMenu(w, self.pattern_var, "snake →↙", "raster →↓").grid(row=5, column=1)

        tk.Label(w, text="Experiment Name:").grid(row=6, column=0)
        self.experiment_name_ent = tk.Entry(w, width=40)
        self.experiment_name_ent.insert(0, "exp")
        self.experiment_name_ent.grid(row=6, column=1, columnspan=2, pady=5, sticky="ew")

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

        tk.Label(w, text="Motion Profile:").grid(row=12, column=0)
        self.motion_config_var = tk.StringVar(value="default")
        # Load profiles from motion_config.json
        motion_config_path = os.path.join("config", "motion_config.json")
        profiles = ["default"]
        if os.path.exists(motion_config_path):
            try:
                with open(motion_config_path, 'r') as f:
                    motion_config_data = json.load(f)
                    profiles = list(motion_config_data.keys())
            except Exception as e:
                logger.warning(f"Error loading motion config: {e}")
        motion_config_menu = tk.OptionMenu(w, self.motion_config_var, *profiles)
        motion_config_menu.grid(row=12, column=1, padx=5, pady=5)
        
        # Motion settings display
        tk.Label(w, text="Motion Settings:").grid(row=13, column=0, sticky="w", padx=5, pady=5)
        self.motion_info_label = tk.Label(w, text="Load config to see settings", fg="gray", font=("Arial", 9))
        self.motion_info_label.grid(row=14, column=0, columnspan=2, sticky="w", padx=5)

        # Experiment settings section (similar to calibration)
        tk.Label(w, text="Experiment Settings:").grid(row=16, column=0, sticky="w", padx=5, pady=5)
        self.experiment_settings_var = tk.StringVar(value="")
        exp_settings_frame = tk.Frame(w)
        exp_settings_frame.grid(row=16, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        
        # List available experiment settings
        exp_dir = EXPERIMENTS_FOLDER
        exp_settings = [""]
        if os.path.exists(exp_dir):
            exp_settings.extend([f for f in os.listdir(exp_dir) if f.endswith("_profile.json")])
        
        exp_settings_menu = tk.OptionMenu(exp_settings_frame, self.experiment_settings_var, *exp_settings, command=self.on_experiment_settings_select)
        exp_settings_menu.pack(side=tk.LEFT, padx=5)
        
        tk.Button(exp_settings_frame, text="Refresh", command=self.refresh_experiment_settings).pack(side=tk.LEFT, padx=5)
        tk.Button(exp_settings_frame, text="Export", command=self.export_experiment_settings).pack(side=tk.LEFT, padx=5)
        
        self.experiment_settings_status_label = tk.Label(w, text="No settings loaded", fg="red", font=("Arial", 9))
        self.experiment_settings_status_label.grid(row=16, column=3, sticky="w", padx=5)

        # Status & controls
        tk.Label(w, text="Status:").grid(row=17, column=0, sticky="w")
        self.status_lbl = tk.Label(w, text="Idle")
        self.status_lbl.grid(row=17, column=1, columnspan=2, sticky="w")

        # Recording indicator button (flashing when recording)
        self.recording_btn = tk.Button(w, text="● REC", bg="gray", state="disabled", relief="flat", width=8)
        self.recording_btn.grid(row=17, column=3, padx=5, pady=5)

        self.run_btn = tk.Button(w, text="Run", command=self.start)
        self.run_btn.grid(row=18, column=0, padx=5, pady=5)
        tk.Button(w, text="Pause", command=self.pause).grid(row=18, column=1, padx=5, pady=5)
        tk.Button(w, text="Stop",  command=self.stop).grid(row=18, column=2, padx=5, pady=5)

        # Timers
        tk.Label(w, text="Duration:").grid(row=19, column=0, sticky="e")
        self.duration_lbl = tk.Label(w, text="00:00:00"); self.duration_lbl.grid(row=19, column=1)
        tk.Label(w, text="Elapsed:").grid(row=20, column=0, sticky="e")
        self.elapsed_lbl = tk.Label(w, text="00:00:00");   self.elapsed_lbl.grid(row=20, column=1)
        tk.Label(w, text="Remaining:").grid(row=21, column=0, sticky="e")
        self.remaining_lbl = tk.Label(w, text="00:00:00"); self.remaining_lbl.grid(row=21, column=1)
        
        # Prevent window resizing when entry fields expand
        w.resizable(False, False)
        
        # Load and display motion config on selection change
        def update_motion_info(*args):
            """Update motion settings display when profile changes."""
            try:
                profile_name = self.motion_config_var.get()
                config_path = os.path.join("config", "motion_config.json")
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        motion_config_data = json.load(f)
                    if profile_name in motion_config_data:
                        motion_cfg = motion_config_data[profile_name]
                        prelim = motion_cfg.get("preliminary", {})
                        between = motion_cfg.get("between_wells", {})
                        profile_display = motion_cfg.get("name", profile_name)
                        info = f"{profile_display}: Preliminary: {prelim.get('feedrate', 'N/A')} mm/min, {prelim.get('acceleration', 'N/A')} mm/s² | "
                        info += f"Between Wells: {between.get('feedrate', 'N/A')} mm/min, {between.get('acceleration', 'N/A')} mm/s²"
                        self.motion_info_label.config(text=info, fg="black")
                    else:
                        self.motion_info_label.config(text=f"Profile '{profile_name}' not found", fg="red")
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
            exp_name = self.experiment_name_ent.get().strip() or "exp"
            date_str = datetime.now().strftime("%Y%m%d")
            output_folder = os.path.join(OUTPUTS_FOLDER, f"{date_str}_{exp_name}")
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
                    x0 = "1"
                    y0 = "A"
            else:
                x0 = "1"
                y0 = "A"
            ts     = time.strftime("%H%M%S")
            ds     = date_str  # Use YYYYMMDD format
            fn = f"{ds}_{ts}_{exp_name}_{y0}{x0}{ext}"
            self.status_lbl.config(text=f"Example: {os.path.join(output_folder, fn)}")

        for wgt in (self.experiment_name_ent,
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
        
        calib_dir = "calibrations"
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
    
    def refresh_experiment_settings(self) -> None:
        """Refresh the list of available experiment settings."""
        if not self.window:
            return
        
        exp_dir = EXPERIMENTS_FOLDER
        exp_settings = [""]
        if os.path.exists(exp_dir):
            exp_settings.extend([f for f in os.listdir(exp_dir) if f.endswith("_profile.json")])
        
        # Update the option menu (simplified - just update the variable)
        current = self.experiment_settings_var.get()
        if current not in exp_settings:
            self.experiment_settings_var.set("")
            self.on_experiment_settings_select("")
        else:
            self.experiment_settings_var.set(current)
    
    def on_experiment_settings_select(self, filename: str) -> None:
        """
        Handle experiment settings selection from dropdown.
        
        Args:
            filename: Selected experiment settings filename (empty string if none)
        """
        if not filename or filename == "":
            # No settings selected
            self.experiment_settings_status_label.config(text="No settings loaded", fg="red")
            return
        
        try:
            # Load experiment settings file
            exp_path = os.path.join(EXPERIMENTS_FOLDER, filename)
            if not os.path.exists(exp_path):
                self.experiment_settings_status_label.config(
                    text=f"Error: File not found: {filename}",
                    fg="red"
                )
                return
            
            with open(exp_path, 'r') as f:
                settings = json.load(f)
            
            # Validate calibration file exists
            calib_file = settings.get("calibration_file")
            if not calib_file:
                self.experiment_settings_status_label.config(
                    text="Error: No calibration file reference in settings",
                    fg="red"
                )
                return
            
            calib_path = os.path.join("calibrations", calib_file)
            if not os.path.exists(calib_path):
                self.experiment_settings_status_label.config(
                    text=f"Error: Referenced calibration file '{calib_file}' not found.",
                    fg="red"
                )
                return
            
            # Load calibration
            self.calibration_var.set(calib_file)
            self.on_calibration_select(calib_file)
            
            # Wait a moment for calibration to load
            self.window.update()
            
            if not self.loaded_calibration:
                self.experiment_settings_status_label.config(text="Error: Failed to load calibration", fg="red")
                return
            
            # Restore settings
            selected_wells = settings.get("selected_wells", [])
            for label, var in self.well_checkboxes.items():
                var.set(label in selected_wells)
            
            # Load action phases
            phases_data = settings.get("action_phases", [{"action": "GPIO OFF", "time": 30.0}])
            # Clear all existing phases (remove from end to avoid index issues)
            while len(self.action_phases) > 1:
                self.remove_action_phase(len(self.action_phases) - 1)
            # Update first phase with loaded data
            if self.action_phases and phases_data:
                self.action_phases[0]["action_var"].set(phases_data[0].get("action", "GPIO OFF"))
                self.action_phases[0]["time_ent"].delete(0, tk.END)
                self.action_phases[0]["time_ent"].insert(0, str(phases_data[0].get("time", 30.0)))
            # Add remaining phases
            for phase_dict in phases_data[1:]:
                self.add_action_phase(phase_dict.get("action", "GPIO OFF"), phase_dict.get("time", 0.0))
            
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
            
            # Handle both old format (motion_config_file) and new format (motion_config_profile)
            motion_profile = settings.get("motion_config_profile") or settings.get("motion_config_file", "default")
            # If old format had .json extension, remove it
            if motion_profile.endswith(".json"):
                motion_profile = motion_profile[:-5]  # Remove .json
            self.motion_config_var.set(motion_profile)
            
            # Handle both old format (filename_scheme) and new format (experiment_name)
            experiment_name = settings.get("experiment_name")
            if not experiment_name:
                # Try to extract from old filename_scheme format if present
                old_scheme = settings.get("filename_scheme", "exp_{y}{x}_{time}_{date}")
                # Try to extract exp name from old scheme (default was "exp")
                if "exp" in old_scheme:
                    experiment_name = "exp"
                else:
                    experiment_name = "exp"
            self.experiment_name_ent.delete(0, tk.END)
            self.experiment_name_ent.insert(0, experiment_name)
            
            # Handle both old format (plain "snake"/"raster") and new format (with symbols)
            pattern_setting = settings.get("pattern", "raster →↓")
            if pattern_setting in ["snake", "raster"]:
                # Old format - add symbols
                pattern_setting = "snake →↙" if pattern_setting == "snake" else "raster →↓"
            self.pattern_var.set(pattern_setting)
            
            self.update_run_button_state()
            self.experiment_settings_status_label.config(text=f"Loaded: {filename}", fg="green")
            
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            self.experiment_settings_status_label.config(text=f"Error loading settings: {e}", fg="red")
    
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
            calib_path = os.path.join("calibrations", filename)
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
            # Use ButtonPress-1 which fires earlier, and check modifier state more reliably
            def make_click_handler(lbl, r, c, v, cb):
                def on_button_press(event):
                    # Check if shift or control is pressed
                    # event.state uses bit flags: Shift=0x1 (0x0001), Control=0x4 (0x0004)
                    # On Raspberry Pi (Linux), event.state bit flags are reliable
                    state = event.state
                    has_shift = bool(state & 0x0001)
                    has_control = bool(state & 0x0004)
                    
                    if has_shift or has_control:
                        # Get the state BEFORE tkinter processes the click and toggles the checkbox
                        checkbox_state = v.get()  # True = checked, False = unchecked
                        
                        # Assess row and column states
                        row_state = self.assess_row_state(r)
                        col_state = self.assess_column_state(c)
                        
                        # Temporarily remove the command callback to prevent the toggle
                        original_command = cb.cget('command')
                        cb.config(command=lambda: None)  # Temporarily disable
                        
                        # Determine action based on checkbox state, row state, and column state
                        if has_shift:
                            # Shift-click: operate on row
                            if checkbox_state:  # Checkbox is checked
                                if row_state == "all_checked":
                                    # State: checked, row: all checked, action: unfill row (uncheck all)
                                    self.uncheck_row(r)
                                else:
                                    # State: checked, row: not all checked, action: fill row (check all)
                                    self.check_row(r)
                            else:  # Checkbox is unchecked
                                if row_state == "all_unchecked":
                                    # State: unchecked, row: all unchecked, action: fill row (check all)
                                    self.check_row(r)
                                elif row_state == "some_checked":
                                    # State: unchecked, row: some checked, action: unfill row (uncheck all)
                                    self.uncheck_row(r)
                                else:  # row_state == "all_checked" (shouldn't happen if checkbox is unchecked)
                                    # Edge case: fill row
                                    self.check_row(r)
                        else:  # has_control
                            # Control-click: operate on column
                            if checkbox_state:  # Checkbox is checked
                                if col_state == "all_checked":
                                    # State: checked, column: all checked, action: unfill column (uncheck all)
                                    self.uncheck_column(c)
                                else:
                                    # State: checked, column: not all checked, action: fill column (check all)
                                    self.check_column(c)
                            else:  # Checkbox is unchecked
                                if col_state == "all_unchecked":
                                    # State: unchecked, column: all unchecked, action: fill column (check all)
                                    self.check_column(c)
                                elif col_state == "some_checked":
                                    # State: unchecked, column: some checked, action: unfill column (uncheck all)
                                    self.uncheck_column(c)
                                else:  # col_state == "all_checked" (shouldn't happen if checkbox is unchecked)
                                    # Edge case: fill column
                                    self.check_column(c)
                        
                        # Restore the command callback
                        def restore_command():
                            cb.config(command=original_command)
                            self.update_run_button_state()
                        
                        # Restore after event processing completes
                        self.checkbox_window.after_idle(restore_command)
                        
                        # Prevent the default checkbox toggle since we handled it via row/col action
                        return "break"
                return on_button_press
            
            # Bind to ButtonPress-1 which fires earlier than Button-1 (before checkbox processes click)
            checkbox.bind("<ButtonPress-1>", make_click_handler(label, row, col, var, checkbox), add="+")
        
        # Update instructions
        instructions_frame = tk.Frame(main_frame)
        instructions_frame.pack(fill="x", pady=(10, 0))
        instructions = (
            "Checkbox Controls:\n"
            "• Click: Toggle single well\n"
            "• Shift+Click: Smart fill/unfill row based on state\n"
            "• Ctrl+Click: Smart fill/unfill column based on state\n"
            "• Use buttons above to check/uncheck all"
        )
        instructions_label = tk.Label(instructions_frame, text=instructions, fg="gray", font=("Arial", 8), justify="left")
        instructions_label.pack(anchor="w")
        
        # Force update to get actual widget sizes
        self.checkbox_window.update_idletasks()
        
        # Calculate actual size needed based on widget requirements
        # Get checkbox frame required size (this includes all checkboxes)
        checkbox_frame_width = max(self.checkbox_frame.winfo_reqwidth(), 1)
        checkbox_frame_height = max(self.checkbox_frame.winfo_reqheight(), 1)
        
        # Get sizes of other components
        button_frame_height = max(button_frame.winfo_reqheight(), 1)
        instructions_height = max(instructions_label.winfo_reqheight(), 1)
        
        # Account for padding and margins
        window_padding_x = 20  # Main frame horizontal padding (padx * 2)
        window_padding_y = 20  # Main frame vertical padding (pady * 2)
        frame_spacing = 20  # Space between frames (pady values combined)
        scrollbar_width = 20  # Vertical scrollbar width
        horizontal_scrollbar_height = 20  # Horizontal scrollbar height
        
        # Determine maximum reasonable display size (to avoid windows that are too large)
        max_display_width = 1000  # Maximum width before horizontal scrolling
        max_display_height = 700  # Maximum height before vertical scrolling
        
        # Calculate if scrolling will be needed
        needs_horizontal_scroll = checkbox_frame_width > max_display_width
        needs_vertical_scroll = checkbox_frame_height > max_display_height
        
        # Calculate required window width
        if needs_horizontal_scroll:
            # Use max display width + scrollbar
            required_width = max_display_width + scrollbar_width + window_padding_x * 2
        else:
            # Use actual checkbox width + scrollbar space (always reserve space for scrollbar)
            required_width = checkbox_frame_width + scrollbar_width + window_padding_x * 2
        
        # Calculate required window height
        # Include: button frame + checkbox area (or max) + instructions + all spacing
        checkbox_display_height = min(checkbox_frame_height, max_display_height) if needs_vertical_scroll else checkbox_frame_height
        required_height = (
            button_frame_height +
            checkbox_display_height +
            instructions_height +
            frame_spacing * 3 +  # Space: after buttons, before instructions, plus margins
            window_padding_y * 2
        )
        
        # Add horizontal scrollbar height if needed
        if needs_horizontal_scroll:
            required_height += horizontal_scrollbar_height
        
        # Ensure minimum window size for usability
        min_width = 400
        min_height = 300
        required_width = max(int(required_width), min_width)
        required_height = max(int(required_height), min_height)
        
        # Set window size
        self.checkbox_window.geometry(f"{required_width}x{required_height}")
        
        # Update canvas scroll region after widgets are created and window is sized
        self.checkbox_window.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        
        # Center the window on screen if possible
        try:
            self.checkbox_window.update_idletasks()
            screen_width = self.checkbox_window.winfo_screenwidth()
            screen_height = self.checkbox_window.winfo_screenheight()
            window_width = self.checkbox_window.winfo_width()
            window_height = self.checkbox_window.winfo_height()
            # Center on screen
            x = max(0, (screen_width - window_width) // 2)
            y = max(0, (screen_height - window_height) // 2)
            self.checkbox_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        except:
            pass  # If positioning fails, just use default position
    
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
    
    def uncheck_row(self, row: int) -> None:
        """Uncheck all wells in the specified row."""
        x_qty = self.loaded_calibration.get("x_quantity", 0)
        for label, (r, c) in self.label_to_row_col.items():
            if r == row:
                self.well_checkboxes[label].set(False)
        self.update_run_button_state()
    
    def uncheck_column(self, col: int) -> None:
        """Uncheck all wells in the specified column."""
        for label, (r, c) in self.label_to_row_col.items():
            if c == col:
                self.well_checkboxes[label].set(False)
        self.update_run_button_state()
    
    def assess_row_state(self, row: int) -> str:
        """
        Assess the state of all checkboxes in a row.
        
        Args:
            row: Row number to assess
            
        Returns:
            "all_checked" if all checkboxes in row are checked,
            "all_unchecked" if all checkboxes in row are unchecked,
            "some_checked" if some (but not all) checkboxes are checked
        """
        checked_count = 0
        total_count = 0
        for label, (r, c) in self.label_to_row_col.items():
            if r == row:
                total_count += 1
                if self.well_checkboxes[label].get():
                    checked_count += 1
        
        if checked_count == 0:
            return "all_unchecked"
        elif checked_count == total_count:
            return "all_checked"
        else:
            return "some_checked"
    
    def assess_column_state(self, col: int) -> str:
        """
        Assess the state of all checkboxes in a column.
        
        Args:
            col: Column number to assess
            
        Returns:
            "all_checked" if all checkboxes in column are checked,
            "all_unchecked" if all checkboxes in column are unchecked,
            "some_checked" if some (but not all) checkboxes are checked
        """
        checked_count = 0
        total_count = 0
        for label, (r, c) in self.label_to_row_col.items():
            if c == col:
                total_count += 1
                if self.well_checkboxes[label].get():
                    checked_count += 1
        
        if checked_count == 0:
            return "all_unchecked"
        elif checked_count == total_count:
            return "all_checked"
        else:
            return "some_checked"
    
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
    
    def add_action_phase(self, action: Optional[str] = None, time: Optional[float] = None) -> None:
        """
        Add a new GPIO action phase row to the GUI.
        
        Args:
            action: Action type ("GPIO ON" or "GPIO OFF"). If None, defaults to "GPIO OFF".
            time: Time in seconds. If None, defaults to 0.0.
        """
        if not self.action_phases_frame:
            return
        
        if action is None:
            action = "GPIO OFF"
        if time is None:
            time = 0.0
        
        phase_num = len(self.action_phases) + 1
        
        # Create frame for this phase row
        phase_frame = tk.Frame(self.action_phases_frame)
        phase_frame.grid(row=len(self.action_phases), column=0, sticky="ew", padx=2, pady=2)
        
        # Phase number label
        phase_label = tk.Label(phase_frame, text=f"Phase {phase_num}:")
        phase_label.grid(row=0, column=0, padx=5)
        
        # Action dropdown
        action_var = tk.StringVar(value=action)
        action_menu = tk.OptionMenu(phase_frame, action_var, "GPIO ON", "GPIO OFF")
        action_menu.grid(row=0, column=1, padx=5)
        
        # Time entry
        time_ent = tk.Entry(phase_frame, width=10)
        time_ent.insert(0, str(time))
        time_ent.grid(row=0, column=2, padx=5)
        
        # Delete button (disabled for first phase)
        delete_btn = tk.Button(
            phase_frame, 
            text="Delete", 
            command=lambda: self.remove_action_phase(phase_num - 1),
            state="normal" if phase_num > 1 else "disabled"
        )
        delete_btn.grid(row=0, column=3, padx=5)
        
        # Store phase data
        phase_data = {
            "frame": phase_frame,
            "phase_num": phase_num,
            "phase_label": phase_label,
            "action_var": action_var,
            "time_ent": time_ent,
            "delete_btn": delete_btn
        }
        self.action_phases.append(phase_data)
        
        # Update phase numbers for all phases
        self._update_phase_numbers()
    
    def remove_action_phase(self, index: int) -> None:
        """
        Remove an action phase from the GUI.
        
        Args:
            index: Index of the phase to remove (0-based)
        """
        if index < 0 or index >= len(self.action_phases):
            return
        
        # Cannot remove first phase
        if index == 0:
            return
        
        # Destroy the frame and remove from list
        phase_data = self.action_phases[index]
        phase_data["frame"].destroy()
        self.action_phases.pop(index)
        
        # Update phase numbers
        self._update_phase_numbers()
    
    def _update_phase_numbers(self) -> None:
        """Update phase number labels and delete button states."""
        for i, phase_data in enumerate(self.action_phases):
            phase_data["phase_num"] = i + 1
            # Update label
            phase_data["phase_label"].config(text=f"Phase {i + 1}:")
            # Update delete button state (disabled for first phase)
            phase_data["delete_btn"].config(state="normal" if i > 0 else "disabled")
            # Update delete button command to use correct index
            phase_data["delete_btn"].config(command=lambda idx=i: self.remove_action_phase(idx))
    
    def get_action_phases(self) -> List[Tuple[str, float]]:
        """
        Get list of action phases from GUI.
        
        Returns:
            List of (action, time) tuples where action is "GPIO ON" or "GPIO OFF"
        """
        phases = []
        for phase_data in self.action_phases:
            action = phase_data["action_var"].get()
            try:
                time_val = float(phase_data["time_ent"].get().strip())
                phases.append((action, time_val))
            except ValueError:
                # Invalid time, skip this phase
                continue
        return phases
    
    def validate_action_phases(self) -> Tuple[bool, str]:
        """
        Validate that all action phases have valid times.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.action_phases:
            return False, "At least one action phase is required"
        
        for i, phase_data in enumerate(self.action_phases):
            time_str = phase_data["time_ent"].get().strip()
            if not time_str:
                return False, f"Phase {i + 1} has no time specified"
            try:
                time_val = float(time_str)
                if time_val < 0:
                    return False, f"Phase {i + 1} has negative time"
            except ValueError:
                return False, f"Phase {i + 1} has invalid time: {time_str}"
        
        return True, ""
    
    def export_experiment_settings(self) -> None:
        """Export current experiment settings to JSON file directly to experiments/ folder."""
        if not self.loaded_calibration:
            self.experiment_settings_status_label.config(text="Error: No calibration loaded. Cannot export settings.", fg="red")
            return
        
        # Get selected wells
        selected_wells = [label for label, var in self.well_checkboxes.items() if var.get()]
        if not selected_wells:
            self.experiment_settings_status_label.config(text="Error: No wells selected. Cannot export settings.", fg="red")
            return
        
        try:
            # Get action phases
            phases = self.get_action_phases()
            if not phases:
                raise ValueError("At least one action phase is required")
            
            # Validate phases
            is_valid, error_msg = self.validate_action_phases()
            if not is_valid:
                raise ValueError(error_msg)
            
            # Convert phases to list of dicts for export
            phases_data = [{"action": action, "time": time} for action, time in phases]
            
            settings = {
                "calibration_file": self.calibration_file,
                "selected_wells": selected_wells,
                "action_phases": phases_data,
                "resolution": [int(self.res_x_ent.get().strip()), int(self.res_y_ent.get().strip())],
                "fps": float(self.fps_ent.get().strip()),
                "export_type": self.export_var.get(),
                "quality": int(self.quality_ent.get().strip()),
                "motion_config_profile": self.motion_config_var.get(),
                "experiment_name": self.experiment_name_ent.get().strip(),
                "pattern": self.pattern_var.get()  # Stores format like "snake →↙" or "raster →↓"
            }
            
            # Ensure experiments folder exists
            success, error_msg = ensure_directory_exists(EXPERIMENTS_FOLDER)
            if not success:
                logger.error(error_msg)
                self.experiment_settings_status_label.config(text=error_msg, fg="red")
                return
            
            # Generate filename with date, time, and experiment name
            experiment_name = self.experiment_name_ent.get().strip() or "exp"
            date_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{date_time_str}_{experiment_name}_profile.json"
            filepath = os.path.join(EXPERIMENTS_FOLDER, filename)
            
            with open(filepath, 'w') as f:
                json.dump(settings, f, indent=2)
            
            self.experiment_settings_status_label.config(text=f"Exported: {filename}", fg="green")
            # Refresh the dropdown to include the new file
            self.refresh_experiment_settings()
            # Select the newly exported file
            self.experiment_settings_var.set(filename)
                
        except Exception as e:
            logger.error(f"Error exporting settings: {e}")
            self.experiment_settings_status_label.config(text=f"Error exporting settings: {e}", fg="red")
    

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
            # Get and validate action phases
            phases = self.get_action_phases()
            if not phases:
                logger.error("No action phases configured")
                self.status_lbl.config(text="Error: At least one action phase is required")
                return
            
            is_valid, error_msg = self.validate_action_phases()
            if not is_valid:
                logger.error(f"Invalid action phases: {error_msg}")
                self.status_lbl.config(text=f"Error: {error_msg}")
                return
            
            # Store phases for use in run_loop
            self.action_phases_list = phases
            
            # Get experiment name
            experiment_name = self.experiment_name_ent.get().strip() or "exp"
            
            # Get current date for folder and filename
            date_str = datetime.now().strftime("%Y%m%d")
            
            # Create output folder with date prefix: outputs/YYYYMMDD_experiment/
            output_folder = os.path.join(OUTPUTS_FOLDER, f"{date_str}_{experiment_name}")
            
            # Check directory permissions before parsing other inputs
            success, error_msg = ensure_directory_exists(output_folder)
            if not success:
                logger.error(error_msg)
                self.status_lbl.config(text=error_msg, fg="red")
                return
            
            # Get other settings
            try:
                res_x = int(self.res_x_ent.get().strip())
                res_y = int(self.res_y_ent.get().strip())
                fps = float(self.fps_ent.get().strip())
                export = self.export_var.get()
                quality = int(self.quality_ent.get().strip())
            except Exception as e:
                logger.error(f"Invalid inputs: {e}")
                self.status_lbl.config(text=f"Error: Invalid inputs - {e}")
                return
        except Exception as e:
            # Catch any unexpected errors in the try block above
            logger.error(f"Unexpected error: {e}")
            self.status_lbl.config(text=f"Error: {e}")
            return

        # Load motion configuration
        try:
            profile_name = self.motion_config_var.get()
            config_path = os.path.join("config", "motion_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    motion_config_data = json.load(f)
                if profile_name in motion_config_data:
                    self.motion_config = motion_config_data[profile_name]
                    prelim = self.motion_config.get("preliminary", {})
                    between = self.motion_config.get("between_wells", {})
                    self.preliminary_feedrate = float(prelim.get("feedrate", 3000))
                    self.preliminary_acceleration = float(prelim.get("acceleration", 500))
                    self.between_wells_feedrate = float(between.get("feedrate", 5000))
                    self.between_wells_acceleration = float(between.get("acceleration", 1000))
                else:
                    # Use defaults if profile not found
                    logger.warning(f"Motion profile '{profile_name}' not found, using defaults")
                    self.motion_config = None
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
        # Extract pattern name (handle both old format "snake"/"raster" and new format with symbols)
        if pattern.startswith("snake"):
            pattern = "snake"
        elif pattern.startswith("raster"):
            pattern = "raster"
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
        # Calculate total time from all phases
        phase_total_time = sum(time for _, time in self.action_phases_list)
        self.total_time = len(self.seq) * phase_total_time
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
            # Store date_str and output_folder in closure for use in loop
            loop_date_str = date_str
            loop_output_folder = output_folder
            loop_experiment_name = experiment_name
            
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
                ds   = loop_date_str  # Use YYYYMMDD format (set at start of experiment)
                ext_map = {"H264": ".h264", "MJPEG": ".mjpeg", "JPEG": ".jpeg"}
                ext  = ext_map.get(export, ".jpeg")
                fname = f"{ds}_{ts}_{loop_experiment_name}_{y_lbl}{x_lbl}{ext}"
                path = os.path.join(loop_output_folder, fname)
                
                # Ensure directory exists (should already be created, but double-check)
                success, error_msg = ensure_directory_exists(loop_output_folder)
                if not success:
                    logger.error(error_msg)
                    self.status_lbl.config(text=error_msg, fg="red")
                    self.running = False
                    break

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

                    # Execute all action phases
                    for phase_idx, (action, phase_time) in enumerate(self.action_phases_list, 1):
                        if not self.running:
                            break
                        
                        # Determine GPIO state
                        state = 1 if action == "GPIO ON" else 0
                        self.laser.switch(state)
                        self.laser_on = (state == 1)
                        
                        # Wait for phase duration
                        phase_start = time.time()
                        action_name = "ON" if action == "GPIO ON" else "OFF"
                        self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Recording - {action_name} for {phase_time}s (Phase {phase_idx}/{len(phases)})")
                        while time.time() - phase_start < phase_time and self.running:
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
