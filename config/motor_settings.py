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
    'max_speed': float(os.getenv('MOTOR_MAX_SPEED', '0.8')),  # 0.0 to 1.0
    'turn_sensitivity': float(os.getenv('MOTOR_TURN_SENSITIVITY', '1.0')),
    'safety_timeout': float(os.getenv('MOTOR_SAFETY_TIMEOUT', '0.5')),  # seconds
    'ramp_rate': float(os.getenv('MOTOR_RAMP_RATE', '0.5')),  # Acceleration rate (0.0 to 1.0 per cycle)
    'use_gpio': os.getenv('MOTOR_USE_GPIO', 'True').lower() == 'true'  # Set to False for simulation
}

# Navigation parameters
navigation_config = {
    'max_speed': float(os.getenv('NAV_MAX_SPEED', '1.0')),  # 0.0 to 1.0
    'turn_aggressiveness': float(os.getenv('NAV_TURN_AGGR', '0.5')),  # 0.0 to 1.0
    'waypoint_tolerance': float(os.getenv('NAV_WP_TOLERANCE', '2.0')),  # meters
    'update_rate': float(os.getenv('NAV_UPDATE_RATE', '0.5')),  # seconds
}

# PID tuning for heading control
# Tune these values based on your robot's characteristics
pid_config = {
    'heading': {
        'kp': float(os.getenv('PID_HEADING_KP', '0.02')),
        'ki': float(os.getenv('PID_HEADING_KI', '0.001')),
        'kd': float(os.getenv('PID_HEADING_KD', '0.01'))
    }
}
