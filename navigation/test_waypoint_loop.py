"""
Unit tests for waypoint loop navigation functionality
Tests the loop mode feature added to waypoint_manager and navigator
"""
import unittest
from navigation.waypoint_manager import SimpleWaypointManager
from navigation.core.data_types import Waypoint


class TestWaypointLoopMode(unittest.TestCase):
    """Test cases for waypoint manager loop functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.waypoints = [
            Waypoint(lat=52.0, lon=21.0, name="WP1", tolerance=0.5),
            Waypoint(lat=52.01, lon=21.01, name="WP2", tolerance=0.5),
            Waypoint(lat=52.02, lon=21.02, name="WP3", tolerance=0.5),
        ]
    
    def test_loop_mode_initialization(self):
        """Test that loop mode can be set during initialization"""
        # Default: loop mode disabled
        manager_no_loop = SimpleWaypointManager()
        self.assertFalse(manager_no_loop.is_loop_mode())
        
        # Explicit: loop mode enabled
        manager_with_loop = SimpleWaypointManager(loop_mode=True)
        self.assertTrue(manager_with_loop.is_loop_mode())
    
    def test_set_loop_mode(self):
        """Test that loop mode can be changed at runtime"""
        manager = SimpleWaypointManager(loop_mode=False)
        self.assertFalse(manager.is_loop_mode())
        
        manager.set_loop_mode(True)
        self.assertTrue(manager.is_loop_mode())
        
        manager.set_loop_mode(False)
        self.assertFalse(manager.is_loop_mode())
    
    def test_advance_without_loop_mode(self):
        """Test that advance_to_next stops at the end without loop mode"""
        manager = SimpleWaypointManager(loop_mode=False)
        for wp in self.waypoints:
            manager.add_waypoint(wp)
        
        # Should advance twice successfully
        self.assertTrue(manager.advance_to_next())  # WP1 -> WP2
        self.assertEqual(manager.get_next_waypoint().name, "WP2")
        
        self.assertTrue(manager.advance_to_next())  # WP2 -> WP3
        self.assertEqual(manager.get_next_waypoint().name, "WP3")
        
        # Should fail to advance beyond last waypoint
        self.assertFalse(manager.advance_to_next())
        self.assertEqual(manager.get_next_waypoint().name, "WP3")  # Still at WP3
    
    def test_advance_with_loop_mode(self):
        """Test that advance_to_next cycles back to first waypoint in loop mode"""
        manager = SimpleWaypointManager(loop_mode=True)
        for wp in self.waypoints:
            manager.add_waypoint(wp)
        
        # First pass through waypoints
        self.assertEqual(manager.get_next_waypoint().name, "WP1")
        self.assertTrue(manager.advance_to_next())  # WP1 -> WP2
        self.assertEqual(manager.get_next_waypoint().name, "WP2")
        
        self.assertTrue(manager.advance_to_next())  # WP2 -> WP3
        self.assertEqual(manager.get_next_waypoint().name, "WP3")
        
        # Should cycle back to WP1
        self.assertTrue(manager.advance_to_next())  # WP3 -> WP1 (loop)
        self.assertEqual(manager.get_next_waypoint().name, "WP1")
        
        # Should continue looping
        self.assertTrue(manager.advance_to_next())  # WP1 -> WP2
        self.assertEqual(manager.get_next_waypoint().name, "WP2")
    
    def test_loop_count_tracking(self):
        """Test that loop count is tracked correctly"""
        manager = SimpleWaypointManager(loop_mode=True)
        for wp in self.waypoints:
            manager.add_waypoint(wp)
        
        # Initially, loop count should be 0
        self.assertEqual(manager.get_loop_count(), 0)
        
        # Complete first loop
        manager.advance_to_next()  # WP1 -> WP2
        manager.advance_to_next()  # WP2 -> WP3
        manager.advance_to_next()  # WP3 -> WP1 (completes loop 1)
        self.assertEqual(manager.get_loop_count(), 1)
        
        # Complete second loop
        manager.advance_to_next()  # WP1 -> WP2
        manager.advance_to_next()  # WP2 -> WP3
        manager.advance_to_next()  # WP3 -> WP1 (completes loop 2)
        self.assertEqual(manager.get_loop_count(), 2)
    
    def test_remaining_count_without_loop(self):
        """Test remaining count in non-loop mode"""
        manager = SimpleWaypointManager(loop_mode=False)
        for wp in self.waypoints:
            manager.add_waypoint(wp)
        
        # At start: all 3 waypoints remaining
        self.assertEqual(manager.get_remaining_count(), 3)
        
        # After advancing: 2 remaining
        manager.advance_to_next()
        self.assertEqual(manager.get_remaining_count(), 2)
        
        # After advancing again: 1 remaining
        manager.advance_to_next()
        self.assertEqual(manager.get_remaining_count(), 1)
        
        # Try to advance beyond last: still 1 remaining
        manager.advance_to_next()
        self.assertEqual(manager.get_remaining_count(), 1)
    
    def test_remaining_count_with_loop(self):
        """Test remaining count in loop mode (always returns total)"""
        manager = SimpleWaypointManager(loop_mode=True)
        for wp in self.waypoints:
            manager.add_waypoint(wp)
        
        # In loop mode, always returns total waypoints
        self.assertEqual(manager.get_remaining_count(), 3)
        
        manager.advance_to_next()
        self.assertEqual(manager.get_remaining_count(), 3)
        
        manager.advance_to_next()
        self.assertEqual(manager.get_remaining_count(), 3)
        
        # Even after looping back
        manager.advance_to_next()  # Loops back to WP1
        self.assertEqual(manager.get_remaining_count(), 3)
    
    def test_clear_resets_loop_count(self):
        """Test that clearing waypoints resets loop count"""
        manager = SimpleWaypointManager(loop_mode=True)
        for wp in self.waypoints:
            manager.add_waypoint(wp)
        
        # Complete a loop
        manager.advance_to_next()
        manager.advance_to_next()
        manager.advance_to_next()
        self.assertEqual(manager.get_loop_count(), 1)
        
        # Clear waypoints
        manager.clear_waypoints()
        self.assertEqual(manager.get_loop_count(), 0)
    
    def test_empty_waypoints_loop_mode(self):
        """Test loop mode behavior with no waypoints"""
        manager = SimpleWaypointManager(loop_mode=True)
        
        # Should not advance when no waypoints
        self.assertFalse(manager.advance_to_next())
        self.assertIsNone(manager.get_next_waypoint())
        self.assertEqual(manager.get_remaining_count(), 0)
    
    def test_single_waypoint_loop_mode(self):
        """Test loop mode with only one waypoint"""
        manager = SimpleWaypointManager(loop_mode=True)
        manager.add_waypoint(self.waypoints[0])
        
        # Should stay on same waypoint
        self.assertEqual(manager.get_next_waypoint().name, "WP1")
        self.assertTrue(manager.advance_to_next())
        self.assertEqual(manager.get_next_waypoint().name, "WP1")
        self.assertEqual(manager.get_loop_count(), 1)


class TestNavigatorLoopMode(unittest.TestCase):
    """Test cases for navigator loop mode integration"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Import here to avoid issues if dependencies are missing
        from navigation.navigator import Navigator
        self.waypoints = [
            Waypoint(lat=52.0, lon=21.0, name="WP1", tolerance=0.5),
            Waypoint(lat=52.01, lon=21.01, name="WP2", tolerance=0.5),
            Waypoint(lat=52.02, lon=21.02, name="WP3", tolerance=0.5),
        ]
    
    def test_navigator_loop_mode_initialization(self):
        """Test navigator can be initialized with loop mode"""
        from navigation.navigator import Navigator
        
        # Default: no loop
        nav_no_loop = Navigator()
        self.assertFalse(nav_no_loop.is_loop_mode())
        
        # With loop
        nav_with_loop = Navigator(loop_mode=True)
        self.assertTrue(nav_with_loop.is_loop_mode())
    
    def test_navigator_set_loop_mode(self):
        """Test navigator loop mode can be changed at runtime"""
        from navigation.navigator import Navigator
        
        nav = Navigator(loop_mode=False)
        self.assertFalse(nav.is_loop_mode())
        
        nav.set_loop_mode(True)
        self.assertTrue(nav.is_loop_mode())
        
        nav.set_loop_mode(False)
        self.assertFalse(nav.is_loop_mode())
    
    def test_set_waypoint_path_with_loop_override(self):
        """Test that set_waypoint_path can override loop mode"""
        from navigation.navigator import Navigator
        
        # Initialize with loop mode disabled
        nav = Navigator(loop_mode=False)
        self.assertFalse(nav.is_loop_mode())
        
        # Set path with loop mode enabled
        nav.set_waypoint_path(self.waypoints, loop_mode=True)
        self.assertTrue(nav.is_loop_mode())
        
        # Set another path with loop mode disabled
        nav.set_waypoint_path(self.waypoints, loop_mode=False)
        self.assertFalse(nav.is_loop_mode())
    
    def test_set_waypoint_path_without_override(self):
        """Test that set_waypoint_path preserves loop mode if not specified"""
        from navigation.navigator import Navigator
        
        # Initialize with loop mode enabled
        nav = Navigator(loop_mode=True)
        self.assertTrue(nav.is_loop_mode())
        
        # Set path without override
        nav.set_waypoint_path(self.waypoints)
        self.assertTrue(nav.is_loop_mode())  # Should stay enabled
    
    def test_get_loop_count(self):
        """Test that navigator exposes loop count"""
        from navigation.navigator import Navigator
        
        nav = Navigator(loop_mode=True)
        self.assertEqual(nav.get_loop_count(), 0)
        
        # Loop count is managed by waypoint_manager
        # This test just verifies the accessor works


if __name__ == '__main__':
    unittest.main()
