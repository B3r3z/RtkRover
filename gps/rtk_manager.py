import logging
import time
from typing import Optional, Dict, Any, Callable
from .factory import RTKFactory
from .core.interfaces import RTKSystemInterface, PositionObserver, Position

logger = logging.getLogger(__name__)

class PositionCallbackAdapter(PositionObserver):
    def __init__(self, callback: Callable):
        self.callback = callback
    
    def on_position_update(self, position: Position):
        position_dict = {
            "lat": position.lat,
            "lon": position.lon,
            "altitude": position.altitude,
            "satellites": position.satellites,
            "hdop": position.hdop,
            "rtk_status": position.rtk_status.value,
            "timestamp": position.timestamp
        }
        self.callback(position_dict)

class RTKManager:
    def __init__(self):
        self.system: Optional[RTKSystemInterface] = None
        self.position_callback: Optional[Callable] = None
        self.running = False
        
        try:
            from config.settings import rtk_config, uart_config
            self.ntrip_config = rtk_config
            self.uart_config = uart_config
        except Exception as e:
            logger.error(f"Configuration error: {e}")
            raise
    
    def start(self) -> bool:
        if self.running:
            return True
            
        try:
            self.system = RTKFactory.create_system(self.uart_config, self.ntrip_config)
            
            if self.position_callback:
                adapter = PositionCallbackAdapter(self.position_callback)
                self.system.add_position_observer(adapter)
            
            if self.system.start():
                self.running = True
                logger.info("RTK Manager started successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to start RTK system: {e}")
            
        return False
    
    def stop(self):
        if self.system:
            self.system.stop()
            self.system = None
        self.running = False
        logger.info("RTK Manager stopped")
    
    def set_position_callback(self, callback: Callable):
        self.position_callback = callback
    
    def get_status(self) -> Dict[str, Any]:
        if not self.system:
            return {
                "rtk_status": "Disconnected", 
                "running": False,
                "gps_connected": False,
                "ntrip_connected": False
            }
        
        stats = self.system.get_status()
        position = self.system.get_current_position()
        
        # Check connection status
        gps_connected = self.system.gps.is_connected() if hasattr(self.system, 'gps') else False
        ntrip_connected = (self.system.ntrip_service.is_connected() 
                          if hasattr(self.system, 'ntrip_service') and self.system.ntrip_service 
                          else False)
        
        return {
            "rtk_status": position.rtk_status.value if position else "No Fix",
            "running": self.running,
            "gps_connected": gps_connected,
            "ntrip_connected": ntrip_connected,
            "rtcm_messages": stats.rtcm_messages,
            "uptime": stats.connection_uptime,
            "current_position": {
                "lat": position.lat if position else 0,
                "lon": position.lon if position else 0,
                "altitude": position.altitude if position else 0,
                "satellites": position.satellites if position else 0,
                "hdop": position.hdop if position else 0
            } if position else None
        }
    
    def get_current_position(self) -> Optional[Dict[str, Any]]:
        if not self.system:
            return None
            
        position = self.system.get_current_position()
        if not position:
            return None
            
        return {
            "lat": position.lat,
            "lon": position.lon,
            "altitude": position.altitude,
            "rtk_status": position.rtk_status.value,
            "satellites": position.satellites,
            "hdop": position.hdop,
            "timestamp": position.timestamp
        }
    
    @property
    def rtk_status(self) -> str:
        position = self.system.get_current_position() if self.system else None
        return position.rtk_status.value if position else "Disconnected"
    
    @property
    def current_position(self) -> Optional[Dict[str, Any]]:
        return self.get_current_position()
    
    def get_track_data(self) -> Dict[str, Any]:
        return {"session_id": "", "points": []}
