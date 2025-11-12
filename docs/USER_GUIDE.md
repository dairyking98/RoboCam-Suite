# RoboCam-Suite User Guide

Complete guide for using the RoboCam-Suite calibration and experiment applications.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Calibration Procedure](#calibration-procedure)
3. [4-Corner Path Calibration](#4-corner-path-calibration)
4. [Experiment Setup](#experiment-setup)
5. [Motion Configuration](#motion-configuration)
6. [Running Experiments](#running-experiments)
7. [Troubleshooting](#troubleshooting)

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
   - **Step Size Selection**: 0.1 mm, 1.0 mm, or 10.0 mm
   - **Movement Controls**:
     - **Y+**: Move forward (positive Y)
     - **Y-**: Move backward (negative Y)
     - **X-**: Move left (negative X)
     - **X+**: Move right (positive X)
     - **Z-**: Move down (negative Z)
     - **Z+**: Move up (positive Z)
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

1. **Start Calibration Mode**:
   - Open calibrate.py
   - Click "4-Corner Calibration" button (when implemented)

2. **Navigate to Upper-Left Corner**:
   - Use movement controls to position camera over the upper-left well
   - Fine-tune position using 0.1 mm steps
   - Click "Record Position" when aligned
   - Confirm the recorded coordinates

3. **Navigate to Lower-Left Corner**:
   - Move to the lower-left well
   - Align and click "Record Position"
   - Confirm coordinates

4. **Navigate to Upper-Right Corner**:
   - Move to the upper-right well
   - Align and click "Record Position"
   - Confirm coordinates

5. **Navigate to Lower-Right Corner**:
   - Move to the lower-right well
   - Align and click "Record Position"
   - Confirm coordinates

6. **Specify Grid Dimensions**:
   - Enter width: Number of wells horizontally
   - Enter depth: Number of wells vertically
   - Example: 8x6 well plate = width: 8, depth: 6

7. **Preview Interpolated Grid**:
   - Review the calculated well positions on the camera preview
   - Verify positions look correct
   - Adjust if needed

8. **Save Calibration**:
   - Enter a calibration name
   - Click "Save Calibration"
   - Calibration is saved as JSON file

9. **Export to Experiment Format**:
   - Click "Export to Experiment"
   - This generates x_values, y_values, x_labels, y_labels
   - Copy these values to experiment.py

### Understanding 4-Corner Interpolation

The system uses bilinear interpolation to calculate all well positions from the four corners:

- **Upper-Left (UL)**: Top-left corner well
- **Lower-Left (LL)**: Bottom-left corner well
- **Upper-Right (UR)**: Top-right corner well
- **Lower-Right (LR)**: Bottom-right corner well

The interpolation accounts for:
- Linear spacing between wells
- Slight rotation of the well plate
- Non-perpendicular alignment
- Z-axis variations across the plate

## Experiment Setup

### Starting the Experiment Application

```bash
./start_experiment.sh
# Or: source venv/bin/activate && python experiment.py
```

### Configuring an Experiment

1. **Open Experiment Window**:
   - Click "Open Experiment" button in the main window

2. **Enter Well Coordinates**:
   - **X Values**: Enter X coordinates (comma or newline separated)
     - Example: `66.6, 93.6, 120.6, 147.6`
   - **Y Values**: Enter Y coordinates (comma or newline separated)
     - Example: `107.1, 125.1, 143.1`
   - **X Labels**: Enter labels for X positions (optional)
     - Example: `2, 5, 8, 11`
   - **Y Labels**: Enter labels for Y positions (optional)
     - Example: `B, D, F`

3. **Configure Timing**:
   - **Times**: Enter three values (OFF, ON, OFF in seconds)
     - Example: `30, 0, 0` means 30s OFF, 0s ON, 0s OFF
     - Example: `10, 20, 10` means 10s OFF, 20s ON, 10s OFF

4. **Set Z Value**:
   - Enter the Z coordinate (focus height) for all wells
   - Example: `86.4`

5. **Select Pattern**:
   - **Snake**: Alternates direction each row (recommended)
   - **Raster**: Always moves left-to-right

6. **Camera Settings**:
   - **Resolution X**: Horizontal pixels (e.g., 640)
   - **Resolution Y**: Vertical pixels (e.g., 512)
   - **FPS**: Frames per second (e.g., 30.0)
   - **Export Type**: H264, MJPEG, or JPEG
   - **JPEG Quality**: 1-100 (for MJPEG/JPEG)

7. **Motion Settings**:
   - **Feedrate**: Movement speed in mm/min (e.g., 1500)
   - **Motion Config**: Select motion configuration file (see Motion Configuration section)

8. **File Settings**:
   - **Filename Scheme**: Pattern for output files
     - Placeholders: `{x}`, `{y}`, `{time}`, `{date}`
     - Example: `exp_{y}{x}_{time}_{date}`
   - **Save Folder**: Directory to save output files

9. **Review Settings**:
   - Check the example filename at the bottom
   - Verify all settings are correct

10. **Save Configuration** (optional):
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

### Selecting a Motion Configuration

1. In the experiment window, find "Motion Config" dropdown
2. Select from available configurations:
   - **default_motion.json**: Balanced speed and precision
   - **fast_motion.json**: High speed for faster experiments
   - **precise_motion.json**: Lower speed for accuracy
   - Custom configurations you've created

### Creating Custom Motion Configuration

1. Copy a template file:
   ```bash
   cp config/motion_configs/default_motion.json config/motion_configs/my_config.json
   ```

2. Edit the file with your preferred values:
   ```json
   {
     "preliminary_feedrate": 2000,
     "preliminary_acceleration": 1000,
     "between_wells_feedrate": 1500,
     "between_wells_acceleration": 800,
     "description": "My custom motion profile",
     "author": "Your Name",
     "created": "2025-01-15"
   }
   ```

3. Save the file
4. Restart experiment.py to see the new configuration in the dropdown

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

## Troubleshooting

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
   - Use 4-corner calibration for best accuracy
   - Record calibration settings for reproducibility

2. **Experiment Setup**:
   - Double-check all coordinates before running
   - Test with a single well first
   - Verify timing settings are correct
   - Ensure sufficient disk space

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
1. Manually entering coordinates in experiment.py
2. Using 4-corner calibration and exporting
3. Editing the CSV file and importing coordinates

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

