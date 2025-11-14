# preview.py - Sequential Well Alignment Preview Tool

## Overview

`preview.py` is a GUI-based application for sequentially previewing well positions for alignment verification before running experiments. It allows users to load wells from calibration files or experiment save files and navigate through them sequentially to verify alignment. This tool is essential for ensuring accurate positioning before executing automated experiments.

## Functionality

### Core Purpose

The preview application enables users to:

1. **Load Wells**: Load well positions from calibration files or experiment save files
2. **Sequential Navigation**: Navigate through wells in order using Next/Previous buttons
3. **Alignment Verification**: Visually verify alignment at each well position using camera preview
4. **Position Checking**: Check that interpolated positions are accurate before experiments
5. **Experiment Preparation**: Verify selected wells from experiment configurations

### Main Workflow

1. **Startup**: Application initializes camera preview and printer connection
2. **Load Wells**: Select source type and load wells from calibration or experiment file
3. **Home Printer**: Home the printer (required before navigation)
4. **Navigate**: Use sequential navigation to move through well positions
5. **Verify**: Check alignment at each position using camera preview
6. **Adjust**: Return to calibrate.py if adjustments are needed

## Features

### 1. High-Performance Camera Preview

- **Native Hardware Acceleration**: Uses DRM or QTGL backend for maximum performance
- **Separate Preview Window**: Preview runs in dedicated window (not embedded in tkinter)
- **Automatic Backend Selection**: Chooses best backend based on system (desktop vs console)
- **FPS Tracking**: Real-time frames-per-second display
- **Optimized Buffering**: Uses `buffer_count=2` for maximum FPS
- **Backend Options**:
  - `auto` (default): Automatically selects best backend
  - `qtgl`: QTGL backend for desktop sessions (X11/Wayland)
  - `drm`: DRM backend for console/headless mode
  - `null`: Headless mode (no preview window)

### 2. Dual Source Loading

#### Loading from Calibration Files

- **Source**: All wells from a saved calibration file
- **Location**: `config/calibrations/*.json`
- **Use Case**: Preview all wells after calibration to verify interpolation accuracy
- **Process**:
  1. Select "Calibration File" radio button
  2. Click "Load" button
  3. Select calibration JSON file
  4. All wells from calibration are loaded into the list

#### Loading from Experiment Save Files

- **Source**: Only checked wells from an exported experiment settings file
- **Location**: Any JSON file exported from experiment.py
- **Use Case**: Preview only the wells that will be used in an experiment
- **Process**:
  1. Select "Experiment Save File" radio button
  2. Click "Load" button
  3. Select experiment settings JSON file
  4. Application loads referenced calibration file
  5. Filters to only selected wells from experiment
  6. Displays filtered wells in the list

### 3. Sequential Navigation

- **Well List**: Scrollable listbox showing all loaded wells with labels (A1, A2, etc.)
- **Selection**: Click on any well in the list to select it
- **Navigation Controls**:
  - **Previous**: Move to previous well in sequence (wraps to last if at first)
  - **Next**: Move to next well in sequence (wraps to first if at last)
  - **Go to Selected**: Move to the currently selected well in the list
- **Automatic Movement**: When navigating, printer automatically moves to well position
- **Position Updates**: Current position and well label are displayed in real-time

### 4. Homing Integration

- **Home Button**: Returns printer to origin (0, 0, 0) position
- **Optional**: Homing is not required - navigation works from current position
- **Current Position Display**: Shows current coordinates on startup (like calibrate.py)
- **Status Indicator**: Shows homing status and completion
- **Automatic Updates**: Position display updates after homing completes
- **Error Handling**: Clear error messages if homing fails

### 5. Status and Position Display

- **Status Display**: Shows current operation status
  - "Ready" when idle
  - "Homing..." during homing
  - "Moving to A1..." during movement
  - "At A1" when positioned
  - Error messages if operations fail
- **Position Display**: Real-time X, Y, Z coordinates
- **Current Well Label**: Shows which well is currently selected/positioned
- **FPS Display**: Real-time preview frames per second
- **Source Status**: Shows number of wells loaded and source file

## Usage

### Starting the Application

```bash
./start_preview.sh
```

Or manually:

```bash
source venv/bin/activate
python preview.py
```

Or with backend selection:

```bash
python preview.py --backend auto    # Auto-select (default)
python preview.py --backend qtgl   # Force QTGL (desktop)
python preview.py --backend drm     # Force DRM (console)
python preview.py --backend null    # Headless mode
```

### Basic Usage Workflow

1. **Launch Application**:
   ```bash
   ./start_preview.sh
   # Or: python preview.py
   ```
   - Current coordinates are displayed on startup

2. **Load Wells**:
   - Choose source type: "Calibration File" or "Experiment Save File"
   - Click "Load" button
   - Select the appropriate file
   - Status will show number of wells loaded

3. **Home Printer** (Optional):
   - Click "Home Printer" button if you want to start from origin
   - Navigation works from current position - homing is not required

4. **Navigate Through Wells**:
   - Click on a well in the list to select it
   - Click "Go to Selected" to move to that well
   - Or use "Next" to move sequentially forward
   - Or use "Previous" to move sequentially backward
   - Use camera preview to verify alignment

5. **Verify Alignment**:
   - Check that camera is centered over each well
   - Verify focus is correct
   - Note any wells that need adjustment

### Example: Previewing All Wells from Calibration

```bash
# Start preview
python preview.py

# In GUI:
# 1. Select "Calibration File"
# 2. Click "Load" → Select "well_plate_8x6.json"
# 3. Status shows: "Loaded 48 wells from well_plate_8x6.json"
# 4. (Optional) Click "Home Printer" to start from origin
# 5. Click "Next" repeatedly to go through all wells
# 6. Verify alignment at each position
```

### Example: Previewing Selected Wells from Experiment

```bash
# Start preview
python preview.py

# In GUI:
# 1. Select "Experiment Save File"
# 2. Click "Load" → Select "my_experiment.json"
# 3. Application loads referenced calibration
# 4. Filters to only selected wells (e.g., A1, A2, B1, B3)
# 5. Status shows: "Loaded 4 selected wells from my_experiment.json"
# 6. (Optional) Click "Home Printer" to start from origin
# 7. Navigate through only the selected wells
# 8. Verify alignment before running experiment
```

## GUI Layout

### Controls Window

```
┌─────────────────────────────────────────────┐
│ Camera preview running in separate window   │
│ (qtgl backend)                              │
├─────────────────────────────────────────────┤
│ Load Wells From:                            │
│ ○ Calibration File  ○ Experiment Save File  │
│ [Load]                                      │
│ Status: Loaded 48 wells from file.json     │
├─────────────────────────────────────────────┤
│ Well List:                                  │
│ ┌─────────────────────────────────────┐   │
│ │ A1                                   │   │
│ │ A2                                   │   │
│ │ A3                                   │   │
│ │ ...                                  │   │
│ │ F8                                   │   │
│ └─────────────────────────────────────┘   │
├─────────────────────────────────────────────┤
│ [Home Printer] [Previous] [Next] [Go to Selected] │
├─────────────────────────────────────────────┤
│ Position (X, Y, Z): 8.00, 150.00, 157.00   │
│ Current Well: A1                            │
│ Preview FPS: 30.0                           │
│ Status: At A1                               │
└─────────────────────────────────────────────┘
```

### Camera Preview Window

- Separate native window (not embedded)
- Hardware-accelerated display
- High-performance preview
- Real-time video feed

## File Formats

### Calibration File Format

Calibration files are loaded from `config/calibrations/*.json`:

```json
{
  "name": "well_plate_8x6",
  "upper_left": [8.0, 150.0, 157.0],
  "lower_left": [6.1, 77.7, 157.0],
  "upper_right": [98.1, 143.4, 157.0],
  "lower_right": [97.1, 78.7, 157.0],
  "x_quantity": 8,
  "y_quantity": 6,
  "interpolated_positions": [
    [8.0, 150.0, 157.0],
    [19.0, 150.0, 157.0],
    ...
  ],
  "labels": ["A1", "A2", "A3", ..., "F8"]
}
```

When loading from calibration file:
- All wells from `interpolated_positions` are loaded
- Labels from `labels` array are used
- Wells are displayed in the order they appear in the arrays

### Experiment Save File Format

Experiment save files are JSON files exported from experiment.py:

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
  "filename_scheme": "exp_{y}{x}_{time}_{date}",
  "save_folder": "/output/filescheme/files",
  "pattern": "snake"
}
```

When loading from experiment save file:
1. Application reads `calibration_file` field
2. Loads the referenced calibration from `config/calibrations/`
3. Filters `interpolated_positions` to only include wells in `selected_wells` array
4. Displays only the filtered wells in the list

## Integration with Workflow

The preview tool is designed to fit into the overall RoboCam-Suite workflow:

### Complete Workflow

1. **Calibrate** (`calibrate.py`):
   - Create calibration with 4-corner method
   - Save calibration to `config/calibrations/`

2. **Preview** (`preview.py`):
   - Load calibration file
   - Navigate through all wells
   - Verify alignment accuracy
   - Return to calibrate.py if adjustments needed

3. **Configure Experiment** (`experiment.py`):
   - Load calibration
   - Select wells via checkbox grid
   - Configure experiment settings
   - Export experiment settings (optional)

4. **Preview Selected Wells** (`preview.py`):
   - Load exported experiment settings
   - Preview only selected wells
   - Verify alignment before experiment

5. **Run Experiment** (`experiment.py`):
   - Execute automated experiment
   - Use verified positions

## Dependencies

- **tkinter**: GUI framework (usually included with Python)
- **picamera2**: Raspberry Pi camera control
- **robocam.robocam_ccc**: Printer control via G-code
- **robocam.camera_preview**: Preview backend utilities
- **robocam.config**: Configuration management

## Technical Details

### Camera Configuration

- **Preview Resolution**: Loaded from config (default: 800x600)
- **Frame Rate**: Loaded from config (default: 30.0 FPS)
- **Backend Selection**: Automatic or manual via `--backend` argument
- **Buffer Count**: 2 (optimized for performance)

### Movement Control

- **Absolute Movement**: Uses `move_absolute()` to move to well positions
- **Coordinate Source**: Positions come from calibration interpolation
- **Z-Axis**: Uses Z coordinate from calibration (all wells typically have same Z)
- **Error Handling**: Catches and displays movement errors clearly

### Navigation Logic

- **Sequential Navigation**: Maintains current index, increments/decrements
- **Wrap-Around**: Next from last goes to first, Previous from first goes to last
- **Listbox Sync**: Listbox selection updates when navigating programmatically
- **Auto-Scroll**: Listbox automatically scrolls to show current well

## Troubleshooting

### No Wells Loaded

- **Problem**: Well list is empty after loading
- **Solution**: 
  - Check that file format is correct (valid JSON)
  - Verify calibration file has `interpolated_positions` and `labels` fields
  - For experiment files, verify `calibration_file` and `selected_wells` fields exist
  - Check that referenced calibration file exists

### Printer Not Moving

- **Problem**: Navigation buttons don't move printer
- **Solution**:
  - Ensure printer is homed first (click "Home Printer")
  - Check printer connection (status will show errors)
  - Verify printer is powered on and ready
  - Check serial port permissions

### Camera Preview Not Showing

- **Problem**: Preview window doesn't appear
- **Solution**:
  - Try different backend: `python preview.py --backend qtgl`
  - Check camera is enabled: `sudo raspi-config` → Interface Options → Camera
  - Verify camera connection
  - Check for error messages in terminal

### Alignment Issues

- **Problem**: Wells appear misaligned in preview
- **Solution**:
  - Return to calibrate.py to adjust positions
  - Re-save calibration with corrected positions
  - Re-load in preview.py to verify
  - Check that well plate hasn't moved since calibration

## Best Practices

1. **Homing is Optional**: Navigation works from current position, just like calibrate.py
2. **Verify After Calibration**: Use preview to check interpolation accuracy after creating calibration
3. **Preview Before Experiments**: Check alignment of selected wells before running long experiments
4. **Use Sequential Navigation**: The Next/Previous buttons make it easy to go through all wells
5. **Check Critical Wells**: Focus verification on wells that are critical for your experiment
6. **Save Time**: Preview selected wells from experiment files to only check what you'll use

## Related Documentation

- **[USER_GUIDE.md](./USER_GUIDE.md)**: Complete user guide with step-by-step procedures
- **[CALIBRATE_PY_README.md](./CALIBRATE_PY_README.md)**: Documentation for calibrate.py
- **[EXPERIMENT_PY_README.md](./EXPERIMENT_PY_README.md)**: Documentation for experiment.py
- **[CAMERA_ARCHITECTURE.md](./CAMERA_ARCHITECTURE.md)**: Camera system technical details

## Examples

### Example 1: Verifying New Calibration

After creating a new calibration in calibrate.py:

```bash
# Start preview
./start_preview.sh
# Or: python preview.py

# Load calibration
# Select "Calibration File" → Load → Select "new_plate.json"

# Home printer
# Click "Home Printer"

# Navigate through all wells
# Click "Next" repeatedly to go through all 48 wells
# Verify each well is correctly aligned
# Note any that need adjustment
```

### Example 2: Previewing Experiment Wells

Before running an experiment:

```bash
# Start preview
./start_preview.sh
# Or: python preview.py

# Load experiment settings
# Select "Experiment Save File" → Load → Select "experiment_1.json"

# Home printer
# Click "Home Printer"

# Navigate through selected wells only
# Use "Next" to go through the 12 selected wells
# Verify alignment before running experiment
```

### Example 3: Quick Alignment Check

Quick check of a few wells:

```bash
# Start preview
./start_preview.sh
# Or: python preview.py

# Load calibration
# Select "Calibration File" → Load → Select calibration

# Home printer
# Click "Home Printer"

# Jump to specific wells
# Click on "A1" in list → "Go to Selected"
# Click on "F8" in list → "Go to Selected"
# Check alignment at corners
```

## Summary

`preview.py` is an essential tool for verifying well positions before running experiments. It provides:

- **Easy Loading**: Load from calibration files or experiment save files
- **Sequential Navigation**: Simple Next/Previous buttons for going through wells
- **Visual Verification**: High-performance camera preview for alignment checking
- **Time Saving**: Preview only selected wells from experiment configurations
- **Error Prevention**: Catch alignment issues before running long experiments

Use preview.py as part of your standard workflow to ensure accurate positioning and successful experiments.

