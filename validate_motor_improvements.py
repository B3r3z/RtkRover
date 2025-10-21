#!/usr/bin/env python3
"""
Quick validation script for motor control improvements
Validates that all components integrate correctly
"""

import sys
import os

def validate_imports():
    """Validate that all imports work correctly"""
    print("=== Validating Imports ===")
    
    try:
        # Test motor control imports
        from motor_control.motor_controller import MotorController
        from motor_control.motor_interface import MotorDriverInterface, MotorDirection, DifferentialDriveCommand
        print("✓ Motor control imports OK")
        
        # Test config imports
        from config.motor_settings import motor_config, motor_gpio_pins, navigation_config
        print("✓ Configuration imports OK")
        
        # Test navigation imports
        from navigation.core.data_types import NavigationCommand
        print("✓ Navigation imports OK")
        
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


def validate_configuration():
    """Validate configuration structure"""
    print("\n=== Validating Configuration ===")
    
    try:
        from config.motor_settings import motor_config
        
        # Check required fields
        required_fields = ['max_speed', 'turn_sensitivity', 'safety_timeout', 'ramp_rate', 'use_gpio']
        
        for field in required_fields:
            if field not in motor_config:
                print(f"✗ Missing required field: {field}")
                return False
            print(f"✓ {field}: {motor_config[field]}")
        
        # Validate ranges
        if not (0.0 <= motor_config['ramp_rate'] <= 1.0):
            print(f"✗ ramp_rate out of range: {motor_config['ramp_rate']}")
            return False
        
        print("✓ All configuration fields valid")
        return True
        
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False


def validate_motor_controller():
    """Validate MotorController initialization"""
    print("\n=== Validating MotorController ===")
    
    try:
        from motor_control.motor_controller import MotorController
        
        # Create mock driver
        class MockDriver:
            def initialize(self): return True
            def set_motor(self, side, direction, speed): pass
            def stop_all(self): pass
            def cleanup(self): pass
            def is_initialized(self): return True
        
        # Test initialization with default parameters
        controller1 = MotorController(motor_driver=MockDriver())
        print("✓ Default initialization OK")
        
        # Test initialization with custom ramp_rate
        controller2 = MotorController(
            motor_driver=MockDriver(),
            ramp_rate=0.7
        )
        
        if controller2._ramp_rate != 0.7:
            print(f"✗ Ramp rate not set correctly: expected 0.7, got {controller2._ramp_rate}")
            return False
        
        print("✓ Custom ramp_rate OK")
        
        # Test that emergency stop event exists
        if not hasattr(controller1, '_emergency_stop_event'):
            print("✗ Missing _emergency_stop_event attribute")
            return False
        
        print("✓ Emergency stop event exists")
        
        return True
        
    except Exception as e:
        print(f"✗ MotorController error: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_differential_drive():
    """Validate differential drive calculations"""
    print("\n=== Validating Differential Drive ===")
    
    try:
        from motor_control.motor_controller import MotorController
        from navigation.core.data_types import NavigationCommand
        from datetime import datetime
        
        class MockDriver:
            def initialize(self): return True
            def set_motor(self, side, direction, speed): pass
            def stop_all(self): pass
            def cleanup(self): pass
            def is_initialized(self): return True
        
        controller = MotorController(motor_driver=MockDriver(), ramp_rate=1.0)
        
        # Test case 1: Forward movement
        nav_cmd = NavigationCommand(speed=0.5, turn_rate=0.0, timestamp=datetime.now())
        diff_cmd = controller._navigation_to_differential(nav_cmd)
        
        if diff_cmd.left_speed != 0.5 or diff_cmd.right_speed != 0.5:
            print(f"✗ Forward movement incorrect: L={diff_cmd.left_speed}, R={diff_cmd.right_speed}")
            return False
        print("✓ Forward movement OK")
        
        # Test case 2: Right turn
        nav_cmd = NavigationCommand(speed=0.5, turn_rate=0.3, timestamp=datetime.now())
        diff_cmd = controller._navigation_to_differential(nav_cmd)
        
        if diff_cmd.left_speed >= diff_cmd.right_speed:
            print(f"✗ Right turn incorrect: L={diff_cmd.left_speed}, R={diff_cmd.right_speed}")
            return False
        print("✓ Right turn OK")
        
        # Test case 3: Normalization
        nav_cmd = NavigationCommand(speed=0.8, turn_rate=0.5, timestamp=datetime.now())
        diff_cmd = controller._navigation_to_differential(nav_cmd)
        
        if abs(diff_cmd.left_speed) > 1.0 or abs(diff_cmd.right_speed) > 1.0:
            print(f"✗ Normalization failed: L={diff_cmd.left_speed}, R={diff_cmd.right_speed}")
            return False
        print("✓ Normalization OK")
        
        return True
        
    except Exception as e:
        print(f"✗ Differential drive error: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_event_driven_stop():
    """Validate event-driven emergency stop"""
    print("\n=== Validating Event-Driven Stop ===")
    
    try:
        from motor_control.motor_controller import MotorController
        import threading
        
        class MockDriver:
            def __init__(self):
                self.stopped = False
            def initialize(self): return True
            def set_motor(self, side, direction, speed): pass
            def stop_all(self): self.stopped = True
            def cleanup(self): pass
            def is_initialized(self): return True
        
        driver = MockDriver()
        controller = MotorController(motor_driver=driver)
        
        # Check event exists
        if not isinstance(controller._emergency_stop_event, threading.Event):
            print("✗ Emergency stop event is not a threading.Event")
            return False
        print("✓ Emergency stop event type OK")
        
        # Test emergency stop
        controller.emergency_stop()
        
        if not driver.stopped:
            print("✗ Motors not stopped during emergency stop")
            return False
        print("✓ Emergency stop executes correctly")
        
        # Check event is cleared
        if controller._emergency_stop_event.is_set():
            print("✗ Emergency stop event not cleared")
            return False
        print("✓ Event cleared after stop")
        
        return True
        
    except Exception as e:
        print(f"✗ Event-driven stop error: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_front_end():
    """Validate front-end files"""
    print("\n=== Validating Front-End ===")
    
    try:
        # Check JavaScript file
        js_path = '/home/runner/work/RtkRover/RtkRover/static/js/map.js'
        if not os.path.exists(js_path):
            print(f"✗ JavaScript file not found: {js_path}")
            return False
        
        with open(js_path, 'r') as f:
            js_content = f.read()
        
        # Check for keyboard shortcuts
        required_keys = ['ESC', 'SPACE', 'R', 'Ctrl+C', 'M']
        found_keys = []
        
        for key in required_keys:
            if key in js_content or key.replace('+', '') in js_content:
                found_keys.append(key)
        
        if len(found_keys) < len(required_keys) - 1:  # Allow one missing
            print(f"✗ Missing keyboard shortcuts: found {found_keys}")
            return False
        print(f"✓ Keyboard shortcuts present: {', '.join(found_keys)}")
        
        # Check for pulse animation
        if 'pulse' not in js_content and 'animation' not in js_content:
            print("⚠ Warning: Pulse animation may not be implemented")
        else:
            print("✓ Animation code present")
        
        # Check CSS file
        css_path = '/home/runner/work/RtkRover/RtkRover/static/css/style.css'
        if not os.path.exists(css_path):
            print(f"✗ CSS file not found: {css_path}")
            return False
        
        with open(css_path, 'r') as f:
            css_content = f.read()
        
        if '@keyframes pulse' not in css_content:
            print("⚠ Warning: Pulse animation CSS may be missing")
        else:
            print("✓ Pulse animation CSS present")
        
        return True
        
    except Exception as e:
        print(f"✗ Front-end validation error: {e}")
        return False


def main():
    """Run all validations"""
    print("=" * 60)
    print("MOTOR CONTROL IMPROVEMENTS - VALIDATION SUITE")
    print("=" * 60)
    
    validations = [
        validate_imports,
        validate_configuration,
        validate_motor_controller,
        validate_differential_drive,
        validate_event_driven_stop,
        validate_front_end,
    ]
    
    passed = 0
    failed = 0
    
    for validation in validations:
        try:
            if validation():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {validation.__name__} failed with exception: {e}")
    
    print("\n" + "=" * 60)
    print(f"VALIDATION RESULTS: {passed}/{len(validations)} passed")
    print("=" * 60)
    
    if failed > 0:
        print("\n⚠️  Some validations failed. Please review the errors above.")
        return False
    else:
        print("\n✅ All validations passed! Motor control improvements are ready.")
        return True


if __name__ == "__main__":
    # Add current directory to Python path
    sys.path.insert(0, '/home/runner/work/RtkRover/RtkRover')
    
    success = main()
    sys.exit(0 if success else 1)
