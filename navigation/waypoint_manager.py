"""Waypoint queue manager implementation"""
from typing import List, Optional
from .core.interfaces import WaypointManager
from .core.data_types import Waypoint
import logging

logger = logging.getLogger(__name__)


class SimpleWaypointManager(WaypointManager):
    """Simple FIFO waypoint queue manager"""
    
    def __init__(self):
        self._waypoints: List[Waypoint] = []
        self._current_index = 0
    
    def add_waypoint(self, waypoint: Waypoint):
        """Add waypoint to end of queue"""
        self._waypoints.append(waypoint)
        logger.info(f"Added waypoint: {waypoint.name or 'Unnamed'} at ({waypoint.lat:.6f}, {waypoint.lon:.6f})")
    
    def get_next_waypoint(self) -> Optional[Waypoint]:
        """Get next waypoint in queue without removing it"""
        if self._current_index < len(self._waypoints):
            return self._waypoints[self._current_index]
        return None
    
    def advance_to_next(self) -> bool:
        """Move to next waypoint in queue"""
        if self._current_index < len(self._waypoints) - 1:
            self._current_index += 1
            logger.info(f"Advanced to waypoint {self._current_index + 1}/{len(self._waypoints)}")
            return True
        return False
    
    def clear_waypoints(self):
        """Clear all waypoints"""
        self._waypoints.clear()
        self._current_index = 0
        logger.info("Cleared all waypoints")
    
    def get_all_waypoints(self) -> List[Waypoint]:
        """Get all waypoints in queue"""
        return self._waypoints.copy()
    
    def remove_waypoint(self, index: int) -> bool:
        """Remove waypoint at specific index"""
        if 0 <= index < len(self._waypoints):
            removed = self._waypoints.pop(index)
            if index < self._current_index:
                self._current_index -= 1
            logger.info(f"Removed waypoint at index {index}: {removed.name or 'Unnamed'}")
            return True
        return False
    
    def get_remaining_count(self) -> int:
        """Get number of waypoints remaining (including current)"""
        return max(0, len(self._waypoints) - self._current_index)
    
    def reset_to_start(self):
        """Reset to first waypoint"""
        self._current_index = 0
        logger.info("Reset to first waypoint")
