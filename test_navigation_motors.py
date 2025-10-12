"""
Example script demonstrating navigation and motor control

This script shows how to use the navigation and motor control systems
"""
import sys
import time
import logging
from navigation.navigator import Navigator
from navigation.core.data_types import Waypoint
from motor_control.motor_controller import MotorController
from motor_control.drivers.l298n_driver import L298NDriver
from config.motor_settings import motor_gpio_pins, motor_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_motor_control():
    """Test motor control in simulation mode"""
    logger.info("=== Testing Motor Control ===")
    
    # Initialize motor driver in simulation mode
    driver = L298NDriver(gpio_pins=motor_gpio_pins, use_gpio=False)
    controller = MotorController(motor_driver=driver, max_speed=0.5)
    
    # Start controller
    if not controller.start():
        logger.error("Failed to start motor controller")
        return
    
    try:
        # Test forward movement
        logger.info("Test 1: Moving forward")
        from navigation.core.data_types import NavigationCommand
        from datetime import datetime
        
        cmd = NavigationCommand(speed=0.5, turn_rate=0.0, timestamp=datetime.now())
        controller.execute_navigation_command(cmd)
        time.sleep(2)
        
        # Test turning right
        logger.info("Test 2: Turning right")
        cmd = NavigationCommand(speed=0.3, turn_rate=0.5, timestamp=datetime.now())
        controller.execute_navigation_command(cmd)
        time.sleep(2)
        
        # Test turning left
        logger.info("Test 3: Turning left")
        cmd = NavigationCommand(speed=0.3, turn_rate=-0.5, timestamp=datetime.now())
        controller.execute_navigation_command(cmd)
        time.sleep(2)
        
        # Stop
        logger.info("Test 4: Stopping")
        controller.emergency_stop()
        time.sleep(1)
        
    finally:
        controller.stop()
    
    logger.info("Motor control test complete\n")


def test_navigation():
    """Test navigation system"""
    logger.info("=== Testing Navigation System ===")
    
    # Initialize navigator
    nav = Navigator(max_speed=1.0, turn_aggressiveness=0.7, waypoint_tolerance=2.0)
    nav.start()
    
    try:
        # Set simulated current position (Warsaw)
        nav.update_position(lat=52.2297, lon=21.0122, heading=0.0)
        logger.info("Current position set to Warsaw")
        
        # Set target waypoint (100m north)
        target = Waypoint(lat=52.2307, lon=21.0122, name="North Target")
        nav.set_target(target)
        logger.info(f"Target set: {target.name}")
        
        # Simulate navigation loop
        for i in range(5):
            # Get navigation command
            cmd = nav.get_navigation_command()
            
            if cmd:
                logger.info(f"Step {i+1}: speed={cmd.speed:.2f}, turn={cmd.turn_rate:.2f}")
                
                # Get current state
                state = nav.get_state()
                logger.info(f"  Distance to target: {state.distance_to_target:.1f}m")
                logger.info(f"  Bearing: {state.bearing_to_target:.1f}°")
            else:
                logger.info("No navigation command")
            
            time.sleep(1)
            
            # Simulate movement (move slightly north each iteration)
            current_pos = nav.get_state().current_position
            if current_pos:
                new_lat = current_pos[0] + 0.0001
                nav.update_position(lat=new_lat, lon=current_pos[1], heading=0.0)
        
    finally:
        nav.stop()
    
    logger.info("Navigation test complete\n")


def test_waypoint_path():
    """Test following a path of waypoints"""
    logger.info("=== Testing Waypoint Path ===")
    
    nav = Navigator()
    nav.start()
    
    try:
        # Set starting position
        nav.update_position(lat=52.2297, lon=21.0122, heading=0.0)
        
        # Define a simple path (square around starting point)
        waypoints = [
            Waypoint(lat=52.2307, lon=21.0122, name="North"),
            Waypoint(lat=52.2307, lon=21.0132, name="Northeast"),
            Waypoint(lat=52.2297, lon=21.0132, name="East"),
            Waypoint(lat=52.2297, lon=21.0122, name="Home"),
        ]
        
        nav.set_waypoint_path(waypoints)
        logger.info(f"Path set with {len(waypoints)} waypoints")
        
        # Get state
        state = nav.get_state()
        logger.info(f"Mode: {state.mode.value}")
        logger.info(f"Status: {state.status.value}")
        logger.info(f"Waypoints remaining: {state.waypoints_remaining}")
        
        if state.target_waypoint:
            logger.info(f"Next waypoint: {state.target_waypoint.name}")
        
    finally:
        nav.stop()
    
    logger.info("Waypoint path test complete\n")


def main():
    """Run all tests"""
    logger.info("Starting Navigation and Motor Control Tests\n")
    
    try:
        test_motor_control()
        test_navigation()
        test_waypoint_path()
        
        logger.info("All tests completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("\nTests interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


if __name__ == '__main__':
    main()
