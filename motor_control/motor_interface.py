"""Motor driver interface and data structures"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class MotorDirection(Enum):
    """Motor rotation direction"""
    FORWARD = "forward"
    BACKWARD = "backward"
    STOP = "stop"


@dataclass
class MotorCommand:
    """Command for individual motor"""
    direction: MotorDirection
    speed: float  # 0.0 to 1.0
    
    def __post_init__(self):
        # Clamp speed
        self.speed = max(0.0, min(1.0, self.speed))


@dataclass
class DifferentialDriveCommand:
    """Command for differential drive system (left/right motors)"""
    left_speed: float  # -1.0 to 1.0 (negative = reverse)
    right_speed: float  # -1.0 to 1.0 (negative = reverse)
    
    def __post_init__(self):
        # Clamp values
        self.left_speed = max(-1.0, min(1.0, self.left_speed))
        self.right_speed = max(-1.0, min(1.0, self.right_speed))


class MotorDriverInterface(ABC):
    """Interface for motor driver implementations"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize motor driver hardware"""
        pass
    
    @abstractmethod
    def set_motor(self, motor_id: str, direction: MotorDirection, speed: float):
        """Set individual motor speed and direction"""
        pass
    
    @abstractmethod
    def stop_all(self):
        """Emergency stop all motors"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """Clean up resources"""
        pass
    
    @abstractmethod
    def is_initialized(self) -> bool:
        """Check if driver is initialized"""
        pass
