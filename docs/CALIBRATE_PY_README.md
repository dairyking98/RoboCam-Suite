# calibrate.py - Manual Positioning and Calibration GUI

## Overview

`calibrate.py` is a GUI-based application for manually positioning a camera-equipped robotic stage over well plates and recording coordinates for calibration. It provides precise movement controls, real-time position tracking, and a guided 4-corner calibration workflow for setting up well-plate experiments.

## Functionality

### Core Purpose

The calibration application enables users to:

1. **Manual Positioning**: Precisely navigate the camera to well positions using step-based movement controls
2. **Coordinate Recording**: Record and save well coordinates for use in experiments
3. **4-Corner Calibration**: Guided workflow for calibrating entire well plates by recording four corner positions
4. **Visual Alignment**: Use high-performance camera preview to visually align with well centers
5. **Calibration Management**: Save and load calibration profiles for reuse across experiments

### Main Workflow

1. **Startup**: Application initializes camera preview and printer connection
2. **Navigation**: User navigates to well positions using movement controls
3. **Positioning**: Fine-tune position using adjustable step sizes (0.1mm, 1.0mm, 10.0mm)
4. **Recording**: Record coordinates either manually or via 4-corner calibration workflow
5. **Saving**: Save calibration profiles to `config/calibrations/` for use in experiments

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

### 2. Precise Movement Controls

- **Step Size Selection**: Three precision levels:
  - **0.1 mm**: Fine positioning for precise alignment
  - **1.0 mm**: Standard movement for normal navigation
  - **10.0 mm**: Coarse movement for large displacements
- **Directional Controls**: Six movement buttons:
  - **Y+**: Move forward (positive Y direction)
  - **Y-**: Move backward (negative Y direction)
  - **X-**: Move left (negative X direction)
  - **X+**: Move right (positive X direction)
  - **Z-**: Move down (negative Z direction)
  - **Z+**: Move up (positive Z direction)
- **Home Function**: Return printer to origin (0, 0, 0) position
- **Real-Time Position Display**: Current X, Y, Z coordinates updated continuously

### 3. 4-Corner Calibration Workflow

The 4-corner calibration method accounts for slight angles and misalignment in well plate positioning by recording four corner positions and interpolating all well positions.

#### Calibration Process

1. **Enter Grid Dimensions**:
   - **X Quantity**: Number of wells horizontally (e.g., 8)
   - **Y Quantity**: Number of wells vertically (e.g., 6)
   - Preview shows total number of wells

2. **Record Corner Positions**:
   - Navigate to **Upper-Left** corner well and click "Set Upper-Left"
   - Navigate to **Lower-Left** corner well and click "Set Lower-Left"
   - Navigate to **Upper-Right** corner well and click "Set Upper-Right"
   - Navigate to **Lower-Right** corner well and click "Set Lower-Right"
   - Each corner shows status indicator (✓ when set)

3. **Automatic Interpolation**:
   - System calculates all well positions using bilinear interpolation
   - Accounts for rotation, skew, and Z-axis variations
   - Generates labels automatically (A1, A2, ..., B1, B2, etc.)

4. **Save Calibration**:
   - Enter calibration name (e.g., "well_plate_8x6")
   - Click "Save Calibration"
   - Saved to `config/calibrations/{name}.json`
   - Status confirms successful save

#### Understanding 4-Corner Interpolation

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

### 4. Real-Time Status Monitoring

- **Position Display**: Current X, Y, Z coordinates (updated continuously)
- **FPS Display**: Real-time preview frames per second
- **Status Indicators**: Color-coded status messages:
  - **Green**: Operation successful
  - **Orange**: Operation in progress
  - **Red**: Error or failure
- **Connection Status**: Shows printer connection state
- **Calibration Status**: Shows which corners are set and interpolation status

### 5. Error Handling and User Feedback

- **Connection Errors**: Clear messages for printer connection failures
- **Movement Errors**: User-friendly error messages for movement failures
- **Timeout Handling**: Graceful handling of communication timeouts
- **Status Updates**: Real-time status feedback for all operations
- **Error Recovery**: Continues operation when non-critical errors occur

## Logic Behind the Implementation

### Architecture

The application follows an object-oriented design with a main `CameraApp` class that manages:

- **GUI Components**: Tkinter-based interface with organized sections
- **Hardware Control**: Integration with `RoboCam` for printer control
- **Camera Management**: Picamera2 instance for preview
- **Calibration Logic**: 4-corner calibration workflow and interpolation

### Preview Backend Selection

```python
def start_best_preview(picam2, backend="auto"):
    if backend == "auto":
        if has_desktop_session():
            return "qtgl"  # Desktop session
        else:
            return "drm"   # Console mode
    else:
        return backend  # User-specified
```

The system automatically selects the best preview backend:
- **Desktop Session**: Uses QTGL (X11/Wayland compatible)
- **Console Mode**: Uses DRM (direct rendering manager)
- **Headless**: Uses null backend (no preview window)

### FPS Tracking

```python
class FPSTracker:
    def update(self):
        # Called for each camera frame
        # Calculates FPS from frame timestamps
        pass
```

FPS is tracked using a callback on each camera frame, providing real-time performance monitoring.

### 4-Corner Interpolation Logic

```python
def generate_path(width, depth, upper_left, lower_left, upper_right, lower_right):
    # Bilinear interpolation across the grid
    # Accounts for rotation and skew
    # Returns list of (X, Y, Z) tuples for all wells
    pass
```

The interpolation uses `WellPlatePathGenerator` from `robocam.stentorcam` to calculate all well positions from the four corners.

### Movement Control Logic

```python
def _safe_move(self, move_func):
    try:
        move_func()  # Execute movement
        self.status_label.config(text="Move successful", fg="green")
    except Exception as e:
        # User-friendly error messages
        self.status_label.config(text=user_msg, fg="red")
```

All movements are wrapped in error handling to provide clear feedback to users.

### Calibration Save Format

```python
calibration_data = {
    "name": calibration_name,
    "upper_left": [x, y, z],
    "lower_left": [x, y, z],
    "upper_right": [x, y, z],
    "lower_right": [x, y, z],
    "x_quantity": x_qty,
    "y_quantity": y_qty,
    "interpolated_positions": [[x, y, z], ...],
    "labels": ["A1", "A2", ...]
}
```

Calibrations are saved as JSON files for easy loading in `experiment.py`.

## Usage Examples

### Basic Manual Calibration

1. **Start Application**:
   ```bash
   ./start_calibrate.sh
   # Or: python calibrate.py --backend qtgl
   ```

2. **Home Printer**:
   - Click "Home Printer" button
   - Wait for homing to complete

3. **Navigate to Well**:
   - Use movement controls to position camera
   - Start with 10.0 mm steps for rough positioning
   - Switch to 0.1 mm steps for fine alignment

4. **Record Position**:
   - Note X, Y, Z coordinates from position display
   - Manually record or use 4-corner calibration

### 4-Corner Calibration Workflow

1. **Enter Grid Dimensions**:
   - X Quantity: `8`
   - Y Quantity: `6`
   - Preview shows: "Total: 48 wells"

2. **Set Upper-Left Corner**:
   - Navigate to top-left well (A1)
   - Fine-tune position with 0.1 mm steps
   - Click "Set Upper-Left"
   - Status shows: "✓ Upper-Left set: (8.0, 150.0, 157.0)"

3. **Set Lower-Left Corner**:
   - Navigate to bottom-left well (A6)
   - Click "Set Lower-Left"
   - Status shows: "✓ Lower-Left set: (6.1, 77.7, 157.0)"

4. **Set Upper-Right Corner**:
   - Navigate to top-right well (H1)
   - Click "Set Upper-Right"
   - Status shows: "✓ Upper-Right set: (98.1, 143.4, 157.0)"

5. **Set Lower-Right Corner**:
   - Navigate to bottom-right well (H6)
   - Click "Set Lower-Right"
   - Status shows: "✓ Lower-Right set: (97.1, 78.7, 157.0)"

6. **Verify Interpolation**:
   - Preview shows: "✓ Interpolated 48 wells. Labels: A1, A2, A3, ..., H6"

7. **Save Calibration**:
   - Enter name: `well_plate_8x6`
   - Click "Save Calibration"
   - Status shows: "✓ Calibration saved: well_plate_8x6.json"

### Preview Backend Selection

**Desktop Session** (default):
```bash
python calibrate.py --backend auto
# Automatically selects qtgl for desktop
```

**Console Mode**:
```bash
python calibrate.py --backend drm
# Uses DRM for console/headless
```

**Headless Mode** (no preview):
```bash
python calibrate.py --backend null
# No preview window, controls only
```

## Calibration File Format

Saved calibrations are stored in `config/calibrations/{name}.json`:

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
    [30.0, 150.0, 157.0],
    ...
  ],
  "labels": [
    "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8",
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8",
    ...
  ]
}
```

## Dependencies

- **tkinter**: GUI framework (usually included with Python)
- **picamera2**: Raspberry Pi camera control
- **robocam.robocam_ccc**: Printer control via G-code
- **robocam.camera_preview**: Preview backend utilities
- **robocam.config**: Configuration management
- **robocam.stentorcam**: WellPlatePathGenerator for interpolation

## Technical Details

### Camera Configuration

- **Preview Resolution**: `1024x820` (configurable via `preview_resolution`)
- **Buffer Count**: `2` (optimized for maximum FPS)
- **Backend**: DRM or QTGL (hardware-accelerated)
- **FPS Tracking**: Callback-based frame counting

### Movement Control

- **G-code Commands**:
  - `G28`: Homing
  - `G91`: Relative positioning mode
  - `G0 X Y Z`: Movement command
  - `M114`: Get current position
  - `M400`: Wait for movement completion

### Threading

- **Main Thread**: Tkinter event loop, GUI updates
- **Position Updates**: `root.after(100, update_status)` for non-blocking updates
- **Camera Preview**: Runs in separate process (native preview)

### Error Handling

- **Connection Errors**: Graceful degradation when printer unavailable
- **Movement Errors**: User-friendly error messages
- **Timeout Handling**: Automatic retry for transient failures
- **Status Updates**: Real-time feedback for all operations

## Troubleshooting

### Common Issues

1. **"Camera/preview start failed"**
   - **Solution**: Check camera is enabled: `sudo raspi-config` → Interface Options → Camera
   - **Solution**: Try different backend: `--backend qtgl` or `--backend drm`
   - **Solution**: Test camera: `libcamera-hello -t 0`

2. **"Printer not connected"**
   - **Solution**: Check USB cable connection
   - **Solution**: Verify baudrate matches printer (default: 115200)
   - **Solution**: Check user permissions: `sudo usermod -a -G dialout $USER`

3. **"Movement failed" or "Homing failed"**
   - **Solution**: Check printer is powered on
   - **Solution**: Verify serial port is accessible
   - **Solution**: Check for mechanical obstructions
   - **Solution**: Review error message in status label

4. **Low FPS in preview**
   - **Solution**: Check camera connection and ribbon cable
   - **Solution**: Reduce preview resolution
   - **Solution**: Close other applications
   - **Solution**: Verify backend selection (qtgl for desktop, drm for console)

5. **"Calibration save failed"**
   - **Solution**: Check `config/calibrations/` directory exists
   - **Solution**: Verify write permissions
   - **Solution**: Ensure all 4 corners are set before saving

6. **Preview window not appearing**
   - **Solution**: Check backend selection (use `--backend qtgl` for desktop)
   - **Solution**: Verify desktop session is active
   - **Solution**: Try `--backend drm` for console mode
   - **Solution**: Use `--backend null` for headless operation

### Best Practices

1. **Calibration**:
   - Always home printer before starting calibration
   - Use 0.1 mm steps for final positioning
   - Verify all 4 corners are accurately positioned
   - Save calibrations with descriptive names

2. **Navigation**:
   - Start with large steps (10.0 mm) for rough positioning
   - Switch to smaller steps (1.0 mm, 0.1 mm) for fine alignment
   - Use camera preview to visually verify alignment

3. **4-Corner Calibration**:
   - Ensure well plate is properly secured before calibration
   - Record corners in order (UL → LL → UR → LR)
   - Verify interpolation preview shows correct number of wells
   - Test calibration by loading in experiment.py

4. **Performance**:
   - Use appropriate backend for your system
   - Monitor FPS to ensure smooth preview
   - Close unnecessary applications during calibration

## Suggested Improvements

### High Priority

1. **Visual Grid Overlay** ✅ **COMPLETED** (via interpolation preview)
   - Show interpolated well positions on preview
   - Crosshair overlay for precise positioning
   - Well labels overlaid on preview

2. **Calibration Validation**
   - Visual preview of interpolated grid
   - Position validation before saving
   - Warning for extreme angles or skew

3. **Calibration Templates**
   - Pre-defined well plate configurations
   - Quick selection of common grid sizes
   - Template library for standard plates

### Medium Priority

4. **Keyboard Shortcuts**
   - Arrow keys for movement
   - Space: Set current corner
   - Enter: Save calibration

5. **Calibration Comparison**
   - Compare multiple calibrations
   - Visualize differences
   - Merge calibrations

6. **Enhanced Error Recovery**
   - Automatic retry for transient failures
   - Position recovery after errors
   - Calibration backup/restore

### Low Priority

7. **Multi-Well Manual Entry**
   - Manual coordinate entry for custom patterns
   - Import coordinates from CSV
   - Export coordinates to CSV

8. **Calibration History**
   - Track calibration changes
   - Revert to previous calibrations
   - Calibration versioning

## Related Documentation

- [USER_GUIDE.md](./USER_GUIDE.md): Step-by-step user procedures
- [EXPERIMENT_PY_README.md](./EXPERIMENT_PY_README.md): Experiment application documentation
- [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md): Development guidelines and architecture
- [CAMERA_ARCHITECTURE.md](./CAMERA_ARCHITECTURE.md): Camera system technical details
- [PLANNED_CHANGES.md](../PLANNED_CHANGES.md): Implementation roadmap
- [ROOM_FOR_IMPROVEMENT.md](../ROOM_FOR_IMPROVEMENT.md): Improvement opportunities

## Author

RoboCam-Suite

## License

See main project LICENSE file.

