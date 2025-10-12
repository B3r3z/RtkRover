"""Simple path planner implementation"""
from typing import List, Tuple, Optional
from ..core.interfaces import PathPlanner
from ..core.data_types import Waypoint
from .geo_utils import GeoUtils


class SimplePathPlanner(PathPlanner):
    """
    Simple direct-line path planner
    For more complex scenarios, this can be extended with A* or other algorithms
    """
    
    def __init__(self):
        self.geo_utils = GeoUtils()
    
    def calculate_path(self, start: tuple, end: tuple, obstacles: List = None) -> List[Waypoint]:
        """
        Calculate simple direct path from start to end
        
        Args:
            start: (lat, lon) starting point
            end: (lat, lon) ending point
            obstacles: List of obstacles (not implemented in simple planner)
            
        Returns:
            List containing single waypoint at destination
        """
        # For simple planner, just return direct waypoint
        # More complex implementations would add intermediate waypoints
        return [Waypoint(lat=end[0], lon=end[1], name="Target")]
    
    def calculate_heading(self, current: tuple, target: tuple) -> float:
        """
        Calculate required heading to target
        
        Args:
            current: (lat, lon) current position
            target: (lat, lon) target position
            
        Returns:
            Heading in degrees (0-360)
        """
        return self.geo_utils.calculate_bearing(
            current[0], current[1],
            target[0], target[1]
        )
    
    def calculate_distance(self, point1: tuple, point2: tuple) -> float:
        """
        Calculate distance between two points
        
        Args:
            point1: (lat, lon)
            point2: (lat, lon)
            
        Returns:
            Distance in meters
        """
        return self.geo_utils.haversine_distance(
            point1[0], point1[1],
            point2[0], point2[1]
        )
    
    def is_waypoint_reached(self, current: tuple, waypoint: Waypoint) -> bool:
        """
        Check if waypoint is reached within tolerance
        
        Args:
            current: (lat, lon) current position
            waypoint: Target waypoint
            
        Returns:
            True if within tolerance radius
        """
        distance = self.calculate_distance(current, (waypoint.lat, waypoint.lon))
        return distance <= waypoint.tolerance
