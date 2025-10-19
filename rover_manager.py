"""
Rover Manager - Main integration class
Coordinates GPS, Navigation, and Motor Control systems
"""
import logging
import threading
import time
from typing import Optional
from datetime import datetime
from queue import Queue, Empty, Full

from gps.core.interfaces import PositionObserver, Position
from navigation.navigator import Navigator
from navigation.core.data_types import Waypoint, NavigationMode
from motor_control.motor_controller import MotorController
from motor_control.drivers.l298n_driver import L298NDriver
from config.motor_settings import motor_gpio_pins, motor_config, navigation_config
from telemetry.metrics import NavigationMetrics

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
        
        # Position update queue for thread-safe GPS updates
        self._position_queue = Queue(maxsize=10)
        self._last_processed_position: Optional[Position] = None
        
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
        
        # Emergency stop tracking
        self._last_emergency_stop: Optional[dict] = None
        
        # Telemetry
        self.metrics = NavigationMetrics()
        
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
        Thread-safe queuing of position updates for processing in control loop
        
        Args:
            position: New GPS position
        """
        try:
            # Try to add position to queue
            self._position_queue.put_nowait(position)
            logger.debug(f"Queued position: ({position.lat:.6f}, {position.lon:.6f})")
        except Full:
            # Queue full - drop oldest position and add new one
            try:
                self._position_queue.get_nowait()
                self._position_queue.put_nowait(position)
                logger.warning("Position queue full, dropped oldest position")
            except Exception as e:
                logger.error(f"Failed to queue position update: {e}")
    
    def _process_position_update(self, position: Position):
        """
        Process a single position update from the queue
        
        Args:
            position: GPS position to process
        """
        heading = getattr(position, 'heading', None)
        speed = getattr(position, 'speed', None)
        
        self.navigator.update_position(
            lat=position.lat,
            lon=position.lon,
            heading=heading,
            speed=speed
        )
        
        logger.debug(f"Processed position: ({position.lat:.6f}, {position.lon:.6f})")
    
    def _check_gps_health(self) -> tuple[bool, str]:
        """
        Check GPS health and quality
        
        Returns:
            tuple: (is_healthy: bool, error_message: str)
        """
        if not self.rtk_manager:
            return False, "RTK Manager not available"
        
        position = self.rtk_manager.get_current_position()
        
        if not position:
            return False, "No GPS position available"
        
        # Check satellite count
        satellites = position.get('satellites', 0)
        if satellites < 4:
            return False, f"Insufficient satellites: {satellites}"
        
        # Check HDOP (Horizontal Dilution of Precision)
        hdop = position.get('hdop', 999)
        if hdop > 5.0:
            return False, f"Poor GPS accuracy (HDOP: {hdop:.1f})"
        
        # Check timestamp freshness
        timestamp_str = position.get('timestamp')
        if timestamp_str:
            try:
                from datetime import timezone
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                age = (datetime.now(timezone.utc) - timestamp).total_seconds()
                if age > 3.0:
                    return False, f"GPS data too old: {age:.1f}s"
            except Exception as e:
                logger.warning(f"Could not parse GPS timestamp: {e}")
        
        return True, ""
    
    def _control_loop(self):
        """
        Main control loop with GPS health monitoring
        Runs at regular intervals to generate and execute navigation commands
        """
        logger.info("Control loop started")
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while not self._stop_control.wait(timeout=self._update_rate):
            try:
                # Process all pending position updates
                positions_processed = 0
                while not self._position_queue.empty():
                    try:
                        position = self._position_queue.get_nowait()
                        self._process_position_update(position)
                        self._last_processed_position = position
                        positions_processed += 1
                    except Empty:
                        break
                    except Exception as e:
                        logger.error(f"Error processing position update: {e}")
                
                if positions_processed > 1:
                    logger.debug(f"Processed {positions_processed} position updates in this cycle")
                
                # 1. Check GPS health
                gps_healthy, gps_error = self._check_gps_health()
                if not gps_healthy:
                    logger.warning(f"GPS unhealthy: {gps_error}")
                    self.motor_controller.emergency_stop()
                    self.metrics.add_gps_loss_event()
                    consecutive_errors += 1
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"GPS unhealthy for {consecutive_errors} cycles, pausing navigation")
                        self.navigator.pause()
                        consecutive_errors = 0
                    
                    continue
                else:
                    consecutive_errors = 0
                
                # 2. Get navigation command
                nav_command = self.navigator.get_navigation_command()
                
                if nav_command:
                    # Execute command via motor controller
                    logger.debug(f"🚗 Nav command: speed={nav_command.speed:.2f}, turn={nav_command.turn_rate:.2f}")
                    self.motor_controller.execute_navigation_command(nav_command)
                elif nav_command is None:
                    # No command (paused, idle, or error)
                    # Stop motors gently (not emergency stop which logs warnings)
                    from motor_control.motor_interface import DifferentialDriveCommand
                    stop_cmd = DifferentialDriveCommand(
                        left_speed=0.0,
                        right_speed=0.0
                    )
                    self.motor_controller.execute_differential_command(stop_cmd)
                
            except Exception as e:
                logger.error(f"Error in control loop: {e}", exc_info=True)
                consecutive_errors += 1
                
                # Safety: stop motors on error
                try:
                    self.motor_controller.emergency_stop()
                except:
                    pass
                
                # Too many errors - stop navigation
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical("Too many control loop errors, stopping navigation")
                    try:
                        self.navigator.stop()
                    except:
                        pass
                    break
        
        # Ensure motors are stopped when loop exits
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
            from navigation.core.data_types import NavigationMode, NavigationStatus
            
            # ✅ Guard: Warn if overwriting active path following
            nav_state = self.navigator.get_state()
            if (nav_state.mode == NavigationMode.PATH_FOLLOWING and 
                nav_state.status == NavigationStatus.NAVIGATING):
                logger.warning(f"⚠️  Overwriting active path following with single waypoint '{name or 'Unnamed'}'")
                logger.warning(f"   {nav_state.waypoints_remaining} waypoints will be lost!")
                logger.warning(f"   Use /cancel first to clear path, or this is intentional override")
                # Continue anyway - user may want to override
            
            waypoint = Waypoint(lat=lat, lon=lon, name=name)
            self.navigator.set_target(waypoint)
            logger.info(f"🎯 Navigating to waypoint: {name or 'Unnamed'}")
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
        
        # Gentle stop (not emergency) - pause is a normal operation
        from motor_control.motor_interface import DifferentialDriveCommand
        stop_cmd = DifferentialDriveCommand(left_speed=0.0, right_speed=0.0)
        self.motor_controller.execute_differential_command(stop_cmd)
        
        logger.info("Navigation paused - motors stopped gently")
    
    def resume_navigation(self):
        """Resume navigation"""
        self.navigator.resume()
        logger.info("Navigation resumed")
    
    def cancel_navigation(self):
        """
        Cancel current navigation - clears waypoints and stops everything
        Unlike emergency_stop which pauses, this completely resets navigation
        """
        # 1. Stop navigation system completely (clears target, sets IDLE)
        self.navigator.stop()
        logger.info("Navigation stopped and cleared")
        
        # 2. Stop motors
        try:
            self.motor_controller.emergency_stop()
            logger.info("Motors stopped during cancel")
        except Exception as e:
            logger.error(f"Failed to stop motors during cancel: {e}")
        
        logger.info("Navigation cancelled - system reset to IDLE")
    
    def emergency_stop(self, reason: str = "Manual"):
        """
        Emergency stop - immediately halt all movement AND pause navigation
        Navigation can be resumed later with resume_navigation()
        
        Args:
            reason: Reason for emergency stop (for logging/telemetry)
        """
        logger.critical(f"🛑 EMERGENCY STOP: {reason}")
        
        # 1. Stop motors immediately
        try:
            self.motor_controller.emergency_stop()
        except Exception as e:
            logger.error(f"Failed to stop motors during emergency stop: {e}")
        
        # 2. PAUSE navigation (not stop) - so it can be resumed later
        try:
            self.navigator.pause()
            logger.info("Navigation PAUSED during emergency stop (can be resumed)")
        except Exception as e:
            logger.error(f"Failed to pause navigator during emergency stop: {e}")
    
        self._last_emergency_stop = {
            'timestamp': datetime.now().isoformat(),
            'reason': reason
        }
        self.metrics.add_emergency_stop()
        
        logger.info("Emergency stop: motors stopped, navigation paused (resumable)")
    
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
        """
        Add waypoint to queue (does NOT start navigation automatically)
        Use start_navigation() to begin following waypoints
        """
        try:
            waypoint = Waypoint(lat=lat, lon=lon, name=name)
            self.navigator.add_waypoint(waypoint, auto_start=False)
            return True
        except Exception as e:
            logger.error(f"Failed to add waypoint: {e}")
            return False
    
    def start_navigation(self) -> bool:
        """
        Start navigation with queued waypoints
        
        Returns:
            True if started successfully, False otherwise
        """
        return self.navigator.start_navigation()
    
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
