# Navigation Module - Waypoint Loop Feature

## Overview

The navigation module now supports **loop navigation**, enabling the rover to continuously cycle through a set of waypoints. This is ideal for automated patrol routes, perimeter monitoring, and repetitive tasks.

## Features

### Loop Mode
- **Continuous Navigation**: The rover automatically cycles back to the first waypoint after reaching the last one
- **Loop Counter**: Tracks the number of complete loops for monitoring and analytics
- **Runtime Toggle**: Loop mode can be enabled/disabled at any time
- **GPS-RTK Integration**: Full integration with GPS-RTK positioning and VTG heading
- **Error Resilient**: Handles GPS dropouts and communication errors gracefully

### Navigation Modes

1. **Single Waypoint Mode** (default)
   - Navigate to one waypoint and stop
   - Status: `IDLE` → `NAVIGATING` → `REACHED_WAYPOINT` → `IDLE`

2. **Path Following Mode** (sequential)
   - Navigate through multiple waypoints in order
   - Stops after reaching the last waypoint
   - Status: `NAVIGATING` → `REACHED_WAYPOINT` → `PATH_COMPLETE`

3. **Loop Mode** (continuous)
   - Navigate through waypoints continuously
   - Cycles back to first waypoint after reaching the last
   - Never reaches `PATH_COMPLETE` status
   - Status: `NAVIGATING` → `REACHED_WAYPOINT` → `NAVIGATING` (repeats)

## Usage

### Basic Loop Navigation

```python
from navigation.navigator import Navigator
from navigation.core.data_types import Waypoint

# Create navigator with loop mode enabled
navigator = Navigator(loop_mode=True)

# Define waypoints
waypoints = [
    Waypoint(lat=52.0, lon=21.0, name="Point 1", tolerance=0.5),
    Waypoint(lat=52.01, lon=21.01, name="Point 2", tolerance=0.5),
    Waypoint(lat=52.02, lon=21.02, name="Point 3", tolerance=0.5),
]

# Set waypoint path with loop mode
navigator.set_waypoint_path(waypoints, loop_mode=True)
navigator.start()
```

### Runtime Control

```python
# Enable loop mode at runtime
navigator.set_loop_mode(True)

# Disable loop mode
navigator.set_loop_mode(False)

# Check if loop mode is active
is_looping = navigator.is_loop_mode()

# Get loop count
loops_completed = navigator.get_loop_count()
```

### Override Loop Mode for Specific Path

```python
# Navigator initialized without loop mode
navigator = Navigator(loop_mode=False)

# Set specific path with loop mode enabled
navigator.set_waypoint_path(waypoints, loop_mode=True)

# Or disable loop for this path
navigator.set_waypoint_path(waypoints, loop_mode=False)
```

## Integration with Rover Manager

The loop mode integrates seamlessly with the existing RoverManager:

```python
from rover_manager import RoverManager
from navigation.core.data_types import Waypoint

# Initialize rover with RTK GPS
rover = RoverManager(rtk_manager=rtk)

# Enable loop mode on navigator
rover.navigator.set_loop_mode(True)

# Add waypoints and start
rover.navigator.set_waypoint_path(waypoints)
rover.start()
```

## GPS-RTK and VTG Integration

The navigation system leverages GPS-RTK for high-precision positioning and VTG sentences for accurate heading:

### VTG (Course Over Ground)
- **Primary Heading Source**: VTG provides real-time course over ground
- **Speed Validation**: Heading is validated against GPS speed
- **Fallback**: If VTG unavailable, heading is calculated from position changes

### GPS-RTK Positioning
- **2-3 cm Accuracy**: High-precision positioning via NTRIP corrections
- **Waypoint Tolerance**: Configurable tolerance (default 0.5m) for waypoint detection
- **Position Staleness Check**: Detects GPS dropouts (>2 seconds without update)

### Example with GPS Updates

```python
# GPS position callback (called by RTK manager)
def on_gps_update(lat, lon, heading, speed):
    # Update navigator with GPS-RTK data
    navigator.update_position(
        lat=lat,           # RTK latitude (high precision)
        lon=lon,           # RTK longitude (high precision)
        heading=heading,   # VTG course over ground
        speed=speed        # VTG speed (m/s)
    )
    
    # Get navigation command
    command = navigator.get_navigation_command()
    if command:
        # Send to motor controller
        motor_controller.execute_command(command)
```

## Error Handling

The navigation system handles various GPS and communication errors:

### GPS Signal Loss
```python
# Automatic detection of stale GPS data (>2 seconds old)
# Navigator returns None and sets ERROR status
command = navigator.get_navigation_command()
if command is None:
    state = navigator.get_state()
    if state.status == NavigationStatus.ERROR:
        print(f"Error: {state.error_message}")
```

### Heading Loss
```python
# If VTG heading unavailable, enters CALIBRATING phase
# Robot drives straight to acquire heading from movement
# Automatically transitions to normal navigation when heading acquired
```

### Communication Interruption
```python
# Pause navigation during communication issues
navigator.pause()

# Resume when connection restored
navigator.resume()

# Loop mode preserves state across pause/resume
```

## State Machine

The navigation system uses a state machine for robust waypoint following:

```
IDLE → CALIBRATING → ALIGNING → DRIVING → REACHED
         ↓              ↑           ↓
         └──────────────┴───────────┘
         (re-enter ALIGNING if heading error > threshold)
```

### States

1. **IDLE**: No target, waiting for waypoint
2. **CALIBRATING**: Acquiring initial heading (if VTG unavailable)
3. **ALIGNING**: Rotating in place to face target
4. **DRIVING**: Moving forward toward target with minor corrections
5. **REACHED**: Waypoint reached, advancing to next (or cycling in loop mode)

## Configuration

### Navigator Parameters

```python
Navigator(
    max_speed=1.0,                    # Maximum speed (0.0-1.0)
    turn_aggressiveness=0.5,          # Turn intensity (0.0-1.0)
    waypoint_tolerance=0.5,           # Waypoint reach threshold (meters)
    align_tolerance=15.0,             # Heading error to exit ALIGN (degrees)
    realign_threshold=30.0,           # Heading error to re-enter ALIGN (degrees)
    align_speed=0.4,                  # Speed during rotation (0.0-1.0)
    align_timeout=10.0,               # Max time in ALIGN phase (seconds)
    drive_correction_gain=0.02,       # Proportional gain for corrections
    loop_mode=False                   # Enable continuous loop navigation
)
```

### Waypoint Configuration

```python
Waypoint(
    lat=52.0,                         # Latitude (decimal degrees)
    lon=21.0,                         # Longitude (decimal degrees)
    name="Waypoint 1",                # Optional name
    tolerance=0.5,                    # Reach threshold (meters)
    speed_limit=None,                 # Optional speed limit (m/s)
    altitude=None                     # Optional altitude (meters)
)
```

## Monitoring and Telemetry

### Navigation State

```python
state = navigator.get_state()

print(f"Mode: {state.mode.value}")
print(f"Status: {state.status.value}")
print(f"Position: {state.current_position}")
print(f"Target: {state.target_waypoint.name}")
print(f"Distance: {state.distance_to_target:.2f}m")
print(f"Bearing: {state.bearing_to_target:.1f}°")
print(f"Heading: {state.current_heading:.1f}°")
print(f"Speed: {state.current_speed:.2f} m/s")
print(f"Waypoints remaining: {state.waypoints_remaining}")
```

### Loop Tracking

```python
if navigator.is_loop_mode():
    loops = navigator.get_loop_count()
    print(f"Completed loops: {loops}")
```

## Best Practices

### 1. Waypoint Spacing
- Space waypoints at least 2-3 meters apart for reliable navigation
- Use larger tolerance (0.5-1.0m) for RTK positioning
- Consider rover turning radius when planning paths

### 2. GPS Signal Quality
- Ensure clear sky view for GPS-RTK
- Monitor RTK fix status (FLOAT vs FIXED)
- Handle GPS dropouts gracefully with error checking

### 3. Loop Safety
- Always implement emergency stop functionality
- Set reasonable loop count limits for testing
- Monitor battery level during continuous operation

### 4. Performance Tuning
- Adjust `align_tolerance` for faster/slower alignment
- Tune `drive_correction_gain` for path tracking accuracy
- Modify `align_speed` based on rover stability

## Testing

### Unit Tests
```bash
# Test waypoint loop functionality
python3 -m unittest navigation.test_waypoint_loop -v

# Test GPS error handling
python3 -m unittest navigation.test_gps_error_handling -v
```

### Integration Test
```python
# Test complete loop with simulated GPS
navigator = Navigator(loop_mode=True)
waypoints = [...]
navigator.set_waypoint_path(waypoints)
navigator.start()

# Simulate GPS updates
for i in range(100):
    navigator.update_position(lat, lon, heading, speed)
    command = navigator.get_navigation_command()
    # Process command...
```

## Troubleshooting

### Loop Not Starting
- Check that waypoints are added: `navigator.waypoint_manager.has_waypoints()`
- Verify loop mode enabled: `navigator.is_loop_mode()`
- Ensure navigator is started: `navigator.start()`

### GPS Heading Issues
- Verify VTG is enabled in GPS configuration
- Check GPS speed > 0.5 m/s for reliable heading
- Use calibration mode for initial heading acquisition

### Waypoint Not Reached
- Check waypoint tolerance (increase if needed)
- Verify GPS position accuracy (RTK FIXED vs FLOAT)
- Monitor distance to target: `state.distance_to_target`

## References

- [GPS-RTK Documentation](https://rtklibexplorer.wordpress.com/)
- [NMEA VTG Sentence](https://www.tronico.fi/OH6NT/docs/NMEA0183.pdf)
- Navigation Architecture: `NAVIGATION_ARCHITECTURE.md`
- Integration Guide: `INTEGRATION_CHECKLIST.md`
