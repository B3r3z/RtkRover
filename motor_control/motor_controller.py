"""High-level motor controller for differential drive robots"""
import logging
import threading
from typing import Optional
from datetime import datetime, timedelta

from .motor_interface import MotorDriverInterface, MotorDirection, DifferentialDriveCommand
from navigation.core.data_types import NavigationCommand

logger = logging.getLogger(__name__)


class MotorController:
    """
    High-level controller for differential drive robots
    Translates navigation commands into motor control signals
    """
    
    def __init__(self, 
                 motor_driver: MotorDriverInterface,
                 max_speed: float = 1.0,
                 turn_sensitivity: float = 1.0,
                 safety_timeout: float = 2.0,
                 ramp_rate: float = 0.5):
        """
        Initialize motor controller
        
        Args:
            motor_driver: Motor driver implementation
            max_speed: Maximum speed multiplier (0.0 to 1.0)
            turn_sensitivity: Turn rate sensitivity multiplier
            safety_timeout: Stop motors if no command received for this many seconds
            ramp_rate: Acceleration rate per cycle (0.0 to 1.0). Higher = faster acceleration
        """
        self.motor_driver = motor_driver
        self.max_speed = max_speed
        self.turn_sensitivity = turn_sensitivity
        self.safety_timeout = safety_timeout
        self._ramp_rate = max(0.01, min(1.0, ramp_rate))  # Clamp to valid range
        
        self._is_running = False
        self._last_command_time: Optional[datetime] = None
        self._current_command: Optional[DifferentialDriveCommand] = None
        
        # Motor ramping state for smooth acceleration/deceleration
        self._current_left_speed = 0.0
        self._current_right_speed = 0.0
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Emergency stop event for immediate response
        self._emergency_stop_event = threading.Event()
        
        # Safety monitoring thread
        self._safety_thread: Optional[threading.Thread] = None
        self._stop_safety_thread = threading.Event()
        
        logger.info(f"Motor controller initialized (ramp_rate={self._ramp_rate:.2f}, safety_timeout={safety_timeout:.1f}s)")
    
    def start(self) -> bool:
        """Start motor controller"""
        if self._is_running:
            logger.warning("Motor controller already running")
            return False
        
        # Initialize motor driver
        if not self.motor_driver.initialize():
            logger.error("Failed to initialize motor driver")
            return False
        
        self._is_running = True
        self._stop_safety_thread.clear()
        
        # Start safety monitoring thread
        self._safety_thread = threading.Thread(target=self._safety_monitor, daemon=True)
        self._safety_thread.start()
        
        logger.info("Motor controller started")
        return True
    
    def stop(self):
        """Stop motor controller"""
        if not self._is_running:
            return
        
        logger.info("Stopping motor controller")
        
        self._is_running = False
        self._stop_safety_thread.set()
        
        # Stop motors
        self.emergency_stop()
        
        # Wait for safety thread
        if self._safety_thread:
            self._safety_thread.join(timeout=2.0)
        
        # Cleanup driver
        self.motor_driver.cleanup()
        
        logger.info("Motor controller stopped")
    
    def execute_navigation_command(self, nav_command: NavigationCommand):
        """
        Execute navigation command by translating to motor speeds
        
        Args:
            nav_command: Navigation command with speed and turn_rate
        """
        if not self._is_running:
            logger.error("⚠️  MOTOR CONTROLLER NOT RUNNING - COMMAND REJECTED!")
            logger.error(f"   Command: speed={nav_command.speed:.2f}, turn={nav_command.turn_rate:.2f}")
            logger.error(f"   Call motor_controller.start() first!")
            return
        
        # Convert navigation command to differential drive
        diff_command = self._navigation_to_differential(nav_command)
        
        # Execute command
        self.execute_differential_command(diff_command)
        
        logger.debug(f"Executed nav command: speed={nav_command.speed:.2f}, turn={nav_command.turn_rate:.2f} → L={diff_command.left_speed:.2f}, R={diff_command.right_speed:.2f}")
    
    def _apply_ramping(self, target_left: float, target_right: float) -> tuple[float, float]:
        """
        Apply smooth acceleration/deceleration ramping to motor speeds
        
        Args:
            target_left: Target left motor speed (-1.0 to 1.0)
            target_right: Target right motor speed (-1.0 to 1.0)
        
        Returns:
            tuple: (ramped_left_speed, ramped_right_speed)
        """
        # Ramp left motor
        left_delta = target_left - self._current_left_speed
        if abs(left_delta) > self._ramp_rate:
            sign = 1 if left_delta > 0 else -1
            self._current_left_speed += self._ramp_rate * sign
        else:
            self._current_left_speed = target_left
        
        # Ramp right motor
        right_delta = target_right - self._current_right_speed
        if abs(right_delta) > self._ramp_rate:
            sign = 1 if right_delta > 0 else -1
            self._current_right_speed += self._ramp_rate * sign
        else:
            self._current_right_speed = target_right
        
        # Log only if speeds changed significantly
        if abs(left_delta) > 0.01 or abs(right_delta) > 0.01:
            logger.debug(f"Ramp: target=({target_left:.2f},{target_right:.2f}) → actual=({self._current_left_speed:.2f},{self._current_right_speed:.2f})")
        
        return self._current_left_speed, self._current_right_speed
    
    def execute_differential_command(self, command: DifferentialDriveCommand):
        """
        Execute differential drive command
        
        Args:
            command: Differential drive command with left/right speeds
        """
        if not self._is_running:
            logger.error("⚠️  MOTOR CONTROLLER NOT RUNNING - COMMAND REJECTED!")
            logger.error(f"   Command: L={command.left_speed:.2f}, R={command.right_speed:.2f}")
            return
        
        with self._lock:
            self._current_command = command
            self._last_command_time = datetime.now()
        
        # Calculate target speeds
        target_left = command.left_speed * self.max_speed
        target_right = command.right_speed * self.max_speed
        
        # Apply ramping for smooth acceleration
        left_speed, right_speed = self._apply_ramping(target_left, target_right)
        
        # Set left motor
        left_dir = MotorDirection.FORWARD if left_speed >= 0 else MotorDirection.BACKWARD
        self.motor_driver.set_motor('left', left_dir, abs(left_speed))
        
        # Set right motor
        right_dir = MotorDirection.FORWARD if right_speed >= 0 else MotorDirection.BACKWARD
        self.motor_driver.set_motor('right', right_dir, abs(right_speed))
        
        # Log motor execution (INFO level for visibility during debugging)
        if abs(left_speed) > 0.01 or abs(right_speed) > 0.01:
            logger.info(f"⚙️  Motors: L={left_speed:.2f}, R={right_speed:.2f}")
        else:
            logger.debug(f"Motors stopped: L={left_speed:.2f}, R={right_speed:.2f}")
    
    def _navigation_to_differential(self, nav_command: NavigationCommand) -> DifferentialDriveCommand:
        """
        Convert navigation command (speed, turn_rate) to differential drive (left, right)
        
        Supports two modes:
        1. Forward motion with turn: speed > 0, turn_rate adjusts L/R differential
        2. Rotation in place: speed = 0, turn_rate causes rotation (for ALIGN phase)
        
        Improved differential drive equation with better normalization:
        - For forward movement with turn:
          left_speed = speed - turn_rate
          right_speed = speed + turn_rate
        - For rotation in place (speed = 0):
          left_speed = -turn_rate
          right_speed = turn_rate
        - Preserves turn ratio when normalizing
        
        Args:
            nav_command: Navigation command
            
        Returns:
            Differential drive command
        """
        speed = nav_command.speed
        turn = nav_command.turn_rate * self.turn_sensitivity
        
        # Check for rotation in place (ALIGN phase)
        if speed == 0.0 and turn != 0.0:
            # Rotate in place: motors in opposite directions
            left_speed = -turn
            right_speed = turn
            # 🔧 IMPROVED: Log first few turn-in-place commands at INFO level for visibility
            if not hasattr(self, '_turn_in_place_count'):
                self._turn_in_place_count = 0
            if self._turn_in_place_count < 3:
                logger.info(f"🔄 Turn-in-place mode: L={left_speed:.2f}, R={right_speed:.2f} (turn={turn:.2f})")
                self._turn_in_place_count += 1
            else:
                logger.debug(f"Turn-in-place: L={left_speed:.2f}, R={right_speed:.2f} (turn={turn:.2f})")
        else:
            # Standard differential drive for forward/backward motion
            # Reset turn-in-place counter when not turning
            if hasattr(self, '_turn_in_place_count'):
                self._turn_in_place_count = 0
            
            left_speed = speed - turn
            right_speed = speed + turn
            
            # Improved normalization that preserves turn characteristics
            # Find the maximum absolute value
            max_abs = max(abs(left_speed), abs(right_speed))
            
            if max_abs > 1.0:
                # Scale both speeds proportionally to maintain turn ratio
                scale_factor = 1.0 / max_abs
                left_speed *= scale_factor
                right_speed *= scale_factor
                
                logger.debug(f"Normalized speeds by {scale_factor:.2f} to maintain turn ratio")
        
        return DifferentialDriveCommand(
            left_speed=left_speed,
            right_speed=right_speed
        )
    
    def emergency_stop(self):
        """Emergency stop - immediately stop all motors using event-driven mechanism"""
        logger.warning("EMERGENCY STOP")
        
        # Set emergency stop event for immediate response
        self._emergency_stop_event.set()
        
        # Stop motors immediately
        self.motor_driver.stop_all()
        
        with self._lock:
            self._current_command = None
            self._last_command_time = None
            # Reset ramping state
            self._current_left_speed = 0.0
            self._current_right_speed = 0.0
        
        # Clear event after handling
        self._emergency_stop_event.clear()
    
    def _safety_monitor(self):
        """
        Event-driven safety monitoring thread
        Checks for timeout and responds immediately to emergency stop events
        More responsive than pure polling
        """
        logger.info("Safety monitor started (event-driven)")
        
        # Use shorter wait intervals for better responsiveness
        check_interval = 0.1  # 100ms checks instead of 500ms
        
        while not self._stop_safety_thread.is_set():
            # Check for emergency stop event with timeout
            if self._emergency_stop_event.wait(timeout=check_interval):
                logger.info("Emergency stop event detected by safety monitor")
                # Event is already handled in emergency_stop(), just continue monitoring
                continue
            
            # Check safety timeout
            with self._lock:
                if self._last_command_time is not None:
                    time_since_last = (datetime.now() - self._last_command_time).total_seconds()
                    
                    if time_since_last > self.safety_timeout:
                        logger.warning(f"Safety timeout: no command for {time_since_last:.1f}s - stopping motors")
                        self.motor_driver.stop_all()
                        self._current_command = None
                        # Reset ramping state on timeout
                        self._current_left_speed = 0.0
                        self._current_right_speed = 0.0
        
        logger.info("Safety monitor stopped")
    
    def get_status(self) -> dict:
        """Get current motor controller status"""
        with self._lock:
            return {
                'is_running': self._is_running,
                'driver_initialized': self.motor_driver.is_initialized(),
                'current_command': {
                    'left_speed': self._current_command.left_speed,
                    'right_speed': self._current_command.right_speed
                } if self._current_command else None,
                'last_command_time': self._last_command_time.isoformat() if self._last_command_time else None,
                'time_since_last_command': (datetime.now() - self._last_command_time).total_seconds() 
                                          if self._last_command_time else None,
                'max_speed': self.max_speed,
                'turn_sensitivity': self.turn_sensitivity,
                'safety_timeout': self.safety_timeout
            }
    
    def set_max_speed(self, speed: float):
        """Set maximum speed (0.0 to 1.0)"""
        self.max_speed = max(0.0, min(1.0, speed))
        logger.info(f"Max speed set to {self.max_speed:.2f}")
    
    def set_turn_sensitivity(self, sensitivity: float):
        """Set turn sensitivity multiplier"""
        self.turn_sensitivity = max(0.1, min(2.0, sensitivity))
        logger.info(f"Turn sensitivity set to {self.turn_sensitivity:.2f}")
