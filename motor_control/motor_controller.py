"""High-level motor controller for differential drive robots"""
import logging
import threading
from typing import Optional
from datetime import datetime

from .motor_interface import MotorDriverInterface, MotorDirection, DifferentialDriveCommand
from navigation.types import NavigationCommand

logger = logging.getLogger(__name__)


class MotorController:
    """
    High-level controller for differential drive robots
    Translates navigation commands (v, w) into motor control signals (left, right)
    """
    
    def __init__(self, 
                 motor_driver: MotorDriverInterface,
                 max_speed: float = 1.0,
                 wheel_base: float = 0.5):  # Distance between wheels in meters (approx) 
        """
        Initialize motor controller
        
        Args:
            motor_driver: Motor driver implementation
            max_speed: Maximum speed multiplier (0.0 to 1.0)
            wheel_base: Distance between wheels in meters (used for kinematics)
        """
        self.motor_driver = motor_driver
        self.max_speed = max_speed
        self.wheel_base = wheel_base
        
        self._is_running = False
        
        # Thread safety
        self._lock = threading.Lock()
        
        logger.info(f"Motor controller initialized (max_speed={max_speed})")
    
    def start(self) -> bool:
        """Start motor controller"""
        with self._lock:
            if self._is_running:
                return True
            
            # Initialize motor driver
            if not self.motor_driver.initialize():
                logger.error("Failed to initialize motor driver")
                return False
            
            self._is_running = True
            
            logger.info("Motor controller started")
            return True
    
    def stop(self):
        """Stop motor controller"""
        with self._lock:
            if not self._is_running:
                return
            
            self._is_running = False
            
            # Stop motors
            self.motor_driver.stop_all()
            
        # Cleanup driver
        self.motor_driver.cleanup()
        logger.info("Motor controller stopped")
    
    def execute_navigation_command(self, nav_command: NavigationCommand):
        """
        Execute navigation command by translating to motor speeds
        
        Args:
            nav_command: Navigation command with speed (m/s) and turn_rate (rad/s)
        """
        if not self._is_running:
            return
        
        # Kinematics: Convert (v, w) to (v_left, v_right)
        # v_left = v - (w * L / 2)
        # v_right = v + (w * L / 2)
        # where L is wheel base
        
        v = nav_command.speed
        w = nav_command.turn_rate
        
        # Simple differential drive kinematics
        # Note: This assumes 'speed' is normalized 0-1 or similar, 
        # but if it's m/s we might need scaling. 
        # For now, we assume the input speed is compatible with motor driver expectations 
        # or we clamp it.
        
        # If turn_rate is just a ratio (-1 to 1), we treat it simply:
        left_speed = v - w
        right_speed = v + w
        
        # Normalize if exceeding max speed
        max_val = max(abs(left_speed), abs(right_speed))
        if max_val > 1.0:
            left_speed /= max_val
            right_speed /= max_val
            
        # Apply global max speed limit
        left_speed *= self.max_speed
        right_speed *= self.max_speed
        
        self._set_motors(left_speed, right_speed)
        
    def _set_motors(self, left_speed: float, right_speed: float):
        """Internal helper to set motor speeds"""
        # Set left motor
        left_dir = MotorDirection.FORWARD if left_speed >= 0 else MotorDirection.BACKWARD
        self.motor_driver.set_motor('left', left_dir, abs(left_speed))
        
        # Set right motor
        right_dir = MotorDirection.FORWARD if right_speed >= 0 else MotorDirection.BACKWARD
        self.motor_driver.set_motor('right', right_dir, abs(right_speed))

