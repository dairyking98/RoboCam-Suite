# RoboCam-Suite

Robotic microscopy system for automated well-plate experiments using a 3D printer as a positioning stage, Raspberry Pi camera for imaging, and GPIO-controlled laser for stimulation.

## Overview

RoboCam-Suite is a scientific experiment automation system designed for well-plate microscopy experiments. It provides precise robotic positioning, automated video/still capture, and laser control for biological experiments. The system consists of two main applications:

- **calibrate.py**: Manual positioning and calibration GUI for setting up well-plate coordinates
- **experiment.py**: Automated experiment execution GUI with configurable timing sequences

## Features

- **Automated Well-Plate Scanning**: Navigate to multiple well positions automatically
- **High-Performance Camera Preview**: Native hardware-accelerated preview (DRM/QTGL) with FPS tracking
- **4-Corner Path Calibration**: Guided calibration procedure to account for angled well plates with automatic interpolation
- **Video/Still Capture**: Record videos or capture still images at each well
- **Laser Control**: GPIO-controlled laser with configurable timing sequences (OFF-ON-OFF)
- **Configurable Experiments**: JSON-based configuration for experiment parameters
- **Motion Configuration**: Separate feedrate and acceleration settings for preliminary and between-wells movements
- **Calibration-Based Experiments**: Load calibrations and select wells via checkbox grid
- **Experiment Settings Export/Import**: Save and load experiment configurations with calibration validation
- **CSV Export**: Export well coordinates and labels for analysis

## Hardware Requirements

**Note: This software is designed for Raspberry Pi only and requires Raspberry Pi hardware.**

- **Raspberry Pi** (with Raspberry Pi OS)
- **Raspberry Pi Camera Module** (Picamera2 compatible)
- **3D Printer** (modified as positioning stage, G-code compatible)
- **GPIO Laser Module** (connected to GPIO pin, default: GPIO 21)
- **USB Serial Connection** to 3D printer (default baudrate: 115200)

## Software Requirements

**Note: This software requires Raspberry Pi OS and cannot run on Windows or macOS.**

- Python 3.7 or higher
- Raspberry Pi OS (required - not compatible with Windows/macOS)
- Required Python packages (see `requirements.txt`)
- RPi.GPIO library (installed via system package manager on Raspberry Pi)

## Installation

### Quick Setup

**Note: These commands are for Raspberry Pi OS (Linux). If you're on Windows, you'll need to use WSL or transfer files to a Raspberry Pi.**

1. Clone or download this repository:
```bash
git clone <repository-url>
cd RoboCam-Suite
```

2. Run the setup script to create a virtual environment and install dependencies:
```bash
chmod +x setup.sh
./setup.sh
```

3. The setup script will:
   - Check for Python 3.x
   - Create a virtual environment in `venv/`
   - Install all required dependencies
   - Create configuration directories
   - Set up template configuration files

### Manual Installation

1. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create configuration directories:
```bash
mkdir -p config/motion_configs
mkdir -p config/templates
```

## Quick Start

### Starting the Calibration Application

```bash
./start_calibrate.sh
# Or manually:
source venv/bin/activate
python calibrate.py
```

### Starting the Experiment Application

```bash
./start_experiment.sh
# Or manually:
source venv/bin/activate
python experiment.py
```

## Usage

### Calibration (calibrate.py)

1. Launch the calibration application:
   ```bash
   ./start_calibrate.sh
   # Or: python calibrate.py --backend auto
   ```

2. Two windows will open:
   - **Camera Preview Window**: Native hardware-accelerated preview (high performance)
   - **Controls Window**: Movement controls, position display, and FPS monitoring

3. Use the controls window to:
   - Navigate to well positions using directional buttons
   - Adjust step size (0.1 mm, 1.0 mm, or 10.0 mm)
   - Home the printer using the "Home" button
   - Monitor position and preview FPS

4. Use the camera preview window to visually align with wells

5. Record positions for calibration (see User Guide for 4-corner calibration)

**Preview Backends**: Use `--backend auto` (default), `qtgl`, `drm`, or `null` for headless mode

### Experiment Setup (experiment.py)

1. Launch the experiment application
2. Click "Open Experiment" to open the experiment configuration window
3. **Load Calibration** (Required):
   - Select a calibration from the dropdown (calibrations saved from calibrate.py)
   - Calibration must be loaded before experiment can start
   - Checkbox grid will appear showing all available wells
4. **Select Wells**:
   - Use checkboxes to select which wells to include in experiment
   - All wells are checked by default
   - Uncheck wells you want to skip
5. Configure timing:
   - Enter three times: OFF duration, ON duration, OFF duration (seconds)
6. Select pattern: "snake" or "raster"
7. Configure camera settings:
   - Resolution (X and Y)
   - FPS
   - Export type (H264, MJPEG, or JPEG)
   - JPEG quality (if applicable)
8. Set feedrate override (optional, mm/min)
9. Select motion configuration file (for feed/acceleration settings)
10. Set filename scheme and save folder
11. **Export/Import Settings** (Optional):
    - Click "Export Experiment Settings" to save current configuration
    - Click "Load Experiment Settings" to restore saved configuration
    - Calibration file must exist for import to succeed
12. Click "Run" to start the experiment

### Configuration Files

#### Calibration Files (config/calibrations/*.json)

Calibration files store 4-corner calibration data with interpolated well positions:

```json
{
  "name": "well_plate_8x6",
  "upper_left": [8.0, 150.0, 157.0],
  "lower_left": [6.1, 77.7, 157.0],
  "upper_right": [98.1, 143.4, 157.0],
  "lower_right": [97.1, 78.7, 157.0],
  "x_quantity": 8,
  "y_quantity": 6,
  "interpolated_positions": [[8.0, 150.0, 157.0], [19.0, 150.0, 157.0], ...],
  "labels": ["A1", "A2", "A3", ..., "F8"]
}
```

#### Experiment Settings Export

Users can export experiment settings to JSON files for reuse:

```json
{
  "calibration_file": "well_plate_8x6.json",
  "selected_wells": ["A1", "A2", "B1", "B3"],
  "times": [30, 0, 0],
  "resolution": [1920, 1080],
  "fps": 30.0,
  "export_type": "H264",
  "quality": 85,
  "motion_config_file": "default.json",
  "feedrate_override": "1500",
  "filename_scheme": "exp_{y}{x}_{time}_{date}",
  "save_folder": "/path/to/output",
  "pattern": "snake"
}
```

#### Motion Configuration (config/motion_configs/*.json)

Motion configuration files define feedrate and acceleration settings:

```json
{
  "preliminary_feedrate": 2000,
  "preliminary_acceleration": 1000,
  "between_wells_feedrate": 1500,
  "between_wells_acceleration": 800,
  "description": "Default motion profile",
  "author": "User",
  "created": "2025-01-01"
}
```

- **preliminary_feedrate/acceleration**: Used for homing and initial positioning moves
- **between_wells_feedrate/acceleration**: Used for movements between wells during experiment

Templates are available in `config/motion_configs/`:
- `default_motion.json`: Balanced settings
- `fast_motion.json`: High speed/acceleration
- `precise_motion.json`: Lower speed/acceleration for precision

## File Naming

The filename scheme supports the following placeholders:
- `{x}`: X label (e.g., "2", "5")
- `{y}`: Y label (e.g., "B", "D")
- `{time}`: Timestamp (HHMMSS format)
- `{date}`: Date (MMMD format, e.g., "Jan1")

Example: `exp_{y}{x}_{time}_{date}` → `exp_B2_143022_Jan1.mjpeg`

## Output Files

### CSV Export (experiment_points.csv)

The experiment generates a CSV file with well coordinates:

```csv
xlabel,ylabel,xval,yval,zval
2,B,66.6,107.1,86.4
5,B,93.6,107.1,86.4
...
```

### Video/Image Files

Videos or images are saved to the specified save folder with the configured filename scheme.

## Troubleshooting

### Serial Port Connection Issues

- **Problem**: Cannot connect to 3D printer
- **Solution**: 
  - Check USB connection
  - Verify baudrate matches printer settings (default: 115200)
  - Check serial port permissions: `sudo usermod -a -G dialout $USER`
  - Restart after adding user to dialout group

### Camera Not Found

- **Problem**: Camera initialization fails
- **Solution**:
  - Ensure camera is enabled: `sudo raspi-config` → Interface Options → Camera
  - Check camera connection
  - Verify Picamera2 is installed correctly

### GPIO Permission Issues

- **Problem**: Cannot control laser (GPIO errors)
- **Solution**:
  - Run with sudo (not recommended for production)
  - Add user to gpio group: `sudo usermod -a -G gpio $USER`
  - Restart after adding user to gpio group

### Low FPS During Recording

- **Problem**: Video recording FPS is lower than expected
- **Solution**:
  - Reduce preview resolution
  - Use separate camera streams for preview and recording (planned feature)
  - Check available CPU/memory resources
  - Reduce recording resolution if necessary

### Printer Not Responding

- **Problem**: G-code commands not executed
- **Solution**:
  - Check serial connection
  - Verify printer is powered on and ready
  - Check for error messages in printer display
  - Ensure M400 wait commands are supported (use robocam_ccc.py)

## Shell Scripts

### setup.sh

Sets up the virtual environment and installs dependencies:
```bash
./setup.sh
```

### start_calibrate.sh

Launches the calibration application:
```bash
./start_calibrate.sh
```

### start_experiment.sh

Launches the experiment application:
```bash
./start_experiment.sh
```

## Project Structure

```
RoboCam-Suite/
├── calibrate.py              # Calibration GUI application
├── experiment.py             # Experiment automation GUI
├── setup.sh                  # Setup script
├── start_calibrate.sh        # Calibration launcher
├── start_experiment.sh       # Experiment launcher
├── requirements.txt          # Python dependencies
├── robocam/                  # Core modules
│   ├── __init__.py
│   ├── robocam_ccc.py       # RoboCam implementation (preferred)
│   ├── robocam.py           # RoboCam implementation (deprecated)
│   ├── laser.py             # GPIO laser control
│   ├── pihqcamera.py        # Camera wrapper
│   └── stentorcam.py        # StentorCam with well plate support
├── config/                   # Configuration files
│   ├── motion_configs/       # Motion configuration templates
│   ├── calibrations/         # Saved 4-corner calibrations
│   └── templates/            # Experiment templates
└── docs/                     # Documentation
    ├── USER_GUIDE.md         # User guide
    └── DEVELOPER_GUIDE.md    # Developer guide
```

## Contributing

When contributing to this project:

1. Follow existing code style
2. Add docstrings to new functions/classes
3. Update documentation for new features
4. Test with actual hardware when possible
5. Use `robocam_ccc.py` as the primary RoboCam implementation

## License

[Specify your license here]

## Authors

[Specify authors here]

## Acknowledgments

- Picamera2 library for Raspberry Pi camera support
- Marlin/RepRap G-code compatibility for 3D printer control

