"""Main navigation system implementation"""
import logging
from typing import Optional, List
from datetime import datetime
import threading
import math

from .types import (
    Waypoint, NavigationCommand, NavigationState,
    NavigationMode, NavigationStatus, NavigationPhase
)
from .geo_utils import GeoUtils
from .pid_controller import PIDController

logger = logging.getLogger(__name__)

class WaypointManager:
    """Simple FIFO waypoint queue manager"""
    
    def __init__(self):
        self._waypoints: List[Waypoint] = []
        self._current_index = 0
    
    def add_waypoint(self, waypoint: Waypoint):
        """Add waypoint to end of queue"""
        self._waypoints.append(waypoint)
        position = len(self._waypoints)
        logger.info(f"Added waypoint #{position}: '{waypoint.name or 'Unnamed'}' at ({waypoint.lat:.6f}, {waypoint.lon:.6f})")
    
    def get_next_waypoint(self) -> Optional[Waypoint]:
        """Get next waypoint in queue without removing it"""
        if self._current_index < len(self._waypoints):
            return self._waypoints[self._current_index]
        return None
    
    def advance_to_next(self) -> bool:
        """Move to next waypoint in queue"""
        if self._current_index < len(self._waypoints) - 1:
            self._current_index += 1
            current_wp = self._waypoints[self._current_index]
            logger.info(f"Advanced to waypoint #{self._current_index + 1}/{len(self._waypoints)}: '{current_wp.name or 'Unnamed'}'")
            return True
        return False
    
    def clear_waypoints(self):
        """Clear all waypoints"""
        count = len(self._waypoints)
        self._waypoints.clear()
        self._current_index = 0
        logger.info(f"Cleared {count} waypoint(s) from queue")
    
    def get_all_waypoints(self) -> List[Waypoint]:
        """Get all waypoints in queue"""
        return self._waypoints.copy()
    
    def get_remaining_count(self) -> int:
        """Get number of waypoints remaining (including current)"""
        return max(0, len(self._waypoints) - self._current_index)
    
    def has_waypoints(self) -> bool:
        """Check if there are any waypoints in the queue"""
        return len(self._waypoints) > 0

class Navigator:
    """
    Main navigation system implementation
    Coordinates GPS position, waypoint management, and generates navigation commands
    """
    
    def __init__(self, 
                 max_speed: float = 1.0,
                 turn_aggressiveness: float = 0.5,
                 waypoint_tolerance: float = 1.0,
                 drive_correction_gain: float = 0.05):
        """
        Initialize navigator
        """
        # Components
        self.geo_utils = GeoUtils()
        self.waypoint_manager = WaypointManager()
        
        # PID controller for smooth heading control
        # KP=0.02 means 10 deg error -> 0.2 turn rate
        self.heading_pid = PIDController(kp=0.02, ki=0.001, kd=0.01, output_limits=(-1.0, 1.0))
        
        # Configuration
        self.max_speed = max_speed
        self.turn_aggressiveness = turn_aggressiveness
        self.default_tolerance = waypoint_tolerance
        self.drive_correction_gain = drive_correction_gain
        
        # State
        self._current_position: Optional[tuple] = None  # (lat, lon)
        self._current_heading: Optional[float] = None  # degrees
        self._current_speed: Optional[float] = None  # m/s
        self._target_waypoint: Optional[Waypoint] = None
        self._last_position_time: Optional[datetime] = None
        
        self._mode = NavigationMode.IDLE
        self._status = NavigationStatus.IDLE
        self._is_running = False
        self._is_paused = False
        self._error_message: Optional[str] = None
        
        # Thread safety
        self._lock = threading.Lock()
        
        logger.info("Navigator initialized")

    def update_position(self, lat: float, lon: float, heading: Optional[float] = None, speed: Optional[float] = None):
        """Update current position from GPS"""
        with self._lock:
            previous_position = self._current_position
            self._current_position = (lat, lon)
            self._last_position_time = datetime.now()
            
            # Priority 1: Use GPS heading (course over ground) when available
            if heading is not None:
                self._current_heading = heading
            # Priority 2: Calculate heading from movement (if moving and have previous position)
            elif previous_position and speed is not None and speed > 0.5:
                # Only calculate if robot is moving (speed > 0.5 m/s)
                calculated_heading = self.geo_utils.calculate_bearing(
                    previous_position[0], previous_position[1],
                    lat, lon
                )
                self._current_heading = calculated_heading
            
            if speed is not None:
                self._current_speed = speed
            
            # logger.debug(f"Position updated: ({lat:.6f}, {lon:.6f}), heading: {self._current_heading}, speed: {speed}")
    
    def _is_position_stale(self, max_age_seconds: float = 2.0) -> bool:
        """Check if current position is too old"""
        if not self._last_position_time:
            return True
        
        age = (datetime.now() - self._last_position_time).total_seconds()
        return age > max_age_seconds
    
    def set_target(self, waypoint: Waypoint):
        """Set single target waypoint and auto-start navigation"""
        with self._lock:
            self._target_waypoint = waypoint
            self._mode = NavigationMode.WAYPOINT
            self._status = NavigationStatus.NAVIGATING
            
            # Reset PID
            self.heading_pid.reset()
            
            # Auto-start if not running
            if not self._is_running:
                self._is_running = True
                self._is_paused = False
            
            logger.info(f"Target set: {waypoint.name or 'Unnamed'} at ({waypoint.lat:.6f}, {waypoint.lon:.6f})")
    
    def set_waypoint_path(self, waypoints: list):
        """Set multiple waypoints for path following"""
        with self._lock:
            self.waypoint_manager.clear_waypoints()
            for wp in waypoints:
                self.waypoint_manager.add_waypoint(wp)
            
            # Set first waypoint as target
            self._target_waypoint = self.waypoint_manager.get_next_waypoint()
            if self._target_waypoint:
                self._mode = NavigationMode.PATH_FOLLOWING
                self._status = NavigationStatus.NAVIGATING
                self.heading_pid.reset()
                
                logger.info(f"Path set with {len(waypoints)} waypoints")
    
    def get_navigation_command(self) -> Optional[NavigationCommand]:
        """
        Calculate navigation command based on current state
        """
        with self._lock:
            # Check if we can navigate
            if not self._is_running or self._is_paused:
                return None
            
            if not self._current_position:
                self._status = NavigationStatus.ERROR
                return None
            
            if self._is_position_stale():
                self._status = NavigationStatus.ERROR
                return None
            
            if not self._target_waypoint:
                self._status = NavigationStatus.IDLE
                return NavigationCommand(speed=0.0, turn_rate=0.0, timestamp=datetime.now())
            
            # Calculate control output
            return self._compute_control_output()
            
    def _compute_control_output(self) -> NavigationCommand:
        """
        Compute speed and turn rate to reach target
        Strategy: Drive to Orient
        """
        current_lat, current_lon = self._current_position
        
        # Calculate distance and bearing to target
        distance = self.geo_utils.haversine_distance(
            current_lat, current_lon,
            self._target_waypoint.lat, self._target_waypoint.lon
        )
        
        bearing_to_target = self.geo_utils.calculate_bearing(
            current_lat, current_lon,
            self._target_waypoint.lat, self._target_waypoint.lon
        )
        
        # Check if waypoint reached
        if distance <= self._target_waypoint.tolerance:
            return self._handle_waypoint_reached()
        
        # If heading is unknown, we must move to acquire it
        if self._current_heading is None:
            logger.info("Heading unknown - Driving forward to acquire GPS heading")
            return NavigationCommand(
                speed=0.6, # Moderate speed to get good GPS fix
                turn_rate=0.0,
                timestamp=datetime.now()
            )
            
        # Calculate heading error
        heading_error = self.geo_utils.calculate_angle_difference(
            self._current_heading,
            bearing_to_target
        )
        
        # PID Control for steering
        turn_output = self.heading_pid.update(heading_error)
        
        # Apply turn aggressiveness
        turn_output *= self.turn_aggressiveness
        
        # Speed control
        # Slow down if turning sharply
        speed = self.max_speed
        if abs(heading_error) > 45.0:
            speed *= 0.5
        elif abs(heading_error) > 90.0:
            speed *= 0.2
            
        return NavigationCommand(
            speed=speed,
            turn_rate=turn_output,
            timestamp=datetime.now()
        )
    
    def _handle_waypoint_reached(self) -> NavigationCommand:
        """Handle when waypoint is reached"""
        waypoint_name = self._target_waypoint.name or 'Unnamed'
        logger.info(f"Waypoint reached: '{waypoint_name}'")
        self._status = NavigationStatus.REACHED_WAYPOINT
        
        if self._mode == NavigationMode.PATH_FOLLOWING:
            if self.waypoint_manager.advance_to_next():
                self._target_waypoint = self.waypoint_manager.get_next_waypoint()
                self._status = NavigationStatus.NAVIGATING
                self.heading_pid.reset()
                logger.info(f"Moving to next waypoint: '{self._target_waypoint.name}'")
            else:
                self._status = NavigationStatus.PATH_COMPLETE
                self._target_waypoint = None
                logger.info("Path complete!")
        else:
            self._target_waypoint = None
            self._status = NavigationStatus.IDLE
        
        return NavigationCommand(speed=0.0, turn_rate=0.0, timestamp=datetime.now())
    
    def get_state(self) -> NavigationState:
        """Get current navigation state"""
        with self._lock:
            distance_to_target = None
            bearing_to_target = None
            
            if self._current_position and self._target_waypoint:
                distance_to_target = self.geo_utils.haversine_distance(
                    self._current_position[0], self._current_position[1],
                    self._target_waypoint.lat, self._target_waypoint.lon
                )
                bearing_to_target = self.geo_utils.calculate_bearing(
                    self._current_position[0], self._current_position[1],
                    self._target_waypoint.lat, self._target_waypoint.lon
                )
            
            return NavigationState(
                current_position=self._current_position,
                target_waypoint=self._target_waypoint,
                distance_to_target=distance_to_target,
                bearing_to_target=bearing_to_target,
                current_heading=self._current_heading,
                current_speed=self._current_speed,
                mode=self._mode,
                status=self._status,
                waypoints_remaining=self.waypoint_manager.get_remaining_count(),
                error_message=self._error_message
            )
    
    def start(self) -> bool:
        """Start navigation"""
        with self._lock:
            self._is_running = True
            self._is_paused = False
            return True
    
    def stop(self):
        """Stop navigation"""
        with self._lock:
            self._is_running = False
            self._is_paused = False
            self._target_waypoint = None
            self._status = NavigationStatus.IDLE
            self.heading_pid.reset()
    
    def pause(self):
        """Pause navigation"""
        with self._lock:
            if self._is_running:
                self._is_paused = True
                self._status = NavigationStatus.PAUSED
    
    def resume(self):
        """Resume navigation"""
        with self._lock:
            if self._is_running and self._is_paused:
                self._is_paused = False
                self._status = NavigationStatus.NAVIGATING if self._target_waypoint else NavigationStatus.IDLE
    
    def add_waypoint(self, waypoint: Waypoint, auto_start: bool = False):
        """Add waypoint to queue"""
        with self._lock:
            self.waypoint_manager.add_waypoint(waypoint)
            if auto_start and not self._target_waypoint:
                self.start_navigation()
    
    def start_navigation(self) -> bool:
        """Start navigation with queued waypoints"""
        with self._lock:
            if not self.waypoint_manager.has_waypoints():
                return False
            
            if not self._target_waypoint:
                self._target_waypoint = self.waypoint_manager.get_next_waypoint()
            
            self._mode = NavigationMode.PATH_FOLLOWING
            self._status = NavigationStatus.NAVIGATING
            self._is_running = True
            self._is_paused = False
            self.heading_pid.reset()
            return True
    
    def clear_waypoints(self):
        """Clear all waypoints"""
        with self._lock:
            self.waypoint_manager.clear_waypoints()
            self._target_waypoint = None
            self._status = NavigationStatus.IDLE
    
    def get_waypoints(self) -> list:
        """Get all waypoints"""
        return self.waypoint_manager.get_all_waypoints()
