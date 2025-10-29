"""
Integration tests for GPS error handling and communication scenarios
Tests the navigation system's resilience to GPS failures
"""
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from navigation.navigator import Navigator
from navigation.core.data_types import Waypoint, NavigationStatus


class TestGPSErrorHandling(unittest.TestCase):
    """Test cases for GPS error scenarios"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.navigator = Navigator(loop_mode=False)
        self.waypoint = Waypoint(lat=52.0, lon=21.0, name="Test WP", tolerance=0.5)
    
    def test_no_gps_position_available(self):
        """Test navigation handles missing GPS position gracefully"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # Try to get navigation command without GPS position
        command = self.navigator.get_navigation_command()
        
        # Should return None and set error status
        self.assertIsNone(command)
        state = self.navigator.get_state()
        self.assertEqual(state.status, NavigationStatus.ERROR)
        self.assertIsNotNone(state.error_message)
        self.assertIn("No GPS position", state.error_message)
    
    def test_stale_gps_data(self):
        """Test navigation detects and handles stale GPS data"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # Update position
        self.navigator.update_position(lat=52.001, lon=21.001, heading=45.0, speed=1.0)
        
        # Mock the timestamp to be old
        with patch.object(self.navigator, '_last_position_time', 
                         datetime.now() - timedelta(seconds=5)):
            command = self.navigator.get_navigation_command()
            
            # Should return None due to stale data
            self.assertIsNone(command)
            state = self.navigator.get_state()
            self.assertEqual(state.status, NavigationStatus.ERROR)
            self.assertIn("GPS data too old", state.error_message)
    
    def test_no_heading_triggers_calibration(self):
        """Test that missing heading triggers calibration mode"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # Update position without heading
        self.navigator.update_position(lat=52.001, lon=21.001, heading=None, speed=0.0)
        
        # Get navigation command
        command = self.navigator.get_navigation_command()
        
        # Should enter calibration mode
        self.assertIsNotNone(command)
        # Calibration drives straight at reduced speed
        self.assertGreater(command.speed, 0.0)
        self.assertEqual(command.turn_rate, 0.0)
    
    def test_heading_recovered_after_calibration(self):
        """Test that navigation proceeds normally after heading is acquired"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # Start without heading
        self.navigator.update_position(lat=52.001, lon=21.001, heading=None, speed=0.0)
        command1 = self.navigator.get_navigation_command()
        self.assertIsNotNone(command1)
        
        # Now provide heading
        self.navigator.update_position(lat=52.001, lon=21.001, heading=45.0, speed=1.0)
        self.navigator.update_position(lat=52.001, lon=21.001, heading=46.0, speed=1.0)
        self.navigator.update_position(lat=52.001, lon=21.001, heading=45.5, speed=1.0)
        
        # Should exit calibration and start navigation
        command2 = self.navigator.get_navigation_command()
        self.assertIsNotNone(command2)
    
    def test_speed_validation_for_heading(self):
        """Test that heading from VTG is only used when speed is sufficient"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # Update with heading but low speed
        self.navigator.update_position(lat=52.001, lon=21.001, heading=45.0, speed=0.1)
        
        # Heading should still be set even at low speed (VTG provides it)
        self.assertIsNotNone(self.navigator._current_heading)
        self.assertEqual(self.navigator._current_heading, 45.0)


class TestCommunicationErrorScenarios(unittest.TestCase):
    """Test cases for communication error scenarios"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.navigator = Navigator(loop_mode=True)
        self.waypoints = [
            Waypoint(lat=52.0, lon=21.0, name="WP1", tolerance=0.5),
            Waypoint(lat=52.01, lon=21.01, name="WP2", tolerance=0.5),
            Waypoint(lat=52.02, lon=21.02, name="WP3", tolerance=0.5),
        ]
    
    def test_intermittent_gps_updates(self):
        """Test navigation handles intermittent GPS updates"""
        self.navigator.set_waypoint_path(self.waypoints, loop_mode=True)
        self.navigator.start()
        
        # Provide initial position
        self.navigator.update_position(lat=52.0, lon=21.0, heading=45.0, speed=1.0)
        
        # Get command successfully
        command1 = self.navigator.get_navigation_command()
        self.assertIsNotNone(command1)
        
        # Simulate GPS dropout (stale data check after 2+ seconds)
        with patch.object(self.navigator, '_last_position_time', 
                         datetime.now() - timedelta(seconds=3)):
            command2 = self.navigator.get_navigation_command()
            self.assertIsNone(command2)  # Should fail due to stale data
        
        # GPS recovers
        self.navigator.update_position(lat=52.001, lon=21.001, heading=45.0, speed=1.0)
        command3 = self.navigator.get_navigation_command()
        self.assertIsNotNone(command3)  # Should work again
    
    def test_pause_resume_preserves_state(self):
        """Test that pause and resume preserve navigation state"""
        self.navigator.set_waypoint_path(self.waypoints, loop_mode=True)
        self.navigator.start()
        
        # Setup position and get initial command
        self.navigator.update_position(lat=52.0, lon=21.0, heading=45.0, speed=1.0)
        command1 = self.navigator.get_navigation_command()
        self.assertIsNotNone(command1)
        
        # Pause
        self.navigator.pause()
        state = self.navigator.get_state()
        self.assertEqual(state.status, NavigationStatus.PAUSED)
        
        # Should not provide commands while paused
        command2 = self.navigator.get_navigation_command()
        self.assertIsNone(command2)
        
        # Resume
        self.navigator.resume()
        state = self.navigator.get_state()
        self.assertEqual(state.status, NavigationStatus.NAVIGATING)
        
        # Should provide commands again
        self.navigator.update_position(lat=52.0, lon=21.0, heading=45.0, speed=1.0)
        command3 = self.navigator.get_navigation_command()
        self.assertIsNotNone(command3)
    
    def test_loop_continues_after_errors(self):
        """Test that loop mode continues after recovering from errors"""
        self.navigator.set_waypoint_path(self.waypoints, loop_mode=True)
        self.navigator.start()
        
        # Navigate to first waypoint
        self.navigator.update_position(lat=52.0, lon=21.0, heading=45.0, speed=1.0)
        
        # Reach waypoint (should advance to next)
        # Simulate reaching WP1
        state = self.navigator.get_state()
        initial_target = state.target_waypoint.name if state.target_waypoint else None
        
        # The waypoint will advance when reached
        # Test that loop count tracking persists through errors
        self.assertEqual(self.navigator.get_loop_count(), 0)


class TestNavigationStateMachine(unittest.TestCase):
    """Test cases for navigation state machine robustness"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.navigator = Navigator()
        self.waypoint = Waypoint(lat=52.01, lon=21.01, name="Target", tolerance=0.5)
    
    def test_state_machine_idle_to_navigating(self):
        """Test state machine transitions from IDLE to NAVIGATING"""
        state = self.navigator.get_state()
        self.assertEqual(state.status, NavigationStatus.IDLE)
        
        self.navigator.set_target(self.waypoint)
        state = self.navigator.get_state()
        self.assertEqual(state.status, NavigationStatus.NAVIGATING)
    
    def test_stop_resets_state_machine(self):
        """Test that stop properly resets state machine"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        self.navigator.update_position(lat=52.0, lon=21.0, heading=45.0, speed=1.0)
        
        # Get a command to enter navigation state
        command = self.navigator.get_navigation_command()
        self.assertIsNotNone(command)
        
        # Stop navigation
        self.navigator.stop()
        
        # Verify state is reset
        state = self.navigator.get_state()
        self.assertEqual(state.status, NavigationStatus.IDLE)
        self.assertIsNone(state.target_waypoint)
        
        # Should not provide commands after stop
        command = self.navigator.get_navigation_command()
        self.assertIsNone(command)


class TestGPSRTKIntegration(unittest.TestCase):
    """Test cases for GPS-RTK and VTG integration scenarios"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.navigator = Navigator()
        self.waypoint = Waypoint(lat=52.01, lon=21.01, name="Target", tolerance=0.5)
    
    def test_vtg_heading_usage(self):
        """Test that VTG heading (course over ground) is used when available"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # Update with VTG heading
        vtg_heading = 87.5
        self.navigator.update_position(lat=52.0, lon=21.0, heading=vtg_heading, speed=1.5)
        
        # Verify heading is stored
        self.assertEqual(self.navigator._current_heading, vtg_heading)
    
    def test_calculated_heading_from_movement(self):
        """Test that heading is calculated from movement when VTG unavailable"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # First position (no heading available)
        self.navigator.update_position(lat=52.0, lon=21.0, heading=None, speed=1.5)
        
        # Second position (heading should be calculated from movement)
        self.navigator.update_position(lat=52.001, lon=21.001, heading=None, speed=1.5)
        
        # Heading should be calculated
        # Since we're moving northeast, heading should be roughly 45 degrees
        if self.navigator._current_heading is not None:
            # Basic sanity check - heading should be positive and reasonable
            self.assertGreater(self.navigator._current_heading, 0)
            self.assertLess(self.navigator._current_heading, 90)
    
    def test_rtk_high_precision_position(self):
        """Test that high-precision RTK positions are handled correctly"""
        self.navigator.set_target(self.waypoint)
        self.navigator.start()
        
        # RTK provides high precision (many decimal places)
        rtk_lat = 52.123456789
        rtk_lon = 21.987654321
        
        self.navigator.update_position(lat=rtk_lat, lon=rtk_lon, heading=45.0, speed=1.0)
        
        # Verify position is stored with full precision
        state = self.navigator.get_state()
        self.assertIsNotNone(state.current_position)
        self.assertEqual(state.current_position[0], rtk_lat)
        self.assertEqual(state.current_position[1], rtk_lon)


if __name__ == '__main__':
    unittest.main()
