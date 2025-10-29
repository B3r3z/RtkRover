"""Main navigation system implementation"""
import logging
from typing import Optional
from datetime import datetime
import threading

from .core.interfaces import NavigationInterface
from .core.data_types import (
    Waypoint, NavigationCommand, NavigationState,
    NavigationMode, NavigationStatus, NavigationPhase
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
                 waypoint_tolerance: float = 0.5,
                 align_tolerance: float = 15.0,
                 realign_threshold: float = 30.0,
                 align_speed: float = 0.4,
                 align_timeout: float = 10.0,
                 drive_correction_gain: float = 0.02,
                 loop_mode: bool = False):
        """
        Initialize navigator
        
        Args:
            max_speed: Maximum speed value (0.0 to 1.0)
            turn_aggressiveness: How aggressive turns are (0.0 to 1.0)
            waypoint_tolerance: Default waypoint reach tolerance in meters
            align_tolerance: Heading error threshold to exit ALIGN phase (degrees)
            realign_threshold: Heading error threshold to re-enter ALIGN from DRIVE (degrees)
            align_speed: Speed multiplier during rotation in place (0.0 to 1.0)
            align_timeout: Maximum time to spend in ALIGN phase (seconds)
            drive_correction_gain: Proportional gain for minor course corrections during DRIVE
            loop_mode: If True, cycles through waypoints continuously (default: False)
        """
        # Components
        self.geo_utils = GeoUtils()
        self.path_planner = SimplePathPlanner()
        self.waypoint_manager = SimpleWaypointManager(loop_mode=loop_mode)
        
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
        

        self.align_tolerance = align_tolerance
        self.realign_threshold = realign_threshold
        self.align_speed = align_speed
        self.align_timeout = align_timeout
        self.drive_correction_gain = drive_correction_gain
        
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
        
        self._navigation_phase = NavigationPhase.IDLE
        self._phase_start_time: Optional[datetime] = None
        
        # Heading calibration phase
        self._calibration_mode = False
        self._calibration_start_time: Optional[datetime] = None
        self._calibration_duration = 5.0  # 🔧 INCREASED: Extended from 3.0s to 5.0s for better heading acquisition
        self._calibration_speed = 0.5  # 🔧 INCREASED: From 0.3 (30%) to 0.5 (50%) - GPS needs movement >0.5 m/s
        self._calibration_samples = []  # 🔧 NEW: Collect heading samples for consistency check
        self._calibration_required_samples = 3  # 🔧 NEW: Need 3 consistent samples to complete calibration
        
        # Thread safety
        self._lock = threading.Lock()
        
        logger.info("Navigator initialized with state machine navigation")
        logger.info(f"  Loop mode: {'enabled' if loop_mode else 'disabled'}")
        logger.info(f"  Align: tolerance={align_tolerance}°, threshold={realign_threshold}°, "
                   f"speed={align_speed:.2f}, timeout={align_timeout}s")
        logger.info(f"  Drive: correction_gain={drive_correction_gain:.3f}")
    
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

            self._navigation_phase = NavigationPhase.IDLE
            self._phase_start_time = None
                        # 🔧 NEW: Reset state machine for new target
            self._navigation_phase = NavigationPhase.IDLE
            self._phase_start_time = None
            # Reset distance logging flags
            for attr in ['_logged_distance_10', '_logged_distance_5', '_last_logged_distance', 
                        '_align_phase_logged', '_drive_phase_logged', '_last_align_log_time', '_last_drive_log_time']:
                if hasattr(self, attr):
                    delattr(self, attr)
            
            # ✅ AUTO-START if not running
            if not self._is_running:
                self._is_running = True
                self._is_paused = False
                logger.info(f"🚀 Navigator auto-started with target: {waypoint.name or 'Unnamed'}")
            
            logger.info(f"🎯 Target set: {waypoint.name or 'Unnamed'} at ({waypoint.lat:.6f}, {waypoint.lon:.6f})")
            logger.info(f"📍 Starting navigation to waypoint '{waypoint.name or 'Unnamed'}' (tolerance: {waypoint.tolerance}m)")
    
    def set_waypoint_path(self, waypoints: list, loop_mode: Optional[bool] = None):
        """
        Set multiple waypoints for path following
        
        Args:
            waypoints: List of Waypoint objects
            loop_mode: Optional override for loop mode. If None, uses navigator's default
        """
        with self._lock:
            # Update loop mode if specified
            if loop_mode is not None:
                self.waypoint_manager.set_loop_mode(loop_mode)
            
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
                
                self._navigation_phase = NavigationPhase.IDLE
                self._phase_start_time = None
                
                loop_status = "loop mode" if self.waypoint_manager.is_loop_mode() else "one-time path"
                logger.info(f"🗺️  Path set with {len(waypoints)} waypoints ({loop_status})")
                logger.info(f"📍 Starting path navigation - First waypoint: '{self._target_waypoint.name or 'Unnamed'}'")
    
    def get_navigation_command(self) -> Optional[NavigationCommand]:
        """
        Calculate navigation command based on current state
        Uses state machine: IDLE → CALIBRATING → ALIGNING → DRIVING → REACHED
        
        Returns:
            NavigationCommand or None if cannot navigate
        """
        with self._lock:
            # Diagnostic logging
            logger.debug(f"get_nav_cmd: running={self._is_running}, paused={self._is_paused}, "
                        f"pos={self._current_position is not None}, target={self._target_waypoint is not None}, "
                        f"heading={self._current_heading}, phase={self._navigation_phase.value}")
            
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
                self._navigation_phase = NavigationPhase.IDLE
                return NavigationCommand(speed=0.0, turn_rate=0.0, timestamp=datetime.now())
            
            # **STATE MACHINE DISPATCHER**
            
            # CALIBRATING phase: Acquire initial heading
            if self._current_heading is None and not self._calibration_mode:
                self._calibration_mode = True
                self._calibration_start_time = datetime.now()
                self._calibration_samples = []
                self._navigation_phase = NavigationPhase.CALIBRATING
                logger.warning(f"🧭 HEADING CALIBRATION STARTED - no GPS heading available")
                logger.warning(f"   Robot will drive straight for up to {self._calibration_duration}s "
                             f"at {self._calibration_speed*100:.0f}% speed")
                logger.warning(f"   Waiting for {self._calibration_required_samples} consistent VTG heading samples")
                logger.warning(f"   GPS must detect movement (speed > 0.5 m/s)")
            
            if self._calibration_mode:
                command = self._handle_calibration()
                if command is None:
                    # Calibration complete, transition handled in _handle_calibration
                    # Re-run state machine for next phase
                    return self.get_navigation_command()
                return command
            
            # State machine router
            if self._navigation_phase == NavigationPhase.IDLE:
                # Start with ALIGNING
                self._navigation_phase = NavigationPhase.ALIGNING
                self._phase_start_time = datetime.now()
                logger.info(f"🎯 Starting navigation - entering ALIGN phase")
                return self._handle_align_phase()
            
            elif self._navigation_phase == NavigationPhase.ALIGNING:
                return self._handle_align_phase()
            
            elif self._navigation_phase == NavigationPhase.DRIVING:
                return self._handle_drive_phase()
            
            elif self._navigation_phase == NavigationPhase.REACHED:
                # Already handled in _handle_drive_phase
                return NavigationCommand(speed=0.0, turn_rate=0.0, timestamp=datetime.now())
            
            else:
                # Shouldn't reach here
                logger.error(f"Unknown navigation phase: {self._navigation_phase}")
                self._navigation_phase = NavigationPhase.ALIGNING
                self._phase_start_time = datetime.now()
                return NavigationCommand(speed=0.0, turn_rate=0.0, timestamp=datetime.now())
    
    def _handle_calibration(self) -> Optional[NavigationCommand]:
        """
        Handle CALIBRATING phase - drive straight to acquire initial heading from GPS VTG
        
        Returns:
            NavigationCommand to drive straight, or None if calibration complete
        """
        elapsed = (datetime.now() - self._calibration_start_time).total_seconds()
        
        # Collect heading samples
        if self._current_heading is not None:
            self._calibration_samples.append(self._current_heading)
            logger.info(f"🧭 Heading sample #{len(self._calibration_samples)}: {self._current_heading:.1f}° "
                       f"(speed={self._current_speed:.2f} m/s)")
        
        # Check if we have enough consistent samples
        if len(self._calibration_samples) >= self._calibration_required_samples:
            # Check consistency (variance < 15°)
            heading_variance = max(self._calibration_samples) - min(self._calibration_samples)
            if heading_variance < 15.0:
                avg_heading = sum(self._calibration_samples) / len(self._calibration_samples)
                self._calibration_mode = False
                self._navigation_phase = NavigationPhase.ALIGNING  # Transition to ALIGN
                self._phase_start_time = datetime.now()
                logger.info(f"✅ Heading calibration complete! Heading: {avg_heading:.1f}° "
                           f"(variance: {heading_variance:.1f}°, took {elapsed:.1f}s)")
                logger.info(f"🔄 Transitioning to ALIGN phase")
                return None  # Return None to signal phase change
            else:
                logger.warning(f"⚠️ Heading samples inconsistent (variance={heading_variance:.1f}°), "
                             f"continuing calibration...")
                self._calibration_samples = self._calibration_samples[-2:]  # Keep last 2 samples
        
        elif elapsed >= self._calibration_duration:
            # Timeout
            self._calibration_mode = False
            if len(self._calibration_samples) > 0:
                avg_heading = sum(self._calibration_samples) / len(self._calibration_samples)
                logger.warning(f"⚠️ Heading calibration TIMEOUT after {elapsed:.1f}s")
                logger.warning(f"   Using partial data: {len(self._calibration_samples)} samples, "
                             f"avg heading: {avg_heading:.1f}°")
                self._navigation_phase = NavigationPhase.ALIGNING
                self._phase_start_time = datetime.now()
                return None
            else:
                logger.error(f"❌ Heading calibration FAILED after {elapsed:.1f}s - no samples collected")
                logger.error(f"   GPS speed may be too low or VTG messages not working")
                self._navigation_phase = NavigationPhase.DRIVING  # Try driving anyway
                self._phase_start_time = datetime.now()
                return None
        else:
            # Continue driving straight
            logger.info(f"🧭 Calibrating heading... {elapsed:.1f}s / {self._calibration_duration}s "
                       f"(samples: {len(self._calibration_samples)}/{self._calibration_required_samples})")
            return NavigationCommand(
                speed=self._calibration_speed,
                turn_rate=0.0,  # Drive perfectly straight
                timestamp=datetime.now(),
                priority=1
            )
    
    def _handle_align_phase(self) -> NavigationCommand:
        """
        Handle ALIGNING phase - rotate in place until facing target
        
        Returns:
            NavigationCommand for rotation in place
        """
        # 🔧 ADDED: Log phase entry (only once per phase)
        if not hasattr(self, '_align_phase_logged') or not self._align_phase_logged:
            logger.info(f"📍 Entered ALIGN phase - rotating to target")
            self._align_phase_logged = True
        
        current_lat, current_lon = self._current_position
        bearing_to_target = self.path_planner.calculate_heading(
            (current_lat, current_lon),
            (self._target_waypoint.lat, self._target_waypoint.lon)
        )
        
        if self._current_heading is None:
            # No heading - can't align, switch to DRIVE
            logger.warning("⚠️ No heading during ALIGN, switching to DRIVE")
            self._navigation_phase = NavigationPhase.DRIVING
            self._phase_start_time = datetime.now()
            self._align_phase_logged = False  # Reset for next time
            logger.info(f"🔄 Phase transition: ALIGN → DRIVE (no heading)")
            return NavigationCommand(speed=self.max_speed * 0.5, turn_rate=0.0, 
                                   timestamp=datetime.now(), priority=1)
        
        # Calculate heading error
        heading_error = self.geo_utils.calculate_angle_difference(
            self._current_heading,
            bearing_to_target
        )
        
        # Check if aligned
        if abs(heading_error) < self.align_tolerance:
            # ALIGNED! Transition to DRIVE
            logger.info(f"✅ Aligned to target! Heading: {self._current_heading:.1f}°, "
                       f"Target: {bearing_to_target:.1f}°, Error: {heading_error:.1f}°")
            self._navigation_phase = NavigationPhase.DRIVING
            self._phase_start_time = datetime.now()
            self.heading_pid.reset()  # Reset PID for fresh start
            self._align_phase_logged = False  # Reset for next time
            logger.info(f"🔄 Phase transition: ALIGN → DRIVE (aligned)")
            return NavigationCommand(speed=self.max_speed, turn_rate=0.0, 
                                   timestamp=datetime.now(), priority=1)
        
        # Check timeout
        elapsed = (datetime.now() - self._phase_start_time).total_seconds()
        if elapsed > self.align_timeout:
            logger.warning(f"⏱️ ALIGN timeout ({elapsed:.1f}s), switching to DRIVE anyway "
                         f"(error: {heading_error:.1f}°)")
            self._navigation_phase = NavigationPhase.DRIVING
            self._phase_start_time = datetime.now()
            self._align_phase_logged = False  # Reset for next time
            logger.info(f"🔄 Phase transition: ALIGN → DRIVE (timeout)")
            return NavigationCommand(speed=self.max_speed * 0.5, turn_rate=0.0, 
                                   timestamp=datetime.now(), priority=1)
        
        # Continue rotating in place
        # Turn direction: positive error = target on right, turn right
        turn_direction = 1.0 if heading_error > 0 else -1.0
        turn_intensity = min(abs(heading_error) / 90.0, 1.0)  # Normalize to 0-1
        
        # 🔧 IMPROVED: Log every 2 seconds instead of every cycle
        if not hasattr(self, '_last_align_log_time') or (datetime.now() - self._last_align_log_time).total_seconds() > 2.0:
            logger.info(f"🔄 Aligning: current={self._current_heading:.1f}°, "
                       f"target={bearing_to_target:.1f}°, error={heading_error:.1f}°, elapsed={elapsed:.1f}s")
            self._last_align_log_time = datetime.now()
        
        # Rotation in place: speed=0, turn_rate controls rotation
        return NavigationCommand(
            speed=0.0,  # Don't move forward
            turn_rate=turn_direction * turn_intensity * self.align_speed,
            timestamp=datetime.now(),
            priority=1
        )
    
    def _handle_drive_phase(self) -> NavigationCommand:
        """
        Handle DRIVING phase - drive straight forward with minor PID correction
        
        Returns:
            NavigationCommand for forward motion with course correction
        """
        # 🔧 ADDED: Log phase entry (only once per phase)
        if not hasattr(self, '_drive_phase_logged') or not self._drive_phase_logged:
            logger.info(f"🚗 Entered DRIVE phase - moving to target")
            self._drive_phase_logged = True
        
        current_lat, current_lon = self._current_position
        
        # Calculate distance and bearing to target
        distance = self.path_planner.calculate_distance(
            (current_lat, current_lon),
            (self._target_waypoint.lat, self._target_waypoint.lon)
        )
        
        bearing_to_target = self.path_planner.calculate_heading(
            (current_lat, current_lon),
            (self._target_waypoint.lat, self._target_waypoint.lon)
        )
        
        # Check if waypoint reached
        if distance <= self._target_waypoint.tolerance:
            self._navigation_phase = NavigationPhase.REACHED
            self._drive_phase_logged = False  # Reset for next time
            logger.info(f"🔄 Phase transition: DRIVE → REACHED")
            return self._handle_waypoint_reached()
        
        # Check heading availability
        if self._current_heading is None:
            logger.warning("⚠️ No heading during DRIVE, continuing straight")
            return NavigationCommand(speed=self.max_speed * 0.5, turn_rate=0.0, 
                                   timestamp=datetime.now(), priority=1)
        
        # Calculate heading error
        heading_error = self.geo_utils.calculate_angle_difference(
            self._current_heading,
            bearing_to_target
        )
        
        # Check if re-alignment needed
        if abs(heading_error) > self.realign_threshold:
            logger.info(f"🔄 Heading error too large ({heading_error:.1f}°), re-aligning...")
            self._navigation_phase = NavigationPhase.ALIGNING
            self._phase_start_time = datetime.now()
            self.heading_pid.reset()  # Reset PID state
            self._drive_phase_logged = False  # Reset for next time
            self._align_phase_logged = False  # Reset for ALIGN entry
            logger.info(f"🔄 Phase transition: DRIVE → ALIGN (error > {self.realign_threshold}°)")
            return self._handle_align_phase()
        
        # Drive straight with SMALL proportional correction
        # Don't use full PID - only proportional correction
        correction = heading_error * self.drive_correction_gain
        correction = max(-0.2, min(0.2, correction))  # Limit to ±0.2
        
        # 🔧 IMPROVED: Log every 2 seconds with detailed info
        if not hasattr(self, '_last_drive_log_time') or (datetime.now() - self._last_drive_log_time).total_seconds() > 2.0:
            logger.info(f"🚗 Driving: dist={distance:.1f}m, heading={self._current_heading:.1f}°, "
                       f"bearing={bearing_to_target:.1f}°, error={heading_error:.1f}°, correction={correction:.2f}")
            self._last_drive_log_time = datetime.now()
        
        # Log progress milestones
        waypoint_name = self._target_waypoint.name or 'Unnamed'
        if distance > 10.0 and not hasattr(self, '_logged_distance_10'):
            logger.info(f"🚗 Navigating to '{waypoint_name}' - Distance: {distance:.1f}m, Bearing: {bearing_to_target:.0f}°")
            self._logged_distance_10 = True
        elif distance <= 5.0 and not hasattr(self, '_logged_distance_5'):
            logger.info(f"➡️  Approaching '{waypoint_name}' - Distance: {distance:.1f}m")
            self._logged_distance_5 = True
        
        return NavigationCommand(
            speed=self.max_speed,
            turn_rate=correction,  # Small correction, not full PID
            timestamp=datetime.now(),
            priority=1
        )
    
    def _handle_waypoint_reached(self) -> NavigationCommand:
        """Handle when waypoint is reached"""
        waypoint_name = self._target_waypoint.name or 'Unnamed'
        waypoint_coords = f"({self._target_waypoint.lat:.6f}, {self._target_waypoint.lon:.6f})"
        
        # Log loop progress if in loop mode
        if self.waypoint_manager.is_loop_mode():
            current_idx = self.waypoint_manager._current_index
            total_wps = len(self.waypoint_manager._waypoints)
            loop_num = self.waypoint_manager.get_loop_count() + 1
            logger.info(f"✅ Waypoint {current_idx + 1}/{total_wps} reached: '{waypoint_name}' (Loop #{loop_num})")
        else:
            logger.info(f"✅ Waypoint reached: '{waypoint_name}' at {waypoint_coords} (tolerance: {self._target_waypoint.tolerance}m)")
        
        self._status = NavigationStatus.REACHED_WAYPOINT
        
        if self._mode == NavigationMode.PATH_FOLLOWING:
            # Move to next waypoint (or cycle in loop mode)
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
                
                if self.waypoint_manager.is_loop_mode():
                    logger.info(f"📍 Moving to next waypoint: '{next_waypoint_name}' (Loop continues)")
                else:
                    logger.info(f"📍 Moving to next waypoint: '{next_waypoint_name}' ({remaining} waypoints remaining)")
            else:
                # Path complete (only happens in non-loop mode)
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
        self._navigation_phase = NavigationPhase.IDLE
        self._phase_start_time = None
        
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
            
            # 🔧 NEW: Reset state machine
            self._navigation_phase = NavigationPhase.IDLE
            self._phase_start_time = None
            self._calibration_mode = False
            
            logger.info("Navigator stopped")
    
    def pause(self):
        """Pause navigation"""
        with self._lock:
            if self._is_running:
                self._is_paused = True
                self._status = NavigationStatus.PAUSED
                self.heading_pid.reset()
                
                # 🔧 NEW: Pause state machine (will resume from same phase)
                # Don't reset phase - remember where we were
                
                waypoint_name = self._target_waypoint.name if self._target_waypoint else "None"
                logger.info(f"⏸️  Navigator paused (current target: '{waypoint_name}', phase: {self._navigation_phase.value})")
    
    def resume(self):
        """Resume navigation"""
        with self._lock:
            if self._is_running and self._is_paused:
                self._is_paused = False
                self._status = NavigationStatus.NAVIGATING if self._target_waypoint else NavigationStatus.IDLE
                self.heading_pid.reset()
                
                # 🔧 NEW: Resume from current phase (or reset to ALIGN if no phase)
                if self._navigation_phase == NavigationPhase.IDLE and self._target_waypoint:
                    self._navigation_phase = NavigationPhase.ALIGNING
                    self._phase_start_time = datetime.now()
                
                waypoint_name = self._target_waypoint.name if self._target_waypoint else "None"
                logger.info(f"▶️  Navigator resumed (target: '{waypoint_name}', phase: {self._navigation_phase.value})")
    
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
    
    def set_loop_mode(self, enabled: bool):
        """
        Enable or disable loop mode for path following
        
        Args:
            enabled: True to enable continuous loop, False for one-time path
        """
        with self._lock:
            self.waypoint_manager.set_loop_mode(enabled)
            mode_str = "enabled" if enabled else "disabled"
            logger.info(f"🔄 Navigator loop mode {mode_str}")
    
    def is_loop_mode(self) -> bool:
        """Check if loop mode is currently enabled"""
        return self.waypoint_manager.is_loop_mode()
    
    def get_loop_count(self) -> int:
        """Get number of complete loops (only relevant in loop mode)"""
        return self.waypoint_manager.get_loop_count()
