"""
Rover Manager - Main integration class
Coordinates GPS, Navigation, and Motor Control systems
"""
import logging
import threading
import time
from typing import Optional
from datetime import datetime

from gps.core.interfaces import PositionObserver, Position
from navigation.navigator import Navigator
from navigation.core.data_types import Waypoint, NavigationMode
from motor_control.motor_controller import MotorController
from motor_control.drivers.l298n_driver import L298NDriver
from config.motor_settings import motor_gpio_pins, motor_config, navigation_config

logger = logging.getLogger(__name__)


class RoverManager(PositionObserver):
    """
    Central manager coordinating all rover subsystems
    Implements the main control loop
    """
    
    def __init__(self, rtk_manager=None):
        """
        Initialize Rover Manager
        
        Args:
            rtk_manager: RTK GPS manager instance
        """
        self.rtk_manager = rtk_manager
        
        # Initialize subsystems
        self.navigator = Navigator(
            max_speed=navigation_config['max_speed'],
            turn_aggressiveness=navigation_config['turn_aggressiveness'],
            waypoint_tolerance=navigation_config['waypoint_tolerance']
        )
        
        # Initialize motor driver
        motor_driver = L298NDriver(
            gpio_pins=motor_gpio_pins,
            use_gpio=motor_config['use_gpio']
        )
        
        self.motor_controller = MotorController(
            motor_driver=motor_driver,
            max_speed=motor_config['max_speed'],
            turn_sensitivity=motor_config['turn_sensitivity'],
            safety_timeout=motor_config['safety_timeout']
        )
        
        # Control loop
        self._control_thread: Optional[threading.Thread] = None
        self._stop_control = threading.Event()
        self._is_running = False
        self._update_rate = navigation_config['update_rate']
        
        # Register as GPS position observer
        if self.rtk_manager:
            self.rtk_manager.add_position_observer(self)
        
        logger.info("Rover Manager initialized")
    
    def start(self) -> bool:
        """Start all rover systems"""
        if self._is_running:
            logger.warning("Rover already running")
            return False
        
        try:
            # Start motor controller
            if not self.motor_controller.start():
                logger.error("Failed to start motor controller")
                return False
            
            # Start navigator
            if not self.navigator.start():
                logger.error("Failed to start navigator")
                self.motor_controller.stop()
                return False
            
            # Start control loop
            self._is_running = True
            self._stop_control.clear()
            self._control_thread = threading.Thread(target=self._control_loop, daemon=True)
            self._control_thread.start()
            
            logger.info("Rover started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start rover: {e}", exc_info=True)
            self.stop()
            return False
    
    def stop(self):
        """Stop all rover systems"""
        if not self._is_running:
            return
        
        logger.info("Stopping rover...")
        
        self._is_running = False
        self._stop_control.set()
        
        # Wait for control thread
        if self._control_thread:
            self._control_thread.join(timeout=2.0)
        
        # Stop subsystems
        self.navigator.stop()
        self.motor_controller.stop()
        
        logger.info("Rover stopped")
    
    def on_position_update(self, position: Position):
        """
        Callback from GPS system when position updates
        
        Args:
            position: New GPS position
        """
        # Extract heading from position if available
        # You may need to add heading to Position dataclass
        heading = getattr(position, 'heading', None)
        speed = getattr(position, 'speed', None)
        
        # Update navigator with new position
        self.navigator.update_position(
            lat=position.lat,
            lon=position.lon,
            heading=heading,
            speed=speed
        )
        
        logger.debug(f"Position updated: ({position.lat:.6f}, {position.lon:.6f})")
    
    def _control_loop(self):
        """
        Main control loop
        Runs at regular intervals to generate and execute navigation commands
        """
        logger.info("Control loop started")
        
        while not self._stop_control.wait(timeout=self._update_rate):
            try:
                # Get navigation command
                nav_command = self.navigator.get_navigation_command()
                
                if nav_command:
                    # Execute command via motor controller
                    self.motor_controller.execute_navigation_command(nav_command)
                else:
                    # No command - ensure motors are stopped
                    self.motor_controller.emergency_stop()
                
            except Exception as e:
                logger.error(f"Error in control loop: {e}", exc_info=True)
                # Safety: stop motors on error
                try:
                    self.motor_controller.emergency_stop()
                except:
                    pass
        
        logger.info("Control loop stopped")
    
    # High-level navigation commands
    
    def go_to_waypoint(self, lat: float, lon: float, name: str = None) -> bool:
        """
        Navigate to single waypoint
        
        Args:
            lat: Target latitude
            lon: Target longitude
            name: Optional waypoint name
            
        Returns:
            True if waypoint set successfully
        """
        try:
            waypoint = Waypoint(lat=lat, lon=lon, name=name)
            self.navigator.set_target(waypoint)
            logger.info(f"Navigating to waypoint: {name or 'Unnamed'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set waypoint: {e}")
            return False
    
    def follow_path(self, waypoints: list) -> bool:
        """
        Follow path of multiple waypoints
        
        Args:
            waypoints: List of (lat, lon) tuples or Waypoint objects
            
        Returns:
            True if path set successfully
        """
        try:
            wp_objects = []
            for i, wp in enumerate(waypoints):
                if isinstance(wp, Waypoint):
                    wp_objects.append(wp)
                elif isinstance(wp, (tuple, list)) and len(wp) >= 2:
                    wp_objects.append(Waypoint(lat=wp[0], lon=wp[1], name=f"WP{i+1}"))
                else:
                    logger.warning(f"Invalid waypoint format at index {i}: {wp}")
                    continue
            
            if wp_objects:
                self.navigator.set_waypoint_path(wp_objects)
                logger.info(f"Following path with {len(wp_objects)} waypoints")
                return True
            else:
                logger.error("No valid waypoints provided")
                return False
                
        except Exception as e:
            logger.error(f"Failed to set path: {e}")
            return False
    
    def pause_navigation(self):
        """Pause navigation (motors stop but waypoints retained)"""
        self.navigator.pause()
        self.motor_controller.emergency_stop()
        logger.info("Navigation paused")
    
    def resume_navigation(self):
        """Resume navigation"""
        self.navigator.resume()
        logger.info("Navigation resumed")
    
    def cancel_navigation(self):
        """Cancel current navigation"""
        self.navigator.stop()
        self.motor_controller.emergency_stop()
        logger.info("Navigation cancelled")
    
    def emergency_stop(self):
        """Emergency stop - immediately halt all movement"""
        logger.warning("EMERGENCY STOP activated")
        self.motor_controller.emergency_stop()
        self.navigator.pause()
    
    # Status and monitoring
    
    def get_rover_status(self) -> dict:
        """Get comprehensive rover status"""
        nav_state = self.navigator.get_state()
        motor_status = self.motor_controller.get_status()
        
        gps_position = None
        if self.rtk_manager:
            gps_position = self.rtk_manager.get_current_position()
        
        return {
            'is_running': self._is_running,
            'timestamp': datetime.now().isoformat(),
            'navigation': nav_state.to_dict(),
            'motor_control': motor_status,
            'gps': gps_position
        }
    
    def get_waypoints(self) -> list:
        """Get all waypoints"""
        return [wp.to_dict() for wp in self.navigator.get_waypoints()]
    
    def add_waypoint(self, lat: float, lon: float, name: str = None) -> bool:
        """Add waypoint to queue"""
        try:
            waypoint = Waypoint(lat=lat, lon=lon, name=name)
            self.navigator.add_waypoint(waypoint)
            return True
        except Exception as e:
            logger.error(f"Failed to add waypoint: {e}")
            return False
    
    def clear_waypoints(self):
        """Clear all waypoints"""
        self.navigator.clear_waypoints()
        logger.info("All waypoints cleared")
    
    def set_max_speed(self, speed: float):
        """Set maximum speed (0.0 to 1.0)"""
        self.motor_controller.set_max_speed(speed)
        logger.info(f"Max speed set to {speed:.2f}")
    
    # Direct motor control (for manual operation)
    
    def manual_drive(self, left_speed: float, right_speed: float):
        """
        Direct motor control (bypasses navigation)
        
        Args:
            left_speed: Left motor speed (-1.0 to 1.0)
            right_speed: Right motor speed (-1.0 to 1.0)
        """
        from motor_control.motor_interface import DifferentialDriveCommand
        
        # Validate speeds
        left_speed = max(-1.0, min(1.0, left_speed))
        right_speed = max(-1.0, min(1.0, right_speed))
        
        command = DifferentialDriveCommand(
            left_speed=left_speed,
            right_speed=right_speed
        )
        
        self.motor_controller.execute_differential_command(command)
        logger.info(f"Manual drive: L={left_speed:.2f}, R={right_speed:.2f}")
    
    def manual_move(self, speed: float, turn_rate: float = 0.0):
        """
        Manual movement with speed and turn rate
        
        Args:
            speed: Forward/backward speed (-1.0 to 1.0)
            turn_rate: Turn rate (-1.0 left to 1.0 right)
        """
        from navigation.core.data_types import NavigationCommand
        from datetime import datetime
        
        # Validate inputs
        speed = max(-1.0, min(1.0, speed))
        turn_rate = max(-1.0, min(1.0, turn_rate))
        
        nav_command = NavigationCommand(
            speed=speed,
            turn_rate=turn_rate,
            timestamp=datetime.now()
        )
        
        self.motor_controller.execute_navigation_command(nav_command)
        logger.info(f"Manual move: speed={speed:.2f}, turn={turn_rate:.2f}")
    
    def stop_motors(self):
        """Stop all motors (does not cancel navigation)"""
        self.motor_controller.emergency_stop()
        logger.info("Motors stopped")
