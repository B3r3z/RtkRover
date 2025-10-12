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
                 safety_timeout: float = 2.0):
        """
        Initialize motor controller
        
        Args:
            motor_driver: Motor driver implementation
            max_speed: Maximum speed multiplier (0.0 to 1.0)
            turn_sensitivity: Turn rate sensitivity multiplier
            safety_timeout: Stop motors if no command received for this many seconds
        """
        self.motor_driver = motor_driver
        self.max_speed = max_speed
        self.turn_sensitivity = turn_sensitivity
        self.safety_timeout = safety_timeout
        
        self._is_running = False
        self._last_command_time: Optional[datetime] = None
        self._current_command: Optional[DifferentialDriveCommand] = None
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Safety monitoring thread
        self._safety_thread: Optional[threading.Thread] = None
        self._stop_safety_thread = threading.Event()
        
        logger.info("Motor controller initialized")
    
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
            logger.warning("Motor controller not running")
            return
        
        # Convert navigation command to differential drive
        diff_command = self._navigation_to_differential(nav_command)
        
        # Execute command
        self.execute_differential_command(diff_command)
        
        logger.debug(f"Executed nav command: speed={nav_command.speed:.2f}, turn={nav_command.turn_rate:.2f}")
    
    def execute_differential_command(self, command: DifferentialDriveCommand):
        """
        Execute differential drive command
        
        Args:
            command: Differential drive command with left/right speeds
        """
        if not self._is_running:
            logger.warning("Motor controller not running")
            return
        
        with self._lock:
            self._current_command = command
            self._last_command_time = datetime.now()
        
        # Apply speed limits
        left_speed = command.left_speed * self.max_speed
        right_speed = command.right_speed * self.max_speed
        
        # Set left motor
        left_dir = MotorDirection.FORWARD if left_speed >= 0 else MotorDirection.BACKWARD
        self.motor_driver.set_motor('left', left_dir, abs(left_speed))
        
        # Set right motor
        right_dir = MotorDirection.FORWARD if right_speed >= 0 else MotorDirection.BACKWARD
        self.motor_driver.set_motor('right', right_dir, abs(right_speed))
        
        logger.debug(f"Differential command: L={left_speed:.2f}, R={right_speed:.2f}")
    
    def _navigation_to_differential(self, nav_command: NavigationCommand) -> DifferentialDriveCommand:
        """
        Convert navigation command (speed, turn_rate) to differential drive (left, right)
        
        Differential drive equation:
        - For forward movement with turn:
          left_speed = speed - turn_rate
          right_speed = speed + turn_rate
        
        Args:
            nav_command: Navigation command
            
        Returns:
            Differential drive command
        """
        speed = nav_command.speed
        turn = nav_command.turn_rate * self.turn_sensitivity
        
        # Calculate differential speeds
        left_speed = speed - turn
        right_speed = speed + turn
        
        # Normalize if speeds exceed limits
        max_abs = max(abs(left_speed), abs(right_speed))
        if max_abs > 1.0:
            left_speed /= max_abs
            right_speed /= max_abs
        
        return DifferentialDriveCommand(
            left_speed=left_speed,
            right_speed=right_speed
        )
    
    def emergency_stop(self):
        """Emergency stop - immediately stop all motors"""
        logger.warning("EMERGENCY STOP")
        self.motor_driver.stop_all()
        
        with self._lock:
            self._current_command = None
            self._last_command_time = None
    
    def _safety_monitor(self):
        """
        Safety monitoring thread
        Stops motors if no command received within timeout period
        """
        logger.info("Safety monitor started")
        
        while not self._stop_safety_thread.wait(timeout=0.5):
            with self._lock:
                if self._last_command_time is not None:
                    time_since_last = (datetime.now() - self._last_command_time).total_seconds()
                    
                    if time_since_last > self.safety_timeout:
                        logger.warning(f"Safety timeout: no command for {time_since_last:.1f}s - stopping motors")
                        self.motor_driver.stop_all()
                        self._current_command = None
        
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
