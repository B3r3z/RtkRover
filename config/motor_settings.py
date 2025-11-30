"""Motor control configuration"""
import os

# L298N GPIO pin configuration
# Adjust these based on your wiring
motor_gpio_pins = {
    'left': {
        'in1': int(os.getenv('MOTOR_LEFT_IN1', '17')),
        'in2': int(os.getenv('MOTOR_LEFT_IN2', '22')),
        'enable': int(os.getenv('MOTOR_LEFT_EN', '12'))
    },
    'right': {
        'in1': int(os.getenv('MOTOR_RIGHT_IN1', '23')),
        'in2': int(os.getenv('MOTOR_RIGHT_IN2', '24')),
        'enable': int(os.getenv('MOTOR_RIGHT_EN', '13'))
    }
}

# Motor control parameters
motor_config = {
    'frequency': 1000,  # Hz
    'use_gpio': True,   # Use GPIO pins for motor control
    'min_duty_cycle': 20,  # Minimum duty cycle to move motors (%)
    'max_duty_cycle': 100,
    'ramp_step': 5,  # Percentage change per step for ramping
    'ramp_delay': 0.05,  # Seconds between ramp steps
    'wheel_base': 0.5,  # Distance between wheels in meters
    'max_speed': 1.0,   # Maximum motor speed multiplier
    'turn_sensitivity': 1.0, # Kept for backward compatibility if needed
    'safety_timeout': 2.0 # Kept for backward compatibility if needed
}

# Navigation parameters
navigation_config = {
    'max_speed': 0.8,  # 0.0 to 1.0
    'turn_aggressiveness': 0.6,
    'waypoint_tolerance': 1.0,  # meters
    'align_tolerance': 10.0,  # degrees
    'realign_threshold': 20.0,  # degrees
    'align_speed': 0.5,
    'align_timeout': 15.0,  # seconds
    'drive_correction_gain': 0.05,
    'calibration_speed': 0.6
}
