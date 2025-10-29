"""Waypoint queue manager implementation"""
from typing import List, Optional
from .core.interfaces import WaypointManager
from .core.data_types import Waypoint
import logging

logger = logging.getLogger(__name__)


class SimpleWaypointManager(WaypointManager):
    """Simple FIFO waypoint queue manager with optional loop support"""
    
    def __init__(self, loop_mode: bool = False):
        """
        Initialize waypoint manager
        
        Args:
            loop_mode: If True, cycles back to first waypoint after reaching the last one
        """
        self._waypoints: List[Waypoint] = []
        self._current_index = 0
        self._loop_mode = loop_mode
        self._loop_count = 0  # Track number of complete loops
    
    def add_waypoint(self, waypoint: Waypoint):
        """Add waypoint to end of queue"""
        self._waypoints.append(waypoint)
        position = len(self._waypoints)
        logger.info(f"➕ Added waypoint #{position}: '{waypoint.name or 'Unnamed'}' at ({waypoint.lat:.6f}, {waypoint.lon:.6f})")
    
    def get_next_waypoint(self) -> Optional[Waypoint]:
        """Get next waypoint in queue without removing it"""
        if self._current_index < len(self._waypoints):
            return self._waypoints[self._current_index]
        return None
    
    def advance_to_next(self) -> bool:
        """
        Move to next waypoint in queue
        
        Returns:
            True if advanced to next waypoint (or cycled in loop mode), False if path complete
        """
        if self._current_index < len(self._waypoints) - 1:
            self._current_index += 1
            current_wp = self._waypoints[self._current_index]
            logger.info(f"⏭️  Advanced to waypoint #{self._current_index + 1}/{len(self._waypoints)}: '{current_wp.name or 'Unnamed'}'")
            return True
        elif self._loop_mode and len(self._waypoints) > 0:
            # Loop back to first waypoint
            self._current_index = 0
            self._loop_count += 1
            current_wp = self._waypoints[self._current_index]
            logger.info(f"🔄 Loop #{self._loop_count + 1} - Cycling back to waypoint #1: '{current_wp.name or 'Unnamed'}'")
            return True
        return False
    
    def clear_waypoints(self):
        """Clear all waypoints"""
        count = len(self._waypoints)
        self._waypoints.clear()
        self._current_index = 0
        self._loop_count = 0
        logger.info(f"🗑️  Cleared {count} waypoint(s) from queue")
    
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
        """
        Get number of waypoints remaining (including current)
        In loop mode, returns total waypoints as there's no end
        """
        if self._loop_mode and len(self._waypoints) > 0:
            return len(self._waypoints)  # Always have waypoints in loop mode
        return max(0, len(self._waypoints) - self._current_index)
    
    def has_waypoints(self) -> bool:
        """Check if there are any waypoints in the queue"""
        return len(self._waypoints) > 0
    
    def reset_to_start(self):
        """Reset to first waypoint"""
        self._current_index = 0
        logger.info("Reset to first waypoint")
    
    def set_loop_mode(self, enabled: bool):
        """
        Enable or disable loop mode
        
        Args:
            enabled: True to enable loop mode, False to disable
        """
        self._loop_mode = enabled
        mode_str = "enabled" if enabled else "disabled"
        logger.info(f"🔄 Loop mode {mode_str}")
    
    def is_loop_mode(self) -> bool:
        """Check if loop mode is enabled"""
        return self._loop_mode
    
    def get_loop_count(self) -> int:
        """Get number of complete loops (only relevant in loop mode)"""
        return self._loop_count
