"""Data structures for navigation system"""
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
from datetime import datetime


class NavigationMode(Enum):
    """Navigation operating modes"""
    MANUAL = "manual"
    WAYPOINT = "waypoint"
    PATH_FOLLOWING = "path_following"
    RETURN_TO_HOME = "return_to_home"
    HOLD_POSITION = "hold_position"


class NavigationStatus(Enum):
    """Current navigation status"""
    IDLE = "idle"
    NAVIGATING = "navigating"
    REACHED_WAYPOINT = "reached_waypoint"
    PATH_COMPLETE = "path_complete"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class Waypoint:
    """Represents a GPS waypoint"""
    lat: float
    lon: float
    name: Optional[str] = None
    altitude: Optional[float] = None
    tolerance: float = 2.0  # meters - radius to consider waypoint reached
    speed_limit: Optional[float] = None  # m/s
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self):
        return {
            'lat': self.lat,
            'lon': self.lon,
            'name': self.name,
            'altitude': self.altitude,
            'tolerance': self.tolerance,
            'speed_limit': self.speed_limit,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


@dataclass
class NavigationCommand:
    """Command for motor control system"""
    speed: float  # -1.0 to 1.0 (negative = reverse)
    turn_rate: float  # -1.0 to 1.0 (negative = left, positive = right)
    timestamp: datetime
    priority: int = 0  # Higher priority commands override lower
    
    def __post_init__(self):
        # Clamp values
        self.speed = max(-1.0, min(1.0, self.speed))
        self.turn_rate = max(-1.0, min(1.0, self.turn_rate))
    
    def to_dict(self):
        return {
            'speed': self.speed,
            'turn_rate': self.turn_rate,
            'timestamp': self.timestamp.isoformat(),
            'priority': self.priority
        }


@dataclass
class NavigationState:
    """Complete navigation state"""
    current_position: Optional[tuple]  # (lat, lon)
    target_waypoint: Optional[Waypoint]
    distance_to_target: Optional[float]  # meters
    bearing_to_target: Optional[float]  # degrees
    current_heading: Optional[float]  # degrees
    current_speed: Optional[float]  # m/s
    mode: NavigationMode
    status: NavigationStatus
    waypoints_remaining: int
    error_message: Optional[str] = None
    
    def to_dict(self):
        return {
            'current_position': self.current_position,
            'target_waypoint': self.target_waypoint.to_dict() if self.target_waypoint else None,
            'distance_to_target': self.distance_to_target,
            'bearing_to_target': self.bearing_to_target,
            'current_heading': self.current_heading,
            'current_speed': self.current_speed,
            'mode': self.mode.value,
            'status': self.status.value,
            'waypoints_remaining': self.waypoints_remaining,
            'error_message': self.error_message
        }
