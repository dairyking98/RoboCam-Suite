# RoboCam-Suite User Guide

Complete guide for using the RoboCam-Suite calibration and experiment applications for FluorCam, StentorCam, and other automated microscopy experiments under the RoboCam umbrella.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Calibration Procedure](#calibration-procedure)
3. [4-Corner Path Calibration](#4-corner-path-calibration)
4. [Preview Alignment Check](#preview-alignment-check)
5. [Experiment Setup](#experiment-setup)
6. [Motion Configuration](#motion-configuration)
7. [Running Experiments](#running-experiments)
8. [Troubleshooting](#troubleshooting)

## Getting Started

### First Time Setup

1. **Hardware Connection**:
   - Connect Raspberry Pi Camera to the camera port
   - Connect 3D printer via USB serial cable
   - Connect laser module to GPIO pin (default: GPIO 21)

2. **Enable Camera**:
   ```bash
   sudo raspi-config
   # Navigate to: Interface Options → Camera → Enable
   # Reboot after enabling
   ```

3. **Set Permissions**:
   ```bash
   # Add user to dialout group for serial access
   sudo usermod -a -G dialout $USER
   
   # Add user to gpio group for GPIO access
   sudo usermod -a -G gpio $USER
   
   # Log out and log back in for changes to take effect
   ```

4. **Run Setup Script**:
   ```bash
   ./setup.sh
   ```

## Calibration Procedure

### Manual Calibration (calibrate.py)

The calibration application allows you to manually position the camera over wells and record coordinates.

#### Starting Calibration

```bash
./start_calibrate.sh
# Or: source venv/bin/activate && python calibrate.py
# Optional: python calibrate.py --backend qtgl  # Force specific backend
```

#### Using the Calibration Interface

The calibration application opens two windows:

1. **Camera Preview Window**: 
   - Native hardware-accelerated preview (separate window)
   - High-performance display using DRM or QTGL backend
   - Automatically selected based on your system
   - Provides smooth, low-latency preview

2. **Controls Window**:
   - **Position Display**: Current X, Y, Z coordinates
   - **FPS Display**: Real-time preview frames per second
   - **Step Size Selection**: 0.1 mm, 1.0 mm, 10.0 mm, or custom value (default: 9.0 mm)
   - **Movement Controls**:
     - **Y+**: Move forward (positive Y)
     - **Y-**: Move backward (negative Y)
     - **X-**: Move left (negative X)
     - **X+**: Move right (positive X)
     - **Z-**: Move down (negative Z)
     - **Z+**: Move up (positive Z)
   - **Go to Coordinate**: Direct coordinate entry and movement
     - **X, Y, Z Entry Fields**: Enter target coordinates
     - **Go Button**: Move to specified coordinates
     - Only axes with values entered will move (blank entries are ignored)
   - **Home Button**: Returns printer to home position (0, 0, 0)

#### Preview Backend Options

You can specify the preview backend when starting calibrate.py:

- `--backend auto` (default): Automatically selects the best backend
  - Uses QTGL for desktop sessions (X11/Wayland)
  - Uses DRM for console/headless mode
- `--backend qtgl`: Force QTGL backend (for desktop sessions)
- `--backend drm`: Force DRM backend (for console)
- `--backend null`: Headless mode (no preview window, useful for remote operation)

#### Calibration Workflow

1. **Home the Printer**: Click "Home" to return to origin
2. **Navigate to First Well**: Use movement controls to position camera over a well
3. **Fine-Tune Position**: Use 0.1 mm step size for precise alignment
4. **Record Position**: Note the X, Y, Z coordinates from the position display
5. **Repeat**: Navigate to additional wells and record their positions

#### Tips for Accurate Calibration

- Use the camera preview to visually align with well centers
- Start with larger step sizes (10 mm) for rough positioning
- Switch to smaller step sizes (0.1 mm) for fine adjustments
- **Use "Go to Coordinate"** to quickly return to previously recorded positions
  - Enter known coordinates in X, Y, Z fields
  - Leave fields blank for axes you don't want to move
  - Click "Go" to move directly to that position
- Record coordinates immediately after positioning to avoid drift
- Consider using the 4-corner calibration method for better accuracy

## 4-Corner Path Calibration

The 4-corner calibration method accounts for slight angles and misalignment in well plate positioning by recording four corner positions and interpolating all well positions.

### When to Use 4-Corner Calibration

- Well plate is not perfectly aligned with printer axes
- You need to calibrate many wells at once
- You want to account for slight rotation or skew
- You're setting up a new well plate configuration

### 4-Corner Calibration Procedure

1. **Start Calibration Application**:
   ```bash
   ./start_calibrate.sh
   ```

2. **Enter Grid Dimensions**:
   - In the "4-Corner Calibration" section, enter:
     - **X Quantity**: Number of wells horizontally (e.g., 8)
     - **Y Quantity**: Number of wells vertically (e.g., 6)
   - Preview will show total number of wells

3. **Navigate to Upper-Left Corner**:
   - Use movement controls to position camera over the upper-left well
   - Fine-tune position using 0.1 mm steps
   - Click "Set Upper-Left" button when aligned
   - Coordinates will be displayed and status indicator turns green (✓)

4. **Navigate to Lower-Left Corner**:
   - Move to the lower-left well
   - Align and click "Set Lower-Left" button
   - Coordinates will be recorded

5. **Navigate to Upper-Right Corner**:
   - Move to the upper-right well
   - Align and click "Set Upper-Right" button
   - Coordinates will be recorded

6. **Navigate to Lower-Right Corner**:
   - Move to the lower-right well
   - Align and click "Set Lower-Right" button
   - Coordinates will be recorded

7. **Verify Interpolation**:
   - Once all 4 corners are set, positions are automatically interpolated
   - Preview will show: "✓ Interpolated X wells. Labels: A1, A2, A3..."
   - Labels are auto-generated in format: A1, A2, ..., A8, B1, B2, ..., etc.

8. **Save Calibration**:
   - Enter a calibration name (e.g., "well_plate_8x6")
   - Click "Save Calibration" button
   - Calibration is saved to `config/calibrations/{YYYYMMDD_HHMMSS}_{name}.json` (automatically prefixed with date and time, e.g., `20241215_143022_well_plate_8x6.json`)
   - Status will confirm successful save with full filename
   - The date/time prefix (format: YYYYMMDD_HHMMSS) helps track when calibrations were created and allows multiple versions with the same name

9. **Use in Experiment**:
   - Calibration is now available in experiment.py
   - Load it from the calibration dropdown
   - Click "Select Cells" button to open well selection window

### Understanding 4-Corner Interpolation

The system uses bilinear interpolation to calculate all well positions from the four corners:

- **Upper-Left (UL)**: Top-left corner well
- **Lower-Left (LL)**: Bottom-left corner well
- **Upper-Right (UR)**: Top-right corner well
- **Lower-Right (LR)**: Bottom-right corner well

**How It Works**:
The bilinear interpolation method works in three steps:
1. For each horizontal position in the grid, interpolates along the top edge (UL → UR)
2. For the same horizontal position, interpolates along the bottom edge (LL → LR)
3. Interpolates vertically between the top and bottom points to get the final well position

This approach properly accounts for:
- Linear spacing between wells
- Rotation of the well plate (correctly handles angled alignment)
- Non-perpendicular alignment (handles skew/distortion)
- Z-axis variations across the plate

By considering both horizontal and vertical components together (rather than independently), the interpolation ensures accurate well positioning even when the plate is rotated or misaligned with the printer axes. This means wells will be correctly aligned when moving from top-left to top-right, and throughout the entire grid.

## Preview Alignment Check

The preview application (`preview.py`) allows you to sequentially navigate through well positions to verify alignment before running experiments. This is especially useful after calibration or when loading a saved experiment configuration.

### Starting Preview

```bash
./start_preview.sh
# Or manually:
source venv/bin/activate
python preview.py
# Or: python preview.py --backend auto
```

### Preview Interface

The preview application opens two windows:

1. **Camera Preview Window**: 
   - Native hardware-accelerated preview (separate window)
   - High-performance display using DRM or QTGL backend
   - Same preview system as calibrate.py

2. **Controls Window**:
   - **Source Selection**: Choose to load from "Calibration File" or "Experiment Save File"
   - **Load Button**: Opens file dialog to select source file
   - **Well List**: Scrollable listbox showing all loaded wells
   - **Navigation Controls**:
     - **Home Printer**: Home the printer (required before navigation)
     - **Previous**: Move to previous well in sequence
     - **Next**: Move to next well in sequence
     - **Go to Selected**: Move to the currently selected well in the list
   - **Status Display**: Shows current well, position, and operation status
   - **Position Display**: Current X, Y, Z coordinates
   - **FPS Display**: Real-time preview frames per second

### Loading Wells

#### From Calibration File

1. Select "Calibration File" radio button
2. Click "Load" button
3. Navigate to `config/calibrations/` directory
4. Select a calibration JSON file
5. All wells from the calibration will be loaded

#### From Experiment Save File

1. Select "Experiment Save File" radio button
2. Click "Load" button
3. Select an exported experiment settings JSON file
4. The application will:
   - Load the referenced calibration file
   - Filter to only the wells that were checked in the experiment
   - Display only those selected wells in the list

### Preview Workflow

1. **Load Wells**:
   - Choose source type (calibration or experiment file)
   - Click "Load" and select the file
   - Status will show number of wells loaded

2. **Home Printer** (Optional):
   - Click "Home Printer" button if you want to start from origin
   - Current coordinates are shown on startup
   - Navigation works from current position - homing is not required

3. **Navigate Through Wells**:
   - **Click on a well** in the list to select it
   - **Use "Go to Selected"** to move to that well position
   - **Use "Next"** to move to the next well sequentially
   - **Use "Previous"** to move to the previous well sequentially
   - Navigation wraps around (Next from last goes to first, Previous from first goes to last)

4. **Verify Alignment**:
   - Use camera preview to visually check alignment at each position
   - Check that camera is centered over each well
   - Verify focus is correct
   - Note any wells that need adjustment

5. **Make Adjustments** (if needed):
   - If alignment is off, note which wells need adjustment
   - Return to calibrate.py to fine-tune positions
   - Re-save calibration if needed
   - Re-load in preview.py to verify

### Tips for Preview

- **Homing is optional**: Navigation works from current position, just like calibrate.py
- **Use sequential navigation**: The "Next" and "Previous" buttons make it easy to go through all wells in order
- **Check critical wells**: Focus on wells that are critical for your experiment
- **Verify before experiment**: Use preview to catch alignment issues before running a long experiment
- **Compare with calibration**: If preview shows misalignment, the calibration may need adjustment

### When to Use Preview

- **After calibration**: Verify that interpolated positions are accurate
- **Before experiments**: Check alignment before running automated experiments
- **After loading experiment settings**: Verify that selected wells are correctly positioned
- **After hardware changes**: If you've moved the well plate or adjusted the setup

### Integration with Workflow

The preview tool fits into the overall workflow:

1. **Calibrate** (calibrate.py) → Create calibration with well positions
2. **Preview** (preview.py) → Verify alignment of all wells or selected wells
3. **Experiment** (experiment.py) → Run automated experiment with verified positions

## Experiment Setup

### Starting the Experiment Application

```bash
./start_experiment.sh
# Or: source venv/bin/activate && python experiment.py
```

### Configuring an Experiment

1. **Open Experiment Window**:
   - Click "Open Experiment" button in the main window

2. **Load Calibration** (Required):
   - Select a calibration from the "Calibration" dropdown
   - Calibrations are loaded from `config/calibrations/` directory
   - Click "Refresh" if you just created a new calibration
   - Status will show "Loaded: {filename} (X wells)" when successful
   - **Note**: Experiment cannot start without a loaded calibration

3. **Select Wells**:
   - After loading calibration, a checkbox grid will automatically appear in the experiment window
   - Each checkbox represents a well (labeled A1, A2, B1, etc.)
   - All wells are checked by default
   - Uncheck wells you want to exclude from the experiment
   - Use "Check All" or "Uncheck All" buttons (above the grid) for quick selection
   - **Keyboard Shortcuts** (Smart Fill/Unfill Logic):
     - **Shift+Click**: Smart fill/unfill all wells in the same row
       - If the clicked checkbox is checked: fills (checks all) in the row
       - If the clicked checkbox is unchecked and the row is all unchecked: fills (checks all) in the row
       - If the clicked checkbox is unchecked and the row has some checked: unfills (unchecks all) in the row
     - **Ctrl+Click**: Smart fill/unfill all wells in the same column
       - If the clicked checkbox is checked: fills (checks all) in the column
       - If the clicked checkbox is unchecked and the column is all unchecked: fills (checks all) in the column
       - If the clicked checkbox is unchecked and the column has some checked: unfills (unchecks all) in the column
   - Instructions are displayed next to the grid explaining all interaction methods
   - Run button will be disabled if no wells are selected

4. **Configure Timing**:
   - **Times**: Enter three values (OFF, ON, OFF in seconds)
     - Example: `30, 0, 0` means 30s OFF, 0s ON, 0s OFF
     - Example: `10, 20, 10` means 10s OFF, 20s ON, 10s OFF

5. **Select Pattern**:
   - **Snake**: Alternates direction each row (recommended)
   - **Raster**: Always moves left-to-right

6. **Camera Settings**:
   - **Resolution X**: Horizontal pixels (default: 1920)
   - **Resolution Y**: Vertical pixels (default: 1080)
   - **FPS**: Frames per second (e.g., 30.0)
   - **Export Type**: H264, MJPEG, or JPEG
   - **JPEG Quality**: 1-100 (for MJPEG/JPEG)

7. **Motion Settings**:
   - **Motion Config**: Select motion configuration file (see Motion Configuration section)
   - Movement speed is controlled by the motion configuration file
   - Separate settings for preliminary movements (homing) and between-wells movements

8. **File Settings**:
   - **Filename Scheme**: Pattern for output files
     - Placeholders: `{x}`, `{y}`, `{time}`, `{date}`
     - Example: `exp_{y}{x}_{time}_{date}`
   - **Save Folder**: Directory to save output files (default: `/output/filescheme/files`)

9. **Status and Recording Indicator**:
   - **Status Display**: Shows current experiment progress, well being processed, and any errors
   - **Recording Button**: Flashes red when video recording is active
     - Gray when not recording
     - Red/dark red flashing during recording
   - **Timers**: Display total duration, elapsed time, and remaining time

10. **Review Settings**:
   - Check the example filename at the bottom
   - Verify all settings are correct

12. **Export/Import Experiment Settings** (Optional):
    - **Export**: Click "Export Experiment Settings" to save current configuration
      - Saves all settings including selected wells and calibration reference
      - Choose save location via file dialog
    - **Import**: Click "Load Experiment Settings" to restore saved configuration
      - Calibration file must exist for import to succeed
      - If calibration is missing, import will fail with error message
      - All settings including checkbox states will be restored

12. **Save Configuration** (optional):
    - Configuration is auto-saved when you close the window
    - You can also manually save

### Filename Scheme Examples

- `exp_{y}{x}_{time}_{date}` → `exp_B2_143022_Jan1.mjpeg`
- `well_{y}{x}_{date}` → `well_B2_Jan1.mjpeg`
- `test_{time}` → `test_143022.mjpeg`

## Motion Configuration

Motion configuration files control the feedrate (speed) and acceleration for different movement phases.

### Understanding Motion Settings

- **Preliminary Feedrate/Acceleration**: Used for:
  - Homing operation
  - Initial positioning moves
  - Moving to first well
  
- **Between-Wells Feedrate/Acceleration**: Used for:
  - All movements between wells during experiment
  - Well-to-well transitions

### Selecting a Motion Profile

1. In the experiment window, find the "Motion Profile" dropdown
2. Select from available profiles:
   - **default**: Balanced speed and precision for general use
   - **precise**: Lower speed and acceleration for maximum precision
   - **fast**: Maximum speed for rapid well-to-well movements

The selected profile's settings are displayed below the dropdown, showing:
- Preliminary feedrate and acceleration (for homing and initial moves)
- Between-wells feedrate and acceleration (for well-to-well movements)

### Creating Custom Motion Profile

1. Open `config/motion_config.json` in a text editor

2. Add a new profile entry with your preferred values:
   ```json
   {
     "default": { ... },
     "precise": { ... },
     "fast": { ... },
     "my_custom_profile": {
       "name": "My Custom Profile",
       "description": "Custom settings for my experiments",
       "preliminary": {
         "feedrate": 2000,
         "acceleration": 1000
       },
       "between_wells": {
         "feedrate": 1500,
         "acceleration": 800
       }
     }
   }
   ```

3. Save the file
4. Restart experiment.py to see the new profile in the dropdown

### Motion Configuration Guidelines

- **High Feedrate/Acceleration**: Faster experiments, but may cause vibration
- **Low Feedrate/Acceleration**: Slower but more precise, reduces vibration
- **Preliminary settings**: Can be higher since initial moves don't need precision
- **Between-wells settings**: Should match your precision requirements

## Running Experiments

### Starting an Experiment

1. **Prepare**:
   - Ensure well plate is properly positioned
   - Verify camera is focused
   - Check laser connection
   - Confirm save folder has sufficient space

2. **Configure**: Complete experiment setup (see Experiment Setup section)

3. **Start**:
   - Click "Run" button in experiment window
   - Experiment will:
     - Home the printer
     - Move to each well in sequence
     - Record video/still at each well
     - Control laser according to timing settings

4. **Monitor**:
   - Watch status messages in the GUI
   - Monitor elapsed time and remaining time
   - Check position updates

### During Experiment

- **Pause**: Click "Pause" to temporarily pause (movement and recording stop)
- **Resume**: Click "Pause" again to resume
- **Stop**: Click "Stop" to abort experiment
  - Laser will turn off
  - Recording will stop
  - Printer will remain at current position

### After Experiment

1. **Check Output Files**:
   - Navigate to save folder
   - Verify all files were created
   - Check file sizes (should be non-zero)

2. **Review CSV File**:
   - Open `experiment_points.csv` in save folder
   - Verify all wells were visited
   - Check coordinates match expectations

3. **Review Logs**:
   - Check log file in `logs/` directory
   - Look for any errors or warnings

## Additional Resources

For detailed documentation on specific applications:

- **[CALIBRATE_PY_README.md](./CALIBRATE_PY_README.md)**: Complete documentation for calibrate.py
- **[PREVIEW_PY_README.md](./PREVIEW_PY_README.md)**: Complete documentation for preview.py
- **[EXPERIMENT_PY_README.md](./EXPERIMENT_PY_README.md)**: Complete documentation for experiment.py
- **[DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md)**: Development guidelines and architecture
- **[CAMERA_ARCHITECTURE.md](./CAMERA_ARCHITECTURE.md)**: Camera system technical details

## Troubleshooting

### Installation Issues

- **Problem**: `ModuleNotFoundError: No module named 'libcamera'` when running scripts
- **Solution**: 
  - Ensure `python3-libcamera` is installed: `sudo apt-get install -y python3-libcamera`
  - The virtual environment must be created with `--system-site-packages` to access system packages
  - Use the fix script: `./fix_dependencies.sh` to automatically fix this
  - Or recreate the venv: `rm -rf venv && python3 -m venv --system-site-packages venv`

- **Problem**: `setup.sh` fails with "Failed to build 'python-prctl'" or missing headers
- **Solution**:
  - Install system dependencies: `sudo apt-get update && sudo apt-get install -y libcap-dev python3-dev build-essential`
  - The setup script should do this automatically, but if it fails, install manually
  - Use the fix script: `./fix_dependencies.sh`

- **Problem**: `ModuleNotFoundError: No module named 'picamera2'` in virtual environment
- **Solution**:
  - Ensure virtual environment is activated: `source venv/bin/activate`
  - Reinstall packages: `pip install -r requirements.txt`
  - Verify installation: `pip list | grep picamera2`

### Printer Not Moving

- **Check serial connection**: Ensure USB cable is connected
- **Verify baudrate**: Default is 115200, check printer settings
- **Check permissions**: User must be in `dialout` group
- **Test connection**: Try homing manually in calibrate.py

### Camera Not Working

- **Enable camera**: Run `sudo raspi-config` → Interface Options → Camera
- **Check connection**: Verify camera ribbon cable is secure
- **Reboot**: Sometimes required after enabling camera
- **Check permissions**: Ensure camera is accessible

### Laser Not Turning On

- **Check GPIO pin**: Default is GPIO 21, verify connection
- **Check permissions**: User must be in `gpio` group
- **Test manually**: Try manual control in calibrate.py
- **Verify wiring**: Check laser module connections

### Low FPS During Recording

- **Reduce preview resolution**: Lower preview quality
- **Check CPU usage**: Close other applications
- **Reduce recording resolution**: Lower resolution = higher FPS
- **Check storage speed**: Ensure save location is fast (not network drive)

### Experiment Stops Unexpectedly

- **Check log file**: Look for error messages
- **Verify coordinates**: Ensure all coordinates are within printer limits
- **Check serial connection**: Printer may have disconnected
- **Review timing**: Very short times may cause issues

### Files Not Saving

- **Check folder permissions**: Ensure save folder is writable
- **Verify disk space**: Check available space with `df -h`
- **Check filename scheme**: Invalid characters may cause issues
- **Review log file**: Look for file write errors

## Best Practices

1. **Calibration**:
   - Calibrate before each experiment session
   - Use 4-corner calibration for best accuracy (now implemented)
   - Save calibrations with descriptive names
   - Calibrations are reusable across experiments
   - Export experiment settings to preserve calibration references

2. **Experiment Setup**:
   - Always load a calibration before running experiment
   - Test with a single well first (uncheck all others)
   - Verify timing settings are correct
   - Ensure sufficient disk space
   - Export experiment settings for reproducibility

3. **Motion Settings**:
   - Start with default motion configuration
   - Adjust based on your precision needs
   - Higher speeds may cause vibration

4. **File Management**:
   - Use descriptive filename schemes
   - Organize experiments in dated folders
   - Keep CSV files with video files for reference

5. **Safety**:
   - Always stop experiment if something looks wrong
   - Monitor first few wells closely
   - Keep emergency stop accessible
   - Verify laser power settings

## Advanced Usage

### Custom Well Patterns

You can create custom well patterns by:
1. Using 4-corner calibration and selecting specific wells via checkboxes
2. Editing the CSV file after export (for reference only - coordinates come from calibration)
3. Creating multiple calibrations for different well plate configurations

### Batch Experiments

To run multiple experiments:
1. Save different experiment configurations
2. Load configuration before each run
3. Change save folder for each experiment
4. Use different filename schemes to distinguish

### Integration with Analysis Tools

The CSV output (`experiment_points.csv`) can be imported into:
- Excel/Google Sheets for basic analysis
- Python pandas for data analysis
- ImageJ/Fiji for image analysis workflows
- Custom analysis scripts

