#!/usr/bin/env python3
"""
Demo script to show enhanced navigation logging
"""

import sys
import logging
from datetime import datetime

# Setup logging to see the output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Add path
sys.path.insert(0, '/home/runner/work/RtkRover/RtkRover')

from navigation.navigator import Navigator
from navigation.core.data_types import Waypoint

def demo_logging():
    """Demonstrate the enhanced logging"""
    print("=" * 70)
    print("ENHANCED NAVIGATION LOGGING DEMO")
    print("=" * 70)
    print()
    
    # Create navigator
    nav = Navigator(
        max_speed=1.0,
        turn_aggressiveness=0.5,
        waypoint_tolerance=2.0
    )
    
    print("\n--- Demo 1: Single Waypoint Navigation ---\n")
    
    # Set a single target waypoint
    wp1 = Waypoint(lat=52.230, lon=21.010, name="Target Point A", tolerance=2.0)
    nav.set_target(wp1)
    
    # Simulate position updates showing distance progress
    print("\nSimulating position updates:")
    positions = [
        (52.220, 21.000, 50.0),  # ~50m away
        (52.225, 21.005, 25.0),  # ~25m away
        (52.228, 21.008, 10.0),  # ~10m away
        (52.229, 21.009, 5.0),   # ~5m away
        (52.2299, 21.0099, 2.0), # ~2m away (approaching)
        (52.230, 21.010, 0.5),   # Reached!
    ]
    
    for lat, lon, expected_dist in positions:
        nav.update_position(lat, lon, heading=90.0, speed=1.0)
        cmd = nav.get_navigation_command()
        if cmd:
            state = nav.get_state()
            if state.distance_to_target:
                print(f"  Position: ({lat:.4f}, {lon:.4f}) - Distance: {state.distance_to_target:.1f}m")
    
    print("\n--- Demo 2: Path Following ---\n")
    
    # Reset navigator
    nav.stop()
    nav.start()
    
    # Create a path with multiple waypoints
    waypoints = [
        Waypoint(lat=52.240, lon=21.020, name="Point 1", tolerance=2.0),
        Waypoint(lat=52.250, lon=21.030, name="Point 2", tolerance=2.0),
        Waypoint(lat=52.260, lon=21.040, name="Point 3", tolerance=2.0),
    ]
    
    nav.set_waypoint_path(waypoints)
    
    # Simulate reaching first waypoint
    print("\nSimulating reaching waypoints:")
    nav.update_position(52.240, 21.020, heading=90.0, speed=1.0)
    cmd = nav.get_navigation_command()
    
    # Simulate reaching second waypoint
    nav.update_position(52.250, 21.030, heading=90.0, speed=1.0)
    cmd = nav.get_navigation_command()
    
    # Simulate reaching third waypoint
    nav.update_position(52.260, 21.040, heading=90.0, speed=1.0)
    cmd = nav.get_navigation_command()
    
    print("\n--- Demo 3: Pause and Resume ---\n")
    
    # Set new target
    wp2 = Waypoint(lat=52.270, lon=21.050, name="Target Point B", tolerance=2.0)
    nav.set_target(wp2)
    
    # Pause navigation
    nav.pause()
    
    # Resume navigation
    nav.resume()
    
    print("\n--- Demo 4: Waypoint Manager Operations ---\n")
    
    # Clear waypoints
    nav.clear_waypoints()
    
    # Add waypoints one by one
    nav.add_waypoint(Waypoint(lat=52.280, lon=21.060, name="WP Alpha", tolerance=2.0))
    nav.add_waypoint(Waypoint(lat=52.290, lon=21.070, name="WP Beta", tolerance=2.0))
    nav.add_waypoint(Waypoint(lat=52.300, lon=21.080, name="WP Gamma", tolerance=2.0))
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE - Check the logs above for enhanced navigation logging")
    print("=" * 70)
    print("\nKey improvements:")
    print("  • 🎯 Clear waypoint targeting messages")
    print("  • 🚗 Distance progress logging at key milestones")
    print("  • ✅ Waypoint reached confirmations")
    print("  • 📍 Path following progress tracking")
    print("  • ⏸️ / ▶️  Pause/resume status")
    print("  • 🏁 Navigation completion messages")

if __name__ == "__main__":
    demo_logging()
