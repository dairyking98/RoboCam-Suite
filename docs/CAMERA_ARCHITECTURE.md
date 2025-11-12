# Camera Architecture: Single vs Multiple Picamera2 Instances

## Overview

This document explains the trade-offs between using a single Picamera2 instance versus multiple instances for preview and recording.

## Current Implementation

### calibrate.py
- **Single Picamera2 instance** for preview
- Uses native hardware-accelerated preview (DRM/QTGL)
- Preview runs in separate window (not in tkinter)
- Optimized with `buffer_count=2`

### experiment.py
- **Single Picamera2 instance** for recording
- Preview disabled during recording (maximizes FPS)
- Optimized recording configuration with `buffer_count=2`
- Video capture runs in separate thread

## Hardware Limitation: Single Camera Module

**Critical Constraint**: Raspberry Pi camera modules (including Pi HQ Camera) only support **ONE active stream at a time** from a single physical camera.

This means:
- ❌ You **cannot** have simultaneous preview and recording streams from the same camera
- ❌ Two Picamera2 instances pointing to the same camera cannot both be active simultaneously
- ✅ You **can** use multiple instances, but only one can be active at a time

## Multiple Picamera2 Instances: When It Makes Sense

### Scenario 1: Multiple Physical Cameras
If you have multiple camera modules connected:
```python
# Camera 0 for preview
preview_cam = Picamera2(0)
preview_cam.configure(preview_cam.create_preview_configuration())
preview_cam.start()

# Camera 1 for recording
record_cam = Picamera2(1)
record_cam.configure(record_cam.create_video_configuration())
record_cam.start()
```
**Benefit**: True simultaneous preview and recording from different cameras.

### Scenario 2: Avoiding Reconfiguration Overhead
For a single camera, you could maintain two instances and switch between them:
```python
# Preview instance (always configured)
preview_cam = Picamera2()
preview_cam.configure(preview_cam.create_preview_configuration())
preview_cam.start()

# Recording instance (configured when needed)
record_cam = Picamera2()
# Keep stopped until recording starts
```

**Potential Benefits**:
- Avoid reconfiguration overhead when switching modes
- Keep preview configuration "warm" while recording

**Drawbacks**:
- Still requires stopping one before starting the other
- Uses more memory (two instances)
- More complex state management
- Minimal performance gain (reconfiguration is fast)

## Current Approach: Single Instance with Reconfiguration

### Why This Works Well

1. **No Hardware Conflict**: Only one stream active at a time
2. **Simpler State Management**: One instance to track
3. **Memory Efficient**: Single instance uses less RAM
4. **Fast Reconfiguration**: Picamera2 reconfiguration is optimized and fast
5. **Standard Practice**: This is the recommended approach for single-camera setups

### Current Optimization Strategy

**calibrate.py**:
- Preview-only mode
- Native hardware-accelerated preview (maximum FPS)
- No recording, so no reconfiguration needed

**experiment.py**:
- Recording-only mode during experiments
- Preview disabled to maximize recording FPS
- Optimized buffer settings (`buffer_count=2`)
- No preview/recording switching during experiment

## When Separate Instances Would Help

### Use Case 1: Live Preview During Experiment Setup
If you wanted to see a live preview while configuring the experiment (before recording starts):

```python
class ExperimentWindow:
    def __init__(self):
        # Preview instance for setup/configuration
        self.preview_cam = Picamera2()
        self.preview_cam.configure(
            self.preview_cam.create_preview_configuration(
                main={'size': (640, 480)},
                buffer_count=2
            )
        )
        self.preview_cam.start()
        # Show preview in GUI during setup
        
        # Recording instance (stopped until experiment starts)
        self.record_cam = Picamera2()
        # Configure when experiment starts
```

**Workflow**:
1. Preview instance runs during GUI configuration
2. When experiment starts: stop preview, configure recording instance, start recording
3. When experiment ends: stop recording, restart preview

**Benefit**: User can see camera view while setting up experiment
**Trade-off**: More complex, but might improve UX

### Use Case 2: Preview Between Wells
If you wanted to show preview between wells (not during recording):

```python
def run_loop():
    for well in wells:
        # Stop recording instance
        record_cam.stop()
        
        # Start preview instance briefly
        preview_cam.start()
        # Show preview for 1 second
        time.sleep(1)
        preview_cam.stop()
        
        # Restart recording instance
        record_cam.start()
        # Record at next well
```

**Benefit**: Visual feedback between wells
**Trade-off**: Adds delay, more complex state management

## Performance Comparison

### Single Instance (Current)
- **Memory**: ~50-100 MB for one instance
- **Reconfiguration Time**: ~50-200ms (negligible)
- **FPS Impact**: None (preview disabled during recording)
- **Complexity**: Low

### Dual Instance (Preview + Recording)
- **Memory**: ~100-200 MB for two instances
- **Switching Time**: ~50-200ms (same as reconfiguration)
- **FPS Impact**: None (only one active at a time)
- **Complexity**: Medium-High

## Recommendation

### For Current Use Case (experiment.py)
**Keep single instance approach** because:
1. ✅ Preview is not needed during recording (experiment runs automatically)
2. ✅ No reconfiguration overhead (configure once at start)
3. ✅ Simpler code, easier to maintain
4. ✅ Already optimized with `buffer_count=2`

### When to Consider Dual Instances
Consider separate instances if:
1. You want live preview during experiment **setup** (before recording)
2. You want preview between wells (with added delay)
3. You have multiple physical cameras
4. You need to avoid any reconfiguration overhead (rarely necessary)

## Implementation Example (If Needed)

If you wanted to add preview during setup:

```python
class ExperimentWindow:
    def __init__(self, parent, picam2, robocam):
        self.parent = parent
        self.robocam = robocam
        
        # Preview instance for setup
        self.preview_cam = Picamera2()
        self.preview_cam.configure(
            self.preview_cam.create_preview_configuration(
                main={'size': (640, 480)},
                buffer_count=2
            )
        )
        
        # Recording instance (will be configured on start)
        self.record_cam = picam2  # Use passed instance for recording
        
    def start(self):
        # Stop preview
        if self.preview_cam.started:
            self.preview_cam.stop()
        
        # Configure recording instance
        video_config = self.record_cam.create_video_configuration(
            main={'size': (res_x, res_y)},
            controls={'FrameRate': fps},
            buffer_count=2
        )
        self.record_cam.stop()
        self.record_cam.configure(video_config)
        self.record_cam.start()
        
        # Start experiment...
        
    def on_close(self):
        # Restart preview if needed
        if not self.preview_cam.started:
            self.preview_cam.start()
```

## Conclusion

For the current RoboCam-Suite use case:
- **Single instance is optimal** - no benefit from dual instances
- **Current optimization is sufficient** - `buffer_count=2`, preview disabled during recording
- **Dual instances would add complexity** without meaningful performance gain

The only reason to use dual instances would be for UX improvement (live preview during setup), which is a feature enhancement, not a performance optimization.

