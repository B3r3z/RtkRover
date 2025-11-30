import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor_control.motor_controller import MotorController
from motor_control.motor_interface import MotorDriverInterface, MotorDirection
from navigation.navigator import Navigator
from navigation.types import Waypoint, NavigationCommand

class TestMotorController(unittest.TestCase):
    def setUp(self):
        self.mock_driver = MagicMock(spec=MotorDriverInterface)
        self.mock_driver.initialize.return_value = True
        self.controller = MotorController(self.mock_driver, max_speed=1.0, wheel_base=0.5)
        self.controller.start()

    def test_forward_kinematics(self):
        # v=1.0, w=0.0 -> L=1.0, R=1.0
        cmd = NavigationCommand(speed=1.0, turn_rate=0.0, timestamp=datetime.now())
        self.controller.execute_navigation_command(cmd)
        
        # Verify driver calls
        # We expect set_motor called for left and right
        # Since implementation might call set_motor multiple times or in specific order, 
        # we just check if it was called with expected values at least once.
        # Actually, let's check the last call args for 'left' and 'right'
        
        # Filter calls
        calls = self.mock_driver.set_motor.call_args_list
        left_calls = [c for c in calls if c[0][0] == 'left']
        right_calls = [c for c in calls if c[0][0] == 'right']
        
        self.assertTrue(len(left_calls) > 0)
        self.assertTrue(len(right_calls) > 0)
        
        # Check values (approximate)
        # Left: 1.0
        self.assertEqual(left_calls[-1][0][1], MotorDirection.FORWARD)
        self.assertAlmostEqual(left_calls[-1][0][2], 1.0)
        
        # Right: 1.0
        self.assertEqual(right_calls[-1][0][1], MotorDirection.FORWARD)
        self.assertAlmostEqual(right_calls[-1][0][2], 1.0)

    def test_turn_kinematics(self):
        # v=0.5, w=0.5 -> L=0.0, R=1.0 (approx, depending on wheel_base logic)
        # Logic: L = v - w, R = v + w
        # L = 0.5 - 0.5 = 0.0
        # R = 0.5 + 0.5 = 1.0
        cmd = NavigationCommand(speed=0.5, turn_rate=0.5, timestamp=datetime.now())
        self.controller.execute_navigation_command(cmd)
        
        calls = self.mock_driver.set_motor.call_args_list
        left_calls = [c for c in calls if c[0][0] == 'left']
        right_calls = [c for c in calls if c[0][0] == 'right']
        
        # Left: 0.0
        self.assertAlmostEqual(left_calls[-1][0][2], 0.0)
        
        # Right: 1.0
        self.assertEqual(right_calls[-1][0][1], MotorDirection.FORWARD)
        self.assertAlmostEqual(right_calls[-1][0][2], 1.0)

class TestNavigator(unittest.TestCase):
    def setUp(self):
        self.navigator = Navigator()
        self.navigator.start()
        
    def test_drive_to_orient_unknown_heading(self):
        # Setup: Target set, but no heading known
        wp = Waypoint(lat=52.0001, lon=21.0001) # Some distance away
        self.navigator.set_target(wp)
        self.navigator.update_position(lat=52.0000, lon=21.0000, heading=None)
        
        cmd = self.navigator.get_navigation_command()
        
        # Expect: Drive forward to acquire heading
        self.assertIsNotNone(cmd)
        self.assertGreater(cmd.speed, 0.0)
        self.assertEqual(cmd.turn_rate, 0.0)
        
    def test_drive_to_orient_known_heading(self):
        # Setup: Target set, heading known
        wp = Waypoint(lat=52.0001, lon=21.0000) # Directly North
        self.navigator.set_target(wp)
        
        # Current: Facing East (90)
        self.navigator.update_position(lat=52.0000, lon=21.0000, heading=90.0)
        
        cmd = self.navigator.get_navigation_command()
        
        # Expect: Turn Left (negative turn_rate)
        self.assertIsNotNone(cmd)
        self.assertLess(cmd.turn_rate, 0.0) # Should turn left to face North (0)
        self.assertGreater(cmd.speed, 0.0) # Should still move forward

if __name__ == '__main__':
    unittest.main()
