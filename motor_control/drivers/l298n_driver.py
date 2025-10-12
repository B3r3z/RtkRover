"""L298N motor driver implementation"""
import logging
from typing import Dict, Optional
from ..motor_interface import MotorDriverInterface, MotorDirection

logger = logging.getLogger(__name__)


class L298NDriver(MotorDriverInterface):
    """
    Driver for L298N dual H-bridge motor controller
    Supports differential drive configuration (left/right motors)
    """
    
    def __init__(self, gpio_pins: Dict[str, Dict[str, int]], use_gpio: bool = True):
        """
        Initialize L298N driver
        
        Args:
            gpio_pins: Dictionary defining pin configuration
                Example:
                {
                    'left': {'in1': 17, 'in2': 22, 'enable': 12},
                    'right': {'in1': 23, 'in2': 24, 'enable': 13}
                }
            use_gpio: If False, runs in simulation mode (for testing without hardware)
        """
        self.gpio_pins = gpio_pins
        self.use_gpio = use_gpio
        self._initialized = True
        self._pwm_frequency = 1000  # Hz
        self._pwm_objects: Dict[str, any] = {}
        
        if self.use_gpio:
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
            except (ImportError, RuntimeError) as e:
                logger.warning(f"RPi.GPIO not available: {e}. Running in simulation mode.")
                self.use_gpio = False
                self.GPIO = None
        else:
            self.GPIO = None
            logger.info("L298N driver initialized in simulation mode")
    
    def initialize(self) -> bool:
        """Initialize GPIO pins and PWM"""
        if self._initialized:
            logger.warning("Driver already initialized")
            return True
        
        if not self.use_gpio:
            logger.info("Simulation mode: GPIO initialization skipped")
            self._initialized = True
            return True
        
        try:
            # Set GPIO mode
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)
            
            # Initialize pins for each motor
            for motor_name, pins in self.gpio_pins.items():
                # Direction pins
                self.GPIO.setup(pins['in1'], self.GPIO.OUT)
                self.GPIO.setup(pins['in2'], self.GPIO.OUT)
                
                # Enable pin (PWM)
                self.GPIO.setup(pins['enable'], self.GPIO.OUT)
                
                # Create PWM object
                pwm = self.GPIO.PWM(pins['enable'], self._pwm_frequency)
                pwm.start(0)  # Start with 0% duty cycle
                self._pwm_objects[motor_name] = pwm
                
                logger.info(f"Initialized {motor_name} motor on pins: {pins}")
            
            self._initialized = True
            logger.info("L298N driver initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize L298N driver: {e}", exc_info=True)
            self._initialized = False
            return False
    
    def set_motor(self, motor_id: str, direction: MotorDirection, speed: float):
        """
        Set motor speed and direction
        
        Args:
            motor_id: 'left' or 'right'
            direction: Motor direction
            speed: Speed value 0.0 to 1.0
        """
        if not self._initialized:
            logger.warning("Driver not initialized")
            return
        
        if motor_id not in self.gpio_pins:
            logger.error(f"Unknown motor: {motor_id}")
            return
        
        # Clamp speed
        speed = max(0.0, min(1.0, speed))
        duty_cycle = speed * 100  # Convert to percentage
        
        pins = self.gpio_pins[motor_id]
        
        if self.use_gpio:
            try:
                # Set direction
                if direction == MotorDirection.FORWARD:
                    self.GPIO.output(pins['in1'], self.GPIO.HIGH)
                    self.GPIO.output(pins['in2'], self.GPIO.LOW)
                elif direction == MotorDirection.BACKWARD:
                    self.GPIO.output(pins['in1'], self.GPIO.LOW)
                    self.GPIO.output(pins['in2'], self.GPIO.HIGH)
                else:  # STOP
                    self.GPIO.output(pins['in1'], self.GPIO.LOW)
                    self.GPIO.output(pins['in2'], self.GPIO.LOW)
                    duty_cycle = 0
                
                # Set speed via PWM
                self._pwm_objects[motor_id].ChangeDutyCycle(duty_cycle)
                
                logger.debug(f"Motor {motor_id}: {direction.value}, speed: {speed:.2f}")
                
            except Exception as e:
                logger.error(f"Error setting motor {motor_id}: {e}")
        else:
            # Simulation mode
            logger.debug(f"[SIM] Motor {motor_id}: {direction.value}, speed: {speed:.2f}, duty: {duty_cycle:.1f}%")
    
    def stop_all(self):
        """Emergency stop all motors"""
        logger.info("Emergency stop - all motors stopped")
        
        for motor_id in self.gpio_pins.keys():
            self.set_motor(motor_id, MotorDirection.STOP, 0.0)
    
    def cleanup(self):
        """Clean up GPIO resources"""
        if not self._initialized:
            return
        
        logger.info("Cleaning up L298N driver")
        
        # Stop all motors first
        self.stop_all()
        
        if self.use_gpio and self.GPIO:
            try:
                # Stop PWM
                for pwm in self._pwm_objects.values():
                    pwm.stop()
                
                # Clean up GPIO
                self.GPIO.cleanup()
                logger.info("GPIO cleanup complete")
                
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
        
        self._initialized = False
        self._pwm_objects.clear()
    
    def is_initialized(self) -> bool:
        """Check if driver is initialized"""
        return self._initialized
    
    def set_pwm_frequency(self, frequency: int):
        """
        Change PWM frequency (must be called before initialize())
        
        Args:
            frequency: PWM frequency in Hz (typically 100-20000)
        """
        if self._initialized:
            logger.warning("Cannot change PWM frequency after initialization")
            return
        
        self._pwm_frequency = frequency
        logger.info(f"PWM frequency set to {frequency} Hz")
