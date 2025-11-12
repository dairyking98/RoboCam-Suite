# experiment.py - Automated Well-Plate Experiment Execution

## Overview

`experiment.py` is a GUI-based application for automating well-plate experiments with synchronized camera capture and laser stimulation. It provides a comprehensive interface for configuring and executing multi-well experiments with precise timing control, motion profiles, and data export capabilities.

## Functionality

### Core Purpose

The application automates the execution of well-plate experiments by:

1. **Automated Movement**: Moves a camera-equipped positioning stage to predefined well coordinates
2. **Synchronized Capture**: Records video or captures still images at each well position
3. **Laser Control**: Provides precise timing sequences for laser stimulation (OFF-ON-OFF pattern)
4. **Data Export**: Generates CSV files with well coordinates and metadata
5. **Configuration Management**: Saves and loads experiment configurations for reproducibility

### Main Workflow

1. **Configuration**: User sets up well positions (X, Y coordinates), labels, timing sequences, camera settings, and motion parameters
2. **Sequence Generation**: Application builds a well sequence based on selected pattern (snake or raster)
3. **Execution**: For each well:
   - Moves to well position with configured motion profile
   - Starts video/still capture
   - Executes laser timing sequence (OFF → ON → OFF)
   - Stops recording and saves file with formatted name
4. **Monitoring**: Real-time status updates, timers, and progress tracking

## Features

### 1. Calibration-Based Well Selection

- **Calibration Loading**: Load saved 4-corner calibrations from `config/calibrations/`
- **Checkbox Grid**: Visual grid of checkboxes for selecting wells
- **Auto-Generated Labels**: Wells labeled automatically (A1, A2, ..., B1, B2, etc.)
- **Interpolated Positions**: All well positions calculated from 4-corner calibration
- **Z Value**: Automatically set from calibration interpolation
- **Pattern Selection**: Choose between "snake" (alternating row direction) or "raster" (consistent direction)
- **Manual Entry Fallback**: Manual coordinate entry available when no calibration loaded (experiment blocked)

### 2. Timing Control

- **Three-Phase Timing**: Configure OFF-ON-OFF laser sequence durations
  - First OFF period: Baseline capture before stimulation
  - ON period: Laser stimulation duration
  - Second OFF period: Post-stimulation observation
- **Pause/Resume**: Pause experiment execution at any time
- **Stop Control**: Emergency stop with automatic laser shutdown and recording termination

### 3. Camera Settings

- **Resolution**: Configurable X and Y resolution (default: 640x512)
- **Frame Rate**: Adjustable FPS (default: 30.0)
- **Export Formats**:
  - **H264**: Video encoding with high bitrate (50 Mbps)
  - **MJPEG**: Motion JPEG video with quality control
  - **JPEG**: Single still image capture
- **Quality Control**: JPEG quality setting (1-100, default: 85)

### 4. Motion Configuration

- **Motion Profiles**: Select from predefined motion configuration files:
  - `default.json`: Balanced speed and precision
  - `fast.json`: Optimized for speed
  - `precise.json`: Optimized for precision
- **Preliminary Settings**: Separate feedrate and acceleration for homing/initial movements
- **Between-Wells Settings**: Separate feedrate and acceleration for well-to-well movements
- **Feedrate Override**: Optional manual feedrate override (mm/min)

### 5. File Management

- **Filename Scheme**: Customizable naming pattern with placeholders:
  - `{x}`: X-axis label (column number)
  - `{y}`: Y-axis label (row letter)
  - `{time}`: Timestamp (HHMMSS)
  - `{date}`: Date (MMMDD)
  - Example: `exp_{y}{x}_{time}_{date}` → `exp_B2_143022_Jan15.h264`
- **Save Folder**: Configurable output directory with browse dialog
- **CSV Export**: Automatic generation of `experiment_points.csv` with well coordinates
- **Experiment Settings Export**: Save complete experiment configuration to JSON
- **Experiment Settings Import**: Load saved configurations with calibration validation

### 6. Configuration Persistence

- **Auto-Save**: Configuration automatically saved to `experiment_config.json`
- **Auto-Load**: Previous settings restored on application start
- **Session Management**: Settings preserved across application restarts
- **Experiment Settings Export**: Export complete configuration including calibration reference
- **Experiment Settings Import**: Load saved configurations with automatic calibration validation

### 7. Real-Time Monitoring

- **Status Display**: Current well, movement status, and capture progress
- **Timers**:
  - **Duration**: Total estimated experiment time
  - **Elapsed**: Time since experiment start
  - **Remaining**: Estimated time to completion
- **Live Preview**: Example filename preview as settings change

## Logic Behind the Implementation

### Architecture

The application follows an object-oriented design with a main `ExperimentWindow` class that manages:

- **GUI Components**: Tkinter-based interface with organized sections
- **Hardware Control**: Integration with `RoboCam` (printer control) and `Laser` (GPIO control)
- **Camera Management**: Picamera2 instance for video/still capture
- **Threading**: Separate execution thread to prevent GUI blocking

### Sequence Generation Logic

When using calibration:
```python
# Get selected wells from checkboxes
selected_wells = [label for label, var in well_checkboxes.items() if var.get()]

# Map labels to interpolated positions
label_to_pos = {label: pos for label, pos in zip(labels, interpolated_positions)}

# Build sequence from selected wells
for label in selected_wells:
    pos = label_to_pos[label]
    # Extract row/column for pattern sorting
    row_num = ord(label[0]) - ord('A')
    col_num = int(label[1:]) - 1
    selected_positions.append((pos[0], pos[1], pos[2], label, row_num, col_num))

# Sort by pattern
if pattern == "snake":
    # Snake: alternate row direction
    selected_positions.sort(key=lambda x: (x[4], x[5] if x[4] % 2 == 0 else -x[5]))
else:  # raster
    # Raster: consistent direction
    selected_positions.sort(key=lambda x: (x[4], x[5]))
```

When using manual entry (deprecated, blocked without calibration):
```python
# Snake Pattern (alternating rows)
for i, y_val in enumerate(ys):
    row = pairs if (i % 2 == 0) else list(reversed(pairs))
    # Even rows: left-to-right, Odd rows: right-to-left
    for x_val, x_lbl in row:
        seq.append((x_val, y_val, x_lbl, y_lbl))
```

### Motion Control Logic

1. **Preliminary Phase** (before homing):
   - Loads preliminary feedrate and acceleration from motion config
   - Applies acceleration via `M204` G-code command
   - Executes homing sequence

2. **Between-Wells Phase** (well movements):
   - Switches to between-wells feedrate and acceleration
   - Applies acceleration settings
   - Uses feedrate override if provided, otherwise uses between-wells feedrate
   - Moves to each well position with `move_absolute()`

### Camera Configuration Logic

The application uses separate camera configurations for different phases:

1. **Preview Configuration** (if needed):
   - Lower resolution (640x480) for GUI display
   - Optimized for real-time preview

2. **Recording Configuration**:
   - Full resolution as specified by user
   - Frame rate control via `FrameRate` parameter
   - Optimized buffer settings (`buffer_count=2`) for maximum FPS
   - Preview disabled during recording to maximize performance

### Timing Sequence Logic

For each well (video modes only):

```python
# Phase 1: OFF (baseline)
laser.switch(0)
start_recording()
wait(off_t seconds)

# Phase 2: ON (stimulation)
laser.switch(1)
wait(on_t seconds)

# Phase 3: OFF (post-stimulation)
laser.switch(0)
wait(off2 seconds)
stop_recording()
```

For JPEG mode:
- Single capture at well position (no timing sequence)

### Error Handling

- **Input Validation**: Type checking and range validation for all user inputs
- **Hardware Errors**: Try-except blocks around all hardware operations
- **Graceful Degradation**: Continues operation when non-critical errors occur
- **User Feedback**: Clear error messages displayed in status label

### Threading Model

- **Main Thread**: GUI event loop (tkinter)
- **Execution Thread**: Experiment run loop (daemon thread)
  - Prevents GUI freezing during long operations
  - Allows pause/stop control from GUI
  - Automatic cleanup on application exit

### Configuration Parsing

Text widgets are parsed using regex to handle multiple input formats:
- Comma-separated: `"1, 2, 3"`
- Newline-separated: `"1\n2\n3"`
- Mixed: `"1, 2\n3, 4"`

Values are extracted and validated before use.

## Suggested Improvements

### High Priority

1. **4-Corner Path Calibration Integration** ✅ **COMPLETED**
   - ✅ Import well positions from calibration workflow
   - ✅ Eliminate manual coordinate entry (blocked without calibration)
   - ✅ Support for angled well plates

2. **GUI Consistency**
   - Standardize button styles and fonts with `calibrate.py`
   - Create shared GUI style module
   - Unified status indicators and progress bars

3. **Experiment Templates**
   - Save/load experiment presets
   - Quick selection of common configurations
   - Template library for different well plate types

4. **Resume Interrupted Experiments**
   - Save progress to file
   - Resume from last completed well
   - Skip already-captured wells on restart

5. **Enhanced Error Recovery**
   - Automatic retry for transient failures
   - Movement validation before capture
   - Position verification after movement

### Medium Priority

6. **Progress Persistence**
   - Save experiment state periodically
   - Recovery from crashes
   - Experiment history log

7. **Validation Before Execution**
   - Preview well sequence
   - Validate all positions are reachable
   - Check disk space availability
   - Verify camera and hardware connectivity

8. **Keyboard Shortcuts**
   - Space: Pause/Resume
   - Escape: Stop
   - Enter: Start (when configured)

9. **FPS Display**
   - Real-time FPS during recording
   - Average FPS per well
   - FPS statistics in status

10. **Enhanced CSV Export**
    - Include timing information
    - Add metadata (resolution, FPS, export type)
    - Include file paths for each well

### Low Priority

11. **Multi-Well Time-Lapse**
    - Return to wells multiple times
    - Configurable intervals
    - Time-lapse sequence generation

12. **Focus Stacking**
    - Multiple Z positions per well
    - Automatic focus stacking
    - Depth-of-field enhancement

13. **Metadata Embedding**
    - Embed experiment parameters in video files
    - EXIF data for JPEG files
    - JSON metadata sidecar files

14. **Remote Monitoring**
    - Web interface for status
    - Remote start/stop control
    - Real-time progress streaming

## Planned Improvements and Fixes

### Phase 2: GUI Consistency & FPS Optimization

**Status**: Mostly Complete

- ✅ Separate camera configurations for preview vs recording
- ✅ Optimized camera buffer settings (`buffer_count=2`)
- ✅ Preview disabled during recording
- ⚠️ Standardize GUI appearance with `calibrate.py` (pending)
- ⚠️ Consistent button styling and fonts (pending)
- ⚠️ Shared GUI style module (pending)

### Phase 3: 4-Corner Path Calibration

**Status**: Completed ✅

- ✅ Import well positions from calibration workflow
- ✅ Support for angled well plates
- ✅ Calibration loading and validation
- ✅ Checkbox grid for well selection
- ✅ Experiment settings export/import
- ✅ Automatic label generation
- ⚠️ Visual preview of well grid overlay (optional enhancement)

### Phase 4: Motion Configuration System

**Status**: Completed ✅

- ✅ Motion configuration file structure (JSON)
- ✅ Preliminary and between-wells settings
- ✅ Configuration file selector in GUI
- ✅ G-code acceleration commands (M204)
- ✅ Automatic application of motion settings
- ✅ Motion settings display in GUI

### Phase 5: Code Quality

**Status**: Mostly Complete

- ✅ Comprehensive error handling
- ✅ Type hints throughout
- ✅ Logging system implemented
- ✅ Configuration management
- ⚠️ Dataclasses for configuration objects (pending)

### Phase 6: Features

**Status**: Partially Complete

- ✅ Experiment settings export/import
- ⚠️ Experiment templates
- ⚠️ Experiment history/logging
- ⚠️ Resume interrupted experiments
- ⚠️ Progress persistence
- ⚠️ Keyboard shortcuts
- ⚠️ FPS display in GUI

### Phase 7: Testing & Reliability

**Status**: Pending

- ⚠️ Unit tests for core modules
- ⚠️ Hardware simulation layer
- ⚠️ Integration tests
- ⚠️ Experiment validation tests

## Usage Example

### Basic Workflow

1. **Launch Application**:
   ```bash
   python experiment.py
   ```

2. **Load Calibration** (Required):
   - Click "Open Experiment"
   - Select calibration from dropdown (e.g., "well_plate_8x6.json")
   - Status should show "Loaded: well_plate_8x6.json (48 wells)"
   - Checkbox grid will appear

3. **Select Wells**:
   - Use checkboxes to select/deselect wells
   - All wells checked by default
   - Uncheck wells to exclude from experiment

4. **Configure Experiment**:
   - Set timing: `30, 0, 0` (30s OFF, 0s ON, 0s OFF)
   - Choose pattern: `snake` or `raster`
   - Z value is automatically set from calibration

3. **Configure Camera**:
   - Resolution: `640` x `512`
   - FPS: `30.0`
   - Export type: `H264`, `MJPEG`, or `JPEG`
   - Quality: `85` (for JPEG/MJPEG)

4. **Configure Motion**:
   - Select motion config: `default.json`
   - Optional feedrate override: `1500` mm/min

5. **Set Output**:
   - Filename scheme: `exp_{y}{x}_{time}_{date}`
   - Save folder: `/path/to/output`

6. **Run Experiment**:
   - Click "Run" to start
   - Monitor progress via status and timers
   - Use "Pause" to pause/resume
   - Use "Stop" to abort

### Configuration File Format

`experiment_config.json` (legacy format, still supported):
```json
{
  "x_values": ["66.6", "93.6", "120.6", "147.6"],
  "x_labels": ["2", "5", "8", "11"],
  "y_values": ["107.1", "125.1", "143.1"],
  "y_labels": ["B", "D", "F"],
  "times": ["30", "0", "0"],
  "z_value": "86.4",
  "pattern": "snake",
  "filename_scheme": "exp_{y}{x}_{time}_{date}",
  "save_folder": "/path/to/output",
  "feedrate": "1500",
  "resolution": ["640", "512"],
  "fps": "30.0",
  "export_type": "H264",
  "quality": "85",
  "motion_config_file": "default.json"
}
```

### Experiment Settings Export Format

When exporting experiment settings:
```json
{
  "calibration_file": "well_plate_8x6.json",
  "selected_wells": ["A1", "A2", "B1", "B3", "C2"],
  "times": [30, 0, 0],
  "resolution": [640, 512],
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

### Calibration File Format

`config/calibrations/{name}.json`:
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

### Motion Configuration Format

`config/motion_configs/default.json`:
```json
{
  "preliminary": {
    "feedrate": 3000,
    "acceleration": 500
  },
  "between_wells": {
    "feedrate": 5000,
    "acceleration": 1000
  }
}
```

## Dependencies

- **tkinter**: GUI framework (usually included with Python)
- **picamera2**: Raspberry Pi camera control
- **robocam.robocam_ccc**: Printer control via G-code
- **robocam.laser**: GPIO laser control
- **robocam.config**: Configuration management
- **robocam.logging_config**: Logging system

## Technical Details

### Camera Configuration

- **Preview Config**: `640x480`, 2 buffers (if preview needed)
- **Recording Config**: User-specified resolution, user-specified FPS, 2 buffers
- **Encoder Selection**:
  - H264: `H264Encoder(bitrate=50_000_000)`
  - MJPEG: `JpegEncoder(q=quality)`
  - JPEG: Direct capture (no encoder)

### Motion Control

- **G-code Commands**:
  - `G28`: Homing
  - `G0 X Y Z`: Absolute movement
  - `M204 P A`: Set acceleration (P=print, A=value)
  - `M400`: Wait for movement completion

### Threading

- **Main Thread**: Tkinter event loop, GUI updates
- **Execution Thread**: Experiment run loop (daemon=True)
- **Timer Updates**: `parent.after(200, update_timers)` for non-blocking updates

### File Naming

- **Placeholders**: `{x}`, `{y}`, `{time}`, `{date}`
- **Time Format**: `%H%M%S` (e.g., "143022")
- **Date Format**: `%b%-d` (e.g., "Jan15")
- **Extension**: Based on export type (`.h264`, `.mjpeg`, `.jpeg`)

## Troubleshooting

### Common Issues

1. **"Invalid times: must provide 3 values"**
   - Ensure timing field contains exactly 3 numbers (OFF, ON, OFF)

2. **"Homing failed"**
   - Check printer connection
   - Verify serial port is accessible
   - Check printer is powered on

3. **"Movement failed"**
   - Verify well positions are within printer bounds
   - Check for mechanical obstructions
   - Verify motion configuration is valid

4. **Low FPS during recording**
   - Reduce resolution
   - Lower FPS setting
   - Check SD card write speed
   - Ensure preview is disabled during recording

5. **Files not saving**
   - Check save folder permissions
   - Verify disk space availability
   - Check filename scheme is valid

6. **"No calibration loaded" error**
   - Load a calibration from the dropdown before starting experiment
   - Create calibration in calibrate.py if none exist
   - Check that calibration file exists in `config/calibrations/`

7. **"Referenced calibration file not found" (on import)**
   - Ensure the calibration file referenced in exported settings exists
   - Re-create the calibration if it was deleted
   - Check file path in exported settings JSON

## Related Documentation

- [USER_GUIDE.md](../USER_GUIDE.md): Step-by-step user procedures
- [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md): Development guidelines
- [CAMERA_ARCHITECTURE.md](./CAMERA_ARCHITECTURE.md): Camera system architecture
- [PLANNED_CHANGES.md](../PLANNED_CHANGES.md): Implementation roadmap
- [ROOM_FOR_IMPROVEMENT.md](../ROOM_FOR_IMPROVEMENT.md): Improvement opportunities

## Author

RoboCam-Suite

## License

See main project LICENSE file.

