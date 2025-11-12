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
CONFIG_JSON: str = "experiment_config.json"
CSV_NAME: str = "experiment_points.csv"
DEFAULT_SCHEME: str = "exp_{y}{x}_{time}_{date}"
DEFAULT_RES: tuple[int, int] = (640, 512)
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
        # Motion configuration
        self.motion_config: Optional[Dict[str, Any]] = None
        self.preliminary_feedrate: float = 3000.0
        self.preliminary_acceleration: float = 500.0
        self.between_wells_feedrate: float = 5000.0
        self.between_wells_acceleration: float = 1000.0

    def load_config(self) -> Dict[str, Any]:
        """
        Load experiment configuration from JSON file.
        
        Returns:
            Dictionary with configuration values, using defaults if file doesn't exist
            or is invalid.
            
        Note:
            Returns default values if config file is missing or invalid.
        """
        cfg: Dict[str, Any] = {}
        if os.path.exists(CONFIG_JSON):
            try:
                with open(CONFIG_JSON) as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
        return {
            "x_values":        cfg.get("x_values", []),
            "x_labels":        cfg.get("x_labels", []),
            "y_values":        cfg.get("y_values", []),
            "y_labels":        cfg.get("y_labels", []),
            "times":           cfg.get("times", []),
            "z_value":         cfg.get("z_value", ""),
            "pattern":         cfg.get("pattern", "snake"),
            "filename_scheme": cfg.get("filename_scheme", DEFAULT_SCHEME),
            "save_folder":     cfg.get("save_folder", os.path.expanduser("~")),
            "feedrate":        cfg.get("feedrate", "100"),
            "resolution":      cfg.get("resolution", list(DEFAULT_RES)),
            "fps":             cfg.get("fps", DEFAULT_FPS),
            "export_type":     cfg.get("export_type", DEFAULT_EXPORT),
            "quality":         cfg.get("quality", DEFAULT_QUALITY),
            "motion_config_file": cfg.get("motion_config_file", "default.json"),
        }

    def save_config(self) -> None:
        """
        Save current experiment configuration to JSON file.
        
        Note:
            Only saves if window exists. Parses text widgets for list values.
        """
        if not self.window:
            return
            
        def parse_list(widget: tk.Text) -> List[str]:
            """Parse text widget content into list of values."""
            raw = widget.get("1.0", tk.END)
            return [v for v in re.split(r"[\s,]+", raw.strip()) if v]
            
        cfg: Dict[str, Any] = {
            "x_values":        parse_list(self.x_vals),
            "x_labels":        parse_list(self.x_lbls),
            "y_values":        parse_list(self.y_vals),
            "y_labels":        parse_list(self.y_lbls),
            "times":           parse_list(self.times),
            "z_value":         self.z_ent.get().strip(),
            "pattern":         self.pattern_var.get(),
            "filename_scheme": self.scheme_ent.get().strip(),
            "save_folder":     self.folder_ent.get().strip(),
            "feedrate":        self.feedrate_ent.get().strip(),
            "resolution":      [self.res_x_ent.get().strip(), self.res_y_ent.get().strip()],
            "fps":             self.fps_ent.get().strip(),
            "export_type":     self.export_var.get(),
            "quality":         self.quality_ent.get().strip(),
            "motion_config_file": self.motion_config_var.get(),
        }
        with open(CONFIG_JSON, "w") as f:
            json.dump(cfg, f, indent=2)

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
        folder: str = self.folder_ent.get().strip() or os.path.expanduser("~")
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
        """
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        cfg = self.load_config()
        w   = tk.Toplevel(self.parent)
        w.title("Experiment")
        self.window = w

        def on_close():
            self.stop()
            self.save_config()
            self.save_csv()
            w.destroy()
            self.window = None
        w.protocol("WM_DELETE_WINDOW", on_close)

        # X/Y/Times fields
        tk.Label(w, text="X Values (comma/newline):").grid(row=0, column=0)
        self.x_vals = tk.Text(w, height=4, width=30)
        self.x_vals.grid(row=1, column=0, padx=5, pady=5)
        tk.Label(w, text="X Labels:").grid(row=0, column=1)
        self.x_lbls = tk.Text(w, height=4, width=30)
        self.x_lbls.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(w, text="Y Values (comma/newline):").grid(row=2, column=0)
        self.y_vals = tk.Text(w, height=4, width=30)
        self.y_vals.grid(row=3, column=0, padx=5, pady=5)
        tk.Label(w, text="Y Labels:").grid(row=2, column=1)
        self.y_lbls = tk.Text(w, height=4, width=30)
        self.y_lbls.grid(row=3, column=1, padx=5, pady=5)

        tk.Label(w, text="Times (Off,On,Off sec):").grid(row=4, column=0, columnspan=2)
        self.times = tk.Text(w, height=4, width=30)
        self.times.grid(row=5, column=0, columnspan=2, padx=5, pady=5)

        for widget, key in [
            (self.x_vals, "x_values"), (self.x_lbls, "x_labels"),
            (self.y_vals, "y_values"), (self.y_lbls, "y_labels"),
            (self.times,  "times")
        ]:
            for v in cfg[key]:
                widget.insert(tk.END, v + "\n")

        # Z value, pattern, filename, folder
        tk.Label(w, text="Z Value:").grid(row=4, column=2)
        self.z_ent = tk.Entry(w); self.z_ent.grid(row=5, column=2, padx=5)
        self.z_ent.insert(0, cfg["z_value"])

        tk.Label(w, text="Pattern:").grid(row=6, column=0)
        self.pattern_var = tk.StringVar(value=cfg["pattern"])
        tk.OptionMenu(w, self.pattern_var, "snake", "raster").grid(row=6, column=1)

        tk.Label(w, text="Filename Scheme:").grid(row=7, column=0)
        self.scheme_ent = tk.Entry(w, width=40)
        self.scheme_ent.insert(0, cfg["filename_scheme"])
        self.scheme_ent.grid(row=7, column=1, columnspan=2, pady=5)

        tk.Label(w, text="Save Folder:").grid(row=8, column=0)
        self.folder_ent = tk.Entry(w, width=40)
        self.folder_ent.insert(0, cfg["save_folder"])
        self.folder_ent.grid(row=8, column=1)
        tk.Button(w, text="Browse…", command=lambda: (
            self.folder_ent.delete(0, tk.END),
            self.folder_ent.insert(0, filedialog.askdirectory())
        )).grid(row=8, column=2)

        # Resolution, FPS, export, quality, feedrate
        tk.Label(w, text="Resolution X:").grid(row=9, column=0)
        self.res_x_ent = tk.Entry(w); self.res_x_ent.grid(row=9, column=1)
        self.res_x_ent.insert(0, cfg["resolution"][0])

        tk.Label(w, text="Resolution Y:").grid(row=10, column=0)
        self.res_y_ent = tk.Entry(w); self.res_y_ent.grid(row=10, column=1)
        self.res_y_ent.insert(0, cfg["resolution"][1])

        tk.Label(w, text="FPS:").grid(row=11, column=0)
        self.fps_ent = tk.Entry(w); self.fps_ent.grid(row=11, column=1)
        self.fps_ent.insert(0, cfg["fps"])

        tk.Label(w, text="Export Type:").grid(row=12, column=0)
        self.export_var = tk.StringVar(value=cfg["export_type"])
        tk.OptionMenu(w, self.export_var, "H264", "MJPEG", "JPEG").grid(row=12, column=1)

        tk.Label(w, text="JPEG Quality:").grid(row=13, column=0)
        self.quality_ent = tk.Entry(w); self.quality_ent.grid(row=13, column=1)
        self.quality_ent.insert(0, cfg["quality"])

        tk.Label(w, text="Motion Config:").grid(row=14, column=0)
        self.motion_config_var = tk.StringVar(value=cfg.get("motion_config_file", "default.json"))
        # List available motion config files
        motion_configs_dir = os.path.join("config", "motion_configs")
        motion_configs = ["default.json"]
        if os.path.exists(motion_configs_dir):
            motion_configs = [f for f in os.listdir(motion_configs_dir) if f.endswith(".json")]
        motion_config_menu = tk.OptionMenu(w, self.motion_config_var, *motion_configs)
        motion_config_menu.grid(row=14, column=1, padx=5, pady=5)
        
        tk.Label(w, text="Feedrate Override (mm/min, optional):").grid(row=15, column=0)
        self.feedrate_ent = tk.Entry(w); self.feedrate_ent.grid(row=15, column=1)
        self.feedrate_ent.insert(0, cfg["feedrate"])
        
        # Motion settings display
        tk.Label(w, text="Motion Settings:").grid(row=16, column=0, sticky="w", padx=5, pady=5)
        self.motion_info_label = tk.Label(w, text="Load config to see settings", fg="gray", font=("Arial", 9))
        self.motion_info_label.grid(row=17, column=0, columnspan=2, sticky="w", padx=5)

        # Status & controls
        tk.Label(w, text="Status:").grid(row=18, column=0, sticky="w")
        self.status_lbl = tk.Label(w, text="Idle")
        self.status_lbl.grid(row=18, column=1, columnspan=2, sticky="w")

        tk.Button(w, text="Run",   command=self.start).grid(row=19, column=0, padx=5, pady=5)
        tk.Button(w, text="Pause", command=self.pause).grid(row=19, column=1, padx=5, pady=5)
        tk.Button(w, text="Stop",  command=self.stop).grid(row=19, column=2, padx=5, pady=5)

        # Timers
        tk.Label(w, text="Duration:").grid(row=20, column=0, sticky="e")
        self.duration_lbl = tk.Label(w, text="00:00:00"); self.duration_lbl.grid(row=20, column=1)
        tk.Label(w, text="Elapsed:").grid(row=21, column=0, sticky="e")
        self.elapsed_lbl = tk.Label(w, text="00:00:00");   self.elapsed_lbl.grid(row=21, column=1)
        tk.Label(w, text="Remaining:").grid(row=22, column=0, sticky="e")
        self.remaining_lbl = tk.Label(w, text="00:00:00"); self.remaining_lbl.grid(row=22, column=1)
        
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

        # Live example filename
        def upd(e=None):
            fld    = self.folder_ent.get() or os.path.expanduser("~")
            sch    = self.scheme_ent.get() or DEFAULT_SCHEME
            ext_map = {"H264": ".h264", "MJPEG": ".mjpeg", "JPEG": ".jpeg"}
            ext    = ext_map.get(self.export_var.get(), ".h264")
            xl     = [v for v in re.split(r"[\s,]+", self.x_lbls.get("1.0",tk.END).strip()) if v]
            yl     = [v for v in re.split(r"[\s,]+", self.y_lbls.get("1.0",tk.END).strip()) if v]
            x0     = xl[0] if xl else "{x}"
            y0     = yl[0] if yl else "{y}"
            ts     = time.strftime("%H%M%S")
            ds     = time.strftime("%b%-d")
            try:
                fn = sch.format(x=x0, y=y0, time=ts, date=ds) + ext
            except:
                fn = sch + ext
            self.status_lbl.config(text=f"Example: {os.path.join(fld,fn)}")

        for wgt in (self.scheme_ent, self.folder_ent, self.x_lbls, self.y_lbls,
                    self.res_x_ent, self.res_y_ent, self.fps_ent):
            wgt.bind("<KeyRelease>", upd)
        self.export_var.trace_add("write", lambda *a: upd())
        upd()

        w.transient(self.parent)
        w.grab_set()

    def start(self) -> None:
        """
        Start the experiment.
        
        Validates inputs, configures camera, builds well sequence,
        and starts experiment execution in a separate thread.
        
        Note:
            - Parses X, Y values and labels from text widgets
            - Requires 3 timing values (OFF, ON, OFF)
            - Builds sequence based on pattern (snake or raster)
            - Starts recording thread for video/still capture
        """
        if self.running:
            return
        try:
            xs      = [float(v) for v in re.split(r"[\s,]+", self.x_vals.get("1.0",tk.END).strip()) if v]
            ys      = [float(v) for v in re.split(r"[\s,]+", self.y_vals.get("1.0",tk.END).strip()) if v]
            xl      = [v for v in re.split(r"[\s,]+", self.x_lbls.get("1.0",tk.END).strip()) if v]
            yl      = [v for v in re.split(r"[\s,]+", self.y_lbls.get("1.0",tk.END).strip()) if v]
            toks    = [v for v in re.split(r"[\s,]+", self.times.get("1.0",tk.END).strip()) if v]
            if len(toks) != 3:
                logger.error("Invalid times: must provide 3 values (OFF, ON, OFF)")
                self.status_lbl.config(text="Error: Enter 3 times (OFF, ON, OFF)")
                return
            off_t, on_t, off2 = map(float, toks)
            self.feedrate     = float(self.feedrate_ent.get().strip())
            self.z_val        = float(self.z_ent.get().strip())
            folder            = self.folder_ent.get().strip() or os.path.expanduser("~")
            os.makedirs(folder, exist_ok=True)
            scheme            = self.scheme_ent.get().strip() or DEFAULT_SCHEME
            res_x             = int(self.res_x_ent.get().strip())
            res_y             = int(self.res_y_ent.get().strip())
            fps               = float(self.fps_ent.get().strip())
            export            = self.export_var.get()
            quality           = int(self.quality_ent.get().strip())
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

        # build sequence
        pairs = list(zip(xs, xl if xl else [str(v) for v in xs]))
        self.seq = []
        for i, y_val in enumerate(ys):
            row = pairs if (i % 2 == 0) else list(reversed(pairs))
            y_lbl = yl[i] if yl else str(y_val)
            for x_val, x_lbl in row:
                self.seq.append((x_val, y_val, x_lbl, y_lbl))

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
                self.robocam.home()
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
            
            # Use feedrate override if provided, otherwise use between-wells feedrate
            use_feedrate = float(self.feedrate_ent.get().strip()) if self.feedrate_ent.get().strip() else self.between_wells_feedrate
            
            for x_val, y_val, x_lbl, y_lbl in self.seq:
                if not self.running: break
                self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Moving to ({x_val:.2f},{y_val:.2f})")
                try:
                    self.robocam.move_absolute(X=x_val, Y=y_val, Z=self.z_val, speed=use_feedrate)
                    time.sleep(1)
                except Exception as e:
                    self.status_lbl.config(text=f"Error: Movement failed - {e}")
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
                    self.picam2.capture_file(path, format="jpeg") #, q=quality)
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Captured JPEG")
                else:
                    # video (H264 or MJPEG)
                    self.picam2.start_recording(self.encoder, path)
                    self.recording = True

                    # OFF
                    self.laser.switch(0); self.laser_on = False
                    t0 = time.time()
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: OFF for {off_t}s")
                    while time.time() - t0 < off_t and self.running:
                        time.sleep(0.05 if not self.paused else 0.1)

                    # ON
                    self.laser.switch(1); self.laser_on = True
                    t1 = time.time()
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: ON for {on_t}s")
                    while time.time() - t1 < on_t and self.running:
                        time.sleep(0.05 if not self.paused else 0.1)

                    # OFF2
                    self.laser.switch(0); self.laser_on = False
                    t2 = time.time()
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: OFF for {off2}s")
                    while time.time() - t2 < off2 and self.running:
                        time.sleep(0.05 if not self.paused else 0.1)

                    try:
                        self.picam2.stop_recording()
                    except:
                        pass
                    self.recording = False
                    self.status_lbl.config(text=f"Well {y_lbl}{x_lbl}: Done")

            self.running = False

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

if __name__ == "__main__":
    """
    Main entry point for experiment application.
    
    Creates main window with "Open Experiment" button to launch
    experiment configuration and execution interface.
    """
    root: tk.Tk = tk.Tk()
    picam2: Picamera2 = Picamera2()
    # Load config for baudrate
    config = get_config()
    baudrate = config.get("hardware.printer.baudrate", 115200)
    robocam: RoboCam = RoboCam(baudrate=baudrate, config=config)
    app: ExperimentWindow = ExperimentWindow(root, picam2, robocam)
    tk.Button(root, text="Open Experiment", command=app.open).pack(padx=20, pady=20)
    root.mainloop()
