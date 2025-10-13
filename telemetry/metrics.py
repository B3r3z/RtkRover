"""Telemetry and metrics collection for RTK Rover"""
from dataclasses import dataclass, field
from typing import List
from datetime import datetime
import statistics


@dataclass
class NavigationMetrics:
    """Metrics for navigation performance tracking"""
    
    # Waypoint metrics
    waypoints_reached: int = 0
    waypoints_missed: int = 0
    
    # Distance and time
    total_distance: float = 0.0  # meters
    total_time: float = 0.0  # seconds
    
    # Accuracy
    average_accuracy: float = 0.0  # meters from waypoint center
    accuracy_samples: List[float] = field(default_factory=list)
    
    # Performance
    max_speed: float = 0.0  # m/s
    
    # Errors and events
    gps_loss_events: int = 0
    navigation_errors: int = 0
    emergency_stops: int = 0
    
    # Session info
    session_start: datetime = field(default_factory=datetime.now)
    
    def add_waypoint_reached(self, accuracy: float):
        """Record a waypoint being reached"""
        self.waypoints_reached += 1
        self.accuracy_samples.append(accuracy)
        if self.accuracy_samples:
            self.average_accuracy = statistics.mean(self.accuracy_samples)
    
    def add_waypoint_missed(self):
        """Record a waypoint being missed"""
        self.waypoints_missed += 1
    
    def add_gps_loss_event(self):
        """Record GPS loss event"""
        self.gps_loss_events += 1
    
    def add_navigation_error(self):
        """Record navigation error"""
        self.navigation_errors += 1
    
    def add_emergency_stop(self):
        """Record emergency stop"""
        self.emergency_stops += 1
    
    def update_max_speed(self, speed: float):
        """Update maximum speed if higher"""
        if speed > self.max_speed:
            self.max_speed = speed
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary"""
        return {
            'waypoints_reached': self.waypoints_reached,
            'waypoints_missed': self.waypoints_missed,
            'total_distance_m': round(self.total_distance, 2),
            'total_time_s': round(self.total_time, 2),
            'average_accuracy_m': round(self.average_accuracy, 2),
            'max_speed_ms': round(self.max_speed, 2),
            'gps_loss_events': self.gps_loss_events,
            'navigation_errors': self.navigation_errors,
            'emergency_stops': self.emergency_stops,
            'session_start': self.session_start.isoformat(),
            'session_duration_s': (datetime.now() - self.session_start).total_seconds()
        }
