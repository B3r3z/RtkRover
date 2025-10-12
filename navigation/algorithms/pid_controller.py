"""PID Controller for smooth navigation"""
import time
from typing import Optional


class PIDController:
    """
    PID (Proportional-Integral-Derivative) controller
    Used for smooth heading and speed control
    """
    
    def __init__(self, kp: float, ki: float, kd: float, output_limits: tuple = (-1.0, 1.0)):
        """
        Initialize PID controller
        
        Args:
            kp: Proportional gain
            ki: Integral gain
            kd: Derivative gain
            output_limits: (min, max) output limits
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limits = output_limits
        
        self._integral = 0.0
        self._last_error = 0.0
        self._last_time = None
    
    def update(self, error: float, dt: Optional[float] = None) -> float:
        """
        Update PID controller with new error
        
        Args:
            error: Current error value
            dt: Time delta since last update (seconds). If None, calculated automatically
            
        Returns:
            Control output value
        """
        current_time = time.time()
        
        # Calculate dt if not provided
        if dt is None:
            if self._last_time is not None:
                dt = current_time - self._last_time
            else:
                dt = 0.0
        
        self._last_time = current_time
        
        if dt <= 0:
            return 0.0
        
        # Proportional term
        p_term = self.kp * error
        
        # Integral term
        self._integral += error * dt
        i_term = self.ki * self._integral
        
        # Derivative term
        derivative = (error - self._last_error) / dt
        d_term = self.kd * derivative
        
        # Calculate output
        output = p_term + i_term + d_term
        
        # Apply limits
        output = max(self.output_limits[0], min(self.output_limits[1], output))
        
        # Store for next iteration
        self._last_error = error
        
        return output
    
    def reset(self):
        """Reset controller state"""
        self._integral = 0.0
        self._last_error = 0.0
        self._last_time = None
    
    def set_gains(self, kp: float, ki: float, kd: float):
        """Update PID gains"""
        self.kp = kp
        self.ki = ki
        self.kd = kd
