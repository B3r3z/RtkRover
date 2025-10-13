"""Main navigation system implementation"""
import logging
from typing import Optional
from datetime import datetime
import threading

from .core.interfaces import NavigationInterface
from .core.data_types import (
    Waypoint, NavigationCommand, NavigationState,
    NavigationMode, NavigationStatus
)
from .algorithms.geo_utils import GeoUtils
from .algorithms.path_planner import SimplePathPlanner
from .algorithms.pid_controller import PIDController
from .waypoint_manager import SimpleWaypointManager

logger = logging.getLogger(__name__)


class Navigator(NavigationInterface):
    """
    Main navigation system implementation
    Coordinates GPS position, waypoint management, and generates navigation commands
    """
    
    def __init__(self, 
                 max_speed: float = 1.0,
                 turn_aggressiveness: float = 0.5,
                 waypoint_tolerance: float = 0.01):
        """
        Initialize navigator
        
        Args:
            max_speed: Maximum speed value (0.0 to 1.0)
            turn_aggressiveness: How aggressive turns are (0.0 to 1.0)
            waypoint_tolerance: Default waypoint reach tolerance in meters
        """
        # Components
        self.geo_utils = GeoUtils()
        self.path_planner = SimplePathPlanner()
        self.waypoint_manager = SimpleWaypointManager()
        
        # PID controller for smooth heading control
        # Tune these values based on your robot's response
        self.heading_pid = PIDController(kp=0.02, ki=0.001, kd=0.01, output_limits=(-1.0, 1.0))
        
        # Configuration
        self.max_speed = max_speed
        self.turn_aggressiveness = turn_aggressiveness
        self.default_tolerance = waypoint_tolerance
        
        # State
        self._current_position: Optional[tuple] = None  # (lat, lon)
        self._current_heading: Optional[float] = None  # degrees
        self._current_speed: Optional[float] = None  # m/s
        self._target_waypoint: Optional[Waypoint] = None
        self._last_position_time: Optional[datetime] = None  # GPS timestamp tracking
        self._mode = NavigationMode.IDLE
        self._status = NavigationStatus.IDLE
        self._is_running = False
        self._is_paused = False
        self._error_message: Optional[str] = None
        
        # Command smoothing
        self._last_command: Optional[NavigationCommand] = None
        self._max_turn_rate_change = 0.3  # Max 30% change per cycle
        self._max_speed_change = 0.5      # Max 50% change per cycle
        
        # Thread safety
        self._lock = threading.Lock()
        
        logger.info("Navigator initialized")
    
    def update_position(self, lat: float, lon: float, heading: Optional[float] = None, speed: Optional[float] = None):
        """Update current position from GPS with intelligent heading handling"""
        with self._lock:
            previous_position = self._current_position
            self._current_position = (lat, lon)
            self._last_position_time = datetime.now()
            
            # Priority 1: Use GPS heading (course over ground) when available
            if heading is not None:
                self._current_heading = heading
                logger.debug(f"Using GPS heading: {heading:.1f}°")
            # Priority 2: Calculate heading from movement (if moving and have previous position)
            elif previous_position and speed is not None and speed > 0.5:
                # Only calculate if robot is moving (speed > 0.5 m/s)
                calculated_heading = self.geo_utils.calculate_bearing(
                    previous_position[0], previous_position[1],
                    lat, lon
                )
                self._current_heading = calculated_heading
                logger.debug(f"Calculated heading from movement: {calculated_heading:.1f}°")
            # else: Keep previous heading value
            
            if speed is not None:
                self._current_speed = speed
            
            logger.debug(f"Position updated: ({lat:.6f}, {lon:.6f}), heading: {self._current_heading}, speed: {speed}")
    
    def _is_position_stale(self, max_age_seconds: float = 2.0) -> bool:
        """
        Check if current position is too old
        
        Args:
            max_age_seconds: Maximum acceptable age of position data
        
        Returns:
            True if position is stale or not available
        """
        if not self._last_position_time:
            return True
        
        age = (datetime.now() - self._last_position_time).total_seconds()
        return age > max_age_seconds
    
    def set_target(self, waypoint: Waypoint):
        """Set single target waypoint"""
        with self._lock:
            self._target_waypoint = waypoint
            self._mode = NavigationMode.WAYPOINT
            self._status = NavigationStatus.NAVIGATING
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
                logger.info(f"Path set with {len(waypoints)} waypoints")
    
    def get_navigation_command(self) -> Optional[NavigationCommand]:
        """
        Calculate navigation command based on current state
        
        Returns:
            NavigationCommand or None if cannot navigate
        """
        with self._lock:
            # Check if we can navigate
            if not self._is_running or self._is_paused:
                return None
            
            if not self._current_position:
                self._error_message = "No GPS position available"
                self._status = NavigationStatus.ERROR
                return None
            
            # Check if GPS data is stale
            if self._is_position_stale(max_age_seconds=2.0):
                self._error_message = "GPS data too old"
                self._status = NavigationStatus.ERROR
                logger.warning("GPS data is stale, stopping navigation")
                return None
            
            if not self._target_waypoint:
                self._status = NavigationStatus.IDLE
                return NavigationCommand(speed=0.0, turn_rate=0.0, timestamp=datetime.now())
            
            # Calculate navigation parameters
            current_lat, current_lon = self._current_position
            target_lat, target_lon = self._target_waypoint.lat, self._target_waypoint.lon
            
            # Distance and bearing to target
            distance = self.path_planner.calculate_distance(
                (current_lat, current_lon),
                (target_lat, target_lon)
            )
            
            bearing_to_target = self.path_planner.calculate_heading(
                (current_lat, current_lon),
                (target_lat, target_lon)
            )
            
            # Check if waypoint reached
            if distance <= self._target_waypoint.tolerance:
                return self._handle_waypoint_reached()
            
            # Calculate turn rate
            if self._current_heading is not None:
                heading_error = self.geo_utils.calculate_angle_difference(
                    self._current_heading,
                    bearing_to_target
                )
                turn_rate = self.heading_pid.update(heading_error)
                turn_rate *= self.turn_aggressiveness
            else:
                # No compass data, use simple proportional control
                turn_rate = 0.0
                logger.warning("No heading data, cannot calculate turn rate")
            
            # Calculate speed (reduce speed when turning sharply)
            speed = self.max_speed
            if abs(turn_rate) > 0.5:
                # Reduce speed during sharp turns
                speed *= (1.0 - abs(turn_rate) * 0.5)
            
            # Apply waypoint speed limit if set
            if self._target_waypoint.speed_limit is not None:
                # Normalize speed limit to 0-1 range (assuming 1.0 = max robot speed)
                speed = min(speed, self._target_waypoint.speed_limit / 2.0)  # Adjust divisor based on robot max speed
            
            self._status = NavigationStatus.NAVIGATING
            self._error_message = None
            
            # Create raw command
            raw_command = NavigationCommand(
                speed=speed,
                turn_rate=turn_rate,
                timestamp=datetime.now(),
                priority=1
            )
            
            # Apply smoothing
            smoothed_command = self._smooth_command(raw_command)
            self._last_command = smoothed_command
            
            return smoothed_command
    
    def _smooth_command(self, command: NavigationCommand) -> NavigationCommand:
        """
        Apply rate limiting to navigation commands to prevent abrupt changes
        
        Args:
            command: Raw navigation command
        
        Returns:
            Smoothed navigation command
        """
        if not self._last_command:
            # First command, no smoothing needed
            return command
        
        smoothed_speed = command.speed
        smoothed_turn = command.turn_rate
        
        # Limit turn rate change
        turn_delta = command.turn_rate - self._last_command.turn_rate
        if abs(turn_delta) > self._max_turn_rate_change:
            sign = 1 if turn_delta > 0 else -1
            smoothed_turn = self._last_command.turn_rate + (self._max_turn_rate_change * sign)
            logger.debug(f"Turn rate limited: {command.turn_rate:.2f} → {smoothed_turn:.2f}")
        
        # Limit speed change
        speed_delta = command.speed - self._last_command.speed
        if abs(speed_delta) > self._max_speed_change:
            sign = 1 if speed_delta > 0 else -1
            smoothed_speed = self._last_command.speed + (self._max_speed_change * sign)
            logger.debug(f"Speed limited: {command.speed:.2f} → {smoothed_speed:.2f}")
        
        return NavigationCommand(
            speed=smoothed_speed,
            turn_rate=smoothed_turn,
            timestamp=command.timestamp,
            priority=command.priority
        )
    
    def _handle_waypoint_reached(self) -> NavigationCommand:
        """Handle when waypoint is reached"""
        logger.info(f"Waypoint reached: {self._target_waypoint.name or 'Unnamed'}")
        self._status = NavigationStatus.REACHED_WAYPOINT
        
        if self._mode == NavigationMode.PATH_FOLLOWING:
            # Move to next waypoint
            if self.waypoint_manager.advance_to_next():
                self._target_waypoint = self.waypoint_manager.get_next_waypoint()
                self._status = NavigationStatus.NAVIGATING
                logger.info("Moving to next waypoint")
            else:
                # Path complete
                self._status = NavigationStatus.PATH_COMPLETE
                self._target_waypoint = None
                logger.info("Path complete!")
        else:
            # Single waypoint mode - stop
            self._target_waypoint = None
            self._status = NavigationStatus.IDLE
        
        # Reset PID controller for next waypoint
        self.heading_pid.reset()
        
        # Return stop command
        return NavigationCommand(speed=0.0, turn_rate=0.0, timestamp=datetime.now())
    
    def get_state(self) -> NavigationState:
        """
        Get current navigation state (thread-safe)
        Returns an immutable snapshot of the current state
        
        Returns:
            NavigationState: Immutable state object
        """
        with self._lock:
            # Calculate derived values under lock
            distance_to_target = None
            bearing_to_target = None
            
            if self._current_position and self._target_waypoint:
                distance_to_target = self.path_planner.calculate_distance(
                    self._current_position,
                    (self._target_waypoint.lat, self._target_waypoint.lon)
                )
                bearing_to_target = self.path_planner.calculate_heading(
                    self._current_position,
                    (self._target_waypoint.lat, self._target_waypoint.lon)
                )
            
            # Return immutable NavigationState (dataclass)
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
            if self._is_running:
                logger.warning("Navigator already running")
                return False
            
            self._is_running = True
            self._is_paused = False
            self._error_message = None
            logger.info("Navigator started")
            return True
    
    def stop(self):
        """Stop navigation"""
        with self._lock:
            self._is_running = False
            self._is_paused = False
            self._target_waypoint = None
            self._status = NavigationStatus.IDLE
            self.heading_pid.reset()
            logger.info("Navigator stopped")
    
    def pause(self):
        """Pause navigation"""
        with self._lock:
            if self._is_running:
                self._is_paused = True
                self._status = NavigationStatus.PAUSED
                self.heading_pid.reset()
                logger.info("Navigator paused")
    
    def resume(self):
        """Resume navigation"""
        with self._lock:
            if self._is_running and self._is_paused:
                self._is_paused = False
                self._status = NavigationStatus.NAVIGATING if self._target_waypoint else NavigationStatus.IDLE
                self.heading_pid.reset()
                logger.info("Navigator resumed")
    
    # Additional utility methods
    
    def add_waypoint(self, waypoint: Waypoint):
        """Add waypoint to queue"""
        with self._lock:
            self.waypoint_manager.add_waypoint(waypoint)
            
            # If not currently navigating, set this as target
            if not self._target_waypoint:
                self._target_waypoint = self.waypoint_manager.get_next_waypoint()
                self._mode = NavigationMode.PATH_FOLLOWING
                self._status = NavigationStatus.NAVIGATING
    
    def clear_waypoints(self):
        """Clear all waypoints"""
        with self._lock:
            self.waypoint_manager.clear_waypoints()
            self._target_waypoint = None
            self._status = NavigationStatus.IDLE
            logger.info("All waypoints cleared")
    
    def get_waypoints(self) -> list:
        """Get all waypoints"""
        return self.waypoint_manager.get_all_waypoints()
