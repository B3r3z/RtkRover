"""
Example script demonstrating loop navigation with GPS-RTK integration
This shows how to use the refactored navigation module with waypoint loops
"""
import logging
import time
from navigation.navigator import Navigator
from navigation.core.data_types import Waypoint, NavigationStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_basic_loop():
    """Example 1: Basic loop navigation"""
    logger.info("=" * 60)
    logger.info("Example 1: Basic Loop Navigation")
    logger.info("=" * 60)
    
    # Create navigator with loop mode enabled
    navigator = Navigator(
        loop_mode=True,
        waypoint_tolerance=0.5,
        max_speed=0.8
    )
    
    # Define waypoints (square pattern)
    waypoints = [
        Waypoint(lat=52.000, lon=21.000, name="Point A", tolerance=0.5),
        Waypoint(lat=52.001, lon=21.000, name="Point B", tolerance=0.5),
        Waypoint(lat=52.001, lon=21.001, name="Point C", tolerance=0.5),
        Waypoint(lat=52.000, lon=21.001, name="Point D", tolerance=0.5),
    ]
    
    # Set waypoint path
    navigator.set_waypoint_path(waypoints)
    navigator.start()
    
    logger.info(f"Loop mode enabled: {navigator.is_loop_mode()}")
    logger.info(f"Total waypoints: {len(waypoints)}")
    logger.info("Navigation started - will loop through waypoints continuously")
    
    return navigator


def example_runtime_control():
    """Example 2: Runtime loop mode control"""
    logger.info("\n" + "=" * 60)
    logger.info("Example 2: Runtime Loop Control")
    logger.info("=" * 60)
    
    # Create navigator without loop mode
    navigator = Navigator(loop_mode=False)
    
    waypoints = [
        Waypoint(lat=52.000, lon=21.000, name="WP1", tolerance=0.5),
        Waypoint(lat=52.001, lon=21.001, name="WP2", tolerance=0.5),
        Waypoint(lat=52.002, lon=21.002, name="WP3", tolerance=0.5),
    ]
    
    navigator.set_waypoint_path(waypoints)
    navigator.start()
    
    logger.info(f"Initial loop mode: {navigator.is_loop_mode()}")
    
    # Enable loop mode at runtime
    navigator.set_loop_mode(True)
    logger.info(f"Loop mode after enable: {navigator.is_loop_mode()}")
    
    # Disable loop mode
    navigator.set_loop_mode(False)
    logger.info(f"Loop mode after disable: {navigator.is_loop_mode()}")
    
    return navigator


def example_with_gps_simulation():
    """Example 3: Loop navigation with simulated GPS updates"""
    logger.info("\n" + "=" * 60)
    logger.info("Example 3: Loop Navigation with GPS Simulation")
    logger.info("=" * 60)
    
    navigator = Navigator(
        loop_mode=True,
        waypoint_tolerance=0.5,
        max_speed=0.8
    )
    
    # Define patrol route
    patrol_route = [
        Waypoint(lat=52.000, lon=21.000, name="Gate", tolerance=0.5),
        Waypoint(lat=52.001, lon=21.000, name="Corner 1", tolerance=0.5),
        Waypoint(lat=52.001, lon=21.001, name="Back wall", tolerance=0.5),
        Waypoint(lat=52.000, lon=21.001, name="Corner 2", tolerance=0.5),
    ]
    
    navigator.set_waypoint_path(patrol_route)
    navigator.start()
    
    logger.info("Simulating GPS-RTK updates for patrol route")
    logger.info(f"Starting position: {patrol_route[0].lat}, {patrol_route[0].lon}")
    
    # Simulate GPS updates
    current_lat = 52.000
    current_lon = 21.000
    current_heading = 0.0
    current_speed = 1.0  # m/s
    
    for i in range(10):
        # Update position (simulated GPS-RTK)
        navigator.update_position(
            lat=current_lat,
            lon=current_lon,
            heading=current_heading,  # VTG course over ground
            speed=current_speed       # VTG speed
        )
        
        # Get navigation command
        command = navigator.get_navigation_command()
        
        if command:
            logger.info(f"Step {i+1}: Speed={command.speed:.2f}, Turn={command.turn_rate:.2f}")
            
            # Simulate movement (very simplified)
            current_lat += 0.0001
            current_heading += 5.0
            
            # Check status
            state = navigator.get_state()
            if state.target_waypoint:
                logger.info(f"  Target: {state.target_waypoint.name}, "
                          f"Distance: {state.distance_to_target:.2f}m")
            
            # Show loop progress
            if navigator.is_loop_mode():
                logger.info(f"  Loops completed: {navigator.get_loop_count()}")
        else:
            logger.warning(f"Step {i+1}: No navigation command (possible error)")
            state = navigator.get_state()
            if state.error_message:
                logger.error(f"  Error: {state.error_message}")
        
        time.sleep(0.1)
    
    return navigator


def example_error_handling():
    """Example 4: GPS error handling"""
    logger.info("\n" + "=" * 60)
    logger.info("Example 4: GPS Error Handling")
    logger.info("=" * 60)
    
    navigator = Navigator(loop_mode=True)
    
    waypoints = [
        Waypoint(lat=52.000, lon=21.000, name="Start", tolerance=0.5),
        Waypoint(lat=52.001, lon=21.001, name="End", tolerance=0.5),
    ]
    
    navigator.set_waypoint_path(waypoints)
    navigator.start()
    
    # Scenario 1: No GPS position
    logger.info("\nScenario 1: Attempting navigation without GPS position")
    command = navigator.get_navigation_command()
    if command is None:
        state = navigator.get_state()
        logger.info(f"Status: {state.status.value}")
        logger.info(f"Error: {state.error_message}")
    
    # Scenario 2: GPS position available
    logger.info("\nScenario 2: GPS position acquired")
    navigator.update_position(lat=52.000, lon=21.000, heading=45.0, speed=1.0)
    command = navigator.get_navigation_command()
    if command:
        logger.info(f"Navigation command: Speed={command.speed:.2f}, Turn={command.turn_rate:.2f}")
        state = navigator.get_state()
        logger.info(f"Status: {state.status.value}")
    
    # Scenario 3: GPS dropout simulation
    logger.info("\nScenario 3: GPS dropout (simulated by not updating position)")
    time.sleep(2.5)  # Wait for position to become stale (>2 seconds)
    command = navigator.get_navigation_command()
    if command is None:
        state = navigator.get_state()
        logger.info(f"Status: {state.status.value}")
        logger.info(f"Error: {state.error_message}")
    
    return navigator


def example_integration_with_rover():
    """Example 5: Integration with RoverManager (pseudo-code)"""
    logger.info("\n" + "=" * 60)
    logger.info("Example 5: Integration with RoverManager")
    logger.info("=" * 60)
    
    logger.info("Pseudo-code for RoverManager integration:")
    logger.info("""
# Initialize rover with RTK GPS
rover = RoverManager(rtk_manager=rtk)

# Enable loop mode on navigator
rover.navigator.set_loop_mode(True)

# Define waypoints
waypoints = [
    Waypoint(lat=52.000, lon=21.000, name="Start"),
    Waypoint(lat=52.001, lon=21.001, name="Middle"),
    Waypoint(lat=52.002, lon=21.002, name="End"),
]

# Set path and start
rover.navigator.set_waypoint_path(waypoints)
rover.start()

# GPS updates will be handled automatically by RTK manager
# through the PositionObserver interface

# Monitor loop progress
while rover.navigator.is_loop_mode():
    state = rover.navigator.get_state()
    loops = rover.navigator.get_loop_count()
    print(f"Loop {loops + 1}, Target: {state.target_waypoint.name}")
    time.sleep(1)
    """)


def main():
    """Run all examples"""
    logger.info("\n" + "=" * 60)
    logger.info("LOOP NAVIGATION EXAMPLES")
    logger.info("Demonstrating refactored navigation module")
    logger.info("=" * 60)
    
    # Run examples
    example_basic_loop()
    example_runtime_control()
    example_with_gps_simulation()
    example_error_handling()
    example_integration_with_rover()
    
    logger.info("\n" + "=" * 60)
    logger.info("All examples completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
