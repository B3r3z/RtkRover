"""Geographic utility functions for navigation"""
import math
from typing import Tuple


class GeoUtils:
    """Utilities for geographic calculations"""
    
    EARTH_RADIUS = 6371000  # meters
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two GPS coordinates using Haversine formula
        
        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
            
        Returns:
            Distance in meters
        """
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        # Haversine formula
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        distance = GeoUtils.EARTH_RADIUS * c
        return distance
    
    @staticmethod
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate bearing from point 1 to point 2
        
        Args:
            lat1, lon1: Starting point coordinates
            lat2, lon2: Target point coordinates
            
        Returns:
            Bearing in degrees (0-360, where 0 is North)
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lon = math.radians(lon2 - lon1)
        
        x = math.sin(delta_lon) * math.cos(lat2_rad)
        y = (math.cos(lat1_rad) * math.sin(lat2_rad) -
             math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))
        
        bearing_rad = math.atan2(x, y)
        bearing_deg = math.degrees(bearing_rad)
        
        # Normalize to 0-360
        bearing_deg = (bearing_deg + 360) % 360
        return bearing_deg
    
    @staticmethod
    def normalize_angle(angle: float) -> float:
        """Normalize angle to -180 to 180 range"""
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle
    
    @staticmethod
    def calculate_angle_difference(current: float, target: float) -> float:
        """
        Calculate shortest angle difference between current and target heading
        
        Args:
            current: Current heading (0-360)
            target: Target heading (0-360)
            
        Returns:
            Angle difference (-180 to 180, negative = turn left, positive = turn right)
        """
        diff = target - current
        return GeoUtils.normalize_angle(diff)
    
    @staticmethod
    def destination_point(lat: float, lon: float, bearing: float, distance: float) -> Tuple[float, float]:
        """
        Calculate destination point given start point, bearing and distance
        
        Args:
            lat, lon: Starting point
            bearing: Bearing in degrees
            distance: Distance in meters
            
        Returns:
            Tuple of (lat, lon) of destination point
        """
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        bearing_rad = math.radians(bearing)
        
        angular_distance = distance / GeoUtils.EARTH_RADIUS
        
        dest_lat = math.asin(
            math.sin(lat_rad) * math.cos(angular_distance) +
            math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad)
        )
        
        dest_lon = lon_rad + math.atan2(
            math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
            math.cos(angular_distance) - math.sin(lat_rad) * math.sin(dest_lat)
        )
        
        return math.degrees(dest_lat), math.degrees(dest_lon)
