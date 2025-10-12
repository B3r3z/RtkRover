"""Navigation system interfaces"""
from abc import ABC, abstractmethod
from typing import Optional, List
from .data_types import Waypoint, NavigationCommand, NavigationState


class NavigationInterface(ABC):
    """Main navigation system interface"""
    
    @abstractmethod
    def update_position(self, lat: float, lon: float, heading: Optional[float] = None):
        """Update current position from GPS"""
        pass
    
    @abstractmethod
    def set_target(self, waypoint: Waypoint):
        """Set target waypoint"""
        pass
    
    @abstractmethod
    def get_navigation_command(self) -> Optional[NavigationCommand]:
        """Calculate and return navigation command based on current state"""
        pass
    
    @abstractmethod
    def get_state(self) -> NavigationState:
        """Get current navigation state"""
        pass
    
    @abstractmethod
    def start(self) -> bool:
        """Start navigation"""
        pass
    
    @abstractmethod
    def stop(self):
        """Stop navigation"""
        pass
    
    @abstractmethod
    def pause(self):
        """Pause navigation"""
        pass
    
    @abstractmethod
    def resume(self):
        """Resume navigation"""
        pass


class PathPlanner(ABC):
    """Interface for path planning algorithms"""
    
    @abstractmethod
    def calculate_path(self, start: tuple, end: tuple, obstacles: List = None) -> List[Waypoint]:
        """Calculate path from start to end, avoiding obstacles"""
        pass
    
    @abstractmethod
    def calculate_heading(self, current: tuple, target: tuple) -> float:
        """Calculate required heading to target (in degrees)"""
        pass
    
    @abstractmethod
    def calculate_distance(self, point1: tuple, point2: tuple) -> float:
        """Calculate distance between two GPS coordinates (in meters)"""
        pass


class WaypointManager(ABC):
    """Interface for waypoint queue management"""
    
    @abstractmethod
    def add_waypoint(self, waypoint: Waypoint):
        """Add waypoint to queue"""
        pass
    
    @abstractmethod
    def get_next_waypoint(self) -> Optional[Waypoint]:
        """Get next waypoint from queue"""
        pass
    
    @abstractmethod
    def clear_waypoints(self):
        """Clear all waypoints"""
        pass
    
    @abstractmethod
    def get_all_waypoints(self) -> List[Waypoint]:
        """Get all waypoints in queue"""
        pass
    
    @abstractmethod
    def remove_waypoint(self, index: int) -> bool:
        """Remove waypoint at index"""
        pass
