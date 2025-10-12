"""
Global Rover Manager Singleton
Centralny punkt zarządzania robotem - integracja z Flask
"""
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class GlobalRoverManager:
    """
    Singleton manager for entire rover system
    Thread-safe initialization and access
    
    Usage:
        from rover_manager_singleton import global_rover_manager
        
        # Initialize with RTK manager
        rover = global_rover_manager.initialize(rtk_manager)
        
        # Get instance
        rover = global_rover_manager.get_rover_manager()
        
        # Use rover
        if rover:
            rover.go_to_waypoint(52.2297, 21.0122, "Target")
    """
    
    _instance: Optional['GlobalRoverManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.rover_manager = None
        self._initialization_lock = threading.Lock()
        self._initialization_attempted = False
        self._initialized = True
        logger.info("Global Rover Manager singleton created")
    
    def initialize(self, rtk_manager):
        """
        Initialize rover manager with RTK system
        
        Args:
            rtk_manager: Initialized RTK Manager instance
            
        Returns:
            RoverManager instance or None if initialization failed
        """
        with self._initialization_lock:
            if self.rover_manager is not None:
                logger.warning("Rover Manager already initialized")
                return self.rover_manager
            
            if self._initialization_attempted:
                logger.warning("Rover Manager initialization already attempted and failed")
                return None
            
            self._initialization_attempted = True
            
            try:
                # Lazy import to avoid circular dependencies
                from rover_manager import RoverManager
                
                logger.info("Initializing Rover Manager...")
                self.rover_manager = RoverManager(rtk_manager=rtk_manager)
                
                # Start rover systems
                if self.rover_manager.start():
                    logger.info("✅ Rover Manager initialized and started successfully")
                    return self.rover_manager
                else:
                    logger.error("❌ Failed to start Rover Manager")
                    self.rover_manager = None
                    return None
                
            except ImportError as e:
                logger.error(f"Failed to import RoverManager: {e}")
                logger.info("This is expected if motor_control or navigation modules are not yet available")
                self.rover_manager = None
                return None
                
            except Exception as e:
                logger.error(f"Failed to initialize Rover Manager: {e}", exc_info=True)
                self.rover_manager = None
                return None
    
    def get_rover_manager(self):
        """
        Get rover manager instance
        
        Returns:
            RoverManager instance or None if not initialized
        """
        return self.rover_manager
    
    def is_initialized(self) -> bool:
        """Check if rover manager is initialized"""
        return self.rover_manager is not None
    
    def shutdown(self):
        """Shutdown rover manager gracefully"""
        with self._initialization_lock:
            if self.rover_manager:
                logger.info("Shutting down Rover Manager...")
                try:
                    self.rover_manager.stop()
                    logger.info("Rover Manager stopped successfully")
                except Exception as e:
                    logger.error(f"Error during Rover Manager shutdown: {e}", exc_info=True)
                finally:
                    self.rover_manager = None
                    self._initialization_attempted = False
    
    def get_status(self) -> dict:
        """
        Get rover system status
        
        Returns:
            Dictionary with status information
        """
        if not self.rover_manager:
            return {
                "initialized": False,
                "running": False,
                "message": "Rover Manager not initialized"
            }
        
        try:
            status = self.rover_manager.get_rover_status()
            status['initialized'] = True
            return status
        except Exception as e:
            logger.error(f"Error getting rover status: {e}")
            return {
                "initialized": True,
                "running": False,
                "error": str(e)
            }


# Global singleton instance
# Import this in your Flask app:
# from rover_manager_singleton import global_rover_manager
global_rover_manager = GlobalRoverManager()
