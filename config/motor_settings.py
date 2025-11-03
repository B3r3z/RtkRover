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
    'max_speed': float(os.getenv('MOTOR_MAX_SPEED', '1.0')),  # 0.0 to 1.0
    'turn_sensitivity': float(os.getenv('MOTOR_TURN_SENSITIVITY', '1.0')),
    'safety_timeout': float(os.getenv('MOTOR_SAFETY_TIMEOUT', '10.5')),  
    'ramp_rate': float(os.getenv('MOTOR_RAMP_RATE', '0.5')),  # Acceleration rate (0.0 to 1.0 per cycle)
    'use_gpio': os.getenv('MOTOR_USE_GPIO', 'True').lower() == 'true'  # Set to False for simulation
}

# Navigation parameters
navigation_config = {
    'max_speed': float(os.getenv('NAV_MAX_SPEED', '1.0')),  # 0.0 to 1.0
    'turn_aggressiveness': float(os.getenv('NAV_TURN_AGGR', '0.4')),  # 0.0 to 1.0
    'waypoint_tolerance': float(os.getenv('NAV_WP_TOLERANCE', '0.01')),  
    'update_rate': float(os.getenv('NAV_UPDATE_RATE', '1.0')),  # seconds
    'calibration_speed': float(os.getenv('NAV_CALIB_SPEED', '0.8')),  # 🔧 INCREASED: Calibration speed (80% to ensure GPS detects movement >0.5 m/s after motor scaling)
    'calibration_duration': float(os.getenv('NAV_CALIB_DURATION', '5.0')),  # 🔧 NEW: Max calibration time in seconds
    'min_speed_for_heading': float(os.getenv('GPS_MIN_SPEED_HEADING', '0.5')),  # 🔧 NEW: Min speed (m/s) for reliable VTG heading
    
    
    'align_tolerance': float(os.getenv('NAV_ALIGN_TOLERANCE', '15.0')),  # degrees - how aligned to be before driving
    'realign_threshold': float(os.getenv('NAV_REALIGN_THRESHOLD', '30.0')),  # degrees - when to re-align during driving
    'align_speed': float(os.getenv('NAV_ALIGN_SPEED', '0.6')),  # 0.0-1.0 - rotation speed during alignment
    'align_timeout': float(os.getenv('NAV_ALIGN_TIMEOUT', '10.0')),  # seconds - max time to spend aligning
    'drive_correction_gain': float(os.getenv('NAV_DRIVE_CORRECTION', '0.02')),  # proportional correction during straight driving
}

# PID tuning for heading control
# Tune these values based on your robot's characteristics
# 🔧 OPTIMIZED: Reduced values to prevent one motor getting too weak during turns
pid_config = {
    'heading': {
        'kp': float(os.getenv('PID_HEADING_KP', '0.012')),  # 🔧 REDUCED: from 0.02 to 0.012 (60%)
        'ki': float(os.getenv('PID_HEADING_KI', '0.0005')),  # 🔧 REDUCED: from 0.001 to 0.0005 (50%)
        'kd': float(os.getenv('PID_HEADING_KD', '0.008'))  # 🔧 REDUCED: from 0.01 to 0.008 (80%)
    }
}
