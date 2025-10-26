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
                 waypoint_tolerance: float = 0.5):
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
        # 🔧 OPTIMIZED: Reduced PID parameters to prevent motor asymmetry (one motor too weak)
        # kp reduced from 0.02 to 0.012 (60%) - gentler proportional response
        # ki reduced from 0.001 to 0.0005 (50%) - slower integral buildup
        # kd reduced from 0.01 to 0.008 (80%) - smoother derivative action
        # output_limits reduced from ±1.0 to ±0.6 - prevents extreme turn rates
        self.heading_pid = PIDController(kp=0.012, ki=0.0005, kd=0.008, output_limits=(-0.6, 0.6))
        
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
        self._approaching_logged: bool = False  # Track if "approaching waypoint" was logged
        
        # Heading calibration phase
        self._calibration_mode = False
        self._calibration_start_time: Optional[datetime] = None
        self._calibration_duration = 5.0  # 🔧 INCREASED: Extended from 3.0s to 5.0s for better heading acquisition
        self._calibration_speed = 0.5  # 🔧 INCREASED: From 0.3 (30%) to 0.5 (50%) - GPS needs movement >0.5 m/s
        self._calibration_samples = []  # 🔧 NEW: Collect heading samples for consistency check
        self._calibration_required_samples = 3  # 🔧 NEW: Need 3 consistent samples to complete calibration
        
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
        """Set single target waypoint and auto-start navigation"""
        with self._lock:
            self._target_waypoint = waypoint
            self._mode = NavigationMode.WAYPOINT
            self._status = NavigationStatus.NAVIGATING
            self._approaching_logged = False  # Reset for new waypoint
            self._calibration_mode = False  # Reset calibration for new target
            self._calibration_start_time = None
            
            # ✅ AUTO-START if not running
            if not self._is_running:
                self._is_running = True
                self._is_paused = False
                logger.info(f"🚀 Navigator auto-started with target: {waypoint.name or 'Unnamed'}")
            
            logger.info(f"🎯 Target set: {waypoint.name or 'Unnamed'} at ({waypoint.lat:.6f}, {waypoint.lon:.6f})")
            logger.info(f"📍 Starting navigation to waypoint '{waypoint.name or 'Unnamed'}' (tolerance: {waypoint.tolerance}m)")
    
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
                self._approaching_logged = False  # Reset for new waypoint
                self._calibration_mode = False  # Reset calibration for path
                self._calibration_start_time = None
                logger.info(f"🗺️  Path set with {len(waypoints)} waypoints")
                logger.info(f"📍 Starting path navigation - First waypoint: '{self._target_waypoint.name or 'Unnamed'}'")
    
    def get_navigation_command(self) -> Optional[NavigationCommand]:
        """
        Calculate navigation command based on current state
        
        Returns:
            NavigationCommand or None if cannot navigate
        """
        with self._lock:
            # Diagnostic logging
            logger.debug(f"get_nav_cmd: running={self._is_running}, paused={self._is_paused}, "
                        f"pos={self._current_position is not None}, target={self._target_waypoint is not None}, "
                        f"heading={self._current_heading}")
            
            # Check if we can navigate
            if not self._is_running or self._is_paused:
                logger.debug(f"⏸️  Navigator not active (running={self._is_running}, paused={self._is_paused})")
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
            
            # **HEADING CALIBRATION PHASE**
            # If no heading available, enter calibration mode - drive straight to establish heading
            if self._current_heading is None and not self._calibration_mode:
                self._calibration_mode = True
                self._calibration_start_time = datetime.now()
                self._calibration_samples = []  # 🔧 Reset samples
                logger.warning(f"🧭 HEADING CALIBRATION STARTED - no GPS heading available")
                logger.warning(f"   Robot will drive straight for up to {self._calibration_duration}s at {self._calibration_speed*100:.0f}% speed")
                logger.warning(f"   Waiting for {self._calibration_required_samples} consistent VTG heading samples")
                logger.warning(f"   GPS must detect movement (speed > 0.5 m/s)")
            
            # During calibration: drive straight at low speed and collect heading samples
            if self._calibration_mode:
                elapsed = (datetime.now() - self._calibration_start_time).total_seconds()
                
                # Collect heading samples
                if self._current_heading is not None:
                    self._calibration_samples.append(self._current_heading)
                    logger.info(f"🧭 Heading sample #{len(self._calibration_samples)}: {self._current_heading:.1f}° (speed={self._current_speed:.2f} m/s)")
                
                # Check if we have enough consistent samples
                if len(self._calibration_samples) >= self._calibration_required_samples:
                    # Check consistency (variance < 15°)
                    heading_variance = max(self._calibration_samples) - min(self._calibration_samples)
                    if heading_variance < 15.0:
                        avg_heading = sum(self._calibration_samples) / len(self._calibration_samples)
                        self._calibration_mode = False
                        logger.info(f"✅ Heading calibration complete! Heading: {avg_heading:.1f}° (variance: {heading_variance:.1f}°, took {elapsed:.1f}s)")
                    else:
                        logger.warning(f"⚠️ Heading samples inconsistent (variance={heading_variance:.1f}°), continuing calibration...")
                        self._calibration_samples = self._calibration_samples[-2:]  # Keep last 2 samples
                
                elif elapsed >= self._calibration_duration:
                    # Timeout
                    self._calibration_mode = False
                    if len(self._calibration_samples) > 0:
                        avg_heading = sum(self._calibration_samples) / len(self._calibration_samples)
                        logger.warning(f"⚠️ Heading calibration TIMEOUT after {elapsed:.1f}s")
                        logger.warning(f"   Using partial data: {len(self._calibration_samples)} samples, avg heading: {avg_heading:.1f}°")
                    else:
                        logger.error(f"❌ Heading calibration FAILED after {elapsed:.1f}s - no samples collected")
                        logger.error(f"   GPS speed may be too low or VTG messages not working")
                else:
                    # Continue driving straight
                    logger.info(f"🧭 Calibrating heading... {elapsed:.1f}s / {self._calibration_duration}s (samples: {len(self._calibration_samples)}/{self._calibration_required_samples})")
                    return NavigationCommand(
                        speed=self._calibration_speed,
                        turn_rate=0.0,  # Drive perfectly straight
                        timestamp=datetime.now(),
                        priority=1
                    )
            
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
            
            # Log progress at key distance milestones
            waypoint_name = self._target_waypoint.name or 'Unnamed'
            if distance > 10.0 and distance % 10.0 < 1.0 and not hasattr(self, '_last_logged_distance'):
                # Log every ~10m when far away
                logger.info(f"🚗 Navigating to '{waypoint_name}' - Distance: {distance:.1f}m, Bearing: {bearing_to_target:.0f}°")
                self._last_logged_distance = distance
            elif distance <= 10.0 and distance > 5.0 and not hasattr(self, '_logged_10m'):
                logger.info(f"🚗 Navigating to '{waypoint_name}' - Distance: {distance:.1f}m")
                self._logged_10m = True
            elif distance <= 5.0 and distance > 2.0 and not hasattr(self, '_logged_5m'):
                logger.info(f"➡️  Getting closer to '{waypoint_name}' - Distance: {distance:.1f}m")
                self._logged_5m = True
            
            # Log when approaching waypoint (within 2m)
            if distance <= 2.0 and not self._approaching_logged:
                logger.info(f"🎯 Approaching waypoint '{waypoint_name}' - {distance:.2f}m away")
                self._approaching_logged = True
            
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
        waypoint_name = self._target_waypoint.name or 'Unnamed'
        waypoint_coords = f"({self._target_waypoint.lat:.6f}, {self._target_waypoint.lon:.6f})"
        logger.info(f"✅ Waypoint reached: '{waypoint_name}' at {waypoint_coords} (tolerance: {self._target_waypoint.tolerance}m)")
        self._status = NavigationStatus.REACHED_WAYPOINT
        
        if self._mode == NavigationMode.PATH_FOLLOWING:
            # Move to next waypoint
            if self.waypoint_manager.advance_to_next():
                self._target_waypoint = self.waypoint_manager.get_next_waypoint()
                self._status = NavigationStatus.NAVIGATING
                self._approaching_logged = False  # Reset for next waypoint
                # Reset distance logging flags for next waypoint
                if hasattr(self, '_last_logged_distance'):
                    delattr(self, '_last_logged_distance')
                if hasattr(self, '_logged_10m'):
                    delattr(self, '_logged_10m')
                if hasattr(self, '_logged_5m'):
                    delattr(self, '_logged_5m')
                
                remaining = self.waypoint_manager.get_remaining_count()
                next_waypoint_name = self._target_waypoint.name or 'Unnamed'
                logger.info(f"📍 Moving to next waypoint: '{next_waypoint_name}' ({remaining} waypoints remaining)")
            else:
                # Path complete
                self._status = NavigationStatus.PATH_COMPLETE
                self._target_waypoint = None
                logger.info("🏁 Path complete! All waypoints reached.")
        else:
            # Single waypoint mode - stop
            self._target_waypoint = None
            self._status = NavigationStatus.IDLE
            logger.info("🏁 Navigation complete - waypoint reached")
        
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
                logger.debug("Navigator already running - OK")
                return True  # ✅ Not an error - idempotent
            
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
                waypoint_name = self._target_waypoint.name if self._target_waypoint else "None"
                logger.info(f"⏸️  Navigator paused (current target: '{waypoint_name}')")
    
    def resume(self):
        """Resume navigation"""
        with self._lock:
            if self._is_running and self._is_paused:
                self._is_paused = False
                self._status = NavigationStatus.NAVIGATING if self._target_waypoint else NavigationStatus.IDLE
                self.heading_pid.reset()
                waypoint_name = self._target_waypoint.name if self._target_waypoint else "None"
                logger.info(f"▶️  Navigator resumed (target: '{waypoint_name}')")
    
    # Additional utility methods
    
    def add_waypoint(self, waypoint: Waypoint, auto_start: bool = False):
        """
        Add waypoint to queue
        
        Args:
            waypoint: Waypoint to add
            auto_start: If True, automatically start navigation if not already active
                       If False, waypoint is just queued (default behavior)
        """
        with self._lock:
            self.waypoint_manager.add_waypoint(waypoint)
            
            # Only auto-start if explicitly requested
            if auto_start and not self._target_waypoint:
                self._target_waypoint = self.waypoint_manager.get_next_waypoint()
                self._mode = NavigationMode.PATH_FOLLOWING
                self._status = NavigationStatus.NAVIGATING
                self._approaching_logged = False  # Reset for new waypoint
                logger.info(f"Waypoint added and navigation auto-started")
            else:
                logger.info(f"Waypoint added to queue (not started)")
    
    def start_navigation(self) -> bool:
        """
        Start navigation with queued waypoints
        
        Returns:
            True if navigation started, False if no waypoints or already navigating
        """
        with self._lock:
            # ✅ If single waypoint already active (from /goto), that's OK - idempotent
            if self._target_waypoint and self._mode == NavigationMode.WAYPOINT:
                logger.info("Single waypoint navigation already active (from /goto) - OK")
                return True
            
            # ✅ If path following already active, also OK - idempotent
            if self._target_waypoint and self._mode == NavigationMode.PATH_FOLLOWING:
                logger.info("Path following already active - OK")
                return True
            
            # Check if we have waypoints
            if not self.waypoint_manager.has_waypoints():
                logger.warning("No waypoints to navigate to")
                return False
            
            # Set first waypoint as target
            self._target_waypoint = self.waypoint_manager.get_next_waypoint()
            if self._target_waypoint:
                self._mode = NavigationMode.PATH_FOLLOWING
                self._status = NavigationStatus.NAVIGATING
                self._is_paused = False
                self._approaching_logged = False  # Reset for new waypoint
                self.heading_pid.reset()
                logger.info(f"Navigation started - target: {self._target_waypoint.name or 'unnamed'}")
                return True
            
            return False
    
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
