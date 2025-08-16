from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

class RTKStatus(Enum):
    DISCONNECTED = "Disconnected"
    GPS_ONLY = "GPS Only"
    RTK_CONNECTED = "RTK Connected"
    NO_FIX = "No Fix"
    SINGLE = "Single"
    DGPS = "DGPS"
    RTK_FLOAT = "RTK Float"
    RTK_FIXED = "RTK Fixed"

@dataclass
class Position:
    lat: float
    lon: float
    altitude: float
    satellites: int
    hdop: float
    rtk_status: RTKStatus
    timestamp: str

@dataclass
class RTKStats:
    rtcm_messages: int
    nmea_errors: int
    connection_uptime: float
    avg_latency: float

class GPS(ABC):
    @abstractmethod
    def connect(self) -> bool: pass
    
    @abstractmethod
    def read_position(self) -> Optional[Position]: pass
    
    @abstractmethod
    def write_rtcm(self, data: bytes) -> bool: pass
    
    @abstractmethod
    def close(self): pass
    
    @abstractmethod
    def is_connected(self) -> bool: pass

class NTRIPService(ABC):
    @abstractmethod
    def connect(self) -> bool: pass
    
    @abstractmethod
    def send_gga(self, gga_data: bytes) -> bool: pass
    
    @abstractmethod
    def get_rtcm_data(self) -> List[bytes]: pass
    
    @abstractmethod
    def disconnect(self): pass
    
    @abstractmethod
    def is_connected(self) -> bool: pass

class PositionObserver(ABC):
    @abstractmethod
    def on_position_update(self, position: Position): pass

class RTKSystemInterface(ABC):
    @abstractmethod
    def start(self) -> bool: pass
    
    @abstractmethod
    def stop(self): pass
    
    @abstractmethod
    def get_status(self) -> RTKStats: pass
    
    @abstractmethod
    def get_current_position(self) -> Optional[Position]: pass
    
    @abstractmethod
    def add_position_observer(self, observer: PositionObserver): pass
